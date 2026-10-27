"""Deterministic ranking and price-change detection (no LLM math)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain_core.tools import tool

from agent.config import W_AFFORDABILITY, W_FIT, W_PRICE_VS_MARKET
from agent.schemas import PriceChange, PricePoint, PropertyRecord, ScoreBreakdown, UserProfile
from agent.tools.memory import load_all_properties, load_profile, save_property_record


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_price_vs_market(
    asking: float,
    fair_value: float | None,
    renovation_cost: float = 0.0,
) -> float:
    """1.0 = great deal vs fair value + reno; 0.0 = badly overpriced."""
    if fair_value is None or fair_value <= 0:
        return 0.5
    effective = asking + max(0.0, renovation_cost)
    # ratio < 1 means under fair value
    ratio = effective / fair_value
    # map ratio 0.7 -> 1.0, 1.0 -> 0.7, 1.3 -> 0.0 roughly
    return _clamp01(1.0 - (ratio - 0.7) / 0.6)


def score_affordability(
    monthly_payment: float | None,
    max_monthly: float,
    affordable: bool | None = None,
) -> float:
    if monthly_payment is None or max_monthly <= 0:
        return 0.5 if affordable is not False else 0.2
    if monthly_payment <= 0:
        return 1.0
    ratio = monthly_payment / max_monthly
    # at or under budget -> high; 1.5x budget -> ~0
    return _clamp01(1.15 - ratio * 0.75)


def score_fit(rec: PropertyRecord, profile: UserProfile) -> float:
    listing = rec.listing
    parts: list[float] = []

    # rooms
    if profile.rooms_min <= listing.rooms <= profile.rooms_max:
        parts.append(1.0)
    elif listing.rooms < profile.rooms_min:
        parts.append(_clamp01(1.0 - (profile.rooms_min - listing.rooms) * 0.35))
    else:
        parts.append(_clamp01(1.0 - (listing.rooms - profile.rooms_max) * 0.2))

    # district
    if not profile.districts:
        parts.append(0.7)
    else:
        wanted = {d.lower() for d in profile.districts}
        parts.append(1.0 if listing.district.lower() in wanted else 0.35)

    # condition / renovation
    if rec.condition_score is not None:
        parts.append(_clamp01(rec.condition_score))
    else:
        cond = (listing.condition or "").lower()
        if "renovat" in cond or "sanier" in cond:
            parts.append(0.45)
        elif "gut" in cond or "good" in cond or "renoviert" in cond:
            parts.append(0.85)
        else:
            parts.append(0.65)

    # budget ceiling soft fit
    if listing.price <= profile.budget:
        parts.append(1.0)
    else:
        over = (listing.price - profile.budget) / max(profile.budget, 1.0)
        parts.append(_clamp01(1.0 - over * 1.5))

    return sum(parts) / len(parts)


def compute_scores(rec: PropertyRecord, profile: UserProfile) -> ScoreBreakdown:
    pvm = score_price_vs_market(rec.listing.price, rec.fair_value, rec.renovation_cost)
    aff = score_affordability(rec.monthly_payment, profile.max_monthly, rec.affordable)
    fit = score_fit(rec, profile)
    total = W_PRICE_VS_MARKET * pvm + W_AFFORDABILITY * aff + W_FIT * fit
    return ScoreBreakdown(
        price_vs_market=round(pvm, 4),
        affordability=round(aff, 4),
        fit=round(fit, 4),
        total=round(total, 4),
    )


def rank_properties(
    records: list[PropertyRecord],
    profile: UserProfile,
) -> list[PropertyRecord]:
    scored: list[PropertyRecord] = []
    for rec in records:
        if rec.status == "rejected":
            rec.scores = compute_scores(rec, profile)
            rec.rank = None
            scored.append(rec)
            continue
        rec.scores = compute_scores(rec, profile)
        scored.append(rec)

    active = [r for r in scored if r.status != "rejected"]
    active.sort(key=lambda r: (r.scores.total if r.scores else 0.0), reverse=True)
    for i, rec in enumerate(active, start=1):
        rec.rank = i
    return scored


def apply_price_updates(
    records: list[PropertyRecord],
    price_map: dict[str, float],
) -> list[PriceChange]:
    """Update stored prices from a fresh scan. Returns detected changes."""
    changes: list[PriceChange] = []
    today = date.today().isoformat()
    by_id = {r.listing.listing_id: r for r in records}
    for listing_id, new_price in price_map.items():
        rec = by_id.get(listing_id)
        if rec is None:
            continue
        old = rec.listing.price
        if abs(old - new_price) < 1.0:
            continue
        rec.listing.price = new_price
        rec.price_history.append(PricePoint(date=today, price=new_price))
        changes.append(
            PriceChange(
                listing_id=listing_id,
                title=rec.listing.title,
                old_price=old,
                new_price=new_price,
                delta=new_price - old,
                old_rank=rec.rank,
            )
        )
    return changes


def format_price_alert(change: PriceChange) -> str:
    direction = "drop" if change.delta < 0 else "increase"
    amount = abs(change.delta)
    rank_bit = ""
    if change.old_rank is not None and change.new_rank is not None:
        rank_bit = f", now rank #{change.new_rank} (was #{change.old_rank})"
    elif change.new_rank is not None:
        rank_bit = f", now rank #{change.new_rank}"
    return (
        f"Price {direction} EUR {amount:,.0f} on {change.title} "
        f"({change.listing_id}){rank_bit}"
    )


@tool
def score_and_rank(user_id: str, price_updates_json: str = "") -> str:
    """Recompute scores and ranks for all stored properties of a user.

    Optionally pass price_updates_json as {"listing_id": new_price, ...} to apply
    price changes first. Returns ranked compact cards plus any Telegram-ready alerts
    for price drops (caller should send_telegram for each alert).
    """
    profile = load_profile(user_id)
    if profile is None:
        return json.dumps({"ok": False, "error": "no_profile"})

    records = load_all_properties(user_id)
    if not records:
        return json.dumps({"ok": True, "ranked": [], "price_alerts": [], "changes": []})

    old_ranks = {r.listing.listing_id: r.rank for r in records}
    changes: list[PriceChange] = []
    if price_updates_json.strip():
        price_map = json.loads(price_updates_json)
        if not isinstance(price_map, dict):
            return json.dumps({"ok": False, "error": "price_updates_json must be an object"})
        changes = apply_price_updates(records, {str(k): float(v) for k, v in price_map.items()})

    ranked = rank_properties(records, profile)
    for rec in ranked:
        save_property_record(user_id, rec)

    new_ranks = {r.listing.listing_id: r.rank for r in ranked}
    alerts: list[str] = []
    change_payload: list[dict[str, Any]] = []
    for ch in changes:
        ch.new_rank = new_ranks.get(ch.listing_id)
        if ch.old_rank is None:
            ch.old_rank = old_ranks.get(ch.listing_id)
        ch.alert = format_price_alert(ch)
        change_payload.append(ch.model_dump())
        if ch.delta < 0:
            alerts.append(ch.alert)

    cards = []
    for rec in sorted(
        [r for r in ranked if r.status != "rejected"],
        key=lambda r: r.rank or 999,
    ):
        cards.append(
            {
                "rank": rec.rank,
                "listing_id": rec.listing.listing_id,
                "title": rec.listing.title,
                "district": rec.listing.district,
                "price": rec.listing.price,
                "rooms": rec.listing.rooms,
                "sqm": rec.listing.sqm,
                "status": rec.status,
                "scores": rec.scores.model_dump() if rec.scores else None,
                "monthly_payment": rec.monthly_payment,
                "fair_value": rec.fair_value,
                "negotiation_target": rec.negotiation_target,
                "insight_summary": rec.insight_summary[:200],
                "url": rec.listing.url,
            }
        )

    return json.dumps(
        {
            "ok": True,
            "count": len(cards),
            "ranked": cards,
            "changes": change_payload,
            "price_alerts": alerts,
            "weights": {
                "price_vs_market": W_PRICE_VS_MARKET,
                "affordability": W_AFFORDABILITY,
                "fit": W_FIT,
            },
        },
        ensure_ascii=False,
    )


@tool
def filter_new_listings(user_id: str, listings_json: str) -> str:
    """Given a JSON array of Listing objects, return only ones not already in memory."""
    try:
        payload = json.loads(listings_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": f"invalid_json: {exc}"})
    if not isinstance(payload, list):
        return json.dumps({"ok": False, "error": "listings_json must be a JSON array"})

    seen = {r.listing.listing_id for r in load_all_properties(user_id)}
    fresh = []
    known = []
    for raw in payload:
        lid = str(raw.get("listing_id", ""))
        if not lid:
            continue
        if lid in seen:
            known.append(lid)
        else:
            fresh.append(raw)
    return json.dumps(
        {
            "ok": True,
            "new_count": len(fresh),
            "known_count": len(known),
            "new_listings": fresh,
            "known_ids": known,
        },
        ensure_ascii=False,
    )


RANKING_TOOLS = [score_and_rank, filter_new_listings]
