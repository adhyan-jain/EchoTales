"""LLM adjudication of deferred cases (plans.md §6 Phase 6).

The expensive tier, reserved for the residual the deterministic path could not
settle. Per the measured budget this is the *only* affordable way to use a
model at mention granularity: a per-mention pass over the corpus is 34.5 hours
locally, while 2-5% of mentions is well under two.

The prompt gives the model exactly what the scorer could not weigh: the entity
wiki summaries for the specific candidates, the surrounding text, and the
scorer's own top features. Handing over the feature contributions matters --
the model is being asked to adjudicate a close call, not to redo the work, and
telling it *why* the call was close focuses it on the disagreement.

`NEW` is always an available answer. An adjudicator that must pick from the
candidate list will confidently link a genuinely new character to whoever
happens to be nearest.
"""

from __future__ import annotations

from dataclasses import dataclass

from echotales.core.enums import Decision, ResolutionMethod
from echotales.core.models import Candidate, ResolutionOutcome
from echotales.pipeline.llm import LLMRequest, LLMRouter
from echotales.pipeline.resolve.retrieve import EntityProfile
from echotales.pipeline.resolve.score import ScoringModel
from echotales.pipeline.resolve.wiki import build_focused_wiki
from pydantic import BaseModel, Field

SYSTEM = (
    "You resolve character identity in translated web novels. "
    "Characters routinely use many names: birth names, titles, code names, "
    "disguises and epithets. Two names with nothing in common may be one "
    "person; two identical titles may be different people who held it at "
    "different times. "
    "Answer NEW when the mention is a character not in the candidate list. "
    "Answer UNCERTAIN rather than guessing when the evidence does not settle it."
)


class AdjudicationResponse(BaseModel):
    """Structured verdict from the model."""

    decision: str = Field(description="one of LINK, NEW, UNCERTAIN")
    target_id: str = Field(default="", description="candidate id when decision is LINK")
    reason: str = Field(default="", description="the evidence that decided it")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


@dataclass(slots=True)
class AdjudicationRequest:
    group_id: str
    surface: str
    context: str
    chapter: float
    candidates: list[Candidate]


def _render_candidates(
    candidates: list[Candidate],
    profiles: dict[str, EntityProfile],
    model: ScoringModel,
) -> str:
    """List candidates with the scorer's reasoning attached."""
    lines: list[str] = []
    for i, candidate in enumerate(candidates, start=1):
        top = model.explain(candidate.evidence)[:3]
        drivers = ", ".join(f"{name}={value:+.2f}" for name, value in top if value)
        lines.append(
            f"{i}. id={candidate.target_id}  label={candidate.label!r}  "
            f"p={candidate.probability:.3f}"
            + (f"  [{drivers}]" if drivers else "")
        )
    return "\n".join(lines)


def adjudicate(
    request: AdjudicationRequest,
    router: LLMRouter,
    profiles: dict[str, EntityProfile],
    model: ScoringModel,
    *,
    novel_id: str = "",
) -> ResolutionOutcome:
    """Ask the model to settle one deferred case.

    Escalated unconditionally (`force_escalate`): the gate already established
    that the cheap path could not decide this, so re-running a weak model on it
    would spend budget to reproduce the same deferral.
    """
    wiki = build_focused_wiki(profiles, [c.target_id for c in request.candidates])
    prompt = (
        f"Chapter {request.chapter:g}.\n\n"
        f"A character is referred to as {request.surface!r}.\n\n"
        f"Surrounding text:\n{request.context[:1200]}\n\n"
        f"Established characters that might match:\n{wiki}\n\n"
        f"Automatic scorer's ranking:\n"
        f"{_render_candidates(request.candidates, profiles, model)}\n\n"
        "Which established character does this mention refer to, if any?"
    )

    result = router.complete(
        LLMRequest(stage="adjudicate", prompt=prompt, system=SYSTEM, max_tokens=500),
        AdjudicationResponse,
        force_escalate=True,
        novel_id=novel_id,
        chapter=request.chapter,
    )
    response = result.value

    decision_text = response.decision.strip().upper()
    if decision_text == "LINK" and response.target_id:
        matched = next(
            (c for c in request.candidates if c.target_id == response.target_id), None
        )
        if matched is not None:
            return ResolutionOutcome(
                group_id=request.group_id,
                decision=Decision.LINK,
                target_kind=matched.target_kind,
                target_id=matched.target_id,
                probability=response.confidence,
                method=ResolutionMethod.LLM_ADJUDICATED,
                candidates=request.candidates,
                rationale=response.reason,
            )
        # A target id that is not in the candidate list is a hallucination, and
        # trusting it would create a link to an entity nobody proposed.
        return ResolutionOutcome(
            group_id=request.group_id,
            decision=Decision.DEFER,
            method=ResolutionMethod.LLM_ADJUDICATED,
            candidates=request.candidates,
            rationale=f"model returned unknown target_id {response.target_id!r}",
        )

    if decision_text == "NEW":
        return ResolutionOutcome(
            group_id=request.group_id,
            decision=Decision.NEW,
            probability=response.confidence,
            method=ResolutionMethod.LLM_ADJUDICATED,
            candidates=request.candidates,
            rationale=response.reason,
        )

    return ResolutionOutcome(
        group_id=request.group_id,
        decision=Decision.DEFER,
        method=ResolutionMethod.LLM_ADJUDICATED,
        candidates=request.candidates,
        rationale=response.reason or "model was uncertain",
    )
