"""Tests for the LLM abstraction and the escalation ladder.

The router is a measurement instrument as much as it is plumbing -- the
escalation rate it produces is a reported result -- so the accounting is
tested as carefully as the routing.
"""

from __future__ import annotations

import pytest
from echotales.core.store import Store
from echotales.pipeline.config import LLMMode, Settings
from echotales.pipeline.llm.base import (
    LLMError,
    LLMParseError,
    LLMProvider,
    LLMRequest,
    LLMResult,
    LLMUnavailable,
    extract_json,
    parse_into,
)
from echotales.pipeline.llm.router import EscalationReason, LLMRouter, default_confidence
from echotales.pipeline.llm.stub import StubProvider
from pydantic import BaseModel


class Answer(BaseModel):
    decision: str
    confidence: float = 1.0


class Bare(BaseModel):
    """No confidence field: the schema makes no confidence claim."""

    label: str


class FakeProvider(LLMProvider):
    """Scriptable provider for exercising router branches."""

    def __init__(
        self,
        tier: str,
        *,
        payload: str | None = None,
        raises: Exception | None = None,
        available: bool = True,
        model: str = "fake",
    ) -> None:
        self.tier = tier
        self._payload = payload
        self._raises = raises
        self._available = available
        self._model = model
        self.calls = 0

    @property
    def model(self) -> str:
        return self._model

    def available(self) -> bool:
        return self._available

    def complete(self, request: LLMRequest, schema):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        assert self._payload is not None
        return LLMResult(
            value=schema.model_validate_json(self._payload),
            model=self._model,
            tier=self.tier,
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=1,
        )


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def req(stage: str = "test") -> LLMRequest:
    return LLMRequest(stage=stage, prompt="who is this?")


def hybrid(**kw: object) -> Settings:
    return Settings(llm_mode=LLMMode.HYBRID, **kw)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# JSON extraction -- small local models are messy, and rejecting cosmetic
# failures would inflate the escalation rate with non-problems.
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_bare_object(self) -> None:
        assert extract_json('{"a": 1}') == '{"a": 1}'

    def test_fenced_block(self) -> None:
        assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_unlabelled_fence(self) -> None:
        assert extract_json('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_object_wrapped_in_prose(self) -> None:
        assert extract_json('Sure! {"a": 1} Hope that helps.') == '{"a": 1}'

    def test_nested_braces(self) -> None:
        assert extract_json('x {"a": {"b": 2}} y') == '{"a": {"b": 2}}'

    def test_braces_inside_strings_are_ignored(self) -> None:
        raw = '{"note": "a } brace"}'
        assert extract_json(f"text {raw}") == raw

    def test_escaped_quote_inside_string(self) -> None:
        raw = '{"note": "say \\" now"}'
        assert extract_json(raw) == raw

    def test_no_json_raises(self) -> None:
        with pytest.raises(LLMParseError, match="no JSON object"):
            extract_json("I do not know.")

    def test_unbalanced_embedded_object_heals(self) -> None:
        assert extract_json('here you go: {"a": 1') == '{"a": 1}'

    def test_bare_truncated_json_heals(self) -> None:
        assert extract_json('{"a": 1') == '{"a": 1}'
        with pytest.raises(LLMParseError):
            parse_into(Answer, '{"a": 1')

    def test_parse_into_reports_the_schema(self) -> None:
        with pytest.raises(LLMParseError, match="Answer"):
            parse_into(Answer, '{"wrong": true}')

    def test_extract_json_truncated_with_schema(self) -> None:
        from echotales.pipeline.mentions.ner import NerResponse
        raw = 'Here is the JSON: {"entities": [{"text": "Fang Yuan", "label": "character"}, {"text": "Spring'
        healed = extract_json(raw, schema=NerResponse)
        assert healed == '{"entities": [{"text": "Fang Yuan", "label": "character"}]}'


# ---------------------------------------------------------------------------
# Stub provider
# ---------------------------------------------------------------------------


class TestStubProvider:
    def test_declines_rather_than_guessing(self) -> None:
        """A conservative default keeps 'no LLM configured' visible as itself."""
        out = StubProvider().complete(req(), Bare)
        assert out.value.label == ""

    def test_registered_response_is_returned(self) -> None:
        stub = StubProvider()
        stub.register_response("adjudicate", {"decision": "NEW", "confidence": 0.9})
        assert stub.complete(req("adjudicate"), Answer).value.decision == "NEW"

    def test_responses_are_stage_scoped(self) -> None:
        stub = StubProvider()
        stub.register_response("a", {"label": "x"})
        assert stub.complete(req("a"), Bare).value.label == "x"
        assert stub.complete(req("b"), Bare).value.label == ""

    def test_calls_are_recorded(self) -> None:
        stub = StubProvider()
        stub.complete(req("s1"), Bare)
        stub.complete(req("s2"), Bare)
        assert [c.stage for c in stub.calls] == ["s1", "s2"]

    def test_invalid_canned_response_fails_loudly(self) -> None:
        stub = StubProvider()
        stub.register_response("x", {"nope": 1})
        with pytest.raises(LLMParseError):
            stub.complete(req("x"), Answer)


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


class TestDefaultConfidence:
    def test_reads_the_field_when_present(self) -> None:
        assert default_confidence(Answer(decision="LINK", confidence=0.4)) == 0.4

    def test_absent_field_means_no_claim_so_certain(self) -> None:
        assert default_confidence(Bare(label="x")) == 1.0


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class TestStubMode:
    def test_stub_mode_never_touches_other_tiers(self, store: Store) -> None:
        local = FakeProvider("local", payload='{"label": "l"}')
        router = LLMRouter(
            settings=Settings(llm_mode=LLMMode.STUB), store=store, local=local
        )
        router.complete(req(), Bare)
        assert local.calls == 0
        assert router.escalation_count == 0


class TestLocalMode:
    def test_uses_local_and_records_the_call(self, store: Store) -> None:
        local = FakeProvider("local", payload='{"label": "l"}')
        router = LLMRouter(
            settings=Settings(llm_mode=LLMMode.LOCAL), store=store, local=local
        )
        assert router.complete(req(), Bare).value.label == "l"
        store.conn.commit()
        assert store.escalation_stats()[0]["calls"] == 1

    def test_unreachable_backend_surfaces_rather_than_silently_degrading(
        self, store: Store
    ) -> None:
        """In local mode there is nothing to fall back to, so the error must escape.

        Swallowing it would turn "ollama is not running" into silently empty
        annotations across a whole novel.
        """
        local = FakeProvider("local", raises=LLMUnavailable("connection refused"))
        router = LLMRouter(
            settings=Settings(llm_mode=LLMMode.LOCAL), store=store, local=local
        )
        with pytest.raises(LLMUnavailable, match="connection refused"):
            router.complete(req(), Bare)


class TestHybridEscalation:
    def test_confident_local_answer_is_kept(self, store: Store) -> None:
        local = FakeProvider("local", payload='{"decision": "LINK", "confidence": 0.95}')
        api = FakeProvider("api", payload='{"decision": "NEW", "confidence": 1.0}')
        router = LLMRouter(settings=hybrid(), store=store, local=local, api=api)

        assert router.complete(req(), Answer).value.decision == "LINK"
        assert api.calls == 0
        assert router.escalation_count == 0

    def test_low_confidence_escalates(self, store: Store) -> None:
        local = FakeProvider("local", payload='{"decision": "LINK", "confidence": 0.2}')
        api = FakeProvider("api", payload='{"decision": "NEW", "confidence": 1.0}')
        router = LLMRouter(settings=hybrid(), store=store, local=local, api=api)

        out = router.complete(req(), Answer)
        assert out.value.decision == "NEW"
        assert out.escalated
        assert out.escalation_reason == EscalationReason.LOW_CONFIDENCE.value
        assert router.escalation_count == 1

    def test_unavailable_local_escalates(self, store: Store) -> None:
        local = FakeProvider("local", payload="{}", available=False)
        api = FakeProvider("api", payload='{"label": "a"}')
        router = LLMRouter(settings=hybrid(), store=store, local=local, api=api)

        out = router.complete(req(), Bare)
        assert out.escalation_reason == EscalationReason.LOCAL_UNAVAILABLE.value
        assert local.calls == 0

    def test_parse_failure_escalates(self, store: Store) -> None:
        local = FakeProvider("local", raises=LLMParseError("bad json"))
        api = FakeProvider("api", payload='{"label": "a"}')
        router = LLMRouter(settings=hybrid(), store=store, local=local, api=api)

        out = router.complete(req(), Bare)
        assert out.escalation_reason == EscalationReason.LOCAL_PARSE_FAILURE.value

    def test_force_escalate_skips_local_entirely(self, store: Store) -> None:
        """The DEFER path: the caller already knows this one is hard."""
        local = FakeProvider("local", payload='{"label": "l"}')
        api = FakeProvider("api", payload='{"label": "a"}')
        router = LLMRouter(settings=hybrid(), store=store, local=local, api=api)

        out = router.complete(req(), Bare, force_escalate=True)
        assert out.value.label == "a"
        assert local.calls == 0
        assert out.escalation_reason == EscalationReason.CALLER_REQUESTED.value

    def test_api_failure_falls_back_to_the_local_answer(self, store: Store) -> None:
        """A weak answer beats no answer when the expensive tier is down."""
        local = FakeProvider("local", payload='{"decision": "LINK", "confidence": 0.1}')
        api = FakeProvider("api", raises=LLMUnavailable("down"))
        router = LLMRouter(settings=hybrid(), store=store, local=local, api=api)

        assert router.complete(req(), Answer).value.decision == "LINK"

    def test_api_failure_with_no_local_answer_raises(self, store: Store) -> None:
        local = FakeProvider("local", raises=LLMError("bad"))
        api = FakeProvider("api", raises=LLMUnavailable("down"))
        router = LLMRouter(settings=hybrid(), store=store, local=local, api=api)

        with pytest.raises(LLMError):
            router.complete(req(), Bare)


class TestEscalationBudget:
    def test_budget_caps_escalations(self, store: Store) -> None:
        local = FakeProvider("local", payload='{"decision": "L", "confidence": 0.1}')
        api = FakeProvider("api", payload='{"decision": "A", "confidence": 1.0}')
        router = LLMRouter(
            settings=hybrid(max_escalations_per_run=1), store=store, local=local, api=api
        )

        assert router.complete(req(), Answer).value.decision == "A"
        # Second call is over budget and keeps the local answer.
        assert router.complete(req(), Answer).value.decision == "L"
        assert api.calls == 1

    def test_budget_exhaustion_with_no_local_answer_raises(self, store: Store) -> None:
        local = FakeProvider("local", raises=LLMError("bad"))
        api = FakeProvider("api", payload='{"label": "a"}')
        router = LLMRouter(
            settings=hybrid(max_escalations_per_run=0), store=store, local=local, api=api
        )
        with pytest.raises(LLMUnavailable, match="budget"):
            router.complete(req(), Bare)


class TestAccounting:
    def test_rate_counts_all_calls_not_just_escalated_ones(self, store: Store) -> None:
        """An escalation rate without its denominator is meaningless."""
        local = FakeProvider("local", payload='{"decision": "L", "confidence": 0.9}')
        api = FakeProvider("api", payload='{"decision": "A", "confidence": 1.0}')
        router = LLMRouter(settings=hybrid(), store=store, local=local, api=api)

        for _ in range(3):
            router.complete(req(), Answer)
        router.complete(req(), Answer, force_escalate=True)

        assert router.call_count == 4
        assert router.escalation_count == 1
        assert router.escalation_rate == pytest.approx(0.25)

    def test_failed_local_attempts_are_still_logged(self, store: Store) -> None:
        """Hiding the attempts that escalated would overstate local performance."""
        local = FakeProvider("local", payload='{"decision": "L", "confidence": 0.1}')
        api = FakeProvider("api", payload='{"decision": "A", "confidence": 1.0}')
        router = LLMRouter(settings=hybrid(), store=store, local=local, api=api)
        router.complete(req("resolve"), Answer)
        store.conn.commit()

        tiers = {r["tier"]: r for r in store.escalation_stats()}
        assert tiers["local"]["calls"] == 1
        assert tiers["api"]["escalations"] == 1

    def test_report_shape(self, store: Store) -> None:
        local = FakeProvider("local", payload='{"label": "l"}')
        router = LLMRouter(
            settings=Settings(llm_mode=LLMMode.LOCAL), store=store, local=local
        )
        router.complete(req(), Bare)
        store.conn.commit()
        report = router.report()
        assert report["mode"] == "local"
        assert report["calls"] == 1

    def test_router_works_without_a_store(self) -> None:
        local = FakeProvider("local", payload='{"label": "l"}')
        router = LLMRouter(settings=Settings(llm_mode=LLMMode.LOCAL), local=local)
        assert router.complete(req(), Bare).value.label == "l"

