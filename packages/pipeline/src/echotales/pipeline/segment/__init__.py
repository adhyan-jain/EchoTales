"""Phase 2: narrative segmentation.

Maps discourse spans onto story-time spans, detecting dreams, flashbacks,
visions and time skips. Conservative by design: the default is one MAIN
segment per chapter, and a non-linear override requires a clear marker.
"""

from echotales.pipeline.segment.detect import (
    MIN_SEGMENT_BLOCKS,
    PROMOTION_THRESHOLD,
    ChapterMarkers,
    find_time_skips,
    scan_chapter,
    segment_chapter,
)
from echotales.pipeline.segment.llm_pass import (
    BoundaryProposal,
    SegmentationResponse,
    needs_llm_pass,
    propose_boundaries,
)
from echotales.pipeline.segment.markers import (
    DEFAULT_MARKER_SET,
    OPTIONAL_KINDS,
    UNIVERSAL_KINDS,
    Marker,
    MarkerKind,
    MarkerSet,
    find_markers,
)
from echotales.pipeline.segment.runner import SegmentReport, segment_novel

__all__ = [
    "DEFAULT_MARKER_SET",
    "MIN_SEGMENT_BLOCKS",
    "OPTIONAL_KINDS",
    "PROMOTION_THRESHOLD",
    "UNIVERSAL_KINDS",
    "BoundaryProposal",
    "ChapterMarkers",
    "Marker",
    "MarkerKind",
    "MarkerSet",
    "SegmentReport",
    "SegmentationResponse",
    "find_markers",
    "find_time_skips",
    "needs_llm_pass",
    "propose_boundaries",
    "scan_chapter",
    "segment_chapter",
    "segment_novel",
]
