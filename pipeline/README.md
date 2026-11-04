# Pipeline — Kazakhstan IT job data

## Daily ETL (main flow — no LLM, no API keys)

The ETL steps live in `etl.py`. **Airflow** runs them every day (`../airflow/dags/seekjobs_daily.py`,
started by `docker compose up`); `run_daily.py` runs the same steps from the command line.

| Step | What it does |
|---|---|
| `extract_<channel>` | fetch the channel; save new posts; re-read the last 7 days to notice **edited** and **deleted** posts |
| `transform_load` | new / changed posts → vacancy filter + rules → `jobs`; posts edited to "вакансия закрыта" or deleted → job hidden |
| `expire_old_jobs` | hide jobs posted more than 45 days ago |
| `quality_check` | **fails** if no channel posted for 3 days or < 20 % of this week's posts look like vacancies (Telegram layout / rules broke); **warns** about silent channels and low city / skills coverage |

Every hidden job keeps its reason in `jobs.inactive_reason` (`expired`, `closed`, `deleted`).

```text
Telegram channels (t.me/s/<name>)  →  scrapers/telegram.py      fetch new posts (public web preview)
                                    →  extract/rules.py          vacancy? title, company, city, salary,
                                                                 level, category, skills, format
                                    →  db.py                     raw_posts + jobs tables
                                                                 (SQLite data/jobs.db, or Postgres)
backend/services/data_loader.py    ←  reads active jobs from the last 45 days, merges reposts
```

```bash
cd pipeline
pip install -r requirements.txt     # 5 small libraries, Python 3.10+
python run_daily.py                 # all steps; first run: last 30 days of every channel (~1 minute)
python run_daily.py                 # later runs: new posts + re-check of the last 7 days
python run_daily.py extract         # or one step: extract | transform | expire | check
python run_daily.py --days 60       # look further back on a channel's first run
python run_daily.py --reextract     # re-run extraction on all saved posts (after improving the rules)
```

**Channels** are listed in `scrapers/telegram_channels.txt` — one name per line, optionally
`name | Company` for a channel that belongs to one employer. Only public channels work
(`https://t.me/s/<name>` must open in a browser). hh.kz is not used: its API now requires
a registered application.

**Run it every day** — with Docker, Airflow does this (UI at http://localhost:8088). Without Docker, on Windows:

```bat
schtasks /Create /SC DAILY /ST 09:00 /TN "SeekJobs collector" ^
  /TR "cmd /c cd /d C:\path\to\SeekJobs-v2\pipeline && python run_daily.py"
```

(macOS/Linux: a cron line `0 9 * * * cd /path/to/SeekJobs-v2/pipeline && python run_daily.py`.)

**Quality** (rules, no LLM — checked by hand on 136 real posts, Nov 2026): 119 kept as vacancies;
the rest were mostly events, channel news, job seekers' CVs and closed vacancies, plus a few very
short real vacancies that were missed. In the kept ones: city found 87 %, level 80 %, skills 71 %,
company 67 %, salary 47 % (many posts don't state a salary). Posts that list several vacancies
become one job. Raw posts are kept, so an LLM pass can improve this later.

## Layout

```text
pipeline/
├── etl.py               the ETL steps (used by Airflow and run_daily.py)
├── run_daily.py         command line for the ETL
├── db.py                database tables + helpers (SQLite by default, Postgres via DATABASE_URL)
├── alerts.py            optional Telegram alert when the ETL fails
├── scrapers/            telegram.py, telegram_channels.txt, older source notebooks
├── extract/             rules.py (job fields), skills.py (shared with backend — keep identical)
├── tests/               pytest (no network)
├── transform/ enrich/   older batch flow: CSV cleaning + LLM enrichment (below)
├── dashboard/           internal Streamlit market dashboard (reads the batch CSV)
└── data/                NOT in git: jobs.db, CSV files
```

## Older batch flow (CSV + LLM enrichment)

Used to build the original ~15k-vacancy dataset. Needs Python 3.11+ and, for the LLM step,
a GROQ_API_KEY. The backend only uses this CSV when the jobs database is empty.

```bash
pip install -r requirements-batch.txt
python run_pipeline.py              # data/raw → … → data/final/analysis_ready_jobs_salary_fixed_v3.csv
python run_pipeline.py --with-llm   # also re-run LLM enrichment (costs API money)
streamlit run dashboard/main.py     # internal analytics dashboard
```

| Step | Command | Output |
|---|---|---|
| 1. Integrate sources | `python transform/integrate_sources.py` | `data/interim/unified_job_database.csv` |
| 2. LLM enrichment | `python -m enrich.main --input data/interim/unified_job_database.csv --output data/interim/enriched_jobs_full_v1.csv --client groq --full-run` | `data/interim/enriched_jobs_full_v1.csv` |
| 3. Prepare | `python transform/prepare_analysis_ready.py` | `data/final/analysis_ready_jobs.csv` + marts |
| 4. Repair salaries | `python transform/repair_salary.py` | `data/final/analysis_ready_jobs_salary_fixed_v3.csv` |

Docs: `docs/README_ANALYSIS_READY_DATASET_RU_EN.md`, `docs/README_LLM_INTEGRATION.md`, `docs/reports/`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```
