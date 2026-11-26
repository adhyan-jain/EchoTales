"""Line-level selective prose adaptation (P2).

Replaces video-side pruning with line-level adaptation decisions:
- KEEP_TEXT: Kept as narrative caption or dialogue balloon.
- SHOW: Communicated through visual imagery, action, and staging.
- CUT: Redundant or connective filler omitted with an explicit rationale.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from echotales.core.enums import SpanType
from echotales.core.models import Span
from echotales.pipeline.render.storyboard_schema import ProseDisposition

# Patterns indicating pure visual descriptions suitable for SHOW
_VISUAL_ACTION_PATTERNS = [
    r"\b(turned|walked|stood|stepped|ran|leaped|jumped|dashed|fell|collapsed)\b",
    r"\b(looked|gazed|stared|glanced|smiled|frowned|glared|sneered|grinned)\b",
    r"\b(wore|dressed in|clothed in|robed in|holding|grasped|clutched|drew|swung)\b",
    r"\b(blood|wound|bleeding|scar|torn|damaged|dirt|mud|sweat)\b",
    r"\b(room|cliff|mountain|sky|clouds|sun|moon|light|shadow|night|rain)\b",
]
_VISUAL_RE = re.compile("|".join(_VISUAL_ACTION_PATTERNS), re.IGNORECASE)

# Patterns indicating inner monologue, philosophical thought or lore (KEEP_TEXT)
_INTERNAL_THOUGHT_PATTERNS = [
    r"\b(thought|pondered|reflected|remembered|recalled|realized|understood)\b",
    r"\b(in his heart|in her mind|secretly wondered|inner voice|doubted)\b",
    r"\b(years ago|centuries past|ancient legend|the secret of|truth was)\b",
]
_THOUGHT_RE = re.compile("|".join(_INTERNAL_THOUGHT_PATTERNS), re.IGNORECASE)

# Redundant prose connective filler that can be safely CUT
_REDUNDANT_FILLERS = [
    r"^(and then|after that|meanwhile|at the same time|needless to say)\b",
    r"\b(as mentioned before|as everyone knows|it went without saying)\b",
]
_FILLER_RE = re.compile("|".join(_REDUNDANT_FILLERS), re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class AdaptationDecision:
    span_id: str
    text: str
    disposition: ProseDisposition
    rationale: str


def classify_prose_line(span: Span) -> AdaptationDecision:
    """Classify a single novel span into KEEP_TEXT, SHOW, or CUT."""
    # Dialogue and inner monologue are always kept
    if span.span_type in (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE):
        return AdaptationDecision(
            span_id=span.id,
            text=span.text,
            disposition=ProseDisposition.KEEP_TEXT,
            rationale="Dialogue and direct character thoughts are preserved.",
        )

    text = span.text.strip()
    if not text:
        return AdaptationDecision(
            span_id=span.id,
            text="",
            disposition=ProseDisposition.CUT,
            rationale="Empty span omitted.",
        )

    # Check for redundant fillers
    if _FILLER_RE.search(text) and len(text) < 40:
        return AdaptationDecision(
            span_id=span.id,
            text=text,
            disposition=ProseDisposition.CUT,
            rationale="Redundant connective transition filler omitted for pacing.",
        )

    # Check for inner reflection or complex lore
    if _THOUGHT_RE.search(text) or span.span_type == SpanType.NARRATION_EXPOSITION:
        return AdaptationDecision(
            span_id=span.id,
            text=text,
            disposition=ProseDisposition.KEEP_TEXT,
            rationale="Lore or psychological reflection requires textual caption to avoid loss of meaning.",
        )

    # Check for visual physical action, posture, or setting
    if _VISUAL_RE.search(text) or span.span_type in (SpanType.NARRATION_ACTION, SpanType.NARRATION_DESCRIPTION):
        return AdaptationDecision(
            span_id=span.id,
            text=text,
            disposition=ProseDisposition.SHOW,
            rationale="Physical movement, posture, or environment is conveyed directly by panel artwork.",
        )

    # Default to KEEP_TEXT for safety
    return AdaptationDecision(
        span_id=span.id,
        text=text,
        disposition=ProseDisposition.KEEP_TEXT,
        rationale="Retained as caption.",
    )


def adapt_spans(spans: Sequence[Span]) -> list[AdaptationDecision]:
    """Process a sequence of spans into adaptation decisions."""
    return [classify_prose_line(s) for s in spans]
