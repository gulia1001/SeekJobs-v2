"""Collect posts from public Telegram channels through their web preview (https://t.me/s/<name>).

No Telegram account or API key is needed — only public channels work. The preview shows
about 20 posts per page; older pages are opened with ?before=<message id>.
Requests are spaced out (REQUEST_DELAY_SECONDS) to be polite to Telegram.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("pipeline.telegram")

CHANNELS_FILE = Path(__file__).with_name("telegram_channels.txt")
BASE_URL = "https://t.me/s/"
USER_AGENT = "SeekJobsBot/0.2 (+https://github.com/gulia1001/SeekJobs-v2)"
REQUEST_DELAY_SECONDS = 1.5


@dataclass
class Channel:
    handle: str
    company: str = ""  # default company when the whole channel belongs to one employer


@dataclass
class Post:
    channel: str
    message_id: int
    posted_at: datetime  # UTC, without tzinfo
    text: str
    url: str


def load_channels(path: Path = CHANNELS_FILE) -> list[Channel]:
    channels: list[Channel] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        handle, _, company = (part.strip() for part in line.partition("|"))
        handle = re.sub(r"^(?:https?://)?(?:t\.me/(?:s/)?)?@?", "", handle).strip("/")
        if handle:
            channels.append(Channel(handle=handle, company=company))
    return channels


def parse_page(html: str, channel: str) -> tuple[list[Post], int | None]:
    """Posts with text on one preview page, plus the smallest message id on the page
    (including posts without text — needed to open the next, older page)."""
    soup = BeautifulSoup(html, "html.parser")
    posts: list[Post] = []
    min_id: int | None = None
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        handle, _, raw_id = msg["data-post"].rpartition("/")
        if not raw_id.isdigit():
            continue
        message_id = int(raw_id)
        min_id = message_id if min_id is None else min(min_id, message_id)
        if "service_message" in msg.get("class", []):
            continue  # "channel pinned a message" etc.

        text_div = msg.select_one("div.tgme_widget_message_bubble > div.tgme_widget_message_text")
        time_tag = msg.select_one("a.tgme_widget_message_date time[datetime]")
        if text_div is None or time_tag is None:
            continue  # photo/video without caption, service message
        for br in text_div.find_all("br"):
            br.replace_with("\n")
        text = text_div.get_text().strip()
        if not text:
            continue
        posted_at = datetime.fromisoformat(time_tag["datetime"]).astimezone(timezone.utc).replace(tzinfo=None)
        posts.append(Post(channel=channel, message_id=message_id, posted_at=posted_at,
                          text=text, url=f"https://t.me/{handle or channel}/{message_id}"))
    return posts, min_id


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def fetch_channel(
    channel: str,
    *,
    since: datetime,
    after_id: int = 0,
    max_pages: int = 50,
    session: requests.Session | None = None,
    delay: float = REQUEST_DELAY_SECONDS,
) -> list[Post]:
    """Posts newer than `after_id` and posted on/after `since` (UTC), oldest first."""
    session = session or _session()
    found: dict[int, Post] = {}
    before: int | None = None
    for page in range(max_pages):
        url = BASE_URL + channel + (f"?before={before}" if before else "")
        try:
            resp = session.get(url, timeout=20, allow_redirects=False)
        except requests.RequestException as e:
            log.warning("%s: request failed: %s", channel, e)
            break
        if resp.status_code != 200:
            # a redirect here means the channel is private, renamed or does not exist
            log.warning("%s: HTTP %s — is the channel public? (%s)", channel, resp.status_code, url)
            break
        posts, min_id = parse_page(resp.text, channel)
        if min_id is None:
            break
        for p in posts:
            if p.message_id > after_id and p.posted_at >= since:
                found[p.message_id] = p
        reached_known = min_id <= after_id + 1
        reached_since = any(p.posted_at < since for p in posts)
        if reached_known or reached_since or min_id <= 1:
            break
        before = min_id
        time.sleep(delay)
    else:
        log.info("%s: stopped after %d pages (max_pages)", channel, max_pages)
    return sorted(found.values(), key=lambda p: p.message_id)
