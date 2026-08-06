"""LLM provider abstraction and escalation router.

Every stage in the pipeline talks to an `LLMRouter`, never to a provider
directly. That indirection is what makes `ECHOTALES_LLM_MODE` a pure config
switch and what keeps the escalation accounting in one place.
"""

from echotales.pipeline.llm.base import (
    LLMError,
    LLMParseError,
    LLMProvider,
    LLMRequest,
    LLMResult,
    LLMUnavailable,
    extract_json,
    parse_into,
    schema_instructions,
)
from echotales.pipeline.llm.router import (
    EscalationReason,
    LLMRouter,
    default_confidence,
)
from echotales.pipeline.llm.stub import StubProvider

__all__ = [
    "EscalationReason",
    "LLMError",
    "LLMParseError",
    "LLMProvider",
    "LLMRequest",
    "LLMResult",
    "LLMRouter",
    "LLMUnavailable",
    "StubProvider",
    "default_confidence",
    "extract_json",
    "parse_into",
    "schema_instructions",
]
