"""World-fact extraction: one model call per entity, any kind.

Shares its discipline with `resolve/appearance_extract.py`, deliberately and
by import rather than by copy -- targeted retrieval over the whole volume,
grounding every value against the passages that produced it, and dating each
fact to the chapter that attests it. Those three were each added in response
to a measured failure (a 20% sampling stride that missed the description it
existed to find; a model inventing "green robes" for a character introduced
as white-clothed; every fact claiming to hold from chapter 1), and they
apply to a location's terrain exactly as they applied to a character's hair.

**Evidence differs by kind, and that is the one real difference.** A person
is described where they are physically `PRESENT` -- a character discussed in
their absence is being gossiped about, not observed. A *place* has no such
distinction: "the South Border was a land of jagged peaks" describes the
South Border whether or not anyone is standing in it, and requiring presence
would discard almost every sentence that defines a region. So non-person
entities gather from any block that mentions them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from echotales.core.enums import (
    OBSERVER_READER,
    AssertedBy,
    Prominence,
    ReferenceMode,
    SpanType,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, DiscoursePosition
from echotales.core.store import Store
from echotales.pipeline.resolve.appearance_extract import (
    _MAX_PASSAGE_CHARS,
    _clean_values,
    attesting_chapter,
    eligible_prominence,
)
from echotales.pipeline.world.schema import KEY_HINTS, keys_for

log = logging.getLogger(__name__)

#: Span types that can define an entity. Wider than appearance's
#: narration-only rule: a clan's colours or a technique's effect is
#: routinely stated in exposition, which appearance deliberately excludes
#: because exposition rarely describes a face.
_INFORMATIVE = (
    SpanType.NARRATION_DESCRIPTION,
    SpanType.NARRATION_ACTION,
    SpanType.NARRATION_EXPOSITION,
)

_MAX_PASSAGES = 50

SYSTEM = (
    "You extract structured facts about a world and its characters from a "
    "translated Chinese web novel. Report only what the passages state or "
    "directly imply. Never invent a fact that is not there -- omit the key "
    "instead. Return only JSON."
)


class WorldFacts(BaseModel):
    """A flat key -> value bag, validated against the kind's vocabulary.

    Deliberately not one model per kind: the keys differ but the handling
    does not, and four near-identical schemas would drift apart the first
    time one of them gained a field.
    """

    facts: dict[str, str] = Field(default_factory=dict)


@dataclass(slots=True)
class WorldReport:
    novel_id: str
    entities_called: int = 0
    facts_written: int = 0
    facts_already_known: int = 0
    skipped_no_evidence: int = 0
    skipped_not_prominent: int = 0
    failures: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        kinds = ", ".join(f"{k}={v}" for k, v in sorted(self.by_kind.items())) or "none"
        return (
            f"{self.novel_id}: {self.facts_written:,} world facts from "
            f"{self.entities_called} model calls\n"
            f"  by kind: {kinds}\n"
            f"  already known: {self.facts_already_known}; "
            f"no evidence: {self.skipped_no_evidence}; "
            f"not prominent: {self.skipped_not_prominent}; "
            f"failed: {self.failures}"
        )


def gather_entity_evidence(
    store: Store,
    novel_id: str,
    target_id: str,
    *,
    require_present: bool,
    max_passages: int = _MAX_PASSAGES,
    per_chapter: int = 3,
) -> list[tuple[float, str]]:
    """`(chapter, passage)` pairs describing this entity.

    `require_present` is the person/place distinction: a character's facts
    come from scenes they are in, a place's from any mention of it. Capped
    per chapter so one dense chapter cannot crowd out the rest of the arc,
    the same reason `appearance_extract` caps.
    """
    modes = (
        {ReferenceMode.PRESENT}
        if require_present
        else set(ReferenceMode)
    )

    blocks_by_chapter: dict[float, set[int]] = {}
    for row in store.conn.execute(
        "SELECT DISTINCT chapter, block_index, reference_mode FROM mention "
        "WHERE novel_id=? AND target_id=? ORDER BY chapter, block_index",
        (novel_id, target_id),
    ):
        if ReferenceMode(row["reference_mode"]) in modes:
            blocks_by_chapter.setdefault(float(row["chapter"]), set()).add(
                int(row["block_index"])
            )

    out: list[tuple[float, str]] = []
    seen: set[str] = set()
    for chapter in sorted(blocks_by_chapter):
        blocks = blocks_by_chapter[chapter]
        taken = 0
        for span in store.get_spans(novel_id, chapter):
            if span.block_index not in blocks or span.span_type not in _INFORMATIVE:
                continue
            text = span.text.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append((chapter, text[:_MAX_PASSAGE_CHARS]))
            taken += 1
            if taken >= per_chapter:
                break
        if len(out) >= max_passages:
            break
    return out[:max_passages]


def build_prompt(label: str, kind: TargetKind, passages: list[str]) -> str:
    keys = keys_for(kind)
    lines = [f"{kind.value}: {label}", "", "Passages mentioning it:"]
    lines += [f"  - {p}" for p in passages]
    lines += ["", "Extract these facts as a JSON object under a 'facts' key:"]
    for key in keys:
        hint = KEY_HINTS.get(key, "")
        lines.append(f"  {key}: {hint}")
    lines += [
        "",
        "Include a key only if the passages state or clearly imply it. "
        "Omit anything you would have to guess.",
        "Keep each value short -- a phrase, not a paragraph.",
        'Return only JSON, shaped {"facts": {"key": "value", ...}}.',
    ]
    return "\n".join(lines)


def extract_entity_facts(
    novel_id: str,
    store: Store,
    entity: object,
    *,
    client: object,
) -> tuple[dict[str, str], list[tuple[float, str]]]:
    """`(facts, evidence)` for one entity, both possibly empty."""
    from echotales.pipeline.llm.tasks import Task

    kind: TargetKind = entity.kind  # type: ignore[attr-defined]
    keys = keys_for(kind)
    if not keys:
        return {}, []

    evidence = gather_entity_evidence(
        store,
        novel_id,
        str(entity.id),  # type: ignore[attr-defined]
        require_present=kind is TargetKind.SELF,
    )
    if not evidence:
        return {}, []

    label = str(entity.canonical_label)  # type: ignore[attr-defined]
    passages = [t for _c, t in evidence]

    try:
        result = client.complete(  # type: ignore[attr-defined]
            Task.WORLD_FACTS,
            build_prompt(label, kind, passages),
            WorldFacts,
            system=SYSTEM,
            novel_id=novel_id,
        )
    except Exception as exc:  # noqa: BLE001 - one entity must not sink the stage
        log.warning("world extraction failed for %s: %s", label, exc)
        raise

    raw = {
        key: str(value).strip()
        # Off-vocabulary keys are dropped, not coerced: an invented key
        # would flow into `state_of` output and into generation prompts
        # looking exactly like a real one.
        for key, value in (result.value.facts or {}).items()
        if key in keys and str(value).strip()
    }
    cleaned = _clean_values(raw, label, " ".join(passages).casefold())
    return cleaned, evidence


def extract_world(
    novel_id: str,
    store: Store,
    *,
    client: object,
    include_incidental: bool = False,
) -> WorldReport:
    """Extract structured facts for every entity the graph knows about.

    Non-person entities are never filtered by prominence: a novel may name
    its central mountain a dozen times and its protagonist five thousand,
    and the mountain still has to be drawable.
    """
    report = WorldReport(novel_id=novel_id)

    for entity in store.all_selves(novel_id):
        kind: TargetKind = entity.kind
        if not keys_for(kind):
            continue

        if kind is TargetKind.SELF and not include_incidental:
            if eligible_prominence(store, novel_id, entity) is Prominence.INCIDENTAL:
                report.skipped_not_prominent += 1
                continue

        try:
            facts, evidence = extract_entity_facts(
                novel_id, store, entity, client=client
            )
        except Exception:  # noqa: BLE001 - already logged
            report.failures += 1
            continue

        if not evidence:
            report.skipped_no_evidence += 1
            continue
        report.entities_called += 1
        if not facts:
            continue

        known = {
            (a.key, a.value)
            for a in store.get_attributes(kind, str(entity.id))
            if a.is_standing
        }

        for key, value in facts.items():
            if (key, value) in known:
                report.facts_already_known += 1
                continue
            at = attesting_chapter(value, evidence)
            if at is None:
                continue
            pos = DiscoursePosition(chapter=at, offset=0)
            store.add_attribute(
                novel_id,
                Attribute(
                    target_kind=kind,
                    target_id=str(entity.id),
                    key=key,
                    value=value,
                    interval=FuzzyInterval.open_ended(at, last_evidence=at),
                    learned_at_pos=pos,
                    observer_id=OBSERVER_READER,
                    asserted_by=AssertedBy.INFERENCE,
                    truth_status=TruthStatus.INFERRED,
                    evidence=f"attested ch{at:g}; {len(evidence)} passages"[:200],
                ),
            )
            report.facts_written += 1
            report.by_kind[kind.value] = report.by_kind.get(kind.value, 0) + 1

    store.conn.commit()
    return report
