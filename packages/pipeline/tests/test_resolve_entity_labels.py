"""Tests for auto-flagging entities founded on non-"character" NER labels.

Pattern found reviewing real pipeline output across three novels: NER labels
a mention "location"/"organization" (Gu Yue Village, the Magician tarot
title, Seoul), the commonness filter deliberately doesn't apply to those
labels (see `mentions/runner.py`'s `rejected()` docstring -- it was already
proven to over-delete real entities like a clan name or a plot item), and
`resolve/runner.py` always mints a `Self` regardless of kind since there is
no non-person `TargetKind`. The result: spurious "characters" pollute the
voice-cast list. This doesn't delete anything (that regressed once already);
it just leaves an automatic review flag.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
from echotales.core.models import Block, Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.corrections import CorrectionLog
from echotales.pipeline.resolve import resolve_novel


def _mention(mid: str, text: str, *, offset: int, group: str, label: str | None) -> Mention:
    return Mention(
        id=mid,
        novel_id="t",
        segment_id="s",
        chapter=1.0,
        offset=offset,
        text=text,
        alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=ReferenceMode.PRESENT,
        block_index=0,
        local_group_id=group,
        entity_label=label,
    )


def _store_with_chapter() -> Store:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text="filler " * 10)],
        )
    )
    return store


class TestAutoFlagNonCharacterEntities:
    def test_location_labeled_entity_gets_flagged(self) -> None:
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Gu Yue Village", offset=0, group="g1", label="location")]
        )
        store.conn.commit()

        with tempfile.TemporaryDirectory() as d:
            clog = CorrectionLog(Path(d) / "t.jsonl")
            resolve_novel("t", store, corrections_log=clog)
            flags = _read_jsonl(Path(d) / "t.jsonl")

        assert len(flags) == 1
        assert flags[0].payload["source"] == "agent:pipeline"
        assert "location" in flags[0].payload["note"]

    def test_character_labeled_entity_is_not_flagged(self) -> None:
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Fang Yuan", offset=0, group="g1", label="character")]
        )
        store.conn.commit()

        with tempfile.TemporaryDirectory() as d:
            clog = CorrectionLog(Path(d) / "t.jsonl")
            resolve_novel("t", store, corrections_log=clog)
            flags = _read_jsonl(Path(d) / "t.jsonl")

        assert flags == []

    def test_mixed_signal_within_group_is_not_flagged(self) -> None:
        """One mention labeled "character" is enough to stay quiet -- a false
        flag is a worse outcome than a missed one for a one-time review note."""
        store = _store_with_chapter()
        store.add_mentions(
            [
                _mention("m1", "Ancient Moon", offset=0, group="g1", label="location"),
                _mention("m2", "Ancient Moon", offset=20, group="g1", label="character"),
            ]
        )
        store.conn.commit()

        with tempfile.TemporaryDirectory() as d:
            clog = CorrectionLog(Path(d) / "t.jsonl")
            resolve_novel("t", store, corrections_log=clog)
            flags = _read_jsonl(Path(d) / "t.jsonl")

        assert flags == []

    def test_no_corrections_log_means_no_flagging(self) -> None:
        """Default-off: every existing caller that doesn't pass corrections_log
        keeps today's behaviour exactly, including in tests elsewhere."""
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Gu Yue Village", offset=0, group="g1", label="location")]
        )
        store.conn.commit()
        report = resolve_novel("t", store)
        assert report.created == 1


def _read_jsonl(path: Path):
    from echotales.pipeline.corrections import Correction
    import json

    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(Correction.from_json(json.loads(line)))
    return out
