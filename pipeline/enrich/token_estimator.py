from __future__ import annotations

import math
from typing import Iterable

from enrich.config import MODEL_PRICING, PipelineConfig
from enrich.prompts import SYSTEM_PROMPT, build_batch_prompt
from enrich.schemas import VacancyLLMInput


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def estimate_batch_input_tokens(rows: Iterable[VacancyLLMInput]) -> int:
    rows = list(rows)
    prompt = build_batch_prompt(rows)
    return estimate_text_tokens(SYSTEM_PROMPT) + estimate_text_tokens(prompt)


def estimate_output_tokens(row_count: int, tokens_per_row: int) -> int:
    return row_count * tokens_per_row


def estimate_cost(input_tokens: int, output_tokens: int, model_name: str) -> float:
    pricing = MODEL_PRICING[model_name]
    input_cost = (input_tokens / 1_000_000) * pricing.input_price_per_million
    output_cost = (output_tokens / 1_000_000) * pricing.output_price_per_million
    return round(input_cost + output_cost, 6)


def estimate_run_costs(rows: list[VacancyLLMInput], config: PipelineConfig, batch_size: int | None = None) -> dict:
    batch_size = max(1, batch_size or config.batch_size)
    batches = [rows[index : index + batch_size] for index in range(0, len(rows), batch_size)]

    input_tokens_total = sum(estimate_batch_input_tokens(batch) for batch in batches)
    output_tokens_total = estimate_output_tokens(len(rows), config.output_tokens_per_row_estimate)

    hybrid_retry_input = math.ceil(input_tokens_total * config.estimated_retry_share)
    hybrid_retry_output = math.ceil(output_tokens_total * config.estimated_retry_share)

    estimate = {
        "row_count": len(rows),
        "batch_count": len(batches),
        "estimated_input_tokens": input_tokens_total,
        "estimated_output_tokens": output_tokens_total,
        "cost_8b_usd": estimate_cost(
            input_tokens=input_tokens_total,
            output_tokens=output_tokens_total,
            model_name=config.cheap_model,
        ),
        "cost_70b_usd": estimate_cost(
            input_tokens=input_tokens_total,
            output_tokens=output_tokens_total,
            model_name=config.fallback_model,
        ),
        "cost_hybrid_usd": round(
            estimate_cost(
                input_tokens=input_tokens_total,
                output_tokens=output_tokens_total,
                model_name=config.cheap_model,
            )
            + estimate_cost(
                input_tokens=hybrid_retry_input,
                output_tokens=hybrid_retry_output,
                model_name=config.fallback_model,
            ),
            6,
        ),
        "hybrid_retry_share_assumption": config.estimated_retry_share,
    }
    return estimate
