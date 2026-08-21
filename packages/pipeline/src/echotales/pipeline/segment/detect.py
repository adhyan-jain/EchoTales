"""Building narrative segments from markers (plans.md Section 6 Phase 2).

Turns per-block markers into `NarrativeSegment` rows mapping discourse spans
onto story-time spans.

The default is **one chapter, one MAIN segment, `story_seq = chapter index`**,
which reduces the entire temporal apparatus to naive behaviour for a linear
novel. Non-linear structure is an override applied only on clear evidence,
because of the asymmetry plans.md names: a missed flashback costs one temporal
misattribution, while a false one costs that *plus* a spurious timeline that
every subsequent fact gets attached to.

Timeline identity matters as much as boundary placement. Each dream gets its
own `DREAM_<n>` timeline rather than sharing a generic one, so that entities
inside separate dreams cannot be linked to each other through a shared
coordinate system they never actually shared.
"""

from __future__ import annotations

from dataclasses import dataclass

from echotales.core.enums import Canonicity, NarrativeLayer, SegmentType
from echotales.core.models import MAIN_TIMELINE, Chapter, NarrativeSegment
from echotales.pipeline.segment.markers import (
    ENTRY_KINDS,
    EXIT_FOR_ENTRY,
    LAYER_FOR_ENTRY,
    Marker,
    MarkerKind,
    find_markers,
)

#: A marker must reach this confidence before it may open a non-MAIN segment.
PROMOTION_THRESHOLD = 0.7

#: A non-MAIN segment shorter than this many blocks is treated as a passing
#: reference rather than a genuine narrative layer. "He recalled that day" in
#: the middle of a fight is a sentence, not a flashback.
MIN_SEGMENT_BLOCKS = 3


@dataclass(slots=True)
class ChapterMarkers:
    chapter: float
    markers: list[Marker]

    @property
    def has_boundary(self) -> bool:
        return any(m.kind in ENTRY_KINDS or m.kind is MarkerKind.TIME_SKIP for m in self.markers)


def scan_chapter(chapter: Chapter) -> ChapterMarkers:
    """Find every boundary marker in a chapter."""
    markers: list[Marker] = []
    for block in chapter.blocks:
        markers.extend(find_markers(block.text, block.index))
    return ChapterMarkers(chapter=chapter.number, markers=markers)


def _timeline_id(kind: MarkerKind, chapter: float, ordinal: int) -> str:
    """Name a derived timeline.

    Keyed by chapter and ordinal so two dreams never share a timeline. Sharing
    one would let entities from unrelated dreams be compared on a common
    coordinate, which is precisely the merge the self/persona model exists to
    prevent.
    """
    if kind is MarkerKind.ENTER_DREAM:
        return f"DREAM_CH{chapter:g}_{ordinal}"
    if kind is MarkerKind.ENTER_FLASHBACK:
        return f"MEMORY_CH{chapter:g}_{ordinal}"
    return f"VISION_CH{chapter:g}_{ordinal}"


def segment_chapter(chapter: Chapter, *, story_seq: float | None = None) -> list[NarrativeSegment]:
    """Partition one chapter into narrative segments.

    Returns at least one segment. When no boundary is detected the result is a
    single MAIN segment covering the whole chapter, which is the correct and
    overwhelmingly common answer.
    """
    seq = float(chapter.number) if story_seq is None else story_seq
    n_blocks = len(chapter.blocks)
    last_index = chapter.blocks[-1].index if chapter.blocks else 0

    scan = scan_chapter(chapter)
    entries = [
        m for m in scan.markers if m.kind in ENTRY_KINDS and m.confidence >= PROMOTION_THRESHOLD
    ]

    if not entries or n_blocks < MIN_SEGMENT_BLOCKS:
        return [_main_segment(chapter, seq, 0, last_index)]

    segments: list[NarrativeSegment] = []
    cursor = 0
    ordinal = 0

    for entry in entries:
        if entry.block_index < cursor:
            continue

        exit_kind = EXIT_FOR_ENTRY[entry.kind]
        exit_marker = next(
            (
                m
                for m in scan.markers
                if m.kind is exit_kind and m.block_index > entry.block_index
            ),
            None,
        )
        # An unterminated layer runs to the end of the chapter. That is the
        # normal shape for a dream that continues into the next chapter, and
        # closing it early would strand its cast on the main timeline.
        end_index = exit_marker.block_index if exit_marker else last_index

        if end_index - entry.block_index < MIN_SEGMENT_BLOCKS:
            continue

        if entry.block_index > cursor:
            segments.append(_main_segment(chapter, seq, cursor, entry.block_index - 1))

        ordinal += 1
        segment_type, layer = LAYER_FOR_ENTRY[entry.kind]
        segments.append(
            NarrativeSegment(
                id=f"{chapter.novel_id}:{chapter.number:g}:seg{len(segments)}",
                novel_id=chapter.novel_id,
                chapter_from=chapter.number,
                offset_from=entry.block_index,
                chapter_to=chapter.number,
                offset_to=end_index,
                timeline_id=_timeline_id(entry.kind, chapter.number, ordinal),
                # A derived timeline has its own internal coordinates starting
                # at 0; it is deliberately not comparable with MAIN_TIMELINE.
                story_seq_from=0.0,
                story_seq_to=float(end_index - entry.block_index),
                segment_type=segment_type,
                narrative_layer=layer,
                canonicity=Canonicity.CANONICAL,
                confidence=entry.confidence,
            )
        )
        cursor = end_index + 1

    if cursor <= last_index:
        segments.append(_main_segment(chapter, seq, cursor, last_index))

    return segments or [_main_segment(chapter, seq, 0, last_index)]


def _main_segment(
    chapter: Chapter, seq: float, from_index: int, to_index: int
) -> NarrativeSegment:
    return NarrativeSegment(
        id=f"{chapter.novel_id}:{chapter.number:g}:main{from_index}",
        novel_id=chapter.novel_id,
        chapter_from=chapter.number,
        offset_from=from_index,
        chapter_to=chapter.number,
        offset_to=to_index,
        timeline_id=MAIN_TIMELINE,
        story_seq_from=seq,
        story_seq_to=seq,
        segment_type=SegmentType.MAIN,
        narrative_layer=NarrativeLayer.MAIN,
        canonicity=Canonicity.CANONICAL,
        confidence=1.0,
    )


def find_time_skips(chapter: Chapter) -> list[Marker]:
    """Time-skip markers within a chapter.

    Recorded separately from segmentation. A skip does not create a new
    timeline -- the story stays on MAIN -- but it does mark a gap of
    unobserved state change, so that a character who is suddenly stronger or
    differently titled afterwards reads as elapsed time rather than as a
    contradiction to be resolved.
    """
    return [m for m in scan_chapter(chapter).markers if m.kind is MarkerKind.TIME_SKIP]
