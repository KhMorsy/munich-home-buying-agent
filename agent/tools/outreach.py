"""Owner outreach and viewing booking (Person C).

`send_owner_message` and `create_calendar_event` have real side effects, so they are
listed in INTERRUPT_ON and the agent pauses for human approval before either runs.
Exports for agent/graph.py: ACTION_TOOLS, INTERRUPT_ON, LIMIT_MIDDLEWARE.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import httpx
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain_core.tools import tool

from agent.config import MODEL_CALL_LIMIT, ROOT, TOOL_CALL_LIMIT
from agent.tools.notify import TelegramError, send_message

CALENDAR_PATH = ROOT / "data" / "mock_calendar.json"
OUTBOX = ROOT / "data" / "outbox"  # booked events as .ics (gitignored)


def _booked_ids() -> set[str]:
    return {p.stem for p in OUTBOX.glob("*.ics")} if OUTBOX.is_dir() else set()


def _free_slots() -> list[dict]:
    slots = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))["free_slots"]
    booked = _booked_ids()
    return [s for s in slots if s["slot_id"] not in booked]


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_time(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%Y%m%dT%H%M%S")


@tool
def draft_owner_message(
    listing_id: str,
    listing_title: str,
    buyer_name: str = "an interested buyer",
    offer_price: float = 0,
    proposed_slots: str = "",
) -> str:
    """Draft (but do not send) a short, polite first message to the property owner.

    offer_price: optional opening price in EUR (use the negotiation target).
    proposed_slots: optional comma-separated viewing times to suggest.
    Show the draft to the user, then call send_owner_message with the final text.
    """
    lines = [
        "Guten Tag,",
        "",
        f"I am writing on behalf of {buyer_name} about your listing "
        f'"{listing_title}" (ref. {listing_id}). The property matches what we are looking for.',
    ]
    if proposed_slots.strip():
        lines.append(f"Would a viewing work for you on one of these times: {proposed_slots.strip()}?")
    else:
        lines.append("Could we arrange a viewing in the coming days?")
    if offer_price:
        lines.append(f"Based on comparable sales, our indicative offer would be around EUR {offer_price:,.0f}.")
    lines += ["", "Kind regards"]
    return "\n".join(lines)


@tool
def send_owner_message(listing_id: str, message: str) -> str:
    """Send the approved message to the property owner. Requires human approval first.

    Only call this with a message the user has seen. Afterwards set the property status
    to owner_contacted.
    """
    try:
        msg = send_message(f"[Buyer inquiry, listing {listing_id}]\n{message}", os.getenv("OWNER_CHAT_ID"))
    except (TelegramError, httpx.HTTPError) as exc:
        return f"FAILED to contact owner: {exc}"
    return f"sent to owner of {listing_id} (message_id={msg['message_id']})"


@tool
def get_free_slots(limit: int = 5) -> str:
    """List the buyer's next free viewing slots (slot_id, start, end) from the calendar."""
    slots = _free_slots()[: max(1, int(limit))]
    return json.dumps({"ok": True, "count": len(slots), "slots": slots})


@tool
def create_calendar_event(listing_id: str, listing_title: str, address: str, slot_id: str) -> str:
    """Book a viewing in the buyer's calendar (writes an .ics file). Requires human approval first.

    slot_id must come from get_free_slots. Afterwards set the status to viewing_booked.
    """
    slot = next((s for s in _free_slots() if s["slot_id"] == slot_id), None)
    if slot is None:
        return json.dumps({"ok": False, "error": f"slot {slot_id} is not free; call get_free_slots"})

    OUTBOX.mkdir(parents=True, exist_ok=True)
    ics = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//munich-home-buying-agent//EN",
            "BEGIN:VEVENT",
            f"UID:{slot_id}-{listing_id}@munich-home-buying-agent",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;TZID=Europe/Berlin:{_ics_time(slot['start'])}",
            f"DTEND;TZID=Europe/Berlin:{_ics_time(slot['end'])}",
            f"SUMMARY:{_ics_escape('Viewing: ' + listing_title)}",
            f"LOCATION:{_ics_escape(address)}",
            f"DESCRIPTION:{_ics_escape('Listing ' + listing_id)}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
    path = OUTBOX / f"{slot_id}.ics"
    path.write_text(ics, encoding="utf-8")
    return json.dumps({"ok": True, "booked": slot, "listing_id": listing_id, "file": path.name})


ACTION_TOOLS = [draft_owner_message, send_owner_message, get_free_slots, create_calendar_event]

# Tools that contact a person or book something: the agent must stop for approval.
INTERRUPT_ON = {
    "send_owner_message": True,
    "create_calendar_event": True,
}

LIMIT_MIDDLEWARE = [
    ToolCallLimitMiddleware(run_limit=TOOL_CALL_LIMIT, exit_behavior="continue"),
    # Hard cap on owner contact per conversation, whatever the model decides.
    ToolCallLimitMiddleware(tool_name="send_owner_message", thread_limit=5, exit_behavior="continue"),
    ModelCallLimitMiddleware(run_limit=MODEL_CALL_LIMIT, exit_behavior="end"),
]
