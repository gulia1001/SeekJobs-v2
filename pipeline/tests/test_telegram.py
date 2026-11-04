from datetime import datetime

from scrapers.telegram import fetch_channel, load_channels, parse_page


def message(post_id: int, text: str | None, when: str = "2026-10-30T09:26:04+00:00", extra_class: str = "") -> str:
    body = f'<div class="tgme_widget_message_text js-message_text" dir="auto">{text}</div>' if text else ""
    return f"""
    <div class="tgme_widget_message_wrap js-widget_message_wrap">
      <div class="tgme_widget_message text_not_supported_wrap {extra_class} js-widget_message"
           data-post="devkz_jobs/{post_id}">
        <div class="tgme_widget_message_bubble">
          {body}
          <div class="tgme_widget_message_footer"><div class="tgme_widget_message_info">
            <span class="tgme_widget_message_meta">
              <a class="tgme_widget_message_date" href="https://t.me/devkz_jobs/{post_id}">
                <time datetime="{when}" class="time">09:26</time></a></span></div></div>
        </div>
      </div>
    </div>"""


def page(*messages: str) -> str:
    return "<html><body><section class='tgme_channel_history'>" + "".join(messages) + "</section></body></html>"


def test_parse_page_keeps_line_breaks_and_inline_text():
    html = page(
        message(101, "Python developer<br/>ЗП: <b>700 000</b> ₸<br/><a href='https://x.kz'>x.kz</a>"),
        message(102, None),                                    # photo without caption
        message(103, "channel pinned a message", extra_class="service_message"),
    )
    posts, min_id = parse_page(html, "devkz_jobs")
    assert min_id == 101
    assert len(posts) == 1
    p = posts[0]
    assert p.text == "Python developer\nЗП: 700 000 ₸\nx.kz"
    assert p.message_id == 101
    assert p.url == "https://t.me/devkz_jobs/101"
    assert p.posted_at == datetime(2026, 10, 30, 9, 26, 4)  # UTC, no tzinfo


class FakeResponse:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status


class FakeSession:
    """Serves pages by the ?before= value and records the URLs asked for."""

    def __init__(self, pages):
        self.pages, self.urls = pages, []

    def get(self, url, **_):
        self.urls.append(url)
        before = url.split("before=")[1] if "before=" in url else None
        return FakeResponse(self.pages.get(before, page()))


def test_fetch_pages_back_until_known_post():
    session = FakeSession({
        None: page(message(30, "new post 30"), message(31, "new post 31")),
        "30": page(message(28, "post 28"), message(29, "post 29")),
        "28": page(message(26, "old 26"), message(27, "old 27")),
    })
    posts = fetch_channel("devkz_jobs", since=datetime(2026, 1, 1), after_id=28, session=session, delay=0)
    assert [p.message_id for p in posts] == [29, 30, 31]
    assert len(session.urls) == 2  # stopped once it reached post 28


def test_fetch_stops_at_since_date():
    session = FakeSession({
        None: page(message(10, "new", when="2026-10-30T00:00:00+00:00")),
        "10": page(message(9, "old", when="2026-08-01T00:00:00+00:00")),
        "9": page(message(8, "older", when="2026-07-01T00:00:00+00:00")),
    })
    posts = fetch_channel("devkz_jobs", since=datetime(2026, 10, 1), session=session, delay=0)
    assert [p.message_id for p in posts] == [10]
    assert len(session.urls) == 2


def test_private_or_missing_channel_is_skipped():
    class Redirect(FakeSession):
        def get(self, url, **_):
            return FakeResponse("", status=302)

    assert fetch_channel("no_such_channel", since=datetime(2026, 1, 1), session=Redirect({}), delay=0) == []


def test_channels_file_format(tmp_path):
    f = tmp_path / "channels.txt"
    f.write_text("# comment\ndevkz_jobs\n\n@itvacancykz\nhttps://t.me/s/workitkz\nhalyk_jumys | Halyk Bank  # employer\n",
                 encoding="utf-8")
    channels = load_channels(f)
    assert [(c.handle, c.company) for c in channels] == [
        ("devkz_jobs", ""), ("itvacancykz", ""), ("workitkz", ""), ("halyk_jumys", "Halyk Bank"),
    ]


def test_real_channels_file_has_requested_channels():
    handles = {c.handle for c in load_channels()}
    assert {"itvacancykz", "devkz_jobs", "halyk_jumys"} <= handles


def test_errors_raise_when_asked():
    """Airflow uses raise_errors=True so a failed fetch fails the task (and is retried)."""
    import pytest
    from scrapers.telegram import ChannelFetchError

    class Broken(FakeSession):
        def get(self, url, **_):
            return FakeResponse("", status=500)

    with pytest.raises(ChannelFetchError, match="HTTP 500"):
        fetch_channel("devkz_jobs", since=datetime(2026, 1, 1), session=Broken({}), delay=0, raise_errors=True)


def test_alerts_without_configuration_do_not_fail(monkeypatch):
    from alerts import send_alert

    monkeypatch.delenv("ALERT_TELEGRAM_BOT_TOKEN", raising=False)
    assert send_alert("test") is False
