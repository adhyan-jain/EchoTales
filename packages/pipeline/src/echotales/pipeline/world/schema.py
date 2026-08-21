"""What the graph should know about every entity, by kind.

`resolve/appearance_extract.py` answers one question -- what does a person
look like -- and nothing answers any of the others. The graph already types
its entities (`TargetKind.LOCATION`, `ORGANIZATION`, `ITEM`, added by Section 10
item 5) and already has a temporal fact table to hang answers on, and on a
real Reverend Insanity database that machinery holds **10 locations and 35
organisations with zero facts attached to any of them**. Qing Mao Mountain,
Gu Yue Village and the South Border are resolved, named, and completely
undescribed.

That gap is why `persona/attire.py` ended up carrying hand-written
`SCENE_LOCALES` and `FACTION_ATTIRE` tables: with nothing extracted, the
visual pipeline had to invent generic courtyards and guess a clan's colours.
Those tables are a workaround for this module not existing, and once it
runs they become a fallback rather than the source.

**Vocabularies are per kind, and closed.** An open-ended "tell me about this
entity" produces prose that cannot be queried, compared, or rendered into a
prompt. A fixed key set per kind gives `state_of` something to return and
image generation something to bind, and lets an off-vocabulary answer be
discarded the way `persona/extract.py` already discards one.

**Every key here is a *standing* property**, deliberately. Facts that change
-- a rank advancing, a character dying, a clan losing its territory -- are
handled by the temporal fact model rather than by overwriting: each
attestation lands as its own `Attribute` row dated to the chapter that
states it, so `state_of(..., position)` can answer "what was true then".
"""

from __future__ import annotations

from echotales.core.enums import TargetKind

#: What to know about a person, beyond how they look.
#:
#: Deliberately excludes appearance: that is
#: `resolve/appearance_extract.py`'s vocabulary and belongs on the PERSONA
#: (the body), while these belong on the SELF (the continuity of
#: consciousness) -- the split `architecture.md Section 4` draws and the one
#: `models.Attribute` routes on.
PERSON_KEYS: tuple[str, ...] = (
    "role",
    "cultivation_rank",
    "faction",
    "titles",
    "status",
    "abilities",
    "personality",
    "goals",
    "origin",
    "reputation",
)

#: What to know about a place. Weighted toward what a panel needs to draw
#: it, because a location's whole downstream job here is to be rendered.
LOCATION_KEYS: tuple[str, ...] = (
    "place_type",
    "terrain",
    "architecture",
    "atmosphere",
    "region",
    "controlling_faction",
    "notable_features",
)

#: What to know about a faction, sect or clan. `colors_attire` exists
#: because it is what `persona/attire.py`'s faction tier wants and currently
#: has to be hand-seeded per novel.
ORGANIZATION_KEYS: tuple[str, ...] = (
    "org_type",
    "purpose",
    "territory",
    "colors_attire",
    "hierarchy",
    "reputation",
    "notable_members",
)

#: What to know about an object. Items are drawn (the Spring Autumn Cicada
#: is a cicada, and glows), so appearance leads.
ITEM_KEYS: tuple[str, ...] = (
    "item_type",
    "appearance",
    "powers",
    "owner",
    "origin",
    "significance",
)

KEYS_BY_KIND: dict[TargetKind, tuple[str, ...]] = {
    TargetKind.SELF: PERSON_KEYS,
    TargetKind.LOCATION: LOCATION_KEYS,
    TargetKind.ORGANIZATION: ORGANIZATION_KEYS,
    TargetKind.ITEM: ITEM_KEYS,
}

#: Human-readable guidance per key, quoted into the extraction prompt.
#: Without it a model reads "origin" differently for a person (where they
#: were born) than for an item (who forged it), and both readings are
#: defensible -- so the prompt states which one is wanted.
KEY_HINTS: dict[str, str] = {
    # person
    "role": "what they do in the story (protagonist, clan elder, hunter)",
    "cultivation_rank": "their cultivation stage or rank, exactly as stated",
    "faction": "the clan, sect or group they belong to",
    "titles": "titles or epithets they are addressed by",
    "status": "alive, dead, missing, exiled, imprisoned",
    "abilities": "named techniques, powers or skills they use",
    "personality": "how they behave, in a few words",
    "goals": "what they are trying to achieve",
    "origin": "where they are from, or their background",
    "reputation": "how others regard them",
    # location
    "place_type": "village, mountain, city, cave, sect grounds, region",
    "terrain": "the landscape: peaks, forest, river, plains",
    "architecture": "what the buildings look like, if any",
    "atmosphere": "the mood of the place: bleak, bustling, sacred",
    "region": "the larger area it sits in",
    "controlling_faction": "who holds or rules it",
    "notable_features": "landmarks or distinctive things found there",
    # organization
    "org_type": "clan, sect, faction, alliance, army",
    "purpose": "what the group exists to do",
    "territory": "where it holds power",
    "colors_attire": "the robes, colours or emblems its members wear",
    "hierarchy": "its ranks or internal structure",
    "notable_members": "characters belonging to it",
    # item
    "item_type": "weapon, Gu worm, treasure, tool, manual",
    "appearance": "what it physically looks like",
    "powers": "what it does",
    "owner": "who holds or uses it",
    "significance": "why it matters to the story",
}


def keys_for(kind: TargetKind) -> tuple[str, ...]:
    """The fact vocabulary for an entity of this kind, or empty if unknown.

    `PERSONA` returns empty on purpose: bodies are described by
    `appearance_extract`, and returning the person vocabulary here would
    duplicate every fact onto both halves of the self/persona split.
    """
    return KEYS_BY_KIND.get(kind, ())
