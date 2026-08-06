"""Pronoun resolution (plans.md §6 Phase 5, revised).

**No fastcoref.** It is trained on OntoNotes-style English literary prose and
degrades badly on translated web fiction: the register, the sentence rhythm and
above all the naming conventions are outside its distribution, so its clusters
have to be discarded more often than they can be used.

The replacement is a five-way strategy, ordered so that the cheapest and most
reliable route is tried first and a model is consulted only for genuinely
ambiguous stretches:

1. **Attribution adjacency** (deterministic, no model). A pronoun immediately
   following a clear dialogue attribution refers to that speaker. This is the
   single most common shape in dialogue-heavy fiction and needs no inference.
2. **Honorific-only exchanges** resolve through the relationship graph, not a
   pronoun model. "Senior said / Junior replied" carries no pronoun at all; the
   referents come from who stands in that relation to the speaker.
3. **Inner monologue** first-person resolves to the POV character automatically.
4. **Crowd reactions** are tagged `UNATTRIBUTED_CHORUS` and left alone.
   Resolving them invents attributions that propagate into voice casting.
5. **Everything else** goes to the model, batched **per paragraph** with the
   scene's active character list supplied.

Paragraph batching rather than chapter batching is deliberate: a pronoun's
antecedent is nearly always within a paragraph or two, and a chapter-sized
prompt buries the local evidence while costing far more context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from echotales.core.enums import AttributionMethod, SpanType
from echotales.core.models import Mention, Span
from echotales.pipeline.anaphora.local import find_pronouns, resolve_pronoun
from pydantic import BaseModel, Field

#: Speech verbs, for the adjacency rule.
_SPEECH_VERBS = (
    r"said|replied|answered|asked|shouted|yelled|screamed|roared|whispered|"
    r"murmured|muttered|mumbled|called|cried|exclaimed|declared|continued|added|"
    r"responded|retorted|snapped|laughed|chuckled|sighed|sneered|scoffed|snorted"
)

_NAME = r"[A-Z][\w’'\-]*(?:\s+[A-Z][\w’'\-]*){0,3}"

#: "Wu An said ... he then added" -- the attribution then a pronoun subject.
_ATTRIBUTION_THEN_PRONOUN = re.compile(
    rf"\b(?P<name>{_NAME})\s+(?:{_SPEECH_VERBS})\b[^.!?]{{0,120}}?[.!?]\s*"
    rf"(?P<pronoun>He|She|They)\b"
)

#: A pronoun subject with a speech verb, needing an antecedent.
_PRONOUN_SPEECH = re.compile(
    rf"\b(?P<pronoun>he|she|they)\s+(?:\w+\s+){{0,2}}?(?:{_SPEECH_VERBS})\b",
    re.IGNORECASE,
)

#: Honorific-only address, carrying a relation rather than a name.
_HONORIFIC_SPEAKER = re.compile(
    r"\b(?P<role>Senior|Junior|Elder|Master|Senior Brother|Junior Brother|"
    r"Senior Sister|Junior Sister|Martial Uncle|Father|Mother|Teacher|Sunbae|Hyung)\b"
    r"\s+(?:" + _SPEECH_VERBS + r")\b",
    re.IGNORECASE,
)

_FIRST_PERSON = re.compile(r"\b(?:I|me|my|mine|myself)\b")


class CorefRoute(StrEnum):
    """Which strategy resolved a pronoun."""

    ATTRIBUTION_ADJACENCY = "ATTRIBUTION_ADJACENCY"
    RELATIONSHIP_GRAPH = "RELATIONSHIP_GRAPH"
    POV_FIRST_PERSON = "POV_FIRST_PERSON"
    UNATTRIBUTED_CHORUS = "UNATTRIBUTED_CHORUS"
    NEAREST_ANTECEDENT = "NEAREST_ANTECEDENT"
    LLM_PARAGRAPH = "LLM_PARAGRAPH"
    UNRESOLVED = "UNRESOLVED"


@dataclass(slots=True)
class CorefResolution:
    pronoun: str
    offset: int
    referent: str | None
    route: CorefRoute
    confidence: float
    evidence: str = ""


@dataclass(slots=True)
class CorefReport:
    resolved: int = 0
    unresolved: int = 0
    llm_paragraphs: int = 0
    by_route: dict[str, int] = field(default_factory=dict)

    @property
    def coverage(self) -> float:
        total = self.resolved + self.unresolved
        return self.resolved / total if total else 0.0

    def record(self, resolution: CorefResolution) -> None:
        self.by_route[resolution.route.value] = self.by_route.get(resolution.route.value, 0) + 1
        if resolution.referent or resolution.route is CorefRoute.UNATTRIBUTED_CHORUS:
            self.resolved += 1
        else:
            self.unresolved += 1


# ---------------------------------------------------------------------------
# 1. Attribution adjacency -- deterministic, no model
# ---------------------------------------------------------------------------


def resolve_by_attribution(text: str, base_offset: int = 0) -> list[CorefResolution]:
    """Link pronouns that directly follow a dialogue attribution.

    The highest-yield deterministic rule in dialogue-heavy prose, and it costs
    nothing: the antecedent is stated one clause earlier.
    """
    out: list[CorefResolution] = []
    for match in _ATTRIBUTION_THEN_PRONOUN.finditer(text):
        out.append(
            CorefResolution(
                pronoun=match.group("pronoun"),
                offset=base_offset + match.start("pronoun"),
                referent=match.group("name"),
                route=CorefRoute.ATTRIBUTION_ADJACENCY,
                confidence=0.9,
                evidence=match.group(0)[:80],
            )
        )
    return out


# ---------------------------------------------------------------------------
# 2. Honorific-only exchanges -- relationship graph, not a pronoun model
# ---------------------------------------------------------------------------


def resolve_by_relationship(
    text: str,
    speaker: str | None,
    relationships: dict[tuple[str, str], str],
    *,
    base_offset: int = 0,
) -> list[CorefResolution]:
    """Resolve role-only speakers through the relationship graph.

    "Senior said" names nobody. The referent is whoever stands in that relation
    to the current speaker, which is a graph lookup rather than a coreference
    problem -- and attempting it as coreference is why role-only exchanges
    defeat generic models.

    `relationships` maps `(speaker, role)` to the referent's identifier.
    """
    if not speaker:
        return []
    out: list[CorefResolution] = []
    for match in _HONORIFIC_SPEAKER.finditer(text):
        role = match.group("role").strip().casefold()
        referent = relationships.get((speaker, role))
        if referent is None:
            continue
        out.append(
            CorefResolution(
                pronoun=match.group("role"),
                offset=base_offset + match.start("role"),
                referent=referent,
                route=CorefRoute.RELATIONSHIP_GRAPH,
                confidence=0.8,
                evidence=f"{role} of {speaker}",
            )
        )
    return out


# ---------------------------------------------------------------------------
# 3 & 4. POV first person, and crowd reactions
# ---------------------------------------------------------------------------


def resolve_first_person(
    span: Span, pov_holder: str | None
) -> list[CorefResolution]:
    """First person inside inner monologue belongs to the POV character."""
    if span.span_type is not SpanType.INNER_MONOLOGUE or not pov_holder:
        return []
    return [
        CorefResolution(
            pronoun=match.group(0),
            offset=span.start + match.start(),
            referent=pov_holder,
            route=CorefRoute.POV_FIRST_PERSON,
            confidence=0.85,
        )
        for match in _FIRST_PERSON.finditer(span.text)
    ]


def mark_chorus(span: Span) -> list[CorefResolution]:
    """Tag crowd reactions and attempt nothing further.

    Resolving an unattributed crowd line invents an attribution, and that
    invention propagates downstream into voice casting where it becomes
    audible.
    """
    if span.span_type is not SpanType.CROWD_REACTION:
        return []
    return [
        CorefResolution(
            pronoun="",
            offset=span.start,
            referent=None,
            route=CorefRoute.UNATTRIBUTED_CHORUS,
            confidence=1.0,
        )
    ]


# ---------------------------------------------------------------------------
# 5. Model fallback -- per paragraph, with the active cast
# ---------------------------------------------------------------------------


class PronounLink(BaseModel):
    pronoun: str = Field(description="the pronoun as written")
    occurrence: int = Field(default=1, description="1-based index of this pronoun in the passage")
    referent: str = Field(description="which listed character it refers to")


class CorefResponse(BaseModel):
    links: list[PronounLink] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


_COREF_SYSTEM = (
    "You resolve pronouns in translated Chinese and Korean web-novel prose. "
    "You are given the characters currently present in the scene. "
    "For each unresolved pronoun, say which of those characters it refers to. "
    "If a pronoun does not refer to any listed character, omit it rather than "
    "guessing."
)


def resolve_paragraph_with_model(
    text: str,
    active_cast: list[str],
    client: object,
    *,
    base_offset: int = 0,
    novel_id: str = "",
    chapter: float | None = None,
) -> list[CorefResolution]:
    """Resolve an ambiguous paragraph's pronouns with the model.

    Batched at paragraph level. A chapter-sized prompt buries the local
    evidence a pronoun actually depends on and costs far more context for a
    worse answer.
    """
    from echotales.pipeline.llm.tasks import Task

    if not active_cast:
        return []

    pronouns = find_pronouns(text)
    if not pronouns:
        return []

    cast = ", ".join(sorted(set(active_cast))[:30])
    prompt = (
        f"Characters currently in this scene: {cast}\n\n"
        f"Passage:\n{text[:2000]}\n\n"
        "Given these characters are in this scene, who does each pronoun refer to?"
    )

    result = client.complete(  # type: ignore[attr-defined]
        Task.COREFERENCE,
        prompt,
        CorefResponse,
        system=_COREF_SYSTEM,
        novel_id=novel_id,
        chapter=chapter,
    )
    response = result.value

    # Map each returned link back onto a concrete offset by counting
    # occurrences; a model cannot be trusted to report character positions.
    out: list[CorefResolution] = []
    cast_set = {c.casefold() for c in active_cast}
    for link in response.links:
        if link.referent.casefold() not in cast_set:
            # A referent outside the supplied cast is a hallucination.
            continue
        matches = [
            offset
            for surface, offset, _, _ in pronouns
            if surface.casefold() == link.pronoun.casefold()
        ]
        index = max(link.occurrence - 1, 0)
        if index >= len(matches):
            continue
        out.append(
            CorefResolution(
                pronoun=link.pronoun,
                offset=base_offset + matches[index],
                referent=link.referent,
                route=CorefRoute.LLM_PARAGRAPH,
                confidence=response.confidence or 0.6,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def needs_model(text: str, resolved_offsets: set[int]) -> bool:
    """Whether a paragraph still has pronoun subjects worth a model call.

    Only pronouns in *subject-of-speech* position matter enough to spend a
    call: an unresolved possessive rarely changes a downstream decision, while
    an unresolved speaker does.
    """
    for match in _PRONOUN_SPEECH.finditer(text):
        if match.start("pronoun") not in resolved_offsets:
            return True
    return False


def resolve_span_pronouns(
    span: Span,
    mentions: list[Mention],
    *,
    pov_holder: str | None = None,
    speaker: str | None = None,
    relationships: dict[tuple[str, str], str] | None = None,
    active_cast: list[str] | None = None,
    client: object | None = None,
    novel_id: str = "",
) -> list[CorefResolution]:
    """Run the five-way strategy over one span, cheapest route first."""
    chorus = mark_chorus(span)
    if chorus:
        return chorus

    out: list[CorefResolution] = []
    out.extend(resolve_first_person(span, pov_holder))
    out.extend(resolve_by_attribution(span.text, span.start))
    out.extend(
        resolve_by_relationship(span.text, speaker, relationships or {}, base_offset=span.start)
    )

    resolved = {r.offset for r in out}

    # Deterministic nearest-antecedent for anything still open.
    for surface, offset, gender, number in find_pronouns(span.text, span.start):
        if offset in resolved:
            continue
        found = resolve_pronoun(offset, gender, number, mentions)
        if found is None:
            continue
        antecedent, confidence, _ = found
        out.append(
            CorefResolution(
                pronoun=surface,
                offset=offset,
                referent=antecedent.text,
                route=CorefRoute.NEAREST_ANTECEDENT,
                confidence=confidence,
            )
        )
        resolved.add(offset)

    # Model only for paragraphs that still have an unresolved speaker.
    if client is not None and active_cast and needs_model(span.text, {r - span.start for r in resolved}):
        out.extend(
            resolve_paragraph_with_model(
                span.text,
                active_cast,
                client,
                base_offset=span.start,
                novel_id=novel_id,
                chapter=span.chapter,
            )
        )

    return out


def attribution_method_for(route: CorefRoute) -> AttributionMethod:
    """Map a coreference route onto the attribution method it implies."""
    return {
        CorefRoute.ATTRIBUTION_ADJACENCY: AttributionMethod.PROXIMAL,
        CorefRoute.RELATIONSHIP_GRAPH: AttributionMethod.EXPLICIT,
        CorefRoute.POV_FIRST_PERSON: AttributionMethod.POV_INFERRED,
        CorefRoute.UNATTRIBUTED_CHORUS: AttributionMethod.UNATTRIBUTED_CHORUS,
        CorefRoute.NEAREST_ANTECEDENT: AttributionMethod.PROXIMAL,
        CorefRoute.LLM_PARAGRAPH: AttributionMethod.CONTEXTUAL_LLM,
        CorefRoute.UNRESOLVED: AttributionMethod.UNRESOLVED,
    }[route]
