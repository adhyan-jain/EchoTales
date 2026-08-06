"""Phase 2 orchestration: chapters in, narrative segments in the store."""

from __future__ import annotations

from dataclasses import dataclass, field

from echotales.core.enums import EventType, SegmentType
from echotales.core.models import Chapter, DiscoursePosition, NarrativeSegment, ResolutionEvent
from echotales.core.store import Store
from echotales.pipeline.llm import LLMRouter
from echotales.pipeline.segment.detect import (
    PROMOTION_THRESHOLD,
    find_time_skips,
    scan_chapter,
    segment_chapter,
)
from echotales.pipeline.segment.llm_pass import needs_llm_pass, propose_boundaries
from echotales.pipeline.segment.markers import LAYER_FOR_ENTRY, Marker, MarkerKind


@dataclass(slots=True)
class SegmentReport:
    novel_id: str
    chapters: int = 0
    segments: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    timelines: set[str] = field(default_factory=set)
    time_skips: int = 0
    llm_calls: int = 0

    def summary(self) -> str:
        counts = ", ".join(f"{k}={v}" for k, v in sorted(self.by_type.items()))
        return (
            f"{self.novel_id}: {self.segments} segments over {self.chapters} chapters\n"
            f"  by type: {counts}\n"
            f"  timelines: {len(self.timelines)}  time skips: {self.time_skips}"
            f"  llm calls: {self.llm_calls}"
        )


_KIND_TO_MARKER = {
    "DREAM": MarkerKind.ENTER_DREAM,
    "FLASHBACK": MarkerKind.ENTER_FLASHBACK,
    "VISION": MarkerKind.ENTER_VISION,
    "PROPHECY": MarkerKind.ENTER_VISION,
}


def segment_novel(
    novel_id: str,
    store: Store,
    *,
    router: LLMRouter | None = None,
    use_llm: bool = False,
    commit_every: int = 25,
) -> SegmentReport:
    """Segment every ingested chapter of a novel.

    `use_llm` gates the fallback pass. Off by default so the deterministic path
    stays runnable and reproducible on its own -- and because the rules already
    resolve the formulaic transitions this genre relies on.
    """
    report = SegmentReport(novel_id=novel_id)
    pending: list[NarrativeSegment] = []

    for i, chapter in enumerate(store.iter_chapters(novel_id), start=1):
        segments = segment_chapter(chapter)

        if use_llm and router is not None:
            markers = scan_chapter(chapter).markers
            if needs_llm_pass(markers, threshold=PROMOTION_THRESHOLD):
                report.llm_calls += 1
                segments = _merge_llm_proposals(chapter, segments, router)

        pending.extend(segments)
        report.chapters += 1
        report.segments += len(segments)
        for segment in segments:
            key = segment.segment_type.value
            report.by_type[key] = report.by_type.get(key, 0) + 1
            report.timelines.add(segment.timeline_id)

        skips = find_time_skips(chapter)
        report.time_skips += len(skips)
        _record_time_skips(store, chapter, skips)

        if i % commit_every == 0:
            store.add_segments(pending)
            store.conn.commit()
            pending.clear()

    if pending:
        store.add_segments(pending)
    store.conn.commit()
    return report


def _merge_llm_proposals(
    chapter: Chapter,
    rule_segments: list[NarrativeSegment],
    router: LLMRouter,
) -> list[NarrativeSegment]:
    """Fold model-proposed boundaries into the rule-derived segmentation.

    Rule segments win on overlap. The rules fire on explicit textual formulae
    and are the higher-precision signal; the model is here for the boundaries
    that carry no formula at all.
    """
    response = propose_boundaries(chapter, router)
    if not response.boundaries or response.confidence < PROMOTION_THRESHOLD:
        return rule_segments

    non_main = [s for s in rule_segments if s.segment_type is not SegmentType.MAIN]
    additions: list[NarrativeSegment] = []

    for proposal in response.boundaries:
        marker_kind = _KIND_TO_MARKER.get(proposal.kind.upper())
        if marker_kind is None:
            continue
        if proposal.end_block <= proposal.start_block:
            continue
        if any(
            not (proposal.end_block < s.offset_from or proposal.start_block > s.offset_to)
            for s in non_main
        ):
            continue

        segment_type, layer = LAYER_FOR_ENTRY[marker_kind]
        additions.append(
            NarrativeSegment(
                id=f"{chapter.novel_id}:{chapter.number:g}:llm{len(additions)}",
                novel_id=chapter.novel_id,
                chapter_from=chapter.number,
                offset_from=proposal.start_block,
                chapter_to=chapter.number,
                offset_to=proposal.end_block,
                timeline_id=f"{segment_type.value}_CH{chapter.number:g}_LLM{len(additions) + 1}",
                story_seq_from=0.0,
                story_seq_to=float(proposal.end_block - proposal.start_block),
                segment_type=segment_type,
                narrative_layer=layer,
                confidence=response.confidence,
            )
        )

    if not additions:
        return rule_segments

    # Trim MAIN segments where a proposal now covers part of their range.
    kept = [s for s in rule_segments if s.segment_type is not SegmentType.MAIN]
    for segment in rule_segments:
        if segment.segment_type is not SegmentType.MAIN:
            continue
        if any(
            not (a.offset_to < segment.offset_from or a.offset_from > segment.offset_to)
            for a in additions
        ):
            continue
        kept.append(segment)

    return sorted(kept + additions, key=lambda s: s.offset_from)


def _record_time_skips(store: Store, chapter: Chapter, skips: list[Marker]) -> None:
    """Log a `time_skip` event per detected skip.

    Represents a gap of unobserved state change, so a character who returns
    stronger or differently titled reads as elapsed time rather than as a
    contradiction for the resolver to reconcile.

    The id carries block index *and* an ordinal: `offset` is a character
    position within its block, so two skips in different blocks can share one.
    """
    for ordinal, skip in enumerate(skips):
        store.append_event(
            ResolutionEvent(
                id=(
                    f"{chapter.novel_id}:{chapter.number:g}"
                    f":skip:{skip.block_index}:{skip.offset}:{ordinal}"
                ),
                seq=store.next_seq(),
                type=EventType.TIME_SKIP,
                payload={
                    "chapter": chapter.number,
                    "block": skip.block_index,
                    "marker": skip.text,
                },
                cause_pos=DiscoursePosition(
                    chapter=int(chapter.number), offset=skip.block_index
                ),
            )
        )
