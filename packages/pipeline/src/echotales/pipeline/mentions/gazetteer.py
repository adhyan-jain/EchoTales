"""Aho-Corasick gazetteer over confirmed aliases (plans.md §6 Phase 3, layer 2).

**This is the compound-interest mechanism.** The automaton starts empty and is
rebuilt at each 30-50 chapter window boundary from aliases the resolver has
confirmed. By chapter 50 it catches most name mentions at zero error and zero
cost; by chapter 100 most decisions resolve by exact match rather than by
scoring. The system gets cheaper and more accurate the further it reads, which
is why "% of decisions resolved by exact match vs. chapter number" is a curve
worth reporting rather than an implementation detail.

Aho-Corasick specifically because the alias set reaches thousands of entries
and every chapter must be scanned against all of them: it matches every pattern
in one pass over the text, independent of how many patterns there are.

Matching is on a **normalised** copy of the text while offsets are reported
against the original, so "Fang Yuan" and "FangYuan" both match without the
stored span drifting off the surface form the reader sees.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import ahocorasick
from echotales.core.enums import AliasType

#: Surface forms that are common words in some contexts and names in others.
#:
#: These need an explicit list because nothing structural separates them: they
#: are capitalised at sentence start exactly as a name is, and an exact
#: gazetteer match on one force-links through the pre-filter at high
#: confidence. One bad entry here propagates to every occurrence in the volume.
#:
#: Blocked only as *whole* surface forms — a compound containing one of these
#: words is still admitted, since the surrounding tokens disambiguate it.
AMBIGUITY_BLOCKLIST: frozenset[str] = frozenset(
    {
        # Abstract nouns used as titles, epithets or code names.
        "fate", "hope", "faith", "grace", "justice", "mercy", "honour", "honor",
        "fortune", "destiny", "chance", "luck", "reason", "will", "spirit",
        "dawn", "dusk", "storm", "frost", "flame", "shadow", "light", "dark",
        "sun", "moon", "star", "sky", "earth", "river", "mountain", "sea",
        "king", "queen", "prince", "princess", "duke", "lord", "lady",
        "master", "elder", "senior", "junior", "brother", "sister",
        "father", "mother", "son", "daughter", "uncle", "aunt",
        # Common words that appear capitalised mid-sentence.
        "one", "two", "three", "first", "second", "third", "last", "next",
        "north", "south", "east", "west", "left", "right",
        "gold", "silver", "iron", "jade", "blood", "bone", "heart", "soul",
        "war", "peace", "death", "life", "time", "world", "heaven", "hell",
        # Interjections and discourse particles.
        "ah", "oh", "eh", "hmm", "well", "yes", "no", "wait", "stop", "look",
        # Genre-generic terms that read as capitalised proper nouns but are
        # common vocabulary in specific novels: "Gu" = worm/insect in
        # Gu-themed cultivation novels (e.g. Reverend Insanity); "veil" =
        # the barrier to the spirit/Beyonder world in Gothic-horror novels
        # (e.g. Lord of the Mysteries). Multi-word aliases such as
        # "Gu Yue Dong Tu" are separate strings and are not affected by
        # blocking the bare token.
        "gu", "veil",
    }
)


@dataclass(frozen=True, slots=True)
class GazetteerHit:
    """One gazetteer match, with offsets into the original text."""

    surface: str
    start: int
    end: int
    alias: str
    alias_type: AliasType
    target_id: str | None = None


def _fold(text: str) -> tuple[str, list[int]]:
    """Casefold and drop internal spacing/punctuation, keeping an offset map.

    Returns the folded string plus, for each folded character, its index in the
    original. The map is what lets a match on the folded text be reported as a
    span of the original -- without it, matching normalised forms would make
    every offset unusable downstream.
    """
    folded: list[str] = []
    offsets: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace() or ch in "'’-–—.·":
            continue
        folded.append(ch.casefold())
        offsets.append(i)
    return "".join(folded), offsets


class Gazetteer:
    """Exact-match alias lookup over a growing vocabulary."""

    def __init__(self) -> None:
        self._automaton: ahocorasick.Automaton | None = None
        self._entries: dict[str, tuple[str, AliasType, str | None]] = {}
        self._dirty = False

    def add(
        self,
        alias: str,
        alias_type: AliasType,
        target_id: str | None = None,
    ) -> None:
        """Register an alias.

        Generic descriptors are refused outright. They are scene-local and must
        never enter the graph (non-negotiable #4); admitting them here would
        reintroduce the largest class of false matches through the cheapest,
        highest-trust path in the pipeline.
        """
        if not alias_type.enters_graph:
            return
        cleaned = alias.strip()
        # Single characters and very short forms match inside unrelated words
        # far too often to be worth their recall.
        if len(cleaned) < 2:
            return
        # Ambiguous whole-word forms are refused. An exact gazetteer match
        # force-links through the pre-filter at high confidence, so one common
        # word admitted here mislinks every occurrence in the volume. A
        # compound containing the word is still fine -- the extra tokens
        # disambiguate it.
        if cleaned.casefold() in AMBIGUITY_BLOCKLIST:
            return
        folded, _ = _fold(cleaned)
        if not folded:
            return
        self._entries[folded] = (cleaned, alias_type, target_id)
        self._dirty = True

    def add_many(self, items: Iterable[tuple[str, AliasType, str | None]]) -> None:
        for alias, alias_type, target_id in items:
            self.add(alias, alias_type, target_id)

    def build(self) -> None:
        """(Re)build the automaton. Called at window boundaries."""
        automaton = ahocorasick.Automaton()
        for folded, payload in self._entries.items():
            automaton.add_word(folded, (folded, *payload))
        if self._entries:
            automaton.make_automaton()
        self._automaton = automaton
        self._dirty = False

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def is_stale(self) -> bool:
        return self._dirty or self._automaton is None

    def find(self, text: str) -> list[GazetteerHit]:
        """Find every registered alias in a piece of text.

        Overlapping matches are resolved longest-first, so "Sect Master Wang"
        is not reduced to "Wang".
        """
        if self.is_stale:
            self.build()
        if self._automaton is None or not self._entries:
            return []

        folded, offsets = _fold(text)
        if not folded:
            return []

        raw: list[tuple[int, int, str, AliasType, str | None]] = []
        for end_index, (key, alias, alias_type, target_id) in self._automaton.iter(folded):
            start_index = end_index - len(key) + 1
            if not _is_boundary(text, folded, offsets, start_index, end_index):
                continue
            raw.append((start_index, end_index, alias, alias_type, target_id))

        return _resolve_overlaps(raw, text, offsets)

    def snapshot(self) -> dict[str, tuple[str, AliasType, str | None]]:
        return dict(self._entries)


def _is_boundary(
    text: str, folded: str, offsets: list[int], start_index: int, end_index: int
) -> bool:
    """Reject matches that fall inside a larger word.

    Folding removes spaces, so "Li" would otherwise match inside "Lian". The
    check is made against the *original* text, where the word boundaries
    actually live.
    """
    orig_start = offsets[start_index]
    orig_end = offsets[end_index]

    before = text[orig_start - 1] if orig_start > 0 else " "
    after = text[orig_end + 1] if orig_end + 1 < len(text) else " "
    return not (before.isalnum() or after.isalnum())


def _resolve_overlaps(
    raw: list[tuple[int, int, str, AliasType, str | None]],
    text: str,
    offsets: list[int],
) -> list[GazetteerHit]:
    """Keep the longest match at each position."""
    # Longest first, then leftmost.
    raw.sort(key=lambda r: (-(r[1] - r[0]), r[0]))
    taken: list[tuple[int, int]] = []
    hits: list[GazetteerHit] = []

    for start_index, end_index, alias, alias_type, target_id in raw:
        if any(s <= start_index <= e or s <= end_index <= e for s, e in taken):
            continue
        taken.append((start_index, end_index))
        orig_start = offsets[start_index]
        orig_end = offsets[end_index] + 1
        hits.append(
            GazetteerHit(
                surface=text[orig_start:orig_end],
                start=orig_start,
                end=orig_end,
                alias=alias,
                alias_type=alias_type,
                target_id=target_id,
            )
        )

    hits.sort(key=lambda h: h.start)
    return hits


def seed_from_lexicon(gazetteer: Gazetteer, lexicon: object) -> None:
    """Seed a gazetteer with a lexicon's known titles.

    Seeded before reading begins, so transferable titles are recognised as
    titles from chapter one rather than being mistaken for names until enough
    evidence accumulates.
    """
    from echotales.pipeline.mentions.lexicon import Lexicon

    if not isinstance(lexicon, Lexicon):
        return
    for title in lexicon.transferable_titles | lexicon.era_locked_titles:
        gazetteer.add(title, AliasType.TRANSFERABLE_TITLE)
    for title in lexicon.pathway_titles:
        gazetteer.add(title, AliasType.PATHWAY_TITLE)
    for title in lexicon.tarot_titles:
        gazetteer.add(title, AliasType.TAROT_TITLE)
    for deictic in lexicon.relational_deictics:
        gazetteer.add(deictic, AliasType.RELATIONAL_DEICTIC)


def iter_windows(chapters: Iterable[float], size: int) -> Iterator[list[float]]:
    """Group chapter numbers into processing windows."""
    window: list[float] = []
    for number in chapters:
        window.append(number)
        if len(window) >= size:
            yield window
            window = []
    if window:
        yield window
