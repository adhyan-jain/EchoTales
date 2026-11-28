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
    AppearanceInText,
    CompiledPrompt,
    PanelBrief,
    PromptSection,
    _compile_composed,
    model_profile,
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

#: One accent colour per layer inside an otherwise desaturated, dark palette (the NoobAI v54 look: dark, with red accents).
_ACCENT = {
    Layer.PRESENT: "a single cold teal-green accent",
    Layer.PAST: "a single blood-red accent",
    Layer.MEMORY: "a single warm gold accent",
    Layer.LORE: "a single faded vermilion accent on grey ink",
    Layer.IMAGINED: "a single cold pale-blue glow",
    Layer.DREAM: "a single violet accent",
}
_TEXTURE_LAYERS = frozenset({Layer.PAST, Layer.LORE, Layer.MEMORY, Layer.DREAM})


@dataclass(frozen=True, slots=True)
class DramaSpec:
    peak: bool
    motion: bool
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


def drama_spec(panel: Panel, *, text: str = "") -> DramaSpec:
    peak = is_peak(panel)
    motion = has_motion(panel, text)
    shot = (_SHOT_PEAK if peak else _SHOT_CALM)[panel.shot]
    if peak and panel.purpose is Purpose.HERO:
        shot = _SHOT_PEAK[Shot.LOW_ANGLE]
    light = (_LIGHT_PEAK_BY_LAYER.get(panel.layer, _LIGHT_PEAK) if peak else "")
    bits: list[str] = []
    if peak:
        bits.append("Ink-wash brush texture at the edges and fine blood-like ink splatter." if panel.layer in _TEXTURE_LAYERS
                    else "Rough ink-brush texture at the edges of the frame.")
    if motion:
        bits.append("Wind whips the hair and the cloth sideways in long streaming lines.")
    if panel.shot in (Shot.WIDE, Shot.EXTREME_WIDE, Shot.OVERHEAD, Shot.LOW_ANGLE) or panel.purpose is Purpose.CROWD_INDIVIDUAL:
        bits.append("Dark out-of-focus silhouettes in the foreground frame the view.")
    if panel.shape in _SHAPE_WORDS and (peak or panel.shape in (Shape.WIDE, Shape.INSET)):
        bits.append(f"{_SHAPE_WORDS[panel.shape].capitalize()}.")
    if peak:
        bits.append(f"A dark desaturated palette with {_ACCENT[panel.layer]}.")
    else:
        bits.append("Muted colour with calm even light.")
    return DramaSpec(peak, motion, shot, light, tuple(bits))


def compile_neutral(brief: PanelBrief, panel: Panel) -> CompiledPrompt:
    """Arm A: the production compiler, given the panel's shot as a plain neutral sentence and nothing else."""
    b = copy.copy(brief)
    b.framing = _SHOT_NEUTRAL[panel.shot]
    return _compile_composed(b, model_profile("z-image-turbo"), AppearanceInText.SHORT)


def compile_drama(brief: PanelBrief, panel: Panel, *, text: str = "") -> CompiledPrompt:
    """Arm B: the same brief, with the framing, light and a drama block written from the panel's schema fields.

    The style lead stays section 0; framing, grade and drama sit right after it and before identity, as the compiler already
    orders framing and grade (Z-Image has no CFG: first and plain wins)."""
    spec = drama_spec(panel, text=text)
    b = copy.copy(brief)
    b.framing = spec.shot_sentence
    if spec.light_sentence:
        b.grade = spec.light_sentence  # a peak's hard light replaces a flat graded light; a calm beat keeps its own `grade`
    comp = _compile_composed(b, model_profile("z-image-turbo"), AppearanceInText.SHORT)
    drama = PromptSection("drama", " ".join(spec.drama_sentences))
    sections = list(comp.sections)
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


def count_tags(n_people: int, *, crowd: bool, faceless: bool) -> str:
    if faceless:
        return "no humans"
    if crowd:
        return "multiple others, crowd, 6+boys, from behind" if n_people <= 1 else "6+boys, crowd"
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
    count = count_tags(n, crowd=crowd, faceless=faceless)
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
