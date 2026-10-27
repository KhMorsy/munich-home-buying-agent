import json
import sys

import pytest

from agent.tools import notify, outreach

sys.path.insert(0, str(outreach.ROOT / "scripts"))
import simulate_price_drop as spd  # noqa: E402


@pytest.fixture
def outbox(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach, "OUTBOX", tmp_path / "outbox")
    return tmp_path / "outbox"


def test_exports_match_contract():
    names = {t.name for t in outreach.ACTION_TOOLS}
    assert set(outreach.INTERRUPT_ON) == {"send_owner_message", "create_calendar_event"}
    assert set(outreach.INTERRUPT_ON) <= names  # every protected tool is actually exported
    assert all(v is True for v in outreach.INTERRUPT_ON.values())
    assert len(outreach.LIMIT_MIDDLEWARE) >= 2


def test_booking_flow_removes_slot_and_writes_ics(outbox):
    slots = json.loads(outreach.get_free_slots.invoke({"limit": 3}))["slots"]
    assert len(slots) == 3
    sid = slots[0]["slot_id"]

    out = json.loads(
        outreach.create_calendar_event.invoke(
            {"listing_id": "mu-1", "listing_title": "Altbau, Stuck", "address": "Agnesstr. 21", "slot_id": sid}
        )
    )
    assert out["ok"]
    ics = (outbox / f"{sid}.ics").read_text()
    assert "BEGIN:VEVENT" in ics and "SUMMARY:Viewing: Altbau\\, Stuck" in ics

    assert sid not in {s["slot_id"] for s in json.loads(outreach.get_free_slots.invoke({"limit": 20}))["slots"]}
    again = json.loads(
        outreach.create_calendar_event.invoke(
            {"listing_id": "mu-2", "listing_title": "x", "address": "y", "slot_id": sid}
        )
    )
    assert not again["ok"]  # no double booking


def test_unknown_slot_rejected(outbox):
    out = json.loads(
        outreach.create_calendar_event.invoke(
            {"listing_id": "a", "listing_title": "b", "address": "c", "slot_id": "nope"}
        )
    )
    assert not out["ok"] and not outbox.exists()


def test_draft_mentions_listing_offer_and_slots():
    text = outreach.draft_owner_message.invoke(
        {"listing_id": "mu-1", "listing_title": "Altbau", "offer_price": 850000, "proposed_slots": "Tue 10:00"}
    )
    assert "mu-1" in text and "850,000" in text and "Tue 10:00" in text


def test_send_owner_message_targets_owner_chat(monkeypatch):
    monkeypatch.setenv("OWNER_CHAT_ID", "999")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    seen = {}

    def fake_send(text, chat_id=None):
        seen.update(text=text, chat_id=chat_id)
        return {"message_id": 3}

    monkeypatch.setattr(outreach, "send_message", fake_send)
    out = outreach.send_owner_message.invoke({"listing_id": "mu-1", "message": "Hello"})
    assert seen["chat_id"] == "999" and "mu-1" in seen["text"] and "message_id=3" in out

    def boom(text, chat_id=None):
        raise notify.TelegramError("chat not found")

    monkeypatch.setattr(outreach, "send_message", boom)
    assert outreach.send_owner_message.invoke({"listing_id": "a", "message": "b"}).startswith("FAILED")


def test_price_drop_rewrites_only_that_price():
    text = (
        '[\n'
        '  {"listing_id": "a-1", "title": "A", "price": 900000, "sqm": 70},\n'
        '  {"listing_id": "b-2", "title": "B", "price": 900000, "sqm": 80}\n'
        ']\n'
    )
    new_text, old, new = spd.drop_price(text, "b-2", 100000, None)
    assert (old, new) == (900000.0, 800000.0)
    a, b = json.loads(new_text)
    assert a["price"] == 900000 and b["price"] == 800000
    assert new_text.splitlines()[1] == text.splitlines()[1]  # untouched line is byte-identical

    _, _, pct = spd.drop_price(text, "a-1", None, 10)
    assert pct == 810000.0
    with pytest.raises(KeyError):
        spd.drop_price(text, "zzz", 1, None)
    with pytest.raises(ValueError):
        spd.drop_price(text, "a-1", 900000, None)


def test_price_drop_works_on_real_seed():
    text = spd.SEED.read_text(encoding="utf-8")
    first = json.loads(text)[0]
    new_text, old, new = spd.drop_price(text, first["listing_id"], 100000, None)
    assert old == first["price"] and new == old - 100000
    assert len(json.loads(new_text)) == len(json.loads(text))
    assert len(new_text.splitlines()) == len(text.splitlines())  # format preserved
