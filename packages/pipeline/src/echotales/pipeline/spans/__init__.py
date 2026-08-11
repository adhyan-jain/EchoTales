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
from echotales.pipeline.spans.scene import (
    ActiveScene,
    MobDescriptor,
    build_active_scenes,
    detect_mobs,
)

__all__ = [
    "ActiveScene",
    "DeliveryMarker",
    "DeliveryPolarity",
    "MobDescriptor",
    "RawSpan",
    "build_active_scenes",
    "classify_block_spans",
    "classify_chapter",
    "classify_span",
    "detect_mobs",
    "dominant_polarity",
    "extract_delivery_markers",
    "split_quoted",
]
