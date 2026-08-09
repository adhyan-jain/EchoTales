"""Tier 4 of speaker attribution: contextual, LLM-backed (plans.md §6 Phase 4).

The three deterministic tiers all lean on context the chapter has already
built up -- a name introduced by an explicit attribution, an established
two-party alternation. The opening chapters of a book have none of that yet,
so a protagonist's very first lines of inner monologue land UNRESOLVED no
matter how obviously "him" they are to a reader who just met the character a
paragraph ago.

This tier is deliberately narrow and deliberately cheap: given the (short)
roster of characters established so far and the text around one still-
unresolved line, ask a small model which of them it belongs to, or none. It is
not asked to discover a new character -- that is mention detection's job, not
this one -- so an answer outside the roster is a hallucination and is
discarded exactly like `attribution.py`'s regex tiers already discard a
capitalised token that is not `_known`.

Gated to a small chapter cutoff (`runner.py::attribute_novel`'s
`llm_chapter_cutoff`) rather than run everywhere: past the opening chapters
the deterministic tiers already carry a built-up cast and alternation history,
so the marginal lines an LLM pass would resolve stop being worth a call per
line. Cold start is a startup cost, not a standing one.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from echotales.core.enums import AttributionMethod, SpanType
from echotales.core.models import Span
from echotales.pipeline.speakers.attribution import Attribution, _known

SYSTEM = (
    "You identify who speaks or thinks one line from a translated web novel. "
    "Answer only with a name from the roster you are given, exactly as "
    "spelled there, or an empty string if none of them fit -- never invent a "
    "name that is not on the roster, and never guess when unsure."
)


class ContextualAttributionResponse(BaseModel):
    speaker: str = Field(
        default="", description="a name from the roster, exact spelling, or empty if none fit"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def attribute_contextual(
    span: Span,
    *,
    preceding: str,
    following: str,
    known_names: frozenset[str],
    roster: list[str],
    client: object,
    novel_id: str = "",
    chapter: float | None = None,
) -> Attribution | None:
    """Ask the model which established character this line belongs to.

    Returns `None` on no answer, low confidence, or a name off the roster --
    all of which leave the span exactly as UNRESOLVED as it already was, so
    this tier can only add attributions, never remove or override one.
    """
    if not roster:
        return None

    from echotales.pipeline.llm.tasks import Task

    kind = "thinks" if span.span_type is SpanType.INNER_MONOLOGUE else "says"
    prompt = (
        f"Characters established so far in this novel: {', '.join(roster[:60])}\n\n"
        f"...{preceding}\n"
        f"[LINE] {span.text}\n"
        f"{following}...\n\n"
        f"Who {kind} the line marked [LINE]?"
    )

    result = client.complete(  # type: ignore[attr-defined]
        Task.SPEAKER_ATTRIBUTION,
        prompt,
        ContextualAttributionResponse,
        system=SYSTEM,
        novel_id=novel_id,
        chapter=chapter,
    )
    name = result.value.speaker.strip()
    if not name or result.value.confidence < 0.5 or not _known(name, known_names):
        return None

    return Attribution(
        span_id=span.id,
        speaker=name,
        method=AttributionMethod.CONTEXTUAL_LLM,
        confidence=min(result.value.confidence, 0.65),
        evidence="llm: cold-start roster match",
    )
