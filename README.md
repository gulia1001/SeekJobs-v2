# SeekJobs

Career assistant for IT job seekers in Kazakhstan. Upload a CV (and optionally a
LinkedIn profile PDF and your GitHub), see fresh matching vacancies with your skill
gaps and market salary, and download a CV tailored to a specific job (PDF / Word).

Jobs are collected once a day by an **Airflow ETL** from public Telegram IT channels
(devkz_jobs, itvacancykz, workitkz, itcom_kz, zhumysbarit, halyk_jumys, insferaforyou — list in
`pipeline/scrapers/telegram_channels.txt`). How it all fits together: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Structure

```text
SeekJobs-v2/
├── frontend/           Next.js 14 — landing page + app
├── backend/            FastAPI — profile analysis, job matching, CV generation & export
├── pipeline/           ETL code: Telegram → rules → database (etl.py, run_daily.py) + older batch flow
├── airflow/            Airflow DAG that runs the ETL daily (dags/seekjobs_daily.py) + its image
├── docs/               ARCHITECTURE.md — diagrams of the system, the ETL and the user flow
├── infra/              Postgres init script
├── docker-compose.yml  Postgres + Airflow + backend + frontend
└── .env.example        settings (all optional)
```

## Run it now — no LLM / API key needed

Needs **Python 3.10+** and **Node.js 20+**. Three terminals, from the project folder:

```bash
# 1. collect jobs (≈1 minute, creates pipeline/data/jobs.db)
cd pipeline
pip install -r requirements.txt
python run_daily.py

# 2. backend — finds pipeline/data/jobs.db by itself
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8001

# 3. frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:3001. Re-run `python run_daily.py` once a day for fresh jobs
(or schedule it — see `pipeline/README.md`); the backend picks up new jobs within 10 minutes.

**What works without an LLM key:** CV / LinkedIn PDF / GitHub analysis, skill detection,
job matching with skill gaps, market salary, job links, CV download as PDF / Word with your
real skills, contacts, GitHub projects and certificates.
**What the key adds** (`GROQ_API_KEY` in `.env`, free tier at console.groq.com): the CV text is
rewritten for each job (summary, experience bullets), and each match gets a one-line explanation.

### Or with Docker — everything incl. the daily Airflow ETL

```bash
docker compose up --build -d
```

| What | Where |
|---|---|
| Website | http://localhost:3001 |
| API | http://localhost:8001/api/health |
| Airflow (ETL) | http://localhost:8088 — login `admin` / `admin` (set `AIRFLOW_ADMIN_PASSWORD` in `.env`) |

Airflow runs the DAG `seekjobs_daily_vacancies` **every day at 08:00 Almaty time** — and once right
after the first start. In the Airflow UI you can see each channel's task, its logs, and press ▶ to run
it now. Needs ~3 GB RAM for Docker. Without Airflow: `docker compose up -d db backend frontend`.

> **OneDrive:** Docker cannot build from a folder synced by OneDrive (`archive/tar: unknown file mode`).
> Keep the project outside OneDrive, e.g. `C:\dev\SeekJobs-v2`, before `docker compose up --build`.

## How matching works

- Skill names are normalized, so `Postgres` = `PostgreSQL`, `React.js` = `React`,
  `1С` = `1C`, `#cpp` = `C++` (`backend/services/skills.py`).
- Score = share of the **job's** skills you have (soft skills and spoken languages are not
  counted). Having many other skills never lowers your score.
- Ranking prefers jobs that list enough skills to judge (4 of 4 beats 1 of 1) and jobs at
  your level (a junior sees senior roles lower).
- Missing skills are listed most-in-demand first. No role selected → all categories.
- Only jobs posted in the last 45 days are shown; a job reposted in several channels is shown once.

## Tests

```bash
cd backend  && pip install -r requirements.txt -r requirements-dev.txt && pytest -q
cd pipeline && pip install -r requirements.txt -r requirements-dev.txt && pytest -q
```

No network, real data or API keys needed. GitHub Actions (`.github/workflows/ci.yml`) runs
both suites (pipeline also on Postgres) and the frontend production build on every push / PR.

## API

| Method | Path | What it does |
|---|---|---|
| GET | `/api/jobs` | Fresh vacancies, newest first (`page`, `limit`, `category`, `level`, `format`) |
| POST | `/api/analyze` | Form: `cv_file` (PDF/DOCX/TXT ≤5 MB), `linkedin_pdf` (LinkedIn "Save to PDF"), `github_url`, `preferred_salary`, `target_roles[]` → skills + top matches |
| POST | `/api/cv/generate` | Tailored CV (JSON + LaTeX) for one job — uses only facts from the CV/profile |
| POST | `/api/cv/export` | `{cv, format: "pdf" \| "docx"}` → downloadable file (real text, Cyrillic supported) |

## Roadmap

- **Phase 0 — cleanup** ✅ structure, secrets out of git, CV-only crash fixed, tailored CV uses real CV text
- **Phase 1 — MVP works end to end** ✅ matching score + skill synonyms, no-role search, PDF/Word export, job links, upload limits, CORS, tests + CI
- **Phase 2 — data engine** ✅ daily Telegram collector (no LLM), jobs database (SQLite/Postgres), freshness + repost merging, level-aware ranking, LinkedIn PDF import instead of scraping; Airflow DAG runs the ETL daily (edits / closed / deleted posts detected, data quality checks, alerts)
- **Phase 3 — product:** accounts, application tracker, RU/KZ/EN, Telegram bot
- **Phase 4–5 — validate & monetize:** pilots with universities/bootcamps, freemium + B2B licences
