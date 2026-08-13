"""The director: deciding what a panel should actually show.

Every prompt this pipeline built until now was **assembled**, not composed --
cast tags, then a truncated slice of narration, then a locale looked up from
a keyword table, then a style suffix. That produces a grammatical prompt that
is nonetheless about nothing: the beat is a fragment torn mid-sentence, the
locale is whichever cue word appeared first, and no part of it knows what is
*happening*. It is why panels came back unrelated to the story around them.

A model reading the whole beat can answer the question the assembler could
not: **what single image would a reader want here?** That is a
comprehension task, and comprehension is exactly what the assembler lacked.

**One call per beat, not per block** -- ~14 a chapter, which is the same
budget discipline §3 applies everywhere, and is only affordable because
`render/beats.py` cut panels from 89 to ~14.

The director is told the canonical appearance of whoever is present
(`persona/canon.py`) and instructed to restate it verbatim, because the
hosted image model takes no reference-image conditioning -- repeating the
description in every prompt is the only consistency lever left.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

SYSTEM = (
    "You are the art director for a Chinese xianxia web-novel adaptation. "
    "Given a passage, decide the single most striking image to draw for it. "
    "Think like a storyboard artist: one clear subject, one clear action, a "
    "real setting, a definite time of day. Never describe several moments at "
    "once, and never describe something the passage does not contain."
)


class PanelDirection(BaseModel):
    """One shot, as the director specifies it."""

    #: "wide" | "medium" | "close" -- framing, in the storyboard sense.
    shot: str = Field(default="medium")
    #: What is happening, as a single visual sentence.
    action: str = Field(default="")
    #: Where it happens, concretely.
    setting: str = Field(default="")
    #: Time of day / weather / light.
    lighting: str = Field(default="")
    #: Objects that must appear (a glowing cicada, a raised sword).
    key_objects: list[str] = Field(default_factory=list)
    #: One or two words of emotional register.
    mood: str = Field(default="")


_SHOTS = {"wide", "medium", "close"}


def build_prompt(
    beat_text: str,
    *,
    cast: dict[str, str],
    novel_style: str,
    max_chars: int = 2400,
) -> str:
    """Ask the director for one shot.

    `cast` maps a present character's name to their canonical appearance;
    it is quoted into the request so the director can name people rather
    than inventing "a young man", and can restate their look.
    """
    lines = [f"Novel setting: {novel_style}", ""]
    if cast:
        lines.append("Characters who may appear, with their fixed appearance:")
        for name, look in cast.items():
            lines.append(f"  - {name}: {look}")
        lines.append("")
    lines += [
        "Passage:",
        beat_text[:max_chars].strip(),
        "",
        "Return JSON with these keys:",
        '  shot          one of "wide", "medium", "close"',
        "  action        one sentence: the single moment to draw",
        "  setting       where it happens, concretely",
        "  lighting      time of day, weather, quality of light",
        "  key_objects   list of objects that must be visible",
        "  mood          one or two words",
        "",
        "Only include characters the passage actually places in the scene.",
        "Return only JSON.",
    ]
    return "\n".join(lines)


@dataclass(slots=True)
class Direction:
    """A director's shot, rendered down to an image prompt."""

    direction: PanelDirection
    cast: dict[str, str]
    novel_style: str

    def to_image_prompt(self) -> str:
        """Compose the final text-to-image prompt.

        Canonical appearances are restated in full here rather than
        referred to, because the hosted image model has no memory between
        panels and no reference-image input -- the description *is* the
        continuity mechanism.
        """
        d = self.direction
        shot = d.shot if d.shot in _SHOTS else "medium"
        framing = {
            "wide": "wide establishing shot, full scene, strong depth",
            "medium": "medium shot, characters and setting both visible",
            "close": "close-up, tight framing on the subject's face",
        }[shot]

        parts: list[str] = []
        if d.action:
            parts.append(d.action)
        for name, look in self.cast.items():
            if name.lower() in (d.action or "").lower():
                parts.append(f"{name} ({look})")
        if d.setting:
            parts.append(d.setting)
        if d.lighting:
            parts.append(d.lighting)
        if d.key_objects:
            parts.append(", ".join(str(o) for o in d.key_objects if o))
        if d.mood:
            parts.append(f"{d.mood} mood")
        parts.append(framing)
        parts.append(self.novel_style)
        parts.append(
            "highly detailed, cinematic lighting, dramatic composition, "
            "masterpiece, best quality"
        )
        return ", ".join(p for p in parts if p)


def direct_beat(
    beat_text: str,
    *,
    cast: dict[str, str],
    novel_style: str,
    client: object,
    novel_id: str = "",
) -> Direction | None:
    """Get one shot from the director, or None if the call fails.

    Returning None rather than raising keeps a failed direction from
    sinking a chapter: `render_panels` falls back to the assembled prompt,
    which is worse but real.
    """
    from echotales.pipeline.llm.tasks import Task

    try:
        result = client.complete(  # type: ignore[attr-defined]
            Task.PANEL_DIRECTION,
            build_prompt(beat_text, cast=cast, novel_style=novel_style),
            PanelDirection,
            system=SYSTEM,
            novel_id=novel_id,
        )
    except Exception as exc:  # noqa: BLE001 - a bad panel must not end a run
        log.warning("panel direction failed: %s", exc)
        return None

    return Direction(direction=result.value, cast=cast, novel_style=novel_style)
