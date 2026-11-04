"""Optional failure alerts to a Telegram chat (used by the Airflow DAG).

Set ALERT_TELEGRAM_BOT_TOKEN (from @BotFather) and ALERT_TELEGRAM_CHAT_ID (your chat or a
group with the bot). Without them alerts are just logged.
"""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger("pipeline.alerts")


def send_alert(text: str) -> bool:
    token, chat = os.getenv("ALERT_TELEGRAM_BOT_TOKEN"), os.getenv("ALERT_TELEGRAM_CHAT_ID")
    if not (token and chat):
        log.warning("ALERT (Telegram alerts not configured): %s", text)
        return False
    try:
        resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat, "text": text[:4000]}, timeout=10)
        return resp.ok
    except requests.RequestException as e:  # an alert must never break the pipeline
        log.warning("Could not send Telegram alert: %s", e)
        return False
