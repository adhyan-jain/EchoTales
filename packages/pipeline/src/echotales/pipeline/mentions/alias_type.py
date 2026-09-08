"""Alias-type classification (plans.md Section 4.1).

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

# Section 5.1: single-holder positions of authority -- exactly one person in
# the story holds each of these at a time (until succession/death transfers
# it), unlike `_ROLE_NOUNS`'s interchangeable bystander occupations
# (innkeeper, merchant, guard). The old blanket "article-led + not
# capitalised => GENERIC_DESCRIPTOR" rule swallowed both alike: "the clan
# head" and "the innkeeper" classified identically, so 219 title occurrences
# across RI ch1-15 produced zero mentions (HANDOFF Section 5) and the
# retriever recall@k gate measured 0% on TRANSFERABLE_TITLE (Section 1.2).
# Deliberately a narrow, curated list rather than "any noun following a
# leading article that isn't a known bystander role": non-negotiable #4
# exists precisely to keep generic descriptors out, and a title must earn
# its way onto this list by actually naming a single-holder office, not by
# being merely capitalised-sounding or authoritative in tone.
_TRANSFERABLE_TITLE_NOUNS = frozenset(
    [
        "clan head", "clan leader", "clan chief", "sect leader", "sect master",
        "sect head", "patriarch", "matriarch", "city lord", "guild master",
        "guild leader", "guild head", "village head", "village chief",
        "headmaster", "dean", "chancellor", "king", "queen", "emperor",
        "empress", "chief elder", "grand elder",
    ]
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
        remainder_lowered = remainder.casefold()
        # Section 5.1: a single-holder office ("the clan head") is checked
        # before the generic-descriptor fallback below, since that fallback
        # would otherwise swallow it identically to "the innkeeper" purely
        # because the remainder isn't capitalised.
        if remainder_lowered in _TRANSFERABLE_TITLE_NOUNS:
            return AliasType.TRANSFERABLE_TITLE, 0.7
        head = remainder.split()[-1].casefold() if remainder.split() else ""
        # "the Ashen Duke" is an epithet; "the innkeeper" is a descriptor.
        if _EPITHET_MARKERS.search(remainder) and head not in _ROLE_NOUNS:
            return AliasType.EPITHET, 0.7
        if head in _ROLE_NOUNS or not remainder[:1].isupper():
            return AliasType.GENERIC_DESCRIPTOR, 0.85
        return AliasType.EPITHET, 0.5

    # A single-holder office named bare, with no article ("Clan Head Wang"'s
    # own title stripped down to "Clan Head", or a translation that drops
    # the article entirely).
    if lowered in _TRANSFERABLE_TITLE_NOUNS:
        return AliasType.TRANSFERABLE_TITLE, 0.65

    # A title compounded with a proper-noun qualifier ("Gu Yue clan head")
    # names the office at least as specifically as the bare noun -- and is
    # what the chapter-level NER pass actually returns once it has enough
    # context to know which clan/sect/village, instead of the article-led
    # "the clan head" form (EVOLUTION 4.62: measured directly against RI ch1
    # full-chapter output, not just the isolated-block form used to first
    # verify the LLM would propose the phrase at all).
    for title in _TRANSFERABLE_TITLE_NOUNS:
        if lowered != title and lowered.endswith(" " + title):
            prefix = text[: -(len(title) + 1)].strip()
            if prefix and prefix[0].isupper():
                return AliasType.TRANSFERABLE_TITLE, 0.6

    # Bare role nouns with no article are still generic.
    if lowered in _ROLE_NOUNS:
        return AliasType.GENERIC_DESCRIPTOR, 0.8

    if _TITLE_CASE.match(text):
        return AliasType.RIGID_NAME, 0.7

    return AliasType.GENERIC_DESCRIPTOR, 0.4


def is_persistable(alias_type: AliasType) -> bool:
    """Whether a binding of this type may reach the graph."""
    return alias_type.enters_graph


def is_transferable_title_phrase(surface: str) -> bool:
    """True if `surface` is a (possibly article-led) single-holder office title.

    Exposed for `chapter_ner.py::plausible_name`, whose "starts uppercase"
    grammatical gate would otherwise reject "the clan head" before it ever
    reaches `classify_alias_type` above — the LLM can be told to propose the
    phrase (EVOLUTION 4.62) but a lowercase-article-led surface still failed
    the earlier plausibility filter, so the two gates have to agree on the
    same curated list.
    """
    text = surface.strip()
    if _ARTICLE_LED.match(text):
        return _ARTICLE_LED.sub("", text).casefold() in _TRANSFERABLE_TITLE_NOUNS
    return text.casefold() in _TRANSFERABLE_TITLE_NOUNS


def bare_title_variant(surface: str) -> str | None:
    """The bare "the <title>" form of a proper-noun-qualified title, or None.

    "Gu Yue clan head" -> "the clan head". Measured gap (EVOLUTION 4.62): the
    chapter-level vocabulary the LLM discovers is matched *deterministically*
    over every block afterward (`chapter_ner.py`'s whole reason for existing
    -- one model call per chapter, not per span), which means an exact-string
    sweep only ever finds the one surface form the model happened to return.
    RI ch1 uses "the Gu Yue clan head" once and bare "the clan head" four
    times later in the same chapter; without this, only the first form's
    occurrences ever became mentions. Folding the bare form into the same
    chapter's discovered vocabulary lets the existing deterministic sweep
    catch both, the same way a gazetteer entry covers every surface variant
    once seeded.
    """
    text = surface.strip()
    lowered = text.casefold()
    for title in _TRANSFERABLE_TITLE_NOUNS:
        if lowered != title and lowered.endswith(" " + title):
            return f"the {title}"
    return None
