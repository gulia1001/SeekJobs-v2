# SeekJobs

AI career assistant for IT job seekers in Kazakhstan. Upload a CV (and optionally
GitHub / LinkedIn), see matching local vacancies with your skill gaps and market
salary, and get a CV tailored to a specific job.

Powered by a cleaned dataset of ~15k Kazakhstan IT vacancies (hh.kz, Kolesa,
Kaspi, Telegram channels).

## Structure

```text
SeekJobs-v2/
├── frontend/           Next.js 14 — landing page + app
├── backend/            FastAPI — profile analysis, job matching, CV generation
├── pipeline/           job data: scrape → clean → LLM enrich → final dataset (see pipeline/README.md)
├── docker-compose.yml  runs backend + frontend
└── .env.example        API keys and settings
```

## Quick start

1. **Get the job data.** It is not in git. Put the files in `pipeline/data/`
   (`final/analysis_ready_jobs_salary_fixed_v3.csv` is the one the backend needs),
   or rebuild them with `pipeline/run_pipeline.py`. Without data the app runs but shows no jobs.
2. **Set keys:** `cp .env.example .env` and fill in `GROQ_API_KEY` (others optional).
3. **Run** — either with Docker:

   ```bash
   docker compose up --build
   ```

   or by hand (two terminals):

   ```bash
   cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8001
   cd frontend && npm install && npm run dev
   ```

Open http://localhost:3001. API health check: http://localhost:8001/api/health

## Tests

```bash
cd backend && pip install -r requirements.txt -r requirements-dev.txt && pytest -q
```

Tests use a small fake dataset in `backend/tests/fixtures/` (no real data or API keys
needed). GitHub Actions (`.github/workflows/ci.yml`) runs backend tests, the frontend
production build and pipeline checks on every push and pull request.

## How matching works

- Skill names are normalized, so `Postgres` = `PostgreSQL`, `React.js` = `React`,
  `1С` = `1C`, `CI/CD` = `CI CD` (`backend/services/skills.py`).
- Score = share of the **job's** skills you have (hard skills + tech stack; soft skills
  are ignored). Having many other skills never lowers your score.
- Ranking slightly prefers jobs with more evidence (5 of 5 skills beats 1 of 1).
- Missing skills are listed most-in-demand first.
- No role selected → searches all categories ("Best matches for you").

## API

| Method | Path | What it does |
|---|---|---|
| GET | `/api/jobs` | Paginated vacancies (`page`, `limit`, `category`, `level`, `format`) |
| POST | `/api/analyze` | Form: `cv_file` (PDF/DOCX/TXT, ≤5 MB), `github_url`, `linkedin_url`, `preferred_salary`, `target_roles[]` (optional) → skills + top matches per role |
| POST | `/api/cv/generate` | Tailored CV (JSON + LaTeX) for one job — uses only facts from the CV/profile |
| POST | `/api/cv/export` | `{cv, format: "pdf" \| "docx"}` → downloadable file (real text, Cyrillic supported) |

## Roadmap

- **Phase 0 — cleanup** ✅ structure, secrets out of git, CV-only crash fixed, tailored CV uses real CV text
- **Phase 1 — MVP works end to end** ✅ new matching score + skill synonyms, no-role search, PDF/Word export, job links, upload limits, CORS config, tests + CI
- **Phase 2 — data engine:** daily fresh jobs in Postgres, legal data sources, LinkedIn PDF import instead of scraping
- **Phase 3 — product:** accounts, application tracker, RU/KZ/EN, Telegram bot
- **Phase 4–5 — validate & monetize:** pilots with universities/bootcamps, freemium + B2B licences
