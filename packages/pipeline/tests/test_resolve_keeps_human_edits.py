"""A re-resolve rebuilds the machine's decisions; it must not delete what a person made. The corrections log marks a
correction applied once and never replays it, so an entity or a mention retarget wiped here is lost while the log
still says applied, and a HUMAN speaker id is left pointing at nothing (audit: resolve.corrections_present)."""

from __future__ import annotations

from echotales.core.enums import (
    AliasType,
    AttributionMethod,
    BlockType,
    Provenance,
    ReferenceMode,
    ResolutionMethod,
    SpanType,
)
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.store import Store
from echotales.pipeline.resolve import resolve_novel


def _mention(mid: str, text: str, offset: int) -> Mention:
    return Mention(
        id=mid, novel_id="t", segment_id="s", chapter=1.0, offset=offset, text=text, alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT, block_index=0,
        local_group_id=mid, entity_label="character",
    )


def test_resolve_keeps_manual_entities_and_human_retargets() -> None:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(Chapter(novel_id="t", number=1.0, title="T", source_href="1.html",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text="filler " * 10)]))
    store.add_mentions([_mention("m1", "Fang Yuan", 0), _mention("m2", "Wang Ju Chi", 20)])
    store.conn.commit()
    resolve_novel("t", store)

    manual = "t:manual:abc123"
    store.add_self(Self(id=manual, novel_id="t", canonical_label="Eve", first_attested_pos=DiscoursePosition(chapter=1, offset=20)))
    human = next(m for m in store.get_mentions("t") if m.id == "m2")
    human.target_id, human.method, human.provenance = manual, ResolutionMethod.MANUAL, Provenance.HUMAN_AUTHORED
    store.add_mentions([human])
    store.add_spans([Span(id="t:1:0:0", novel_id="t", chapter=1.0, block_index=0, start=0, end=5, span_type=SpanType.DIALOGUE,
                          text="Hello", speaker_self_id=manual, attribution_method=AttributionMethod.HUMAN, confidence=1.0)])
    store.conn.commit()

    resolve_novel("t", store)

    assert store.get_self(manual) is not None
    kept = next(m for m in store.get_mentions("t") if m.id == "m2")
    assert kept.target_id == manual and kept.provenance is Provenance.HUMAN_AUTHORED
    machine = next(m for m in store.get_mentions("t") if m.id == "m1")
    assert machine.target_id and machine.target_id != manual
