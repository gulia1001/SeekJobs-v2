"""Run the job-data pipeline end to end.

    raw exports (data/raw) -> integrate -> [LLM enrich] -> prepare -> repair salary
                                                                   -> data/final/analysis_ready_jobs_salary_fixed_v3.csv

The backend reads that last file. LLM enrichment costs API money, so it only
runs with --with-llm; otherwise the existing data/interim/enriched_jobs_full_v1.csv is reused.

Usage (from the pipeline/ folder):
    python run_pipeline.py                 # clean + prepare, reuse existing enrichment
    python run_pipeline.py --with-llm      # also re-run LLM enrichment (needs GROQ_API_KEY)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
INTERIM = PIPELINE_DIR / "data" / "interim"


def run(step: str, args: list[str]) -> None:
    print(f"\n=== {step} ===", flush=True)
    subprocess.run([sys.executable, *args], cwd=PIPELINE_DIR, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--with-llm", action="store_true", help="Re-run LLM enrichment (costs API money)")
    parser.add_argument("--llm-client", choices=["groq", "ollama"], default="groq")
    args = parser.parse_args()

    run("1. Integrate sources", ["transform/integrate_sources.py", "--mode", "clean"])

    enriched = INTERIM / "enriched_jobs_full_v1.csv"
    if args.with_llm:
        run("2. LLM enrichment", [
            "-m", "enrich.main",
            "--input", str(INTERIM / "unified_job_database.csv"),
            "--output", str(enriched),
            "--client", args.llm_client,
            "--full-run",
        ])
    elif not enriched.exists():
        sys.exit(f"Missing {enriched}. Run with --with-llm once to create it.")
    else:
        print("\n=== 2. LLM enrichment: skipped (reusing existing file) ===")

    run("3. Prepare analysis-ready dataset", ["transform/prepare_analysis_ready.py"])
    run("4. Repair salary layer", ["transform/repair_salary.py"])
    print("\nDone. Backend input: data/final/analysis_ready_jobs_salary_fixed_v3.csv")


if __name__ == "__main__":
    main()
