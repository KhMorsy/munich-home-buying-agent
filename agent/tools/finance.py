"""Mortgage rates and the deterministic mortgage plan (Person B).

Rates are annual percentages (3.7 means 3.7% p.a.). The LLM never does this math.
"""

from __future__ import annotations

import json
import logging
import os
import re
from statistics import median

from langchain_core.tools import tool

from agent.config import GRUNDERWERBSTEUER, MAKLER_PCT, NOTARY_PCT
from agent.schemas import FinanceResult

logger = logging.getLogger(__name__)

# 10-year fixed (Sollzins) fallback for Germany, autumn 2026 ballpark
FALLBACK_RATE_PCT = 3.7
RATE_RANGE = (1.0, 8.0)


def purchase_costs(price: float, include_makler: bool = True) -> dict[str, float]:
    """German side costs on top of the price (Bavaria)."""
    grunderwerb = price * GRUNDERWERBSTEUER
    notary = price * NOTARY_PCT
    makler = price * MAKLER_PCT if include_makler else 0.0
    return {
        "grunderwerbsteuer": round(grunderwerb, 2),
        "notary_land_registry": round(notary, 2),
        "makler": round(makler, 2),
        "side_costs_total": round(grunderwerb + notary + makler, 2),
    }


def annuity_monthly_payment(loan: float, rate_pct: float, years: int) -> float:
    """Classic annuity: constant monthly payment that repays `loan` over `years`."""
    if loan <= 0:
        return 0.0
    n = years * 12
    r = rate_pct / 100 / 12
    if r == 0:
        return loan / n
    return loan * r / (1 - (1 + r) ** -n)


def max_loan_for_payment(monthly: float, rate_pct: float, years: int) -> float:
    """Inverse of annuity_monthly_payment."""
    n = years * 12
    r = rate_pct / 100 / 12
    if r == 0:
        return monthly * n
    return monthly * (1 - (1 + r) ** -n) / r


def compute_mortgage_plan(
    listing_id: str,
    price: float,
    equity: float,
    monthly_max: float,
    rate_pct: float = FALLBACK_RATE_PCT,
    years: int = 30,
    include_makler: bool = True,
    extra_costs: float = 0.0,
) -> FinanceResult:
    """Full plan for one listing. extra_costs = e.g. renovation financed with the loan."""
    costs = purchase_costs(price, include_makler)
    total = price + costs["side_costs_total"] + max(0.0, extra_costs)
    loan = max(0.0, total - equity)
    monthly = annuity_monthly_payment(loan, rate_pct, years)
    affordable = monthly <= monthly_max if monthly_max > 0 else False

    notes = [
        f"Side costs EUR {costs['side_costs_total']:,.0f} "
        f"(GrESt {GRUNDERWERBSTEUER:.1%}, notary {NOTARY_PCT:.0%}, "
        f"Makler {MAKLER_PCT if include_makler else 0:.2%})",
        f"Loan-to-price {loan / price:.0%}" if price > 0 else "",
    ]
    if extra_costs > 0:
        notes.append(f"Includes EUR {extra_costs:,.0f} renovation in the loan")
    if equity < costs["side_costs_total"]:
        notes.append("Equity does not cover side costs; banks usually require that, expect a rate surcharge")
    if monthly_max > 0:
        max_loan = max_loan_for_payment(monthly_max, rate_pct, years)
        max_price = (max_loan + equity - max(0.0, extra_costs)) / (
            1 + GRUNDERWERBSTEUER + NOTARY_PCT + (MAKLER_PCT if include_makler else 0)
        )
        notes.append(f"Max price at EUR {monthly_max:,.0f}/month: EUR {max_price:,.0f}")

    return FinanceResult(
        listing_id=listing_id,
        total_purchase_cost=round(total, 2),
        loan_amount=round(loan, 2),
        rate=round(rate_pct, 3),
        monthly_payment=round(monthly, 2),
        years=years,
        affordable=affordable,
        notes="; ".join(n for n in notes if n),
    )


_RATE_RE = re.compile(r"(\d[,.]\d{1,2})\s*%")


def fetch_live_rate() -> float | None:
    """Median 10-year fixed rate quoted in Tavily results, or None."""
    if not os.getenv("TAVILY_API_KEY"):
        return None
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        resp = client.search(query="aktuelle Bauzinsen 10 Jahre Zinsbindung Sollzins", max_results=5)
        found = []
        for hit in resp.get("results", []):
            for m in _RATE_RE.finditer(hit.get("content", "")):
                value = float(m.group(1).replace(",", "."))
                if RATE_RANGE[0] <= value <= RATE_RANGE[1]:
                    found.append(value)
        return round(median(found), 2) if found else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live rate lookup failed: %s", exc)
        return None


@tool
def get_mortgage_rates(live: bool = True) -> str:
    """Current German 10-year fixed mortgage rate in % p.a. Falls back to a default if offline."""
    rate = fetch_live_rate() if live else None
    return json.dumps(
        {
            "ok": True,
            "rate_10y_fixed_pct": rate if rate is not None else FALLBACK_RATE_PCT,
            "source": "tavily" if rate is not None else "fallback",
        }
    )


@tool
def mortgage_plan(
    listing_id: str,
    price: float,
    equity: float,
    monthly_max: float,
    rate: float = 0,
    years: int = 30,
    include_makler: bool = True,
    renovation_cost: float = 0,
) -> str:
    """Deterministic mortgage plan for one listing. Returns FinanceResult JSON.

    rate: annual % (e.g. 3.7). 0 = use the default rate. Get a live one from get_mortgage_rates.
    renovation_cost: optional amount financed on top of the purchase.
    Includes Bavarian side costs: Grunderwerbsteuer 3.5%, notary ~2%, Makler 3.57%.
    """
    rate_pct = rate if rate > 0 else FALLBACK_RATE_PCT
    if rate_pct < 0.2:  # given as a fraction (0.037)
        rate_pct *= 100
    result = compute_mortgage_plan(
        listing_id, price, equity, monthly_max, rate_pct, years, include_makler, renovation_cost
    )
    return result.model_dump_json()


FINANCE_TOOLS = [get_mortgage_rates, mortgage_plan]
