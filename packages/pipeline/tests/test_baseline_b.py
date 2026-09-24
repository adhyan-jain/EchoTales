"""Tests for Baseline B (dual-LLM memorisation).

`materialize_mentions` failed **three times in a row** on 2026-09-24, each time
*after* a completed 433-second LLM run — `Store.add_mention` (the API is
`add_mentions`), then `SpanType.NARRATION` (it is `NARRATION_ACTION`), then
`Provenance.MODEL` (that is `eval.gold.Provenance`; the `Mention` field wants
`core.enums.Provenance.MACHINE`). None of it needed a model to catch. These
tests run the insertion path with no Ollama, so the next wrong enum costs a
second instead of seven minutes.
"""

from __future__ import annotations

from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter
from echotales.core.store import Store
from echotales.pipeline.eval.baseline_b import (
    BaselineBResult,
    _chunks,
    materialize_mentions,
)


def _store_with_chapter() -> Store:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="1.html",
            blocks=[
                Block(
                    index=0,
                    block_type=BlockType.PROSE,
                    text="Zhou Mingrui opened his eyes in a strange room.",
                )
            ],
        )
    )
    return store


def _result(**over: object) -> BaselineBResult:
    base: dict = dict(
        chapters=(1, 1),
        mentions=[{"chapter": 1.0, "surface": "Zhou Mingrui", "abs_offset": 0, "entity_id": "b1"}],
        entities=[{"id": "b1", "name": "Zhou Mingrui", "descriptors": []}],
        extractor_calls=1,
        linker_calls=1,
        prompt_tokens=10,
        output_tokens=5,
        wall_seconds=1.0,
    )
    base.update(over)
    return BaselineBResult(**base)


class TestMaterializeMentions:
    """The path that burned three completed runs."""

    def test_it_writes_real_mention_rows(self) -> None:
        store = _store_with_chapter()
        inserted = materialize_mentions(store, "t", _result())
        assert inserted == 1
        rows = store.get_mentions("t", chapter=1.0)
        assert len(rows) == 1
        assert rows[0].text == "Zhou Mingrui"

    def test_target_ids_are_namespaced_so_scoring_cannot_confuse_baselines(self) -> None:
        """`score_b3` runs unmodified over these rows, and Baseline A writes
        `baseline_<id>` into the same table. Without distinct prefixes the two
        baselines' partitions would silently merge."""
        store = _store_with_chapter()
        materialize_mentions(store, "t", _result())
        assert store.get_mentions("t", chapter=1.0)[0].target_id == "baseline_b_b1"

    def test_a_chapter_missing_from_the_store_is_skipped_not_raised(self) -> None:
        store = _store_with_chapter()
        result = _result(
            mentions=[
                {"chapter": 1.0, "surface": "Zhou Mingrui", "abs_offset": 0, "entity_id": "b1"},
                {"chapter": 99.0, "surface": "Nobody", "abs_offset": 0, "entity_id": "b2"},
            ]
        )
        assert materialize_mentions(store, "t", result) == 1

    def test_no_mentions_inserts_nothing(self) -> None:
        store = _store_with_chapter()
        assert materialize_mentions(store, "t", _result(mentions=[])) == 0


class TestChunking:
    def test_chunks_reassemble_losslessly(self) -> None:
        """Offsets are recovered against the full chapter text, so a chunker
        that drops or duplicates a character silently shifts every mention
        after it."""
        text = "para one.\n\n" + ("x" * 4000) + "\n\npara three."
        assert "".join(c for _, c in _chunks(text)) == text

    def test_it_prefers_a_paragraph_boundary(self) -> None:
        text = ("a" * 1500) + "\n\n" + ("b" * 1500) + "\n\n" + ("c" * 1500)
        chunks = _chunks(text, size=2000)
        assert len(chunks) > 1
        # The first split lands on the paragraph break, not mid-run.
        assert not chunks[0][1].endswith("b")

    def test_short_text_is_one_chunk(self) -> None:
        assert len(_chunks("short", size=2000)) == 1
