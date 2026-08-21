"""Chapter-granularity LLM name discovery for layer 1.

The design rule in §3 of the handoff is that no stage may call a model per span
or per mention: at 1.9 s/call a per-span pass over this corpus is 34.5 hours.
So the model is not asked *where* the mentions are — it is asked *which surface
forms in this chapter are names*, once per chapter, and the resulting vocabulary
is then matched deterministically over every span with the same Aho-Corasick
machinery layer 2 already uses.

That split matters for more than cost. The model contributes the one thing
capitalisation matching cannot do — deciding that "Spring Autumn Cicada" is a
name and "major factions of justice" is not — while offsets, boundaries and
overlap resolution stay exact rather than being hallucinated back as character
positions.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import AliasType
from echotales.pipeline.mentions.gazetteer import Gazetteer
from echotales.pipeline.mentions.ner import MentionDetector, NerSpan

log = logging.getLogger(__name__)

#: Characters per model call. A chapter in this corpus is 9-14k characters and
#: `num_ctx=8192` tokens holds roughly 24k, so most chapters are one call. The
#: split is at paragraph boundaries so a name is never cut in half.
CHUNK_CHARS = 12_000

#: A returned surface longer than this is a sentence the model copied out of
#: the passage rather than a name. Seen on chapter 1 of the primary novel.
MAX_NAME_CHARS = 48
MAX_NAME_TOKENS = 6

#: Labels the model is allowed to return. Anything else is dropped rather than
#: coerced, since a label it invented is not evidence of anything.
_KEEP_LABELS = frozenset({"character", "location", "organization"})

#: A name contains none of these. The comma matters as much as the full stop:
#: the model's commonest overreach is returning an apposition it copied whole
#: ("Fang Yuan, the demon") rather than the name inside it.
_SENTENCE_MARK = re.compile(r"[.!?;:,]")


@dataclass(slots=True)
class ChapterNames:
    """The vocabulary one chapter contributed, with provenance."""

    surfaces: dict[str, str] = field(default_factory=dict)
    calls: int = 0
    rejected: int = 0
    cached: bool = False

    def characters(self) -> list[str]:
        return [s for s, label in self.surfaces.items() if label == "character"]


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on paragraph boundaries, never mid-name."""
    if len(text) <= size:
        return [text] if text.strip() else []
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for para in text.split("\n"):
        if length + len(para) > size and current:
            chunks.append("\n".join(current))
            current, length = [], 0
        current.append(para)
        length += len(para) + 1
    if current:
        chunks.append("\n".join(current))
    return [c for c in chunks if c.strip()]


def plausible_name(surface: str) -> bool:
    """Reject the failure modes a small model actually produces.

    Not a general name test — a grammatical one runs later in
    `commonness.py`. This only throws out returns that cannot be a name in any
    reading: copied sentences, punctuation-bearing fragments, and forms that
    are entirely lowercase in a corpus whose translations capitalise names
    consistently.
    """
    surface = surface.strip()
    # Strip trailing sentence punctuation before the check: a model may
    # return "Gu Yue Bo!" (pasting the exclamation that follows in the
    # text) and the name itself is still valid. Internal punctuation
    # (a comma mid-string, a period not at the end) still fails below
    # because _SENTENCE_MARK is a search, not a full-string match.
    surface = surface.rstrip(".!?;:,")
    if not (2 <= len(surface) <= MAX_NAME_CHARS):
        return False
    if len(surface.split()) > MAX_NAME_TOKENS:
        return False
    if _SENTENCE_MARK.search(surface):
        return False
    if not any(c.isalpha() for c in surface):
        return False
    # Names in these translations are capitalised without exception. A wholly
    # lowercase return is a description the model paraphrased.
    return surface[0].isupper()


class NameCache:
    """On-disk cache of the per-chapter NER pass.

    The model call is the pipeline's dominant cost — 6.5 minutes of a 7-minute
    40-chapter run — and it is a pure function of (chapter text, model). Every
    downstream stage is being tuned against its output, so without a cache each
    threshold change costs a full re-read of the volume and the iteration loop
    stops being usable.

    Keyed by a hash of the chapter text so an ingestion change or a different
    model invalidates the entry rather than silently reusing a stale one.
    """

    def __init__(self, path: Path, *, model: str = "") -> None:
        self.path = path
        self.model = model
        self._data: dict[str, dict[str, str]] = {}
        self._dirty = False
        if path.exists():
            try:
                self._data = json.loads(path.read_text())
            except (OSError, ValueError):
                log.warning("unreadable NER cache at %s; starting empty", path)

    def _key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return f"{self.model}:{digest}"

    def get(self, text: str) -> dict[str, str] | None:
        return self._data.get(self._key(text))

    def put(self, text: str, surfaces: dict[str, str]) -> None:
        self._data[self._key(text)] = surfaces
        self._dirty = True

    def flush(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=0, sort_keys=True))
        self._dirty = False


def extract_chapter_names(
    detector: MentionDetector,
    text: str,
    *,
    known_names: list[str],
    chapter: float | None = None,
    cache: NameCache | None = None,
) -> ChapterNames:
    """Ask the model which surface forms in this chapter are names."""
    result = ChapterNames()
    if cache is not None and (hit := cache.get(text)) is not None:
        result.surfaces = dict(hit)
        result.cached = True
        return result
    for chunk in chunk_text(text):
        try:
            spans = detector.detect_with_context(  # type: ignore[call-arg]
                chunk, known_names, chapter=chapter
            )
        except TypeError:
            spans = detector.detect_with_context(chunk, known_names)
        except Exception as exc:
            log.warning("NER failed on chapter %s: %s", chapter, exc)
            continue
        result.calls += 1
        for span in spans:
            surface = span.text.strip()
            label = span.label.strip().lower()
            if label not in _KEEP_LABELS or not plausible_name(surface):
                result.rejected += 1
                continue
            # A form claimed as a character anywhere in the chapter stays a
            # character: the confusable direction is character -> location
            # (clan names double as place names), and losing the person is
            # worse than carrying an extra location.
            if result.surfaces.get(surface) != "character":
                result.surfaces[surface] = label
    if cache is not None and result.calls:
        cache.put(text, result.surfaces)
    return result


class VocabularyDetector(MentionDetector):
    """Layer-1 detector over a fixed surface set, matched exactly.

    Substituted for `HeuristicDetector` when a model is available: same
    interface, same per-span call pattern, but the vocabulary was decided once
    per chapter by the model instead of by a capitalisation regex.
    """

    def __init__(self, surfaces: dict[str, str], *, score: float = 0.85) -> None:
        self.labels = surfaces
        self.score = score
        self._gazetteer = Gazetteer()
        for surface in surfaces:
            self._gazetteer.add(surface, AliasType.RIGID_NAME)
        self._gazetteer.build()

    def detect(self, text: str) -> list[NerSpan]:
        return [
            NerSpan(
                text=hit.surface,
                start=hit.start,
                end=hit.end,
                label=self.labels.get(hit.alias, "character"),
                score=self.score,
            )
            for hit in self._gazetteer.find(text)
        ]
