"""Shared data contracts. Do not change without team agreement."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

PropertyStatus = Literal[
    "new",
    "suggested",
    "shortlisted",
    "owner_contacted",
    "viewing_proposed",
    "viewing_booked",
    "rejected",
]


class Listing(BaseModel):
    listing_id: str
    url: str = ""
    title: str
    district: str
    address: str = ""
    sqm: float
    rooms: float
    price: float
    year_built: int | None = None
    condition: str = "unknown"  # e.g. renovated / needs_renovation / good
    description: str = ""
    contact: str = ""


class CompSale(BaseModel):
    price: float
    sqm: float
    date: date | str
    district: str | None = None
    address: str | None = None


class FinanceResult(BaseModel):
    listing_id: str
    total_purchase_cost: float
    loan_amount: float
    rate: float
    monthly_payment: float
    years: int = 30
    affordable: bool
    notes: str = ""


class ValuationResult(BaseModel):
    listing_id: str
    fair_value: float
    price_per_sqm: float
    district_avg_per_sqm: float
    renovation_needed: bool = False
    renovation_cost: float = 0.0
    condition_score: float = Field(ge=0.0, le=1.0, default=0.7)
    summary: str = ""


class NegotiationResult(BaseModel):
    listing_id: str
    comps: list[CompSale] = Field(default_factory=list)
    target_price: float
    max_discount_pct: float
    arguments: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    price_vs_market: float = Field(ge=0.0, le=1.0)
    affordability: float = Field(ge=0.0, le=1.0)
    fit: float = Field(ge=0.0, le=1.0)
    total: float = Field(ge=0.0, le=1.0)


class PricePoint(BaseModel):
    date: str  # ISO date
    price: float


class UserProfile(BaseModel):
    user_id: str
    budget: float
    equity: float
    max_monthly: float
    rooms_min: float = 2.0
    rooms_max: float = 5.0
    districts: list[str] = Field(default_factory=list)
    must_haves: list[str] = Field(default_factory=list)
    property_type: str = "apartment"  # apartment | house
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class PropertyRecord(BaseModel):
    """Listing plus pipeline / scoring state kept in long-term memory."""

    listing: Listing
    price_history: list[PricePoint] = Field(default_factory=list)
    status: PropertyStatus = "new"
    scores: ScoreBreakdown | None = None
    rank: int | None = None
    fair_value: float | None = None
    renovation_cost: float = 0.0
    negotiation_target: float | None = None
    monthly_payment: float | None = None
    affordable: bool | None = None
    condition_score: float | None = None
    insight_summary: str = ""
    first_seen: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    last_seen: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class RunLog(BaseModel):
    date: str  # YYYY-MM-DD
    suggested_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    price_alerts: list[str] = Field(default_factory=list)


class PriceChange(BaseModel):
    listing_id: str
    title: str
    old_price: float
    new_price: float
    delta: float
    old_rank: int | None = None
    new_rank: int | None = None
    alert: str = ""
