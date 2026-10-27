"""Verify the Telegram + LangSmith setup (Person C).

    python scripts/setup_check.py --find-chats   # list chat ids of people who messaged the bot
    python scripts/setup_check.py                # check env, Telegram, LangSmith
    python scripts/setup_check.py --no-send      # same, but don't send the test message
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from agent.tools.notify import API, TelegramError, send_message  # noqa: E402

REQUIRED = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "OWNER_CHAT_ID", "LANGSMITH_API_KEY"]


def tg(method: str) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN is not set in .env (create a bot with @BotFather first)")
    data = httpx.get(API.format(token=token, method=method), timeout=10).json()
    if not data.get("ok"):
        sys.exit(f"Telegram {method} failed: {data.get('description')}")
    return data["result"]


def find_chats() -> None:
    me = tg("getMe")
    print(f"Bot: @{me['username']}")
    seen: dict[int, str] = {}
    for upd in tg("getUpdates"):
        chat = (upd.get("message") or upd.get("edited_message") or {}).get("chat")
        if chat:
            name = chat.get("username") or chat.get("first_name") or chat.get("title") or "?"
            seen[chat["id"]] = name
    if not seen:
        print(f"No chats yet. Open t.me/{me['username']}, press Start, send 'hi', then rerun.")
        print("The teammate playing the property owner must do the same.")
        return
    for cid, name in seen.items():
        print(f"  chat_id={cid}  ({name})")
    print("Put yours in TELEGRAM_CHAT_ID and the teammate's in OWNER_CHAT_ID in .env")


def check(send: bool) -> int:
    failures = 0

    def report(ok: bool, label: str, detail: str = "") -> None:
        nonlocal failures
        failures += not ok
        print(f"[{'OK' if ok else 'FAIL'}] {label}{(': ' + detail) if detail else ''}")

    for key in REQUIRED:
        report(bool(os.getenv(key, "").strip()), f"{key} set")

    if os.getenv("TELEGRAM_BOT_TOKEN"):
        try:
            me = tg("getMe")
            report(True, "Telegram bot reachable", f"@{me['username']}")
        except SystemExit as exc:
            report(False, "Telegram bot reachable", str(exc))
        if send:
            for var, who in (("TELEGRAM_CHAT_ID", "buyer"), ("OWNER_CHAT_ID", "owner")):
                if not os.getenv(var):
                    continue
                try:
                    msg = send_message(f"Setup check: {who} chat is wired up.", os.getenv(var))
                    report(True, f"test message to {var}", f"message_id={msg['message_id']}")
                except (TelegramError, httpx.HTTPError) as exc:
                    report(False, f"test message to {var}", str(exc))

    if os.getenv("LANGSMITH_API_KEY"):
        try:
            from langsmith import Client, traceable

            project = os.getenv("LANGSMITH_PROJECT", "default")
            report(os.getenv("LANGSMITH_TRACING", "").lower() == "true", "LANGSMITH_TRACING=true")
            Client().list_projects(limit=1).__next__()  # auth check

            @traceable(name="setup_check", project_name=project)
            def ping() -> str:
                return "pong"

            ping()
            report(True, "LangSmith auth + test trace", f"project '{project}'")
        except StopIteration:
            report(True, "LangSmith auth")
        except Exception as exc:  # noqa: BLE001
            report(False, "LangSmith", str(exc)[:200])
    return failures


if __name__ == "__main__":
    ap =argparse.ArgumentParser()
    ap.add_argument("--find-chats", action="store_true")
    ap.add_argument("--no-send", action="store_true")
    args = ap.parse_args()
    if args.find_chats:
        find_chats()
    else:
        sys.exit(1 if check(send=not args.no_send) else 0)
