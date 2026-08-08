"""`get_spans`/`get_mentions` must return reading order, not offset order.

`Span.start`/`end` and `Mention.offset` are documented as block-local, not
chapter-local (see the field docstrings on `Mention.offset`). A query that
orders by that offset alone, without `block_index` first, sorts every block's
first span together, then every block's second span together -- correct only
by coincidence when every block contributes exactly one span or mention.

Found by hand while auditing why the webview appeared to truncate dialogue: a
paragraph split into a quote plus a trailing narration tag ("...", he said.)
produces two spans in the same block, one at a low local offset and one
higher. The narration tag was never dropped -- it was sorted elsewhere in the
chapter, next to unrelated blocks that happened to share its offset value,
which read exactly like a cut-off sentence in the viewer. `resolve/runner.py`
depends on the same ordering for `get_mentions` to process a chapter in true
discourse order (its own module docstring: "Order is not an implementation
detail"), so this was a correctness bug for Phase 6, not only a display bug.
"""

from __future__ import annotations

from echotales.core.enums import (
    AliasType,
    AttributionMethod,
    ReferenceMode,
    ResolutionMethod,
    SpanType,
)
from echotales.core.models import Mention, Span
from echotales.core.store import Store


def _span(block_index: int, start: int, end: int, text: str) -> Span:
    return Span(
        id=f"n:1:{block_index}:{start}",
        novel_id="n",
        chapter=1.0,
        block_index=block_index,
        start=start,
        end=end,
        span_type=SpanType.NARRATION_ACTION,
        text=text,
        attribution_method=AttributionMethod.UNRESOLVED,
    )


def _mention(block_index: int, offset: int, text: str) -> Mention:
    return Mention(
        id=f"n:1:m{block_index}:{offset}",
        novel_id="n",
        segment_id="n:1:main0",
        chapter=1.0,
        offset=offset,
        text=text,
        alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=ReferenceMode.NARRATOR_REFERENCE,
        method=ResolutionMethod.SCORED,
        block_index=block_index,
    )


class TestSpanOrdering:
    def test_reading_order_survives_a_block_with_two_spans(self) -> None:
        """The exact shape that exposed the bug: block 1 has a low- and a
        high-offset span, and block 2's only span's offset falls *between*
        them -- enough to interleave under `ORDER BY start` alone."""
        store = Store(":memory:")
        store.add_spans(
            [
                _span(0, 0, 10, "block 0"),
                _span(1, 0, 20, "block 1, quote"),
                _span(2, 0, 15, "block 2"),
                _span(1, 20, 80, "block 1, narration tag"),
            ]
        )
        store.conn.commit()

        spans = store.get_spans("n", 1.0)
        assert [s.block_index for s in spans] == [0, 1, 1, 2]

    def test_second_span_of_a_block_is_not_lost(self) -> None:
        """Regression for the specific symptom: naive neighbour-search code
        that assumes adjacency in the returned list finds one span and
        concludes the other was dropped, when both are present."""
        store = Store(":memory:")
        store.add_spans([_span(5, 0, 59, "quote"), _span(5, 59, 80, "narration tag")])
        store.conn.commit()

        spans = store.get_spans("n", 1.0)
        assert len(spans) == 2
        assert {(s.start, s.end) for s in spans} == {(0, 59), (59, 80)}


class TestMentionOrdering:
    def test_reading_order_survives_a_block_with_two_mentions(self) -> None:
        store = Store(":memory:")
        store.add_mentions(
            [
                _mention(0, 0, "A"),
                _mention(1, 0, "B"),
                _mention(2, 0, "C"),
                _mention(1, 40, "D"),
            ]
        )
        store.conn.commit()

        mentions = store.get_mentions("n", chapter=1.0)
        assert [m.block_index for m in mentions] == [0, 1, 1, 2]
        assert [m.text for m in mentions] == ["A", "B", "D", "C"]

    def test_matters_for_discourse_order_processing_across_a_whole_novel(self) -> None:
        """`resolve_novel` calls `get_mentions(novel_id, chapter.number)` per
        chapter and relies on the returned order being reading order."""
        store = Store(":memory:")
        store.add_mentions(
            [
                _mention(3, 0, "third-block"),
                _mention(1, 0, "first-block"),
                _mention(2, 50, "second-block-late-offset"),
                _mention(1, 90, "first-block-late-offset"),
            ]
        )
        store.conn.commit()

        mentions = store.get_mentions("n", chapter=1.0)
        assert [m.text for m in mentions] == [
            "first-block",
            "first-block-late-offset",
            "second-block-late-offset",
            "third-block",
        ]
