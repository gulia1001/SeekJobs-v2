from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


TELEGRAM_SOURCE_FALLBACK = "telegram"
STRUCTURED_SOURCES = {"hh_kz", "kaspi_jobs", "kolesa_jobs"}

CATEGORY_VALUES = [
    "data",
    "software_engineering",
    "qa",
    "devops",
    "product",
    "design",
    "analytics",
    "security",
    "management",
    "support",
    "marketing",
    "sales",
    "hr",
    "finance",
    "other",
    "unknown",
]

LEVEL_VALUES = [
    "intern",
    "junior",
    "middle",
    "senior",
    "teamlead",
    "manager",
    "unknown",
]

EMPLOYMENT_VALUES = [
    "full_time",
    "part_time",
    "contract",
    "internship",
    "temporary",
    "unknown",
]

WORK_FORMAT_VALUES = [
    "office",
    "remote",
    "hybrid",
    "unknown",
]

ENGLISH_LEVEL_VALUES = [
    "not_required",
    "a1",
    "a2",
    "b1",
    "b2",
    "c1",
    "c2",
    "unknown",
]

CURRENCY_VALUES = [
    "KZT",
    "USD",
    "EUR",
    "RUB",
    "BYN",
    "UZS",
    "KGS",
    "unknown",
]


@dataclass(slots=True, frozen=True)
class ModelPricing:
    name: str
    input_price_per_million: float
    output_price_per_million: float


MODEL_PRICING = {
    "llama-3.1-8b-instant": ModelPricing(
        name="llama-3.1-8b-instant",
        input_price_per_million=0.05,
        output_price_per_million=0.08,
    ),
    "llama3.1:8b": ModelPricing(
        name="llama3.1:8b",
        input_price_per_million=0.05,
        output_price_per_million=0.08,
    ),
    "llama-3.3-70b-versatile": ModelPricing(
        name="llama-3.3-70b-versatile",
        input_price_per_million=0.59,
        output_price_per_million=0.79,
    ),
    "llama3.3:70b": ModelPricing(
        name="llama3.3:70b",
        input_price_per_million=0.59,
        output_price_per_million=0.79,
    ),
}


@dataclass(slots=True)
class PipelineConfig:
    input_path: Path
    output_path: Path
    mode: str = "hybrid"
    batch_size: int = 30
    min_description_length: int = 200
    cheap_model: str = "llama-3.1-8b-instant"
    fallback_model: str = "llama-3.3-70b-versatile"
    client: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    sample_size: int = 300
    low_confidence_threshold: float = 0.45
    review_confidence_threshold: float = 0.80
    sample_telegram: int = 200
    sample_hh: int = 70
    sample_other: int = 30
    full_run: bool = False
    random_seed: int = 42
    cheap_model_safe_batch_size: int = 5
    hybrid_safe_batch_size: int = 5
    low_confidence_threshold: float = 0.65
    review_confidence_threshold: float = 0.85
    raw_model_confidence_weight: float = 0.03
    checkpoint_root: Path = field(default_factory=lambda: Path(".llm_checkpoints"))
    baseline_suffix: str = ".baseline.csv"
    failed_rows_filename: str = "failed_llm_rows.csv"
    audit_log_filename: str = "llm_audit_log.jsonl"
    quality_report_filename: str = "quality_report.json"
    checkpoint_filename: str = "checkpoint_rows.jsonl"
    state_filename: str = "checkpoint_state.json"
    estimated_retry_share: float = 0.10
    output_tokens_per_row_estimate: int = 190

    @property
    def output_dir(self) -> Path:
        return self.output_path.parent

    @property
    def output_stem(self) -> str:
        return self.output_path.stem

    @property
    def baseline_path(self) -> Path:
        return self.output_dir / f"{self.output_stem}{self.baseline_suffix}"

    @property
    def failed_rows_path(self) -> Path:
        return self.output_dir / self.failed_rows_filename

    @property
    def audit_log_path(self) -> Path:
        return self.output_dir / self.audit_log_filename

    @property
    def quality_report_path(self) -> Path:
        return self.output_dir / self.quality_report_filename

    @property
    def checkpoint_dir(self) -> Path:
        return self.checkpoint_root / self.output_stem

    @property
    def checkpoint_rows_path(self) -> Path:
        return self.checkpoint_dir / self.checkpoint_filename

    @property
    def checkpoint_state_path(self) -> Path:
        return self.checkpoint_dir / self.state_filename
