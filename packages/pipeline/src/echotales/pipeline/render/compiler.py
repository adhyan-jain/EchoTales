"""Prompt compiler: the graph's view of a panel, written in the image model's own format.

Why this exists (owner review, 2026-11-15): the panels of Reverend Insanity chapter 1, a cliff edge where Fang Yuan stands
cold and unafraid among many righteous-sect fighters, came out as one sad figure on a flat background, because the prompt
carried no setting and no crowd and forced "solo", while a 77-token fit silently dropped the clauses that did (a recorded
example lost the layout, setting, lighting and location: 102 tokens cut to 73). The graph knew the scene; it never reached
the model. This module is pure (no model, no GPU, no database): it turns one typed `PanelBrief` into one `CompiledPrompt`
whose labelled `sections` say which text carried the setting, the cast, the action. It never truncates; length is the
encoder's job (`workers_local` chunks the whole prompt, so nothing is cut).

Prompt formats (what the model families document; `PromptFormat` holds the choice)
- SDXL anime models (NoobAI XL, Illustrious). The NoobAI-XL 1.1 card
  (https://huggingface.co/Laxhar/noobai-XL-1.1, "Usage Guidelines") gives the caption order
  `<1girl/1boy/1other/...>, <character>, <series>, <artists>, <special tags>, <general tags>, <other tags>`, quality tags
  by popularity percentile (masterpiece, best quality, ...), Euler a, CFG 5-6, 25-30 steps, about 1024x1024 area (832x1216
  best), and a negative starting "nsfw, worst quality, old, early, low quality, lowres, signature, username, logo, bad
  hands, mutated hands". The card does not say underscores or spaces; Illustrious
  (https://huggingface.co/OnomaAIResearch/Illustrious-XL-v1.0) says only "Danbooru-style tags, plain English, or both".
  This project measured score tags (score_9, score_8_up) beating masterpiece/best quality on this checkpoint
  (memory: echotales-image-model-stack), so the NoobAI profile keeps them; the quality tags are a profile field. Section
  order here: quality, count, character, expression, action, crowd, setting, composition, lighting, objects, mood, style.
- Anima (circlestone-labs/Anima, https://huggingface.co/circlestone-labs/Anima): lowercase tags with spaces, quality /
  meta / year / safety first, then count, character, series, artist, general tags, then natural language ("at least two
  sentences", describe each named character's appearance). This module writes tags then 2 to 4 sentences.

Appearance in text. Stage B will condition identity on reference images, so appearance should leave the text prompt:
`AppearanceInText.SHORT` (default) writes at most `SHORT_ITEMS` identity items (hair, outfit, eyes, a mark), `OFF` writes
none, `FULL` writes every fact valid at the panel's story position. `CompiledPrompt.appearance_written` says per character.

Demeanour is derived, not guessed (`derive_demeanour`): a stated expression (from the text or the director) wins; else
the persona's Big Five and register decide, damped by scene tension, so a ruthless, composed character in a tense scene is
"cold, contemptuous calm" and never "sad". The fields consulted are returned with the result.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum

log = logging.getLogger(__name__)

#: Identity items written under `AppearanceInText.SHORT`: enough for the model to keep hair and clothes, few enough that
#: reference images (stage B) carry the rest.
SHORT_ITEMS = 4

# ---------------------------------------------------------------------------
# model profiles
# ---------------------------------------------------------------------------


class PromptFormat(StrEnum):
    SDXL_TAGS = "sdxl_tags"
    ANIMA = "anima"
    #: Plain sentences for a text encoder that is a language model (Z-Image's Qwen3-4B): no tags, no negative prompt.
    NATURAL = "natural"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """Everything that differs per image model, so the model is one config value (`render.image_model`)."""

    key: str
    model_id: str
    family: PromptFormat
    width: int
    height: int
    steps: int
    guidance: float
    sampler: str
    quality_tags: str
    negative_base: str
    licence: str
    #: Why the profile cannot run here, or "" when it can. A profile that cannot run stays listed and says so.
    unavailable: str = ""
    underscores: bool = False


PROFILES: dict[str, ModelProfile] = {
    "noobai-xl-1.1": ModelProfile(
        key="noobai-xl-1.1",
        model_id="Laxhar/noobai-XL-1.1",
        family=PromptFormat.SDXL_TAGS,
        width=832, height=1216, steps=28, guidance=5.5, sampler="euler_a",
        quality_tags="score_9, score_8_up, score_7_up, very aesthetic, absurdres",
        negative_base=(
            "worst quality, low quality, lowres, bad anatomy, bad hands, mutated hands, extra fingers, text, "
            "annotations, japanese text, speech bubble, watermark, signature, username, logo, blurry"
        ),
        licence="fair-ai-public-license-1.0-sd (non-commercial, card metadata)",
    ),
    "anima": ModelProfile(
        key="anima",
        model_id="circlestone-labs/Anima-Base-v1.0-Diffusers",
        family=PromptFormat.ANIMA,
        width=832, height=1216, steps=30, guidance=4.5, sampler="flow_match_euler",
        quality_tags="masterpiece, best quality, score_7, safe",
        negative_base=(
            "worst quality, low quality, score_1, score_2, score_3, artist name, blurry, jpeg artifacts, "
            "chromatic aberration, text, watermark"
        ),
        licence="CircleStone Labs Non-Commercial License (derivative of Cosmos-Predict2-2B, NVIDIA Open Model License)",
        # Set by the owner's rules, not by capability: weights are not downloaded yet (5.65 GB), so no run has been measured.
        unavailable="",
    ),
}
PROFILES["z-image-turbo"] = ModelProfile(
    key="z-image-turbo",
    model_id="Tongyi-MAI/Z-Image-Turbo",
    family=PromptFormat.NATURAL,
    width=832, height=1216, steps=9, guidance=0.0, sampler="flow_match_euler",
    quality_tags="",
    # Turbo is distilled without CFG, so a negative prompt has no effect; every exclusion is written as a positive
    # "no panel borders, no text" clause in the style sentence instead (probe 2026-11-16: no negative was ever passed).
    negative_base="",
    licence="Apache-2.0 (model card, https://huggingface.co/Tongyi-MAI/Z-Image-Turbo)",
)
DEFAULT_MODEL = "noobai-xl-1.1"


def model_profile(key: str | None = None) -> ModelProfile:
    """The profile for `key`; an unknown key raises, because a typo silently rendering with another model would make a
    model comparison meaningless."""
    chosen = (key or DEFAULT_MODEL).strip().lower()
    if chosen not in PROFILES:
        raise ValueError(f"unknown image model {key!r}; expected one of {sorted(PROFILES)}")
    return PROFILES[chosen]


# ---------------------------------------------------------------------------
# brief
# ---------------------------------------------------------------------------


class OutputMode(StrEnum):
    MANGA = "manga"
    COLOUR = "colour"


class AppearanceInText(StrEnum):
    OFF = "off"
    SHORT = "short"
    FULL = "full"


@dataclass(slots=True)
class CharacterBrief:
    """One person in frame, as the graph says they are at this story position."""

    name: str
    gender: str = "unknown"  # male | female | unknown | creature
    age_band: str = ""
    #: Appearance facts valid at the panel's position, kind -> value (`appearance_of(..., position=...)`).
    appearance: dict[str, str] = field(default_factory=dict)
    #: What they wear / transient condition at this beat ("green robes", "wounded, bloodied").
    attire: str = ""
    condition: str = ""
    #: Big Five values 0-1 by letter (o, c, e, a, n) and register, from the persona's trait profile.
    big_five: dict[str, float] = field(default_factory=dict)
    register: str = ""
    #: The face as the text or director states it ("calm expression"); wins over any trait inference.
    stated_expression: str = ""
    lead: bool = False
    #: Position in frame: "center", "left", "right", "foreground", "background", "kneeling in front".
    position: str = "center"
    #: Physical pose: "standing", "sitting", "kneeling", "fighting stance", "running".
    pose: str = "standing"
    #: Name of another character with identical face (twins: "same face as").
    same_face_as: str = ""
    #: True for monsters, spirit beasts, or non-human entities.
    is_creature: bool = False
    #: The body's stated age in years when the text gives one ("a fifteen year old"); 0 when it does not.
    age_years: int = 0


@dataclass(slots=True)
class CrowdBrief:
    """People in frame who are not individual characters, and their stance toward the lead."""

    description: str  # "righteous-sect martial artists in pale robes"
    size: str = "many"  # few | many
    gender: str = "male"  # male | female | mixed
    stance: str = ""  # a clause with a verb: "surround him, weapons drawn"
    #: Exact headcount when the text gives one; 0 means "use `size`" ("a dozen or more" / "three or four"). Only the natural-
    #: language profile writes a number; the tag profiles keep `size`.
    count: int = 0


@dataclass(slots=True)
class PanelBrief:
    novel_id: str
    characters: list[CharacterBrief]
    crowd: CrowdBrief | None = None
    location: str = ""
    location_description: str = ""
    #: The director's setting and lighting tags, when there is one.
    setting: str = ""
    lighting: str = ""
    shot: str = "medium"  # wide | medium | close
    camera: str = ""  # "low angle", "from above", "eye-level"
    action: str = ""
    key_objects: list[str] = field(default_factory=list)
    mood: str = ""
    #: Scene tension, 0-1; damps trait-derived anxiety (a composed character does not look afraid when the scene is tense).
    tension: float = 0.0
    mode: OutputMode = OutputMode.MANGA
    #: Genre art direction (`genre_direction`), never hard-coded here.
    art_direction: str = ""
    era_wardrobe: str = ""
    manhua: bool = False
    is_indoor: bool = False
    #: The director's composed paragraph (who stands where, what each does and shows on the face, wounds, setting detail,
    #: light, camera), written in the owner's probe style. The Z-Image profile builds the prompt around it.
    composition: str = ""
    #: The scene's staging sheet text (set, blocking, light), identical on every panel of the scene.
    staging: str = ""
    #: "text" when the panel's own text shows something; "inferred" when the director chose a visual from the text's
    #: referents because nothing visible was stated. Carried so `audit` can count them.
    visual_source: str = ""


def genre_direction(novel_id: str) -> tuple[str, str, bool]:
    """`(art direction, wardrobe, manhua flavour)` from the novel's genre profile."""
    from echotales.pipeline.persona.genre import profile

    p = profile(novel_id)
    return p.style_anchor, p.wardrobe, "chinese" in p.style_anchor or "xianxia" in p.style_anchor


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PromptSection:
    label: str
    text: str


@dataclass(slots=True)
class CompiledPrompt:
    positive: str
    negative: str
    sections: list[PromptSection]
    negative_sections: list[PromptSection]
    family: PromptFormat
    mode: OutputMode
    #: Per character: whether appearance was written into the text (stage B reads this to know who needs a reference).
    appearance_written: dict[str, bool]
    #: Per character: the graph fields the demeanour came from.
    demeanour_fields: dict[str, list[str]]

    def section_texts(self) -> list[tuple[str, str]]:
        return [(s.label, s.text) for s in self.sections]


# ---------------------------------------------------------------------------
# demeanour
# ---------------------------------------------------------------------------

_TENSE = ("tense", "hostile", "confront", "anticipation", "menac", "threat", "danger", "battle", "siege", "fight")
_SORROW = ("sad", "grief", "mourn", "sorrow", "tears", "despair", "regret")


@dataclass(frozen=True, slots=True)
class Demeanour:
    tags: list[str]
    sentence: str
    fields_used: list[str]


def derive_demeanour(c: CharacterBrief, mood: str = "", tension: float = 0.0) -> Demeanour:
    """The face and bearing of `c` in a scene of this `mood`.

    Order of authority: the stated expression (text or director), then the persona's Big Five (a = agreeableness, n =
    neuroticism, e = extraversion, c = conscientiousness), then the mood word alone. Failure this fixes: a wounded,
    bleeding lead drew a pained face because the checkpoint reads injury as pain, even where the text says four times that
    his expression did not change. Neuroticism is shown only when conscientiousness is also low: Fang Yuan's stored
    profile is n=0.80 but c=0.70, and a disciplined character does not look afraid.
    """
    used: list[str] = []
    mood_l = (mood or "").lower()
    tense = tension >= 0.5 or any(w in mood_l for w in _TENSE)
    if mood:
        used.append(f"scene.mood={mood}")
    if tension:
        used.append(f"scene.tension={tension:g}")
    if c.stated_expression:
        used.append(f"stated_expression={c.stated_expression}")
        tags = [t.strip().replace("_", " ") for t in c.stated_expression.split(",") if t.strip()]
        return Demeanour(tags, f"{c.name}'s face is {' and '.join(tags)}.", used)

    a, n, e, cons = (c.big_five.get(k) for k in ("a", "n", "e", "c"))
    for letter, value in (("a", a), ("n", n), ("e", e), ("c", cons)):
        if value is not None:
            used.append(f"big_five.{letter}={value:g}")
    if c.register:
        used.append(f"register={c.register}")

    tags: list[str]
    if any(w in mood_l for w in _SORROW):
        tags, how = ["sorrowful", "downcast eyes"], "sorrowful, with downcast eyes"
    elif a is not None and a <= 0.45 and (e is None or e <= 0.5):
        if n is not None and n >= 0.65 and cons is not None and cons < 0.5:
            tags, how = ["cold eyes", "tense jaw", "guarded"], "cold and guarded, jaw tight"
        elif tense:
            tags, how = ["cold eyes", "contemptuous", "calm expression"], "coldly contemptuous and perfectly calm"
        else:
            tags, how = ["cold eyes", "calm expression"], "cold and calm"
    elif n is not None and n >= 0.65 and (cons is None or cons < 0.5):
        tags, how = (["wary", "anxious"], "wary and anxious") if tense else (["uneasy"], "uneasy")
    elif a is not None and a >= 0.65:
        tags, how = (["concerned", "determined"], "concerned but determined") if tense else (
            ["gentle expression", "attentive"], "gentle and attentive")
    elif tense:
        tags, how = ["serious", "focused"], "serious and focused"
    else:
        tags, how = ["calm expression"], "calm"
    return Demeanour(tags, f"{c.name}'s face is {how}.", used)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_HAIR = re.compile(r"hair")
_OUTFIT = re.compile(r"cloth|attire|robe|outfit|wear|garment")
_EYES = re.compile(r"eye")
_MARK = re.compile(r"scar|mark|tattoo|feature|beard|distinguish")
_SKIP = ("age_band", "gender", "register", "archetype", "big_five", "trait_provenance", "current_condition")


def appearance_phrases(c: CharacterBrief, mode: AppearanceInText) -> list[str]:
    """Appearance as short noun phrases, per the switch. `OFF` returns nothing; `SHORT` at most `SHORT_ITEMS` items."""
    if mode is AppearanceInText.OFF:
        return []
    facts = {k: v for k, v in c.appearance.items() if v and k not in _SKIP}
    hair_bits = [v for k, v in facts.items() if _HAIR.search(k)]
    hair = (" ".join(v.replace(" hair", "") for v in hair_bits) + " hair").strip() if hair_bits else ""
    eyes = [f"{v} eyes" for k, v in facts.items() if _EYES.search(k)]
    marks = [v for k, v in facts.items() if _MARK.search(k)]
    outfit = [c.attire] if c.attire else [v for k, v in facts.items() if _OUTFIT.search(k)]
    used = {k for k in facts if _HAIR.search(k) or _EYES.search(k) or _MARK.search(k) or _OUTFIT.search(k)}
    rest = [f"{v} {k.replace('_', ' ')}" if k in ("skin_tone",) else v for k, v in facts.items() if k not in used]
    ordered = ([hair] if hair else []) + outfit + eyes + marks
    if mode is AppearanceInText.SHORT:
        return ordered[:SHORT_ITEMS]
    return ordered + rest


def _tag(text: str, profile: ModelProfile) -> str:
    text = text.strip().lower()
    if re.fullmatch(r"score_\d+(_up)?", text):
        return text
    return text if profile.underscores else text.replace("_", " ")


def _tags(items: list[str], profile: ModelProfile) -> list[str]:
    out: list[str] = []
    for item in items:
        for part in item.split(","):
            t = _tag(part, profile)
            if t and t not in out:
                out.append(t)
    return out


def _count_tags(b: PanelBrief) -> list[str]:
    """Headcount tags. "solo" is only ever written for exactly one person and no crowd: forced "solo" erased the whole
    mob in the failure that motivated this module."""
    word = {"male": "boy", "female": "girl"}
    people = b.characters
    if not people and b.crowd is None:
        return ["no_humans", "scenery"]
    genders = [word.get(c.gender) for c in people]
    tags: list[str] = []
    if b.crowd is None and len(people) == 1:
        g = genders[0]
        tags = [f"1{g}", "solo"] if g else ["1other", "solo"]
        if g == "boy":
            tags.append("male focus")
        return tags
    boys, girls = genders.count("boy"), genders.count("girl")
    if b.crowd is not None:
        lead = people[0] if people else None
        if lead is not None and genders[0]:
            tags.append(f"1{genders[0]}")
        cg = b.crowd.gender
        if cg in ("male", "mixed"):
            tags.append("multiple boys")
        if cg in ("female", "mixed"):
            tags.append("multiple girls")
        if b.crowd.size == "many":
            tags += ["6+boys" if cg == "male" else "6+girls" if cg == "female" else "crowd", "crowd"]
        if lead is not None and genders[0] == "boy":
            tags.append("male focus")
        return list(dict.fromkeys(tags))
    if boys:
        tags.append(f"{boys}boy" if boys == 1 else f"{boys}boys")
    if girls:
        tags.append(f"{girls}girl" if girls == 1 else f"{girls}girls")
    return tags or [f"{len(people)}others"]


_SHOT = {"wide": "wide shot", "medium": "medium shot", "close": "close-up"}


def _location_text(b: PanelBrief) -> str:
    return b.location_description or b.location


# ---------------------------------------------------------------------------
# monochrome wording
# ---------------------------------------------------------------------------


def _mode_tags(b: PanelBrief) -> list[str]:
    if b.mode is OutputMode.MANGA:
        tags = ["monochrome", "greyscale", "screentone", "ink lineart", "high contrast", "manga"]
        is_dark = any(w in f"{b.lighting} {b.mood} {b.setting}".lower() for w in ("night", "dark", "horror", "midnight", "shadow", "dungeon", "gloomy", "ominous"))
        if is_dark:
            tags += ["heavy shadows", "deep black shading", "dark atmosphere", "chiaroscuro"]
        if b.manhua:
            tags += ["chinese manhua", "ink wash"]
        return tags
    return []


_COLOUR_NEG = "color, colorful, colored, vibrant colors, watercolor, sepia, 3d, realistic"


# ---------------------------------------------------------------------------
# compile
# ---------------------------------------------------------------------------


def compile_prompt(
    brief: PanelBrief,
    profile: ModelProfile | None = None,
    *,
    appearance: AppearanceInText = AppearanceInText.SHORT,
) -> CompiledPrompt:
    """Compile `brief` for `profile`'s prompt format. Never truncates, never drops a section."""
    profile = profile or model_profile()
    if profile.family is PromptFormat.ANIMA:
        return _compile_anima(brief, profile, appearance)
    if profile.family is PromptFormat.NATURAL:
        return _compile_natural(brief, profile, appearance)
    return _compile_sdxl(brief, profile, appearance)


_NATURAL_SHOT = {"wide": "A wide establishing shot", "medium": "A medium shot", "close": "A close-up portrait"}
_NOUN = {"male": "man", "female": "woman"}
_CHILD_NOUN = {"male": "boy", "female": "girl", "unknown": "child"}
_TEEN_NOUN = {"male": "teenage boy", "female": "teenage girl", "unknown": "teenager"}
_CREATURE_WORDS = re.compile(r"\b(beast|centipede|demon|spirit|dragon|monster|imp|wolf|chimera|creature|fiend)\b", re.IGNORECASE)
_INDOOR_KEYWORDS = re.compile(
    r"\b(room|hall|chamber|house|interior|bed|study|cabin|palace\s+interior|shop|dungeon|cell|pavilion\s+interior|bamboo\s+house)\b",
    re.IGNORECASE,
)


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("_", " ")).strip().strip(",.")


def identity_sentence(c: CharacterBrief, appearance: AppearanceInText = AppearanceInText.SHORT) -> str:
    """The fixed one-sentence description of a character, built only from the graph's body facts (hair, eyes, marks, attire).

    Identical wording in every panel of the same character is the stopgap for identity until reference-image conditioning
    exists: the probe (2026-11-16) drew the same hero with a different face in three panels of one scene whenever the
    description changed between prompts. Nothing scene-dependent (wounds, mood, action) goes in; those are separate
    sentences. Facts are written in the order the model should weigh them: hair, eyes, marks, then clothes."""
    if c.same_face_as:
        return f"{c.name} has the identical facial features and face as {c.same_face_as} (twin), but wears {_plain(c.attire) or 'distinct robes'}."
    if c.is_creature or c.gender == "creature" or _CREATURE_WORDS.search(c.name):
        cond = f", {_plain(c.condition)}" if c.condition else ""
        return f"{c.name} is a monstrous {_plain(c.name).lower()}{cond}."

    age_band = (c.age_band or "").lower()
    young = age_band in ("child", "teen", "teenager", "adolescent", "youth")
    if young and c.age_years:
        # RI's reborn fifteen-year-old was drawn as the grown man because "youth" had no wording and no number; a stated
        # age in plain words is what lets Z-Image draw a younger version of the same face.
        if age_band == "child" or c.age_years < 13:
            noun = _CHILD_NOUN.get(c.gender, "child")
        else:
            noun = {"male": "boy", "female": "girl"}.get(c.gender, "teenager")
        head = f"{c.name} is a {c.age_years}-year-old {noun}"
    elif age_band == "child":
        noun = _CHILD_NOUN.get(c.gender, "child")
        head = f"{c.name} is a young {noun}"
    elif age_band in ("teen", "teenager", "adolescent", "youth"):
        noun = _TEEN_NOUN.get(c.gender, "teenager")
        head = f"{c.name} is a {noun}"
    else:
        noun = _NOUN.get(c.gender, "person")
        age = c.age_band if c.age_band and c.age_band not in ("adult", "unknown") else ""
        head = f"{c.name} is a{'n' if (age or noun)[0] in 'aeiou' else ''} {f'{age} ' if age else ''}{noun}"

    if appearance is AppearanceInText.OFF:
        return head + "."
    facts = {k: v for k, v in c.appearance.items() if v and k not in _SKIP}
    hair_bits = [v for k, v in facts.items() if _HAIR.search(k)]
    feats = ([(" ".join(v.replace(" hair", "") for v in hair_bits) + " hair").strip()] if hair_bits else [])
    feats += [f"{v} eyes" for k, v in facts.items() if _EYES.search(k)]
    feats += [v for k, v in facts.items() if _MARK.search(k)]
    if appearance is AppearanceInText.SHORT:
        feats = feats[: SHORT_ITEMS - (1 if c.attire else 0)]
    if not feats and not c.attire:
        _ASSUMED_MARKERS = [
            "hair tied in a high ponytail",
            "short neatly combed hair",
            "hair pinned up at the back",
            "shoulder-length dark hair",
            "hair tied back with a ribbon",
            "parted straight hair",
            "braided side hair",
            "thick swept-back hair",
        ]
        import hashlib
        h = int(hashlib.md5(c.name.encode("utf-8")).hexdigest(), 16)
        feats = [_ASSUMED_MARKERS[h % len(_ASSUMED_MARKERS)]]
    text = head
    if feats:
        text += " with " + (", ".join(feats[:-1]) + " and " + feats[-1] if len(feats) > 1 else feats[0])
    if young:
        text += ", a smooth youthful face and a " + ("slight build" if c.gender == "female" else "slim boyish build")
    if c.attire:
        text += f", wearing {_plain(c.attire)}"
    return _plain(text) + "."


def _face_words(tags: list[str]) -> str:
    """Demeanour tags as words after "face is": `calm expression` -> `calm`, `light smile` -> `a light smile`."""
    words = []
    for t in tags:
        t = re.sub(r"\s*expression$", "", _plain(t)).strip()
        if t:
            words.append(f"a {t}" if re.search(r"(smile|stare|laugh|frown|grin)$", t) else t)
    return " and ".join(words) if words else "calm"


_WARM = re.compile(r"smil|laugh|grin|chuckl|giggl|cheer|joy")


def _cold_face(c: CharacterBrief) -> str:
    """Wording for a cold, disagreeable lead (agreeableness <= 0.45, extraversion <= 0.5: the same test `derive_demeanour`
    uses), or "" for anyone else.

    Why: in the 2026-11-16 Z-Image run "cold" came out neutral in a close-up, a bare stated "light smile" drew a warm
    smile on Fang Yuan, and a stated "laughing" drew a cheerful shonen hero. A language-model encoder takes the word it is
    given, so a stated smile or laugh is rewritten as its cold form and the sentence names the absence of warmth. The
    wording is generic to the trait profile, not to one novel."""
    a, e = c.big_five.get("a"), c.big_five.get("e")
    is_cold = (
        (a is not None and a <= 0.45 and (e is None or e <= 0.5))
        or "cold" in c.register.lower()
        or (c.lead and "cold" in c.stated_expression.lower())
    )
    if not is_cold:
        return ""
    stated = _plain(c.stated_expression).lower()
    poss = {"male": "his", "female": "her"}.get(c.gender, "their")
    base = "cold and unmoved, eyes half-lidded with contempt, no warmth in it"
    if re.search(r"laugh|chuckl", stated):
        return base + f", a cold mocking laugh that never reaches {poss} dead eyes"
    if _WARM.search(stated):
        return base + ", at most a thin mocking smirk, never a warm or cheerful smile"
    return base


def _headcount(crowd: CrowdBrief) -> str:
    if crowd.count > 0:
        return f"{crowd.count}"
    return "a dozen or more" if crowd.size == "many" else "three or four"


def _compile_natural(b: PanelBrief, profile: ModelProfile, appearance: AppearanceInText) -> CompiledPrompt:
    """3 to 6 plain sentences in the order a language-model encoder weighs them: composition, the lead (fixed identity
    sentence, then demeanour), who else is there and where they stand, the setting with light and mood, one style sentence.

    Why this order and shape: the probe's one-paragraph prompts put the hero, a cliff and a crowd of 12-20 in all 4 of 4
    images, but the crowd stood beside the hero rather than ringing him, because "a crowd" gave no position; the stance
    clause ("ringed around him on all sides") is mandatory whenever there are others. Never truncated."""
    if b.composition:
        return _compile_composed(b, profile, appearance)
    lead = b.characters[0] if b.characters else None
    s: list[PromptSection] = []
    shot = _NATURAL_SHOT.get(b.shot, "A medium shot") + (f", {_plain(b.camera)}" if b.camera else "")
    action = _plain(b.action)
    if lead is None and b.crowd is None:
        s.append(PromptSection("composition", f"{shot}: pure scenery establishing shot of the environment, completely empty of people, no characters present{': ' + action if action else ''}."))
    else:
        framing = f", framing {lead.name}" if lead else ""
        s.append(PromptSection("composition", f"{shot}{framing}{': ' + action if action else ''}."))
    written: dict[str, bool] = {}
    fields: dict[str, list[str]] = {}
    if lead is not None:
        s.append(PromptSection(f"character:{lead.name}", identity_sentence(lead, appearance)))
        written[lead.name] = appearance is not AppearanceInText.OFF
        d = derive_demeanour(lead, b.mood, b.tension)
        fields[lead.name] = d.fields_used
        face = _cold_face(lead) or _face_words(d.tags)
        extra = f" {lead.name}'s condition: {_plain(lead.condition)}." if lead.condition else ""
        pos_str = f" {lead.name} is positioned {_plain(lead.position)}." if lead.position and lead.position != "center" else ""
        s.append(PromptSection("demeanour", f"{lead.name}'s face is {face}.{extra}{pos_str}"))
    others = b.characters[1:]
    for c in others:
        written[c.name] = appearance is not AppearanceInText.OFF
        fields[c.name] = derive_demeanour(c, b.mood, b.tension).fields_used
    parts = []
    if others:
        other_sentences = []
        for c in others:
            ident = identity_sentence(c, appearance)
            d = derive_demeanour(c, b.mood, b.tension)
            c_face = _cold_face(c) or _face_words(d.tags)
            clauses = []
            if c.position and c.position != "center":
                clauses.append(f"positioned {_plain(c.position)}")
            if c.pose and c.pose != "standing":
                clauses.append(f"in a {_plain(c.pose)} pose")
            if c_face:
                clauses.append(f"face is {c_face}")
            if clauses:
                other_sentences.append(f"{ident} {c.name} is {', '.join(clauses)}.")
            else:
                other_sentences.append(ident)
        parts.append(" ".join(other_sentences))
    if b.crowd is not None:
        who = lead.name if lead else "the center of the frame"
        stance = _plain(b.crowd.stance) or f"stand close around {who}"
        if lead is None:
            parts.append(f"The scene is filled with {_headcount(b.crowd)} {_plain(b.crowd.description)}; they {stance}.")
        elif lead.gender == "female":
            parts.append(f"In the scene with her are {_headcount(b.crowd)} {_plain(b.crowd.description)}; they {stance}.")
        else:
            parts.append(f"In the scene with him are {_headcount(b.crowd)} {_plain(b.crowd.description)}; they {stance}.")
    if parts:
        s.append(PromptSection("others", " ".join(parts)))
    place = _plain(_location_text(b))
    detail = _plain(b.setting)
    light = _plain(b.lighting)
    mood = _plain(b.mood)
    seen: list[str] = []
    for x in [t.strip() for t in f"{place},{detail}".split(",")]:  # the location and the director's setting repeat each other
        if x and x.lower() not in (y.lower() for y in seen):
            seen.append(x)
    where = ", ".join(seen)
    tail = "; ".join(([f"the light is {light}"] if light else []) + ([f"the mood is {mood}"] if mood else []))
    objs = f" Visible: {', '.join(_plain(o) for o in b.key_objects)}." if b.key_objects else ""

    is_indoor = b.is_indoor or bool(_INDOOR_KEYWORDS.search(f"{where} {detail}"))
    indoor_prefix = "inside an enclosed room, indoor interior, enclosed space with walls and ceiling, no outdoor landscape; " if is_indoor else ""

    if where or tail or is_indoor:
        sentence = (f"The setting is {indoor_prefix}{where}" if where else f"The setting is {indoor_prefix.rstrip('; ')}") + (f"; {tail}" if tail and where else f" {tail}" if tail else "")
        s.append(PromptSection("setting", sentence + "." + objs))
    s.append(PromptSection("style", _style_sentence(b)))
    s = [x for x in s if x.text]
    return CompiledPrompt(
        positive=" ".join(x.text for x in s), negative="", sections=s, negative_sections=[], family=profile.family,
        mode=b.mode, appearance_written=written, demeanour_fields=fields,
    )


_MANGA_LEAD = "Black and white manga panel, screentone shading, bold ink linework."


def _compile_composed(b: PanelBrief, profile: ModelProfile, appearance: AppearanceInText) -> CompiledPrompt:
    """Z-Image prompt in the order of the probe prompts the owner liked: a short style lead, the director's composed
    paragraph, one fixed identity sentence per visible character, then setting and light.

    Why: the 2026-11-16 real render opened with a composition fragment and closed with a 60-word style paragraph, and
    drew the same standing man in 10 of 18 panels; the hand-written probes were a lead plus one composed scene and drew the
    crowd ringing the hero. The identity sentences are identical on every panel of an interval (looks stay consistent) and
    nothing scene-dependent is in them; wounds and clothing state live in the paragraph, which comes from the panel's text.
    Setting clauses the paragraph already says are not repeated."""
    from echotales.pipeline.persona.genre import style_lead

    lead = _MANGA_LEAD if b.mode is OutputMode.MANGA else style_lead(b.novel_id)
    s = [PromptSection("style", lead)]
    if b.staging:
        s.append(PromptSection("staging", b.staging.strip()))
    s.append(PromptSection("composition", b.composition.strip()))
    written: dict[str, bool] = {}
    fields: dict[str, list[str]] = {}
    for c in b.characters:
        s.append(PromptSection(f"character:{c.name}", identity_sentence(c, appearance)))
        written[c.name] = appearance is not AppearanceInText.OFF
        fields[c.name] = derive_demeanour(c, b.mood, b.tension).fields_used
    said = f"{b.composition} {b.staging}".lower()
    clauses: list[str] = []
    for x in [t.strip() for t in f"{_plain(_location_text(b))},{_plain(b.setting)}".split(",")]:
        if x and x.lower() not in said and x.lower() not in (y.lower() for y in clauses):
            clauses.append(x)
    light = _plain(b.lighting)
    if light and light.lower() not in said:
        clauses.append(f"the light is {light}")
    if clauses:
        s.append(PromptSection("setting", f"Setting: {'; '.join(clauses)}."))
    return CompiledPrompt(
        positive=" ".join(x.text for x in s), negative="", sections=s, negative_sections=[], family=profile.family,
        mode=b.mode, appearance_written=written, demeanour_fields=fields,
    )


def _style_sentence(b: PanelBrief) -> str:
    if b.mode is OutputMode.MANGA:
        is_dark = any(w in f"{b.lighting} {b.mood} {b.setting}".lower() for w in ("night", "dark", "horror", "midnight", "shadow", "dungeon", "gloomy", "ominous"))
        if is_dark:
            text = ("A dark high-contrast black-and-white manga illustration: heavy black ink shading, deep shadows, "
                    "dramatic chiaroscuro, dark atmospheric manga aesthetic, pure black and white only, no panel borders, "
                    "no speech bubbles and no text")
        else:
            text = ("A crisp black-and-white manga illustration: a single full-bleed image with clean black ink linework and "
                    "screentone shading, pure black and white only, no panel borders, no speech bubbles and no text")
    elif b.manhua:
        return ("A Chinese donghua illustration in the guofeng style: detailed, painterly xianxia art with ink-wash mountains, "
                "mist, a muted cold palette and soft painterly backgrounds, a single full-bleed image with no panel borders, "
                "no speech bubbles and no text, hanfu with wide sleeves and cross collars.")
    else:
        text = "A richly coloured painted illustration: a single full-bleed image with no panel borders, no speech bubbles and no text"

    if b.manhua:
        # Architecture removed from global style sentence per EVOLUTION 4.165 so paifang does not appear in rooms/forests
        text += ("; Chinese manhua and donghua style in an ancient-Chinese xianxia world, hanfu with wide sleeves and cross collars, "
                 "and topknots with hairpins")
    else:
        art_lower = b.art_direction.lower()
        ward_lower = b.era_wardrobe.lower()
        if "victorian" in art_lower or "gothic" in art_lower or "gaslamp" in ward_lower:
            text += ("; Victorian gothic style, authentic Victorian era attire with frock coats, waistcoats, and dresses, detailed period background")
        elif "modern" in art_lower or "contemporary" in art_lower:
            text += ("; modern cinematic urban atmosphere, contemporary clothing and jackets")
        elif "fantasy" in art_lower or "medieval" in ward_lower:
            text += ("; western fantasy style, detailed medieval fantasy attire, leather and cloth textures")
        elif "sci-fi" in art_lower or "science" in art_lower:
            text += ("; futuristic sci-fi aesthetic, sleek textures, atmospheric cinematic lighting")
        elif b.era_wardrobe and "hanfu" not in ward_lower:
            text += f"; {b.art_direction or 'period drama'} aesthetic, authentic {b.era_wardrobe}"

    return text + "."


def _characters(
    b: PanelBrief, profile: ModelProfile, appearance: AppearanceInText
) -> tuple[list[PromptSection], dict[str, bool], dict[str, list[str]], list[Demeanour]]:
    sections: list[PromptSection] = []
    written: dict[str, bool] = {}
    fields: dict[str, list[str]] = {}
    dems: list[Demeanour] = []
    for c in b.characters:
        items = appearance_phrases(c, appearance)
        written[c.name] = bool(items)
        parts = [c.name]
        if c.is_creature or c.gender == "creature" or _CREATURE_WORDS.search(c.name):
            parts += ["monster", "creature", "non-human"]
        elif c.age_band and c.age_band != "adult":
            parts.append(c.age_band)
        parts += items
        if c.position and c.position != "center":
            parts.append(c.position)
        if c.pose and c.pose != "standing":
            parts.append(c.pose)
        if c.condition:
            parts.append(c.condition)
        sections.append(PromptSection(f"character:{c.name}", ", ".join(_tags(parts, profile))))
        d = derive_demeanour(c, b.mood, b.tension)
        fields[c.name] = d.fields_used
        dems.append(d)
    return sections, written, fields, dems


def _negative(b: PanelBrief, profile: ModelProfile) -> list[PromptSection]:
    parts = [PromptSection("negative:base", profile.negative_base)]
    if b.mode is OutputMode.MANGA:
        parts.append(PromptSection("negative:colour", _COLOUR_NEG))
    if not b.characters and b.crowd is None:
        parts.append(PromptSection("negative:people", "person, people, human, man, woman, 1boy, 1girl, crowd, face, figure"))
    elif b.crowd is None and len(b.characters) == 1:
        parts.append(PromptSection("negative:crowd", "crowd, multiple people"))
    if b.characters and all(c.gender == "male" for c in b.characters) and (b.crowd is None or b.crowd.gender == "male"):
        parts.append(PromptSection("negative:gender", "girl, woman, female, 1girl"))
    if b.is_indoor or bool(_INDOOR_KEYWORDS.search(f"{_location_text(b)} {b.setting}")):
        parts.append(PromptSection("negative:indoor", "outdoor, open sky, mountains, exterior, outside, trees"))
    parts.append(PromptSection("negative:style", "chibi, moe, kawaii, childlike, cat ears, school uniform, modern clothing"))
    return parts


def _compile_sdxl(b: PanelBrief, profile: ModelProfile, appearance: AppearanceInText) -> CompiledPrompt:
    char_sections, written, fields, dems = _characters(b, profile, appearance)
    s: list[PromptSection] = [
        PromptSection("quality", profile.quality_tags),
        PromptSection("count", ", ".join(_tags(_count_tags(b), profile))),
    ]
    if char_sections:
        s += char_sections
        exp = [t for d in dems for t in d.tags]
        if exp:
            s.append(PromptSection("expression", ", ".join(_tags(exp, profile))))
    if b.action:
        s.append(PromptSection("action", ", ".join(_tags([b.action], profile))))
    if b.crowd is not None:
        s.append(PromptSection("crowd", ", ".join(_tags([b.crowd.description, b.crowd.stance], profile))))
    setting = [_location_text(b), b.setting]
    if b.is_indoor or bool(_INDOOR_KEYWORDS.search(f"{_location_text(b)} {b.setting}")):
        setting.insert(0, "indoor interior, room")
    if any(setting):
        s.append(PromptSection("setting", ", ".join(_tags(setting, profile))))
    s.append(PromptSection("composition", ", ".join(_tags([_SHOT.get(b.shot, "medium shot"), b.camera], profile))))
    if b.lighting:
        s.append(PromptSection("lighting", ", ".join(_tags([b.lighting], profile))))
    if b.key_objects:
        s.append(PromptSection("objects", ", ".join(_tags(b.key_objects, profile))))
    if b.mood:
        s.append(PromptSection("mood", ", ".join(_tags([b.mood], profile))))
    style = _mode_tags(b) + ([b.art_direction] if b.art_direction else []) + ([b.era_wardrobe] if b.era_wardrobe else [])
    s.append(PromptSection("style", ", ".join(_tags(style, profile))))
    s = [x for x in s if x.text]
    neg = _negative(b, profile)
    return CompiledPrompt(
        positive=", ".join(x.text for x in s), negative=", ".join(x.text for x in neg), sections=s,
        negative_sections=neg, family=profile.family, mode=b.mode, appearance_written=written, demeanour_fields=fields,
    )


def _compile_anima(b: PanelBrief, profile: ModelProfile, appearance: AppearanceInText) -> CompiledPrompt:
    char_sections, written, fields, dems = _characters(b, profile, appearance)
    s: list[PromptSection] = [
        PromptSection("quality", profile.quality_tags),
        PromptSection("count", ", ".join(_tags(_count_tags(b), profile))),
    ]
    s += char_sections
    tags = [b.action] + [_SHOT.get(b.shot, "medium shot"), b.camera] + _mode_tags(b) + ([b.art_direction] if b.art_direction else [])
    s.append(PromptSection("tags", ", ".join(_tags(tags, profile))))
    # Natural language, 2 to 4 sentences (card: "at least two sentences", describe each named character).
    lead = b.characters[0] if b.characters else None
    place = _location_text(b)
    first = (f"{lead.name} stands " if lead else "The scene shows ") + (f"in {place}" if place else "in frame")
    if b.crowd is not None:
        first += f", while {b.crowd.description} {b.crowd.stance or 'look on'}"
    first += "."
    sentences = [first]
    if dems and lead is not None:
        action = f" while {b.action.replace('_', ' ')}" if b.action else ""
        sentences.append(f"{dems[0].sentence.rstrip('.')}{action}.")
    extra = ", ".join(x for x in (b.setting.replace("_", " "), b.lighting.replace("_", " "), b.mood.replace("_", " ")) if x)
    if extra:
        sentences.append(f"The scene is lit and set with {extra}.")
    if b.key_objects:
        sentences.append(f"Visible: {', '.join(b.key_objects)}.")
    s.append(PromptSection("prose", " ".join(sentences[:4])))
    s = [x for x in s if x.text]
    neg = _negative(b, profile)
    return CompiledPrompt(
        positive=", ".join(x.text for x in s[:-1]) + ". " + s[-1].text,
        negative=", ".join(x.text for x in neg), sections=s, negative_sections=neg, family=profile.family, mode=b.mode,
        appearance_written=written, demeanour_fields=fields,
    )


# ---------------------------------------------------------------------------
# graph readers (lazy imports keep `compile_prompt` itself free of the store)
# ---------------------------------------------------------------------------


def _big_five(raw: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in (raw or "").split(","):
        key, _, value = part.partition("=")
        try:
            out[key.strip()] = float(value)
        except ValueError:
            continue
    return out


def character_brief(
    store: object, novel_id: str, self_id: str, position: float, *, stated_expression: str = "",
    gender_hint: str = "", lead: bool = False, beat_text: str = "",
) -> CharacterBrief:
    """One character's state at story `position`: persona body, position-scoped appearance, genre defaults, traits.

    Same sources `render/panels.py::character_looks` uses (`persona_at`, `appearance_of(position=)`, `resolve_appearance`,
    `_demographics`), so a compiled prompt and the legacy one describe the same body. `gender_hint` fills a gender the
    stored profile leaves `unknown` (Fang Yuan reads `unknown` in the RI database), and only then.
    """
    from echotales.pipeline.persona.attire import resolve_appearance
    from echotales.pipeline.persona.reference_gen import _demographics, appearance_of
    from echotales.pipeline.persona.split import persona_at, standing_values

    entity = store.get_self(self_id)  # type: ignore[attr-defined]
    persona_id = persona_at(store, self_id, position)  # type: ignore[arg-type]
    stated = appearance_of(store, persona_id, standing_only=False, position=position)  # type: ignore[arg-type]
    appearance = resolve_appearance(novel_id, stated)
    if beat_text:
        from echotales.pipeline.render.panels import apply_transient_overrides

        # Torn robes and blood come from what this beat's prose says, exactly as `character_looks` does.
        appearance = apply_transient_overrides(appearance, beat_text)
    attire = appearance.pop("typical_attire", "")
    condition = appearance.pop("current_condition", "")
    gender, age = _demographics(store, persona_id, novel_id=novel_id, entity_id=self_id, position=position)  # type: ignore[arg-type]
    values = standing_values(store, persona_id, position=position)  # type: ignore[arg-type]
    years = 0
    if age in ("child", "youth", "teen", "teenager", "adolescent"):
        from echotales.pipeline.persona.reference_gen import body_age_years

        years = body_age_years(store, persona_id, novel_id=novel_id, entity_id=self_id, position=position)  # type: ignore[arg-type]
    return CharacterBrief(
        name=entity.canonical_label, gender=gender if gender in ("male", "female") else (gender_hint or "unknown"),
        age_band=age, age_years=years, appearance=appearance, attire=attire, condition=condition,
        big_five=_big_five(values.get("big_five", "")), register=values.get("register", ""),
        stated_expression=stated_expression, lead=lead,
    )


def _match_director_characters(store: object, self_ids: list[str], dir_chars: list) -> list[tuple[object, str]]:
    """Pair each director character with the cast self whose label or alias it names, in the director's order.

    The pairing used to be by list index, so a director that listed the second cast member first (it lists whoever the
    passage leads with, `self_ids` follow the cast order) gave each person the other's body, pose and expression.
    A name matches a label or alias exactly, else when its words are all inside one label (`Fang` for `Fang Yuan`) and
    that label is the only candidate; a self is used once. A director name that matches nobody is dropped with a log
    line (it is not in CAST, see `direction._validate_direction`). Empty result means nothing matched, and the caller
    then draws the cast as given rather than a panel with no people."""
    from echotales.core.enums import TargetKind

    names: dict[str, set[str]] = {}
    for sid in self_ids:
        entity = store.get_self(sid)  # type: ignore[attr-defined]
        labels = {entity.canonical_label} if entity is not None and entity.canonical_label else set()
        labels |= {a.alias for a in store.get_aliases_for(TargetKind.SELF, sid)}  # type: ignore[attr-defined]
        names[sid] = {" ".join(x.casefold().split()) for x in labels if x}
    pairs: list[tuple[object, str]] = []
    used: set[str] = set()
    for cd in dir_chars:
        want = " ".join((getattr(cd, "name", "") or "").casefold().split())
        free = [sid for sid in self_ids if sid not in used]
        hit = [sid for sid in free if want in names[sid]]
        if not hit and want:
            hit = [sid for sid in free if any(set(want.split()) <= set(n.split()) for n in names[sid])]
        if len(hit) == 1:
            used.add(hit[0])
            pairs.append((cd, hit[0]))
        else:
            log.info("director character %r matches no unused cast member (%s) -- dropped", getattr(cd, "name", ""),
                     "ambiguous" if hit else "not in cast")
    return pairs


def brief_from_direction(
    store: object, novel_id: str, self_ids: list[str], position: float, direction: object | None, *, location: str = "",
    mode: OutputMode = OutputMode.MANGA, is_crowd: bool = False, gender_hint: str = "", beat_text: str = "",
) -> PanelBrief:
    """A `PanelBrief` from the panel's cast and the director's `PanelDirection` (setting, lighting, layout, action, mood).

    The crowd comes from the director's layout and the crowd-cut flag, never from the headcount tag: the old path wrote
    "solo" because nothing here knew a crowd existed."""
    art, wardrobe, manhua = genre_direction(novel_id)
    d = direction
    layout = (getattr(d, "layout", "") or "").lower()
    crowd = None
    others_dir = getattr(d, "others", None)
    if others_dir is not None and getattr(others_dir, "kind", ""):
        raw_count = getattr(others_dir, "count", 0)
        count = int(raw_count) if isinstance(raw_count, int) or (isinstance(raw_count, str) and raw_count.isdigit()) else 0
        crowd = CrowdBrief(
            description=others_dir.kind,
            size="many" if count == 0 or count > 4 else "few",
            gender="male" if gender_hint == "male" else "mixed",
            stance=getattr(others_dir, "relation_to_lead", "") or "around the lead",
            count=count,
        )
    elif is_crowd or any(w in layout for w in ("surround", "crowd", "ring", "outnumber", "multiple", "army")):
        crowd = CrowdBrief(description="many people", size="many", gender="male" if gender_hint == "male" else "mixed",
                           stance=(getattr(d, "layout", "") or "around the lead").replace("_", " "))
    mood = getattr(d, "mood", "") or ""
    composition = (getattr(d, "composition", "") or "").strip()
    if composition:
        # The paragraph carries the beat's clothing and wounds; the identity sentence must stay the interval's fixed
        # wording, so beat prose is not allowed to rewrite attire or condition (it put "deep green robes" on the reborn
        # boy and "young and soft" on the cliff, EVOLUTION 4.164).
        beat_text = ""

    dir_chars = getattr(d, "characters", []) or []
    matched = _match_director_characters(store, self_ids, dir_chars) if dir_chars else []
    chars: list[CharacterBrief] = []
    if matched:
        for i, (cd, sid) in enumerate(matched):
            expr = getattr(cd, "expression", "") or (getattr(d, "expression", "") if i == 0 else "")
            cb = character_brief(
                store, novel_id, sid, position, gender_hint=gender_hint, lead=i == 0,
                stated_expression=expr, beat_text=beat_text,
            )
            cb.position = getattr(cd, "position", "center") or "center"
            cb.pose = getattr(cd, "pose", "standing") or "standing"
            if getattr(cd, "condition", "") and not composition:
                cb.condition = cd.condition
            chars.append(cb)
    else:
        for i, sid in enumerate(self_ids):
            cb = character_brief(
                store, novel_id, sid, position, gender_hint=gender_hint, lead=i == 0,
                stated_expression=(getattr(d, "expression", "") or "") if i == 0 else "",
                beat_text=beat_text,
            )
            chars.append(cb)

    camera = getattr(d, "camera_angle", "") or getattr(d, "camera", "") or ""
    loc_detail = getattr(d, "location_detail", "") or ""
    props = list(getattr(d, "props", []) or []) + list(getattr(d, "key_objects", []) or [])
    is_indoor = bool(_INDOOR_KEYWORDS.search(f"{location} {getattr(d, 'setting', '')} {loc_detail}"))

    return PanelBrief(
        novel_id=novel_id, characters=chars, crowd=crowd, location=location,
        location_description=loc_detail,
        setting=getattr(d, "setting", "") or "", lighting=getattr(d, "lighting", "") or "",
        shot=getattr(d, "shot", "medium") or "medium", camera=camera,
        action=getattr(d, "action", "") or "",
        key_objects=props, mood=mood,
        tension=0.8 if any(w in mood.lower() for w in _TENSE) else 0.0, mode=mode, art_direction=art,
        era_wardrobe=wardrobe, manhua=manhua, is_indoor=is_indoor,
        composition=composition, staging=(getattr(d, "staging", "") or "") if composition else "",
        visual_source=getattr(d, "visual_source", "") or "",
    )
