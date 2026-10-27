"""Run each Person B subagent standalone on a seed listing and validate its JSON.

Usage: python scripts/test_subagents.py [listing_id]   (needs OPENAI_API_KEY in .env)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from langchain.agents import create_agent

from agent.schemas import FinanceResult, NegotiationResult, ValuationResult
from agent.subagents import SUBAGENTS
from agent.tools.finance import compute_mortgage_plan
from agent.tools.listings import load_seed_listings

RESULT_MODELS = {
    "financial": FinanceResult,
    "valuation": ValuationResult,
    "negotiation": NegotiationResult,
}
BUYER = {"equity": 180_000, "monthly_max": 2_800}


def extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in reply: {text[:200]!r}")
    return match.group(0)


def task_for(name: str, listing_json: str, listing_id: str, price: float) -> str:
    if name == "financial":
        return (
            f"Mortgage plan for listing_id={listing_id}, price={price:.0f} EUR. "
            f"Buyer equity {BUYER['equity']} EUR, max monthly payment {BUYER['monthly_max']} EUR."
        )
    return f"Analyse this listing:\n{listing_json}"


def main() -> int:
    listing_id = sys.argv[1] if len(sys.argv) > 1 else "mu-schwabing-04"
    listing = next(l for l in load_seed_listings() if l.listing_id == listing_id)
    listing_json = listing.model_dump_json()
    failures = 0

    for spec in SUBAGENTS:
        name = spec["name"]
        agent = create_agent(model=spec["model"], tools=spec["tools"], system_prompt=spec["system_prompt"])
        out = agent.invoke(
            {"messages": [{"role": "user", "content": task_for(name, listing_json, listing_id, listing.price)}]}
        )
        reply = out["messages"][-1].content
        if isinstance(reply, list):
            reply = "".join(part.get("text", "") for part in reply if isinstance(part, dict))
        try:
            result = RESULT_MODELS[name].model_validate_json(extract_json(reply))
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {exc}")
            continue

        if name == "financial":
            expected = compute_mortgage_plan(listing_id, listing.price, rate_pct=result.rate, **BUYER)
            if abs(result.monthly_payment - expected.monthly_payment) > expected.monthly_payment * 0.01:
                failures += 1
                print(f"[FAIL] financial: monthly {result.monthly_payment} != tool {expected.monthly_payment}")
                continue
        print(f"[OK]   {name}: {json.dumps(result.model_dump(mode='json'), ensure_ascii=False)[:300]}")

    print("all subagents OK" if not failures else f"{failures} subagent(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
