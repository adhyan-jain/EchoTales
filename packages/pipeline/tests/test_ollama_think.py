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


def _thinking_call(response: str, thinking: str = "") -> tuple[dict, _Out]:  # type: ignore[type-arg]
    import json

    sent: dict = {}  # type: ignore[type-arg]

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"response": response, "thinking": thinking})

    provider = OllamaProvider(model="qwen3:8b")
    provider._client = httpx.Client(transport=httpx.MockTransport(handler))
    req = LLMRequest(stage="scene_segment", prompt="p", system="s", max_tokens=7000, extra={"think": True})
    return sent, provider.complete(req, _Out).value


def test_think_request_drops_the_schema_format_and_keeps_the_cap() -> None:
    # Measured (v5): with `format` set the model skips its reasoning entirely, so a thinking request must not send it.
    sent, _ = _thinking_call('{"answer": "x"}')
    assert sent["think"] is True and "format" not in sent
    assert sent["options"]["num_predict"] == 7000
    assert _sent_body("qwen3:8b").get("format") is not None  # the default path is unchanged


def test_inline_trace_with_braces_is_ignored_and_the_json_after_it_is_parsed() -> None:
    reply = '<think>maybe {"answer": "wrong"} or not, let me see</think>\n```json\n{"answer": "right"}\n```'
    assert _thinking_call(reply)[1].answer == "right"


def test_split_think_separates_trace_and_answer_and_an_unfinished_trace_has_no_answer() -> None:
    from echotales.pipeline.llm.ollama import split_think

    assert split_think("<think>a</think>b") == ("<think>a</think>", "b")
    assert split_think("no trace") == ("", "no trace")
    assert split_think("<think>cut off while thinking {")[1] == ""
