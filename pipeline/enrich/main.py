from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from enrich.config import PipelineConfig
from enrich.pipeline import GroqEnrichmentPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Ollama/LLM enrichment pipeline for job vacancies")
    parser.add_argument("--input", required=True, help="Input CSV path, e.g. data/interim/unified_job_database.csv")
    parser.add_argument("--output", required=True, help="Output CSV path, e.g. data/interim/enriched_jobs_full_v1.csv")
    parser.add_argument("--mode", choices=["8b", "70b", "hybrid"], default="hybrid", help="Inference strategy")
    parser.add_argument("--batch-size", type=int, default=30, help="Rows per LLM batch")
    parser.add_argument("--min-description-length", type=int, default=200, help="Minimum description_clean length")
    parser.add_argument("--client", choices=["groq", "ollama"], default="ollama", help="LLM backend client")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Local Ollama HTTP API URL")
    parser.add_argument("--cheap-model", default="llama-3.1-8b-instant", help="Cheap model for mass extraction")
    parser.add_argument("--fallback-model", default="llama-3.3-70b-versatile", help="Fallback model for retries")
    parser.add_argument("--full-run", action="store_true", help="Process all eligible rows instead of sample=300")
    parser.add_argument("--sample-size", type=int, default=300, help="Default sample size before full run")
    parser.add_argument("--sample-telegram", type=int, default=200, help="Telegram rows in default sample")
    parser.add_argument("--sample-hh", type=int, default=70, help="HH rows in default sample")
    parser.add_argument("--sample-other", type=int, default=30, help="Kaspi/Kolesa rows in default sample")
    parser.add_argument("--random-seed", type=int, default=42, help="Random seed for reproducible sampling")
    return parser


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    config = PipelineConfig(
        input_path=Path(args.input),
        output_path=Path(args.output),
        mode=args.mode,
        batch_size=args.batch_size,
        min_description_length=args.min_description_length,
        client=args.client,
        ollama_url=args.ollama_url,
        cheap_model=args.cheap_model,
        fallback_model=args.fallback_model,
        sample_size=args.sample_size,
        sample_telegram=args.sample_telegram,
        sample_hh=args.sample_hh,
        sample_other=args.sample_other,
        full_run=args.full_run,
        random_seed=args.random_seed,
    )

    pipeline = GroqEnrichmentPipeline(config=config)
    summary = pipeline.run()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Enriched CSV: {config.output_path}")
    print(f"Audit log: {config.audit_log_path}")
    print(f"Failed rows: {config.failed_rows_path}")
    print(f"Quality report: {config.quality_report_path}")


if __name__ == "__main__":
    main()
