"""Phase 1: span-level classification and delivery-marker extraction."""

from echotales.pipeline.spans.classify import (
    RawSpan,
    classify_block_spans,
    classify_chapter,
    classify_span,
    split_quoted,
)
from echotales.pipeline.spans.delivery import (
    DeliveryMarker,
    DeliveryPolarity,
    dominant_polarity,
    extract_delivery_markers,
)

__all__ = [
    "DeliveryMarker",
    "DeliveryPolarity",
    "RawSpan",
    "classify_block_spans",
    "classify_chapter",
    "classify_span",
    "dominant_polarity",
    "extract_delivery_markers",
    "split_quoted",
]
