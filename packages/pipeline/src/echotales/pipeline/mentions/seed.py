"""Layer 0: seed the gazetteer from dialogue attribution (deterministic).

Runs over the **full volume before any model does anything**. The insight is
that speech attribution is the highest-precision naming signal a novel offers:
`X said` is almost never anything but a character's name, needs no model, and
in dialogue-heavy web fiction it fires constantly.

Seeding from it first inverts the usual order. Instead of a model discovering
names and a gazetteer slowly catching up, the gazetteer arrives already
populated and the model is asked only about what the regex could not see. That
is both cheaper and more accurate than any ML-first ordering, and it is why
this layer is numbered 0 rather than being folded into Layer 1.

Chapter titles are parsed too: in this genre they routinely name the character
the chapter is about, and they are free to read.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from echotales.core.enums import AliasType
from echotales.core.store import Store
from echotales.pipeline.ingest.normalize import comparison_key
from echotales.pipeline.mentions.alias_type import classify_alias_type
from echotales.pipeline.mentions.lexicon import Lexicon

#: Speech verbs. Shared shape with Phase 4 attribution, but used here to
#: harvest *names* rather than to attribute a specific line.
_SPEECH_VERBS = (
    r"said|says|spoke|replied|replies|answered|asked|asks|shouted|shouts|yelled|"
    r"screamed|roared|whispered|whispers|murmured|muttered|mumbled|called|cried|"
    r"exclaimed|declared|continued|added|adds|responded|retorted|snapped|laughed|"
    r"chuckled|sighed|sneered|sneers|scoffed|snorted|urged|explained|interrupted|"
    r"interjected|greeted|repeated|stated|remarked|noted|agreed|admitted|warned|"
    r"ordered|commanded|announced|questioned|countered|insisted|pleaded|begged"
)

_NAME = r"[A-Z][\w’'\-]*(?:\s+[A-Z][\w’'\-]*){0,4}"

#: "Ba De said" -- name then verb, allowing a short adverbial between.
_NAME_THEN_VERB = re.compile(rf"\b(?P<name>{_NAME})\s+(?:\w+\s+){{0,2}}?(?:{_SPEECH_VERBS})\b")

#: "said Ba De" -- verb then name.
_VERB_THEN_NAME = re.compile(rf"\b(?:{_SPEECH_VERBS})\s+(?P<name>{_NAME})\b")

#: Direct address inside dialogue: "Elder Ba De, I have something to report."
_ADDRESS = re.compile(rf"[“\"']\s*(?P<name>{_NAME})\s*,")

#: Chapter titles frequently name their subject.
_TITLE_NAME = re.compile(rf"\b(?P<name>{_NAME})\b")

_STOPWORDS = frozenset(
    ["The", "A", "An", "And", "But", "Or", "If", "When", "While", "After", "Before", "Because", "Although", "Though", "Since", "However", "Therefore", "Thus", "So", "Then", "Now", "Here", "There", "This", "That", "These", "Those", "They", "Them", "Their", "His", "Her", "Its", "He", "She", "It", "We", "You", "I", "Me", "My", "Our", "Your", "What", "Who", "Whom", "Which", "Why", "How", "Where", "Yes", "No", "Not", "All", "Some", "Any", "Every", "Each", "Both", "Either", "Neither", "One", "Two", "Three", "In", "On", "At", "To", "From", "By", "With", "For", "Of", "As", "Is", "Was", "Were", "Are", "Be", "Been", "Being", "Do", "Did", "Does", "Have", "Has", "Had", "Will", "Would", "Can", "Could", "Shall", "Should", "May", "Might", "Must", "Let", "Just", "Even", "Still", "Yet", "Only", "Also", "Very", "Too", "Much", "Many", "More", "Most", "Less", "Least", "Such", "Same", "Other", "Another", "Once", "Twice", "Again", "Ever", "Never", "Always", "Often", "Sometimes", "Perhaps", "Maybe", "Suddenly", "Immediately", "Finally", "Meanwhile", "Afterwards", "Nevertheless", "Moreover", "Chapter", "Prologue", "Epilogue", "Interlude", "Side", "Story", "Extra", "Volume", "Part", "Book"]
)

#: Interjections and discourse particles. These sit exactly where a name sits
#: in the direct-address pattern ("Hmph, you dare?") and are capitalised, so
#: nothing structural separates them from a name -- they have to be listed.
_INTERJECTIONS = frozenset(
    ["Ah", "Ahh", "Aha", "Ha", "Haha", "Hah", "Heh", "Hmph", "Hmm", "Hm", "Hey", "Oh", "Ohh", "Oi", "Eh", "Uh", "Um", "Er", "Wow", "Whoa", "Alas", "Alright", "Right", "Okay", "Ok", "Well", "Yes", "No", "Nope", "Yeah", "Yep", "Nay", "Aye", "Sigh", "Tsk", "Tch", "Damn", "Hell", "Heavens", "Gods", "God", "Buddha", "Amen", "Please", "Sorry", "Thanks", "Thank", "Congratulations", "Indeed", "Certainly", "Absolutely", "Exactly", "Precisely", "Naturally", "Obviously", "Truly", "Really", "Wait", "Stop", "Look", "Listen", "Come", "Go", "Hurry", "Quick", "Silence", "Enough", "Impossible", "Incredible", "Unbelievable", "Amazing", "Interesting", "Good", "Great", "Fine", "Bad", "Terrible", "Excellent", "Perfect"]
)


@dataclass(slots=True)
class SeedCandidate:
    """A name harvested by Layer 0."""

    surface: str
    alias_type: AliasType
    count: int = 0
    first_chapter: float = 0.0
    #: HIGH for attribution matches, MEDIUM for titles and direct address.
    confidence: float = 0.9
    sources: set[str] = field(default_factory=set)

    @property
    def key(self) -> str:
        return comparison_key(self.surface)


@dataclass(slots=True)
class SeedReport:
    novel_id: str
    chapters: int = 0
    candidates: int = 0
    from_attribution: int = 0
    from_titles: int = 0
    from_address: int = 0
    dropped_generic: int = 0

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.candidates:,} seed names from {self.chapters} chapters\n"
            f"  attribution={self.from_attribution:,}  titles={self.from_titles:,}  "
            f"address={self.from_address:,}  dropped generic={self.dropped_generic:,}"
        )


def _trim(name: str) -> str:
    """Drop leading and trailing stopwords so 'Then Ba De' yields 'Ba De'."""
    tokens = name.split()
    while tokens and tokens[0] in _STOPWORDS:
        tokens = tokens[1:]
    while tokens and tokens[-1] in _STOPWORDS:
        tokens = tokens[:-1]
    return " ".join(tokens)


def canonical_surface(name: str) -> str:
    """The bare name, with honorific and rank decoration removed.

    Necessary because the decorated form is usually the *more* frequent one in
    this genre -- characters are addressed by rank far more often than by bare
    name. Preferring the longest observed surface therefore canonicalises a
    character as "Junior <name>" or "<name>-ssi", which then fails to match
    every undecorated mention of the same person.

    Falls back to the original when stripping would leave nothing, so a
    character whose only known form *is* a title keeps an identifier.
    """
    from echotales.pipeline.ingest.normalize import strip_honorifics

    stripped = strip_honorifics(name).strip()
    return stripped or name.strip()


def _is_interjection(name: str) -> bool:
    """Whether a captured token is a discourse particle rather than a name.

    Interjections occupy the same syntactic slot as a vocative and are
    capitalised, so only a list separates them.
    """
    tokens = name.split()
    return bool(tokens) and all(t in _INTERJECTIONS for t in tokens)


def harvest_from_text(text: str) -> dict[str, str]:
    """Names in one piece of text, mapped to the pattern that found them."""
    found: dict[str, str] = {}

    for pattern, source in (
        (_NAME_THEN_VERB, "attribution"),
        (_VERB_THEN_NAME, "attribution"),
        (_ADDRESS, "address"),
    ):
        for match in pattern.finditer(text):
            name = _trim(match.group("name"))
            # Single-token names are kept: many characters in this genre are
            # referred to by one token, and Layer 0's precision comes from the
            # speech-verb context rather than from name length.
            if len(name) >= 2 and name not in _STOPWORDS:
                found.setdefault(name, source)

    return found


def harvest_from_title(title: str) -> list[str]:
    """Names in a chapter title.

    Titles in this genre routinely name their subject and cost nothing to read,
    but they carry no sentence context, so callers should treat these as
    medium- rather than high-confidence.
    """
    out: list[str] = []
    for match in _TITLE_NAME.finditer(title):
        name = _trim(match.group("name"))
        if len(name) >= 3 and name not in _STOPWORDS and " " in name:
            out.append(name)
    return out


def seed_from_volume(
    novel_id: str,
    store: Store,
    *,
    lexicon: Lexicon | None = None,
    min_count: int = 2,
) -> tuple[dict[str, SeedCandidate], SeedReport]:
    """Harvest candidate names from the whole volume.

    `min_count` guards against one-off regex noise: a name attributed speech
    twice anywhere in the volume is real, a single hit often is not.
    """
    lex = lexicon or Lexicon()
    report = SeedReport(novel_id=novel_id)
    counts: Counter[str] = Counter()
    candidates: dict[str, SeedCandidate] = {}

    for chapter in store.iter_chapters(novel_id):
        report.chapters += 1

        for name in harvest_from_title(chapter.title):
            _record(
                candidates, counts, name, "title", chapter.number, 0.7, lex, report
            )

        for block in chapter.blocks:
            if not block.block_type.is_story_content:
                continue
            for name, source in harvest_from_text(block.text).items():
                confidence = 0.9 if source == "attribution" else 0.75
                _record(
                    candidates, counts, name, source, chapter.number, confidence, lex, report
                )

    kept = {k: v for k, v in candidates.items() if v.count >= min_count}
    report.candidates = len(kept)
    report.from_attribution = sum(1 for c in kept.values() if "attribution" in c.sources)
    report.from_titles = sum(1 for c in kept.values() if "title" in c.sources)
    report.from_address = sum(1 for c in kept.values() if "address" in c.sources)
    return kept, report


def _record(
    candidates: dict[str, SeedCandidate],
    counts: Counter[str],
    name: str,
    source: str,
    chapter: float,
    confidence: float,
    lexicon: Lexicon,
    report: SeedReport,
) -> None:
    if _is_interjection(name):
        return

    alias_type, _ = classify_alias_type(name, lexicon=lexicon)
    if not alias_type.enters_graph:
        report.dropped_generic += 1
        return

    # Canonicalise on the bare name so decorated and undecorated mentions of
    # one character collapse to a single candidate.
    surface = canonical_surface(name)
    if not surface or _is_interjection(surface):
        return

    # A form that is *only* a title after stripping is a title, not a name.
    # Recording it as a name would let every holder collide under one entry.
    bare_type, _ = classify_alias_type(surface, lexicon=lexicon)
    if bare_type in (AliasType.RELATIONAL_DEICTIC, AliasType.TRANSFERABLE_TITLE):
        alias_type = bare_type

    key = comparison_key(surface)
    if not key:
        return
    counts[key] += 1

    existing = candidates.get(key)
    if existing is None:
        candidates[key] = SeedCandidate(
            surface=surface,
            alias_type=alias_type,
            count=1,
            first_chapter=chapter,
            confidence=confidence,
            sources={source},
        )
        return

    existing.count += 1
    existing.sources.add(source)
    existing.confidence = max(existing.confidence, confidence)
    existing.first_chapter = min(existing.first_chapter, chapter)
    # Prefer the *shortest* bare form: it is the one that matches most
    # mentions, which is the opposite of the longest-wins rule that
    # canonicalised characters under their honorific.
    if len(surface) < len(existing.surface):
        existing.surface = surface
