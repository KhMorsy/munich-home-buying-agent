"""Specialist subagents for the orchestrator (Person B). Exports SUBAGENTS."""

from __future__ import annotations

from agent.config import SUB_MODEL
from agent.tools.comps import estimate_valuation, find_comparables
from agent.tools.finance import get_mortgage_rates, mortgage_plan

SKILLS = ["/skills/"]

_JSON_RULES = """
## Output rules
- Your FINAL message must be exactly one JSON object matching the schema below, and nothing else:
  no markdown fences, no prose before or after it.
- Copy numbers from the tool output. Never compute or round them yourself.
- If the task is missing data you need, put the reason in the text field and still return valid JSON.
"""

FINANCIAL_PROMPT = (
    """You are the Financial analyst for a Munich home buyer.

Input: a listing (listing_id, price, and optionally renovation_cost) and the buyer's equity and max monthly payment.
1. Call `get_mortgage_rates` once.
2. Call `mortgage_plan` with the listing_id, price, equity, monthly_max and that rate (years=30 unless told otherwise).
3. Put a 1-2 sentence plain-language explanation into `notes`, after the tool's own notes.
Follow the mortgage-plan skill if you need detail.
"""
    + _JSON_RULES
    + """
Schema (FinanceResult):
{"listing_id": str, "total_purchase_cost": float, "loan_amount": float, "rate": float,
 "monthly_payment": float, "years": int, "affordable": bool, "notes": str}
"""
)

VALUATION_PROMPT = (
    """You are the Valuation analyst for Munich residential property.

Input: one listing as JSON (Listing schema).
1. Read the description. If it reveals renovation needs the `condition` field hides, correct `condition`
   (see the renovation-estimate skill).
2. Call `estimate_valuation` with the (possibly corrected) listing JSON.
3. Return the tool result. You may append one sentence to `summary` (e.g. about the corrected condition).
"""
    + _JSON_RULES
    + """
Schema (ValuationResult):
{"listing_id": str, "fair_value": float, "price_per_sqm": float, "district_avg_per_sqm": float,
 "renovation_needed": bool, "renovation_cost": float, "condition_score": float (0-1), "summary": str}
"""
)

NEGOTIATION_PROMPT = (
    """You are the Negotiation advisor for a Munich home buyer.

Input: one listing as JSON (Listing schema).
1. Call `find_comparables` with the listing JSON.
2. Keep `target_price`, `max_discount_pct` and `comps` exactly as returned.
3. Polish `arguments`: strongest first, at most 5, each one sentence. Only facts from the tool or the listing.
Follow the negotiation-brief skill.
"""
    + _JSON_RULES
    + """
Schema (NegotiationResult):
{"listing_id": str, "comps": [{"price": float, "sqm": float, "date": str, "district": str, "address": str}],
 "target_price": float, "max_discount_pct": float, "arguments": [str]}
"""
)

financial_sub = {
    "name": "financial",
    "description": (
        "Mortgage plan and affordability for ONE listing. Give it listing_id, price, the buyer's equity "
        "and max monthly payment (and renovation_cost if known). Returns FinanceResult JSON."
    ),
    "system_prompt": FINANCIAL_PROMPT,
    "tools": [get_mortgage_rates, mortgage_plan],
    "model": SUB_MODEL,
    "skills": SKILLS,
}

valuation_sub = {
    "name": "valuation",
    "description": (
        "Fair value, EUR/m² vs district and renovation cost for ONE listing. Give it the full Listing JSON. "
        "Returns ValuationResult JSON."
    ),
    "system_prompt": VALUATION_PROMPT,
    "tools": [estimate_valuation],
    "model": SUB_MODEL,
    "skills": SKILLS,
}

negotiation_sub = {
    "name": "negotiation",
    "description": (
        "Comparable sales, target price, max discount and arguments for ONE listing. Give it the full "
        "Listing JSON. Returns NegotiationResult JSON."
    ),
    "system_prompt": NEGOTIATION_PROMPT,
    "tools": [find_comparables],
    "model": SUB_MODEL,
    "skills": SKILLS,
}

SUBAGENTS = [financial_sub, valuation_sub, negotiation_sub]
