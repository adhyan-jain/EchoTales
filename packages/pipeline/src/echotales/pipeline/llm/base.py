"""LLM provider protocol.

Every call site asks for **structured output validated by a Pydantic schema**,
never free text. Two reasons: the pipeline runs unattended over hundreds of
chapters, so an unparseable answer must fail loudly at one call site rather
than silently corrupt a downstream heuristic; and a validated schema is what
lets a small local model and a large API model be genuinely interchangeable.

Providers do not retry or fall back on their own. Escalation is the router's
job, so that every escalation decision is recorded in one place -- the
`llm_call` table -- and the "% routed to expensive inference vs. accuracy
gained" measurement stays trustworthy.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel, ValidationError

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMError(RuntimeError):
    """Provider could not produce a usable answer."""


class LLMUnavailable(LLMError):
    """Provider is not reachable or not configured.

    Distinct from `LLMError` so the router can tell "this backend is down"
    (fall through to another tier) from "the model answered badly" (which may
    be worth escalating for a better answer).
    """


class LLMParseError(LLMError):
    """Response did not validate against the requested schema."""


@dataclass(slots=True)
class LLMResult[T: BaseModel]:
    """A parsed response plus the accounting the eval harness needs."""

    value: T
    model: str
    tier: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    # Set by the router when this result came from an escalated call.
    escalated: bool = False
    escalation_reason: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class LLMRequest:
    """One structured-output request.

    `stage` names the pipeline phase ("span_classify", "adjudicate", ...) and
    is what the escalation report groups by, so it should stay stable.
    """

    stage: str
    prompt: str
    system: str = ""
    max_tokens: int = 2048
    temperature: float = 0.0
    # Free-form hints a provider may ignore.
    extra: dict[str, object] = field(default_factory=dict)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def heal_json(text: str, schema: type[BaseModel] | None = None) -> str:
    """Attempt to repair a truncated JSON string by closing open strings, arrays, and objects."""
    start = text.find('{')
    start_arr = text.find('[')
    if start == -1 and start_arr == -1:
        return text
    if start == -1 or (start_arr != -1 and start_arr < start):
        start = start_arr

    text = text[start:]
    stack = []
    in_string = False
    escaped = False

    i = 0
    clean_text = []
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
                clean_text.append(ch)
            elif ch == '\\':
                escaped = True
                clean_text.append(ch)
            elif ch == '"':
                in_string = False
                clean_text.append(ch)
            else:
                clean_text.append(ch)
        else:
            if ch == '"':
                in_string = True
                clean_text.append(ch)
            elif ch in ('{', '['):
                stack.append(ch)
                clean_text.append(ch)
            elif ch in ('}', ']'):
                if stack:
                    stack.pop()
                clean_text.append(ch)
            else:
                clean_text.append(ch)
        i += 1

    if in_string:
        if clean_text and clean_text[-1] == '\\':
            clean_text.pop()
        clean_text.append('"')

    healed = "".join(clean_text)
    healed = healed.rstrip()

    for _ in range(50):
        test_str = healed
        for delim in reversed(stack):
            if delim == '{':
                test_str += '}'
            elif delim == '[':
                test_str += ']'

        try:
            json.loads(test_str)
            if schema is not None:
                schema.model_validate_json(test_str)
            return test_str
        except (json.JSONDecodeError, ValidationError):
            pass

        if not healed:
            break

        last_ch = healed[-1]
        healed = healed[:-1]

        if (last_ch == '{' and stack and stack[-1] == '{') or (last_ch == '[' and stack and stack[-1] == '['):
            stack.pop()
        elif last_ch == '}':
            stack.append('{')
        elif last_ch == ']':
            stack.append('[')

        healed = healed.rstrip().rstrip(',:')

    return text


def extract_json(text: str, schema: type[BaseModel] | None = None) -> str:
    """Pull a JSON object out of a model response.

    Small local models wrap JSON in prose or code fences far more often than
    large ones do, and rejecting those responses outright would inflate the
    escalation rate with failures that are purely cosmetic -- distorting the
    very metric the escalation ladder is supposed to report. So: try the raw
    text, then a fenced block, then the outermost brace-balanced span.
    """
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        try:
            json.loads(stripped)
            if schema is not None:
                schema.model_validate_json(stripped)
            return stripped
        except (json.JSONDecodeError, ValidationError):
            pass

    fenced = _FENCE.search(text)
    if fenced:
        return fenced.group(1).strip()

    start = text.find("{")
    if start == -1:
        raise LLMParseError(f"no JSON object found in response: {text[:200]!r}")

    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    try:
        return heal_json(text[start:], schema=schema)
    except Exception as exc:
        raise LLMParseError(f"unbalanced JSON object in response: {text[:200]!r}") from exc


def parse_into[T: BaseModel](schema: type[T], text: str) -> T:
    """Validate a raw response into the requested schema."""
    payload = extract_json(text, schema=schema)
    try:
        return schema.model_validate_json(payload)
    except ValidationError as exc:
        raise LLMParseError(f"response did not match {schema.__name__}: {exc}") from exc


def schema_instructions(schema: type[BaseModel]) -> str:
    """Render a JSON-schema instruction block to append to a prompt.

    Included verbatim for local models, which do not support a native
    structured-output mode the way the API does.
    """
    return (
        "Respond with a single JSON object and nothing else: no markdown, "
        "no bullet points or numbered lists, no headings, no code fences, "
        "no explanation before or after -- the entire response must be "
        "parseable as JSON on its own, starting with { and ending with }. "
        "It must conform to this JSON Schema:\n"
        f"{json.dumps(schema.model_json_schema(), indent=2)}"
    )


class LLMProvider(ABC):
    """One backend at one tier."""

    #: "stub" | "local" | "api" -- used for accounting and routing.
    tier: str = "unknown"

    @property
    @abstractmethod
    def model(self) -> str:
        """Model identifier, recorded against every call."""

    @abstractmethod
    def complete(self, request: LLMRequest, schema: type[SchemaT]) -> LLMResult[SchemaT]:
        """Run one request and parse the response into `schema`.

        Raises `LLMUnavailable` if the backend cannot be reached, or
        `LLMParseError` if the response will not validate.
        """

    def available(self) -> bool:
        """Cheap reachability probe. Providers should not raise here."""
        return True
