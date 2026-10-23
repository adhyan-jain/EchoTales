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

import re






_DEFAULT_STYLE = "web-novel illustration, no further style data seeded for this novel"


def _genre(novel_id: str):  # -> GenreProfile
    """The novel's genre profile (`persona/genre.py`), the fallback for every per-novel table below.

    Every lookup here used to fall back to Reverend Insanity's own value for a novel the table did not list, so ORV's
    reference sheets were drawn in hanfu and every new project was drawn as a Chinese cultivation novel.
    """
    from echotales.pipeline.persona.genre import profile

    return profile(novel_id)


def _genre_named(name: str):  # -> GenreProfile
    from echotales.pipeline.persona.genre import GENRES

    return GENRES[name]


_DEFAULT_WORLD = "detailed background environment"






def setting_first(novel_id: str) -> bool:
    """Whether this novel's image prompts rank the place and key objects above mood and quality tags (`genre.py`)."""
    return _genre(novel_id).setting_first


def style_anchor(novel_id: str) -> str:
    """The short tier-0 genre/rendering anchor for this novel.

    Falls back to the novel's genre profile (`persona/genre.py`) for an unmapped `novel_id`; it used to fall back to
    RI's own value, which drew every unlisted novel as xianxia.
    """
    return _genre(novel_id).style_anchor


def manga_base(novel_id: str) -> str:
    """The fuller style/rendering block for this novel. See `style_anchor`."""
    return _genre(novel_id).manga_base






def reference_anchor(novel_id: str) -> str:
    """The short reference-sheet framing/medium anchor for this novel."""
    return _genre(novel_id).reference_anchor


def reference_style(novel_id: str) -> str:
    """The fuller reference-sheet style block for this novel."""
    return _genre(novel_id).reference_style




def hands_default_clause(novel_id: str) -> str:
    """The genre-appropriate hands-concealed fallback for this novel."""
    return _genre(novel_id).hands_clause



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
    # A bedroom needs its own cue: LotM chapter 1 is a bedroom scene and had none, so it fell through to "wood"
    # (see `scene_locale`) and was filed under a forest. Only books whose locale table has a "bedroom" key use these.
    "bedroom": "bedroom", "bed": "bedroom", "pillow": "bedroom", "blanket": "bedroom", "mattress": "bedroom",
}


#: How much one whole-word hit counts, for the non-xianxia books. A place-defining word outweighs a material or a
#: generic one: "bed" says where a scene is, "wood" is what a thing is made of (a forest says "forest", "woods" or
#: "trees"), and "inside" is in nearly every
#: interior and every thought ("inside his head"), so it says nothing.
_CUE_WEIGHT: dict[str, float] = {
    "bedroom": 3.0, "bed": 3.0, "pillow": 2.0, "blanket": 2.0, "mattress": 2.0,
    "wood": 0.0, "clan": 0.5, "inside": 0.0,
    # "his temples" is a body part ("a throbbing pain in his temples", LotM ch1 block 3), not a building.
    "temple": 0.5,
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
    locales = _genre(novel_id).scene_locales
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
    # Whole-word cues for the non-xianxia books: a substring count read "wooden" in "a low wooden bed" as a forest cue
    # and stapled "a moonlit moor, low cloud" onto every panel of a night-time bedroom (LotM render review,
    # 2026-10-18). Reverend Insanity keeps the substring count its locales were tuned with. A cue for a place this
    # book's table does not have is skipped rather than raising later on `locales[key]`.
    whole_words = setting_first(novel_id)
    for cue, key in _LOCALE_CUES.items():
        if key not in locales:
            continue
        if whole_words:
            hits = len(re.findall(rf"\b{re.escape(cue)}(?:s|es)?\b", low)) * _CUE_WEIGHT.get(cue, 1.0)
        else:
            hits = low.count(cue)
        if hits:
            scores[key] = scores.get(key, 0) + hits
    if whole_words:
        # One ambiguous word is not evidence of a place: require a full point, so a scene whose only hit is
        # "temples" or "wood" counts as having no cue and inherits the chapter's place (`panels.py`).
        scores = {key: score for key, score in scores.items() if score >= 1.0}

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


#: Cue words for a hostile, surrounded confrontation, grounded in RI ch1's
#: actual opening siege text -- "Enemies surrounded him all around; there
#: was already no way out" (block 8), "the major factions of justice...
#: heavily surrounded Fang Yuan" (block 12), "this place is already
#: covered in inescapable nets" (block 1) -- not invented, same citation
#: discipline as `WORLD_CONTEXT`. **This is not a missing `SCENE_LOCALES`
#: bucket.** `scene_locale()` already correctly cue-matches "mountain" for
#: this exact text (block 6's "mountain breeze", block 14's "side of the
#: mountain") -- verified directly, not assumed. The real gap is that
#: "a narrow mountain path, pine and mist, cliffs falling away" describes
#: the physical setting accurately but reads as a serene nature scene, not
#: a siege, however correct the location itself is. An orthogonal mood
#: modifier (same shape as the night/day check above) fixes that without
#: making a new locale bucket compete with "mountain" for cue-matching
#: priority, which a same-scored word list would do.
_HOSTILITY_CUES: tuple[str, ...] = ("surrounded", "no way out", "inescapable")


def hostile_confrontation_modifier(text: str) -> str:
    """A short atmosphere clause when the text marks a hostile, surrounded
    confrontation, else `""`. Layered onto whatever locale/crowd content a
    caller already has -- not a replacement for `scene_locale()`'s own
    location text."""
    low = text.lower()
    if any(cue in low for cue in _HOSTILITY_CUES):
        # No "weapons drawn"/"blades" wording: this novel's
        # `GENRE_MISMATCH_PROPS` negative-prompts sword/blade imagery
        # specifically because the text never supports it (moonblade
        # attacks, not swords) -- asserting it here would fight that
        # negative clause instead of cooperating with it.
        return "hostile, closing in, tense standoff"
    return ""


def world_setting(novel_id: str) -> str:
    """The scenery vocabulary for this novel's world."""
    return _genre(novel_id).world_setting


def world_context(novel_id: str) -> str:
    """The novel's *specific* visual signature -- power system, named
    locations, faction identity -- as distinct from `world_setting`'s
    generic scenery vocabulary.

    Setting/atmosphere register only: this must never reach the
    identity/condition tier, which is why it is threaded through
    `direction.build_prompt`'s `novel_style` line rather than the cast
    clause. Empty for a novel with no seeded entry rather than falling
    back to `_DEFAULT_WORLD` -- an absent primer should mean "say
    nothing extra", not "describe a generic environment twice".
    """
    return _genre(novel_id).world_context



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
    # A named non-East-Asian genre gets no hair/eye default rather than the East Asian fallback below.
    prof = _genre(novel_id)
    defaults = prof.appearance if prof.appearance or prof is not _genre_named("generic") else _FALLBACK_APPEARANCE
    out = dict(defaults)
    out.update({k: v for k, v in stated.items() if v})
    return out


def resolve_attire(novel_id: str, *, explicit: str | None = None) -> str:
    """What a character wears: the attire already resolved from the book, else the genre's house style.

    The faction, rank and region tiers were hand-written tables keyed by three novel ids, so any other book skipped
    them (product plan step 2, 2026-10-24). A faction or rank the reader extracts from the text arrives as `explicit`.
    The last tier is an instruction about how to draw, not a garment; it only keeps an undescribed character from
    being drawn with nothing at all.
    """
    if explicit:
        return explicit
    return _genre(novel_id).novel_style
