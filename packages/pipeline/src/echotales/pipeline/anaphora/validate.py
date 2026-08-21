"""Validation of local mention groups (plans.md Section 6 Phase 5).

Grouping is cheap and slightly reckless; this pass is where precision comes
back. Every group is checked for violations that prove it cannot denote a
single entity, and a violating group is **split** rather than repaired --
guessing which half is correct would trade a detectable error for a silent one.

Three checks, each corresponding to a specific way the grouper goes wrong:

**Co-presence.** Two mentions simultaneously present doing different things
cannot be one persona. Note this operates on *personas*, never on selves: for a
clone or soul avatar simultaneous presence is expected and correct, which is
why the split is expressed at persona level and suppressed when a concurrent
binding exists.

**Layer boundary.** A group spanning a narrative-layer boundary (main into
dream) is split unconditionally. Dream-realm entities do not cluster with
main-timeline ones -- the protagonist living as someone else's son inside a
dream is a temporary dream persona, not a main-timeline identity.

**Cluster-count sanity.** When groups vastly outnumber the distinct rigid names
in a chapter, something upstream is fragmenting entities, and the chapter is
flagged for escalation rather than trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

from echotales.core.enums import ReferenceMode
from echotales.core.models import MAIN_TIMELINE, Mention, NarrativeSegment
from echotales.pipeline.anaphora.local import MentionGroup

#: Two PRESENT mentions closer than this, with different surface forms, are
#: treated as simultaneous.
_COPRESENCE_WINDOW = 200


class ViolationKind:
    CO_PRESENCE = "CO_PRESENCE"
    LAYER_BOUNDARY = "LAYER_BOUNDARY"
    CLUSTER_COUNT = "CLUSTER_COUNT"


@dataclass(slots=True)
class Violation:
    kind: str
    group_id: str
    detail: str
    mention_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationResult:
    groups: list[MentionGroup]
    violations: list[Violation] = field(default_factory=list)
    needs_escalation: bool = False

    @property
    def split_count(self) -> int:
        return sum(1 for v in self.violations if v.kind != ViolationKind.CLUSTER_COUNT)


def _segment_for(mention: Mention, segments: list[NarrativeSegment]) -> str:
    """Which timeline a mention sits in.

    Compares **block indices**, which is the unit segment bounds are expressed
    in. Using `mention.offset` here compares a character offset against a block
    index; the mismatch made most mentions match no segment at all, and the
    resulting empty timeline split against MAIN_TIMELINE produced thousands of
    phantom layer-boundary violations.
    """
    for segment in segments:
        lo = (segment.chapter_from, segment.offset_from)
        hi = (segment.chapter_to, segment.offset_to)
        if lo <= (mention.chapter, mention.block_index) <= hi:
            return segment.timeline_id
    # No containing segment: treat as the main timeline rather than as a
    # distinct unnamed one, so an unsegmented mention never triggers a split.
    return MAIN_TIMELINE


def check_layer_boundary(
    group: MentionGroup,
    mentions_by_id: dict[str, Mention],
    segments: list[NarrativeSegment],
) -> list[MentionGroup] | None:
    """Split a group that straddles two timelines.

    Unconditional: a dream persona and a main-timeline identity are different
    entities even when they share a name, and merging them lets dream-only
    facts leak onto the canonical timeline.
    """
    by_timeline: dict[str, list[str]] = {}
    for mention_id in group.mention_ids:
        mention = mentions_by_id.get(mention_id)
        if mention is None:
            continue
        by_timeline.setdefault(_segment_for(mention, segments), []).append(mention_id)

    if len(by_timeline) <= 1:
        return None

    return [
        MentionGroup(
            id=f"{group.id}.{i}",
            mention_ids=ids,
            label=group.label,
            timeline_id=timeline,
            confidence=group.confidence,
            rationale=[*group.rationale, "split_on_layer_boundary"],
        )
        for i, (timeline, ids) in enumerate(sorted(by_timeline.items()))
    ]


def check_co_presence(
    group: MentionGroup,
    mentions_by_id: dict[str, Mention],
    *,
    concurrent_personas: frozenset[str] = frozenset(),
) -> Violation | None:
    """Detect mentions that are simultaneously present but distinct.

    `concurrent_personas` lists labels known to have concurrent persona
    bindings -- clones, soul avatars, sustained parallel disguises. For those,
    simultaneous presence is the expected shape and must not trigger a split.
    That suppression is exactly why the penalty is defined between personas and
    never between selves.
    """
    if group.label in concurrent_personas:
        return None

    present = sorted(
        (
            m
            for mid in group.mention_ids
            if (m := mentions_by_id.get(mid)) is not None
            and m.reference_mode is ReferenceMode.PRESENT
        ),
        key=lambda m: (m.chapter, m.offset),
    )

    for a, b in pairwise(present):
        if a.chapter != b.chapter:
            continue
        if a.text == b.text:
            continue
        if b.offset - a.offset <= _COPRESENCE_WINDOW:
            return Violation(
                kind=ViolationKind.CO_PRESENCE,
                group_id=group.id,
                detail=(
                    f"{a.text!r} and {b.text!r} both present within "
                    f"{b.offset - a.offset} characters"
                ),
                mention_ids=[a.id, b.id],
            )
    return None


def split_on_co_presence(
    group: MentionGroup,
    mentions_by_id: dict[str, Mention],
) -> list[MentionGroup]:
    """Split a co-presence violation by surface form.

    Splitting by surface form rather than trying to decide which mentions were
    correctly grouped: the grouper's only evidence was the surface form, so
    that is the only axis along which its decision can be safely undone.
    """
    by_text: dict[str, list[str]] = {}
    for mention_id in group.mention_ids:
        mention = mentions_by_id.get(mention_id)
        if mention is None:
            continue
        by_text.setdefault(mention.text, []).append(mention_id)

    return [
        MentionGroup(
            id=f"{group.id}~{i}",
            mention_ids=ids,
            label=text,
            timeline_id=group.timeline_id,
            confidence=group.confidence * 0.9,
            rationale=[*group.rationale, "split_on_co_presence"],
        )
        for i, (text, ids) in enumerate(sorted(by_text.items()))
    ]


def validate_groups(
    groups: list[MentionGroup],
    mentions: list[Mention],
    segments: list[NarrativeSegment],
    *,
    concurrent_personas: frozenset[str] = frozenset(),
    cluster_ratio_threshold: float = 2.5,
) -> ValidationResult:
    """Run every check and split what fails."""
    mentions_by_id = {m.id: m for m in mentions}
    violations: list[Violation] = []
    out: list[MentionGroup] = []

    for group in groups:
        layer_split = check_layer_boundary(group, mentions_by_id, segments)
        if layer_split is not None:
            violations.append(
                Violation(
                    kind=ViolationKind.LAYER_BOUNDARY,
                    group_id=group.id,
                    detail=f"group spans {len(layer_split)} timelines",
                    mention_ids=list(group.mention_ids),
                )
            )
            candidates = layer_split
        else:
            candidates = [group]

        for candidate in candidates:
            violation = check_co_presence(
                candidate, mentions_by_id, concurrent_personas=concurrent_personas
            )
            if violation is None:
                out.append(candidate)
                continue
            violations.append(violation)
            out.extend(split_on_co_presence(candidate, mentions_by_id))

    # Cluster-count sanity: far more groups than distinct rigid names means
    # something upstream is fragmenting entities.
    distinct_names = {
        m.text for m in mentions if m.alias_type.name == "RIGID_NAME"
    }
    needs_escalation = bool(
        distinct_names and len(out) > len(distinct_names) * cluster_ratio_threshold
    )
    if needs_escalation:
        violations.append(
            Violation(
                kind=ViolationKind.CLUSTER_COUNT,
                group_id="",
                detail=(
                    f"{len(out)} groups for {len(distinct_names)} distinct names; "
                    "escalating rather than trusting"
                ),
            )
        )

    return ValidationResult(groups=out, violations=violations, needs_escalation=needs_escalation)
