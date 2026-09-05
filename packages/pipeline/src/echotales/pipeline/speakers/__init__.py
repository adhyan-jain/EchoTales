"""Phase 4: speaker attribution by escalation (turn-taking tier removed, Section 3.3)."""

from echotales.pipeline.speakers.attribution import (
    Attribution,
    attribute_explicit,
    attribute_proximal,
    attribute_span,
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
    "detect_pov_holder",
]
