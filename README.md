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

## API

| Method | Path | What it does |
|---|---|---|
| GET | `/api/jobs` | Paginated vacancies (`page`, `limit`, `category`, `level`, `format`) |
| POST | `/api/analyze` | Form: `cv_file`, `github_url`, `linkedin_url`, `preferred_salary`, `target_roles[]` → skills + top matches per role |
| POST | `/api/cv/generate` | Tailored CV (JSON + LaTeX) for one job |

## Roadmap

- **Phase 0 — cleanup** ✅ structure, secrets out of git, CV-only crash fixed, tailored CV uses real CV text
- **Phase 1 — MVP works end to end:** better matching score, PDF/DOCX output, config & CORS, tests + CI
- **Phase 2 — data engine:** daily fresh jobs in Postgres, legal data sources, LinkedIn PDF import instead of scraping
- **Phase 3 — product:** accounts, application tracker, RU/KZ/EN, Telegram bot
- **Phase 4–5 — validate & monetize:** pilots with universities/bootcamps, freemium + B2B licences
