"""Show, Don't Tell: Narration pruning for visual adaptation modes.

In an audiobook, every line of prose must be read out loud.
In visual modes (manga pages, motion comic, anime video), pure visual descriptions
are redundant when the image already conveys them.

If a panel shows Fang Yuan standing on a mountain peak in the rain, a narrator
droning "Fang Yuan stood on the mountain peak as the cold rain poured down"
ruins the cinematic pacing and treats the viewer like a toddler with a picture book.

This module categorizes narration spans into:
1. `CONVEYED_VISUALLY`:
   Visual actions, physical postures, clothing details, immediate room/scenery
   descriptions, and facial expressions that are already drawn in the panel.
   -> Pruned / muted in visual adaptation modes.
2. `ABSTRACT_UNSEEN`:
   Inner psychological reflections, historical lore, non-visual sensory cues
   (sounds, smells, chill in the air), cultivation mechanics, and time skips.
   -> Kept as voiceover / narrative captions.
3. `DIALOGUE_KEEP`:
   Spoken dialogue and inner monologues are always preserved.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from echotales.core.enums import SpanType
from echotales.core.models import Span


class NarrationVisualStatus(StrEnum):
    CONVEYED_VISUALLY = "conveyed_visually"
    ABSTRACT_UNSEEN = "abstract_unseen"
    DIALOGUE_KEEP = "dialogue_keep"


#: Verbs and nouns that describe visible physical posture, gestures, or camera elements
_VISUAL_ACTION_PATTERNS = re.compile(
    r"\b(stood|sat|walked|stepped|turned|looked|gazed|stared|smiled|frowned|glanced|"
    r"held|drew|raised|lowered|nodded|shook|wore|dressed|pointing|reaching|"
    r"robes|sword|hair|eyes|face|hand|blade|door|window|mountain|courtyard|sky|rain|clouds)\b",
    re.IGNORECASE,
)

#: Abstract, non-visual, psychological, or lore markers that an image cannot show
_ABSTRACT_UNSEEN_PATTERNS = re.compile(
    r"\b(thought|remembered|recalled|pondered|knew|understood|realized|wondered|"
    r"past life|five hundred years|legend|history|centuries|rumor|ancient records|"
    r"soul|essence|cultivation|technique|plan|scheme|regret|motive|secret|"
    r"felt|smell|stench|fragrance|sound|whisper|echoed|chill|heat|pain|pressure|"
    r"three days later|next morning|months passed|meanwhile)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class PruningReport:
    """Audit summary of narration reduction."""

    total_spans: int = 0
    dialogue_kept: int = 0
    abstract_kept: int = 0
    visually_pruned: int = 0

    @property
    def reduction_rate(self) -> float:
        narration_total = self.abstract_kept + self.visually_pruned
        return self.visually_pruned / narration_total if narration_total else 0.0

    def summary(self) -> str:
        return (
            f"Narration pruning: {self.visually_pruned} redundant visual spans pruned, "
            f"{self.abstract_kept} abstract voiceovers kept, "
            f"{self.dialogue_kept} dialogues kept "
            f"(reduction: {self.reduction_rate:.1%})"
        )


def classify_span_visual_status(span: Span) -> NarrationVisualStatus:
    """Decide whether a span should be spoken in visual adaptation modes."""
    if span.span_type is SpanType.DIALOGUE:
        return NarrationVisualStatus.DIALOGUE_KEEP

    if span.span_type is SpanType.INNER_MONOLOGUE:
        return NarrationVisualStatus.ABSTRACT_UNSEEN

    text = span.text.strip()
    if not text:
        return NarrationVisualStatus.CONVEYED_VISUALLY

    # If it contains explicit thoughts, lore, non-visual senses, or time transitions
    if _ABSTRACT_UNSEEN_PATTERNS.search(text):
        return NarrationVisualStatus.ABSTRACT_UNSEEN

    # If it heavily describes visible physical posture, setting, or expressions
    if _VISUAL_ACTION_PATTERNS.search(text):
        return NarrationVisualStatus.CONVEYED_VISUALLY

    # Default narration: short descriptions (< 8 words) describing physical states are visual
    words = text.split()
    if len(words) <= 10:
        return NarrationVisualStatus.CONVEYED_VISUALLY

    return NarrationVisualStatus.ABSTRACT_UNSEEN


def prune_spans_for_visual_mode(
    spans: Sequence[Span],
    *,
    is_visual_mode: bool = True,
) -> tuple[list[Span], PruningReport]:
    """Filter spans for visual adaptation (manga / motion comic / anime).

    In audiobook mode (is_visual_mode=False), returns all spans unchanged.
    In visual mode, filters out spans that merely duplicate what the panel shows.
    """
    report = PruningReport(total_spans=len(spans))
    if not is_visual_mode:
        for span in spans:
            if span.span_type is SpanType.DIALOGUE:
                report.dialogue_kept += 1
            else:
                report.abstract_kept += 1
        return list(spans), report

    kept: list[Span] = []
    for span in spans:
        status = classify_span_visual_status(span)
        if status is NarrationVisualStatus.DIALOGUE_KEEP:
            report.dialogue_kept += 1
            kept.append(span)
        elif status is NarrationVisualStatus.ABSTRACT_UNSEEN:
            report.abstract_kept += 1
            kept.append(span)
        else:
            report.visually_pruned += 1

    return kept, report
