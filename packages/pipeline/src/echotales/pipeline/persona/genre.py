"""Visual genre profiles: the style vocabulary image generation uses when a novel has no hand-tuned entry.

`attire.py`'s per-novel tables (style anchor, manga base, reference sheet, hands clause, world, locales, props) were
written for Reverend Insanity first and every lookup fell back to RI's value for a novel it did not list. Lord of the
Mysteries got its own entries and stopped coming out xianxia; Omniscient Reader's Viewpoint got three of the seven
and still drew hanfu reference sheets and sleeve-hidden hands in modern Seoul; and every new project (any id the
tables do not name) was drawn as a Chinese cultivation novel. A profile carries the whole vocabulary for one genre,
so a novel is described by naming its genre, and a per-novel table entry, where one exists, still wins.

The genre is a project property (`novel.visual_genre`), set from the Settings page or `POST /api/projects/<id>/genre`, and
`detect_genre` proposes one from the book's own words when none is set. `use_store_genre` registers it for the
process before a render or a reference run, because every `attire.py` lookup takes only a `novel_id`.

The xianxia and Victorian profiles take RI's and LotM's drawing-style entries verbatim, so neither novel's prompts
change; facts true of one book only (RI's Gu and moonblades-not-swords, LotM's Beyonder potions) stay in that novel's
own `attire.py` entries, since swords are ordinary in most xianxia. The modern-apocalypse profile completes ORV from
counts in its own text (data/db/omniscient-readers-viewpoint.db, 85,419 words): constellation 351, coin 263,
scenario 232, dokkaebi 150, monster 84, station 64, subway 39; sword 65 against gun 5, so it does not negate swords.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from echotales.core.store import Store


@dataclass(frozen=True, slots=True)
class GenreProfile:
    label: str
    style_anchor: str
    manga_base: str
    reference_anchor: str
    reference_style: str
    hands_clause: str
    world_setting: str
    world_context: str
    novel_style: str
    #: Replaces `prompt.py::_NEGATIVE_CULTURE` -- RI's "modern clothing, school uniform" is a correct negative for a
    #: cultivation novel and exactly wrong for one set in a modern city.
    negative_culture: str
    mismatch_props: tuple[str, ...] = ()
    scene_locales: dict[str, str] = field(default_factory=dict)
    appearance: dict[str, str] = field(default_factory=dict)
    #: Words whose frequency in the book suggests this genre (`detect_genre`): whole words, plural allowed, and a
    #: trailing `*` for a stem. Prefix matching for every entry counted "carriage" and "card" as `car`, which
    #: scored LotM as contemporary fiction.
    lexicon: tuple[str, ...] = ()


_FRAMING = "three-quarter shot from head to thigh"
_SHEET = f"solo, single character, {_FRAMING}, facing viewer, detailed face, plain background"
_SERIOUS = "solemn atmosphere, mature serious art style"

GENRES: dict[str, GenreProfile] = {
    "xianxia": GenreProfile(
        label="Xianxia / cultivation",
        style_anchor="guofeng illustration, chinese ink painting, xianxia",
        manga_base=(
            "guofeng illustration, chinese ink painting, xianxia, wuxia, "
            "ancient chinese fantasy, hanfu with long wide sleeves, "
            "ink wash, muted limited palette, "
            "elegant brushwork, negative space, subtle gradients, "
            f"{_SERIOUS}"
        ),
        reference_anchor=f"{_FRAMING}, guofeng illustration, chinese ink painting, xianxia",
        reference_style=(
            f"{_SHEET}, "
            "guofeng illustration, chinese ink painting, xianxia, wuxia, "
            "hanfu with long wide sleeves, ink wash, muted limited palette, "
            "serious cold expression, mature proportions, sharp features"
        ),
        hands_clause="hands concealed in long draping sleeves",
        world_setting=(
            "ancient Chinese cultivation world, stone courtyards, timber halls "
            "with upturned tiled roofs, bamboo groves, terraced mountain "
            "villages, mist over jagged peaks, stone steps, paper lanterns"
        ),
        world_context="",
        novel_style="xianxia web-novel illustration, Chinese fantasy",
        negative_culture="cherry blossoms, japanese shrine, modern clothing, school uniform",
        mismatch_props=("modern clothes", "modern clothing", "school uniform", "hoodie", "jeans", "business suit"),
        appearance={"hair_color": "black", "eye_color": "dark brown", "skin_tone": "fair"},
        lexicon=("cultivat*", "sect", "dao", "qi", "dantian", "immortal", "martial", "elder", "clan", "spirit stone",
                 "primeval", "gu master", "young master", "senior brother", "junior sister"),
    ),
    "victorian_gothic": GenreProfile(
        label="Victorian gothic / gaslamp",
        style_anchor="gothic engraving illustration, Victorian ink etching, occult mystery",
        manga_base=(
            "gothic engraving illustration, Victorian occult mystery, "
            "period-accurate tailored coats and waistcoats, "
            "cross-hatched linework, desaturated muted palette, fog and gaslight, "
            "ornate negative space, subtle gradients, "
            f"{_SERIOUS}"
        ),
        reference_anchor=f"{_FRAMING}, gothic engraving illustration, Victorian ink etching, occult mystery",
        reference_style=(
            f"{_SHEET}, "
            "gothic engraving illustration, Victorian occult mystery, "
            "period-accurate tailored coat and waistcoat, "
            "cross-hatched linework, desaturated muted palette, "
            "serious cold expression, mature proportions, sharp features"
        ),
        hands_clause="gloved hands, one resting in a coat pocket",
        world_setting=(
            "Victorian gaslamp city, cobbled streets, wrought-iron street lamps, "
            "brick townhouses, fog, horse-drawn carriages, cathedral spires"
        ),
        world_context="",
        novel_style="Victorian gaslamp fantasy, muted desaturated palette",
        negative_culture="hanfu, xianxia, japanese shrine, modern clothing, school uniform",
        mismatch_props=("xianxia", "hanfu", "cultivator", "samurai", "kimono", "cyberpunk", "futuristic armor"),
        appearance={"hair_color": "brown", "eye_color": "grey", "skin_tone": "pale"},
        lexicon=("carriage", "gas lamp", "gaslight", "revolver", "top hat", "cravat", "waistcoat", "pence", "soli",
                 "cathedral", "occult", "tarot", "madam", "steam", "shilling", "coachman", "bonnet", "parlour",
                 "candle", "telegraph", "cab", "hansom", "inspector", "constable"),
    ),
    "modern_apocalypse": GenreProfile(
        label="Modern apocalypse / urban fantasy",
        style_anchor="modern manhwa illustration, high contrast urban apocalypse",
        manga_base=(
            "modern korean manhwa illustration, clean digital linework, "
            "contemporary casual clothing, ruined city, "
            "high contrast, desaturated palette, harsh rim light, "
            f"{_SERIOUS}"
        ),
        reference_anchor=f"{_FRAMING}, modern manhwa illustration, high contrast",
        reference_style=(
            f"{_SHEET}, "
            "modern korean manhwa illustration, contemporary casual clothing, "
            "clean digital linework, desaturated palette, "
            "serious expression, mature proportions, sharp features"
        ),
        hands_clause="hands in jacket pockets",
        world_setting=(
            "modern Seoul in collapse, subway tunnels, cracked asphalt, "
            "toppled high-rises, overturned cars, rebar and rubble, ash sky"
        ),
        world_context="scenario system, constellations, dokkaebi, subway carriages",
        novel_style="modern Korean urban apocalypse, high contrast",
        negative_culture="hanfu, xianxia, ancient chinese, japanese shrine, cherry blossoms",
        mismatch_props=("hanfu", "xianxia", "cultivator robes", "kimono", "samurai", "medieval armor", "castle"),
        scene_locales={
            "hall": "a fluorescent-lit lobby, shattered glass, dead screens",
            "courtyard": "a cracked plaza between high-rises",
            "mountain": "a collapsed overpass above the city",
            "cave": "a dark subway tunnel, emergency lights",
            "village": "a ruined city street, overturned cars, dead neon signs",
            "forest": "an overgrown city park, broken benches",
            "night": "a blacked-out street at night, a burning wreck",
            "night_wild": "a ruined skyline under a red night sky",
        },
        appearance={"hair_color": "black", "eye_color": "dark brown", "skin_tone": "fair"},
        lexicon=("scenario", "constellation", "subway", "smartphone", "monster", "apocalypse", "survivor", "dokkaebi",
                 "zombie", "ruins", "apartment", "station"),
    ),
    "contemporary": GenreProfile(
        label="Contemporary / modern day",
        style_anchor="modern anime illustration, contemporary setting",
        manga_base=(
            "modern anime illustration, clean linework, contemporary clothing, "
            "everyday city setting, natural soft lighting, muted palette, subtle gradients, "
            "mature serious art style"
        ),
        reference_anchor=f"{_FRAMING}, modern anime illustration, contemporary clothing",
        reference_style=(
            f"{_SHEET}, modern anime illustration, contemporary casual clothing, "
            "clean linework, muted palette, calm expression, mature proportions"
        ),
        hands_clause="hands in pockets",
        world_setting="contemporary city, apartment interiors, offices, cafes, streets, trains",
        world_context="",
        novel_style="contemporary realistic fiction, modern day",
        negative_culture="hanfu, xianxia, medieval armor, japanese shrine",
        mismatch_props=("hanfu", "xianxia", "medieval armor", "castle", "robes"),
        scene_locales={
            "hall": "a modern apartment living room, window light",
            "courtyard": "a quiet city square, benches",
            "mountain": "a hiking trail above the city",
            "cave": "an underground parking garage",
            "village": "a busy city street, shop fronts",
            "forest": "a city park, tall trees",
            "night": "a city street at night, streetlights",
            "night_wild": "a dark park at night",
        },
        lexicon=("phone", "cellphone", "smartphone", "computer", "internet", "taxi", "apartment", "email", "laptop",
                 "television", "tv", "supermarket", "highway", "airport", "website", "text message"),
    ),
    "western_fantasy": GenreProfile(
        label="Western fantasy / medieval",
        style_anchor="western high fantasy illustration, painterly",
        manga_base=(
            "western high fantasy illustration, painterly ink and wash, "
            "medieval clothing, cloaks and leather, stone and timber, "
            "muted earthy palette, subtle gradients, "
            f"{_SERIOUS}"
        ),
        reference_anchor=f"{_FRAMING}, western high fantasy illustration, painterly",
        reference_style=(
            f"{_SHEET}, western high fantasy illustration, medieval clothing, cloak and leather, "
            "painterly, muted earthy palette, serious expression, mature proportions, sharp features"
        ),
        hands_clause="gloved hands resting on a belt",
        world_setting="medieval fantasy kingdom, stone castles, timber villages, forests, torchlit halls, mountain passes",
        world_context="",
        novel_style="western high fantasy",
        negative_culture="hanfu, xianxia, modern clothing, school uniform, japanese shrine",
        mismatch_props=("hanfu", "xianxia", "katana", "kimono", "modern clothing", "gun", "car"),
        scene_locales={
            "hall": "a torchlit castle hall, banners, stone pillars",
            "courtyard": "a castle courtyard, flagstones, battlements",
            "mountain": "a windswept mountain pass",
            "cave": "a dark cavern, torchlight",
            "village": "a timber-framed village street, thatched roofs",
            "forest": "an old oak forest, shafts of light",
            "night": "a castle courtyard at night, torches",
            "night_wild": "a moonlit forest clearing",
        },
        lexicon=("knight", "castle", "kingdom", "dragon", "mage", "spell", "elf", "elves", "dwarf", "tavern", "sword",
                 "magic", "wizard", "sorcer*", "squire", "lance", "armour", "armor"),
    ),
    "science_fiction": GenreProfile(
        label="Science fiction",
        style_anchor="science fiction illustration, sleek futuristic design",
        manga_base=(
            "science fiction illustration, clean hard-surface linework, "
            "futuristic clothing, metal and glass, holographic light, "
            "cool desaturated palette, subtle gradients, "
            f"{_SERIOUS}"
        ),
        reference_anchor=f"{_FRAMING}, science fiction illustration, futuristic clothing",
        reference_style=(
            f"{_SHEET}, science fiction illustration, futuristic clothing, "
            "clean linework, cool palette, serious expression, mature proportions, sharp features"
        ),
        hands_clause="gloved hands at the sides",
        world_setting="starship corridors, neon megacity, holographic displays, metal and glass, distant planets",
        world_context="",
        novel_style="science fiction",
        negative_culture="hanfu, xianxia, medieval armor, horse carriage, japanese shrine",
        mismatch_props=("hanfu", "xianxia", "castle", "horse-drawn carriage", "kimono", "medieval armor"),
        scene_locales={
            "hall": "a starship bridge, holographic consoles",
            "courtyard": "an open plaza under a domed sky",
            "mountain": "a barren alien ridge",
            "cave": "a maintenance tunnel, conduit lights",
            "village": "a neon megacity street, rain",
            "forest": "an alien jungle, bioluminescent plants",
            "night": "a neon street at night, rain",
            "night_wild": "an alien landscape under two moons",
        },
        lexicon=("starship", "spaceship", "planet", "laser", "android", "robot", "galaxy", "orbit", "space station",
                 "cyber*", "hologram", "warp"),
    ),
    "generic": GenreProfile(
        label="Other (neutral)",
        style_anchor="detailed illustration, cinematic composition",
        manga_base=(
            "detailed digital illustration, clean linework, muted palette, "
            f"subtle gradients, cinematic lighting, {_SERIOUS}"
        ),
        reference_anchor=f"{_FRAMING}, detailed illustration",
        reference_style=f"{_SHEET}, detailed illustration, clean linework, muted palette, mature proportions",
        hands_clause="hands relaxed at the sides",
        world_setting="detailed background environment",
        world_context="",
        novel_style="web-novel illustration, no further style data seeded for this novel",
        negative_culture="",
        scene_locales={
            "hall": "inside a large hall",
            "courtyard": "an open courtyard",
            "mountain": "a mountain path",
            "cave": "a dark cave",
            "village": "a small town street",
            "forest": "a forest",
            "night": "a street at night, deep shadows",
            "night_wild": "a dark wilderness at night",
        },
    ),
}

#: The three research novels, so their renders keep the profile they were tuned under without a database lookup.
NOVEL_GENRE: dict[str, str] = {
    "reverend-insanity": "xianxia",
    "lord-of-the-mysteries": "victorian_gothic",
    "omniscient-readers-viewpoint": "modern_apocalypse",
}

#: Set per process by `use_store_genre`: a project's stored or detected genre.
_PROJECT_GENRE: dict[str, str] = {}


def genre_of(novel_id: str) -> str:
    # `""` is the many `novel_id: str = ""` defaults (a prompt built with no novel in hand), which always got RI's
    # xianxia vocabulary; they keep it. A real project id the tables do not list is what drew new books as xianxia.
    if not novel_id:
        return "xianxia"
    return _PROJECT_GENRE.get(novel_id) or NOVEL_GENRE.get(novel_id) or "generic"


def profile(novel_id: str) -> GenreProfile:
    return GENRES[genre_of(novel_id)]


#: A genre needs this many lexicon hits per 10,000 words, and a lead over the runner-up, before it is proposed;
#: below that the neutral profile is the honest default rather than a guess.
MIN_HITS_PER_10K = 6.0
MIN_LEAD = 1.3


def _lexicon_pattern(word: str) -> str:
    if word.endswith("*"):
        return r"\b" + re.escape(word[:-1])
    return r"\b" + re.escape(word) + r"(?:s|es)?\b"


def detect_genre(store: Store, novel_id: str, *, max_chapters: int = 20) -> tuple[str, dict[str, float]]:
    """The genre the book's own words point to, with per-genre hits per 10,000 words.

    Deterministic and local (no model call), over the first `max_chapters` chapters, because a style has to be
    chosen before the first render. Returns ("generic", scores) when no genre clears `MIN_HITS_PER_10K` with a
    `MIN_LEAD` margin over the runner-up.
    """
    texts = []
    for n in store.chapter_numbers(novel_id)[:max_chapters]:
        texts.extend(s.text for s in store.get_spans(novel_id, n))
    text = " ".join(texts).casefold()
    words = max(len(text.split()), 1)
    scores = {}
    for name, prof in GENRES.items():
        if prof.lexicon:
            hits = sum(len(re.findall(_lexicon_pattern(w), text)) for w in prof.lexicon)
            scores[name] = round(hits * 10_000 / words, 2)
    ranked = sorted(scores, key=lambda g: scores[g], reverse=True)
    if not ranked:
        return "generic", scores
    best = ranked[0]
    second = scores[ranked[1]] if len(ranked) > 1 else 0.0
    if scores[best] < MIN_HITS_PER_10K or scores[best] < MIN_LEAD * second:
        return "generic", scores
    return best, scores


_DETECTED: dict[tuple[str, str, int, int], tuple[str, dict[str, float]]] = {}


def detect_genre_cached(store: Store, novel_id: str) -> tuple[str, dict[str, float]]:
    """`detect_genre`, remembered per (database, novel, chapter count, span count).

    The project list asks for it on every poll (Settings, library, sidebar) and detection reads 20 chapters: 1.1 s
    per request for three novels before this. It depends only on the text, so a re-ingest, which changes the counts,
    is the only thing that invalidates it.
    """
    chapters = store.conn.execute("SELECT COUNT(*) FROM chapter WHERE novel_id=?", (novel_id,)).fetchone()[0]
    spans = store.conn.execute("SELECT COUNT(*) FROM span WHERE novel_id=?", (novel_id,)).fetchone()[0]
    key = (store.path, novel_id, chapters, spans)
    if key not in _DETECTED:
        _DETECTED[key] = detect_genre(store, novel_id)
    return _DETECTED[key]


def stored_genre(store: Store, novel_id: str) -> str | None:
    row = store.get_novel(novel_id) or {}
    value = row.get("visual_genre")
    return value if value in GENRES else None


def use_store_genre(store: Store, novel_id: str) -> str:
    """Register this project's genre for the process and return it.

    A stored choice wins; a research novel keeps its tuned profile; anything else is detected from its text. Called
    at the top of every image-generating entry point (`render_panels`, `generate_references`), since the lookups in
    `attire.py` see only the novel id.
    """
    genre = stored_genre(store, novel_id) or NOVEL_GENRE.get(novel_id) or detect_genre_cached(store, novel_id)[0]
    _PROJECT_GENRE[novel_id] = genre
    return genre
