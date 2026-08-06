"""API provider backed by Claude.

The escalation tier. Handles the residual few percent of cases the local model
defers on -- reveals, deceptions, title transfers and cross-chapter identity
questions where getting it wrong poisons every later decision about that
entity.

Imported lazily: the `anthropic` package is an optional extra, and a checkout
without it must still be able to run the whole pipeline in `stub` or `local`
mode.
"""

from __future__ import annotations

import os
import time

from echotales.pipeline.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResult,
    LLMUnavailable,
    SchemaT,
    parse_into,
    schema_instructions,
)

DEFAULT_MODEL = "claude-sonnet-4-5"


class AnthropicProvider(LLMProvider):
    tier = "api"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        *,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: object | None = None

    @property
    def model(self) -> str:
        return self._model

    def _ensure_client(self) -> object:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise LLMUnavailable(
                "the anthropic package is not installed; run `uv sync --extra api`"
            ) from exc
        self._client = Anthropic(
            api_key=self._api_key, timeout=self._timeout, max_retries=self._max_retries
        )
        return self._client

    def available(self) -> bool:
        if not self._api_key:
            return False
        try:
            self._ensure_client()
        except LLMUnavailable:
            return False
        return True

    def complete(self, request: LLMRequest, schema: type[SchemaT]) -> LLMResult[SchemaT]:
        client = self._ensure_client()
        prompt = f"{request.prompt}\n\n{schema_instructions(schema)}"
        started = time.perf_counter()
        try:
            message = client.messages.create(  # type: ignore[attr-defined]
                model=self._model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=request.system or "You extract structured data from prose.",
                messages=[
                    {"role": "user", "content": prompt},
                    # Prefilling an opening brace suppresses preamble entirely,
                    # which is cheaper and more reliable than asking for it.
                    {"role": "assistant", "content": "{"},
                ],
            )
        except Exception as exc:
            raise LLMUnavailable(f"anthropic request failed: {exc}") from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )
        # Re-attach the prefilled brace before parsing.
        value = parse_into(schema, "{" + text if not text.lstrip().startswith("{") else text)
        return LLMResult(
            value=value,
            model=self._model,
            tier=self.tier,
            prompt_tokens=int(getattr(message.usage, "input_tokens", 0)),
            completion_tokens=int(getattr(message.usage, "output_tokens", 0)),
            latency_ms=elapsed_ms,
        )
