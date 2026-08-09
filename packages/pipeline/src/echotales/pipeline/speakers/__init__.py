"""Phase 4: speaker attribution by four-tier escalation."""

from echotales.pipeline.speakers.attribution import (
    Attribution,
    attribute_explicit,
    attribute_proximal,
    attribute_span,
    attribute_turn_taking,
    detect_pov_holder,
)
from echotales.pipeline.speakers.contextual import attribute_contextual
from echotales.pipeline.speakers.runner import (
    AttributionReport,
    attribute_chapter,
    attribute_novel,
)

__all__ = [
    "Attribution",
    "AttributionReport",
    "attribute_chapter",
    "attribute_contextual",
    "attribute_explicit",
    "attribute_novel",
    "attribute_proximal",
    "attribute_span",
    "attribute_turn_taking",
    "detect_pov_holder",
]
