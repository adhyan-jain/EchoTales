"""Romanization normalization and translator-handoff detection.

Two related problems, both specific to translated web fiction.

**Romanization drift.** The same name arrives spelled several ways: spacing
("Fang Yuan" / "FangYuan"), hyphenation ("Shi-Cheng" / "Shi Cheng"), diacritics
("Lü" / "Lu"), and apostrophes ("Xi'an" / "Xian"). These are not different
names, and letting them reach the resolver as distinct surface forms wastes the
evidence budget on a problem that a normalisation pass solves outright.

**Translator handoffs.** Long fan translations change hands. When they do, a
large batch of names re-romanises simultaneously at a chapter boundary. That
looks, to an entity resolver, exactly like a cast of new characters arriving at
once -- which is why it is detected explicitly and reported rather than left
for Phase 6 to be confused by.

The normalised form is a *matching key*, never a display form. The original
surface string is always what gets stored and shown; normalisation only decides
whether two strings should be compared as the same name.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from echotales.core.store import Store

# Honorifics and rank prefixes that attach to names in these genres. Stripped
# only when building a *comparison* key -- the resolver still scores the full
# surface form, because "Elder Wang" and "Wang" carry different evidence.
_HONORIFIC_PREFIXES = (
    "elder",
    "senior",
    "junior",
    "master",
    "grandmaster",
    "young master",
    "young miss",
    "lady",
    "lord",
    "sir",
    "miss",
    "mister",
    "mr",
    "mrs",
    "ms",
    "uncle",
    "aunt",
    "brother",
    "sister",
    "patriarch",
    "matriarch",
    "sect master",
    "peak lord",
    "hall master",
    "grand elder",
    "supreme elder",
    "first seat",
    "first elder",
)

_HONORIFIC_SUFFIXES = (
    "-san",
    "-sama",
    "-kun",
    "-chan",
    "-senpai",
    "-shi",
    "-nim",
    "-ssi",
    "-ge",
    "-jie",
    "-di",
    "-mei",
)

# An optional trailing period is essential, not cosmetic: abbreviated titles
# are written "Mr. Fool", so a pattern demanding `mr\s+` never fires and every
# abbreviated form silently fails to normalise. That split "Mr. Fool" from
# "Fool" while "Miss Justice" (no period) collapsed correctly -- an
# inconsistency that is very hard to spot by eye.
_PREFIX_RE = re.compile(
    r"^(?:"
    + "|".join(re.escape(h.rstrip(".")) for h in sorted(_HONORIFIC_PREFIXES, key=len, reverse=True))
    + r")\.?\s+",
    re.IGNORECASE,
)

# Leading determiners. Stripped for *matching* only. Alias typing still sees
# the raw surface, where article-led-ness is what separates an epithet
# ("the Crimson Emperor") from a generic descriptor ("the innkeeper") -- so
# removing it here does not weaken that distinction.
_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)

_SUFFIX_RE = re.compile(
    r"(?:" + "|".join(re.escape(s) for s in _HONORIFIC_SUFFIXES) + r")$",
    re.IGNORECASE,
)

_PUNCT = re.compile(r"['’\-–—.·]")
_WS = re.compile(r"\s+")


def strip_diacritics(text: str) -> str:
    """Fold accented characters to ASCII: "Lü" -> "Lu"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_romanization(name: str) -> str:
    """Build a comparison key for a name.

    Folds case, diacritics, internal punctuation and whitespace, so that
    "Shi-Cheng", "Shi Cheng" and "ShiCheng" collapse together.

    Note this removes *all* spacing, which is aggressive on purpose: Chinese
    given names are romanised with inconsistent word breaks and the spacing
    carries no information. It would be wrong for European names, so this is
    applied per-source rather than globally.
    """
    text = strip_diacritics(name).casefold()
    text = _PUNCT.sub("", text)
    text = _WS.sub("", text)
    return text


def strip_honorifics(name: str, *, strip_articles: bool = False) -> str:
    """Remove leading rank prefixes and trailing honorific suffixes.

    Applied repeatedly, since stacked honorifics ("Senior Brother Wang") are
    ordinary in this genre.

    `strip_articles` additionally removes a leading determiner. Off by default
    because the raw article matters to alias typing; on for comparison keys,
    where "The Justice" and "Miss Justice" must reach the same key.
    """
    text = name.strip()
    changed = True
    while changed:
        changed = False
        for pattern in (_PREFIX_RE, _SUFFIX_RE) + ((_ARTICLE_RE,) if strip_articles else ()):
            stripped = pattern.sub("", text)
            if stripped != text:
                text, changed = stripped, True
    return text.strip()


#: Possessive suffixes, straight and curly. Both occur in the same volume.
_POSSESSIVE_RE = re.compile(r"['’]s\b|s['’]$", re.IGNORECASE)


def strip_morphology(name: str) -> str:
    """Remove possessive and plural inflection.

    Without this, "<name>" and "<name>'s" become two entities. Measured on one
    volume that cost 121 redundant entities, including the protagonist's
    possessive form accumulating 863 mentions of its own.

    Plural stripping is applied only to multi-character stems and never when
    the result would collide with a shorter distinct name, because English
    plural `-s` is indistinguishable from a name that simply ends in `s`.
    """
    text = _POSSESSIVE_RE.sub("", name).strip()
    # Only strip a trailing plural when the stem is long enough that the `s`
    # is unlikely to be part of the name itself.
    if len(text) > 4 and text.endswith(("s", "S")) and not text.endswith(("ss", "us", "is")):
        text = text[:-1]
    return text.strip()


def display_label(surfaces: Iterable[str]) -> str:
    """Pick the label an entity is shown and exported under.

    `comparison_key` is deliberately lossy — it exists to make two forms *meet*,
    not to be read. Labelling an entity from the raw longest surface instead
    means the possessive wins whenever it is the longest variant, which is how
    "<name>'s" ends up at the top of the review table as though it were a
    separate character.

    So: strip the inflection and a leading article for display, but keep
    honorifics and clan prefixes — those carry information a reader auditing the
    graph wants, and unlike inflection they are not noise.
    """
    # Longest wins, tie-broken toward a form that needed no cleaning, so a
    # surface that occurs verbatim in the text beats a reconstructed one.
    ranked = [
        (len(cleaned), cleaned == surface.strip(), cleaned)
        for surface in surfaces
        if (cleaned := _ARTICLE_RE.sub("", strip_morphology(surface)).strip())
    ]
    return max(ranked)[2] if ranked else ""


def comparison_key(name: str) -> str:
    """The key two surface forms are compared under.

    Strips, in order: honorifics and articles, then possessive and plural
    inflection, then romanisation variance. In this corpus a single referent is
    routinely written "The X", "Mr. X", "Miss X", "X's" and bare "X" — treating
    those as five entities is a large and silent source of over-splitting.
    """
    return normalize_romanization(
        strip_morphology(strip_honorifics(name, strip_articles=True))
    )


def name_containment(a: str, b: str, *, ambiguous_tokens: frozenset[str] | None = None) -> float:
    """Evidence that one name is the other with a leading name component dropped.

    In this corpus a character is written "Gu Yue Mo Bei" on introduction and
    "Mo Bei" thereafter. Character-level similarity cannot see that: Jaro-Winkler
    is prefix-weighted, so the two score around 0.5 and fall under the
    similarity floor, and the pair becomes two entities. Measured on 40 chapters
    of the primary novel that was three duplicated characters out of 39.

    **The >= 2-token case** (house-prefixed names, e.g. "Gu Yue Mo Bei" ->
    "Mo Bei") needs no corpus knowledge: the shared part is required to be
    **at least two tokens**, and that is the whole safety property (Section 4.5
    restated) — a shared *single* token is usually a bare surname, which
    identifies a *family* rather than a person, so "Elder Wang" and
    "Xiao Wang" must not merge on the strength of "Wang" alone. No clan list
    is involved — the rule is structural and transfers to a novel whose
    houses this code has never seen.

    **The 1-token case** (a dropped given name, e.g. Korean family-name-first
    "Kim Dokja" -> "Dokja", Section 4.15) is the same shape wearing the opposite
    risk: here the *specific* component is the one that survives, and the
    *ambiguous* one (the surname, "Kim") is what's dropped. The 2-token floor
    alone can't tell these apart by token count -- it needs to know which
    component is actually ambiguous *in this novel's cast*. `ambiguous_tokens`
    supplies that: a lowercased token attested as a name component across two
    or more distinct entities (built by the caller from the corpus's own
    profiles — see `resolve/runner.py`). A single surviving token is treated
    as a genuine dropped-given-name match only when it is *not* itself one of
    those ambiguous components — i.e. it uniquely identifies one entity in
    this cast, the same property "Dokja" has and "Wang" does not. Callers
    that don't supply `ambiguous_tokens` (the default, `None`) get the old,
    strictly-2-token-or-nothing behaviour — a caller-supplied *empty*
    frozenset is a real answer ("this corpus has no ambiguous components")
    and is not the same thing as `None` ("this caller has no opinion").

    Returns 0.0 when the containment does not hold, so callers can `max()` it
    against a character-level score without diluting either.
    """
    short, long_ = sorted((name_tokens(a), name_tokens(b)), key=len)
    if not short or len(short) == len(long_):
        return 0.0
    # The shorter form must be a **suffix**, not merely a substring. In this
    # naming convention the house/surname comes first and the personal name
    # last, so the form that survives abbreviation is the tail. Requiring a
    # suffix is what stops the clan name itself — "Gu Yue", also two tokens —
    # from matching every one of its members and merging the whole family.
    if long_[-len(short) :] != short:
        return 0.0
    if len(short) == 1:
        if ambiguous_tokens is None or short[0] in ambiguous_tokens:
            return 0.0
    # Confidence falls as the dropped prefix grows: sharing 2 of 3 tokens is
    # stronger evidence than sharing 2 of 6.
    return 0.80 + 0.15 * (len(short) / len(long_))


def name_tokens(name: str) -> list[str]:
    """Lowercase-comparable name components, for both `name_containment` and
    corpus-wide token-ambiguity tables built from `EntityProfile.aliases`."""
    return [
        token.casefold()
        for raw in strip_morphology(strip_honorifics(name)).split()
        if (token := normalize_romanization(raw))
    ]


def are_variants(a: str, b: str) -> bool:
    """Whether two surface forms are romanization variants of one name."""
    return bool(a and b) and comparison_key(a) == comparison_key(b)


# ---------------------------------------------------------------------------
# Translator handoff detection
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class HandoffReport:
    """A chapter boundary where the translation appears to change hands."""

    chapter: float
    changed_forms: int
    detail: str
    #: old surface form -> new surface form, for the confirmation prompt.
    mapping: dict[str, str]


_CAPITALISED = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b")

# Words that are capitalised for position rather than because they are names.
_STOPWORDS = frozenset(
    {
        "The", "A", "An", "He", "She", "It", "They", "We", "You", "I", "His", "Her",
        "But", "And", "Or", "If", "When", "After", "Before", "This", "That", "These",
        "Those", "There", "Then", "However", "Although", "Because", "While", "Chapter",
    }
)


def _candidate_names(text: str, limit: int = 400) -> Counter[str]:
    """Rough proper-noun frequency for a chapter.

    Capitalisation-based and deliberately crude -- this runs before NER and
    only needs to detect a *mass* shift in spelling, not to identify entities.
    """
    counts: Counter[str] = Counter()
    for match in _CAPITALISED.finditer(text):
        token = match.group(0)
        if token.split()[0] in _STOPWORDS:
            continue
        if len(token) < 3:
            continue
        counts[token] += 1
        if len(counts) > limit * 4:
            break
    return counts


def detect_translator_handoffs(
    store: Store,
    novel_id: str,
    *,
    min_changed: int = 20,
    window: int = 5,
) -> list[HandoffReport]:
    """Find chapter boundaries where many surface forms re-romanise at once.

    The signal is a batch of names that vanish and are simultaneously replaced
    by romanization variants of themselves. One name changing is noise; twenty
    changing together at a single boundary is a new translator.

    `min_changed` follows plans.md Section 6 Phase 0 (20+ simultaneous changes).
    """
    chapters = list(store.iter_chapters(novel_id))
    if len(chapters) < window * 2:
        return []

    reports: list[HandoffReport] = []
    for i in range(window, len(chapters) - window):
        before: Counter[str] = Counter()
        after: Counter[str] = Counter()
        for ch in chapters[i - window : i]:
            before.update(_candidate_names(ch.story_text))
        for ch in chapters[i : i + window]:
            after.update(_candidate_names(ch.story_text))

        vanished = {n for n in before if n not in after and before[n] >= 2}
        appeared = {n for n in after if n not in before and after[n] >= 2}
        if not vanished or not appeared:
            continue

        # Pair each vanished form with an appeared form that normalises the
        # same way. Unpaired changes are ordinary cast turnover, not a handoff.
        appeared_by_key: dict[str, str] = {comparison_key(n): n for n in appeared}
        mapping = {
            old: appeared_by_key[key]
            for old in vanished
            if (key := comparison_key(old)) in appeared_by_key
        }

        if len(mapping) >= min_changed:
            reports.append(
                HandoffReport(
                    chapter=chapters[i].number,
                    changed_forms=len(mapping),
                    detail=f"{len(mapping)} surface forms re-romanised simultaneously",
                    mapping=mapping,
                )
            )

    # Collapse neighbouring detections: one handoff triggers several adjacent
    # windows, and reporting each would misstate how many there were.
    deduped: list[HandoffReport] = []
    for report in reports:
        if deduped and report.chapter - deduped[-1].chapter <= window:
            if report.changed_forms > deduped[-1].changed_forms:
                deduped[-1] = report
            continue
        deduped.append(report)
    return deduped
