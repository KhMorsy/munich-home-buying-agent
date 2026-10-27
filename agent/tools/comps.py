"""Comparable sales, valuation and negotiation numbers (Person B).

All numbers here are deterministic so the subagents explain them instead of guessing.
"""

from __future__ import annotations

import json
from statistics import median
from typing import Any

from langchain_core.tools import tool

from agent.config import ROOT
from agent.schemas import CompSale, Listing, NegotiationResult, ValuationResult

SEED_SOLD_PATH = ROOT / "data" / "seed_sold_history.json"

# Munich fallback EUR/m² when a district has no comps
CITY_AVG_PER_SQM = 10_200

# condition -> (condition_score 0-1, renovation EUR per m²)
CONDITION_TABLE: dict[str, tuple[float, float]] = {
    "new": (0.95, 0),
    "renovated": (0.9, 0),
    "good": (0.75, 0),
    "dated": (0.55, 350),
    "needs_renovation": (0.3, 900),
    "unknown": (0.6, 150),
}


def normalize_condition(condition: str) -> str:
    c = (condition or "").strip().lower().replace(" ", "_").replace("-", "_")
    if c in CONDITION_TABLE:
        return c
    if "sanier" in c or "needs" in c or "renovation" in c or "renovierungs" in c:
        return "needs_renovation"
    if "renoviert" in c or "renovated" in c:
        return "renovated"
    if "neu" in c or "new" in c or "erstbezug" in c:
        return "new"
    if "dated" in c or "auffrischen" in c or "original" in c:
        return "dated"
    if "gut" in c or "good" in c or "gepflegt" in c:
        return "good"
    return "unknown"


def load_sold_history() -> list[dict[str, Any]]:
    return json.loads(SEED_SOLD_PATH.read_text(encoding="utf-8"))


def select_comps(listing: Listing, max_results: int = 5) -> list[dict[str, Any]]:
    """Same-district sales closest in size (falls back to all of Munich)."""
    sold = load_sold_history()
    pool = [s for s in sold if s["district"].lower() == listing.district.lower()] or sold
    pool.sort(key=lambda s: (abs(s["sqm"] - listing.sqm), abs(s["rooms"] - listing.rooms)))
    return pool[:max_results]


def district_avg_per_sqm(district: str) -> float:
    rows = [s for s in load_sold_history() if s["district"].lower() == district.lower()]
    if not rows:
        return CITY_AVG_PER_SQM
    return round(median(s["price"] / s["sqm"] for s in rows), 0)


def size_factor(sqm: float) -> float:
    """Small flats sell for more per m², big ones for less."""
    if sqm < 45:
        return 1.05
    if sqm > 110:
        return 0.95
    return 1.0


def compute_valuation(listing: Listing) -> ValuationResult:
    """Fair value of the flat in good / renovated condition, plus the cost to get it there."""
    cond = normalize_condition(listing.condition)
    condition_score, reno_per_sqm = CONDITION_TABLE[cond]
    comps = select_comps(listing)
    comp_psqm = median(c["price"] / c["sqm"] for c in comps)
    district_avg = district_avg_per_sqm(listing.district)

    premium = 1.0
    if cond == "new" or (listing.year_built or 0) >= 2015:
        premium = 1.08
    elif cond == "renovated":
        premium = 1.03

    fair_value = comp_psqm * listing.sqm * size_factor(listing.sqm) * premium
    renovation_cost = reno_per_sqm * listing.sqm
    price_per_sqm = listing.price / listing.sqm
    gap = (listing.price + renovation_cost) / fair_value - 1

    verdict = "fairly priced"
    if gap > 0.08:
        verdict = "overpriced"
    elif gap < -0.05:
        verdict = "below market"
    summary = (
        f"{verdict.capitalize()}: asking EUR {price_per_sqm:,.0f}/m² vs comps EUR {comp_psqm:,.0f}/m² "
        f"(district median EUR {district_avg:,.0f}/m², {len(comps)} sales). "
        f"Fair value EUR {fair_value:,.0f}"
        + (f", renovation est. EUR {renovation_cost:,.0f} ({cond})." if renovation_cost else ".")
    )
    return ValuationResult(
        listing_id=listing.listing_id,
        fair_value=round(fair_value, -3),
        price_per_sqm=round(price_per_sqm, 0),
        district_avg_per_sqm=district_avg,
        renovation_needed=reno_per_sqm >= 900,
        renovation_cost=round(renovation_cost, -2),
        condition_score=condition_score,
        summary=summary,
    )


def compute_negotiation(listing: Listing) -> NegotiationResult:
    """Target price from comps minus renovation: always ask 3-12% off."""
    valuation = compute_valuation(listing)
    comps = select_comps(listing)
    comp_psqm = median(c["price"] / c["sqm"] for c in comps)
    comp_value = valuation.fair_value - valuation.renovation_cost
    asking = listing.price

    target = round(min(asking * 0.97, max(comp_value, asking * 0.88)), -3)
    discount = (asking - target) / asking * 100

    arguments = [
        f"Comparable sales in {listing.district} average EUR {comp_psqm:,.0f}/m²; "
        f"this listing asks EUR {asking / listing.sqm:,.0f}/m².",
    ]
    if valuation.renovation_cost:
        arguments.append(
            f"Renovation needed (~EUR {valuation.renovation_cost:,.0f}) should come off the price."
        )
    if asking > valuation.fair_value * 1.08:
        arguments.append("Asking price is clearly above recent sales; expect it to sit on the market.")
    if listing.year_built and listing.year_built < 1980 and normalize_condition(listing.condition) != "renovated":
        arguments.append(f"Built {listing.year_built}: energy upgrades (windows/heating) are likely due.")
    if "no balcony" in listing.description.lower() or "busy road" in listing.description.lower():
        arguments.append("Location/amenity drawbacks (no balcony or a busy road) limit the buyer pool.")
    arguments.append("Financing is prepared; a quick, certain closing is worth a discount to the seller.")

    return NegotiationResult(
        listing_id=listing.listing_id,
        comps=[
            CompSale(price=c["price"], sqm=c["sqm"], date=c["date"], district=c["district"], address=c["address"])
            for c in comps
        ],
        target_price=target,
        max_discount_pct=round(discount, 1),
        arguments=arguments,
    )


def _parse_listing(listing_json: str) -> Listing:
    return Listing.model_validate_json(listing_json)


@tool
def find_comparables(listing_json: str, max_results: int = 5) -> str:
    """Recent comparable sales for a listing plus a deterministic negotiation target.

    listing_json: a Listing object as JSON. Returns NegotiationResult JSON
    (comps, target_price, max_discount_pct, arguments).
    """
    try:
        listing = _parse_listing(listing_json)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"invalid listing_json: {exc}"})
    result = compute_negotiation(listing)
    result.comps = result.comps[: max(1, int(max_results))]
    return result.model_dump_json()


@tool
def estimate_valuation(listing_json: str) -> str:
    """Fair value, EUR/m² vs district, renovation need and cost for a listing.

    listing_json: a Listing object as JSON. Returns ValuationResult JSON.
    """
    try:
        listing = _parse_listing(listing_json)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"invalid listing_json: {exc}"})
    return compute_valuation(listing).model_dump_json()


COMPS_TOOLS = [find_comparables, estimate_valuation]
