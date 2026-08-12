"""`PanelCast` -> one text-to-image prompt string (xyz.md Step 4).

`get_panel_cast` (`runner.py`) already resolved *what* is in frame and what
each element should look like; this module only has to say it in the order
an SDXL-class model reads best -- style and setting first (they set the
frame the rest is composited into), foreground subjects next in scene
importance, background last, since a diffusion prompt weights earlier
tokens more heavily than later ones.
"""

from __future__ import annotations

from echotales.pipeline.persona.runner import PanelCast

#: Appended to every prompt. Keeps panels from drifting into photorealism or
#: 3D-render territory, which reads as jarringly out of place next to
#: hand-styled manhwa panels.
_QUALITY_SUFFIX = "clean line art, dynamic composition, high detail"

#: Universal negative prompt. Not novel-specific -- these are diffusion
#: artifacts to suppress regardless of style, distinct from `attire.py`'s
#: per-novel style tables.
NEGATIVE_PROMPT = (
    "photorealistic, 3d render, blurry, deformed hands, extra limbs, "
    "watermark, text, signature, lowres"
)


def build_image_prompt(panel_cast: PanelCast) -> str:
    """Compose one prompt string from a resolved `PanelCast`.

    Returns a style/environment-only prompt (still a valid establishing-shot
    prompt) when nobody is in frame -- `get_panel_cast` returns exactly that
    shape for a block outside every tracked scene.
    """
    parts: list[str] = []
    if panel_cast.environment:
        parts.append(panel_cast.environment)

    for character in panel_cast.foreground_characters:
        parts.append(f"{character.self_label} wearing {character.attire}")

    for mob in panel_cast.background_mobs:
        descriptor = f"background: {mob.description}"
        if mob.attire:
            descriptor += f" ({mob.attire})"
        parts.append(descriptor)

    parts.append(_QUALITY_SUFFIX)
    return ", ".join(parts)
