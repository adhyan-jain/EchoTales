"""Layer 1 mention detection (docs/design/plans.md Section 6 Phase 3).

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

The passage is sent as **overlapping windows covering the whole chapter**. It
used to be sent as `text[:6000]` and no further, which made roughly half of
every novel invisible to this layer; see `NER_WINDOW_CHARS` for the measurement
and EVOLUTION 4.76 for what it cost downstream.

A deterministic `HeuristicDetector` remains as the offline fallback so the
pipeline runs with no model at all.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel, Field

DEFAULT_LABELS = ("character", "location", "organization", "item")

#: Characters of chapter text per model call. Until 2026-09-23 this path sent
#: `text[:6000]` and stopped there, so on a corpus whose median chapter is
#: 11,667 characters **about half of every novel was never seen by the mention
#: layer at all** (RI 51.9%, LOTM ~49%, ORV ~50% of text reaching NER; the RI
#: figures re-measured from the shipped database, the others from the plan). An
#: entity named only past the cut -- Bai Ning Bing, first appearing at offsets
#: 6697/6814/8757 of RI chapter 1 -- was never named, so `_locate` never looked
#: for it, and it had zero mentions until chapter 108. 6,000 is kept as the
#: window size because it is the size this path has always used and is proven
#: safe against `num_ctx=8192` with the system prompt and a 120-name roster on
#: top; the fix is to send every window, not to send a bigger one.
NER_WINDOW_CHARS = 6_000

#: Overlap between consecutive windows. A name straddling a seam is truncated
#: in one window and whole in the next, and only the whole form can be located.
NER_WINDOW_OVERLAP = 600


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
    ["The", "A", "An", "And", "But", "Or", "If", "When", "While", "After", "Before", "Because", "Although", "Though", "Since", "However", "Therefore", "Thus", "So", "Then", "Now", "Here", "There", "This", "That", "These", "Those", "They", "Them", "Their", "His", "Her", "Its", "He", "She", "It", "We", "You", "I", "Me", "My", "Our", "Your", "What", "Who", "Whom", "Which", "Why", "How", "Where", "Yes", "No", "Not", "All", "Some", "Any", "Every", "Each", "Both", "Either", "Neither", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "First", "Second", "Third", "Last", "Next", "Chapter", "In", "On", "At", "To", "From", "By", "With", "For", "Of", "As", "Is", "Was", "Were", "Are", "Be", "Been", "Being", "Do", "Did", "Does", "Have", "Has", "Had", "Will", "Would", "Can", "Could", "Shall", "Should", "May", "Might", "Must", "Let", "Just", "Even", "Still", "Yet", "Only", "Also", "Very", "Too", "Much", "Many", "More", "Most", "Less", "Least", "Such", "Same", "Other", "Another", "Once", "Twice", "Again", "Ever", "Never", "Always", "Often", "Sometimes", "Perhaps", "Maybe", "Suddenly", "Immediately", "Finally", "Meanwhile", "Afterwards", "Nevertheless", "Moreover",
     "Everyone", "Everybody", "Someone", "Somebody", "Anyone", "Anybody", "No", "None"]
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
    label: str = Field(
        description="one of: character, location, organization, item"
    )


class NerResponse(BaseModel):
    entities: list[NerEntity] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


_NER_SYSTEM = (
    "You extract character and location references from a novel.\n"
    "Some novels, especially translated Chinese and Korean web novels, name "
    "characters in ways ordinary English fiction does not:\n"
    "- a descriptive epithet fused to a personal name, which reads in English "
    "as an ordinary noun phrase but is a proper name\n"
    "- cultivation or rank prefixes attached to a personal name\n"
    "- creature and item names that function as personal names\n"
    "- a single-holder office title used ON ITS OWN in place of a name, such "
    "as \"the clan head\", \"the sect leader\", \"the city lord\", \"the "
    "patriarch\", \"the village chief\", \"the guild master\" — when context "
    "makes clear exactly one specific person holds it. You MUST return these "
    "as character candidates, exactly as written including the leading "
    "article \"the\".\n"
    "Treat such compound forms as single character entities. Do NOT return "
    "generic role words that any number of people could hold and that name no "
    "specific individual (a guard, an innkeeper, an old man, a merchant) — "
    "those are descriptions, not names.\n"
    "Label each return character, location, organization or item. Use "
    "\"item\" for a NAMED object, artifact, technique or creature that is "
    "possessed, used or sought rather than acting as a person — a named Gu, "
    "a named sword, a named treasure. Use \"character\" for it only if it "
    "speaks or acts of its own will. A generic object with no name of its "
    "own (a sword, a pill, a talisman) is not an item and must not be "
    "returned at all."
)

_NER_PROMPT = (
    "Characters already known in this novel:\n{roster}\n\n"
    "Passage:\n{passage}\n\n"
    "List every character, location, organization and item referenced in the "
    "passage, including any NOT in the known list above. Return the exact "
    "surface form as it appears."
)


def ner_pass_fingerprint() -> str:
    """A short hash of everything that decides what this pass returns.

    `NameCache` keys on (model, chapter text) alone, which was correct while
    the pass was a pure function of those two. It stopped being correct the
    moment the passage stopped being `text[:6000]`: without this, the
    2026-09-23 windowing fix would have been **completely inert on every
    novel that already has a cache** — the rerun meant to measure it would
    have replayed the truncated vocabulary and reported no change, and the
    diagnosis would have looked refuted by its own fix.

    Derived rather than hand-bumped on purpose: an edit to the system prompt,
    the label vocabulary or the window geometry invalidates the cache by
    itself, and nobody has to remember to increment anything.
    """
    material = "\x00".join(
        [
            _NER_SYSTEM,
            _NER_PROMPT,
            ",".join(DEFAULT_LABELS),
            str(NER_WINDOW_CHARS),
            str(NER_WINDOW_OVERLAP),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]


class QwenNerDetector(MentionDetector):
    """LLM-backed NER, dispatched through `ModelClient` on the NER task.

    Runs **per chapter window**, not per span: the measured budget makes a
    per-span pass over this corpus 34.5 hours locally. Offsets are recovered
    by searching the source text for each returned surface form, because a
    model cannot be relied on to report character positions accurately.

    **Cost, stated plainly against `docs/design/architecture.md` Section 7.** That section's
    design rule is "per chapter -- one call covering the whole chapter", and
    this is now a median of 3 calls per chapter (11,667 chars / a 5,400-char
    stride), rising with chapter length. Over the 600-chapter corpus that is
    ~1,800 calls and ~57 min local at the measured 1.9 s/call, against ~600
    calls and 19 min before. It stays firmly inside the rule's actual intent --
    the granularity is still O(chapter), not O(span), and the forbidden 65,296
    -call shape is 36x further away -- but it is not literally one call per
    chapter any more, and Section 7's table understates this stage by 3x.
    The `NameCache` absorbs the cost on every rerun; only a first pass pays it.
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
        # One call per window over the WHOLE chapter, not one call over its
        # first 6,000 characters. Each window's returns are located against
        # the full text rather than the window, so no offset arithmetic is
        # needed and a name introduced in window 2 still picks up its window-1
        # occurrences for free -- which is also why the old truncation only
        # ever lost entities appearing *exclusively* past the cut, and lost
        # those completely.
        best: dict[tuple[int, int, str], NerSpan] = {}
        for window in _windows(text):
            prompt = _NER_PROMPT.format(roster=roster, passage=window)

            result = self.client.complete(  # type: ignore[attr-defined]
                Task.NER,
                prompt,
                NerResponse,
                system=_NER_SYSTEM,
                novel_id=self.novel_id,
                chapter=chapter,
            )
            for span in _locate(result.value.entities, text, result.value.confidence):
                key = (span.start, span.end, span.text)
                previous = best.get(key)
                if previous is None or _outranks(span, previous):
                    best[key] = span
        return sorted(best.values(), key=lambda s: s.start)


def _outranks(candidate: NerSpan, incumbent: NerSpan) -> bool:
    """Which of two windows' verdicts on the same span survives the union.

    Higher confidence wins. On a tie -- the common case, since one model at
    one temperature returns the same `confidence` for most windows -- the
    "character" label wins, for the reason `chapter_ner` applies the same rule
    downstream: clan names double as place names, and mistyping a person as a
    location silently drops them from voice and panel casting, while the
    reverse costs one visible row in the cast list. Without this the surviving
    label would depend on window order.
    """
    if candidate.score != incumbent.score:
        return candidate.score > incumbent.score
    return candidate.label == "character" and incumbent.label != "character"


def _windows(
    text: str,
    size: int = NER_WINDOW_CHARS,
    overlap: int = NER_WINDOW_OVERLAP,
) -> list[str]:
    """Slice a chapter into overlapping passages, covering all of it.

    Deliberately not paragraph-aligned like `chapter_ner.chunk_text`: the
    overlap already guarantees every name appears whole in some window, and a
    chapter with one 7,000-character paragraph must still be covered rather
    than silently producing an over-long window.
    """
    if overlap >= size:
        # Clamping instead would silently turn one chapter into thousands of
        # model calls at stride 1 -- the one failure mode this file is being
        # fixed for is a cost decision made invisibly, so this one is loud.
        raise ValueError(f"NER window overlap {overlap} must be below size {size}")
    if len(text) <= size:
        return [text] if text else []
    stride = size - overlap
    out: list[str] = []
    start = 0
    while start < len(text):
        out.append(text[start : start + size])
        if start + size >= len(text):
            break
        start += stride
    return out


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
