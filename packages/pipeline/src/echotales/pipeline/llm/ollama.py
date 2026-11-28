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
import re
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

_THINK_BLOCK = re.compile(r"<think>.*?(?:</think>|\Z)", re.DOTALL)


def split_think(text: str) -> tuple[str, str]:
    """(reasoning trace, final answer) of a model reply that carries its trace inline as <think>...</think>.

    Scene segmentation v5 lets the model reason before the JSON; a trace can contain braces and half-formed
    JSON, so `extract_json` must only ever see what follows it. An unterminated trace (the token cap hit mid-thought)
    leaves an empty answer, which the caller treats as a failed call rather than guessing a cut out of the thoughts.
    """
    trace = "".join(m.group(0) for m in _THINK_BLOCK.finditer(text))
    return trace, _THINK_BLOCK.sub("", text).strip()


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
        if self._model.startswith("qwen3"):
            # qwen3 thinks by default; a reasoning trace under a schema `format` and a 1500-token cap either
            # truncates the JSON or leaks into it. Only this family gets the flag so every other model's request
            # stays identical to the recorded reader runs.
            body["think"] = False
        if request.extra.get("think") is True:
            # Per-request opt-in (segment v5: one whole-chapter call). Never a provider-wide switch: every other
            # stage keeps the forced think=False above, so recorded runs of those stages do not change.
            body["think"] = True
            # Measured on qwen3:8b (v5): with a schema `format` ollama constrains decoding from the first token and the
            # model skips its reasoning entirely (7 tokens, empty trace). So a thinking request goes out without
            # `format`; the schema is still rendered into the prompt and the JSON is parsed after the trace.
            body.pop("format", None)
        started = time.perf_counter()
        try:
            resp = self._client.post(f"{self.host}/api/generate", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"ollama request failed: {exc}") from exc

        data = resp.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        # With think=true ollama returns the trace in a separate `thinking` field; some builds leave it inline.
        _trace, answer = split_think(data.get("response", ""))
        value = parse_into(schema, answer)
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
