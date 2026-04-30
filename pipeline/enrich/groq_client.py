from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Tuple

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from enrich.prompts import SYSTEM_PROMPT, build_batch_prompt
from enrich.schemas import BatchExtractionResponse, VacancyExtraction, VacancyLLMInput


class LLMClientError(RuntimeError):
    pass


class GroqClientError(LLMClientError):
    pass


def _extract_json_payload(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        raise GroqClientError("Empty LLM response.")
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise GroqClientError("No JSON object found in LLM response.")
    return json.loads(text[start : end + 1])


@dataclass(slots=True)
class BatchLLMResult:
    items: List[VacancyExtraction]
    raw_response: str


class GroqExtractionClient:
    def __init__(self, api_key: str | None = None, max_retries: int = 4):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise GroqClientError("GROQ_API_KEY is not set.")

        try:
            from groq import Groq
        except ImportError as exc:
            raise GroqClientError("Package 'groq' is not installed. Run: pip install groq") from exc

        self._client = Groq(api_key=self.api_key)
        self.max_retries = max_retries

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _chat_completion(self, model: str, prompt: str):
        return self._client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

    def extract_batch(self, rows: List[VacancyLLMInput], model: str) -> BatchLLMResult:
        prompt = build_batch_prompt(rows)
        response = self._chat_completion(model=model, prompt=prompt)
        raw_text = response.choices[0].message.content or ""
        payload = _extract_json_payload(raw_text)
        validated = BatchExtractionResponse.model_validate(payload)
        return BatchLLMResult(items=validated.items, raw_response=raw_text)

    def extract_single(self, row: VacancyLLMInput, model: str) -> Tuple[VacancyExtraction, str]:
        result = self.extract_batch([row], model=model)
        if len(result.items) != 1:
            raise GroqClientError(f"Expected a single item, got {len(result.items)}.")
        return result.items[0], result.raw_response

