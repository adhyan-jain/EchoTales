"""Drama compiler: storyboard `Panel` fields -> Z-Image sentences (arm B) and NoobAI tags (arm C) that carry manhwa drama.

Why (owner, 2026-11-28, from contact sheets of RI ch1): NoobAI XL panels (v54) had inked chiaroscuro, wind-whipped cloth, low
angles, dark desaturated palettes with red accents -- and were often irrelevant (a woman in a dress at the cliff). Z-Image
Turbo panels (v57) were relevant but flat: even light, calm centred medium shots, neutral faces. Z-Image has no CFG, so a
mood only appears when it is said plainly, early and as a drawable thing ("hard black shadows across half the face"), not as
an adjective ("dramatic"). So the drama is a table from schema enums (`Purpose`, `Shot`, `Shape`, `Layer`) to sentences:
nothing here names a novel, a person or a place, and the novel's own facts still come only from the brief.

`STYLE_ANCHOR` (the genre style lead) stays the first section: the compiled prompt starts with it and the drama sentences
follow the framing, before the identity sentences, because what Z-Image reads first and fixedly is what holds."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from echotales.pipeline.render.compiler import (
    _ADULT_FACE,
    AppearanceInText,
    CharacterBrief,
    CompiledPrompt,
    PanelBrief,
    PromptSection,
    _compile_composed,
    _identity_head,
    body_is_young,
    identity_sentence,
    model_profile,
    trim_staging,
)
from echotales.pipeline.storyboard.schema import Layer, Panel, Purpose, Shape, Shot

#: Purposes that are a peak of the scene (grammar rule 5/7: shout, face, reaction, insert, hero). Everything else is calm.
PEAK_PURPOSES = frozenset({
    Purpose.COLD_OPEN, Purpose.EXTREME_CLOSE, Purpose.HERO, Purpose.REACTION, Purpose.CROWD_INDIVIDUAL, Purpose.TRANSITION,
})
#: Purposes that stay calm even on a tall or bleed shape: a card or an establishing wide is not a peak.
CALM_PURPOSES = frozenset({
    Purpose.TITLE_CARD, Purpose.TIME_PLACE_CARD, Purpose.NAME_CARD, Purpose.ESTABLISHING, Purpose.DIALOGUE,
})

_MOTION = re.compile(
    r"\b(wind|whip\w*|gust\w*|storm\w*|rain\w*|fall\w*|rush\w*|charg\w*|flutter\w*|blow\w*|swirl\w*|flee\w*|"
    r"explo\w*|detonat\w*|burst\w*|shout\w*|scream\w*|roar\w*|laugh\w*|surg\w*)\b", re.I)

#: Camera: the angle sentence per shot enum. A peak overrides the neutral ones with a low or tilted view, because 12 of 12 v57
#: panels were eye-level and centred (contact sheet 2026-11-28).
_SHOT_PEAK = {
    Shot.EXTREME_WIDE: "A vast high wide view, the figures tiny against the land.",
    Shot.WIDE: "A dramatic low wide shot seen from the ground, the figures towering against the sky.",
    Shot.MEDIUM: "A tilted dutch-angle medium shot, the horizon slanting.",
    Shot.MEDIUM_CLOSE: "A dramatic low-angle shot looking up at the face, slightly tilted.",
    Shot.CLOSE: "A tight dramatic close-up on the face from a slightly low angle, the frame tilted.",
    Shot.EXTREME_CLOSE: "An extreme close-up cropped tight on the eyes and brow, filling the whole frame.",
    Shot.INSERT: "A tight cropped insert of the object, hard light, shallow depth of field.",
    Shot.OVERHEAD: "A steep overhead bird's-eye view looking straight down, figures small and radiating outward.",
    Shot.LOW_ANGLE: "An extreme low-angle full-body shot from the ground looking up, the figure monumental against the sky.",
}
_SHOT_CALM = {
    Shot.EXTREME_WIDE: "A wide establishing view with deep atmospheric depth.",
    Shot.WIDE: "A wide shot with layered depth.",
    Shot.MEDIUM: "A medium shot.",
    Shot.MEDIUM_CLOSE: "A medium close-up.",
    Shot.CLOSE: "A close-up portrait.",
    Shot.EXTREME_CLOSE: "An extreme close-up, cropped tight.",
    Shot.INSERT: "A close insert of the object.",
    Shot.OVERHEAD: "A high overhead view.",
    Shot.LOW_ANGLE: "A low-angle shot looking up.",
}
#: The neutral framing the baseline arm A gets, so A differs from B only by the drama.
_SHOT_NEUTRAL = {
    Shot.EXTREME_WIDE: "A wide establishing shot.", Shot.WIDE: "A wide shot.", Shot.MEDIUM: "A medium shot.",
    Shot.MEDIUM_CLOSE: "A medium shot.", Shot.CLOSE: "A close-up portrait.", Shot.EXTREME_CLOSE: "A close-up portrait.",
    Shot.INSERT: "A close-up of the object.", Shot.OVERHEAD: "A view from above.", Shot.LOW_ANGLE: "A shot from a low angle.",
}

_SHAPE_WORDS = {
    Shape.TALL: "tall vertical composition, the subject filling the frame from head to feet",
    Shape.WIDE: "wide panoramic composition with the subject small against a large space",
    Shape.DIAGONAL: "a strongly diagonal composition, figures and horizon on a slant",
    Shape.BLEED: "a full-bleed composition with the subject breaking out of the frame",
    Shape.INSET: "a small isolated vignette with a soft dark edge",
}

#: Light per intensity. Peaks get hard directional light; calm beats keep the staged or graded light (`lightgrade`), so a calm
#: panel is deliberately NOT given chiaroscuro: contrast only reads as drama against calm.
_LIGHT_PEAK = ("Hard chiaroscuro: a single strong rim light, hard-edged black shadows across half the face and body, "
               "deep inky blacks and high contrast.")
_LIGHT_PEAK_BY_LAYER = {
    Layer.MEMORY: "A glowing backlit halo, soft bloom and long hard shadows, high contrast.",
    Layer.IMAGINED: "A cold glow around the figure against deep darkness, hard rim light, high contrast.",
    Layer.LORE: "High-contrast ink silhouette lighting, deep black shapes against a pale ground.",
}

#: One saturated accent light per layer inside an otherwise dark, desaturated palette. v1 said "a single X accent" and the 13-panel
#: sheets came out muted next to the RI manhua slices, whose peaks carry one intensely saturated colour (red sky, teal glow);
#: the colour is now a light that rakes across the subject, said as a light because Z-Image paints a lit thing and ignores a tint.
_ACCENT = {
    Layer.PRESENT: "cold teal-green",
    Layer.PAST: "blood-red",
    Layer.MEMORY: "warm gold",
    Layer.LORE: "faded vermilion",
    Layer.IMAGINED: "cold pale-blue",
    Layer.DREAM: "violet",
}
#: The void an isolated (IMAGINED / REFERENCED_INSET) subject floats in, in the layer's own palette.
_VOID = {
    Layer.IMAGINED: "an abstract void filled with a soft cold pale-blue glow",
    Layer.MEMORY: "a hazy abstract field of warm gold glow",
    Layer.DREAM: "a drifting abstract violet mist",
    Layer.LORE: "a pale abstract ink-grey void",
    Layer.PAST: "an abstract blood-red haze",
    Layer.PRESENT: "an abstract dark void with a soft glow",
}
_TEXTURE_LAYERS = frozenset({Layer.PAST, Layer.LORE, Layer.MEMORY, Layer.DREAM})


@dataclass(frozen=True, slots=True)
class DramaSpec:
    peak: bool
    motion: bool
    #: Nobody may be drawn (empty cast, no crowd): the light, the blast, the place or one pair of eyes only.
    people_free: bool
    #: A person who is talked about or pictured, not present: drawn alone on a glow, with no place and no bystanders.
    isolated: bool
    shot_sentence: str
    light_sentence: str
    drama_sentences: tuple[str, ...]


def is_peak(panel: Panel) -> bool:
    if panel.purpose in CALM_PURPOSES:
        return False
    if panel.purpose in PEAK_PURPOSES:
        return True
    from echotales.pipeline.storyboard.schema import LetterKind

    return panel.shape in (Shape.BLEED, Shape.TALL) or any(lt.kind in (LetterKind.SHOUT, LetterKind.SFX) for lt in panel.letters)


def has_motion(panel: Panel, extra: str = "") -> bool:
    """Motion is read from the panel's own drawn text (and any text the caller adds), not from the purpose: a calm beat in
    rain still has wind in the cloth, a shout in a still room does not."""
    return bool(_MOTION.search(f"{panel.visual} {extra}"))


def is_isolated(panel: Panel) -> bool:
    """A subject who is talked about or imagined, not present (schema: layer IMAGINED, purpose REFERENCED_INSET). v1 compiled these
    like any other beat and the referenced man came out standing among people in the hall (13-panel bake-off, p10)."""
    return panel.layer is Layer.IMAGINED or panel.purpose is Purpose.REFERENCED_INSET


def is_people_free(panel: Panel, brief: PanelBrief | None) -> bool:
    """No identity to draw: an empty cast with no crowd. v1 still added people there: the detonation (p05) gained a man in black
    from "across half the face and body" in the peak light sentence, and the eyes-only panel (p12) gained two figures above the eyes.
    With no brief (the tag arm) only the panel's own cast is known."""
    if panel.cast:
        return False
    return brief is None or (not brief.characters and brief.crowd is None)


def drama_spec(panel: Panel, *, text: str = "", brief: PanelBrief | None = None) -> DramaSpec:
    peak = is_peak(panel)
    motion = has_motion(panel, text)
    isolated = is_isolated(panel)
    free = is_people_free(panel, brief) and not isolated
    shot = (_SHOT_PEAK if peak else _SHOT_CALM)[panel.shot]
    if peak and panel.purpose is Purpose.HERO:
        shot = _SHOT_PEAK[Shot.LOW_ANGLE]
    if free and peak and panel.shot in _SHOT_PEAK_FREE:
        shot = _SHOT_PEAK_FREE[panel.shot]
    if free and panel.shot is Shot.EXTREME_CLOSE:
        # "cropped tight on the eyes and brow" invited a brow, a forehead and then a head with figures above it (p12).
        shot = "An extreme macro close-up of one single pair of eyes, filling the whole frame edge to edge."
    if free:
        # The people-bearing light says "across half the face and body": on a blast it drew a man (p05).
        light = ("Hard chiaroscuro: one strong light source, hard-edged black shadows, deep inky blacks and high contrast."
                 if peak else "")
    elif isolated:
        light = _LIGHT_PEAK_BY_LAYER.get(panel.layer, _LIGHT_PEAK_BY_LAYER[Layer.IMAGINED])
    else:
        light = _LIGHT_PEAK_BY_LAYER.get(panel.layer, _LIGHT_PEAK) if peak else ""
    bits: list[str] = []
    if free:
        if panel.shot is Shot.EXTREME_CLOSE:
            bits.append("The irises hold small reflected lights and streaks of rain, and nothing else is in the frame: no forehead, "
                        "no nose, no mouth, no second person, no figures.")
        else:
            bits.append("The frame holds no people, no bodies, no faces and no silhouettes: it is made only of the light, the matter "
                        "and the place itself.")
    if peak and not isolated:
        bits.append("Ink-wash brush texture at the edges and fine blood-like ink splatter." if panel.layer in _TEXTURE_LAYERS
                    else "Rough ink-brush texture at the edges of the frame.")
    if motion and not free:
        bits.append("Wind whips the hair and the cloth sideways in long streaming lines.")
    elif motion:
        bits.append("Debris, rain and light streak across the frame in long diagonal lines.")
    if not free and not isolated and (
            panel.shot in (Shot.WIDE, Shot.EXTREME_WIDE, Shot.OVERHEAD, Shot.LOW_ANGLE) or panel.purpose is Purpose.CROWD_INDIVIDUAL):
        bits.append("Dark out-of-focus silhouettes in the foreground frame the view.")  # silhouettes are people: never on a people-free panel
    if peak and not isolated:
        # The RI manhua slices carry extreme perspective and diagonal energy; v1's low angle and tilt alone stayed tame (round 1 sheets).
        bits.append("Extreme perspective, strong foreshortening, a diagonal composition and a dynamic pose." if not free
                    else "Extreme perspective, the force of it radiating diagonally toward the viewer.")
    # A wide or tall composition sentence contradicted an eyes-only extreme close-up ("the subject small against a large space").
    close = panel.shot in (Shot.CLOSE, Shot.EXTREME_CLOSE, Shot.INSERT, Shot.MEDIUM_CLOSE)
    if not isolated and panel.shape in _SHAPE_WORDS and (peak or panel.shape in (Shape.WIDE, Shape.INSET)) and not (
            close and panel.shape in (Shape.WIDE, Shape.TALL, Shape.DIAGONAL)) and not (
            free):  # "the subject" of a shape sentence is a person to the model
        bits.append(f"{_SHAPE_WORDS[panel.shape].capitalize()}.")
    if isolated:
        bits.append(f"A dark palette with one intensely saturated {_ACCENT[panel.layer]} glow around the subject.")
    elif peak:
        bits.append(f"A dark desaturated palette with one intensely saturated {_ACCENT[panel.layer]} accent light raking across the scene.")
    else:
        bits.append("A muted colour palette and a calm, composed frame.")
    return DramaSpec(peak, motion, free, isolated, shot, light, tuple(bits))


# ---------------------------------------------------------------------------
# identity: age and gender lead the character clause
# ---------------------------------------------------------------------------

#: Visible age markers per age band. v1 left "middle-aged" and "a 15-year-old" as one word in the head of the sentence, and the
#: clan head came out about 30 and young Fang Yuan an adult (bake-off p07, p13): a word is not a face, so the band becomes drawn
#: features, placed straight after the head, before hair and clothes.
_AGE_MARKERS = {
    "middle-aged": "greying temples, a lined face with creases at the eyes and mouth, and a mature heavy build",
    "elder": "a deeply lined weathered face and a frail stooped build",
    "teen": "a youthful soft round face with no lines or stubble, a slight narrow frame and a noticeably smaller stature",
}
#: Camera sentences for a panel with nobody in it: the people-bearing peak sentences ("the figures towering against the sky") drew
#: figures into the detonation panel (p05).
_SHOT_PEAK_FREE = {
    Shot.EXTREME_WIDE: "A vast high wide view of the land.",
    Shot.WIDE: "A dramatic low wide shot seen from the ground, looking up at the sky.",
    Shot.OVERHEAD: "A steep overhead bird's-eye view looking straight down.",
    Shot.LOW_ANGLE: "An extreme low-angle view from the ground looking up at the sky.",
}


def _age_key(c: CharacterBrief) -> str:
    band = (c.age_band or "").lower()
    if body_is_young(band, c.age_years):
        return "teen"
    return {"elderly": "elder", "ageless-ancient": "elder"}.get(band, band)


def drama_identity_sentence(c: CharacterBrief) -> str:
    """`identity_sentence` with the age made visible and the gender spelled out.

    The sentence still starts with the head ("X is a middle-aged man"), whose noun carries the gender from the cast's look or
    dossier; the age markers follow it. The adult-face clause is dropped for bands with markers because "an adult face with a
    defined jaw" told the model to draw a thirty-year-old. A beard is written for an elder only when the cast's own facts
    mention one."""
    base = identity_sentence(c, AppearanceInText.SHORT)
    key = _age_key(c)
    marker = _AGE_MARKERS.get(key)
    if not marker or c.is_creature or c.gender == "creature" or c.same_face_as:
        return base
    if key == "elder" and not any("hair" in k for k in c.appearance):
        marker = "white hair, " + marker  # a beard only where the cast's own facts give one (they are folded in below), never invented
    head, _ = _identity_head(c)
    if not base.startswith(head):
        return base
    tail = base[len(head):].replace(_ADULT_FACE, "")
    if tail.startswith(" with "):
        tail = ", " + tail[len(" with "):]  # fold the look's own facts into the same "with" list
    return f"{head} with {marker}{tail}"


def compile_neutral(brief: PanelBrief, panel: Panel) -> CompiledPrompt:
    """Arm A: the production compiler, given the panel's shot as a plain neutral sentence and nothing else."""
    b = copy.copy(brief)
    b.framing = _SHOT_NEUTRAL[panel.shot]
    return _compile_composed(b, model_profile("z-image-turbo"), AppearanceInText.SHORT)


def _isolated_brief(b: PanelBrief, panel: Panel) -> PanelBrief:
    """An isolated subject drops the place, the other people and the room's staging: a vision is one figure on a glow. v1 kept the
    hall, so Bai Ning Bing (an imagined, referenced man) was drawn standing among people in it (p10)."""
    b.location = b.setting = b.location_description = ""
    b.crowd = None
    b.staging = trim_staging(b.staging.strip(), "eyes", b.shot) if b.staging else ""  # keeps the Light line only
    names = " and ".join(c.name for c in b.characters) or "The subject"
    expr = next((c.stated_expression for c in b.characters if c.stated_expression), "")
    mood = f", {expr}," if expr else ""
    b.composition = (f"{names}{mood} stands alone as an isolated figure floating in {_VOID[panel.layer]}, pictured as a vision. "
                     f"No room, no walls, no furniture, no ground and no other people anywhere in the frame.")
    b.empty_hands = False
    return b


def compile_drama(brief: PanelBrief, panel: Panel, *, text: str = "") -> CompiledPrompt:
    """Arm B / B2: the same brief, with the framing, light and a drama block written from the panel's schema fields.

    The style lead stays section 0; framing, grade and drama sit right after it and before identity, as the compiler already
    orders framing and grade (Z-Image has no CFG: first and plain wins). B2 changes (bake-off round 1 failures): age markers and
    explicit gender in every character clause, isolated subjects on a glow with no place, no people on an empty cast."""
    spec = drama_spec(panel, text=text, brief=brief)
    b = copy.copy(brief)
    b.framing = spec.shot_sentence
    if spec.light_sentence:
        b.grade = spec.light_sentence  # a peak's hard light replaces a flat graded light; a calm beat keeps its own `grade`
    if spec.isolated:
        b = _isolated_brief(b, panel)
    comp = _compile_composed(b, model_profile("z-image-turbo"), AppearanceInText.SHORT)
    drama = PromptSection("drama", " ".join(spec.drama_sentences))
    sections = list(comp.sections)
    by_name = {f"character:{c.name}": c for c in b.characters if not c.back_turned}
    for i, sec in enumerate(sections):
        if sec.label in by_name:
            sections[i] = PromptSection(sec.label, drama_identity_sentence(by_name[sec.label]))
    at = next((i for i, s in enumerate(sections) if s.label == "grade"), None)
    at = (at if at is not None else next((i for i, s in enumerate(sections) if s.label == "framing"), 0)) + 1
    sections.insert(at, drama)
    comp.sections = sections
    comp.positive = " ".join(s.text for s in sections)
    return comp


# ---------------------------------------------------------------------------
# arm C: NoobAI tags
# ---------------------------------------------------------------------------

_TAG_SHOT = {
    Shot.EXTREME_WIDE: "from far away, extremely wide shot, scenery", Shot.WIDE: "wide shot, full body",
    Shot.MEDIUM: "cowboy shot", Shot.MEDIUM_CLOSE: "upper body", Shot.CLOSE: "portrait, close-up, face focus",
    Shot.EXTREME_CLOSE: "extreme close-up, eye focus, portrait", Shot.INSERT: "close-up, object focus, no humans",
    Shot.OVERHEAD: "from above, bird's-eye view", Shot.LOW_ANGLE: "from below, full body, looking up",
}
_TAG_PEAK = ("dutch angle, dramatic lighting, chiaroscuro, hard shadows, rim light, high contrast, ink wash, sumi-e, "
             "ink splatter, dark, desaturated, limited palette")
_TAG_MOTION = "wind, windswept hair, flowing clothes, motion lines, dynamic pose"
_TAG_ACCENT = {
    Layer.PRESENT: "teal accent", Layer.PAST: "red accent, blood", Layer.MEMORY: "gold accent, glowing",
    Layer.LORE: "monochrome, greyscale, red accent", Layer.IMAGINED: "glowing, pale blue accent, silhouette",
    Layer.DREAM: "purple accent",
}


def count_tags(n_people: int, *, crowd: bool, faceless: bool, eyes_only: bool = False) -> str:
    """"no humans" on an eyes-only panel drew a landscape (the eyes are a person's, just an unnamed one), so it is "solo"."""
    if eyes_only:
        return "solo"
    if faceless:
        return "no humans"
    if crowd:
        # "from behind" only when no lead is placed among them: it contradicted an overhead view of the lead in the middle.
        return "6+boys, crowd, from behind" if n_people == 0 else "6+boys, crowd"
    return {0: "no humans", 1: "solo", 2: "2boys", 3: "3boys"}.get(n_people, "multiple boys")


def compile_noobai_tags(panel: Panel, *, identity_tags: list[str], scene_tags: list[str], crowd: bool = False,
                        gender_tag: str = "boy", text: str = "") -> tuple[str, str, list[tuple[str, str]]]:
    """Arm C: danbooru-style tags from the same `Panel`, drama tags included. Returns (positive, negative, sections).

    NoobAI wants score tags first and tags not sentences; its 77-token chunks are handled by the worker's compel chunking, so
    the order here is the priority order (subject, shot, scene, drama). Comparison only: NoobAI is never the default
    (licence, D58)."""
    profile = model_profile("noobai-xl-1.1")
    spec = drama_spec(panel, text=text)
    faceless = panel.shot is Shot.INSERT and not panel.cast
    n = len(panel.cast)
    eyes_only = panel.shot is Shot.EXTREME_CLOSE and not panel.cast
    count = count_tags(n, crowd=crowd, faceless=faceless or (n == 0 and not crowd and panel.shot not in (Shot.EXTREME_CLOSE,)
                                                              and panel.purpose is not Purpose.EXTREME_CLOSE), eyes_only=eyes_only)
    count = count.replace("boy", gender_tag) if gender_tag != "boy" else count
    sections: list[tuple[str, str]] = [
        ("quality", profile.quality_tags),
        ("count", count),
        ("identity", ", ".join(identity_tags)),
        ("shot", _TAG_SHOT[panel.shot]),
        ("scene", ", ".join(scene_tags)),
    ]
    drama = [_TAG_ACCENT[panel.layer]]
    if spec.peak:
        drama.insert(0, _TAG_PEAK)
    if spec.motion:
        drama.append(_TAG_MOTION)
    sections.append(("drama", ", ".join(drama)))
    sections = [(k, v) for k, v in sections if v]
    return ", ".join(v for _, v in sections), profile.negative_base, sections
