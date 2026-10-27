"""Listing search: seed data (always) plus optional live Tavily results (Person B)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

from langchain_core.tools import tool

from agent.config import ROOT
from agent.schemas import Listing

logger = logging.getLogger(__name__)

SEED_LISTINGS_PATH = ROOT / "data" / "seed_listings.json"
PORTAL_DOMAINS = ["immobilienscout24.de", "immowelt.de", "kleinanzeigen.de"]
# "Reihenhaus", "Einfamilienhaus", "Doppelhaushälfte", "house" - but not "Penthouse"
HOUSE_RE = re.compile(r"haus\b|haushälfte|\bhouse\b|\bvilla\b", re.IGNORECASE)
PRICE_TOLERANCE = 1.10  # show listings up to 10% over budget (negotiation room)
DESCRIPTION_MAX = 240


def make_listing_id(url: str = "", address: str = "", sqm: float = 0, rooms: float = 0) -> str:
    """Stable id from the URL, or from address + size + rooms when there is no URL."""
    if url:
        key = url.split("?")[0].rstrip("/").lower()
    else:
        key = f"{address.strip().lower()}|{float(sqm):.0f}|{float(rooms):.1f}"
    return "l-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def load_seed_listings() -> list[Listing]:
    """Read the seed file fresh on every call so simulated price drops show up."""
    raw = json.loads(SEED_LISTINGS_PATH.read_text(encoding="utf-8"))
    out = []
    for item in raw:
        if not item.get("listing_id"):
            item["listing_id"] = make_listing_id(
                item.get("url", ""), item.get("address", ""), item.get("sqm", 0), item.get("rooms", 0)
            )
        out.append(Listing.model_validate(item))
    return out


def is_house(listing: Listing) -> bool:
    return bool(HOUSE_RE.search(listing.title))


def matches(
    listing: Listing,
    districts: list[str],
    max_price: float,
    rooms_min: float,
    rooms_max: float,
    min_sqm: float,
    property_type: str,
) -> bool:
    if districts and listing.district.lower() not in districts:
        return False
    if max_price > 0 and listing.price > max_price * PRICE_TOLERANCE:
        return False
    if rooms_min > 0 and listing.rooms < rooms_min:
        return False
    if rooms_max > 0 and listing.rooms > rooms_max:
        return False
    if min_sqm > 0 and listing.sqm < min_sqm:
        return False
    if property_type == "house" and not is_house(listing):
        return False
    if property_type == "apartment" and is_house(listing):
        return False
    return True


_PRICE_RE = re.compile(r"([\d.]{6,11})\s*(?:€|eur)", re.IGNORECASE)
_SQM_RE = re.compile(r"(\d{2,3}(?:[.,]\d+)?)\s*(?:m²|m2|qm)", re.IGNORECASE)
_ROOMS_RE = re.compile(r"(\d(?:[.,]5)?)\s*(?:-\s*)?(?:zimmer|zi\b|rooms?)", re.IGNORECASE)


def _num(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def parse_live_result(result: dict[str, Any], district_hint: str) -> Listing | None:
    """Best-effort parse of a Tavily hit. Returns None when price or size is missing."""
    text = f"{result.get('title', '')} {result.get('content', '')}"
    price_m, sqm_m = _PRICE_RE.search(text), _SQM_RE.search(text)
    if not price_m or not sqm_m:
        return None
    try:
        price = float(price_m.group(1).replace(".", ""))
        sqm = _num(sqm_m.group(1))
    except ValueError:
        return None
    if not (50_000 <= price <= 10_000_000 and 15 <= sqm <= 400):
        return None
    rooms_m = _ROOMS_RE.search(text)
    rooms = _num(rooms_m.group(1)) if rooms_m else 0.0
    url = result.get("url", "")
    return Listing(
        listing_id=make_listing_id(url=url),
        url=url,
        title=str(result.get("title", ""))[:120],
        district=district_hint or "München",
        sqm=sqm,
        rooms=rooms,
        price=price,
        description=str(result.get("content", ""))[:DESCRIPTION_MAX],
        contact="see listing",
    )


def search_live(districts: list[str], max_price: float, rooms_min: float, property_type: str) -> list[Listing]:
    """Tavily search over the big German portals. Returns [] on any failure."""
    if not os.getenv("TAVILY_API_KEY"):
        return []
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        kind = "Haus" if property_type == "house" else "Wohnung"
        found: list[Listing] = []
        for district in districts or [""]:
            query = f"{kind} kaufen München {district} {int(rooms_min) or ''} Zimmer bis {int(max_price) or ''} €"
            resp = client.search(query=query, include_domains=PORTAL_DOMAINS, max_results=8)
            for hit in resp.get("results", []):
                listing = parse_live_result(hit, district.title())
                if listing:
                    found.append(listing)
        return found
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live listing search failed, using seed only: %s", exc)
        return []


def compact(listing: Listing) -> dict[str, Any]:
    data = listing.model_dump()
    data["description"] = data["description"][:DESCRIPTION_MAX]
    return data


@tool
def search_listings(
    districts: str = "",
    max_price: float = 0,
    rooms_min: float = 0,
    rooms_max: float = 0,
    min_sqm: float = 0,
    property_type: str = "apartment",
    limit: int = 10,
    include_live: bool = False,
) -> str:
    """Search Munich listings for sale matching the buyer's criteria.

    districts: comma-separated Munich districts (e.g. "Schwabing,Sendling"); empty = all.
    max_price: purchase price ceiling in EUR (listings up to 10% above are kept for negotiation).
    property_type: "apartment", "house" or "any".
    include_live: also query immobilienscout24 / immowelt / kleinanzeigen via Tavily.
    Returns full Listing objects (JSON) that can be passed to filter_new_listings and upsert_property.
    Already-known listings are included on purpose so price changes can be detected.
    """
    wanted = [d.strip().lower() for d in districts.split(",") if d.strip()]
    ptype = (property_type or "any").strip().lower()
    seed = load_seed_listings()

    # Treat "about N rooms" as a small band when min==max (agents often pass both as 3).
    rmin, rmax = rooms_min, rooms_max
    if rmin > 0 and rmax > 0 and abs(rmin - rmax) < 1e-9:
        rmin = max(0.0, rmin - 0.5)
        rmax = rmax + 0.5

    def _filter(
        pool: list[Listing],
        dists: list[str],
        price_cap: float,
        lo: float,
        hi: float,
        sqm: float,
        ptype_local: str,
    ) -> list[Listing]:
        return [listing for listing in pool if matches(listing, dists, price_cap, lo, hi, sqm, ptype_local)]

    results = _filter(seed, wanted, max_price, rmin, rmax, min_sqm, ptype)
    relaxed: list[str] = []

    # Soft fallbacks so the demo never returns an empty market for realistic criteria.
    if not results and max_price > 0:
        wider = max_price * 1.15 / PRICE_TOLERANCE  # effective ~+15% more headroom beyond base tol
        results = _filter(seed, wanted, wider, rmin, rmax, min_sqm, ptype)
        if results:
            relaxed.append("widened_budget_15pct")
    if not results and wanted:
        results = _filter(seed, [], max_price or 0, rmin, rmax, min_sqm, ptype)
        if results:
            relaxed.append("dropped_district_filter")
    if not results:
        results = _filter(seed, wanted or [], max_price or 0, 0, 0, 0, ptype if ptype != "any" else "any")
        if results:
            relaxed.append("dropped_room_filters")
    if not results:
        results = list(seed)
        relaxed.append("returned_full_seed_catalog")

    sources = ["seed"]
    if include_live:
        live = [
            listing
            for listing in search_live(wanted, max_price, rooms_min, ptype)
            if matches(listing, [], max_price, rmin, rmax, min_sqm, "any")
        ]
        seen = {r.listing_id for r in results}
        results += [listing for listing in live if listing.listing_id not in seen]
        if live:
            sources.append("tavily")

    # cheapest per sqm first, so the shortlist starts with likely bargains
    results.sort(key=lambda r: r.price / max(r.sqm, 1))
    results = results[: max(1, int(limit))]
    note = ""
    if relaxed:
        note = (
            "Exact filters were empty; returned closest matches ("
            + ", ".join(relaxed)
            + "). Tell the buyer what was relaxed."
        )
    return json.dumps(
        {
            "ok": True,
            "count": len(results),
            "sources": sources,
            "relaxed": relaxed,
            "note": note,
            "listings": [compact(r) for r in results],
        },
        ensure_ascii=False,
    )


LISTING_TOOLS = [search_listings]
