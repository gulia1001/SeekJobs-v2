from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError
from tqdm import tqdm

from enrich.client_factory import LLMClientError, create_extraction_client
from enrich.config import PipelineConfig, STRUCTURED_SOURCES
from enrich.schemas import VacancyExtraction, VacancyLLMInput
from enrich.telegram_prefill import (
    PREFILL_FIELDS,
    compact_parser_hints,
    reconcile_prefill_and_llm,
    telegram_prefill_extract,
    telegram_prefill_quality,
    validate_final_telegram_record,
)
from enrich.token_estimator import estimate_run_costs
from enrich.validation import compute_extraction_confidence, merge_row_with_extraction, sanitize_extraction


TRACKED_COVERAGE_FIELDS = [
    "title_normalized",
    "company",
    "city",
    "category",
    "level",
    "employment",
    "work_format",
    "experience_min",
    "experience_max",
    "requirements_clean",
    "responsibilities_clean",
    "hard_skills",
    "soft_skills",
    "tech_stack",
    "salary_raw",
    "salary_from",
    "salary_to",
    "currency",
    "salary_period",
]

LIST_EXPORT_COLUMNS = ["hard_skills", "soft_skills", "tech_stack"]
JSON_EXPORT_COLUMNS = [
    "parser_hints",
    "parser_quality",
    "final_field_sources",
    "final_field_confidence",
    "review_flags",
    "conflict_flags",
    "validation_fixes",
]
OBJECT_RUNTIME_COLUMNS = [
    "title_normalized",
    "company",
    "city",
    "category",
    "level",
    "employment",
    "work_format",
    "requirements_clean",
    "responsibilities_clean",
    "hard_skills",
    "soft_skills",
    "tech_stack",
    "salary_raw",
    "salary_period",
    "currency",
    "extraction_method",
    "parser_hints",
    "parser_quality",
    "final_field_sources",
    "final_field_confidence",
    "review_flags",
    "conflict_flags",
    "validation_fixes",
    "llm_merge_status",
    "llm_model",
]


def _is_telegram_source(source: str) -> bool:
    return source not in STRUCTURED_SOURCES


def _description_length(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.len()


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def _preview_text(text: Any, limit: int = 280) -> str:
    value = str(text or "")
    return value[:limit]


def _normalize_comparable(value: Any) -> Any:
    if isinstance(value, pd.Series):
        return value.tolist()
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray, dict)):
        try:
            return value.tolist()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, tuple):
        return list(value)
    return value


def _values_differ(old_value: Any, new_value: Any) -> bool:
    old_value = _normalize_comparable(old_value)
    new_value = _normalize_comparable(new_value)

    if isinstance(old_value, dict) or isinstance(new_value, dict):
        old_dict = old_value if isinstance(old_value, dict) else {}
        new_dict = new_value if isinstance(new_value, dict) else {}
        return old_dict != new_dict

    if isinstance(old_value, list) or isinstance(new_value, list):
        old_list = old_value if isinstance(old_value, list) else ([] if pd.isna(old_value) else [old_value])
        new_list = new_value if isinstance(new_value, list) else ([] if pd.isna(new_value) else [new_value])
        return old_list != new_list

    if pd.isna(old_value) and pd.isna(new_value):
        return False
    if pd.isna(old_value) != pd.isna(new_value):
        return True
    return old_value != new_value


def _has_trackable_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return len(value) > 0
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "unknown", "none", "null", "[]"}
    try:
        return bool(pd.notna(value))
    except Exception:  # noqa: BLE001
        return value is not None


def _sample_n(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if n <= 0 or df.empty:
        return df.iloc[0:0].copy()
    if len(df) <= n:
        return df.copy()
    return df.sample(n=n, random_state=seed)


class GroqEnrichmentPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.client = None
        self.failed_rows: list[dict[str, Any]] = []
        self.current_batch_source_rows: dict[str, pd.Series] = {}
        self.current_batch_prefill: dict[str, dict[str, Any]] = {}
        self.current_batch_parser_quality: dict[str, dict[str, Any]] = {}
        self.metrics: dict[str, Any] = {
            "total_rows": 0,
            "processed_rows": 0,
            "merged_rows": 0,
            "review_rows": 0,
            "failed_rows": 0,
            "llm_called_rows": 0,
            "parser_only_rows": 0,
            "skipped_low_confidence_rows": 0,
            "no_missing_target_rows": 0,
            "review_flags_count": 0,
            "validation_fixes_count": 0,
            "model_usage": defaultdict(int),
            "per_source_processed": defaultdict(int),
            "per_source_merged": defaultdict(int),
            "per_source_failed": defaultdict(int),
            "parser_prefill_hits": defaultdict(int),
            "llm_field_hits": defaultdict(int),
            "final_field_hits": defaultdict(int),
            "conflict_count": defaultdict(int),
            "sample_conflict_rows": [],
        }

    def _get_client(self):
        if self.client is None:
            self.client = create_extraction_client(self.config)
        return self.client

    def load_dataset(self) -> pd.DataFrame:
        df = pd.read_csv(self.config.input_path)
        df = df.set_index("id", drop=False)
        self.metrics["total_rows"] = int(len(df))
        for column in OBJECT_RUNTIME_COLUMNS:
            if column in df.columns:
                df[column] = df[column].astype("object")
            else:
                df[column] = None
        if "llm_review_flag" not in df.columns:
            df["llm_review_flag"] = False
        if "llm_merge_status" not in df.columns:
            df["llm_merge_status"] = None
        if "llm_model" not in df.columns:
            df["llm_model"] = None
        if "llm_called" not in df.columns:
            df["llm_called"] = False
        if "parser_only" not in df.columns:
            df["parser_only"] = False
        df["llm_review_flag"] = df["llm_review_flag"].astype(bool)
        df["llm_called"] = df["llm_called"].astype(bool)
        df["parser_only"] = df["parser_only"].astype(bool)
        return df

    def _effective_batch_size(self) -> int:
        batch_size = max(1, self.config.batch_size)
        if self.config.mode == "8b":
            return min(batch_size, self.config.cheap_model_safe_batch_size)
        if self.config.mode == "hybrid":
            return min(batch_size, self.config.hybrid_safe_batch_size)
        return batch_size

    def _compute_sample_targets(
        self,
        telegram_count: int,
        hh_count: int,
        other_count: int,
    ) -> tuple[int, int, int]:
        desired = {
            "telegram": min(telegram_count, self.config.sample_telegram),
            "hh": min(hh_count, self.config.sample_hh),
            "other": min(other_count, self.config.sample_other),
        }
        total_desired = sum(desired.values())
        if total_desired <= self.config.sample_size:
            return desired["telegram"], desired["hh"], desired["other"]

        scaled = {}
        remainders = []
        allocated = 0
        for key, value in desired.items():
            scaled_value = (value / total_desired) * self.config.sample_size if total_desired else 0
            floored = int(scaled_value)
            scaled[key] = floored
            allocated += floored
            remainders.append((scaled_value - floored, key))

        remaining = self.config.sample_size - allocated
        for _, key in sorted(remainders, reverse=True):
            if remaining <= 0:
                break
            if scaled[key] < desired[key]:
                scaled[key] += 1
                remaining -= 1

        return scaled["telegram"], scaled["hh"], scaled["other"]

    def freeze_baseline(self, df: pd.DataFrame) -> None:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        if not self.config.baseline_path.exists():
            df.reset_index(drop=True).to_csv(self.config.baseline_path, index=False, encoding="utf-8")

    def select_candidates(self, df: pd.DataFrame) -> pd.DataFrame:
        candidates = df.copy()
        candidates["description_clean"] = candidates["description_clean"].fillna("")
        candidates["description_length"] = _description_length(candidates["description_clean"])
        candidates = candidates[
            (candidates["is_duplicate"] == False)
            & (candidates["description_clean"].str.strip() != "")
            & (candidates["description_length"] > self.config.min_description_length)
        ].copy()

        candidates["source_priority"] = candidates["source"].apply(
            lambda value: 0 if _is_telegram_source(value) else (1 if value == "hh_kz" else 2)
        )
        candidates = candidates.sort_values(
            by=["source_priority", "description_length", "source"],
            ascending=[True, False, True],
        )

        if self.config.full_run:
            return candidates

        telegram = candidates[candidates["source"].apply(_is_telegram_source)]
        hh = candidates[candidates["source"] == "hh_kz"]
        other = candidates[candidates["source"].isin(["kaspi_jobs", "kolesa_jobs"])]

        tg_target, hh_target, other_target = self._compute_sample_targets(
            telegram_count=len(telegram),
            hh_count=len(hh),
            other_count=len(other),
        )

        sampled = [
            _sample_n(telegram, tg_target, self.config.random_seed),
            _sample_n(hh, hh_target, self.config.random_seed),
            _sample_n(other, other_target, self.config.random_seed),
        ]
        sample_df = pd.concat(sampled, axis=0)

        if len(sample_df) < self.config.sample_size:
            remainder = candidates.loc[~candidates.index.isin(sample_df.index)]
            needed = self.config.sample_size - len(sample_df)
            if needed > 0 and len(remainder) > 0:
                sample_df = pd.concat(
                    [
                        sample_df,
                        remainder.sample(n=min(len(remainder), needed), random_state=self.config.random_seed),
                    ],
                    axis=0,
                )

        sample_df = sample_df.sort_values(
            by=["source_priority", "description_length", "source"],
            ascending=[True, False, True],
        )
        return sample_df

    def estimate_tokens(self, selected_df: pd.DataFrame) -> dict[str, Any]:
        inputs = []
        for _, row in selected_df.iterrows():
            parser_hints = None
            if _is_telegram_source(str(row["source"])):
                prefill = telegram_prefill_extract(str(row.get("description_clean") or ""))
                parser_quality = telegram_prefill_quality(prefill, str(row.get("description_clean") or ""))
                parser_hints = compact_parser_hints(parser_quality) or None
            inputs.append(
                VacancyLLMInput(
                    id=row["id"],
                    source=row["source"],
                    title=row.get("title"),
                    description_clean=row["description_clean"],
                    parser_hints=parser_hints,
                )
            )
        return estimate_run_costs(inputs, self.config, batch_size=self._effective_batch_size())

    def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=_json_default) + "\n")

    def _is_successful_checkpoint(self, entry: dict[str, Any]) -> bool:
        merge_status = str(entry.get("meta", {}).get("merge_status") or "").lower()
        return merge_status in {"auto_merged", "merged_with_review", "no_missing_targets"}

    def _load_checkpoint_entries(self) -> dict[str, dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        if not self.config.checkpoint_rows_path.exists():
            return entries
        with self.config.checkpoint_rows_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                existing = entries.get(payload["id"])
                if existing is not None:
                    if self._is_successful_checkpoint(existing) and not self._is_successful_checkpoint(payload):
                        continue
                entries[payload["id"]] = payload
        return entries

    def _apply_checkpoint(self, df: pd.DataFrame, checkpoint_entries: dict[str, dict[str, Any]]) -> set[str]:
        completed_ids = set()
        for row_id, entry in checkpoint_entries.items():
            if row_id not in df.index:
                continue
            for key, value in entry.get("patch", {}).items():
                df.at[row_id, key] = value
            if self._is_successful_checkpoint(entry):
                completed_ids.add(row_id)
        return completed_ids

    def _save_state(self, completed_ids: set[str]) -> None:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "completed_ids": sorted(completed_ids),
        }
        self.config.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.config.checkpoint_state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _progress_bar(self, batches: list[pd.DataFrame]):
        return tqdm(
            batches,
            desc="LLM enrichment",
            unit="batch",
            mininterval=2.0,
            dynamic_ncols=False,
            ncols=86,
            leave=True,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}]",
        )

    def _log_audit(
        self,
        batch_ids: list[str],
        model_name: str,
        request_kind: str,
        raw_response: str | None,
        error_message: str | None = None,
    ) -> None:
        self._append_jsonl(
            self.config.audit_log_path,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": model_name,
                "request_kind": request_kind,
                "ids": batch_ids,
                "error": error_message,
                "raw_response": raw_response,
            },
        )

    def _log_row_event(
        self,
        row_id: str,
        stage: str,
        row: pd.Series | None = None,
        *,
        error_type: str | None = None,
        error_message: str | None = None,
        parser_result: dict[str, Any] | None = None,
        llm_result: dict[str, Any] | None = None,
        final_result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._append_jsonl(
            self.config.audit_log_path,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "row_id": row_id,
                "stage": stage,
                "error_type": error_type,
                "error_message": error_message,
                "raw_text_preview": _preview_text(row.get("description_clean") if row is not None else ""),
                "parser_result": parser_result,
                "llm_result": llm_result,
                "final_result": final_result,
                "metadata": metadata or {},
            },
        )

    def _prepare_batch_prefill(self, batch_df: pd.DataFrame) -> None:
        self.current_batch_prefill = {}
        self.current_batch_parser_quality = {}
        for _, row in batch_df.iterrows():
            row_id = row["id"]
            if _is_telegram_source(str(row["source"])):
                text = str(row.get("description_clean") or "")
                prefill = telegram_prefill_extract(text)
                parser_quality = telegram_prefill_quality(prefill, text)
                self.current_batch_prefill[row_id] = prefill
                self.current_batch_parser_quality[row_id] = parser_quality
                for field in PREFILL_FIELDS:
                    if parser_quality.get(field, {}).get("confidence") != "missing":
                        self.metrics["parser_prefill_hits"][field] += 1
                self._log_row_event(
                    row_id=row_id,
                    stage="parser_prefill",
                    row=row,
                    parser_result=prefill,
                    metadata={"parser_quality": parser_quality},
                )
            else:
                self.current_batch_prefill[row_id] = {}
                self.current_batch_parser_quality[row_id] = {}

    def _prepare_candidate_result(
        self,
        row_id: str,
        extraction: VacancyExtraction,
        *,
        record_metrics: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        row = self.current_batch_source_rows[row_id]
        context_text = str(row.get("description_clean") or "")
        sanitized = sanitize_extraction(extraction, context_text=context_text)
        if record_metrics:
            for field, value in sanitized.items():
                if field in TRACKED_COVERAGE_FIELDS and _has_trackable_value(value):
                    self.metrics["llm_field_hits"][field] += 1

        parser_quality = self.current_batch_parser_quality.get(row_id, {})
        final_candidate = dict(sanitized)
        reconcile_meta = {}
        validation_fixes: list[str] = []

        if _is_telegram_source(str(row.get("source") or "")):
            final_candidate = reconcile_prefill_and_llm(parser_quality, sanitized)
            final_candidate["english_mention"] = (
                final_candidate.get("english_mention")
                if final_candidate.get("english_mention") is not None
                else row.get("english_mention")
            )
            final_candidate = validate_final_telegram_record(final_candidate)
            validation_fixes = final_candidate.get("validation_fixes", []) or []
            reconcile_meta = {
                "final_field_sources": final_candidate.get("final_field_sources", {}),
                "final_field_confidence": final_candidate.get("final_field_confidence", {}),
                "review_flags": final_candidate.get("review_flags", []),
                "conflict_flags": final_candidate.get("conflict_flags", []),
                "validation_fixes": validation_fixes,
            }
            if record_metrics:
                for field in final_candidate.get("conflict_flags", []):
                    self.metrics["conflict_count"][field] += 1
                self.metrics["review_flags_count"] += len(final_candidate.get("review_flags", []))
                self.metrics["validation_fixes_count"] += len(validation_fixes)
                if final_candidate.get("conflict_flags"):
                    if len(self.metrics["sample_conflict_rows"]) < 10:
                        self.metrics["sample_conflict_rows"].append(
                            {
                                "id": row_id,
                                "source": row.get("source"),
                                "conflict_flags": final_candidate.get("conflict_flags", []),
                                "review_flags": final_candidate.get("review_flags", []),
                            }
                        )

        if record_metrics:
            for field in TRACKED_COVERAGE_FIELDS:
                value = final_candidate.get(field)
                if _has_trackable_value(value):
                    self.metrics["final_field_hits"][field] += 1

        return final_candidate, {
            "parser_result": self.current_batch_prefill.get(row_id, {}),
            "parser_quality": parser_quality,
            "llm_result": sanitized,
            "reconcile_meta": reconcile_meta,
        }

    def _retry_rows_with_fallback(
        self,
        rows: list[VacancyLLMInput],
        successes: dict[str, VacancyExtraction],
        model_used: dict[str, str],
    ) -> tuple[dict[str, VacancyExtraction], dict[str, str], list[dict[str, Any]]]:
        failures = []
        for row in rows:
            try:
                extraction, raw_response = self._get_client().extract_single(row, model=self.config.fallback_model)
                self._log_audit(
                    batch_ids=[row.id],
                    model_name=self.config.fallback_model,
                    request_kind="single_retry",
                    raw_response=raw_response,
                )
                successes[row.id] = extraction
                model_used[row.id] = self.config.fallback_model
                self.metrics["model_usage"][self.config.fallback_model] += 1
            except Exception as exc:  # noqa: BLE001
                self._log_audit(
                    batch_ids=[row.id],
                    model_name=self.config.fallback_model,
                    request_kind="single_retry",
                    raw_response=None,
                    error_message=str(exc),
                )
                failures.append(
                    {
                        "id": row.id,
                        "source": row.source,
                        "title": row.title,
                        "reason": str(exc),
                        "model": self.config.fallback_model,
                    }
                )
        return successes, model_used, failures

    def _retry_rows_with_primary_model(
        self,
        rows: list[VacancyLLMInput],
        model_name: str,
        successes: dict[str, VacancyExtraction],
        model_used: dict[str, str],
    ) -> tuple[dict[str, VacancyExtraction], dict[str, str], list[dict[str, Any]]]:
        failures = []
        for row in rows:
            try:
                extraction, raw_response = self._get_client().extract_single(row, model=model_name)
                self._log_audit(
                    batch_ids=[row.id],
                    model_name=model_name,
                    request_kind="single_primary_retry",
                    raw_response=raw_response,
                )
                successes[row.id] = extraction
                model_used[row.id] = model_name
                self.metrics["model_usage"][model_name] += 1
            except Exception as exc:  # noqa: BLE001
                self._log_audit(
                    batch_ids=[row.id],
                    model_name=model_name,
                    request_kind="single_primary_retry",
                    raw_response=None,
                    error_message=str(exc),
                )
                failures.append(
                    {
                        "id": row.id,
                        "source": row.source,
                        "title": row.title,
                        "reason": str(exc),
                        "model": model_name,
                    }
                )
        return successes, model_used, failures

    def _extract_batch_with_strategy(
        self,
        rows: list[VacancyLLMInput],
    ) -> tuple[dict[str, VacancyExtraction], dict[str, str], list[dict[str, Any]]]:
        successes: dict[str, VacancyExtraction] = {}
        model_used: dict[str, str] = {}
        failures: list[dict[str, Any]] = []

        primary_model = self.config.cheap_model if self.config.mode in {"8b", "hybrid"} else self.config.fallback_model
        expected_ids = {row.id for row in rows}

        try:
            batch_result = self._get_client().extract_batch(rows, model=primary_model)
            self._log_audit(
                batch_ids=[row.id for row in rows],
                model_name=primary_model,
                request_kind="batch",
                raw_response=batch_result.raw_response,
            )
            self.metrics["model_usage"][primary_model] += len(rows)
            for item in batch_result.items:
                if item.id in expected_ids:
                    successes[item.id] = item
                    model_used[item.id] = primary_model
        except (ValidationError, LLMClientError, Exception) as exc:  # noqa: BLE001
            self._log_audit(
                batch_ids=[row.id for row in rows],
                model_name=primary_model,
                request_kind="batch",
                raw_response=None,
                error_message=str(exc),
            )

        missing_rows = [row for row in rows if row.id not in successes]

        if self.config.mode == "8b" and missing_rows:
            successes, model_used, primary_retry_failures = self._retry_rows_with_primary_model(
                missing_rows,
                model_name=primary_model,
                successes=successes,
                model_used=model_used,
            )
            failures.extend(primary_retry_failures)
            failed_ids = {item["id"] for item in primary_retry_failures}
            missing_rows = [row for row in missing_rows if row.id in failed_ids]

        low_confidence_rows = []
        if self.config.mode == "hybrid":
            for row in rows:
                item = successes.get(row.id)
                if not item:
                    continue
                source_row = self.current_batch_source_rows.get(row.id)
                if source_row is None:
                    continue
                candidate_result, _ = self._prepare_candidate_result(row.id, item)
                computed_confidence, _ = compute_extraction_confidence(source_row, candidate_result, self.config)
                if computed_confidence < self.config.low_confidence_threshold:
                    low_confidence_rows.append(row)

        retry_rows = []
        if self.config.mode == "hybrid":
            retry_map = {row.id: row for row in missing_rows + low_confidence_rows}
            retry_rows = list(retry_map.values())
        elif self.config.mode == "70b" and missing_rows:
            retry_rows = missing_rows

        if retry_rows:
            fallback_successes, model_used, fallback_failures = self._retry_rows_with_fallback(
                retry_rows,
                successes=successes,
                model_used=model_used,
            )
            successes = fallback_successes
            failures.extend(fallback_failures)
            failed_ids = {item["id"] for item in fallback_failures}
            missing_rows = [row for row in missing_rows if row.id in failed_ids]

        if self.config.mode == "8b":
            for row in missing_rows:
                failures.append(
                    {
                        "id": row.id,
                        "source": row.source,
                        "title": row.title,
                        "reason": "Row missing from 8B batch response.",
                        "model": primary_model,
                    }
                )

        return successes, model_used, failures

    def _build_inputs(self, batch_df: pd.DataFrame) -> list[VacancyLLMInput]:
        return [
            VacancyLLMInput(
                id=row["id"],
                source=row["source"],
                title=row.get("title"),
                description_clean=row["description_clean"],
                parser_hints=compact_parser_hints(self.current_batch_parser_quality.get(row["id"], {})) or None,
            )
            for _, row in batch_df.iterrows()
        ]

    def _record_failed_rows(self, failures: list[dict[str, Any]]) -> None:
        self.failed_rows.extend(failures)
        self.metrics["failed_rows"] += len(failures)
        for item in failures:
            self.metrics["per_source_failed"][item["source"]] += 1

    def _checkpoint_row(self, row_id: str, patch: dict[str, Any], meta: dict[str, Any]) -> None:
        entry = {
            "id": row_id,
            "patch": patch,
            "meta": meta,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._append_jsonl(self.config.checkpoint_rows_path, entry)

    def _prepare_export_df(self, df: pd.DataFrame) -> pd.DataFrame:
        export_df = df.reset_index(drop=True).copy()
        for column in LIST_EXPORT_COLUMNS:
            export_df[column] = export_df[column].apply(
                lambda value: json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value
            )
        for column in JSON_EXPORT_COLUMNS:
            export_df[column] = export_df[column].apply(
                lambda value: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
            )
        return export_df

    def _coverage_snapshot(self, df: pd.DataFrame) -> dict[str, float]:
        snapshot = {}
        for column in TRACKED_COVERAGE_FIELDS:
            series = df[column]
            if series.dtype == "object":
                filled = ~series.fillna("").astype(str).str.strip().str.lower().isin(["", "unknown", "nan", "none", "null", "[]"])
            else:
                filled = series.notna()
            snapshot[column] = round(float(filled.mean() * 100), 2)
        return snapshot

    def _write_quality_report(
        self,
        baseline_df: pd.DataFrame,
        final_df: pd.DataFrame,
        selected_df: pd.DataFrame,
        token_estimate: dict[str, Any],
    ) -> None:
        telegram_selected = selected_df[selected_df["source"].apply(_is_telegram_source)] if not selected_df.empty else selected_df
        telegram_selected_count = max(1, int(len(telegram_selected))) if len(telegram_selected) else 1
        processed_count = max(1, int(self.metrics["processed_rows"])) if self.metrics["processed_rows"] else 1
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_path": str(self.config.input_path),
            "output_path": str(self.config.output_path),
            "mode": self.config.mode,
            "batch_size": self.config.batch_size,
            "effective_batch_size": self._effective_batch_size(),
            "full_run": self.config.full_run,
            "low_confidence_threshold": self.config.low_confidence_threshold,
            "review_confidence_threshold": self.config.review_confidence_threshold,
            "total_rows": int(self.metrics["total_rows"]),
            "selected_rows": int(len(selected_df)),
            "processed_rows": int(self.metrics["processed_rows"]),
            "merged_rows": int(self.metrics["merged_rows"]),
            "review_rows": int(self.metrics["review_rows"]),
            "failed_rows": int(self.metrics["failed_rows"]),
            "llm_called_rows": int(self.metrics["llm_called_rows"]),
            "parser_only_rows": int(self.metrics["parser_only_rows"]),
            "skipped_low_confidence_rows": int(self.metrics["skipped_low_confidence_rows"]),
            "no_missing_target_rows": int(self.metrics["no_missing_target_rows"]),
            "review_flags_count": int(self.metrics["review_flags_count"]),
            "validation_fixes_count": int(self.metrics["validation_fixes_count"]),
            "model_usage": dict(self.metrics["model_usage"]),
            "per_source_processed": dict(self.metrics["per_source_processed"]),
            "per_source_merged": dict(self.metrics["per_source_merged"]),
            "per_source_failed": dict(self.metrics["per_source_failed"]),
            "parser_prefill_coverage_pct": {
                field: round((count / telegram_selected_count) * 100, 2)
                for field, count in sorted(self.metrics["parser_prefill_hits"].items())
            },
            "llm_coverage_pct": {
                field: round((count / processed_count) * 100, 2)
                for field, count in sorted(self.metrics["llm_field_hits"].items())
            },
            "final_coverage_pct": {
                field: round((count / processed_count) * 100, 2)
                for field, count in sorted(self.metrics["final_field_hits"].items())
            },
            "conflict_count": dict(sorted(self.metrics["conflict_count"].items())),
            "coverage_before_pct": self._coverage_snapshot(baseline_df),
            "coverage_after_pct": self._coverage_snapshot(final_df),
            "sample_failed_rows": self.failed_rows[:10],
            "sample_conflict_rows": self.metrics["sample_conflict_rows"],
            "critical_failure": bool(
                self.metrics["processed_rows"] == 0
                or (len(selected_df) > 0 and (self.metrics["failed_rows"] / len(selected_df)) > 0.30)
            ),
            "token_estimate": token_estimate,
        }
        self.config.quality_report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def run(self) -> dict[str, Any]:
        df = self.load_dataset()
        baseline_df = df.copy(deep=True)
        self.freeze_baseline(df)
        self.current_batch_source_rows: dict[str, pd.Series] = {}

        checkpoint_entries = self._load_checkpoint_entries()
        completed_ids = self._apply_checkpoint(df, checkpoint_entries)

        selected_df = self.select_candidates(df)
        selected_df = selected_df.loc[~selected_df.index.isin(completed_ids)].copy()

        token_estimate = self.estimate_tokens(selected_df)

        if selected_df.empty:
            export_df = self._prepare_export_df(df)
            export_df.to_csv(self.config.output_path, index=False, encoding="utf-8")
            self._write_quality_report(baseline_df, df, selected_df, token_estimate)
            return {
                "selected_rows": 0,
                "message": "No rows left to process.",
                "token_estimate": token_estimate,
            }

        batch_size = self._effective_batch_size()
        batches = [selected_df.iloc[index : index + batch_size] for index in range(0, len(selected_df), batch_size)]

        for batch_df in self._progress_bar(batches):
            self.current_batch_source_rows = {row["id"]: row for _, row in batch_df.iterrows()}
            self._prepare_batch_prefill(batch_df)
            batch_inputs = self._build_inputs(batch_df)
            self.metrics["llm_called_rows"] += len(batch_inputs)
            successes, model_used_by_id, failures = self._extract_batch_with_strategy(batch_inputs)
            self._record_failed_rows(failures)

            for input_row in batch_inputs:
                current_row = df.loc[input_row.id]
                extraction = successes.get(input_row.id)
                if extraction is None:
                    self._log_row_event(
                        row_id=input_row.id,
                        stage="llm_error",
                        row=current_row,
                        error_type="llm_missing_result",
                        error_message="No extraction result returned for row.",
                        parser_result=self.current_batch_prefill.get(input_row.id, {}),
                        metadata={"parser_quality": self.current_batch_parser_quality.get(input_row.id, {})},
                    )
                    self._checkpoint_row(
                        row_id=input_row.id,
                        patch={},
                        meta={"merge_status": "failed", "merged_fields": [], "model": None},
                    )
                    continue

                candidate_result, candidate_meta = self._prepare_candidate_result(
                    input_row.id,
                    extraction,
                    record_metrics=True,
                )
                updated_row, merge_meta = merge_row_with_extraction(current_row, candidate_result, self.config)
                updated_row["llm_model"] = model_used_by_id.get(input_row.id)
                updated_row["llm_called"] = True
                updated_row["parser_only"] = False
                updated_row["parser_hints"] = self.current_batch_prefill.get(input_row.id, {})
                updated_row["parser_quality"] = self.current_batch_parser_quality.get(input_row.id, {})
                updated_row["final_field_sources"] = candidate_meta.get("reconcile_meta", {}).get("final_field_sources")
                updated_row["final_field_confidence"] = candidate_meta.get("reconcile_meta", {}).get("final_field_confidence")
                updated_row["review_flags"] = candidate_meta.get("reconcile_meta", {}).get("review_flags", [])
                updated_row["conflict_flags"] = candidate_meta.get("reconcile_meta", {}).get("conflict_flags", [])
                updated_row["validation_fixes"] = candidate_meta.get("reconcile_meta", {}).get("validation_fixes", [])

                patch = {}
                for column, new_value in updated_row.items():
                    old_value = current_row.get(column)
                    if _values_differ(old_value, new_value):
                        patch[column] = new_value

                for column, value in patch.items():
                    df.at[input_row.id, column] = value

                merge_status = merge_meta["merge_status"]
                self.metrics["processed_rows"] += 1
                self.metrics["per_source_processed"][input_row.source] += 1
                if merge_status in {"auto_merged", "merged_with_review"}:
                    self.metrics["merged_rows"] += 1
                    self.metrics["per_source_merged"][input_row.source] += 1
                elif merge_status == "skipped_low_confidence":
                    self.metrics["skipped_low_confidence_rows"] += 1
                elif merge_status == "no_missing_targets":
                    self.metrics["no_missing_target_rows"] += 1
                if merge_meta.get("review_flag"):
                    self.metrics["review_rows"] += 1

                self._log_row_event(
                    row_id=input_row.id,
                    stage="final_merge",
                    row=current_row,
                    parser_result=candidate_meta.get("parser_result"),
                    llm_result=candidate_meta.get("llm_result"),
                    final_result={field: updated_row.get(field) for field in TRACKED_COVERAGE_FIELDS + ["llm_confidence", "llm_merge_status"]},
                    metadata={
                        "parser_quality": candidate_meta.get("parser_quality", {}),
                        "reconcile_meta": candidate_meta.get("reconcile_meta", {}),
                        "merge_meta": merge_meta,
                        "model": updated_row["llm_model"],
                    },
                )

                completed_ids.add(input_row.id)
                self._checkpoint_row(
                    row_id=input_row.id,
                    patch=patch,
                    meta={
                        "merge_status": merge_status,
                        "merged_fields": merge_meta["merged_fields"],
                        "llm_confidence": merge_meta["llm_confidence"],
                        "confidence_meta": merge_meta.get("confidence_meta", {}),
                        "review_flags": updated_row.get("review_flags", []),
                        "conflict_flags": updated_row.get("conflict_flags", []),
                        "model": updated_row["llm_model"],
                    },
                )

            self._save_state(completed_ids)

        export_df = self._prepare_export_df(df)
        export_df.to_csv(self.config.output_path, index=False, encoding="utf-8")

        failed_df = pd.DataFrame(self.failed_rows).drop_duplicates(subset=["id", "reason"], keep="last")
        failed_df.to_csv(self.config.failed_rows_path, index=False, encoding="utf-8")

        self._write_quality_report(baseline_df, df, selected_df, token_estimate)

        return {
            "selected_rows": int(len(selected_df)),
            "processed_rows": int(self.metrics["processed_rows"]),
            "merged_rows": int(self.metrics["merged_rows"]),
            "failed_rows": int(self.metrics["failed_rows"]),
            "review_rows": int(self.metrics["review_rows"]),
            "llm_called_rows": int(self.metrics["llm_called_rows"]),
            "parser_only_rows": int(self.metrics["parser_only_rows"]),
            "effective_batch_size": int(batch_size),
            "token_estimate": token_estimate,
            "output_path": str(self.config.output_path),
        }
