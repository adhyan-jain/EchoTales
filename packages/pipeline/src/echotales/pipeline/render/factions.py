"""Whose elders are these?

A role word is only half a description. "Elders discuss worriedly" is what
the director wrote for RI ch1, and it is accurate and useless: this novel
runs the same word past the Gu Yue clan, the Bai clan, the Xiong clan and
later a dozen sects, all in one volume, and a picture of unspecified elders
is a picture that cannot be consistent with any of them. Worse, nothing
stops two different clans' elders from being drawn identically in adjacent
chapters, which reads as a continuity error rather than as vagueness.

The graph would be the right source for this and currently cannot answer
it: RI's chapter 1 has no resolved ORGANIZATION mention at all (the first
is chapter 4), while the prose says "Gu Yue Village" and "the Gu Yue clan
head" repeatedly. So the faction is read from the scene's own text, by the
naming convention the genre uses without exception -- `<Name> Clan`,
`<Name> Sect`, `<Name> Village`. That is a weaker source than resolution
and it is honest about it: no match means the role word stays unqualified,
which is where it started.

**Scoped to the scene, deliberately.** The faction a role word belongs to
is a property of where the camera is standing, not of the novel: when Fang
Yuan leaves the Gu Yue clan, "the elders" means his hosts' elders from that
scene onward, with no rule to update anywhere.
"""

from __future__ import annotations

import re
from collections import Counter

#: `Gu Yue Clan`, `Bai Village`, `Spirit Affinity Sect`. The name may be
#: several capitalised words; the kind word may be capitalised or not,
#: since translations vary ("the Gu Yue clan head").
_FACTION_RE = re.compile(
    r"\b((?:[A-Z][a-z]+\s+){1,3})"
    # The kind word matches in either case -- translations write "the Gu
    # Yue clan head" beside "Gu Yue Village", and requiring a capital here
    # missed every lowercase one, which is most of them.
    r"(?i:(clan|sect|village|alliance|hall|academy))\b"
)

#: Role words worth qualifying. A word not in here is left alone: "warriors"
#: or "villagers" gain nothing from a clan name, while an elder, a guard or
#: a disciple is defined by whose they are.
#: Nudges `scene_faction` toward the organisation rather than the place.
#: Small on purpose: it settles ties between two names for one faction, and
#: must not let a passing mention of a sect outrank the clan whose hall the
#: scene is actually set in.
_KIND_BONUS: dict[str, float] = {"clan": 0.5, "sect": 0.5, "alliance": 0.25}

QUALIFIABLE_ROLES: frozenset[str] = frozenset(
    {"elder", "elders", "disciple", "disciples", "guard", "guards",
     "clan head", "clan leader", "sect master", "members", "cultivators"}
)


def scene_faction(text: str) -> str:
    """The dominant faction named in this stretch of prose, or "".

    Most-mentioned wins, and the returned string keeps the kind word in the
    novel's own vocabulary ("Gu Yue clan", not "Gu Yue") so a prompt can use
    it directly. A tie is broken by first appearance, which for a scene is
    almost always the faction whose ground it opens on.
    """
    # Kind words, most specific first. One place is named both ways in the
    # same scene -- RI ch1 has "Gu Yue Village" and "the Gu Yue clan head"
    # two blocks apart -- and "Gu Yue clan elders" is what a reader would
    # say, so the organisation wins over the settlement it lives in.
    counts: Counter[str] = Counter()
    order: dict[str, int] = {}
    for position, match in enumerate(_FACTION_RE.finditer(text)):
        name = " ".join(match.group(1).split())
        # "The Gu Yue clan" -- the article is part of the capitalised run
        # when a sentence starts on it, and reads wrong inside a prompt.
        if name.split()[0] in ("The", "A", "An", "His", "Her", "Their", "Our"):
            name = " ".join(name.split()[1:])
        if not name:
            continue
        kind = match.group(2).lower()
        label = f"{name} {kind}"
        counts[label] += 1
        order.setdefault(label, position)

    if not counts:
        return ""
    best = max(
        counts,
        key=lambda label: (
            counts[label] + _KIND_BONUS.get(label.rsplit(" ", 1)[1], 0),
            -order[label],
        ),
    )
    return best


#: Region words that distinguish two same-named factions. The genre names
#: its geography as consistently as its organisations.
_REGION_RE = re.compile(
    r"\b((?:[A-Z][a-z]+\s+){1,3})(?i:(mountain|mountains|ridge|valley|"
    r"plains|province|region|city|kingdom|continent))\b"
)


def scene_region(text: str) -> str:
    """The geography this scene sits in, or "".

    **Two clans can share a name.** After Qing Mao mountain's three clans
    are destroyed, Reverend Insanity introduces a *different* Bai clan
    elsewhere, and nothing in the words "Bai clan" separates them. A reader
    disambiguates by where they are standing; so does this.
    """
    for match in _REGION_RE.finditer(text or ""):
        name = " ".join(match.group(1).split())
        if name.split()[0] in ("The", "A", "An"):
            name = " ".join(name.split()[1:])
        if name:
            return f"{name} {match.group(2).lower()}"
    return ""


def faction_key(faction: str, region: str) -> str:
    """A stable identity for a faction, distinguishing same-named ones.

    Not used in prompts -- a prompt wants "Bai clan", not
    "Bai clan@Qing Mao mountain". This is the handle for anything that must
    not merge two organisations: continuity of dress and insignia across
    chapters, and eventually a graph entity per faction.
    """
    if not faction:
        return ""
    return f"{faction}@{region}" if region else faction


def qualify_role(role: str, faction: str) -> str:
    """"elders" + "Gu Yue clan" -> "Gu Yue clan elders"."""
    if not faction:
        return role
    stripped = role.strip().casefold()
    if stripped not in QUALIFIABLE_ROLES:
        return role
    # Already carries a faction ("Gu Yue clan elders" from the prose).
    if faction.casefold() in stripped:
        return role
    return f"{faction} {role.strip()}"
