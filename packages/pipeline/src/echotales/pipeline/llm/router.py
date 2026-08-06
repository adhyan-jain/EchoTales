"""The escalation ladder.

Not plumbing. plans.md §7 names "% routed to expensive inference vs. accuracy
gained" as a contribution of this work, which makes the routing decision a
measurement instrument. Two consequences shape this module:

- **Every call is logged**, including the ones that never escalate. A rate is
  meaningless without its denominator.
- **Escalation reasons are enumerated**, not free text, so the report can group
  by cause and say *why* the expensive tier was needed rather than only how
  often.

The ladder itself is deliberately simple: try local, and escalate when the
local answer is unusable or unconfident. Sophistication here would be hard to
attribute in the ablation.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from echotales.core.store import Store
from echotales.pipeline.config import LLMMode, Settings, get_settings
from echotales.pipeline.llm.base import (
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResult,
    LLMUnavailable,
    SchemaT,
)
from echotales.pipeline.llm.stub import StubProvider


class EscalationReason(StrEnum):
    """Why a request went to the expensive tier."""

    #: Local backend unreachable or not configured.
    LOCAL_UNAVAILABLE = "LOCAL_UNAVAILABLE"
    #: Local response would not validate against the schema.
    LOCAL_PARSE_FAILURE = "LOCAL_PARSE_FAILURE"
    #: Local answered, but below the confidence threshold.
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    #: The caller judged the case hard before asking (e.g. a DEFER from the gate).
    CALLER_REQUESTED = "CALLER_REQUESTED"
    #: Escalation budget exhausted; the local answer was kept.
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


#: Given a parsed response, report the model's own confidence in it.
#: Defaults to reading a `confidence` field when the schema has one.
ConfidenceFn = Callable[[object], float]


def default_confidence(value: object) -> float:
    """Read `confidence` off a response, treating its absence as certain.

    Absence means the schema makes no confidence claim, so there is nothing to
    escalate on -- a stage that wants confidence-based escalation must put the
    field in its schema.
    """
    conf = getattr(value, "confidence", None)
    return float(conf) if isinstance(conf, int | float) else 1.0


class LLMRouter:
    """Routes requests across tiers and records the accounting.

    `store` is optional so the router can be used in unit tests without a
    database, but in a real run it should always be supplied -- otherwise the
    escalation report has no data.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        store: Store | None = None,
        local: LLMProvider | None = None,
        api: LLMProvider | None = None,
        stub: LLMProvider | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store
        self._local = local
        self._api = api
        self._stub = stub or StubProvider()
        self._escalations = 0
        self._calls = 0

    # ---- provider construction ----------------------------------------

    @property
    def local(self) -> LLMProvider | None:
        if self._local is None and self.settings.llm_mode in (LLMMode.LOCAL, LLMMode.HYBRID):
            from echotales.pipeline.llm.ollama import OllamaProvider

            self._local = OllamaProvider(
                model=self.settings.llm_local_model,
                host=self.settings.llm_local_host,
                timeout=self.settings.llm_local_timeout,
                num_ctx=self.settings.llm_local_num_ctx,
            )
        return self._local

    @property
    def api(self) -> LLMProvider | None:
        if self._api is None and self.settings.llm_mode in (LLMMode.API, LLMMode.HYBRID):
            from echotales.pipeline.llm.anthropic import AnthropicProvider

            self._api = AnthropicProvider(
                model=self.settings.llm_api_model,
                api_key=self.settings.anthropic_api_key or None,
                timeout=self.settings.llm_api_timeout,
            )
        return self._api

    # ---- accounting ----------------------------------------------------

    def _record(
        self,
        request: LLMRequest,
        result: LLMResult[SchemaT] | None,
        provider: LLMProvider,
        *,
        escalated: bool,
        reason: str,
        ok: bool,
        novel_id: str,
        chapter: float | None,
    ) -> None:
        if self.store is None:
            return
        self.store.log_llm_call(
            stage=request.stage,
            tier=provider.tier,
            model=provider.model,
            escalated=escalated,
            escalation_reason=reason,
            prompt_tokens=result.prompt_tokens if result else 0,
            completion_tokens=result.completion_tokens if result else 0,
            latency_ms=result.latency_ms if result else 0,
            ok=ok,
            novel_id=novel_id,
            chapter=chapter,
        )

    @property
    def escalation_count(self) -> int:
        return self._escalations

    @property
    def call_count(self) -> int:
        return self._calls

    @property
    def escalation_rate(self) -> float:
        return self._escalations / self._calls if self._calls else 0.0

    # ---- the ladder ------------------------------------------------------

    def complete(
        self,
        request: LLMRequest,
        schema: type[SchemaT],
        *,
        force_escalate: bool = False,
        confidence_fn: ConfidenceFn = default_confidence,
        novel_id: str = "",
        chapter: float | None = None,
    ) -> LLMResult[SchemaT]:
        """Run a request, escalating if the cheap tier cannot handle it.

        `force_escalate` is how a caller says "I already know this one is
        hard" -- the resolver passes it for cases the conformal gate returned
        DEFER on, which is the single highest-value use of the expensive tier.
        """
        self._calls += 1
        mode = self.settings.llm_mode

        if mode is LLMMode.STUB:
            result = self._stub.complete(request, schema)
            self._record(
                request,
                result,
                self._stub,
                escalated=False,
                reason="",
                ok=True,
                novel_id=novel_id,
                chapter=chapter,
            )
            return result

        if mode is LLMMode.API:
            return self._run_api(
                request, schema, EscalationReason.CALLER_REQUESTED, novel_id, chapter, counted=False
            )

        if mode is LLMMode.LOCAL:
            provider = self.local
            if provider is None:
                raise LLMUnavailable("llm_mode=local but no local provider is configured")
            result = provider.complete(request, schema)
            self._record(
                request,
                result,
                provider,
                escalated=False,
                reason="",
                ok=True,
                novel_id=novel_id,
                chapter=chapter,
            )
            return result

        # ---- hybrid ----
        if force_escalate:
            return self._run_api(
                request, schema, EscalationReason.CALLER_REQUESTED, novel_id, chapter
            )

        provider = self.local
        reason: EscalationReason | None = None
        local_result: LLMResult[SchemaT] | None = None

        if provider is None or not provider.available():
            reason = EscalationReason.LOCAL_UNAVAILABLE
        else:
            try:
                local_result = provider.complete(request, schema)
            except LLMUnavailable:
                reason = EscalationReason.LOCAL_UNAVAILABLE
            except LLMError:
                reason = EscalationReason.LOCAL_PARSE_FAILURE
            else:
                if confidence_fn(local_result.value) < self.settings.escalation_confidence_threshold:
                    reason = EscalationReason.LOW_CONFIDENCE

        if reason is None:
            assert local_result is not None
            assert provider is not None
            self._record(
                request,
                local_result,
                provider,
                escalated=False,
                reason="",
                ok=True,
                novel_id=novel_id,
                chapter=chapter,
            )
            return local_result

        # Record the failed/low-confidence local attempt so the denominator is
        # honest -- an escalation rate that hides the attempts it escalated
        # from would overstate how well the cheap tier performs.
        if provider is not None:
            self._record(
                request,
                local_result,
                provider,
                escalated=False,
                reason=reason.value,
                ok=local_result is not None,
                novel_id=novel_id,
                chapter=chapter,
            )

        if self._escalations >= self.settings.max_escalations_per_run:
            if local_result is not None:
                return local_result
            raise LLMUnavailable(
                f"escalation budget of {self.settings.max_escalations_per_run} exhausted "
                f"and the local tier produced no usable answer for stage {request.stage!r}"
            )

        try:
            return self._run_api(request, schema, reason, novel_id, chapter)
        except LLMError:
            # The expensive tier failed too. A usable local answer beats none.
            if local_result is not None:
                return local_result
            raise

    def _run_api(
        self,
        request: LLMRequest,
        schema: type[SchemaT],
        reason: EscalationReason,
        novel_id: str,
        chapter: float | None,
        *,
        counted: bool = True,
    ) -> LLMResult[SchemaT]:
        provider = self.api
        if provider is None:
            raise LLMUnavailable("no API provider is configured")
        result = provider.complete(request, schema)
        result.escalated = counted
        result.escalation_reason = reason.value if counted else ""
        if counted:
            self._escalations += 1
        self._record(
            request,
            result,
            provider,
            escalated=counted,
            reason=reason.value if counted else "",
            ok=True,
            novel_id=novel_id,
            chapter=chapter,
        )
        return result

    def report(self) -> dict[str, object]:
        """Summary for the eval harness."""
        return {
            "mode": self.settings.llm_mode.value,
            "calls": self._calls,
            "escalations": self._escalations,
            "escalation_rate": round(self.escalation_rate, 4),
            "by_stage": self.store.escalation_stats() if self.store else [],
        }
