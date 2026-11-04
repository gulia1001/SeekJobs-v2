"""SeekJobs Telegram bot: connect an account and get new matching jobs every morning.

  python telegram_bot.py               # answer commands + send the daily digest at DIGEST_HOUR (Almaty time)
  python telegram_bot.py --digest-now  # send today's digest once and exit

Commands: /start <code> (connect — the website gives the link), /jobs (best matches now),
          /stop (pause the daily message), /resume, /help
Needs TELEGRAM_BOT_TOKEN from @BotFather (and TELEGRAM_BOT_USERNAME for the website's link).
Without a token the bot exits — the rest of SeekJobs works without it.
"""
from __future__ import annotations

import argparse
import html
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

import pandas as pd  # noqa: E402
from sqlalchemy import and_, insert, select, update  # noqa: E402

from services import app_db  # noqa: E402
from services.data_loader import find_matching_vacancies, load_jobs  # noqa: E402
from services.job_matcher import _row_to_job  # noqa: E402

log = logging.getLogger("seekjobs.bot")

ALMATY = timezone(timedelta(hours=5))  # Kazakhstan: UTC+5 all year
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR") or 9)  # after the 08:00 ETL
DIGEST_MAX_JOBS = 5
FRESH_DAYS = 3  # the digest only announces jobs posted in the last few days

TEXT = {
    "en": {
        "welcome": "Hi! I send IT vacancies from Kazakhstan that match your CV.\n\n"
                   "To connect: log in on the SeekJobs website → Account → <b>Connect Telegram</b>.",
        "linked": "✅ Connected! Every morning I'll send new jobs that match your profile.\n"
                  "Send /jobs to see the best matches now.",
        "bad_code": "This link has expired or was already used. Open Account → Connect Telegram on the website again.",
        "no_profile": "Your profile is empty. On the website, analyze your CV and press <b>Save profile</b>.",
        "jobs_header": "Your best matches right now:",
        "digest_header": "☀️ New jobs for you today: {n}",
        "no_matches": "No matching jobs right now. I'll write when new ones appear.",
        "stopped": "Paused. I won't send the daily message. Send /resume to turn it back on.",
        "resumed": "Daily messages are on again.",
        "help": "/jobs — best matches now\n/stop — pause the daily message\n/resume — turn it back on",
        "open": "Open",
        "match": "match",
    },
    "ru": {
        "welcome": "Привет! Я присылаю IT-вакансии Казахстана, которые подходят к вашему резюме.\n\n"
                   "Чтобы подключиться: войдите на сайте SeekJobs → Аккаунт → <b>Подключить Telegram</b>.",
        "linked": "✅ Готово! Каждое утро я буду присылать новые подходящие вакансии.\n"
                  "Отправьте /jobs, чтобы увидеть лучшие совпадения сейчас.",
        "bad_code": "Ссылка устарела или уже использована. Снова откройте на сайте Аккаунт → Подключить Telegram.",
        "no_profile": "Профиль пуст. На сайте проанализируйте резюме и нажмите <b>Сохранить профиль</b>.",
        "jobs_header": "Лучшие совпадения сейчас:",
        "digest_header": "☀️ Новые вакансии для вас сегодня: {n}",
        "no_matches": "Подходящих вакансий пока нет. Напишу, когда появятся новые.",
        "stopped": "Пауза: ежедневные сообщения выключены. Отправьте /resume, чтобы включить снова.",
        "resumed": "Ежедневные сообщения снова включены.",
        "help": "/jobs — лучшие вакансии сейчас\n/stop — выключить ежедневные сообщения\n/resume — включить снова",
        "open": "Открыть",
        "match": "совпадение",
    },
    "kk": {
        "welcome": "Сәлем! Мен түйіндемеңізге сай келетін Қазақстандағы IT вакансияларын жіберемін.\n\n"
                   "Қосылу үшін: SeekJobs сайтына кіріңіз → Аккаунт → <b>Telegram қосу</b>.",
        "linked": "✅ Дайын! Әр таңертең профиліңізге сай жаңа вакансияларды жіберемін.\n"
                  "Қазір ең сәйкес вакансияларды көру үшін /jobs жіберіңіз.",
        "bad_code": "Сілтеменің мерзімі өтті немесе ол қолданылған. Сайтта Аккаунт → Telegram қосу бөлімін қайта ашыңыз.",
        "no_profile": "Профиліңіз бос. Сайтта түйіндемеңізді талдап, <b>Профильді сақтау</b> батырмасын басыңыз.",
        "jobs_header": "Қазіргі ең сәйкес вакансиялар:",
        "digest_header": "☀️ Бүгін сізге жаңа вакансиялар: {n}",
        "no_matches": "Әзірге сәйкес вакансия жоқ. Жаңалары шыққанда жазамын.",
        "stopped": "Кідіріс: күнделікті хабарламалар өшірілді. Қайта қосу үшін /resume жіберіңіз.",
        "resumed": "Күнделікті хабарламалар қайта қосылды.",
        "help": "/jobs — қазіргі ең сәйкес вакансиялар\n/stop — күнделікті хабарламаны өшіру\n/resume — қайта қосу",
        "open": "Ашу",
        "match": "сәйкестік",
    },
}


def t(lang: str | None, key: str, **kw) -> str:
    return TEXT.get(lang or "ru", TEXT["ru"])[key].format(**kw)


# ── Telegram HTTP API ───────────────────────────────────────────────────────
class TelegramAPI:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self.base = f"https://api.telegram.org/bot{token}"
        self.http = client or httpx.Client(timeout=40)

    def get_updates(self, offset: int, timeout: int = 25) -> list[dict]:
        r = self.http.get(f"{self.base}/getUpdates",
                          params={"offset": offset, "timeout": timeout, "allowed_updates": '["message"]'})
        r.raise_for_status()
        return r.json().get("result", [])

    def send_message(self, chat_id: str | int, text: str) -> bool:
        """False when the user blocked the bot (HTTP 403)."""
        r = self.http.post(f"{self.base}/sendMessage", json={
            "chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
        if r.status_code == 403:
            return False
        r.raise_for_status()
        return True


# ── accounts ↔ chats ────────────────────────────────────────────────────────
def link_chat(code: str, chat_id: str) -> dict | None:
    """Connect the chat to the account that created `code`. Returns the user or None."""
    tl, u = app_db.telegram_links, app_db.users
    now = app_db.utcnow()
    with app_db.get_engine().begin() as conn:
        row = conn.execute(select(tl).where(tl.c.link_code == code, tl.c.code_expires_at > now)).mappings().first()
        if not row:
            return None
        # a chat belongs to one account: free it if another account had it
        conn.execute(update(tl).where(tl.c.chat_id == chat_id, tl.c.user_id != row["user_id"]).values(chat_id=None))
        conn.execute(update(tl).where(tl.c.user_id == row["user_id"]).values(
            chat_id=chat_id, linked_at=now, link_code=None, code_expires_at=None))
        conn.execute(update(app_db.profiles).where(app_db.profiles.c.user_id == row["user_id"]).values(notify=True))
        return dict(conn.execute(select(u).where(u.c.id == row["user_id"])).mappings().one())


def user_by_chat(chat_id: str) -> dict | None:
    tl, u = app_db.telegram_links, app_db.users
    with app_db.get_engine().connect() as conn:
        row = conn.execute(select(u).join(tl, tl.c.user_id == u.c.id).where(tl.c.chat_id == chat_id)).mappings().first()
    return dict(row) if row else None


def unlink_chat(chat_id: str) -> None:
    with app_db.get_engine().begin() as conn:
        conn.execute(update(app_db.telegram_links).where(app_db.telegram_links.c.chat_id == chat_id)
                     .values(chat_id=None))


def get_profile(user_id: int) -> dict | None:
    import json

    with app_db.get_engine().connect() as conn:
        p = conn.execute(select(app_db.profiles).where(app_db.profiles.c.user_id == user_id)).mappings().first()
    if not p:
        return None
    return {"skills": json.loads(p["skills"] or "[]"), "target_roles": json.loads(p["target_roles"] or "[]"),
            "level": p["level"] or "", "notify": bool(p["notify"])}


def set_notify(user_id: int, on: bool) -> None:
    with app_db.get_engine().begin() as conn:
        conn.execute(update(app_db.profiles).where(app_db.profiles.c.user_id == user_id).values(notify=on))


# ── matches ─────────────────────────────────────────────────────────────────
def top_matches(profile: dict, limit: int, exclude: set[str] = frozenset(), fresh_only: bool = False) -> list[dict]:
    rows = find_matching_vacancies(profile["skills"], categories=profile["target_roles"] or None,
                                   user_level=profile["level"], top_n=limit + len(exclude) + 20)
    if fresh_only and "posted_at" in rows.columns:
        cutoff = pd.Timestamp(app_db.utcnow() - timedelta(days=FRESH_DAYS))
        rows = rows[rows["posted_at"].isna() | (pd.to_datetime(rows["posted_at"]) >= cutoff)]
    out = []
    for _, row in rows.iterrows():
        job = _row_to_job(row)
        if job["id"] in exclude:
            continue
        out.append({**job, "score": round(float(row["match_score"]) * 100)})
        if len(out) == limit:
            break
    return out


def format_jobs(header: str, jobs: list[dict], lang: str) -> str:
    lines = [header, ""]
    for j in jobs:
        where = " · ".join(filter(None, [j["company"], j["city"]]))
        salary = "" if j["salary_display"] == "Salary not listed" else j["salary_display"]
        details = " · ".join(filter(None, [salary, f"{t(lang, 'match')} {j['score']}%"]))
        link = f' — <a href="{html.escape(j["url"])}">{t(lang, "open")}</a>' if j["url"] else ""
        lines.append(f"<b>{html.escape(j['title'])}</b>{link}\n{html.escape(where)}\n{html.escape(details)}\n")
    return "\n".join(lines).strip()


# ── commands ────────────────────────────────────────────────────────────────
def handle_update(api: TelegramAPI, update_: dict) -> None:
    msg = update_.get("message") or {}
    chat_id = str((msg.get("chat") or {}).get("id") or "")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return
    command, _, arg = text.partition(" ")
    command = command.split("@")[0].lower()  # "/jobs@SeekJobsBot" in groups
    user = user_by_chat(chat_id)
    lang = (user or {}).get("language") or "ru"

    if command == "/start" and arg.strip():
        linked = link_chat(arg.strip(), chat_id)
        if linked:
            api.send_message(chat_id, t(linked["language"], "linked"))
        else:
            api.send_message(chat_id, t(lang, "bad_code"))
        return
    if not user:
        api.send_message(chat_id, t(lang, "welcome"))
        return
    if command == "/jobs":
        profile = get_profile(user["id"])
        if not profile or not profile["skills"]:
            api.send_message(chat_id, t(lang, "no_profile"))
            return
        jobs = top_matches(profile, DIGEST_MAX_JOBS)
        api.send_message(chat_id, format_jobs(t(lang, "jobs_header"), jobs, lang) if jobs else t(lang, "no_matches"))
    elif command == "/stop":
        set_notify(user["id"], False)
        api.send_message(chat_id, t(lang, "stopped"))
    elif command == "/resume":
        set_notify(user["id"], True)
        api.send_message(chat_id, t(lang, "resumed"))
    else:
        api.send_message(chat_id, t(lang, "help"))


# ── daily digest ────────────────────────────────────────────────────────────
def send_digest(api: TelegramAPI) -> dict:
    """For every connected user with daily messages on: up to 5 new matching jobs they have not
    been sent before. Users with nothing new get no message."""
    u, tl, p, ns = app_db.users, app_db.telegram_links, app_db.profiles, app_db.notifications_sent
    with app_db.get_engine().connect() as conn:
        users = conn.execute(
            select(u.c.id, u.c.language, tl.c.chat_id).join(tl, tl.c.user_id == u.c.id)
            .join(p, p.c.user_id == u.c.id).where(and_(tl.c.chat_id.isnot(None), p.c.notify == True))  # noqa: E712
        ).mappings().all()
    load_jobs()  # refresh the dataset if it is older than the reload interval
    stats = {"users": len(users), "messages": 0, "jobs": 0}
    for user in users:
        profile = get_profile(user["id"])
        if not profile or not profile["skills"]:
            continue
        with app_db.get_engine().connect() as conn:
            already = set(conn.execute(select(ns.c.job_id).where(ns.c.user_id == user["id"])).scalars())
        jobs = top_matches(profile, DIGEST_MAX_JOBS, exclude=already, fresh_only=True)
        if not jobs:
            continue
        lang = user["language"] or "ru"
        if not api.send_message(user["chat_id"], format_jobs(t(lang, "digest_header", n=len(jobs)), jobs, lang)):
            unlink_chat(user["chat_id"])  # the user blocked the bot
            continue
        now = app_db.utcnow()
        with app_db.get_engine().begin() as conn:
            conn.execute(insert(ns), [{"user_id": user["id"], "job_id": j["id"], "sent_at": now} for j in jobs])
        stats["messages"] += 1
        stats["jobs"] += len(jobs)
    log.info("Digest: %(users)d connected users, %(messages)d messages, %(jobs)d jobs", stats)
    return stats


def next_digest_time(now: datetime) -> datetime:
    """Next DIGEST_HOUR:00 Almaty time, as an aware datetime."""
    local = now.astimezone(ALMATY)
    target = local.replace(hour=DIGEST_HOUR, minute=0, second=0, microsecond=0)
    return target if target > local else target + timedelta(days=1)


def run(api: TelegramAPI) -> None:
    offset = 0
    next_digest = next_digest_time(datetime.now(timezone.utc))
    log.info("Bot started. Next digest at %s Almaty time.", next_digest.strftime("%Y-%m-%d %H:%M"))
    while True:
        try:
            for upd in api.get_updates(offset):
                offset = upd["update_id"] + 1
                try:
                    handle_update(api, upd)
                except Exception:
                    log.exception("Could not handle update %s", upd.get("update_id"))
            if datetime.now(timezone.utc) >= next_digest:
                send_digest(api)
                next_digest = next_digest_time(datetime.now(timezone.utc))
        except httpx.HTTPError as e:
            log.warning("Telegram connection problem: %s — retrying in 5 s", e)
            time.sleep(5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--digest-now", action="store_true", help="send today's digest once and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-14s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN is not set — the Telegram bot is off.")
        return 0
    api = TelegramAPI(token)
    app_db.get_engine()
    if args.digest_now:
        send_digest(api)
        return 0
    run(api)
    return 0


if __name__ == "__main__":
    sys.exit(main())
