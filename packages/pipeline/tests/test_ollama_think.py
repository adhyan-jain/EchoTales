"""A thinking model must not spend the reader's token budget on a reasoning trace.

Why: qwen3:8b thinks by default; under a JSON-schema `format` and a 1500-token cap the trace either eats the budget
(truncated JSON fails validation) or leaks into the response. The provider asks ollama for `think: false` for that
family only, so the request every other model receives stays byte-for-byte what the recorded runs used.
"""

from __future__ import annotations

import httpx
from echotales.pipeline.llm.base import LLMRequest
from echotales.pipeline.llm.ollama import OllamaProvider
from pydantic import BaseModel


class _Out(BaseModel):
    answer: str


def _sent_body(model: str) -> dict:  # type: ignore[type-arg]
    sent: dict = {}  # type: ignore[type-arg]

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"response": '{"answer": "x"}'})

    provider = OllamaProvider(model=model)
    provider._client = httpx.Client(transport=httpx.MockTransport(handler))
    provider.complete(LLMRequest(stage="reader", prompt="p", system="s", temperature=0.0, max_tokens=50), _Out)
    return sent


def test_qwen3_is_asked_not_to_think() -> None:
    assert _sent_body("qwen3:8b")["think"] is False


def test_other_models_request_is_unchanged() -> None:
    assert "think" not in _sent_body("gemma2:9b")
    assert "think" not in _sent_body("qwen2.5:7b")
