"""Arm C2: a storyboard `Panel` + its `PanelBrief` -> Danbooru tags for NoobAI-XL and Illustrious-XL, with B2's drama vocabulary.

Why (art bake-off v3, owner 2026-11-28): arm C (`drama.compile_noobai_tags`) took hand-written identity and scene tag lists, so
it could not be run on a real storyboard, and it was "off-text on most panels" because nothing stopped a people-free panel
from drawing people or an imagined inset from drawing a room. B2 fixed exactly those with rules driven by schema enums; this
module applies the same rules to tags and derives the identity and scene tags from the cast look facts (`CharacterBrief`) and
the panel's own composition text, so a real `Storyboard` compiles without a hand-built tag list.

The rules B2 obeys, restated for a tag model that has a negative prompt (Z-Image has none, so there a prohibition is weak):
no people on an empty-cast panel (`no humans` plus people tags in the negative), an isolated subject on a black void for an
imagined or referenced inset (no scene tags at all), eyes only for an eyes-only panel (nose, mouth and body in the negative),
age and gender spelled as tags. Nothing here names a novel, a person or a place; the novel's facts come only from the brief."""

from __future__ import annotations

import re
from dataclasses import dataclass

from echotales.pipeline.render.compiler import CharacterBrief, PanelBrief, model_profile
from echotales.pipeline.render.drama import (
    _GLOW,
    _TAG_ACCENT,
    _TAG_MOTION,
    _age_key,
    count_tags,
    drama_spec,
)
from echotales.pipeline.storyboard.schema import Layer, LetterKind, Panel, Purpose, Shape, Shot

#: Checkpoint key -> `compiler.PROFILES` key. Quality words and the base negative come from the profile, never from here.
CHECKPOINTS = {"noobai": "noobai-xl-1.1", "illustrious": "illustrious-xl-0.1"}

_PEOPLE_NEG = "1boy, 1girl, 2boys, multiple boys, solo focus, person, humanoid, silhouette, face, hands"
_EYES_NEG = "nose, mouth, lips, forehead, chin, hair, neck, body, full face, 2boys, 1girl, multiple views"
_ISOLATED_NEG = "background, scenery, landscape, mountain, sky, building, room, floor, crowd, 2boys, multiple boys, multiple views"

# --- shot vocabulary: the Shot enum -> camera tags, a peak taking the angled, foreshortened variant ---------------------------
_SHOT_PEAK = {
    Shot.EXTREME_WIDE: "from far away, extremely wide shot, from above, scenery",
    Shot.WIDE: "wide shot, full body, from below, dutch angle, foreshortening",
    Shot.MEDIUM: "cowboy shot, dutch angle, dynamic angle",
    Shot.MEDIUM_CLOSE: "upper body, from below, dutch angle",
    Shot.CLOSE: "portrait, close-up, face focus, from below, dutch angle",
    Shot.EXTREME_CLOSE: "extreme close-up, close-up, face focus, dutch angle",
    Shot.INSERT: "close-up, object focus, depth of field",
    Shot.OVERHEAD: "from above, bird's-eye view, high angle",
    Shot.LOW_ANGLE: "from below, low angle, full body, looking up, foreshortening, dynamic pose",
}
_SHOT_CALM = {
    Shot.EXTREME_WIDE: "from far away, extremely wide shot, scenery",
    Shot.WIDE: "wide shot, full body",
    Shot.MEDIUM: "cowboy shot",
    Shot.MEDIUM_CLOSE: "upper body",
    Shot.CLOSE: "portrait, close-up",
    Shot.EXTREME_CLOSE: "extreme close-up, close-up",
    Shot.INSERT: "close-up, object focus",
    Shot.OVERHEAD: "from above, high angle",
    Shot.LOW_ANGLE: "from below, low angle",
}
#: Shot tags for a panel with nobody in it: the people-bearing ones ("full body", "looking up", "face focus") drew people.
_SHOT_FREE = {
    Shot.EXTREME_WIDE: "from far away, extremely wide shot, scenery",
    Shot.WIDE: "wide shot, scenery, from below, dutch angle",
    Shot.OVERHEAD: "from above, bird's-eye view, scenery",
    Shot.LOW_ANGLE: "from below, low angle, scenery",
}
_EYES_ONLY = "extreme close-up, eye focus, eyes, close-up, macro, reflection"

_PEAK_LOOK = ("chiaroscuro, dramatic lighting, hard shadows, rim light, backlighting, high contrast, ink wash, sumi-e, ink splatter, "
              "dark, desaturated, limited palette")
_PEAK_LOOK_FREE = ("chiaroscuro, dramatic lighting, hard shadows, high contrast, ink wash, sumi-e, dark, desaturated, limited palette")
_CALM_LOOK = "muted colors, soft lighting, calm"
_SHAPE_TAGS = {
    Shape.DIAGONAL: "diagonal composition, dutch angle", Shape.BLEED: "dynamic pose, foreshortening",
    Shape.TALL: "vertical composition", Shape.WIDE: "wide composition", Shape.INSET: "vignetting, dark border",
}
_LINES = "speed lines, emphasis lines, motion blur"
#: A glow's colour as a tag, for an isolated subject (`drama._GLOW` names it as a colour sentence for Z-Image).
_GLOW_TAGS = {"cold pale-blue": "blue aura, glowing, blue theme", "warm gold": "golden aura, glowing, orange theme",
              "violet": "purple aura, glowing, purple theme", "pale ink-grey": "monochrome, greyscale, glowing",
              "blood-red": "red aura, glowing, red theme"}

# --- cast look facts -> tags --------------------------------------------------------------------------------------------------
_COLOURS = ("black", "white", "silver", "grey", "gray", "gold", "golden", "blonde", "blond", "brown", "red", "blue", "green", "teal",
            "purple", "pink", "orange", "yellow", "crimson", "violet", "navy", "maroon", "cyan")
_HAIR_STYLE = (
    (r"top-?knot", "topknot, hair bun"), (r"pony-?tail", "ponytail"), (r"braid", "braid"), (r"\bbun\b", "hair bun"),
    (r"loose|down|flowing", "hair down"), (r"tied|bound", "hair tied back"), (r"bald|shaved", "bald"),
)
_GARMENTS = (
    ("robe", "robe, chinese clothes, wide sleeves"), ("hanfu", "hanfu, chinese clothes"), ("garment", "chinese clothes"),
    ("coat", "coat"), ("dress", "dress"), ("uniform", "uniform"), ("armor", "armor"), ("armour", "armor"), ("cloak", "cloak"),
    ("suit", "suit"), ("kimono", "kimono"), ("shirt", "shirt"), ("jacket", "jacket"),
)
_CONDITION = (
    (r"blood", "blood on clothes, blood on face"), (r"wound|injur|bleed", "injury, blood"), (r"torn|ragged|tattered", "torn clothes"),
    (r"soak|wet|drench", "wet clothes, wet hair"), (r"pale", "pale skin"), (r"sweat", "sweat"), (r"tear", "tears"),
)
_EXPRESSION = (
    (r"mad|manic|insane", "crazy eyes, laughing, open mouth"), (r"laugh", "laughing, open mouth"), (r"mock|smirk|sneer", "smirk"),
    (r"snarl|hatred|angry|anger|rage|furious", "angry, clenched teeth, furrowed brow"), (r"shout|scream|roar", "shouting, open mouth"),
    (r"cold|composed|calm|expressionless|distant|silent", "expressionless"), (r"stun|startl|shock|astonish", "wide-eyed, shocked"),
    (r"solemn|grave|serious|intent", "serious"), (r"tired|weary", "tired"), (r"pensive|thought", "pensive"),
    (r"smile|amused", "smile"), (r"cry|tear|sorrow|grief", "crying"),
)
#: Composition text -> scene tags. A generic vocabulary of places, light and weather, never a novel's names.
_SCENE = (
    (r"\bcliff", "cliff, mountain"), (r"mountain", "mountain"), (r"village", "village, scenery"), (r"temple|shrine|altar", "temple, altar, indoors"),
    (r"hall", "hall, indoors"), (r"garret|attic|\broom\b", "indoors"), (r"window", "window"), (r"night", "night"),
    (r"dusk|sunset|twilight", "sunset, evening"), (r"red sky|blood-red sky", "red sky"), (r"rain", "rain"), (r"lantern", "lantern"),
    (r"candle", "candle, candlelight"), (r"tablet", "tablet"), (r"explo|detonat|shock-?wave|blast", "explosion, shockwave, debris, light rays"),
    (r"cloud", "clouds"), (r"wind|gust", "wind"), (r"fog|mist", "fog"), (r"snow", "snow"), (r"forest|tree", "forest"),
    (r"blood.*(pool|spread)|pool of blood", "blood pool"), (r"sword|blade", "sword"),
)
_POSE = (
    (r"kneel", "kneeling"), (r"prayer|prays|praying", "praying, own hands clasped"), (r"\bsit|seated", "sitting"),
    (r"look\w* at (his|her|their) own \w* ?\w*(palm|hand)", "looking at hands"), (r"look\w* (out|outside)", "looking outside"),
    (r"look\w* down", "looking down"), (r"hand raised|raises? (a|his|her) hand", "arm up"),
)


def _words(text: str) -> str:
    return re.sub(r"[-_]+", " ", text.lower())


def _first(pairs: tuple[tuple[str, str], ...], text: str) -> list[str]:
    return [tags for pat, tags in pairs if re.search(pat, text)]


def _hair_tags(text: str) -> list[str]:
    t = _words(text)
    out = [f"{c} hair" for c in _COLOURS if re.search(rf"\b{c}\b", t)][:2]
    out += [f"{ln} hair" for ln in ("long", "short", "medium", "very long") if re.search(rf"\b{ln}\b", t)][:1]
    out += _first(_HAIR_STYLE, t)
    return out or ([f"{t.strip()} hair"] if t.strip() and len(t.split()) <= 3 else [])


def _attire_tags(text: str) -> list[str]:
    t = _words(text)
    out: list[str] = []
    for key, tags in _GARMENTS:
        m = re.search(rf"((?:\w+ ){{0,2}})\b{key}s?\b", t)
        if m:
            mods = [w for w in m.group(1).split() if w in _COLOURS or w in ("dark", "pale", "deep", "torn", "plain", "flowing", "ceremonial")]
            if mods:
                out.append(f"{' '.join(mods)} {key}")
            out.append(tags)
            break
    return out or ([t.strip()] if t.strip() and len(t.split()) <= 4 else [])


def identity_tags(c: CharacterBrief) -> list[str]:
    """The cast look facts as tags, age and gender first. Mirrors `drama.drama_identity_sentence`: a band is drawn features, not a word."""
    female = c.gender == "female"
    key = _age_key(c)
    out: list[str] = ["1girl" if female else "1boy"]
    if not female:
        out.append("male focus")
    if key == "teen":
        out += ["teenager", "youthful", "slim", "smooth skin"]
    elif key == "middle-aged":
        out += ["middle-aged", "mature female" if female else "mature male", "wrinkles", "aged up"]
    elif key == "elder":
        out += ["old woman" if female else "old man", "wrinkled skin", "frail"]
        if not any("hair" in k for k in c.appearance):
            out.append("white hair")
    else:
        out += ["mature female" if female else "mature male"]
    app = {k.lower(): v for k, v in c.appearance.items()}
    if app.get("hair"):
        out += _hair_tags(app["hair"])
    if app.get("eyes"):
        eye = _words(app["eyes"]).replace(" eyes", "").strip()
        out.append(eye if eye.endswith("eyes") else f"{eye} eyes")
    feats = _words(app.get("features", ""))
    out += [t for pat, t in ((r"beard", "beard, facial hair"), (r"mustache|moustache", "mustache"), (r"scar", "scar")) if re.search(pat, feats)]
    out += _attire_tags(c.attire)
    out += _first(_CONDITION, _words(c.condition))
    out += _first(_EXPRESSION, _words(c.stated_expression))[:1]  # first match wins: "a cold mocking smile" is a smirk, not blank
    if c.pose and c.pose != "standing":
        out += _first(_POSE, _words(c.pose))
    return [t.strip() for tags in out for t in tags.split(",") if t.strip()]  # one tag per element: a table row may hold several


def scene_tags(brief: PanelBrief, panel: Panel) -> list[str]:
    """Place, weather, light and action tags from the panel's own text (composition, place, light, visual). Empty for an isolated subject."""
    text = _words(" ".join([brief.composition, brief.location, brief.lighting, brief.setting, panel.visual]))
    out = [t for pat, tags in _SCENE for t in ([tags] if re.search(pat, text) else [])]
    if brief.characters:
        out += _first(_POSE, _words(brief.composition))
    return out


@dataclass(frozen=True, slots=True)
class TagPrompt:
    positive: str
    negative: str
    sections: list[tuple[str, str]]
    checkpoint: str


def _dedupe(tags: str) -> str:
    seen: dict[str, None] = {}
    for t in (x.strip() for x in tags.split(",")):
        if t:
            seen.setdefault(t, None)
    return ", ".join(seen)


def compile_c2(panel: Panel, brief: PanelBrief, *, checkpoint: str = "noobai", text: str = "", trigger: str = "") -> TagPrompt:
    """Arm C2: tags for one panel, in priority order (quality, count, trigger, identity, shot, scene, drama).

    `trigger` is a character LoRA's trigger word, placed right after the count so it is read before the look it replaces.
    `checkpoint` picks the quality words and the base negative only (`CHECKPOINTS`); the drama vocabulary is the same for both."""
    profile = model_profile(CHECKPOINTS[checkpoint])
    spec = drama_spec(panel, text=text, brief=brief)
    free, isolated, peak = spec.people_free, spec.isolated, spec.peak
    eyes_only = free and panel.shot is Shot.EXTREME_CLOSE
    crowd = brief.crowd is not None
    n = len(brief.characters)
    neg = [profile.negative_base]
    if eyes_only:
        count = "solo"
    elif free:
        count = "no humans"
        neg.append(_PEOPLE_NEG)
    elif isolated:
        count = "solo"
        neg.append(_ISOLATED_NEG)
    else:
        count = count_tags(n, crowd=crowd, faceless=False)
    who = [t for c in brief.characters if not c.back_turned for t in identity_tags(c)] if not free else []
    if n and all(c.gender == "female" for c in brief.characters):
        count = count.replace("boys", "girls")
    if crowd or n > 1:
        who = [t for t in who if t not in ("1boy", "1girl", "male focus")]  # the count tag already says how many
    if crowd and not free:
        who.append("faceless" if panel.shot in (Shot.WIDE, Shot.EXTREME_WIDE, Shot.OVERHEAD) else "crowd")
    if eyes_only:
        shot = _EYES_ONLY
        neg.append(_EYES_NEG)
    elif free:
        shot = _SHOT_FREE.get(panel.shot, _SHOT_CALM[panel.shot])
    else:
        hero = peak and panel.purpose is Purpose.HERO
        shot = (_SHOT_PEAK[Shot.LOW_ANGLE] if hero else _SHOT_PEAK[panel.shot]) if peak else _SHOT_CALM[panel.shot]
    scene = [] if isolated or eyes_only else scene_tags(brief, panel)
    if eyes_only:
        scene = [t for t in scene_tags(brief, panel) if t in ("night", "rain", "lantern", "candlelight")]
    drama: list[str] = []
    if isolated:
        drama += ["simple background", "black background", "floating", _GLOW_TAGS[_GLOW[panel.layer]], "cowboy shot"]
        shot = ""
    elif peak:
        drama.append(_PEAK_LOOK_FREE if free else _PEAK_LOOK)
        if panel.shape in _SHAPE_TAGS and not (free and panel.shape is Shape.TALL) and not eyes_only:
            drama.append(_SHAPE_TAGS[panel.shape])
        if any(lt.kind in (LetterKind.SHOUT, LetterKind.SFX) for lt in panel.letters) or panel.purpose in (
                Purpose.EXTREME_CLOSE, Purpose.TRANSITION):
            drama.append(_LINES)
        drama.append(_TAG_ACCENT[panel.layer])
    else:
        drama += [_CALM_LOOK, _TAG_ACCENT[panel.layer]]
    if spec.motion and not (free and not peak):
        drama.append("debris, motion lines, light rays" if free else _TAG_MOTION)
    if free:
        drama = [t.replace(", blood", "") if t.endswith(", blood") else t for t in drama]  # a blast has no blood in it
    if panel.layer in (Layer.MEMORY, Layer.DREAM) and not isolated:
        drama.append("soft focus, bloom")
    sections = [("quality", profile.quality_tags), ("count", count), ("trigger", trigger), ("identity", ", ".join(who)),
                ("shot", shot), ("scene", ", ".join(scene)), ("drama", ", ".join(drama))]
    seen: set[str] = set()  # across sections too: "wind" and "dynamic pose" arrived from both the shot and the motion block
    deduped = []
    for k, v in sections:
        keep = [t for t in _dedupe(v).split(", ") if t and t not in seen]
        seen.update(keep)
        if keep:
            deduped.append((k, ", ".join(keep)))
    sections = deduped
    return TagPrompt(", ".join(v for _, v in sections), _dedupe(", ".join(neg)), sections, checkpoint)
