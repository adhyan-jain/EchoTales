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
MANGA_STYLE = (
    "manga panel, black and white, ink lines, screentone shading, "
    "dynamic composition, no color, professional manga art"
)

#: Universal negative prompt. Speech bubbles are excluded because dialogue
#: is carried by the audio track, not drawn into the frame.
NEGATIVE_PROMPT = (
    "color, colored, photorealistic, western comic, 3d render, watermark, "
    "text, speech bubble, blurry, deformed hands, extra limbs, lowres"
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


def build_image_prompt(
    panel_cast: PanelCast,
    *,
    beat: str = "",
    character_appearances: dict[str, str] | None = None,
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

    if beat:
        parts.append(summarise_beat(beat))
    if panel_cast.environment:
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
