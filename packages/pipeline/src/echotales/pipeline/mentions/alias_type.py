"""Alias-type classification (plans.md §4.1).

Assigning a type at detection time is what makes the rest of the resolver
tractable. Each type carries different resolution behaviour:

- `RIGID_NAME` -- near-permanent, strong linking evidence.
- `TRANSFERABLE_TITLE` -- transfer-eligible, so temporal validity is checked
  before any link.
- `RELATIONAL_DEICTIC` -- resolves relative to the *speaker*, never globally.
  "Master" from two disciples denotes two different people.
- `EPITHET` -- usually rigid per holder, occasionally shared.
- `PATHWAY_TITLE` / `TAROT_TITLE` -- source-specific, systematically ambiguous.
- `GENERIC_DESCRIPTOR` -- **never enters the graph** (non-negotiable #4).

Getting generic descriptors out of the binding table eliminates the largest
single class of false matches and false transfers, so the classifier is biased
toward calling something generic when it looks generic.
"""

from __future__ import annotations

import re

from echotales.core.enums import AliasType
from echotales.pipeline.mentions.lexicon import Lexicon

# A leading article is the strongest single signal of a generic descriptor:
# proper names in these translations do not take one, so "the innkeeper" is
# structurally distinguishable from "Fang Yuan" without knowing either word.
_ARTICLE_LED = re.compile(r"^(?:the|a|an|that|this|those|these)\s+", re.IGNORECASE)

# Occupation and role nouns that make an article-led phrase generic rather
# than an epithet.
_ROLE_NOUNS = frozenset(
    ["man", "woman", "boy", "girl", "child", "elder", "youth", "stranger", "person", "people", "crowd", "guard", "soldier", "servant", "maid", "attendant", "merchant", "trader", "innkeeper", "shopkeeper", "clerk", "officer", "constable", "detective", "driver", "waiter", "landlord", "landlady", "priest", "monk", "nun", "doctor", "physician", "apothecary", "blacksmith", "farmer", "hunter", "fisherman", "beggar", "thief", "bandit", "disciple", "cultivator", "master", "student", "scholar", "official", "minister", "messenger", "courier", "captain", "sailor", "worker", "labourer", "laborer", "villager", "citizen"]
)

# Descriptive epithets: article-led but naming a specific, distinctive holder.
_EPITHET_MARKERS = re.compile(
    r"\b(?:great|grand|dark|light|blood|iron|jade|golden|silver|crimson|azure|"
    r"eternal|immortal|ancient|first|last|supreme|heavenly|demon|devil|ghost|"
    r"sword|blade|flame|frost|thunder|storm|shadow|moon|sun|star)\b",
    re.IGNORECASE,
)

_TITLE_CASE = re.compile(r"^[A-Z][\w’'\-]*(?:\s+[A-Z][\w’'\-]*)*$")


def classify_alias_type(
    surface: str,
    *,
    lexicon: Lexicon | None = None,
    is_address: bool = False,
) -> tuple[AliasType, float]:
    """Assign an alias type and a confidence.

    `is_address` marks a surface form used as direct address in dialogue, which
    raises the prior on a relational deictic ("Master, I have returned").
    """
    text = surface.strip()
    if not text:
        return AliasType.GENERIC_DESCRIPTOR, 1.0

    # The lexicon is authoritative where it has an opinion: it encodes
    # knowledge that cannot be recovered from the text.
    if lexicon is not None:
        known = lexicon.alias_type_for(text)
        if known is not None:
            return known, 0.95

        # Progressive-rank prefixes ("Golden Core Elder Wang") are drift, not
        # transfer: strip the rank and re-classify the remainder.
        if lexicon.is_progressive_rank(text):
            stripped = lexicon.strip_rank(text)
            if stripped and stripped != text:
                inner, confidence = classify_alias_type(
                    stripped, lexicon=lexicon, is_address=is_address
                )
                return inner, confidence * 0.9

    lowered = text.casefold()

    # Deictics are decided before the generic branches, because the two
    # overlap textually and the determiner is what separates them.
    # "this old man" is a character referring to themselves; "the old man" is a
    # scene-local descriptor. Same head noun, opposite handling.
    if lowered.startswith(("this ", "my ", "your ", "our ")):
        return AliasType.RELATIONAL_DEICTIC, 0.75

    # A form used as direct address is relational even when the head noun is an
    # ordinary role word -- "Master, I have returned" names a specific person
    # relative to the speaker.
    if is_address and len(text.split()) <= 2:
        return AliasType.RELATIONAL_DEICTIC, 0.6

    if _ARTICLE_LED.match(text):
        remainder = _ARTICLE_LED.sub("", text)
        head = remainder.split()[-1].casefold() if remainder.split() else ""
        # "the Ashen Duke" is an epithet; "the innkeeper" is a descriptor.
        if _EPITHET_MARKERS.search(remainder) and head not in _ROLE_NOUNS:
            return AliasType.EPITHET, 0.7
        if head in _ROLE_NOUNS or not remainder[:1].isupper():
            return AliasType.GENERIC_DESCRIPTOR, 0.85
        return AliasType.EPITHET, 0.5

    # Bare role nouns with no article are still generic.
    if lowered in _ROLE_NOUNS:
        return AliasType.GENERIC_DESCRIPTOR, 0.8

    if _TITLE_CASE.match(text):
        return AliasType.RIGID_NAME, 0.7

    return AliasType.GENERIC_DESCRIPTOR, 0.4


def is_persistable(alias_type: AliasType) -> bool:
    """Whether a binding of this type may reach the graph."""
    return alias_type.enters_graph
