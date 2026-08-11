"""Phase 5: local anaphora resolution (plans.md §6 Phase 5).

**Not clustering.** Non-negotiable #1. Clustering assumes similarity implies
identity, and this content violates that constantly in both directions: "Fang
Yuan" and "Liu Guan Yi" share no surface form yet are one self, while two
unrelated "Elder Wang"s share every character. So resolution here is explicit
chain-following -- each pronoun is linked to a specific antecedent by a rule
that can be named, and anything without a nearby antecedent is left unresolved.

**Local only.** One chapter, one narrative layer. No cross-chapter resolution
happens here; that is Phase 6's job with the whole evidence vector. The output
is within-chapter mention groups, each labelled by its most informative surface
form.

**Precision over recall** (non-negotiable #9). A false merge corrupts an entity
permanently and propagates into every later decision about it; a missed link
costs one mention that Phase 6 may still recover. When in doubt, do nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from echotales.core.enums import AliasType, ReferenceMode, SpanType
from echotales.core.models import Mention, Span

# Third-person pronouns, with the agreement features needed to reject a wrong
# antecedent. First and second person are excluded: they resolve to the speaker
# and addressee, which speaker attribution already handles.
_PRONOUNS: dict[str, tuple[str, str]] = {
    "he": ("m", "sg"),
    "him": ("m", "sg"),
    "his": ("m", "sg"),
    "himself": ("m", "sg"),
    "she": ("f", "sg"),
    "her": ("f", "sg"),
    "hers": ("f", "sg"),
    "herself": ("f", "sg"),
    "they": ("n", "pl"),
    "them": ("n", "pl"),
    "their": ("n", "pl"),
    "themselves": ("n", "pl"),
    "it": ("n", "sg"),
    "its": ("n", "sg"),
}

_PRONOUN_RE = re.compile(
    r"\b(" + "|".join(sorted(_PRONOUNS, key=len, reverse=True)) + r")\b", re.IGNORECASE
)

#: How far back a pronoun may look, in characters. Deliberately short: a
#: distant antecedent is usually the wrong one, and a wrong link is worse than
#: none.
_MAX_ANTECEDENT_DISTANCE = 600

#: Gendered words that let an antecedent's gender be inferred from context.
_MALE_CUES = re.compile(r"\b(?:he|him|his|man|men|boy|father|brother|son|uncle|sir|lord|king|"
                        r"emperor|master|monk|priest|gentleman)\b", re.IGNORECASE)
_FEMALE_CUES = re.compile(r"\b(?:she|her|hers|woman|women|girl|mother|sister|daughter|aunt|"
                          r"lady|madam|queen|empress|miss|mistress)\b", re.IGNORECASE)


@dataclass(slots=True)
class MentionGroup:
    """Mentions within one chapter and layer believed to denote one entity."""

    id: str
    mention_ids: list[str] = field(default_factory=list)
    label: str = ""
    timeline_id: str = ""
    confidence: float = 1.0
    #: Rules that produced the links, for auditing a bad merge later.
    rationale: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.mention_ids)


@dataclass(slots=True)
class PronounLink:
    pronoun: str
    offset: int
    antecedent_mention_id: str
    antecedent_text: str
    confidence: float
    rule: str


def infer_gender(name: str, contexts: list[str]) -> str:
    """Guess an entity's gender from surrounding pronouns and role words.

    Returns "m", "f", or "n" (unknown). Used only to *reject* incompatible
    antecedents, never to assert an attribute -- a wrong guess here should cost
    a missed link, not a fabricated fact about a character.
    """
    male = sum(len(_MALE_CUES.findall(c)) for c in contexts)
    female = sum(len(_FEMALE_CUES.findall(c)) for c in contexts)
    if male > female * 2 and male >= 2:
        return "m"
    if female > male * 2 and female >= 2:
        return "f"
    return "n"


def find_pronouns(text: str, base_offset: int = 0) -> list[tuple[str, int, str, str]]:
    """Locate third-person pronouns as `(surface, offset, gender, number)`."""
    out: list[tuple[str, int, str, str]] = []
    for match in _PRONOUN_RE.finditer(text):
        surface = match.group(1)
        gender, number = _PRONOUNS[surface.casefold()]
        out.append((surface, base_offset + match.start(), gender, number))
    return out


def resolve_pronoun(
    pronoun_offset: int,
    gender: str,
    number: str,
    candidates: list[Mention],
    *,
    genders: dict[str, str] | None = None,
    max_distance: int = _MAX_ANTECEDENT_DISTANCE,
) -> tuple[Mention, float, str] | None:
    """Link one pronoun to the nearest agreeing antecedent.

    Only mentions *before* the pronoun are considered: cataphora exists but is
    rare in this prose, and admitting it roughly doubles the candidate set for
    a small recall gain.

    Returns `None` rather than guessing when nothing agrees. That is the
    precision-over-recall rule in practice.
    """
    genders = genders or {}
    prior = [
        m
        for m in candidates
        if m.offset < pronoun_offset
        and pronoun_offset - m.offset <= max_distance
        and m.alias_type is AliasType.RIGID_NAME
    ]
    if not prior:
        return None

    # Nearest first: recency is the dominant signal for pronoun antecedents.
    prior.sort(key=lambda m: pronoun_offset - m.offset)

    agreeing = []
    for mention in prior:
        known = genders.get(mention.text, "n")
        # "n" on either side means unknown, which is compatible with anything.
        if gender != "n" and known != "n" and gender != known:
            continue
        agreeing.append((mention, known))

    if not agreeing:
        return None

    mention, known = agreeing[0]
    distance = pronoun_offset - mention.offset

    # Confidence decays with distance and rises when gender was actually
    # checked rather than merely not contradicted.
    confidence = 0.85 if known != "n" and gender != "n" else 0.6
    if distance > max_distance / 2:
        confidence *= 0.8

    # An unambiguous single candidate is stronger evidence than picking the
    # nearest of several.
    rule = "unique_agreeing_antecedent" if len(agreeing) == 1 else "nearest_agreeing_antecedent"
    if len(agreeing) == 1:
        confidence = min(1.0, confidence + 0.1)

    return mention, confidence, rule


def group_mentions(
    mentions: list[Mention],
    spans: list[Span],
    *,
    timeline_id: str = "",
    min_confidence: float = 0.6,
) -> tuple[list[MentionGroup], list[PronounLink]]:
    """Build within-chapter mention groups by explicit chain-following.

    Mentions sharing a surface form are grouped first (safe within one chapter),
    then pronouns are attached to their antecedents.
    """
    by_surface: dict[str, list[Mention]] = {}
    for mention in mentions:
        if mention.alias_type is AliasType.RIGID_NAME:
            by_surface.setdefault(mention.text, []).append(mention)

    # Gender is inferred once per surface form from its local contexts.
    contexts_by_name: dict[str, list[str]] = {}
    for span in spans:
        for name in by_surface:
            if name in span.text:
                contexts_by_name.setdefault(name, []).append(span.text)
    genders = {name: infer_gender(name, ctx) for name, ctx in contexts_by_name.items()}

    groups: list[MentionGroup] = []
    group_by_mention: dict[str, MentionGroup] = {}
    for name, group_mentions_ in by_surface.items():
        group = MentionGroup(
            id=f"g{len(groups)}",
            mention_ids=[m.id for m in group_mentions_],
            label=name,
            timeline_id=timeline_id,
            rationale=["same_surface_form_within_chapter"],
        )
        groups.append(group)
        for mention in group_mentions_:
            group_by_mention[mention.id] = group

    links: list[PronounLink] = []
    for span in spans:
        if span.span_type in (SpanType.NON_DIEGETIC, SpanType.SYSTEM_WINDOW):
            continue
        for surface, offset, gender, number in find_pronouns(span.text, span.start):
            resolved = resolve_pronoun(offset, gender, number, mentions, genders=genders)
            if resolved is None:
                continue
            antecedent, confidence, rule = resolved
            if confidence < min_confidence:
                continue
            links.append(
                PronounLink(
                    pronoun=surface,
                    offset=offset,
                    antecedent_mention_id=antecedent.id,
                    antecedent_text=antecedent.text,
                    confidence=confidence,
                    rule=rule,
                )
            )

    return groups, links


#: Family terms only, not honorifics like "Master"/"Senior" that are used as
#: direct address to strangers as often as to kin, and not "brother"/"sister"/
#: "father"/"mother", which are common polite address to non-relatives in this
#: genre and would false-bind too often. Precision over recall, same as this
#: module's own stated rule: a missed kinship link costs one mention Phase 6
#: may still recover some other way; a wrong one corrupts an entity.
_KINSHIP_TERMS = frozenset({"uncle", "aunt", "grandfather", "grandmother", "grandpa", "grandma"})
_KINSHIP_RE = re.compile(r"\b(" + "|".join(_KINSHIP_TERMS) + r")\b", re.IGNORECASE)

#: How far *after* a kinship word a rigid name may start and still count as
#: naming it, in apposition ("his Uncle Gu Yue Dong Tu's eyebrows"). Small and
#: one-directional on purpose: "Uncle took in Fang Yuan" has a rigid name only
#: 20-odd characters after "Uncle" too, close enough for a symmetric distance
#: check to wrongly bind the whole rest of the chapter's "Uncle" to Fang Yuan
#: instead of Gu Yue Dong Tu -- caught by actually running this against real
#: chapter text, not by construction. Apposition is specifically "kinship word,
#: then the name, with nothing but a space/comma between" -- a name that is
#: merely the object of the sentence a few words later is not that.
_KINSHIP_APPOSITION_GAP = 3


def find_kinship_terms(text: str, base_offset: int = 0) -> list[tuple[str, int]]:
    """Locate bare third-person kinship words ("Uncle", "Aunt", ...).

    Unlike a name, these are never proposed as mention candidates upstream --
    the NER prompt explicitly rejects bare role words ("the guard", "the
    innkeeper") as descriptions rather than names, and a bare kinship word is
    the same shape. Found directly from span text instead, the same way
    `find_pronouns` finds pronouns without needing them pre-detected.
    """
    return [(m.group(1), base_offset + m.start()) for m in _KINSHIP_RE.finditer(text)]


def resolve_kinship_group(
    term_offset: int,
    term_end: int,
    term_block_index: int,
    mentions: list[Mention],
    *,
    established: Mention | None,
    block_text: str | None = None,
    apposition_gap: int = _KINSHIP_APPOSITION_GAP,
) -> tuple[Mention, float, str] | None:
    """Bind one kinship word occurrence to who it denotes.

    Three rules, tried in order:

    0. The kinship word is already the leading word of an existing rigid-name
       mention in the same block ("Uncle Gu Yue Dong Tu" detected whole, not
       as "Uncle" plus a separate "Gu Yue Dong Tu") -- the honorific-stripping
       in `ingest/normalize.py` only ever affects *comparison* keys, never
       what actually gets stored as a mention's surface, so a name detected
       with its honorific attached is the common case, not the exception.
       This occurrence is already covered by that mention, so the caller
       should not mint a second, redundant one for it -- only record the
       binding.
    1. A rigid name immediately following this occurrence, in apposition,
       establishes (or reinforces) the binding -- "his Uncle Gu Yue Dong Tu's
       eyebrows". Must start right after the word ends (`apposition_gap`),
       not merely somewhere nearby: "Uncle took in Fang Yuan" has a rigid name
       a similar distance away but is not naming who "Uncle" is. Also must sit
       in the *same block*: `Mention.offset` is block-local (see its own
       docstring), so comparing raw offsets across two different blocks
       compares two unrelated coordinate origins and can match purely by
       coincidence -- found by actually running this against a real chapter,
       where it bound "Uncle" to whatever character's name happened to have a
       numerically-close offset in a completely different paragraph.
    2. Otherwise, reuse whichever antecedent this kinship word was last bound
       to earlier in the chapter. This is the case that actually matters: a
       kinship word recurring through a scene almost never has a name next to
       it after the first use ("Uncle heaved a sigh", "Uncle's cold voice
       emerged") -- the text already said who it is once, same as a pronoun
       does not repeat its antecedent's name either. Lower confidence than
       rule 1 since it is one step further from the text.

    The third element of the return tuple is the rule name; the caller uses
    `"kinship_fused"` specifically to know not to mint a redundant mention for
    an occurrence rule 0 covers.
    """
    fused = [
        m
        for m in mentions
        if m.alias_type is AliasType.RIGID_NAME
        and m.block_index == term_block_index
        and m.offset == term_offset
    ]
    if fused:
        return fused[0], 0.9, "kinship_fused"
    def _is_apposed(m: Mention) -> bool:
        if not (0 <= m.offset - term_end <= apposition_gap):
            return False
        if block_text is None:
            return True
        # The gap must be pure whitespace. "uncle, Fang Yuan laughed" has a
        # rigid name only 2 characters after "uncle" too -- a character-count
        # gap alone cannot tell that apart from "Uncle Gu Yue Dong Tu"'s
        # single space, and the comma is exactly the signal that the name
        # starts a new clause rather than naming who "uncle" is. Found by
        # actually running this against real chapters, again: "his aunt and
        # uncle, Fang Yuan laughed" bound every "aunt"/"uncle" in two whole
        # chapters to the protagonist before this check existed.
        return block_text[term_end:m.offset].strip() == ""

    apposed = [
        m
        for m in mentions
        if m.alias_type is AliasType.RIGID_NAME
        and m.block_index == term_block_index
        and _is_apposed(m)
    ]
    if apposed:
        apposed.sort(key=lambda m: m.offset)
        return apposed[0], 0.85, "kinship_apposed_name"
    if established is not None:
        return established, 0.55, "kinship_sticky_binding"
    return None


def most_informative_label(mentions: list[Mention]) -> str:
    """Pick the surface form that best identifies a group.

    Longest rigid name wins: "Sect Master Wang Lin" identifies its holder more
    precisely than "Wang", and the label is what Phase 6 retrieves against.
    """
    rigid = [m.text for m in mentions if m.alias_type is AliasType.RIGID_NAME]
    if rigid:
        return max(rigid, key=len)
    return mentions[0].text if mentions else ""


def present_cast(mentions: list[Mention]) -> set[str]:
    """Entities physically present, for co-presence checks and panel casting.

    Uses `reference_mode`, so a character merely *named* in dialogue is
    excluded. Without this a scene that mentions nine characters is treated as
    containing nine.
    """
    return {
        m.text
        for m in mentions
        if m.reference_mode is ReferenceMode.PRESENT
    }
