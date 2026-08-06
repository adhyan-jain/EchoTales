"""Local provider backed by ollama.

The bulk tier. Runs a quantized 7-8B model on the development GPU, which is
enough for the high-volume, low-ambiguity passes (span classification, mention
sweeps) but not for adjudicating a genuinely hard identity decision -- that is
what the escalation ladder is for.

Two accommodations for small models, both deliberate:

- ollama's ``format`` parameter takes a JSON Schema and constrains decoding,
  which removes most malformed-JSON failures at the source.
- The schema is *also* rendered into the prompt. Constrained decoding fixes
  syntax, not comprehension; showing the field names materially improves
  whether the values mean anything.
"""

from __future__ import annotations

import os
import time

import httpx
from echotales.pipeline.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResult,
    LLMUnavailable,
    SchemaT,
    parse_into,
    schema_instructions,
)

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b-instruct"


class OllamaProvider(LLMProvider):
    tier = "local"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str | None = None,
        *,
        timeout: float = 180.0,
        num_ctx: int = 8192,
    ) -> None:
        self._model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        # Long default timeout: an 8B model on a laptop GPU running an 8k
        # context is slow, and a spurious timeout mid-run would escalate a
        # perfectly answerable case to the paid tier and skew the report.
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._client = httpx.Client(timeout=timeout)

    @property
    def model(self) -> str:
        return self._model

    def available(self) -> bool:
        try:
            resp = self._client.get(f"{self.host}/api/tags", timeout=3.0)
            resp.raise_for_status()
            models = {m.get("name", "") for m in resp.json().get("models", [])}
        except Exception:
            return False
        # ollama reports "qwen2.5:7b-instruct"; accept a bare family name too.
        return any(m == self._model or m.startswith(f"{self._model}:") for m in models)

    def complete(self, request: LLMRequest, schema: type[SchemaT]) -> LLMResult[SchemaT]:
        prompt = f"{request.prompt}\n\n{schema_instructions(schema)}"
        body = {
            "model": self._model,
            "prompt": prompt,
            "system": request.system,
            "stream": False,
            "format": schema.model_json_schema(),
            "options": {
                "temperature": request.temperature,
                "num_ctx": self.num_ctx,
                "num_predict": request.max_tokens,
            },
        }
        started = time.perf_counter()
        try:
            resp = self._client.post(f"{self.host}/api/generate", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"ollama request failed: {exc}") from exc

        data = resp.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        value = parse_into(schema, data.get("response", ""))
        return LLMResult(
            value=value,
            model=self._model,
            tier=self.tier,
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
            latency_ms=elapsed_ms,
        )

    def close(self) -> None:
        self._client.close()
