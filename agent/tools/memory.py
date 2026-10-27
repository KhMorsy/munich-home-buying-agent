"""Long-term memory tools backed by the LangGraph Store.

Namespaces:
  ("users", user_id)      key "profile"
  ("properties", user_id) key listing_id
  ("runs", user_id)       key YYYY-MM-DD
  ("insights", user_id)   key listing_id  (long text, loaded on demand)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from langchain_core.tools import tool

from agent.config import STATUS_PIPELINE
from agent.schemas import (
    Listing,
    PricePoint,
    PropertyRecord,
    PropertyStatus,
    RunLog,
    UserProfile,
)
from agent.tools.store_util import get_agent_store, get_json, list_json, put_json


def _users_ns(user_id: str) -> tuple[str, ...]:
    return ("users", user_id)


def _props_ns(user_id: str) -> tuple[str, ...]:
    return ("properties", user_id)


def _runs_ns(user_id: str) -> tuple[str, ...]:
    return ("runs", user_id)


def _insights_ns(user_id: str) -> tuple[str, ...]:
    return ("insights", user_id)


def _now() -> str:
    return datetime.utcnow().isoformat()


def _compact_property(rec: PropertyRecord) -> dict[str, Any]:
    listing = rec.listing
    return {
        "listing_id": listing.listing_id,
        "title": listing.title,
        "district": listing.district,
        "sqm": listing.sqm,
        "rooms": listing.rooms,
        "price": listing.price,
        "status": rec.status,
        "rank": rec.rank,
        "scores": rec.scores.model_dump() if rec.scores else None,
        "monthly_payment": rec.monthly_payment,
        "affordable": rec.affordable,
        "fair_value": rec.fair_value,
        "renovation_cost": rec.renovation_cost,
        "negotiation_target": rec.negotiation_target,
        "insight_summary": rec.insight_summary[:280],
        "url": listing.url,
    }


@tool
def save_profile(
    user_id: str,
    budget: float,
    equity: float,
    max_monthly: float,
    rooms_min: float = 2.0,
    rooms_max: float = 5.0,
    districts: str = "",
    must_haves: str = "",
    property_type: str = "apartment",
) -> str:
    """Save or update the buyer's profile in long-term memory.

    districts and must_haves are comma-separated strings.
    """
    profile = UserProfile(
        user_id=user_id,
        budget=budget,
        equity=equity,
        max_monthly=max_monthly,
        rooms_min=rooms_min,
        rooms_max=rooms_max,
        districts=[d.strip() for d in districts.split(",") if d.strip()],
        must_haves=[m.strip() for m in must_haves.split(",") if m.strip()],
        property_type=property_type,
        updated_at=_now(),
    )
    store = get_agent_store()
    put_json(store, _users_ns(user_id), "profile", profile.model_dump())
    return json.dumps({"ok": True, "profile": profile.model_dump()}, ensure_ascii=False)


@tool
def get_profile(user_id: str) -> str:
    """Load the buyer's saved profile. Returns empty if none yet."""
    store = get_agent_store()
    data = get_json(store, _users_ns(user_id), "profile")
    if not data:
        return json.dumps({"ok": False, "error": "no_profile"})
    return json.dumps({"ok": True, "profile": data}, ensure_ascii=False)


@tool
def get_seen_ids(user_id: str) -> str:
    """Return every listing_id already stored for this user (for dedup)."""
    store = get_agent_store()
    ids = [key for key, _ in list_json(store, _props_ns(user_id))]
    return json.dumps({"ok": True, "seen_ids": ids, "count": len(ids)})


@tool
def upsert_property(
    user_id: str,
    listing_json: str,
    status: str = "new",
    fair_value: float | None = None,
    renovation_cost: float = 0.0,
    negotiation_target: float | None = None,
    monthly_payment: float | None = None,
    affordable: bool | None = None,
    condition_score: float | None = None,
    insight_summary: str = "",
) -> str:
    """Create or update a property record. Pass listing as a JSON object matching Listing.

    If the listing already exists and the price changed, appends to price_history.
    Returns a compact summary (never the full history dump).
    """
    store = get_agent_store()
    listing = Listing.model_validate_json(listing_json)
    existing = get_json(store, _props_ns(user_id), listing.listing_id)

    if existing:
        rec = PropertyRecord.model_validate(existing)
        old_price = rec.listing.price
        rec.listing = listing
        rec.last_seen = _now()
        if status in STATUS_PIPELINE:
            rec.status = status  # type: ignore[assignment]
        if fair_value is not None:
            rec.fair_value = fair_value
        rec.renovation_cost = renovation_cost
        if negotiation_target is not None:
            rec.negotiation_target = negotiation_target
        if monthly_payment is not None:
            rec.monthly_payment = monthly_payment
        if affordable is not None:
            rec.affordable = affordable
        if condition_score is not None:
            rec.condition_score = condition_score
        if insight_summary:
            rec.insight_summary = insight_summary
        if abs(old_price - listing.price) >= 1.0:
            rec.price_history.append(
                PricePoint(date=date.today().isoformat(), price=listing.price)
            )
        price_changed = abs(old_price - listing.price) >= 1.0
        old = old_price
    else:
        if status not in STATUS_PIPELINE:
            status = "new"
        rec = PropertyRecord(
            listing=listing,
            price_history=[PricePoint(date=date.today().isoformat(), price=listing.price)],
            status=status,  # type: ignore[arg-type]
            fair_value=fair_value,
            renovation_cost=renovation_cost,
            negotiation_target=negotiation_target,
            monthly_payment=monthly_payment,
            affordable=affordable,
            condition_score=condition_score,
            insight_summary=insight_summary,
            first_seen=_now(),
            last_seen=_now(),
        )
        price_changed = False
        old = listing.price

    put_json(store, _props_ns(user_id), listing.listing_id, rec.model_dump(mode="json"))
    compact = _compact_property(rec)
    compact["price_changed"] = price_changed
    compact["previous_price"] = old
    return json.dumps({"ok": True, "property": compact}, ensure_ascii=False)


@tool
def update_status(user_id: str, listing_id: str, status: str) -> str:
    """Move a property along the pipeline status."""
    if status not in STATUS_PIPELINE:
        return json.dumps(
            {"ok": False, "error": f"invalid_status", "allowed": list(STATUS_PIPELINE)}
        )
    store = get_agent_store()
    data = get_json(store, _props_ns(user_id), listing_id)
    if not data:
        return json.dumps({"ok": False, "error": "not_found", "listing_id": listing_id})
    rec = PropertyRecord.model_validate(data)
    rec.status = status  # type: ignore[assignment]
    rec.last_seen = _now()
    put_json(store, _props_ns(user_id), listing_id, rec.model_dump(mode="json"))
    return json.dumps({"ok": True, "listing_id": listing_id, "status": status})


@tool
def add_insight(user_id: str, listing_id: str, insight_summary: str, long_insight: str = "") -> str:
    """Attach a short insight summary to a property. Optional long_insight is stored separately."""
    store = get_agent_store()
    data = get_json(store, _props_ns(user_id), listing_id)
    if not data:
        return json.dumps({"ok": False, "error": "not_found", "listing_id": listing_id})
    rec = PropertyRecord.model_validate(data)
    rec.insight_summary = insight_summary[:500]
    rec.last_seen = _now()
    put_json(store, _props_ns(user_id), listing_id, rec.model_dump(mode="json"))
    if long_insight.strip():
        put_json(
            store,
            _insights_ns(user_id),
            listing_id,
            {"listing_id": listing_id, "text": long_insight, "updated_at": _now()},
        )
    return json.dumps(
        {"ok": True, "listing_id": listing_id, "insight_summary": rec.insight_summary}
    )


@tool
def get_insight(user_id: str, listing_id: str) -> str:
    """Load the long insight text for one listing (on demand, keeps context lean)."""
    store = get_agent_store()
    data = get_json(store, _insights_ns(user_id), listing_id)
    if not data:
        prop = get_json(store, _props_ns(user_id), listing_id)
        if prop:
            return json.dumps(
                {
                    "ok": True,
                    "listing_id": listing_id,
                    "text": prop.get("insight_summary", ""),
                    "source": "summary_only",
                }
            )
        return json.dumps({"ok": False, "error": "not_found"})
    return json.dumps({"ok": True, **data}, ensure_ascii=False)


@tool
def get_shortlist(user_id: str, statuses: str = "suggested,shortlisted") -> str:
    """Return compact cards for properties in the given statuses (comma-separated)."""
    wanted = {s.strip() for s in statuses.split(",") if s.strip()}
    store = get_agent_store()
    cards = []
    for _, raw in list_json(store, _props_ns(user_id)):
        rec = PropertyRecord.model_validate(raw)
        if rec.status in wanted:
            cards.append(_compact_property(rec))
    cards.sort(key=lambda c: (c["rank"] is None, c["rank"] if c["rank"] is not None else 999))
    return json.dumps({"ok": True, "count": len(cards), "properties": cards}, ensure_ascii=False)


@tool
def get_property(user_id: str, listing_id: str) -> str:
    """Load one compact property record."""
    store = get_agent_store()
    data = get_json(store, _props_ns(user_id), listing_id)
    if not data:
        return json.dumps({"ok": False, "error": "not_found"})
    rec = PropertyRecord.model_validate(data)
    return json.dumps({"ok": True, "property": _compact_property(rec)}, ensure_ascii=False)


@tool
def log_run(
    user_id: str,
    suggested_ids: str,
    summary: str,
    price_alerts: str = "",
    run_date: str = "",
) -> str:
    """Record a daily/weekly scan. suggested_ids and price_alerts are comma-separated."""
    day = run_date or date.today().isoformat()
    ids = [x.strip() for x in suggested_ids.split(",") if x.strip()]
    alerts = [x.strip() for x in price_alerts.split("|") if x.strip()]
    entry = RunLog(date=day, suggested_ids=ids, summary=summary[:500], price_alerts=alerts)
    store = get_agent_store()
    put_json(store, _runs_ns(user_id), day, entry.model_dump())
    return json.dumps({"ok": True, "run": entry.model_dump()}, ensure_ascii=False)


@tool
def get_run_history(user_id: str, limit: int = 7) -> str:
    """Return the last N scan run logs (daily recall without bloating context)."""
    store = get_agent_store()
    rows = list_json(store, _runs_ns(user_id))
    rows.sort(key=lambda kv: kv[0], reverse=True)
    runs = [v for _, v in rows[: max(1, limit)]]
    return json.dumps({"ok": True, "runs": runs}, ensure_ascii=False)


# Pure helpers used by ranking (not exposed as tools)
def load_profile(user_id: str) -> UserProfile | None:
    data = get_json(get_agent_store(), _users_ns(user_id), "profile")
    return UserProfile.model_validate(data) if data else None


def load_all_properties(user_id: str) -> list[PropertyRecord]:
    return [
        PropertyRecord.model_validate(raw)
        for _, raw in list_json(get_agent_store(), _props_ns(user_id))
    ]


def save_property_record(user_id: str, rec: PropertyRecord) -> None:
    put_json(
        get_agent_store(),
        _props_ns(user_id),
        rec.listing.listing_id,
        rec.model_dump(mode="json"),
    )


MEMORY_TOOLS = [
    save_profile,
    get_profile,
    get_seen_ids,
    upsert_property,
    update_status,
    add_insight,
    get_insight,
    get_shortlist,
    get_property,
    log_run,
    get_run_history,
]
