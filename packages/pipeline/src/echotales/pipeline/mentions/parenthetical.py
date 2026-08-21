"""Parenthetical disambiguation (plans.md Section 6 Phase 3).

A parenthesised name beside another name means one of three quite different
things, and getting it wrong is expensive in both directions:

**(a) Translator gloss** -- "Wu Liao (Wu Le)". An alternate romanisation of the
same person. Should produce one entity with two surface forms.

**(b) Simultaneous-action shorthand** -- "Wu An (Wu Liao) nodded", meaning both
did it. Two independent characters. Merging them destroys a character.

**(c) Author disclosure of true identity** -- "Wu Yi Hai (Fang Yuan)". The
narrator telling the reader who is really behind a disguise. One self, two
personas, and the alias must be marked `FABRICATED` rather than merged
naively.

Heuristics resolve the clear cases and the rest escalate. The ordering matters:
(a) is checked first because a romanisation variant is textually detectable
with no world knowledge, while (b) and (c) both require knowing whether the two
names are already established as separate entities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from echotales.pipeline.ingest.normalize import comparison_key

_PARENTHETICAL = re.compile(
    r"(?P<outer>[A-Z][\w’'\-]*(?:\s+[A-Z][\w’'\-]*){0,3})"
    r"\s*[（(]\s*(?P<inner>[A-Z][\w’'\-]*(?:\s+[A-Z][\w’'\-]*){0,3})\s*[)）]"
)

# Sentence-initial capitalised words that the outer group would otherwise
# absorb: "Then Wu Yi Hai (Fang Yuan)" must yield "Wu Yi Hai", not "Then Wu Yi
# Hai", or the name never matches anything else in the graph.
_LEADING_STOPWORDS = frozenset(
    ["The", "A", "An", "And", "But", "Or", "If", "When", "While", "After", "Before", "Because", "Although", "Though", "Since", "However", "Therefore", "Thus", "So", "Then", "Now", "Here", "There", "This", "That", "These", "Those", "They", "Them", "He", "She", "It", "We", "You", "I", "In", "On", "At", "To", "From", "By", "With", "For", "Of", "As", "Is", "Was", "Were", "Are", "Be", "Suddenly", "Immediately", "Finally", "Meanwhile", "Afterwards", "Nevertheless", "Moreover", "Only"]
)


def _trim_leading_stopwords(name: str) -> str:
    tokens = name.split()
    while tokens and tokens[0] in _LEADING_STOPWORDS:
        tokens = tokens[1:]
    return " ".join(tokens)

# Verbs immediately after the closing bracket suggest both names are agents of
# one action, i.e. the shorthand reading.
_JOINT_VERB = re.compile(
    r"^\s*(?:also\s+)?(?:both\s+)?"
    r"(?:nodded|agreed|replied|answered|responded|said|spoke|laughed|bowed|"
    r"followed|left|arrived|entered|stood|sat|watched|looked|turned)\b",
    re.IGNORECASE,
)


class ParentheticalKind(StrEnum):
    TRANSLATOR_GLOSS = "TRANSLATOR_GLOSS"
    SIMULTANEOUS_ACTION = "SIMULTANEOUS_ACTION"
    IDENTITY_DISCLOSURE = "IDENTITY_DISCLOSURE"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class Parenthetical:
    outer: str
    inner: str
    kind: ParentheticalKind
    start: int
    end: int
    confidence: float
    reason: str


def _shares_surname(a: str, b: str) -> bool:
    """Whether two names share a leading token.

    In these genres the surname comes first, so a shared first token is weak
    evidence of kinship -- which makes them *different* people, not the same
    one. Useful as a signal against the gloss reading.
    """
    ta, tb = a.split(), b.split()
    return bool(ta and tb) and ta[0].casefold() == tb[0].casefold()


def classify_parenthetical(
    outer: str,
    inner: str,
    *,
    following_text: str = "",
    known_entities: frozenset[str] = frozenset(),
) -> tuple[ParentheticalKind, float, str]:
    """Decide what a parenthesised name means.

    `known_entities` holds comparison keys of entities already established as
    independent. Two names both already known separately is the strongest
    available signal for the shorthand reading.
    """
    key_outer, key_inner = comparison_key(outer), comparison_key(inner)

    # (a) Same name under a different romanisation.
    if key_outer == key_inner:
        return (
            ParentheticalKind.TRANSLATOR_GLOSS,
            0.95,
            "names normalise to the same comparison key",
        )

    # Near-identical keys are still almost certainly one name: translators
    # differ on a single vowel or a doubled consonant far more often than two
    # distinct characters happen to be named this similarly.
    if _close_keys(key_outer, key_inner):
        return (
            ParentheticalKind.TRANSLATOR_GLOSS,
            0.75,
            "comparison keys differ by one character",
        )

    # (b) Both already established independently, and a joint verb follows.
    both_known = key_outer in known_entities and key_inner in known_entities
    joint_verb = bool(_JOINT_VERB.match(following_text))
    if both_known and joint_verb:
        return (
            ParentheticalKind.SIMULTANEOUS_ACTION,
            0.85,
            "both names already known as separate entities and a joint verb follows",
        )
    if both_known:
        return (
            ParentheticalKind.SIMULTANEOUS_ACTION,
            0.65,
            "both names already established as separate entities",
        )

    # (c) One name unknown: the narrator is disclosing who is behind the other.
    # Shared surname argues against disclosure -- relatives, not one person.
    if not _shares_surname(outer, inner):
        if key_inner not in known_entities and key_outer in known_entities:
            return (
                ParentheticalKind.IDENTITY_DISCLOSURE,
                0.6,
                "parenthesised name is not an established separate entity",
            )
        if key_outer not in known_entities and key_inner in known_entities:
            return (
                ParentheticalKind.IDENTITY_DISCLOSURE,
                0.6,
                "outer name is not an established separate entity",
            )

    return (
        ParentheticalKind.AMBIGUOUS,
        0.3,
        "insufficient evidence; escalate",
    )


def _close_keys(a: str, b: str) -> bool:
    """Whether two comparison keys differ by at most one character."""
    if abs(len(a) - len(b)) > 1 or not a or not b:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))


def find_parentheticals(
    text: str,
    *,
    known_entities: frozenset[str] = frozenset(),
) -> list[Parenthetical]:
    """Find and classify every parenthesised name pair in a piece of text."""
    out: list[Parenthetical] = []
    for match in _PARENTHETICAL.finditer(text):
        outer = _trim_leading_stopwords(match.group("outer").strip())
        inner = _trim_leading_stopwords(match.group("inner").strip())
        if not outer or not inner:
            continue
        following = text[match.end() : match.end() + 60]
        kind, confidence, reason = classify_parenthetical(
            outer, inner, following_text=following, known_entities=known_entities
        )
        out.append(
            Parenthetical(
                outer=outer,
                inner=inner,
                kind=kind,
                start=match.start(),
                end=match.end(),
                confidence=confidence,
                reason=reason,
            )
        )
    return out
