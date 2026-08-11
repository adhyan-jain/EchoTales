"""4-tier visual-prompt fallback chain (xyz.md Step 4).

    explicit persona trait -> faction attire default -> regional aesthetic
    default -> novel general style

Per-novel, hand-seeded tables rather than graph-backed facts -- `TargetKind`
(`core/enums.py`) only has `SELF`/`PERSONA`/`MOB_GROUP`, so a faction or a
region has no row it could attach an `Attribute` to without a schema change
(the same gap HANDOFF §10 item 5 already flags for item/location entities).
Keeping this as a static lookup is the same "lightest thing that could work"
call `spans/scene.py::detect_mobs` already made for background crowds: real
data, scoped to what actually needs it, no migration risk.
"""

from __future__ import annotations

#: novel_id -> faction name (lowercased) -> attire description.
FACTION_ATTIRE: dict[str, dict[str, str]] = {
    "reverend-insanity": {
        "gu yue clan": "green and brown silk cultivator robes with a silver clan emblem",
        "white province": "plain grey hemp robes, minimal ornamentation",
    },
}

#: novel_id -> region name (lowercased) -> aesthetic description.
REGIONAL_AESTHETIC: dict[str, dict[str, str]] = {
    "reverend-insanity": {
        "southern border": "mountainous cultivation-sect robes, bamboo accessories",
    },
}

#: novel_id -> fallback house style when nothing more specific is known.
NOVEL_STYLE: dict[str, str] = {
    "reverend-insanity": "xianxia web-novel illustration, Gu-worm era Chinese fantasy",
    "lord-of-the-mysteries": "Victorian gaslamp fantasy, muted desaturated palette",
    "omniscient-readers-viewpoint": "modern Korean urban apocalypse, high contrast",
}

_DEFAULT_STYLE = "web-novel illustration, no further style data seeded for this novel"


def resolve_attire(
    novel_id: str,
    *,
    explicit: str | None = None,
    faction: str | None = None,
    region: str | None = None,
) -> str:
    """Walk the 4-tier chain and return the first tier that has an answer.

    `explicit` is whatever the caller already resolved for this specific
    character (a persona attribute, if one exists -- see the package
    docstring for why that's usually `None` today). `faction`/`region` are
    plain names, looked up case-insensitively against the tables above.
    """
    if explicit:
        return explicit
    if faction:
        hit = FACTION_ATTIRE.get(novel_id, {}).get(faction.strip().lower())
        if hit:
            return hit
    if region:
        hit = REGIONAL_AESTHETIC.get(novel_id, {}).get(region.strip().lower())
        if hit:
            return hit
    return NOVEL_STYLE.get(novel_id, _DEFAULT_STYLE)
