"""Telegram notifications (Person C).

`send_telegram` is the agent tool used for price-drop alerts to the buyer.
`send_message` is the plain helper that outreach.py reuses to post as the "owner".
"""

from __future__ import annotations

import os

import httpx
from langchain_core.tools import tool

from agent.config import ROOT  # noqa: F401  (importing config loads .env)

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4096  # Telegram hard limit per message
TIMEOUT = 10.0


class TelegramError(RuntimeError):
    """Raised by send_message when Telegram is unconfigured or rejects the call."""


def send_message(text: str, chat_id: str | None = None) -> dict:
    """Send plain text to `chat_id` (default TELEGRAM_CHAT_ID). Returns the Telegram message."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN is not set")
    if not chat_id:
        raise TelegramError("chat id missing (TELEGRAM_CHAT_ID / OWNER_CHAT_ID not set)")

    # No parse_mode: listing titles contain characters that break Markdown/HTML escaping.
    resp = httpx.post(
        API.format(token=token, method="sendMessage"),
        json={"chat_id": chat_id, "text": text[:MAX_LEN], "disable_web_page_preview": True},
        timeout=TIMEOUT,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code != 200 or not data.get("ok"):
        raise TelegramError(f"Telegram {resp.status_code}: {data.get('description', resp.text[:200])}")
    return data["result"]


@tool
def send_telegram(text: str) -> str:
    """Send a short alert to the buyer's Telegram chat, e.g. a price drop with the new rank.

    Use plain text, one or two sentences, e.g.
    "Price drop EUR 100k on Schwabing 3-room, now rank #5 (was #9)".
    Do not use this to contact property owners.
    """
    try:
        msg = send_message(text)
    except (TelegramError, httpx.HTTPError) as exc:
        return f"FAILED to send Telegram message: {exc}"
    return f"sent (message_id={msg['message_id']})"
