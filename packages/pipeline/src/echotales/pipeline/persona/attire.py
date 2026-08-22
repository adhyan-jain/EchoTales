"""5-tier visual-prompt fallback chain (xyz.md Step 4).

    explicit persona trait -> faction attire default -> rank attire default
    -> regional aesthetic default -> novel general style

Per-novel, hand-seeded tables rather than graph-backed facts -- `TargetKind`
(`core/enums.py`) only has `SELF`/`PERSONA`/`MOB_GROUP`, so a faction or a
region has no row it could attach an `Attribute` to without a schema change
(the same gap HANDOFF Section 10 item 5 already flags for item/location entities).
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

#: novel_id -> rank keyword (lowercased) -> attire description, checked as a
#: substring of whatever rank text the caller has (a title like "Dark Hall
#: Elder" or a `rank_insignia` appearance attribute) -- ranks are rarely
#: stated as the bare keyword alone, so an exact-match lookup would miss
#: almost everything a real title contains.
#:
#: Sits between faction and region: a character's rank is closer to their
#: own identity than the region they happen to be standing in, but a named
#: faction (when known) still says more about what they'd actually wear than
#: a generic rank bucket does.
RANK_ATTIRE: dict[str, dict[str, str]] = {
    "reverend-insanity": {
        "elder": "aged sect elder's formal robes, dark trim, walking staff",
        "sect master": "ornate sect master's ceremonial robes, sect crest prominent",
        "disciple": "simple disciple's robes in sect colours, plain sash",
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

#: The world a panel is set in, per novel.
#:
#: **Distinct from `NOVEL_STYLE`, which is a drawing style, not a place.**
#: That distinction was invisible until real panels came out: the panel
#: prompt's "environment" slot was being filled by `resolve_attire`, whose
#: last tier returns `"xianxia web-novel illustration, Gu-worm era Chinese
#: fantasy"` -- an instruction about *how to draw*, containing nothing about
#: where anyone is standing. The result was characters floating on abstract
#: ink swirls with no world behind them.
#:
#: These are scenery nouns on purpose. A diffusion model draws a courtyard
#: when told "stone courtyard"; it draws nothing recognisable when told
#: "Chinese fantasy". Kept per novel because the settings genuinely differ
#: -- RI's cultivation villages and ORV's collapsing Seoul share no
#: architecture at all.
WORLD_SETTING: dict[str, str] = {
    "reverend-insanity": (
        "ancient Chinese cultivation world, stone courtyards, timber halls "
        "with upturned tiled roofs, bamboo groves, terraced mountain "
        "villages, mist over jagged peaks, stone steps, paper lanterns"
    ),
    "lord-of-the-mysteries": (
        "Victorian gaslamp city, cobbled streets, wrought-iron street lamps, "
        "brick townhouses, fog, horse-drawn carriages, cathedral spires"
    ),
    "omniscient-readers-viewpoint": (
        "modern Seoul in collapse, subway tunnels, cracked asphalt, "
        "toppled high-rises, overturned cars, rebar and rubble, ash sky"
    ),
}

_DEFAULT_WORLD = "detailed background environment"

#: Concrete locales per novel, keyed by a cue word that suggests them.
#: `world_setting` is the world's general vocabulary; these are *places*, and
#: a panel needs one specific place rather than a list of everything the
#: world contains.
SCENE_LOCALES: dict[str, dict[str, str]] = {
    "reverend-insanity": {
        "hall": "inside a timber clan hall, carved pillars, hanging banners",
        "courtyard": "a walled stone courtyard, flagstones, low roofs beyond",
        "mountain": "a narrow mountain path, pine and mist, cliffs falling away",
        "cave": "a damp stone cave, rough walls, torchlight",
        "village": "a terraced hillside village, tiled roofs, stone steps",
        "forest": "a dense bamboo grove, shafts of light",
        "night": "a moonlit courtyard at night, deep shadows, paper lanterns",
        "night_wild": "a dark forest clearing under moonlight, twisted branches",
    },
    "lord-of-the-mysteries": {
        "hall": "a panelled Victorian study, bookshelves, oil lamp",
        "courtyard": "a fog-bound cobbled square, iron railings",
        "mountain": "a bleak coastal cliff, grey sky",
        "cave": "a brick undercroft, dripping arches, lantern light",
        "village": "a narrow terraced street, chimney pots, gaslight",
        "forest": "a bare winter wood, mist between trunks",
        "night": "a gaslit street at night, long shadows, fog",
        "night_wild": "a moonlit moor, low cloud",
    },
}

#: Cue word -> locale key. Checked against the block's own text, so the
#: setting suits the scene rather than being decided by a coin flip.
_LOCALE_CUES: dict[str, str] = {
    "hall": "hall", "chamber": "hall", "throne": "hall", "inside": "hall",
    # RI ch1's ancestral-hall scene never says "hall" outside one interior
    # line -- the walk-out and discussion blocks say "ancestral temple" /
    # "sacred temple" instead (Section 4.31 item 11), which the cue table missed
    # entirely.
    "temple": "hall",
    "courtyard": "courtyard", "gate": "courtyard", "yard": "courtyard",
    "mountain": "mountain", "peak": "mountain", "cliff": "mountain",
    "slope": "mountain", "ridge": "mountain",
    "cave": "cave", "cavern": "cave", "tunnel": "cave", "underground": "cave",
    "village": "village", "town": "village", "street": "village",
    "market": "village", "clan": "village",
    "forest": "forest", "bamboo": "forest", "trees": "forest", "wood": "forest",
}


def scene_locale(
    novel_id: str, beat: str, *, block_index: int = 0, strict: bool = False
) -> str:
    """A specific place for this panel to happen in.

    **Cue-matched where the prose suggests somewhere, varied where it does
    not.** A panel with no stated setting still has to happen *somewhere*;
    falling back to the world's general vocabulary produced characters on
    abstract ink, and falling back to one fixed locale would make every
    unstated block the same courtyard. So an unmatched block rotates
    through the novel's locales by block index -- varied across a chapter,
    yet identical on a re-render, which matters because panels are cached
    and a re-run must not silently redecorate the chapter.

    `strict=True` disables that rotation and returns `""` on no cue match
    instead. For `render/scenes.py`'s boundary detection, not panel
    generation: the rotation exists specifically to make two *unrelated*
    unstated blocks look different, which is exactly backwards for "did
    the location actually change" -- confirmed directly, not guessed:
    treating the rotating fallback as a real signal turned a 92-block RI
    chapter into 78 one-block "scenes," since almost every block without
    an explicit cue rotated to a different locale than its neighbour by
    sheer block-index arithmetic.
    """
    locales = SCENE_LOCALES.get(novel_id)
    if not locales:
        return ""

    low = beat.casefold()

    # **Weigh the cues, do not take the first one that appears.** This is
    # called once per *scene* now, not once per block, so the text is long
    # enough that several unrelated cues almost always occur somewhere in
    # it -- and first-match simply returned whichever key happened to sit
    # earliest in the dict. Measured on RI ch1's opening siege, which is
    # stated as a mountaintop over and over ("Qing Mao Mountain", "the
    # mountain rock beneath his feet", "the mountain breeze") and still
    # resolved to a bamboo grove because a single "bamboo" appeared first.
    scores: dict[str, int] = {}
    for cue, key in _LOCALE_CUES.items():
        hits = low.count(cue)
        if hits:
            scores[key] = scores.get(key, 0) + hits

    # Night only when the text actually reads as night, not when the word
    # occurs anywhere in it. Block 18's *poem* ("the morning is fine like
    # hair and night is like...") flipped that panel to a moonlit forest
    # while its own prose said "looking at the setting sun".
    night_words = ("night", "midnight", "moonlight", "moonlit", "starlight")
    day_words = ("sun", "sunset", "sunlight", "dawn", "morning", "daylight", "afternoon")
    night = sum(low.count(w) for w in night_words) > sum(low.count(w) for w in day_words)

    if scores:
        key = max(scores, key=lambda k: scores[k])
        if night and key in ("courtyard", "village"):
            return locales.get("night", locales[key])
        if night and key in ("forest", "mountain"):
            return locales.get("night_wild", locales[key])
        return locales[key]

    if strict:
        return ""

    if night:
        return locales.get("night", "")

    ordered = [v for k, v in sorted(locales.items()) if not k.startswith("night")]
    return ordered[block_index % len(ordered)] if ordered else ""


def world_setting(novel_id: str) -> str:
    """The scenery vocabulary for this novel's world."""
    return WORLD_SETTING.get(novel_id, _DEFAULT_WORLD)


#: Per-novel appearance defaults, filling attributes the prose never states.
#:
#: **A default is not a guess, and it is not randomness.** The text of a
#: Chinese cultivation novel does not stop to say its characters have black
#: hair for the same reason an English novel does not say its characters
#: have two hands -- it is assumed. Leaving those fields empty hands the
#: choice to the diffusion model, which invents a *different* answer per
#: panel and produces exactly the chapter-to-chapter drift the reference
#: sheet exists to prevent. A stated-once default is stable, correct far
#: more often than not, and always overridden by anything the text
#: actually says (`resolve_appearance` applies it last).
#:
#: Keyed per novel rather than globally because the setting decides: RI and
#: ORV are East Asian, LOTM is Victorian-European pastiche, and giving all
#: three the same hair is how a background crowd ends up looking wrong.
APPEARANCE_DEFAULTS: dict[str, dict[str, str]] = {
    "reverend-insanity": {
        "hair_color": "black",
        "eye_color": "dark brown",
        "skin_tone": "fair",
    },
    "omniscient-readers-viewpoint": {
        "hair_color": "black",
        "eye_color": "dark brown",
        "skin_tone": "fair",
    },
    "lord-of-the-mysteries": {
        "hair_color": "brown",
        "eye_color": "grey",
        "skin_tone": "pale",
    },
}

#: Used when a novel has no seeded table. Deliberately the East Asian
#: default: this pipeline's target corpus is predominantly translated
#: Chinese/Korean web fiction (HANDOFF Section 1), so it is the majority case
#: rather than a neutral one.
_FALLBACK_APPEARANCE = {
    "hair_color": "black",
    "eye_color": "dark brown",
}


def resolve_appearance(novel_id: str, stated: dict[str, str]) -> dict[str, str]:
    """Fill unstated appearance fields with this novel's defaults.

    Anything the text stated wins outright -- this only ever adds keys, and
    never overwrites one that came from the prose.
    """
    defaults = APPEARANCE_DEFAULTS.get(novel_id, _FALLBACK_APPEARANCE)
    out = dict(defaults)
    out.update({k: v for k, v in stated.items() if v})
    return out


def resolve_attire(
    novel_id: str,
    *,
    explicit: str | None = None,
    faction: str | None = None,
    rank: str | None = None,
    region: str | None = None,
) -> str:
    """Walk the 5-tier chain and return the first tier that has an answer.

    `explicit` is whatever the caller already resolved for this specific
    character (a persona attribute, if one exists -- see the package
    docstring for why that's usually `None` today). `faction`/`rank`/
    `region` are plain text, looked up case-insensitively against the
    tables above -- `rank` as a substring match (see `RANK_ATTIRE`), the
    other two exact.

    The bottom of the old 4-tier chain (`NOVEL_STYLE`) is an instruction
    about *how to draw*, not a garment -- correct as a style suffix, wrong
    as an attire clause for an undescribed character. `rank` gives one more
    real tier before falling back to that: a character with no extracted
    attire and no known faction usually still has a stated or inferable
    rank ("Elder", "Disciple"), and that says far more about what they'd
    plausibly wear than the novel's overall drawing style does.
    """
    if explicit:
        return explicit
    if faction:
        hit = FACTION_ATTIRE.get(novel_id, {}).get(faction.strip().lower())
        if hit:
            return hit
    if rank:
        low = rank.strip().lower()
        for keyword, hit in RANK_ATTIRE.get(novel_id, {}).items():
            if keyword in low:
                return hit
    if region:
        hit = REGIONAL_AESTHETIC.get(novel_id, {}).get(region.strip().lower())
        if hit:
            return hit
    return NOVEL_STYLE.get(novel_id, _DEFAULT_STYLE)
