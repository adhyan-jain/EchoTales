"""Beat segmentation: which moments of a chapter get drawn.

Every chapter saturates the panel budget, so `_merge_to_budget` -- not the
boundary logic -- is what actually decides what the reader sees. These pin
the criterion it decides by.
"""

from __future__ import annotations

from echotales.core.enums import SpanType
from echotales.core.models import Span
from echotales.pipeline.render.beats import segment_beats


def _spans(texts: dict[int, str], span_type: SpanType = SpanType.NARRATION_ACTION):
    return [
        Span(
            id=f"s{i}",
            novel_id="t",
            chapter=1.0,
            block_index=i,
            start=0,
            end=len(t),
            text=t,
            span_type=span_type,
        )
        for i, t in sorted(texts.items())
    ]


class TestBudget:
    def test_a_short_chapter_keeps_every_beat(self) -> None:
        beats = segment_beats(_spans({0: "He walked.", 1: "Rain fell."}))
        assert sum(len(b.blocks) for b in beats) == 2

    def test_every_block_survives_the_merge(self) -> None:
        """Merging shares a picture between blocks; it never drops one.
        Losing prose here would silently desync picture from audio."""
        texts = {i: f"Block {i} of quiet prose about nothing much at all." for i in range(40)}
        beats = segment_beats(_spans(texts), max_panels=5)
        assert len(beats) <= 5
        covered = sorted(b for beat in beats for b in beat.blocks)
        assert covered == list(range(40))

    def test_blocks_stay_in_reading_order(self) -> None:
        texts = {i: f"Block {i}." for i in range(30)}
        beats = segment_beats(_spans(texts), max_panels=4)
        covered = [b for beat in beats for b in beat.blocks]
        assert covered == sorted(covered)


class TestDramaSurvives:
    """The criterion, and the reason it changed: word count kept whatever the
    prose spent the most words on, which in a web novel is exposition."""

    def test_a_violent_moment_outlives_longer_quiet_prose(self) -> None:
        long_quiet = (
            "The Gu room was sixty square meters, and the walls held rows of "
            "silver plates, each engraved with the rank and name of the Gu "
            "stored within, arranged by the clan in order of seniority. "
        ) * 3
        texts = {0: long_quiet, 1: long_quiet, 2: "He killed them all.", 3: long_quiet}
        beats = segment_beats(_spans(texts), max_panels=2)

        # The violent block must not have been folded into a neighbour: it
        # either leads a beat or stands alone in one.
        owner = next(b for b in beats if 2 in b.blocks)
        assert owner.blocks == [2] or owner.lead_block == 2

    def test_a_transformation_earns_its_own_panel(self) -> None:
        """RI ch1's climax -- "I have been reborn" -- scored zero before the
        director shared `persona/split.py`'s cue table, and was merged into a
        panel with a conversation about the weather."""
        filler = "The elders spoke quietly of the harvest and the weather. " * 4
        texts = {
            0: filler,
            1: filler,
            2: "With the Spring Autumn Cicada I have been reborn, going back 500 years!",
            3: filler,
            4: filler,
        }
        beats = segment_beats(_spans(texts), max_panels=2)
        owner = next(b for b in beats if 2 in b.blocks)
        assert owner.blocks == [2] or owner.lead_block == 2
