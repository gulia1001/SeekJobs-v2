from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Tuple

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from enrich.prompts import SYSTEM_PROMPT, build_batch_prompt
from enrich.schemas import BatchExtractionResponse, VacancyExtraction, VacancyLLMInput
from enrich.groq_client import _extract_json_payload, LLMClientError


class OllamaClientError(LLMClientError):
    pass


@dataclass(slots=True)
class BatchLLMResult:
    items: List[VacancyExtraction]
    raw_response: str


class OllamaExtractionClient:
    def __init__(self, url: str | None = None, max_retries: int = 4):
        self.url = url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.max_retries = max_retries
        self._session = requests.Session()

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _chat_completion(self, model: str, prompt: str) -> dict:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        response = self._session.post(
            f"{self.url}/v1/chat/completions",
            json=payload,
            timeout=120,
        )
        if response.status_code != 200:
            raise OllamaClientError(f"Ollama request failed: {response.status_code} {response.text}")
        return response.json()

    def extract_batch(self, rows: List[VacancyLLMInput], model: str) -> BatchLLMResult:
        prompt = build_batch_prompt(rows)
        response = self._chat_completion(model=model, prompt=prompt)
        choices = response.get("choices")
        if not choices or not isinstance(choices, list):
            raise OllamaClientError("Invalid Ollama response format: missing choices.")
        raw_text = choices[0].get("message", {}).get("content", "") or ""
        payload = _extract_json_payload(raw_text)
        validated = BatchExtractionResponse.model_validate(payload)
        return BatchLLMResult(items=validated.items, raw_response=raw_text)

    def extract_single(self, row: VacancyLLMInput, model: str) -> Tuple[VacancyExtraction, str]:
        result = self.extract_batch([row], model=model)
        if len(result.items) != 1:
            raise OllamaClientError(f"Expected a single item, got {len(result.items)}.")
        return result.items[0], result.raw_response
