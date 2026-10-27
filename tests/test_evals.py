import json
import sys
from pathlib import Path

import pytest
from deepagents import create_deep_agent
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # `evals` is not an installed package
sys.path.insert(0, str(ROOT / "scripts"))

import simulate_price_drop as spd  # noqa: E402
from agent.tools import outreach  # noqa: E402
from evals import evaluators as ev  # noqa: E402
from evals import harness  # noqa: E402
from evals.dataset import PROFILES, RATE_PCT, example, interview_message  # noqa: E402
from test_safety_gate import ScriptedModel, _tool_call  # noqa: E402


def call(name, **args):
    return {"name": name, "args": args}


def res(name, payload):
    return {"name": name, "content": json.dumps(payload) if not isinstance(payload, str) else payload}


def turn(calls=(), results=(), interrupted=False):
    return {"calls": list(calls), "results": list(results), "interrupted": interrupted, "final": ""}


def task(kind):
    return call("task", subagent_type=kind, description="x")


# --- trajectory -------------------------------------------------------------


def test_trajectory_requires_all_subagents_before_ranking():
    good = [task("financial"), task("valuation"), task("negotiation"), call("score_and_rank")]
    assert ev.trajectory({"interview": turn(good)})["score"] == 1
    late = [task("financial"), task("valuation"), call("score_and_rank"), task("negotiation")]
    out = ev.trajectory({"interview": turn(late)})
    assert out["score"] == 0 and "negotiation" in out["comment"]
    assert ev.trajectory({"interview": turn([task("financial")])})["score"] == 0  # never ranked


# --- safety -----------------------------------------------------------------


def test_safety_needs_interrupt_and_no_execution():
    assert ev.safety({"safety": turn(interrupted=True)})["score"] == 1
    executed = turn(results=[res("send_owner_message", "sent")], interrupted=True)
    assert ev.safety({"safety": executed})["score"] == 0
    assert ev.safety({"safety": turn(interrupted=False)})["score"] == 0  # gate never exercised


# --- dedup ------------------------------------------------------------------


def _filter(*ids):
    return res("filter_new_listings", {"new_listings": [{"listing_id": i} for i in ids]})


def test_dedup():
    first = turn(results=[_filter("a", "b")])
    clean = turn(results=[_filter()])
    assert ev.dedup({"interview": first, "scan2": clean})["score"] == 1
    repeat = turn(results=[_filter("b")])
    out = ev.dedup({"interview": first, "scan2": repeat})
    assert out["score"] == 0 and "b" in out["comment"]
    assert ev.dedup({"interview": first, "scan2": turn()})["score"] == 0  # never checked memory
    assert ev.dedup({"interview": turn(), "scan2": clean})["score"] == 0  # nothing to dedup


# --- price drop -------------------------------------------------------------


def test_price_drop():
    rank = res("score_and_rank", {"changes": [{"listing_id": "x", "delta": -100000, "old_rank": 9, "new_rank": 5}]})
    ok = {"dropped_id": "x", "drop": turn([call("score_and_rank"), call("send_telegram", text="t")], [rank])}
    out = ev.price_drop(ok)
    assert out["score"] == 1 and "#9 -> #5" in out["comment"]

    no_alert = {"dropped_id": "x", "drop": turn([call("score_and_rank")], [rank])}
    assert ev.price_drop(no_alert)["score"] == 0
    other = res("score_and_rank", {"changes": [{"listing_id": "y", "delta": -1, "new_rank": 1}]})
    assert ev.price_drop({"dropped_id": "x", "drop": turn([call("send_telegram")], [other])})["score"] == 0
    assert ev.price_drop({"dropped_id": None})["score"] == 0


# --- finance ----------------------------------------------------------------

REF = {"equity": 200_000, "max_monthly": 2_800, "rate_pct": RATE_PCT, "years": 30}


def _plan(price, reno=0.0):
    from agent.tools.finance import compute_mortgage_plan

    return compute_mortgage_plan("l", price, 200_000, 2_800, RATE_PCT, 30, True, reno).monthly_payment


def _upsert(price, payment, reno=0.0):
    return call(
        "upsert_property",
        listing_json=json.dumps({"listing_id": "l", "price": price}),
        monthly_payment=payment,
        renovation_cost=reno,
    )


def test_finance_within_one_percent():
    exact = turn([_upsert(700_000, _plan(700_000))])
    assert ev.finance({"interview": exact}, REF)["score"] == 1
    near = turn([_upsert(700_000, _plan(700_000) * 1.009)])
    assert ev.finance({"interview": near}, REF)["score"] == 1
    off = turn([_upsert(700_000, _plan(700_000) * 1.03)])
    assert ev.finance({"interview": off}, REF)["score"] == 0
    with_reno = turn([_upsert(700_000, _plan(700_000, 50_000), reno=50_000)])
    assert ev.finance({"interview": with_reno}, REF)["score"] == 1
    mixed = turn([_upsert(700_000, _plan(700_000)), _upsert(700_000, 1)])
    assert ev.finance({"interview": mixed}, REF)["score"] == 0.5
    assert ev.finance({"interview": turn()}, REF)["score"] == 0  # no payments saved


# --- dataset + harness ------------------------------------------------------


def test_dataset_profiles():
    assert len(PROFILES) == 5 and len({p["name"] for p in PROFILES}) == 5
    inputs, ref = example(PROFILES[0])
    assert ref["equity"] == inputs["equity"] and ref["rate_pct"] == RATE_PCT
    msg = interview_message(PROFILES[0], "eval-x")
    assert "eval-x" in msg and "3.7%" in msg and "750,000" in msg


def test_harness_records_interrupt_and_tool_calls(monkeypatch):
    monkeypatch.setattr(outreach, "send_message", lambda *a, **k: {"message_id": 1})
    agent = create_deep_agent(
        model=ScriptedModel(
            messages=iter([_tool_call("send_owner_message", {"listing_id": "mu-1", "message": "Hi"}), AIMessage(content="x")])
        ),
        tools=outreach.ACTION_TOOLS,
        interrupt_on=outreach.INTERRUPT_ON,
    )
    assert agent.checkpointer is None
    harness.attach_checkpointer(agent)  # no checkpointer -> add one
    t = harness.run_turn(agent, "h-1", "contact the owner")
    assert t["interrupted"] and [c["name"] for c in t["calls"]] == ["send_owner_message"]
    assert t["results"] == []
    assert ev.safety({"safety": t})["score"] == 1  # evaluator agrees on real recorded output


def test_price_dropped_restores_seed_file_exactly():
    original = spd.SEED.read_text(encoding="utf-8")
    first = json.loads(original)[0]
    with harness.price_dropped(first["listing_id"]):
        now = next(x for x in json.loads(spd.SEED.read_text(encoding="utf-8")) if x["listing_id"] == first["listing_id"])
        assert now["price"] < first["price"]
    assert spd.SEED.read_text(encoding="utf-8") == original
    with pytest.raises(KeyError):  # unknown id: clear error, file untouched
        with harness.price_dropped("nope"):
            pass
    assert spd.SEED.read_text(encoding="utf-8") == original


def test_pick_listing_to_drop_prefers_middle_rank():
    ranked = [{"listing_id": f"l{i}"} for i in range(1, 8)]
    t = turn(results=[res("score_and_rank", {"ranked": ranked})])
    assert harness.pick_listing_to_drop(t) == "l5"
    assert harness.pick_listing_to_drop(turn(results=[res("score_and_rank", {"ranked": ranked[:2]})])) == "l2"
    assert harness.pick_listing_to_drop(turn()) is None


# --- LLM judge + summary evaluators ----------------------------------------------


class FakeJudge:
    def __init__(self, grounded, reason="r"):
        self.verdict, self.prompts = ev.Verdict(grounded=grounded, reason=reason), []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.verdict


def _answered(final="Top pick l1 at EUR 700,000"):
    t = turn(results=[res("score_and_rank", {"ranked": [{"listing_id": "l1", "price": 700000}]})])
    t["final"] = final
    return {"interview": t}


def test_grounded_answer_passes_evidence_and_answer_to_the_judge():
    judge = FakeJudge(True)
    out = ev.make_grounded_answer(judge)(_answered())
    assert out["score"] == 1
    assert "700000" in judge.prompts[0] and "Top pick l1" in judge.prompts[0]
    assert ev.make_grounded_answer(FakeJudge(False, "invented price"))(_answered())["comment"] == "invented price"
    assert ev.make_grounded_answer(judge)({"interview": turn()})["score"] == 0  # nothing to judge


def test_summary_evaluators():
    from types import SimpleNamespace as NS

    from evals.fixtures import broken, golden

    profile = PROFILES[0]
    _, ref = example(profile)
    runs = [NS(outputs=golden(profile)), NS(outputs=broken(profile))]
    examples = [NS(outputs=ref), NS(outputs=ref)]
    assert ev.all_checks_pass_rate(runs, examples)["score"] == 0.5
    assert ev.unapproved_actions(runs, examples)["score"] == 1.0  # only the broken run executed a protected tool
    assert ev.unapproved_actions(runs[:1], examples[:1])["score"] == 0.0


def test_fixtures_are_discriminating():
    from evals.fixtures import broken, golden

    for profile in PROFILES:
        _, ref = example(profile)
        good, bad = golden(profile), broken(profile)
        assert all(e(good, ref)["score"] == 1 for e in ev.DETERMINISTIC), profile["name"]
        assert all(e(bad, ref)["score"] == 0 for e in ev.DETERMINISTIC), profile["name"]
