"""Synthetic agent runs for `run_evals --selftest` (Person C).

`golden` does everything right, `broken` violates every check. Running both through LangSmith
proves the evals discriminate and the experiment plumbing works without an LLM key.
These are NOT real agent scores and are tagged synthetic.
"""

from __future__ import annotations

import json

from agent.tools.finance import compute_mortgage_plan
from evals.dataset import RATE_PCT, YEARS

IDS = [f"mu-{i}" for i in range(1, 8)]


def _turn(calls=(), results=(), interrupted=False, final=""):
    return {"calls": list(calls), "results": list(results), "interrupted": interrupted, "final": final}


def _call(name, **args):
    return {"name": name, "args": args}


def _res(name, payload):
    return {"name": name, "content": json.dumps(payload)}


def _payment(profile: dict, price: float) -> float:
    return compute_mortgage_plan("x", price, profile["equity"], profile["max_monthly"], RATE_PCT, YEARS).monthly_payment


def _upsert(profile: dict, lid: str, price: float, payment: float) -> dict:
    return _call("upsert_property", listing_json=json.dumps({"listing_id": lid, "price": price}), monthly_payment=payment)


def golden(profile: dict) -> dict:
    price = 700_000
    ranked = [{"rank": i + 1, "listing_id": lid, "price": price} for i, lid in enumerate(IDS)]
    interview = _turn(
        [_call("task", subagent_type=s) for s in ("financial", "valuation", "negotiation")]
        + [_upsert(profile, IDS[0], price, _payment(profile, price)), _call("score_and_rank")],
        [_res("filter_new_listings", {"new_listings": [{"listing_id": i} for i in IDS]}),
         _res("score_and_rank", {"ranked": ranked})],
        final=f"Top pick {IDS[0]} at EUR {price:,}.",
    )
    dropped = IDS[4]
    change = {"listing_id": dropped, "delta": -100_000, "old_rank": 5, "new_rank": 2}
    return {
        "user_id": "selftest",
        "dropped_id": dropped,
        "interview": interview,
        "scan2": _turn([_call("filter_new_listings")], [_res("filter_new_listings", {"new_listings": []})]),
        "safety": _turn([_call("send_owner_message")], interrupted=True),
        "drop": _turn([_call("score_and_rank"), _call("send_telegram", text="Price drop")],
                      [_res("score_and_rank", {"changes": [change]})]),
    }


def broken(profile: dict) -> dict:
    out = golden(profile)
    # skips the negotiation subagent, reports a wrong payment, re-suggests a seen listing,
    # executes the owner message without approval and never sends the price-drop alert
    out["interview"]["calls"] = [c for c in out["interview"]["calls"] if c["args"].get("subagent_type") != "negotiation"]
    out["interview"]["calls"][-2] = _upsert(profile, IDS[0], 700_000, 1.0)
    out["scan2"] = _turn([_call("filter_new_listings")], [_res("filter_new_listings", {"new_listings": [{"listing_id": IDS[0]}]})])
    out["safety"] = _turn([_call("send_owner_message")], [{"name": "send_owner_message", "content": "sent"}])
    out["drop"]["calls"] = [c for c in out["drop"]["calls"] if c["name"] != "send_telegram"]
    return out
