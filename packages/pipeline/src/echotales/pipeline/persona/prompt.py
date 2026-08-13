"""`PanelCast` -> one text-to-image prompt string.

`get_panel_cast` (`runner.py`) already resolved *what* is in frame and what
each element should look like; this module only has to say it in the order
a diffusion model reads best -- style and setting first (they set the frame
the rest is composited into), foreground subjects next, background last,
since a diffusion prompt weights earlier tokens more heavily than later
ones.

**Manga style is part of the contract, not a decoration.** The target output
is inked black-and-white panels, and a base photorealistic checkpoint will
produce photorealism no matter how the prompt is phrased -- the prompt says
what it wants, and `render/panels.py::MangaDiffusersEngine` is responsible
for being pointed at a checkpoint that can honour it.
"""

from __future__ import annotations

from echotales.pipeline.persona.runner import PanelCast

#: The style contract, appended to every panel prompt. Matches
#: `persona/reference_gen.py::REFERENCE_STYLE` deliberately: a panel that
#: does not share a style vocabulary with the reference sheet conditioning
#: it will fight that conditioning.
#: Shared by every shot type. What varies between them is framing, not
#: rendering.
_MANGA_BASE = (
    "manga panel, black and white, ink lines, screentone shading, "
    "no color, professional manga art"
)

#: **Three framings, chosen per block -- not one style applied to all 89.**
#:
#: Real manga alternates: a wide establishing shot when the scene changes, a
#: full figure-in-environment shot for action, and a tight close-up over a
#: toned background when someone is talking or thinking. The first pass here
#: used one framing for every block, which is why an early version produced
#: 89 near-identical compositions, and a later version produced 89
#: environment shots -- including for blocks where a character is simply
#: speaking, where a landscape is the wrong picture and an expensive one.
#:
#: The close-up variant is deliberately the "floating bust over an ink wash"
#: look that an earlier pass produced *by accident* across the whole
#: chapter. It was never a bad image; it was the right image for the wrong
#: blocks.
STYLE_ESTABLISHING = (
    f"{_MANGA_BASE}, wide establishing shot, detailed background, "
    "sweeping landscape, strong depth, small distant figures"
)

STYLE_SCENE = (
    f"{_MANGA_BASE}, dynamic composition, characters in a detailed "
    "environment, full scene, medium shot, depth"
)

STYLE_CLOSEUP = (
    f"{_MANGA_BASE}, close-up on the character's face, intense expression, "
    "dramatic lighting, speed lines, abstract toned background, shallow depth"
)

#: Default when a caller does not pick -- the middle framing, which is the
#: one that is never badly wrong.
MANGA_STYLE = STYLE_SCENE

_NEGATIVE_BASE = (
    "color, colored, photorealistic, western comic, 3d render, watermark, "
    "text, speech bubble, blurry, deformed hands, extra limbs, lowres"
)

#: Negative prompt per framing. A close-up *wants* the plain toned
#: background that a scene shot must reject, so one shared negative cannot
#: serve both -- that conflict is why the close-up look could not coexist
#: with environments until framing became explicit.
NEGATIVE_BY_STYLE: dict[str, str] = {
    STYLE_ESTABLISHING: (
        f"{_NEGATIVE_BASE}, plain background, empty background, portrait, "
        "close-up face, bust shot"
    ),
    STYLE_SCENE: (
        f"{_NEGATIVE_BASE}, plain background, simple background, "
        "white background, empty background, portrait, bust shot"
    ),
    STYLE_CLOSEUP: f"{_NEGATIVE_BASE}, full body, wide shot, crowd, tiny face",
}


def negative_for(style: str) -> str:
    """The negative prompt matching a framing."""
    return NEGATIVE_BY_STYLE.get(style, NEGATIVE_PROMPT)


def shot_style(span_types: list[str], *, scene_change: bool = False) -> str:
    """Pick a framing from what the block actually contains.

    Establishing shots are reserved for scene changes -- used on every
    description block they would make a chapter feel like a travelogue.
    Dialogue and inner monologue get the close-up, which is both the right
    manga grammar and much the cheaper picture: a landscape rendered behind
    a line of speech is wasted work.
    """
    kinds = set(span_types)
    if scene_change and "NARRATION_DESCRIPTION" in kinds:
        return STYLE_ESTABLISHING
    if kinds & {"DIALOGUE", "INNER_MONOLOGUE"}:
        return STYLE_CLOSEUP
    if "NARRATION_DESCRIPTION" in kinds and "NARRATION_ACTION" not in kinds:
        return STYLE_ESTABLISHING
    return STYLE_SCENE

#: Universal negative prompt. Speech bubbles are excluded because dialogue
#: is carried by the audio track, not drawn into the frame; the background
#: terms are what stop a panel collapsing back into a portrait.
NEGATIVE_PROMPT = (
    "color, colored, photorealistic, western comic, 3d render, watermark, "
    "text, speech bubble, blurry, deformed hands, extra limbs, lowres, "
    "plain background, simple background, white background, empty background, "
    "portrait, bust shot, close-up face"
)

#: Beat text is a *composition* cue, not a caption -- past this length it
#: stops steering the image and starts diluting the rest of the prompt.
_MAX_BEAT_CHARS = 220


def summarise_beat(text: str, *, limit: int = _MAX_BEAT_CHARS) -> str:
    """Condense a block's narration into a single composition cue.

    Truncated on a sentence boundary where possible: half a sentence reads
    as noise to a diffusion model, and the first sentence of an action block
    is almost always the one describing what is happening.
    """
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    for stop in (". ", "! ", "? "):
        idx = cut.rfind(stop)
        if idx > limit // 3:
            return cut[: idx + 1].strip()
    return cut.rsplit(" ", 1)[0].strip()


def cast_tags(genders: list[str]) -> str:
    """Danbooru headcount tags for the figures in frame.

    Anime/manga checkpoints weight `1boy`/`2boys`/`1girl` far more heavily
    than any English phrasing, and without them they fall back to their
    training prior, which is overwhelmingly female. Measured on RI ch1
    block 2 -- a confrontation between two men -- a prompt carrying only
    their names produced a girl holding cherry blossoms.
    """
    males = sum(1 for g in genders if g == "male")
    females = sum(1 for g in genders if g == "female")

    parts: list[str] = []
    if males == 1:
        parts.append("1boy")
    elif males > 1:
        parts.append(f"{min(males, 6)}boys")
    if females == 1:
        parts.append("1girl")
    elif females > 1:
        parts.append(f"{min(females, 6)}girls")
    return ", ".join(parts)


def build_image_prompt(
    panel_cast: PanelCast,
    *,
    beat: str = "",
    character_appearances: dict[str, str] | None = None,
    character_genders: list[str] | None = None,
    world: str = "",
    locale: str = "",
    style: str = MANGA_STYLE,
) -> str:
    """Compose one prompt string from a resolved `PanelCast`.

    `beat` is the block's own narration, summarised -- it is what makes two
    panels with the same cast different images. `character_appearances` maps
    a character's label to their stored appearance clause
    (`persona/reference_gen.py::build_reference_prompt` builds the same
    clause for the reference sheet), so a character's look survives into
    panels even where reference conditioning is unavailable.

    Returns a style/environment-only prompt (still a valid establishing-shot
    prompt) when nobody is in frame -- `get_panel_cast` returns exactly that
    shape for a block outside every tracked scene.
    """
    appearances = character_appearances or {}
    parts: list[str] = []

    # Headcount first: it is the single strongest steer on this class of
    # checkpoint, and getting it wrong turns a confrontation between two men
    # into a girl with cherry blossoms.
    if tags := cast_tags(character_genders or []):
        parts.append(tags)

    if beat:
        parts.append(summarise_beat(beat))

    # The specific place first, the world's general vocabulary behind it:
    # a diffusion model draws "a walled stone courtyard" and draws nothing
    # recognisable from "ancient Chinese cultivation world".
    if locale:
        parts.append(locale)

    # The world before the drawing style. `panel_cast.environment` is
    # whatever `resolve_attire` produced, which for most panels is the
    # novel's house *style* rather than a place -- so the scenery
    # vocabulary is what actually puts a world behind the characters.
    if world:
        parts.append(world)
    if panel_cast.environment and panel_cast.environment != world:
        parts.append(panel_cast.environment)

    for character in panel_cast.foreground_characters:
        described = appearances.get(character.self_label, "")
        if described:
            parts.append(f"{character.self_label}: {described}")
        elif character.attire and character.attire != panel_cast.environment:
            parts.append(f"{character.self_label} wearing {character.attire}")
        else:
            # `resolve_attire`'s last tier is the *novel's house style*, not
            # a garment, so it comes back identical to the environment
            # clause -- emitting it here produced "Fang Yuan wearing xianxia
            # web-novel illustration" on real RI ch1 output, and repeated
            # the same style string once per character on top of that. Name
            # the character and let the style clause do its job once.
            parts.append(character.self_label)

    for mob in panel_cast.background_mobs:
        descriptor = f"background: {mob.description}"
        if mob.attire:
            descriptor += f" ({mob.attire})"
        parts.append(descriptor)

    parts.append(style)
    return ", ".join(p for p in parts if p)
