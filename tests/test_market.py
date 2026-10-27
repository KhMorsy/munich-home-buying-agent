"""Unit tests for Person B: finance math, seed data, search, valuation, negotiation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.schemas import FinanceResult, Listing, NegotiationResult, ValuationResult
from agent.tools.comps import compute_negotiation, compute_valuation, load_sold_history
from agent.tools.finance import (
    annuity_monthly_payment,
    compute_mortgage_plan,
    max_loan_for_payment,
    mortgage_plan,
)
from agent.tools.listings import load_seed_listings, make_listing_id, search_listings


# --- finance -------------------------------------------------------------

def test_annuity_known_example():
    # EUR 400k at 4% over 30 years: 1,909.66/month (standard annuity table value)
    assert annuity_monthly_payment(400_000, 4.0, 30) == pytest.approx(1909.66, abs=0.01)
    # EUR 300k at 3% over 25 years: 1,422.63/month
    assert annuity_monthly_payment(300_000, 3.0, 25) == pytest.approx(1422.63, abs=0.01)


def test_annuity_inverse_and_edge_cases():
    loan = max_loan_for_payment(2_000, 3.7, 30)
    assert annuity_monthly_payment(loan, 3.7, 30) == pytest.approx(2_000, abs=0.01)
    assert annuity_monthly_payment(0, 3.7, 30) == 0
    assert annuity_monthly_payment(360_000, 0, 30) == pytest.approx(1_000)


def test_mortgage_plan_side_costs_and_affordability():
    plan = compute_mortgage_plan("x", price=700_000, equity=150_000, monthly_max=2_600, rate_pct=3.7)
    # 3.5% + 2% + 3.57% = 9.07% side costs
    assert plan.total_purchase_cost == pytest.approx(763_490, abs=1)
    assert plan.loan_amount == pytest.approx(613_490, abs=1)
    assert plan.monthly_payment == pytest.approx(annuity_monthly_payment(613_490, 3.7, 30), abs=0.01)
    assert plan.affordable is (plan.monthly_payment <= 2_600)
    no_agent = compute_mortgage_plan("x", 700_000, 150_000, 2_600, 3.7, include_makler=False)
    assert no_agent.total_purchase_cost == pytest.approx(738_500, abs=1)


def test_mortgage_plan_tool_returns_finance_result():
    out = mortgage_plan.invoke(
        {"listing_id": "mu-sendling-01", "price": 719_000, "equity": 180_000, "monthly_max": 2_500, "rate": 3.7}
    )
    result = FinanceResult.model_validate_json(out)
    assert result.listing_id == "mu-sendling-01"
    assert result.rate == 3.7
    # fraction input is accepted too
    frac = FinanceResult.model_validate_json(
        mortgage_plan.invoke(
            {"listing_id": "a", "price": 719_000, "equity": 180_000, "monthly_max": 2_500, "rate": 0.037}
        )
    )
    assert frac.monthly_payment == pytest.approx(result.monthly_payment)


# --- seed data -------------------------------------------------------------

def test_seed_listings_valid_and_varied():
    listings = load_seed_listings()
    assert len(listings) >= 25
    assert len({l.listing_id for l in listings}) == len(listings)
    districts = {l.district for l in listings}
    assert {"Schwabing", "Maxvorstadt", "Sendling", "Pasing", "Trudering"} <= districts
    vals = [compute_valuation(l) for l in listings]
    assert sum(v.renovation_needed for v in vals) >= 2
    overpriced = [l for l, v in zip(listings, vals) if l.price + v.renovation_cost > v.fair_value * 1.08]
    assert len(overpriced) >= 3


def test_sold_history_valid():
    sold = load_sold_history()
    assert len(sold) >= 30
    for row in sold:
        assert row["price"] > 0 and row["sqm"] > 0 and row["date"].startswith("2026-")


# --- search ----------------------------------------------------------------

def test_search_filters_and_returns_listings():
    out = json.loads(
        search_listings.invoke(
            {"districts": "Schwabing, Sendling", "max_price": 800_000, "rooms_min": 2, "rooms_max": 3}
        )
    )
    assert out["ok"] and out["count"] > 0
    for raw in out["listings"]:
        listing = Listing.model_validate(raw)
        assert listing.district in {"Schwabing", "Sendling"}
        assert listing.price <= 880_000 and 2 <= listing.rooms <= 3


def test_search_property_type():
    houses = json.loads(search_listings.invoke({"property_type": "house"}))["listings"]
    assert {h["listing_id"] for h in houses} == {"mu-pasing-04", "mu-trudering-01"}
    flats = json.loads(search_listings.invoke({"property_type": "apartment", "limit": 50}))["listings"]
    assert "mu-schwabing-03" in {f["listing_id"] for f in flats}  # Penthouse is a flat
    assert all("reihenhaus" not in f["title"].lower() for f in flats)


def test_listing_id_is_stable():
    a = make_listing_id(url="https://www.immowelt.de/expose/abc?utm=1")
    b = make_listing_id(url="https://www.immowelt.de/expose/abc/")
    assert a == b
    assert make_listing_id(address="Foo 1", sqm=70, rooms=3) == make_listing_id(address=" foo 1", sqm=70.2, rooms=3)


# --- valuation / negotiation -----------------------------------------------

def _seed(listing_id: str) -> Listing:
    return next(l for l in load_seed_listings() if l.listing_id == listing_id)


def test_valuation_flags_renovation_and_overpricing():
    reno = compute_valuation(_seed("mu-schwabing-04"))
    assert isinstance(reno, ValuationResult)
    assert reno.renovation_needed and reno.renovation_cost > 50_000
    assert 0 <= reno.condition_score <= 1
    over = compute_valuation(_seed("mu-maxvorstadt-04"))
    assert over.fair_value < _seed("mu-maxvorstadt-04").price
    assert "overpriced" in over.summary.lower()


def test_negotiation_target_bounds():
    for listing in load_seed_listings():
        neg = compute_negotiation(listing)
        assert isinstance(neg, NegotiationResult)
        assert listing.price * 0.88 - 1_000 <= neg.target_price <= listing.price * 0.97 + 1_000
        assert 2.5 <= neg.max_discount_pct <= 12.5
        assert neg.comps and neg.arguments
