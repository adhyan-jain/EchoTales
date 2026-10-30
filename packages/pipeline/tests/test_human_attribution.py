"""A reviewer's speaker decision must survive every later stage (audit 2026-10-31, blockers B1 and B2).

Before: `_apply_reassign_speaker` wrote EXPLICIT and left the reader's confidence of 0.0, so the voice stage voiced the
reviewed line as "unconfirmed", the review queue listed it again, and a speakers or reader re-run overwrote it with
the correction already marked applied. The method HUMAN is the one marker no pipeline stage writes.
"""

from __future__ import annotations

import time

from echotales.core.enums import AttributionMethod, BlockType, Prominence, SpanType
from echotales.core.models import Block, Chapter, DiscoursePosition, Self, Span
from echotales.core.store import Store
from echotales.pipeline import review_gate as rg
from echotales.pipeline.corrections import Correction, CorrectionLog, CorrectionType, apply_pending
from echotales.pipeline.speakers.runner import attribute_novel

NOVEL = "t"
TEXT = '"Who goes there?" a guard shouted.'


def _store() -> Store:
    store = Store(":memory:")
    store.add_novel(NOVEL, "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id=NOVEL, number=1.0, title="One", source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text=TEXT)],
        )
    )
    store.add_self(
        Self(id=f"{NOVEL}:self1", novel_id=NOVEL, canonical_label="Fang Yuan", prominence=Prominence.RECURRING,
             first_attested_pos=DiscoursePosition(chapter=1, offset=0))
    )
    # What the reader leaves behind for a line it could not place: unnamed, confidence 0.0.
    store.add_spans([
        Span(id=f"{NOVEL}:1:0:0", novel_id=NOVEL, chapter=1.0, block_index=0, start=0, end=len(TEXT),
             span_type=SpanType.DIALOGUE, text=TEXT, attribution_method=AttributionMethod.UNRESOLVED, confidence=0.0)
    ])
    store.conn.commit()
    return store


def _assign(store: Store, tmp_path, **payload) -> None:
    log = CorrectionLog(tmp_path / "t.jsonl")
    log.add(Correction(novel_id=NOVEL, type=CorrectionType.REASSIGN_SPEAKER,
                       payload={"span_id": f"{NOVEL}:1:0:0", "chapter": 1.0, **payload}))
    assert apply_pending(store, log)["count"] == 1


def test_reviewed_line_is_settled_in_the_queue(tmp_path) -> None:
    store = _store()
    assert [i["reason"] for i in rg.speaker_queue(store, NOVEL)["items"]] == ["unnamed"]

    _assign(store, tmp_path, speaker_id=f"{NOVEL}:self1")

    span = store.get_spans(NOVEL, 1.0)[0]
    assert (span.attribution_method, span.confidence) == (AttributionMethod.HUMAN, 1.0)
    assert rg.speaker_queue(store, NOVEL)["items"] == []


def test_reviewed_anonymous_slot_is_settled_too(tmp_path) -> None:
    store = _store()
    _assign(store, tmp_path, anon_slot=2)
    assert rg.speaker_queue(store, NOVEL)["items"] == []


def test_clearing_a_line_returns_it_to_the_queue(tmp_path) -> None:
    store = _store()
    _assign(store, tmp_path, speaker_id=f"{NOVEL}:self1")
    # `apply_pending` seeds the event seq from the millisecond clock; two applies inside one ms collide, which a
    # reviewer clicking by hand never does.
    time.sleep(0.01)
    _assign(store, tmp_path, speaker_id=None)

    span = store.get_spans(NOVEL, 1.0)[0]
    assert (span.attribution_method, span.confidence) == (AttributionMethod.UNRESOLVED, 0.0)
    assert [i["reason"] for i in rg.speaker_queue(store, NOVEL)["items"]] == ["unnamed"]


def test_speakers_rerun_keeps_the_reviewers_decision(tmp_path) -> None:
    store = _store()
    _assign(store, tmp_path, speaker_id=f"{NOVEL}:self1")

    attribute_novel(NOVEL, store)

    span = store.get_spans(NOVEL, 1.0)[0]
    assert span.speaker_self_id == f"{NOVEL}:self1"
    assert (span.attribution_method, span.confidence) == (AttributionMethod.HUMAN, 1.0)
