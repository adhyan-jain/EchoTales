"""Deterministic stub provider.

Makes the entire pipeline runnable with no GPU, no model download and no
network, which is what allows CI to exercise Phases 1-6 end to end. It is also
the fixture backend for tests: responses are keyed by stage and are stable
across runs, so a test asserting on resolver behaviour is not also implicitly
asserting on a language model's mood.

The stub answers *conservatively* -- it declines rather than guesses. That
matters: if it invented plausible-looking answers, a pipeline bug that should
surface as "no LLM configured" would instead surface as quietly wrong output.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from echotales.pipeline.llm.base import (
    LLMParseError,
    LLMProvider,
    LLMRequest,
    LLMResult,
    SchemaT,
)
from pydantic import BaseModel

#: stage -> callable producing a raw JSON response for that stage.
StubHandler = Callable[[LLMRequest, type[BaseModel]], str]


def _empty_for_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Build the most conservative instance a schema will accept.

    Required scalars get neutral values; required containers get empty ones.
    The result means "I have nothing to add", which is the correct default for
    every LLM stage in this pipeline -- each one is a *supplement* to a
    deterministic pass, never the sole source of truth.
    """
    out: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        if not field.is_required():
            continue
        ann = field.annotation
        origin = getattr(ann, "__origin__", None)
        if origin in (list, set, tuple):
            out[name] = []
        elif origin is dict:
            out[name] = {}
        elif ann is bool:
            out[name] = False
        elif ann is int:
            out[name] = 0
        elif ann is float:
            out[name] = 0.0
        elif ann is str:
            out[name] = ""
        elif isinstance(ann, type) and issubclass(ann, BaseModel):
            out[name] = _empty_for_schema(ann)
        else:
            # Enums and unions: take the first literal the schema allows.
            choices = getattr(ann, "__args__", None)
            if choices:
                out[name] = choices[0] if not isinstance(choices[0], type) else ""
            else:
                out[name] = None
    return out


class StubProvider(LLMProvider):
    """Returns canned or schema-empty responses.

    Register per-stage handlers to script specific behaviour in a test:

        stub = StubProvider()
        stub.register("adjudicate", lambda req, schema: '{"decision": "NEW"}')
    """

    tier = "stub"

    def __init__(self, model: str = "stub") -> None:
        self._model = model
        self._handlers: dict[str, StubHandler] = {}
        #: Every request seen, for assertions about *whether* a stage called out.
        self.calls: list[LLMRequest] = []

    @property
    def model(self) -> str:
        return self._model

    def register(self, stage: str, handler: StubHandler) -> None:
        self._handlers[stage] = handler

    def register_response(self, stage: str, payload: BaseModel | dict[str, Any] | str) -> None:
        """Register a fixed response for a stage."""
        if isinstance(payload, BaseModel):
            text = payload.model_dump_json()
        elif isinstance(payload, dict):
            text = json.dumps(payload)
        else:
            text = payload
        self._handlers[stage] = lambda _req, _schema: text

    def complete(self, request: LLMRequest, schema: type[SchemaT]) -> LLMResult[SchemaT]:
        self.calls.append(request)
        handler = self._handlers.get(request.stage)
        raw = handler(request, schema) if handler else json.dumps(_empty_for_schema(schema))
        try:
            value = schema.model_validate_json(raw)
        except Exception as exc:
            raise LLMParseError(
                f"stub response for stage {request.stage!r} did not match "
                f"{schema.__name__}: {exc}"
            ) from exc
        return LLMResult(
            value=value,
            model=self._model,
            tier=self.tier,
            prompt_tokens=len(request.prompt) // 4,
            completion_tokens=len(raw) // 4,
            latency_ms=0,
        )

    def available(self) -> bool:
        return True
