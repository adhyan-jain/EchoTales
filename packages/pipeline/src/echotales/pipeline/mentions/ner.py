"""Layer 1 mention detection (plans.md §6 Phase 3).

**Qwen2.5, not GLiNER.** The deciding factor is training data rather than
architecture: Qwen is trained on Chinese web-novel content *and* its English
translations, so it has seen the naming conventions this corpus uses. Xianxia
names are frequently compound — a descriptive epithet fused to a personal name
— and in English translation they read as ordinary noun phrases. A model
without that prior parses them as descriptions and misses the entity entirely.
Western-trained NER has no such prior, and no amount of label engineering
supplies it.

The detector is given the **working name list from Layer 0** as context. That
changes the question from "find the characters" to "find the characters *not
already in this list*", which is both easier and far less prone to
re-discovering the same cast every chapter.

A deterministic `HeuristicDetector` remains as the offline fallback so the
pipeline runs with no model at all.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel, Field

DEFAULT_LABELS = ("character", "location", "organization")


@dataclass(frozen=True, slots=True)
class NerSpan:
    text: str
    start: int
    end: int
    label: str
    score: float = 1.0


class MentionDetector(ABC):
    """Layer-1 detector interface."""

    @abstractmethod
    def detect(self, text: str) -> list[NerSpan]:
        """Find candidate entity mentions in a piece of text."""

    def detect_with_context(self, text: str, known_names: list[str]) -> list[NerSpan]:
        """Detect, given the names already established.

        Detectors that cannot use the hint ignore it.
        """
        return self.detect(text)

    @property
    def name(self) -> str:
        return type(self).__name__


# ---------------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------------

_CAPITALISED = re.compile(
    r"\b[A-Z][a-z’'\-]+(?:\s+(?:of|the|de|van|von)\s+[A-Z][a-z’'\-]+|\s+[A-Z][a-z’'\-]+){0,3}\b"
)

_STOPWORDS = frozenset(
    ["The", "A", "An", "And", "But", "Or", "If", "When", "While", "After", "Before", "Because", "Although", "Though", "Since", "However", "Therefore", "Thus", "So", "Then", "Now", "Here", "There", "This", "That", "These", "Those", "They", "Them", "Their", "His", "Her", "Its", "He", "She", "It", "We", "You", "I", "Me", "My", "Our", "Your", "What", "Who", "Whom", "Which", "Why", "How", "Where", "Yes", "No", "Not", "All", "Some", "Any", "Every", "Each", "Both", "Either", "Neither", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "First", "Second", "Third", "Last", "Next", "Chapter", "In", "On", "At", "To", "From", "By", "With", "For", "Of", "As", "Is", "Was", "Were", "Are", "Be", "Been", "Being", "Do", "Did", "Does", "Have", "Has", "Had", "Will", "Would", "Can", "Could", "Shall", "Should", "May", "Might", "Must", "Let", "Just", "Even", "Still", "Yet", "Only", "Also", "Very", "Too", "Much", "Many", "More", "Most", "Less", "Least", "Such", "Same", "Other", "Another", "Once", "Twice", "Again", "Ever", "Never", "Always", "Often", "Sometimes", "Perhaps", "Maybe", "Suddenly", "Immediately", "Finally", "Meanwhile", "Afterwards", "Nevertheless", "Moreover"]
)


class HeuristicDetector(MentionDetector):
    """Capitalisation-based detector for offline runs.

    Genuinely useful rather than a placeholder — these translations capitalise
    personal names consistently — but it cannot recognise a lowercase epithet
    or a compound descriptive name, which is precisely the gap Qwen fills.
    """

    def __init__(self, *, min_length: int = 2) -> None:
        self.min_length = min_length

    def detect(self, text: str) -> list[NerSpan]:
        spans: list[NerSpan] = []
        for match in _CAPITALISED.finditer(text):
            surface = match.group(0).strip()
            tokens = surface.split()
            while tokens and tokens[0] in _STOPWORDS:
                tokens = tokens[1:]
            if not tokens:
                continue
            trimmed = " ".join(tokens)
            if len(trimmed) < self.min_length:
                continue
            start = match.start() + surface.index(tokens[0])
            spans.append(
                NerSpan(
                    text=trimmed,
                    start=start,
                    end=start + len(trimmed),
                    label="character",
                    score=0.6 if len(tokens) == 1 else 0.8,
                )
            )
        return spans


# ---------------------------------------------------------------------------
# Qwen2.5 via ModelClient
# ---------------------------------------------------------------------------


class NerEntity(BaseModel):
    text: str = Field(description="the exact surface form as it appears in the text")
    label: str = Field(description="one of: character, location, organization")


class NerResponse(BaseModel):
    entities: list[NerEntity] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


_NER_SYSTEM = (
    "You extract character and location references from translated Chinese and "
    "Korean web novels.\n"
    "These works name characters in ways Western fiction does not:\n"
    "- a descriptive epithet fused to a personal name, which reads in English "
    "as an ordinary noun phrase but is a proper name\n"
    "- cultivation or rank prefixes attached to a personal name\n"
    "- creature and item names that function as personal names\n"
    "Treat such compound forms as single character entities. Do NOT return "
    "generic role words on their own (the guard, the innkeeper, the old man) — "
    "those are descriptions, not names."
)


class QwenNerDetector(MentionDetector):
    """LLM-backed NER, dispatched through `ModelClient` on the NER task.

    Runs **per chapter**, not per span: the measured budget makes a per-span
    pass over this corpus 34.5 hours locally, while a per-chapter pass is
    minutes. Offsets are recovered by searching the source text for each
    returned surface form, because a model cannot be relied on to report
    character positions accurately.
    """

    def __init__(self, client: object, *, novel_id: str = "") -> None:
        self.client = client
        self.novel_id = novel_id

    def detect(self, text: str) -> list[NerSpan]:
        return self.detect_with_context(text, [])

    def detect_with_context(
        self,
        text: str,
        known_names: list[str],
        *,
        chapter: float | None = None,
    ) -> list[NerSpan]:
        from echotales.pipeline.llm.tasks import Task

        roster = ", ".join(sorted(known_names)[:120]) if known_names else "(none yet)"
        prompt = (
            f"Characters already known in this novel:\n{roster}\n\n"
            f"Passage:\n{text[:6000]}\n\n"
            "List every character, location and organization referenced in the "
            "passage, including any NOT in the known list above. Return the "
            "exact surface form as it appears."
        )

        result = self.client.complete(  # type: ignore[attr-defined]
            Task.NER,
            prompt,
            NerResponse,
            system=_NER_SYSTEM,
            novel_id=self.novel_id,
            chapter=chapter,
        )
        return _locate(result.value.entities, text, result.value.confidence)


def _locate(entities: list[NerEntity], text: str, confidence: float) -> list[NerSpan]:
    """Map returned surface forms back onto character offsets.

    Every occurrence is emitted, not just the first: a name mentioned four
    times in a chapter is four mentions, and collapsing them would understate
    prominence and lose the co-presence signal.
    """
    spans: list[NerSpan] = []
    for entity in entities:
        surface = entity.text.strip()
        if len(surface) < 2:
            continue
        start = text.find(surface)
        while start >= 0:
            spans.append(
                NerSpan(
                    text=surface,
                    start=start,
                    end=start + len(surface),
                    label=entity.label.strip().lower() or "character",
                    score=confidence,
                )
            )
            start = text.find(surface, start + 1)
    spans.sort(key=lambda s: s.start)
    return spans


def get_detector(
    client: object | None = None,
    *,
    novel_id: str = "",
) -> MentionDetector:
    """Build the best available detector.

    Falls back to the heuristic when no client is supplied, so a checkout with
    no models degrades in recall rather than failing to run.
    """
    if client is None:
        return HeuristicDetector()
    return QwenNerDetector(client, novel_id=novel_id)
