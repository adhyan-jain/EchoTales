"""Telling common nouns from proper names, from the corpus itself.

The hardest false-positive class in this content is the capitalised common
noun: role words, item names and power-scale terms are capitalised exactly like
personal names, so orthography cannot separate them. Measured on one volume,
a role noun appears 0% lowercase — identical to a character name.

Hand-listing them does not generalise either: every novel invents its own
vocabulary, and a list written from outside the text is the same mistake as a
hand-written lexicon.

Two **grammatical** signals do separate them, and both are computable from the
text with no model:

**Determiner rate.** Proper names do not take "a", "the", "every", "several".
Common nouns do, constantly. Measured on one volume: a role noun ran 48%
determiner-preceded against 0.08% for the protagonist's name — nearly three
orders of magnitude apart.

**Plural rate.** Proper names do not pluralise. If the plural form occurs in
the corpus at any real frequency, the singular is a class, not an individual.

Rates, never counts: a name mentioned 5,000 times will pick up a handful of
spurious determiner matches, and an absolute threshold would flag it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Determiners and quantifiers that a proper name does not take.
#:
#: Possessive pronouns count as determiners here, and are the signal that
#: catches kinship terms specifically. "Grandpa" is capitalised as consistently
#: as any name and never pluralises, so the article and plural tests both pass
#: it — but "his grandpa" is ubiquitous and "his Fang Yuan" does not occur.
#: Without them, kinship nouns become entities and duplicate the relative they
#: refer to.
_DETERMINERS = (
    "a|an|the|every|each|some|many|several|few|all|both|other|another|"
    "this|that|these|those|any|no|countless|numerous|various|certain|"
    "one|two|three|four|five|ten|dozens of|hundreds of|thousands of|"
    "his|her|their|its|my|your|our"
)

#: Above this share of determiner-preceded occurrences, treat as a common noun.
#: Well clear of the ~1% that real names pick up incidentally.
DETERMINER_RATE_THRESHOLD = 0.08

#: Above this share of plural occurrences, treat as a class rather than a person.
PLURAL_RATE_THRESHOLD = 0.05

#: Below this many occurrences the rates are too noisy to act on, so the
#: surface is left alone rather than judged on one or two hits.
MIN_OCCURRENCES = 8

#: Power-scale and measurement patterns. Structural, so no counting needed:
#: "Rank One", "Stage Three", "Level 5" name a position on a scale, never a
#: person, and they are capitalised in exactly the same way as a name.
_SCALE_PATTERN = re.compile(
    r"^(?:rank|stage|level|grade|tier|realm|sequence|step|layer|phase)\s*"
    r"(?:[0-9]+|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)$",
    re.IGNORECASE,
)

#: A bare scale word on its own ("Rank", "Grade") is likewise never a person.
_BARE_SCALE = re.compile(
    r"^(?:rank|stage|level|grade|tier|realm|sequence)$", re.IGNORECASE
)


@dataclass(slots=True)
class CommonnessProfile:
    """Per-surface grammatical evidence, derived from one corpus."""

    determiner_rate: dict[str, float] = field(default_factory=dict)
    plural_rate: dict[str, float] = field(default_factory=dict)
    occurrences: dict[str, int] = field(default_factory=dict)
    #: Casefolded corpus, retained so surfaces discovered *after* the profile
    #: was built can still be measured. Layer 1 now proposes vocabulary the
    #: Layer 0 seed list never contained, and an unmeasured surface silently
    #: skips the filter entirely — which is how "Grandpa" became an entity.
    corpus: str = ""

    def is_common_noun(self, surface: str) -> bool:
        """Whether a surface form names a class rather than an individual."""
        if is_scale_term(surface):
            return True

        key = surface.casefold()
        if key not in self.occurrences and self.corpus:
            self.measure(surface)
        total = self.occurrences.get(key, 0)
        if total < MIN_OCCURRENCES:
            # Too rare to judge grammatically. Leaving it alone is the safe
            # direction: a missed filter costs one noisy entity, while a wrong
            # filter deletes a real character outright.
            return False

        return (
            self.determiner_rate.get(key, 0.0) >= DETERMINER_RATE_THRESHOLD
            or self.plural_rate.get(key, 0.0) >= PLURAL_RATE_THRESHOLD
        )

    def measure(self, surface: str) -> None:
        """Measure one surface against the retained corpus, caching the result."""
        key = surface.casefold()
        if key in self.occurrences or len(key) < 2:
            return
        _measure_into(self, key, self.corpus)

    def explain(self, surface: str) -> str:
        key = surface.casefold()
        return (
            f"{surface!r}: {self.occurrences.get(key, 0)} occurrences, "
            f"determiner={self.determiner_rate.get(key, 0.0):.1%}, "
            f"plural={self.plural_rate.get(key, 0.0):.1%}"
        )


def is_scale_term(surface: str) -> bool:
    """Whether a surface names a position on a power/measurement scale."""
    text = surface.strip()
    return bool(_SCALE_PATTERN.match(text) or _BARE_SCALE.match(text))


def build_profile(text: str, candidates: list[str]) -> CommonnessProfile:
    """Measure determiner and plural rates for each candidate surface form.

    One pass per candidate over the corpus. Candidates come from Layer 0/1, so
    this is bounded by the vocabulary size rather than by the text length.
    """
    lowered = text.casefold()
    profile = CommonnessProfile(corpus=lowered)

    for surface in candidates:
        key = surface.casefold()
        if key and len(key) >= 2:
            _measure_into(profile, key, lowered)

    return profile


def _measure_into(profile: CommonnessProfile, key: str, lowered: str) -> None:
    """One candidate's rates, written into the profile."""
    escaped = re.escape(key)
    total = len(re.findall(rf"\b{escaped}\b", lowered))
    if total == 0:
        # Recorded as zero so a surface absent from the corpus is not
        # re-measured on every chapter that proposes it.
        profile.occurrences[key] = 0
        return

    determiner_hits = len(re.findall(rf"\b(?:{_DETERMINERS})\s+{escaped}\b", lowered))
    # Plural counted against singular+plural so the rate is the share of
    # occurrences that are plural, not a ratio that can exceed 1.
    plural_hits = len(re.findall(rf"\b{escaped}s\b", lowered))

    profile.occurrences[key] = total
    profile.determiner_rate[key] = determiner_hits / total
    profile.plural_rate[key] = plural_hits / (total + plural_hits)


# ---------------------------------------------------------------------------
# Non-diegetic credits
# ---------------------------------------------------------------------------

#: Translation-group credits. These sit inside the chapter body in fan
#: exports, so block classification does not always catch them, and they then
#: read as recurring characters — one volume produced four such "characters"
#: with 481 mentions between them.
_CREDIT_TERMS = (
    "translator", "translated", "editor", "edited", "proofreader", "proofread",
    "typesetter", "uploader", "raws", "raw provider", "tl note", "tln",
    "patreon", "ko-fi", "kofi", "discord", "webnovel", "wuxiaworld",
    "novelupdates", "sponsor", "chapter sponsor", "support us", "donate",
)

_CREDIT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in _CREDIT_TERMS) + r")\b", re.IGNORECASE
)


def looks_like_credit(surface: str, context: str = "") -> bool:
    """Whether a surface form is a translation credit rather than a character.

    Checks the surface itself and, when supplied, its context — a group's name
    is arbitrary and unrecognisable on its own, but it sits next to the word
    "translator" every time it appears.
    """
    if _CREDIT_RE.search(surface):
        return True
    return bool(context) and bool(_CREDIT_RE.search(context))


def credit_surfaces(text: str, candidates: list[str], *, rate: float = 0.5) -> set[str]:
    """Candidates that mostly co-occur with credit vocabulary.

    Catches the group name itself, which carries no giveaway of its own. A high
    co-occurrence rate is the signal: a character occasionally appears near the
    word "translator", a translation group essentially always does.
    """
    lowered = text.casefold()
    flagged: set[str] = set()

    for surface in candidates:
        key = surface.casefold()
        if len(key) < 3:
            continue
        occurrences = [m.start() for m in re.finditer(rf"\b{re.escape(key)}\b", lowered)]
        if len(occurrences) < 3:
            continue
        near_credit = sum(
            1
            for pos in occurrences
            if _CREDIT_RE.search(lowered[max(0, pos - 80) : pos + 80])
        )
        if near_credit / len(occurrences) >= rate:
            flagged.add(surface)

    return flagged
