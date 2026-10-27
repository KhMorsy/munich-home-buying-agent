"""Unit tests for deterministic ranking + price-change alerts (Person A)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.schemas import Listing, PropertyRecord, UserProfile
from agent.tools import store_util
from agent.tools.memory import save_property_record
from agent.tools.ranking import compute_scores, format_price_alert, rank_properties
from agent.tools.store_util import put_json


def _profile() -> UserProfile:
    return UserProfile(
        user_id="u1",
        budget=800_000,
        equity=160_000,
        max_monthly=2_500,
        rooms_min=2,
        rooms_max=3.5,
        districts=["Schwabing", "Maxvorstadt"],
    )


def _rec(
    lid: str,
    price: float,
    fair: float,
    monthly: float,
    district: str = "Schwabing",
    reno: float = 0.0,
) -> PropertyRecord:
    return PropertyRecord(
        listing=Listing(
            listing_id=lid,
            title=f"Flat {lid}",
            district=district,
            sqm=70,
            rooms=3,
            price=price,
            condition="good",
        ),
        status="suggested",
        fair_value=fair,
        renovation_cost=reno,
        monthly_payment=monthly,
        affordable=monthly <= 2500,
        condition_score=0.8,
    )


def test_better_deal_ranks_higher():
    store_util.reset_fallback_store()
    profile = _profile()
    cheap = _rec("a", price=650_000, fair=700_000, monthly=2000)
    pricey = _rec("b", price=780_000, fair=700_000, monthly=2400)
    ranked = rank_properties([cheap, pricey], profile)
    by_id = {r.listing.listing_id: r for r in ranked}
    assert by_id["a"].rank == 1
    assert by_id["b"].rank == 2
    assert by_id["a"].scores.total > by_id["b"].scores.total


def test_price_drop_alert_and_rerank():
    store = store_util.reset_fallback_store()
    profile = _profile()
    put_json(store, ("users", "u1"), "profile", profile.model_dump())

    a = _rec("a", price=750_000, fair=700_000, monthly=2300)
    b = _rec("b", price=700_000, fair=700_000, monthly=2100)
    for rec in (a, b):
        save_property_record("u1", rec)

    from agent.tools.ranking import score_and_rank

    # First rank
    out1 = json.loads(score_and_rank.invoke({"user_id": "u1"}))
    assert out1["ok"]
    ranks_before = {c["listing_id"]: c["rank"] for c in out1["ranked"]}
    assert ranks_before["b"] < ranks_before["a"]  # b better initially

    # Drop a by 100k → should improve and alert
    out2 = json.loads(
        score_and_rank.invoke(
            {"user_id": "u1", "price_updates_json": json.dumps({"a": 650_000})}
        )
    )
    assert out2["price_alerts"], "expected a price-drop alert"
    assert "drop" in out2["price_alerts"][0].lower()
    ranks_after = {c["listing_id"]: c["rank"] for c in out2["ranked"]}
    assert ranks_after["a"] <= ranks_after["b"]
    change = out2["changes"][0]
    assert change["old_rank"] == ranks_before["a"]
    assert change["new_rank"] == ranks_after["a"]
    assert "was #" in format_price_alert(
        __import__("agent.schemas", fromlist=["PriceChange"]).PriceChange.model_validate(change)
    )


def test_compute_scores_bounds():
    profile = _profile()
    rec = _rec("x", price=700_000, fair=700_000, monthly=2000)
    scores = compute_scores(rec, profile)
    assert 0 <= scores.price_vs_market <= 1
    assert 0 <= scores.affordability <= 1
    assert 0 <= scores.fit <= 1
    assert 0 <= scores.total <= 1
