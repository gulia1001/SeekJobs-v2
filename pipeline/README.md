# Pipeline — Kazakhstan IT job data

Collects IT vacancies (hh.kz, Kolesa, Kaspi, Telegram channels), cleans and
normalizes them, enriches them with an LLM, and produces the dataset the backend uses.

## Layout

```text
pipeline/
├── scrapers/        source collection notebooks (to be turned into scripts)
├── transform/       integrate_sources.py → prepare_analysis_ready.py → repair_salary.py
├── enrich/          LLM enrichment (Groq or local Ollama)
├── dashboard/       internal Streamlit market-analytics dashboard
├── docs/            dataset docs and quality reports
├── run_pipeline.py  runs all steps in order
└── data/            NOT in git — see below
    ├── raw/         raw source exports (hh_*.csv, kolesa_*.csv, kaspi_*.csv, Telegram -100…_*.csv)
    ├── interim/     unified_job_database.csv, enriched_jobs_full_v1.csv
    ├── final/       analysis_ready_jobs_salary_fixed_v3.csv  ← backend reads this
    └── reports/
```

Data files are kept out of git (size + scraped content). Store them in cloud
storage and copy them into `data/` locally.

## Run

Requires **Python 3.11+** (`enrich/` uses `enum.StrEnum`).

```bash
cd pipeline
pip install -r requirements.txt

python run_pipeline.py              # clean + prepare (reuses existing LLM enrichment)
python run_pipeline.py --with-llm   # also re-run LLM enrichment — costs API money, needs GROQ_API_KEY

streamlit run dashboard/main.py     # internal analytics dashboard
```

Steps can also be run one by one:

| Step | Command | Output |
|---|---|---|
| 1. Integrate sources | `python transform/integrate_sources.py` | `data/interim/unified_job_database.csv` |
| 2. LLM enrichment | `python -m enrich.main --input data/interim/unified_job_database.csv --output data/interim/enriched_jobs_full_v1.csv --client groq --full-run` | `data/interim/enriched_jobs_full_v1.csv` |
| 3. Prepare | `python transform/prepare_analysis_ready.py` | `data/final/analysis_ready_jobs.csv` + marts |
| 4. Repair salaries | `python transform/repair_salary.py` | `data/final/analysis_ready_jobs_salary_fixed_v3.csv` |

LLM progress is checkpointed in `.llm_checkpoints/` (not in git), so an
interrupted enrichment run can resume.

## Docs

- `docs/README_ANALYSIS_READY_DATASET_RU_EN.md` — dataset columns and rules
- `docs/README_LLM_INTEGRATION.md` — LLM enrichment design
- `docs/reports/` — data quality and audit reports
