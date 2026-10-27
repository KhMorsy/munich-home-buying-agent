import httpx
import pytest

from agent.tools import notify


def _resp(status=200, body=None):
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://x"))


def test_send_message_requires_config(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(notify.TelegramError, match="TOKEN"):
        notify.send_message("hi")

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(notify.TelegramError, match="chat id"):
        notify.send_message("hi")


def test_send_message_posts_to_chat_and_truncates(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    seen = {}

    def fake_post(url, json, timeout):
        seen.update(url=url, json=json)
        return _resp(body={"ok": True, "result": {"message_id": 7}})

    monkeypatch.setattr(notify.httpx, "post", fake_post)

    assert notify.send_message("x" * 5000)["message_id"] == 7
    assert seen["url"].endswith("/bottok/sendMessage")
    assert seen["json"]["chat_id"] == "111"
    assert len(seen["json"]["text"]) == notify.MAX_LEN

    notify.send_message("hi", chat_id="222")
    assert seen["json"]["chat_id"] == "222"


def test_tool_returns_error_string_instead_of_raising(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.setattr(
        notify.httpx,
        "post",
        lambda *a, **k: _resp(400, {"ok": False, "description": "chat not found"}),
    )
    out = notify.send_telegram.invoke({"text": "hi"})
    assert out.startswith("FAILED") and "chat not found" in out

    def boom(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(notify.httpx, "post", boom)
    assert notify.send_telegram.invoke({"text": "hi"}).startswith("FAILED")
