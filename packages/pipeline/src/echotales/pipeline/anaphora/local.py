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
