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

import re
from dataclasses import dataclass, field
from enum import StrEnum

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
    gender: str = "unknown"  # male | female | unknown
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
    camera: str = ""  # "low angle", "from above"
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


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("_", " ")).strip().strip(",.")


def identity_sentence(c: CharacterBrief, appearance: AppearanceInText = AppearanceInText.SHORT) -> str:
    """The fixed one-sentence description of a character, built only from the graph's body facts (hair, eyes, marks, attire).

    Identical wording in every panel of the same character is the stopgap for identity until reference-image conditioning
    exists: the probe (2026-11-16) drew the same hero with a different face in three panels of one scene whenever the
    description changed between prompts. Nothing scene-dependent (wounds, mood, action) goes in; those are separate
    sentences. Facts are written in the order the model should weigh them: hair, eyes, marks, then clothes."""
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
    text = head
    if feats:
        text += " with " + (", ".join(feats[:-1]) + " and " + feats[-1] if len(feats) > 1 else feats[0])
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
    lead = b.characters[0] if b.characters else None
    s: list[PromptSection] = []
    shot = _NATURAL_SHOT.get(b.shot, "A medium shot") + (f", {_plain(b.camera)}" if b.camera else "")
    action = _plain(b.action)
    framing = f", framing {lead.name}" if lead else ""
    s.append(PromptSection("composition", f"{shot}{framing}{': ' + action if action else ''}."))
    written: dict[str, bool] = {}
    fields: dict[str, list[str]] = {}
    if lead is not None:
        s.append(PromptSection(f"character:{lead.name}", identity_sentence(lead, appearance)))
        written[lead.name] = appearance is not AppearanceInText.OFF
        d = derive_demeanour(lead, b.mood, b.tension)
        fields[lead.name] = d.fields_used
        face = _face_words(d.tags)
        extra = f" {lead.name}'s condition: {_plain(lead.condition)}." if lead.condition else ""
        s.append(PromptSection("demeanour", f"{lead.name}'s face is {face}.{extra}"))
    others = b.characters[1:]
    for c in others:
        written[c.name] = appearance is not AppearanceInText.OFF
        fields[c.name] = derive_demeanour(c, b.mood, b.tension).fields_used
    parts = []
    if others:
        parts.append(" ".join(identity_sentence(c, appearance) for c in others))
    if b.crowd is not None:
        who = lead.name if lead else "the center of the frame"
        stance = _plain(b.crowd.stance) or f"stand close around {who}"
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
    if where or tail:
        sentence = (f"The setting is {where}" if where else "The scene is") + (f"; {tail}" if tail and where else f" {tail}" if tail else "")
        s.append(PromptSection("setting", sentence + "." + objs))
    s.append(PromptSection("style", _style_sentence(b)))
    s = [x for x in s if x.text]
    return CompiledPrompt(
        positive=" ".join(x.text for x in s), negative="", sections=s, negative_sections=[], family=profile.family,
        mode=b.mode, appearance_written=written, demeanour_fields=fields,
    )


def _style_sentence(b: PanelBrief) -> str:
    if b.mode is OutputMode.MANGA:
        text = ("A crisp black-and-white manga illustration: a single full-bleed image with clean black ink linework and "
                "screentone shading, pure black and white only, no panel borders, no speech bubbles and no text")
    else:
        text = "A richly coloured painted illustration: a single full-bleed image with no panel borders, no speech bubbles and no text"
    if b.manhua:
        # One sentence on purpose (the profile is 3-6 sentences); the exclusions are stated because a Japanese torii gate
        # and short hair appeared in the NoobAI compiled-manga run of 2026-11-16.
        text += ("; Chinese manhua and donghua style, an ancient-Chinese xianxia world with hanfu robes and traditional "
                 "Chinese architecture, explicitly not Japanese, with no kimono, no katana and no torii gate")
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
        parts = [c.name] + ([c.age_band] if c.age_band and c.age_band != "adult" else []) + items
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
    if b.crowd is None and len(b.characters) == 1:
        parts.append(PromptSection("negative:crowd", "crowd, multiple people"))
    if b.characters and all(c.gender == "male" for c in b.characters) and (b.crowd is None or b.crowd.gender == "male"):
        parts.append(PromptSection("negative:gender", "girl, woman, female, 1girl"))
    parts.append(PromptSection("negative:style", "chibi, moe, kawaii, childlike, cat ears, school uniform, modern clothing"))
    return parts


def _compile_sdxl(b: PanelBrief, profile: ModelProfile, appearance: AppearanceInText) -> CompiledPrompt:
    char_sections, written, fields, dems = _characters(b, profile, appearance)
    s: list[PromptSection] = [
        PromptSection("quality", profile.quality_tags),
        PromptSection("count", ", ".join(_tags(_count_tags(b), profile))),
    ]
    s += char_sections
    exp = [t for d in dems for t in d.tags]
    if exp:
        s.append(PromptSection("expression", ", ".join(_tags(exp, profile))))
    if b.action:
        s.append(PromptSection("action", ", ".join(_tags([b.action], profile))))
    if b.crowd is not None:
        s.append(PromptSection("crowd", ", ".join(_tags([b.crowd.description, b.crowd.stance], profile))))
    setting = [_location_text(b), b.setting]
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
    return CharacterBrief(
        name=entity.canonical_label, gender=gender if gender in ("male", "female") else (gender_hint or "unknown"),
        age_band=age, appearance=appearance, attire=attire, condition=condition,
        big_five=_big_five(values.get("big_five", "")), register=values.get("register", ""),
        stated_expression=stated_expression, lead=lead,
    )


def brief_from_direction(
    store: object, novel_id: str, self_ids: list[str], position: float, direction: object | None, *, location: str = "",
    mode: OutputMode = OutputMode.MANGA, is_crowd: bool = False, gender_hint: str = "",
) -> PanelBrief:
    """A `PanelBrief` from the panel's cast and the director's `PanelDirection` (setting, lighting, layout, action, mood).

    The crowd comes from the director's layout and the crowd-cut flag, never from the headcount tag: the old path wrote
    "solo" because nothing here knew a crowd existed."""
    art, wardrobe, manhua = genre_direction(novel_id)
    d = direction
    layout = (getattr(d, "layout", "") or "").lower()
    crowd = None
    if is_crowd or any(w in layout for w in ("surround", "crowd", "ring", "outnumber", "multiple", "army")):
        crowd = CrowdBrief(description="many people", size="many", gender="male" if gender_hint == "male" else "mixed",
                           stance=(getattr(d, "layout", "") or "around the lead").replace("_", " "))
    mood = getattr(d, "mood", "") or ""
    chars = [
        character_brief(store, novel_id, sid, position, gender_hint=gender_hint, lead=i == 0,
                        stated_expression=(getattr(d, "expression", "") or "") if i == 0 else "")
        for i, sid in enumerate(self_ids)
    ]
    return PanelBrief(
        novel_id=novel_id, characters=chars, crowd=crowd, location=location,
        setting=getattr(d, "setting", "") or "", lighting=getattr(d, "lighting", "") or "",
        shot=getattr(d, "shot", "medium") or "medium", action=getattr(d, "action", "") or "",
        key_objects=list(getattr(d, "key_objects", []) or []), mood=mood,
        tension=0.8 if any(w in mood.lower() for w in _TENSE) else 0.0, mode=mode, art_direction=art,
        era_wardrobe=wardrobe, manhua=manhua,
    )
