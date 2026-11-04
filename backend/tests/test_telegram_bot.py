"""Telegram bot: linking, commands, daily digest — with a fake Telegram (no network)."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import telegram_bot as bot
from conftest import new_account


class FakeTelegram:
    def __init__(self, blocked: set[str] = frozenset()):
        self.sent: list[tuple[str, str]] = []
        self.blocked = blocked

    def send_message(self, chat_id, text):
        if str(chat_id) in self.blocked:
            return False
        self.sent.append((str(chat_id), text))
        return True

    def last(self, chat_id):
        return [t for c, t in self.sent if c == str(chat_id)][-1]


def message(chat_id, text):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


@pytest.fixture
def linked_user(client, monkeypatch, profile_payload):
    """A user with a saved profile whose Telegram chat 7001… is connected. Returns (headers, chat_id, api)."""
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "SeekJobsTestBot")
    headers, user = new_account(client, language="en")
    client.put("/api/me/profile", headers=headers, json=profile_payload)
    code = client.post("/api/me/telegram", headers=headers).json()["url"].split("start=")[1]
    chat_id = str(7000 + user["id"])
    api = FakeTelegram()
    bot.handle_update(api, message(chat_id, f"/start {code}"))
    assert "Connected" in api.last(chat_id)
    return headers, chat_id, api


def test_connect_with_link_code(client, linked_user):
    headers, chat_id, api = linked_user
    assert client.get("/api/me/telegram", headers=headers).json()["linked"] is True


def test_link_code_works_once_and_expires(client, linked_user, monkeypatch):
    headers, chat_id, api = linked_user
    code = client.post("/api/me/telegram", headers=headers).json()["url"].split("start=")[1]
    bot.handle_update(api, message("999", f"/start {code}"))
    bot.handle_update(api, message("998", f"/start {code}"))  # second use
    assert "Connected" in api.last("999")
    assert "устарела" in api.last("998")  # unknown chat: Russian by default

    from sqlalchemy import update

    from services import app_db
    code = client.post("/api/me/telegram", headers=headers).json()["url"].split("start=")[1]
    with app_db.get_engine().begin() as conn:  # make it 20 minutes old
        conn.execute(update(app_db.telegram_links).where(app_db.telegram_links.c.link_code == code)
                     .values(code_expires_at=app_db.utcnow() - timedelta(minutes=5)))
    bot.handle_update(api, message("997", f"/start {code}"))
    assert "устарела" in api.last("997")


def test_unknown_chat_gets_instructions_in_russian(client):
    api = FakeTelegram()
    bot.handle_update(api, message("123456", "/jobs"))
    assert "Подключить Telegram" in api.last("123456")


def test_jobs_command_lists_matches(linked_user):
    _, chat_id, api = linked_user
    bot.handle_update(api, message(chat_id, "/jobs@SeekJobsTestBot"))
    text = api.last(chat_id)
    assert "Backend Developer (Python)" in text
    assert '<a href="https://hh.kz/vacancy/1">Open</a>' in text
    assert "match 100%" in text


def test_daily_digest_sends_each_job_once(linked_user):
    _, chat_id, api = linked_user
    bot.send_digest(api)
    first = api.last(chat_id)
    assert first.startswith("☀️") and "Backend Developer (Python)" in first

    sent_before = len(api.sent)
    bot.send_digest(api)  # nothing new since the last digest
    assert all(c != chat_id for c, _ in api.sent[sent_before:])


def test_stop_and_resume(linked_user):
    _, chat_id, api = linked_user
    bot.handle_update(api, message(chat_id, "/stop"))
    assert "Paused" in api.last(chat_id)
    sent_before = len(api.sent)
    bot.send_digest(api)
    assert all(c != chat_id for c, _ in api.sent[sent_before:])

    bot.handle_update(api, message(chat_id, "/resume"))
    bot.send_digest(api)
    assert api.last(chat_id).startswith("☀️")


def test_blocked_bot_unlinks_chat(client, linked_user):
    headers, chat_id, _ = linked_user
    bot.send_digest(FakeTelegram(blocked={chat_id}))
    assert client.get("/api/me/telegram", headers=headers).json()["linked"] is False


def test_next_digest_time_is_9_in_almaty():
    # 03:00 UTC = 08:00 Almaty -> today 09:00 Almaty
    nxt = bot.next_digest_time(datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc))
    assert (nxt.day, nxt.hour, nxt.utcoffset()) == (5, 9, timedelta(hours=5))
    # 05:00 UTC = 10:00 Almaty -> tomorrow
    assert bot.next_digest_time(datetime(2026, 11, 5, 5, 0, tzinfo=timezone.utc)).day == 6


def test_http_client_talks_to_telegram():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [{"update_id": 5}]})
        if json.loads(request.content)["chat_id"] == "blocked":
            return httpx.Response(403, json={"ok": False})
        return httpx.Response(200, json={"ok": True})

    api = bot.TelegramAPI("123:ABC", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert api.get_updates(offset=5) == [{"update_id": 5}]
    assert api.send_message("42", "<b>hi</b>") is True
    assert api.send_message("blocked", "hi") is False
    payload = json.loads(requests[1].content)
    assert requests[1].url.path == "/bot123:ABC/sendMessage"
    assert payload == {"chat_id": "42", "text": "<b>hi</b>", "parse_mode": "HTML", "disable_web_page_preview": True}


def test_bot_without_token_exits_quietly(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert bot.main([]) == 0
