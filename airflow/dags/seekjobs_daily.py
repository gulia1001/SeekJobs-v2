"""
### SeekJobs — daily vacancy ETL

Collects IT vacancies from public Telegram channels **once a day at 08:00 Almaty time**.

`prepare_database` → `extract_<channel>` (one task per channel, 3 at a time) → `transform_load` → `expire_old_jobs` → `quality_check`

* **Channels:** `pipeline/scrapers/telegram_channels.txt` — add a line and the DAG gets a new task.
* **Relevant data:** only real vacancies are kept (no CV posts, ads, events); the last 7 days of every
  channel are re-read so posts edited to "вакансия закрыта" or deleted are hidden; jobs older than
  45 days expire; reposts of the same job are merged when the site reads them.
* **Failures** are retried twice; with `ALERT_TELEGRAM_BOT_TOKEN` + `ALERT_TELEGRAM_CHAT_ID` set you get
  a Telegram message. `quality_check` fails when no channel posted for 3 days or the rules stop recognizing vacancies.
* The same steps run without Airflow: `cd pipeline && python run_daily.py`.
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta

import pendulum
from airflow.sdk import dag, task

PIPELINE_DIR = os.environ.get("SEEKJOBS_PIPELINE_DIR", "/opt/airflow/pipeline")
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from scrapers.telegram import load_channels  # noqa: E402  (only reads the channel list file)


def _engine():
    import db  # the jobs database — DATABASE_URL in the environment

    return db.get_engine()


def _alert_on_failure(context) -> None:
    from alerts import send_alert

    ti = context.get("task_instance")
    send_alert(
        f"⚠️ SeekJobs ETL failed: {getattr(ti, 'task_id', '?')} (try {getattr(ti, 'try_number', '?')})\n"
        f"{context.get('exception')}"
    )


@dag(
    dag_id="seekjobs_daily_vacancies",
    schedule="0 8 * * *",
    start_date=pendulum.datetime(2026, 11, 1, tz="Asia/Almaty"),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=3,  # at most 3 channels fetched at the same time — be polite to Telegram
    default_args={
        "owner": "seekjobs",
        "retries": 2,
        "retry_delay": timedelta(minutes=10),
        "on_failure_callback": _alert_on_failure,
    },
    tags=["seekjobs", "etl", "telegram"],
    doc_md=__doc__,
)
def seekjobs_daily_vacancies():
    @task
    def prepare_database() -> str:
        """Create / upgrade the tables once, before the channel tasks start in parallel."""
        engine = _engine()
        return engine.url.render_as_string(hide_password=True)

    @task(execution_timeout=timedelta(minutes=15))
    def extract(handle: str, company: str = "") -> dict:
        """E: fetch one channel (new posts + re-read last 7 days) into raw_posts."""
        import etl
        from scrapers.telegram import Channel

        return etl.extract_channel(_engine(), Channel(handle, company), raise_errors=True)

    # all_done: still process what the other channels returned if one channel failed
    @task(trigger_rule="all_done", execution_timeout=timedelta(minutes=30))
    def transform_load() -> dict:
        """T+L: new/edited/deleted posts → vacancy filter + rules → jobs table."""
        import etl

        companies = {etl.source_of(c): c.company for c in load_channels()}
        return etl.transform_load(_engine(), companies)

    @task
    def expire_old_jobs() -> int:
        """Hide jobs posted more than 45 days ago."""
        import etl

        return etl.expire_old_jobs(_engine())

    @task(retries=0)
    def quality_check() -> dict:
        """Fail loudly when the data stops looking right."""
        import etl

        return etl.quality_check(_engine(), load_channels())

    extracts = [extract.override(task_id=f"extract_{c.handle}")(c.handle, c.company) for c in load_channels()]
    prepare_database() >> extracts >> transform_load() >> expire_old_jobs() >> quality_check()


seekjobs_daily_vacancies()
