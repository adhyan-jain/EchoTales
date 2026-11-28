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
import os
import re
from dataclasses import dataclass, field
from enum import StrEnum

from echotales.pipeline.render.framing import rows_not_ring

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
    # Art bake-off v3 (arm C2): the open Illustrious-XL v0.1 base that NoobAI-XL itself was trained from. It is read as plain
    # danbooru tags with the masterpiece-family quality words (its card); NoobAI's score_* tags mean nothing to it.
    "illustrious-xl-0.1": ModelProfile(
        key="illustrious-xl-0.1",
        model_id="OnomaAIResearch/Illustrious-xl-early-release-v0",
        family=PromptFormat.SDXL_TAGS,
        width=832, height=1216, steps=28, guidance=5.5, sampler="euler_a",
        quality_tags="masterpiece, best quality, amazing quality, very aesthetic, absurdres",
        negative_base=(
            "worst quality, low quality, lowres, bad anatomy, bad hands, extra digits, jpeg artifacts, text, "
            "speech bubble, watermark, signature, username, logo, blurry"
        ),
        licence="fair-ai-public-license-1.0-sd (HF card metadata; non-commercial style share-alike terms)",
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


def default_model() -> str:
    """The configured image model (`render.image_model`: Z-Image Turbo since D58). This used to be a constant "noobai-xl-1.1",
    so a bare `compile_prompt(brief)` wrote NoobAI tags although every real render is Z-Image (EVOLUTION 4.171)."""
    from echotales.pipeline.config import get_settings

    return str(get_settings().render_image_model)


def model_profile(key: str | None = None) -> ModelProfile:
    """The profile for `key`, or for the configured image model when none is given. A key the engine registry
    (`pipeline/engines/registry.py`) does not list on the compiler surface raises, because a typo silently rendering with another
    model would make a model comparison meaningless."""
    from echotales.pipeline.engines import registry

    chosen = (key or default_model()).strip().lower()
    if chosen not in registry.compiler_profiles() or chosen not in PROFILES:
        raise ValueError(f"unknown image model {key!r}; expected one of {sorted(registry.compiler_profiles())}")
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
    #: The interval's locked hair, eyes, build and outfit plus the scene-stated state (`persona/identity_lock.py`). When
    #: set, `identity_sentence` is built from it, so every panel of the interval repeats the same words.
    locked: object | None = None
    #: The listener of an over-the-shoulder shot: drawn once, as the back of a head in the foreground, and nowhere else in the
    #: panel (not in the paragraph, not in Blocking, no face).
    back_turned: bool = False


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
    #: The framing sentence (`render/framing.py`) written right after the style lead, and its focus ("prop" is an insert with
    #: nobody in it, "eyes" and "hands" are crops of the lead).
    framing: str = ""
    frame_focus: str = ""
    #: The prop an insert is about ("lamp"): the staging Set is cut to the clauses that name it.
    frame_subject: str = ""
    #: True when the text names no weapon, no held thing and no seat for the lead: the compiler then states the hands, because the
    #: model's prior for a robe is a sword (RI cliff r4, 5 of 13 panels).
    empty_hands: bool = False
    #: The lead's face as drawn parts (`render/face.py`), written right after the identity so it is not the paragraph's last words.
    face: str = ""
    #: The light and mood grade written from the scene's stated time and light source (`render/lightgrade.py`), right after the
    #: framing; empty when the text states no light.
    grade: str = ""
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
#: Adults are drawn as adults: a face with a defined jaw and mature proportions, never the big-eyed round face of a child.
_ADULT_FACE = ", an adult face with a defined jaw and mature proportions"
_CHILD_NOUN = {"male": "boy", "female": "girl", "unknown": "child"}
_TEEN_NOUN = {"male": "teenage boy", "female": "teenage girl", "unknown": "teenager"}
_CREATURE_WORDS = re.compile(r"\b(beast|centipede|demon|spirit|dragon|monster|imp|wolf|chimera|creature|fiend)\b", re.IGNORECASE)
_INDOOR_KEYWORDS = re.compile(
    r"\b(room|hall|chamber|house|interior|bed|study|cabin|palace\s+interior|shop|dungeon|cell|pavilion\s+interior|bamboo\s+house)\b",
    re.IGNORECASE,
)


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("_", " ")).strip().strip(",.")


def body_is_young(age_band: str, age_years: int = 0) -> bool:
    """Whether a body is drawn as a child or a teenager. The graph's "youth" band covers 13 to about 25 and was always drawn as a
    teenage boy, so LotM's 22-year-old Klein came out about twelve (round 3, 16 of 16 panels): "youth" is young only when a stated
    age says under 18; with no age it is a young adult. Child, teen, teenager and adolescent stay young."""
    band = (age_band or "").lower()
    if band == "youth":
        return 0 < age_years < 18
    return band in ("child", "teen", "teenager", "adolescent")


def _identity_head(c: CharacterBrief) -> tuple[str, bool]:
    """`("Name is a 15-year-old boy", young)`: who the person is before any look."""
    age_band = (c.age_band or "").lower()
    young = body_is_young(age_band, c.age_years)
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
    elif young:
        noun = _TEEN_NOUN.get(c.gender, "teenager")
        head = f"{c.name} is a {noun}"
    else:
        noun = _NOUN.get(c.gender, "person")
        age = c.age_band if c.age_band and c.age_band not in ("adult", "unknown", "youth") else ""
        if age_band == "youth":
            age = "young"
        head = f"{c.name} is a{'n' if (age or noun)[0] in 'aeiou' else ''} {f'{age} ' if age else ''}{noun}"
    return head, young


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

    head, young = _identity_head(c)

    if appearance is AppearanceInText.OFF:
        return head + "."
    if c.locked is not None:
        # The interval's locked words (`persona/identity_lock.py`): hair style, build and clothes included, so the model has
        # nothing left to choose per panel. A young body keeps its youthful face, which the lock does not carry.
        # A stated age and a youthful face still drew a tall grown man (RI rebirth r4): the build is stated for a young body too.
        face = (", a smooth youthful face and a " + ("slight build" if c.gender == "female" else "slim boyish build")
                + ", still growing, shorter than a grown adult") if young else _ADULT_FACE if c.age_band != "elder" else ""
        return _plain(f"{head} with {c.locked.description()}{face}") + "."  # type: ignore[attr-defined]
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
    elif c.age_band != "elder":
        text += _ADULT_FACE
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
    if b.composition or b.framing:
        # A blanked paragraph (director rejected for a crowd or a group) still has the planned framing and the staging sheet:
        # the old sentence below ended in "ink-wash mountains, mist, painterly" and 4 of 4 such RI cliff panels came out as a
        # white-ground ink-wash painting (round 5, EVOLUTION 4.173).
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




def _back_identity(c: CharacterBrief, appearance: AppearanceInText) -> str:
    """The identity sentence of the back-turned listener: his own hair and clothes (so the foreground figure matches the man the
    reader knows, P&P ch1 v3 drew an unrelated dark-coated stranger), with the face sentence swapped for the fact that it is hidden."""
    text = identity_sentence(c, appearance).replace(_ADULT_FACE, "").rstrip(" .")
    text = text.replace(", a smooth youthful face", "")
    return f"{text}. He is the figure in the foreground seen from behind, his face turned away and hidden." if c.gender != "female" else (
        f"{text}. She is the figure in the foreground seen from behind, her face turned away and hidden.")


def _compile_composed(b: PanelBrief, profile: ModelProfile, appearance: AppearanceInText) -> CompiledPrompt:
    """Z-Image prompt in the order of the probe prompts the owner liked: a short style lead, the director's composed
    paragraph, one fixed identity sentence per visible character, then setting and light.

    Why: the 2026-11-16 real render opened with a composition fragment and closed with a 60-word style paragraph, and
    drew the same standing man in 10 of 18 panels; the hand-written probes were a lead plus one composed scene and drew the
    crowd ringing the hero. The identity sentences are identical on every panel of an interval (looks stay consistent) and
    nothing scene-dependent is in them; wounds and clothing state live in the paragraph, which comes from the panel's text.
    Setting clauses the paragraph already says are not repeated."""
    from echotales.pipeline.persona.genre import style_lead
    lead = style_lead(b.novel_id, people=b.frame_focus != "prop", look="bw" if b.mode is OutputMode.MANGA else "colour")
    s = [PromptSection("style", lead)]
    # The framing comes straight after the style lead: Z-Image has no CFG, so the shot named first and plainly is the shot drawn.
    # Before this the compiled prompt never named a shot (16 of 16 LotM panels were one medium shot, EVOLUTION 4.171).
    if b.framing:
        s.append(PromptSection("framing", b.framing))
    insert = b.frame_focus == "prop"
    if b.grade:
        # "the subject lit only by ..." read as a person in an insert and drew men beside the lamp (round 5 LotM p7, p13).
        s.append(PromptSection("grade", b.grade.replace("the subject", "the object") if insert else b.grade))
    # A view with no face in it (an insert, from behind, from above) has no paragraph and no face sentence: both describe a person
    # facing the viewer.
    faceless = insert or b.frame_focus in _FACELESS_FOCUS
    # The listener of an over-the-shoulder shot is the back of a head and nothing else: the director's paragraph places him
    # ("her husband who sits calmly in an armchair") and would draw him a second time, so it goes (P&P ch1 v3).
    back_view = any(c.back_turned for c in b.characters)
    staging_text = trim_staging(b.staging.strip(), b.frame_focus, b.shot, b.frame_subject) if b.staging else ""
    staging_text = rows_not_ring(blocking_of_drawn(staging_text, [c.name for c in b.characters if not c.back_turned]))
    stage = PromptSection("staging", staging_text) if staging_text else None
    cropped = rows_not_ring(b.composition.strip())
    if b.shot == "close" and b.frame_focus in ("", "eyes", "hands"):
        from echotales.pipeline.render.framing import (
            crop_composition,
        )

        cropped = crop_composition(cropped, b.frame_focus) if b.frame_focus != "hands" else ""
    comp = None if faceless or back_view or not cropped else PromptSection("composition", cropped)
    written: dict[str, bool] = {}
    fields: dict[str, list[str]] = {}
    # Identity right after the style lead, before the scene: Z-Image has no CFG, so what the prompt says first and fixedly is
    # what holds (RI cliff scene 2026-11-20: with the identity last, the robe changed colour and the hair style changed in
    # 13 panels of one scene; staging and the paragraph carried the scene and said nothing of clothes).
    for c in b.characters:
        if b.frame_focus in ("reverse", "overview"):
            # Round 7: a reverse shot on the crowd leaves the lead out; with his identity sentence the model drew him in the middle of
            # the crowd, who stood around him facing the viewer (cliff r7 p4).
            continue
        s.append(PromptSection(f"character:{c.name}", _back_identity(c, appearance) if c.back_turned else identity_sentence(c, appearance)))
        written[c.name] = appearance is not AppearanceInText.OFF
        fields[c.name] = derive_demeanour(c, b.mood, b.tension).fields_used
    # The lead's face as drawn parts, straight after the identity and before the scene: said once, last and in three words
    # ("cold mocking smile") it drew a mild smile; "mocking" must read as mocking (round 3, defect 7).
    if b.face and b.characters and (not faceless or b.frame_focus in _FACE_FOCUS):
        s.append(PromptSection("face", f"{b.characters[0].name}'s face: {b.face}."))
    if b.empty_hands and b.characters and not faceless and b.shot != "close":
        lead_c = b.characters[0]
        s.append(PromptSection("hands", f"{lead_c.name}'s hands hang empty at {'her' if lead_c.gender == 'female' else 'his'} sides."))
    if b.crowd is not None and not b.composition and not faceless:
        # With the paragraph blanked nothing says where the others stand, and the fallback "they surrounding" drew them behind and
        # around the lead facing the same way, so he read as their leader (RI cliff r4 p5). Opponents face the lead across a gap.
        who = b.characters[0].name if b.characters else "the lead"
        stance = b.crowd.stance.lower()
        if re.search(r"\b(?:circle|ring|encircl\w*)\b", stance):
            where = f"in rows facing {who}"  # never a ring: owner rule, round 8
        else:
            where = f"on the far side of a gap from {who}, all of them facing {who}"
        s.append(PromptSection("others", f"{_headcount(b.crowd)} {_plain(b.crowd.description)} stand packed close together {where}."))
    # A close shot leads with its own paragraph: staging first drew a second small hero at the cliff edge behind the
    # foreground one (2 of 2 seeds, 2026-11-19); paragraph first drew one (2 of 2).
    s += [x for x in ((comp, stage) if (stage and b.shot == "close") else (stage, comp)) if x]
    said = f"{cropped} {staging_text}".lower()
    clauses: list[str] = []
    # A staging sheet that names a Set is the one statement of the place (and "Light:" of the light): the genre locale and the
    # director's own setting are guesses from cue words, and appended after it they drew a timber hall and an open field on
    # a cliff scene (RI ch1, 2026-11-19, panels 9-15).
    staged_set = bool(re.search(r"\bSet:", b.staging))
    staged_light = bool(re.search(r"\bLight:", b.staging))
    if not staged_set:
        for x in [t.strip() for t in f"{_plain(_location_text(b))},{_plain(b.setting)}".split(",")]:
            if x and x.lower() not in said and x.lower() not in (y.lower() for y in clauses):
                clauses.append(x)
    light = _plain(b.lighting)
    if light and light.lower() not in said and not staged_light:
        clauses.append(f"the light is {light}")
    if clauses:
        s.append(PromptSection("setting", f"Setting: {'; '.join(clauses)}."))
    return CompiledPrompt(
        positive=" ".join(x.text for x in s), negative="", sections=s, negative_sections=[], family=profile.family,
        mode=b.mode, appearance_written=written, demeanour_fields=fields,
    )


#: Round 7 views (EVOLUTION 4.182) with no paragraph, face or Blocking: they are not a person facing the viewer.
_ROUND7_FOCUS = ("reverse", "overview", "low", "down", "profile")
_FACELESS_FOCUS = ("behind", "topdown", *_ROUND7_FOCUS)
#: Of those, the views whose picture does show his face (a low angle from below, a profile): the face sentence stays, the paragraph and
#: Blocking do not.
_FACE_FOCUS = ("low", "profile")

_STAGE_PART = re.compile(r"\b(Set|Blocking|Light):\s*(.*?)(?=\s+(?:Set|Blocking|Light):|\Z)", re.S)


def trim_staging(staging: str, focus: str, shot: str, subject: str = "") -> str:
    """The staging sheet cut to what the shot can see. The sheet's Blocking line ("stands alone facing right; the others stand in
    rows") is a full-body, wide arrangement: left in a close-up it drew the crowd and the whole body again, and in an insert it
    drew the people. An insert keeps the Set clauses that name its prop (the whole Set drew the man again: "a desk in front of him",
    round 4 LotM p7); an eye or hand crop keeps only the Light; a close-up keeps the Set's first clause (the place) and the Light,
    because the furniture list pulled the picture back to a chest-up man at a desk; a view from behind or above keeps the whole Set
    and the Light, no Blocking; every other shot keeps the whole sheet."""
    parts = {m.group(1): f"{m.group(1)}: {m.group(2).strip()}" for m in _STAGE_PART.finditer(staging)}
    if not parts:
        return staging
    if focus == "prop":
        keep: tuple[str, ...] = ("Light",)
        clauses = [c.strip() for c in re.split(r";\s*", parts.get("Set", "")[len("Set:"):]) if c.strip()]
        named = [c for c in clauses if subject and re.search(rf"\b{re.escape(subject.split()[-1].lower())}", c.lower())
                 and not re.search(r"\b(?:him|her|them|his|hers)\b", c, re.I)]
        if named:
            parts["Set"] = "Set: " + "; ".join(named).rstrip(".") + "."
            keep = ("Set", "Light")
    elif focus in ("eyes", "hands"):
        keep = ("Light",)
    elif focus in ("behind", "topdown", *_ROUND7_FOCUS):
        keep = ("Set", "Light")
    elif shot == "close":
        keep = ("Set", "Light")
        first = re.split(r";\s*", parts.get("Set", "")[len("Set:"):].strip(), maxsplit=1)[0].strip().rstrip(".")
        if first:
            parts["Set"] = f"Set: {first}."
    else:
        return staging
    return " ".join(parts[k] for k in keep if k in parts)


_BLOCKED_PERSON = re.compile(
    r"^(?P<subj>(?:(?:Mr|Mrs|Ms|Miss|Dr|Lord|Lady|Sir|Elder|Master|Madam|Madame)\.?\s+)?[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,2})\s+"
    r"(?:stands?|sits?|kneels?|leans?|walks?|waits?|crouch\w*|lies|lie|is|are|faces?|looks?|watch\w*|rests?|paces?|hovers?|"
    r"hangs?|holds?|reclines?|perch\w*)\b")
_BLOCKED_GROUP = {"the", "a", "an", "others", "some", "several", "all", "everyone", "everybody", "two", "three", "four", "behind", "at", "in"}


def blocking_of_drawn(staging: str, drawn: list[str]) -> str:
    """The staging sheet with its Blocking line cut to the people this panel draws.

    P&P ch1 v3, p1 and p9: the scene's sheet blocked both spouses ("Mrs. Bennet stands on the left; Mr. Bennet stands on the
    right") but the panel's cast held only him, so the model drew the undescribed one as an unrequested woman in grey and the
    named one a second time. A clause is cut when it names one person (a capitalised name before a posture verb) who is not
    among `drawn`; group clauses ("the elders kneel in two rows") are kept, and an emptied Blocking line is dropped."""
    if not drawn or "Blocking:" not in staging:
        return staging
    from echotales.pipeline.render.direction import name_key

    keys = [name_key(n).split() for n in drawn]

    def drawn_name(subj: str) -> bool:
        words = name_key(subj).split()
        return any(set(words) <= set(k) or set(k) <= set(words) for k in keys)

    def keep(clause: str) -> bool:
        m = _BLOCKED_PERSON.match(clause.strip())
        return m is None or m.group("subj").split()[0].lower() in _BLOCKED_GROUP or drawn_name(m.group("subj"))

    parts = [(m.group(1), m.group(2).strip()) for m in _STAGE_PART.finditer(staging)]
    if not parts:
        return staging
    out: list[str] = []
    for label, body in parts:
        if label == "Blocking":
            kept = [c for c in re.split(r";\s*", body.rstrip(".")) if c.strip() and keep(c)]
            if not kept:
                continue
            body = "; ".join(kept) + "."
        out.append(f"{label}: {body}")
    return " ".join(out)


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
        # "ink-wash mountains", "mist" and "painterly" drew a white-ground ink painting (round 5); the same cel-shaded colour look
        # as the composed lead, with the xianxia clothing.
        return ("A Chinese donghua illustration in the guofeng style: clean fine lineart, soft cel shading, a muted cold palette and "
                "detailed cinematic backgrounds, a single full-bleed image with no panel borders, "
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
    gender_hint: str = "", lead: bool = False, beat_text: str = "", scene: object | None = None,
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
    persona_id = persona_at(store, self_id, position)
    stated = appearance_of(store, persona_id, standing_only=False, position=position)
    appearance = resolve_appearance(novel_id, stated)
    if beat_text:
        from echotales.pipeline.render.panels import apply_transient_overrides

        # Torn robes and blood come from what this beat's prose says, exactly as `character_looks` does.
        appearance = apply_transient_overrides(appearance, beat_text)
    attire = appearance.pop("typical_attire", "")
    condition = appearance.pop("current_condition", "")
    # The graph's own appearance facts, before the genre default fills any gap: the lock chooses its defaults itself, once.
    graph_facts = {k: v for k, v in stated.items() if v}
    gender, age = _demographics(store, persona_id, novel_id=novel_id, entity_id=self_id, position=position)
    values = standing_values(store, persona_id, position=position)
    years = 0
    if age in ("child", "youth", "teen", "teenager", "adolescent"):
        from echotales.pipeline.persona.reference_gen import body_age_years

        years = body_age_years(store, persona_id, novel_id=novel_id, entity_id=self_id, position=position)
    final_gender = gender if gender in ("male", "female") else (gender_hint or "unknown")
    young = body_is_young(age, years)
    from echotales.pipeline.persona.identity_lock import lock_for

    locked = lock_for(
        store, novel_id, self_id, persona_id, facts=graph_facts, gender=final_gender, young=young,
        name=entity.canonical_label, manhua=genre_direction(novel_id)[2], scene=scene,
        genre={k: v for k, v in appearance.items() if k in ("hair_color", "eye_color") and v and not graph_facts.get(k)},
    )
    # Look-by-epoch (`persona/looks.py`): what the text says this person looks like at THIS story time, with every gap filled
    # per person. The lock above gave every character the same genre-default sentence (RI v57: three people, one topknot) and
    # one set of robes for the whole chapter. An approved reference sheet is the approved description and still wins.
    if locked.source.get("hair") != "sheet" and os.environ.get("ECHOTALES_LOOK_BY_EPOCH", "1") != "0":
        from echotales.pipeline.persona import looks as _looks

        at = _looks.position_to_block(store, novel_id, position)
        if at is not None:
            look = _looks.look_at(
                store, novel_id, self_id, chapter=at[0], block=at[1], client=getattr(scene, "client", None),
            )
            locked = _looks.locked_from_look(look, locked.persona_id)
            if look.fact("age_band") is not None and not look.fact("age_band").invented:  # type: ignore[union-attr]
                age = _looks.COMPILER_BAND.get(look.age_band, age)
                years = years if body_is_young(age, years) else 0
            if final_gender not in ("male", "female") and look.gender:
                final_gender = look.gender
            condition = look.condition or ""
    return CharacterBrief(
        name=entity.canonical_label, gender=final_gender,
        age_band=age, age_years=years, appearance=appearance, attire=attire, condition=condition,
        big_five=_big_five(values.get("big_five", "")), register=values.get("register", ""),
        stated_expression=stated_expression, lead=lead, locked=locked,
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
    from echotales.pipeline.render.direction import name_key

    names: dict[str, set[str]] = {}
    for sid in self_ids:
        entity = store.get_self(sid)  # type: ignore[attr-defined]
        labels = {entity.canonical_label} if entity is not None and entity.canonical_label else set()
        labels |= {a.alias for a in store.get_aliases_for(TargetKind.SELF, sid)}  # type: ignore[attr-defined]
        names[sid] = {name_key(x) for x in labels if x}
    pairs: list[tuple[object, str]] = []
    used: set[str] = set()
    for cd in dir_chars:
        want = name_key(getattr(cd, "name", "") or "")
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
    scene: object | None = None,
) -> PanelBrief:
    """A `PanelBrief` from the panel's cast and the director's `PanelDirection` (setting, lighting, layout, action, mood).

    The crowd comes from the director's layout and the crowd-cut flag, never from the headcount tag: the old path wrote
    "solo" because nothing here knew a crowd existed."""
    from echotales.pipeline.render.lightgrade import light_grade

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
    passage = beat_text
    frame_focus = getattr(d, "frame_focus", "") or ""
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
                stated_expression=expr, beat_text=beat_text, scene=scene,
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
                beat_text=beat_text, scene=scene,
            )
            chars.append(cb)

    frame_subject = getattr(d, "frame_subject", "") or ""
    if frame_focus == "over-shoulder" and frame_subject and chars:
        # The listener named by the framing is drawn only as the back of a head; a director that listed him first must not make him
        # the lead of the face and framing sentences (the speaker leads the shot, EVOLUTION 4.190).
        from types import SimpleNamespace

        from echotales.pipeline.render.direction import name_key

        want = set(name_key(frame_subject).split())
        for c in chars:
            have = set(name_key(c.name).split())
            c.back_turned = bool(want) and (want <= have or have <= want)
        if not any(c.back_turned for c in chars):
            # The director drew only the speaker (P&P rerun: 1 listener in 3 was missing from `characters`): the back figure still
            # needs the listener's own hair and clothes, or the model invents a stranger, so he joins from the cast.
            for _cd, sid in _match_director_characters(store, self_ids, [SimpleNamespace(name=frame_subject)])[:1]:
                cb = character_brief(store, novel_id, sid, position, gender_hint=gender_hint, lead=False, stated_expression="",
                                     beat_text="" if composition else beat_text, scene=scene)
                if name_key(cb.name) not in {name_key(c.name) for c in chars}:
                    cb.back_turned = True
                    chars.append(cb)
        if any(c.back_turned for c in chars) and not all(c.back_turned for c in chars):
            chars.sort(key=lambda c: c.back_turned)  # stable: speaker(s) first, the listener last
            for i, c in enumerate(chars):
                c.lead = i == 0
        else:
            for c in chars:
                c.back_turned = False
    if frame_focus == "prop":
        # An insert of an object has nobody in it: the vision check must not expect a lead, nor the compiler draw one.
        chars, crowd = [], None
    lead_face = ""
    if chars:
        from echotales.pipeline.render.direction import name_key
        from echotales.pipeline.render.face import (
            drop_calm_clause,
            infer_expression,
            is_neutral,
        )

        # The director's entry for the person who leads the shot (the speaker, first in `chars`), not merely the first it listed.
        lead_dir = next((cd for cd in dir_chars if name_key(getattr(cd, "name", "") or "") == name_key(chars[0].name)),
                        dir_chars[0] if dir_chars else None)
        said = (getattr(lead_dir, "expression", "") if lead_dir is not None else "") or (getattr(d, "expression", "") or "")
        # An over-the-shoulder panel whose lead is the one listening: the line's emotion belongs to the speaker behind, so only the
        # director's own reading of the reaction is used there (render/speech.py, rule 15). When the lead speaks to a back-turned
        # listener (EVOLUTION 4.190) the line IS the lead's, and is read like any other.
        lead_face = said if frame_focus == "over-shoulder" and not any(c.back_turned for c in chars) else infer_expression(said, passage, mood=mood)
        # Round 8 (RI ch1 v56): this block ran only when the director wrote a paragraph, so a close-up or eye crop with none got no
        # face sentence at all (22 of 45 panels had no face line, 34 of 45 a director face that was its own example phrase).
        if composition and lead_face and not is_neutral(lead_face):
            composition = drop_calm_clause(composition)

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
        framing=getattr(d, "frame", "") or "", frame_focus=frame_focus, face=_drawn(lead_face),
        frame_subject=getattr(d, "frame_subject", "") or "",
        empty_hands=bool(chars) and not props and not _HOLDS.search(f"{passage} {composition} {getattr(d, 'staging', '') or ''}"),
        grade=light_grade(
            (getattr(d, "staging", "") or "") if composition else "", getattr(d, "lighting", "") or "", passage,
            f"{location} {getattr(d, 'setting', '')} {loc_detail}", composition, mood=mood, mono=mode is OutputMode.MANGA,
        ),
    )


#: Anything that gives the lead's hands something to do, or a seat or surface to rest them on: the empty-hands sentence is only for a
#: standing figure whose text names nothing held (a robe's prior is a sword; a desk scene's hands are on the desk).
_HOLDS = re.compile(
    r"\b(?:hold\w*|held|grip\w*|clutch\w*|carr(?:y|ies|ied|ying)|wield\w*|draw[sn]?|drew|raise[sd]?|lift\w*|pick\w*|took|take[sn]?|"
    r"reach\w*|point\w*|clasp\w*|cross\w*|fold\w*|sit\w*|sat|seat\w*|kneel\w*|knelt|lying|lies|lay|desk|table|bed|chair|"
    r"hands?|fists?|fingers?|palms?|sleeves?|pocket\w*)\b", re.I)


def _drawn(expression: str) -> str:
    from echotales.pipeline.render.face import drawn_face

    return drawn_face(expression) if expression else ""
