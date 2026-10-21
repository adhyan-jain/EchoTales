"""The reader-gold scorer: speakers matched by name, unnamed slots never right, scare-quote spans counted."""

from __future__ import annotations

import json
from pathlib import Path

from echotales.core.enums import BlockType, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Self, Span
from echotales.core.store import Store
from echotales.pipeline.eval import reader_gold as g


def _store(speakers: dict[int, str | None]) -> Store:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    store.add_chapter(
        Chapter(
            novel_id="n", number=1.0, title="T", source_href="a",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text="“Hello.” She smiled."),
                    Block(index=1, block_type=BlockType.PROSE, text="“Bye,” said Tom. A “scare” quote.")],
        )
    )
    spans = [
        Span(id="s0", novel_id="n", chapter=1.0, block_index=0, start=0, end=8, span_type=SpanType.DIALOGUE,
             text="“Hello.”", speaker_self_id=speakers.get(0)),
        Span(id="s1", novel_id="n", chapter=1.0, block_index=1, start=0, end=6, span_type=SpanType.DIALOGUE,
             text="“Bye,”", speaker_self_id=speakers.get(1)),
        Span(id="s2", novel_id="n", chapter=1.0, block_index=1, start=19, end=26, span_type=SpanType.DIALOGUE,
             text="“scare”", speaker_self_id="Tom"),
    ]
    store.add_spans(spans)
    store.add_self(
        Self(id="loc1", novel_id="n", canonical_label="Chanis Gate",
             first_attested_pos=DiscoursePosition(chapter=1, offset=0), kind=TargetKind.SELF)
    )
    return store


def _gold(tmp_path: Path) -> g.GoldChapter:
    path = tmp_path / "gold.json"
    path.write_text(json.dumps({
        "novel_id": "n", "chapter": 1, "provenance": "model", "confirmed": False,
        "characters": [
            {"id": "tom", "name": "Tom", "kind": "person", "aliases": []},
            {"id": "she", "name": "Alice", "kind": "person", "aliases": ["She"]},
        ],
        "non_characters": [{"name": "Chanis Gate", "kind": "location"}],
        "age_facts": [{"character": "she", "value": 17, "quote": "x"}],
        "lines": [{"block": 0, "q": 0, "speaker": "she"}, {"block": 1, "q": 0, "speaker": "tom"}],
    }), encoding="utf-8")
    return g.load_reader_gold(path)


def test_correct_names_score_and_scare_quote_is_false_dialogue(tmp_path: Path) -> None:
    score = g.score_speakers(_gold(tmp_path), _store({0: "Alice", 1: "Tom"}))
    assert (score.correct, score.total) == (2, 2)
    assert score.false_dialogue == 1  # the "scare" span covers no gold line


def test_anonymous_slot_is_never_correct(tmp_path: Path) -> None:
    score = g.score_speakers(_gold(tmp_path), _store({0: "n:anon:1:1", 1: "Tom"}))
    assert (score.correct, score.total) == (1, 2)
    assert "expected she" in score.misses[0]


def test_unclosed_multi_paragraph_quote_is_found() -> None:
    assert [m.start() for m in g._QUOTE.finditer("“I like fair trade.\nsecond")] == [0]


def test_place_typed_as_person_is_a_kind_error(tmp_path: Path) -> None:
    score = g.score_kinds(_gold(tmp_path), _store({}))
    assert (score.correct, score.total) == (0, 1)


def test_missing_age_is_a_miss(tmp_path: Path) -> None:
    score = g.score_ages(_gold(tmp_path), _store({}))
    assert (score.correct, score.total) == (0, 1)
