"""One staging sheet per scene, decided once and repeated verbatim in every panel of that scene.

Why (owner review of the 2026-11-19 renders): panels of one scene were each directed from scratch, so the cliff changed
between panels, the hero stood on the crowd's side in one and against it in the next, and a crowd the text only says
"shouted at him" was drawn as a ring around him. A manhwa reads as continuous because the set, light, costume and who
stands where never change between panels; only camera, action and expression do. The sheet carries exactly the first
three and each panel's own paragraph carries the rest.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class SceneStaging(BaseModel):
    """What stays fixed for every panel of one scene."""

    #: The place, concrete and taken only from the scene's own text ("bare rock cliff edge, twisted pines, sea of clouds").
    set: str = Field(default="")
    #: Who stands where, facing whom, on which side of the frame; crowds in rows or a shallow arc on one side.
    blocking: str = Field(default="")
    #: Time of day and light, only if the scene states or implies it.
    light: str = Field(default="")

    def text(self) -> str:
        parts = []
        if self.set.strip():
            parts.append(f"Set: {self.set.strip().rstrip('.')}.")
        if self.blocking.strip():
            parts.append(f"Blocking: {self.blocking.strip().rstrip('.')}.")
        if self.light.strip():
            parts.append(f"Light: {self.light.strip().rstrip('.')}.")
        return " ".join(parts)


STAGING_SYSTEM = (
    "You are the stage manager of a manhwa adaptation. For ONE scene you write the fixed staging sheet that every panel of the "
    "scene will repeat unchanged. Use only what the scene text states or plainly implies.\n"
    "- set: the place in concrete terms from the text (ground, rock, trees, water, weather, furniture). No buildings, "
    "gates, pavilions or ornaments the text does not name.\n"
    "- blocking: who stands where, facing whom, and on which side of the frame. Keep one axis: the lead on one side, the "
    "others on the opposite side facing the lead, so the camera never crosses the line between them. A crowd or group "
    "faces its focus in rows on ONE side of the frame; it never "
    "forms a ring around anyone unless the text literally says they surround him. People who kneel to a master kneel in "
    "rows in front of him, facing him. Use only names from CAST.\n"
    "- Distance between a crowd and a lone lead comes from DEPTH, never from an instruction to leave space empty (the image model "
    "ignores \"twenty paces of empty ground\": 0 of 4 seeds). When a crowd faces a lone figure, stage it one of two ways and say "
    "which: (a) the crowd in the foreground in tidy rows seen from behind, all facing away from the camera, and the lead small and "
    "alone far ahead on the highest or farthest point, bare ground between; or (b) the camera behind the lead's shoulder looking "
    "down, the crowd small in rows far below on a lower ledge. Choose (a) unless the lead is above the crowd in the text and the "
    "scene is about him looking down at them. (Z-Image Turbo, 4 seeds each, 2026-11-19: (a) 4 of 4 a tiny lone figure on the summit with rows facing him, but 2 of 4 also "
    "a green-robed lookalike in the foreground rows; (b) 4 of 4 a clear gap, the crowd a thin line; the side-by-side wording "
    "separated only where the cliff happened to.)\n"
    "- light: time of day and light only if stated or implied. A coloured glow belongs to what glows or to the window it falls "
    "through: name that thing in set (\"a red moon in the window, its red light on the desk\") and keep light to the ambient "
    "time and strength; a bare colour as the scene's light tinted a person red (LotM ch1 block 24).\n"
    "Be specific: name the ground, the nearest and farthest features, the side of the frame each group occupies and the "
    "distance between them. Example of the level of detail (structure only, never reuse its content): set: \"a flat "
    "lakeshore of grey pebbles with reeds on the left and a low hill behind\"; blocking: \"the old fisherman sits on the "
    "left facing right; three children kneel in two rows on the right, all facing him, an arm's length of empty "
    "pebbles between them\"; light: \"overcast noon\". Name people exactly as the scene text does.\n"
    "- If a PREVIOUS STAGING is given, this scene continues it. A place or light that THIS scene's own text states replaces "
    "the previous one; where the text states none, repeat the previous set, blocking and light word for word. A memory, a "
    "thought, a laugh or a line of speech does not move anyone: the set stays, and nothing the text does not mention is added.\n"
    "- If LATER TEXT is given, the scene itself states no place: take the place from it (it is the same place) and stage only "
    "this scene's own people and lines.\n"
    "Return JSON with keys set, blocking, light, each one or two plain sentences."
)

_RING = re.compile(r"\b(circle|ring(?:ed|s)?|surround\w*|encircl\w*|all sides|around (?:him|her|them))\b", re.I)
# "surrounded" in the text is prose for outnumbered, not geometry (RI ch1: "enemies surrounded him" on a cliff edge with rock behind
# him); only an explicit circle or ring is staged as one.
_TEXT_RING = re.compile(r"\b(in a circle|a circle|ring of|encircl\w*|in a ring)", re.I)
_NAME = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")


def validate_staging(
    s: SceneStaging, *, scene_text: str, cast: list[str]
) -> tuple[SceneStaging, list[str]]:
    """Drop what the scene does not support. Returns the cleaned sheet and the reasons text was removed.

    Two failures measured in the 2026-11-19 renders: a crowd that only "shouted at him" was written as a ring around him,
    and the director put a character who is not in CAST into the blocking."""
    rejects: list[str] = []
    blocking = s.blocking
    allowed = {n.lower() for n in cast}
    text_l = scene_text.lower()
    for m in _NAME.finditer(blocking):
        name = m.group(0)
        if name.lower() not in allowed and name.lower() not in text_l:
            rejects.append(f"name outside cast: {name}")
            kept = [c for c in re.split(r"(?<=[;,])\s+", blocking) if name not in c]
            blocking = " ".join(kept).rstrip(",; ")
    if _RING.search(blocking) and not _TEXT_RING.search(scene_text):
        rejects.append("ring not stated by the text")
        kept = [c for c in re.split(r"(?<=[;,])\s+", blocking) if not _RING.search(c)]
        blocking = " ".join(kept).rstrip(",; ")
        lead = cast[0] if cast else "the lead"
        blocking = (blocking + "; " if blocking else "") + f"the others stand in rows on one side of the frame, all facing {lead}"
    if rejects:
        return SceneStaging(set=s.set, blocking=blocking, light=s.light), rejects
    return s, rejects


def direct_staging(
    scene_text: str, *, cast: dict[str, str], novel_style: str, client: object, novel_id: str = "", max_chars: int = 2600,
    previous: str = "", lookahead: str = "",
) -> SceneStaging | None:
    """One director call per scene. None on any failure; panels then fall back to their own paragraph.

    `previous` is the sheet of the scene before: RI ch1's memory scenes state no place and a fresh call invented a grassy hillside
    and a hall beside the cliff scene they belong to. `lookahead` is the next scenes' text for a scene that opens a chapter with
    no place of its own (block 0 of RI ch1 is one shouted line; alone it was staged as a meadow, and every later scene carried that)."""
    from echotales.pipeline.llm.tasks import Task

    prompt = "\n".join([
        f"Novel setting: {novel_style}",
        f"CAST: {list(cast) if cast else '(none listed: use the names exactly as the scene text writes them)'}",
        *([f"PREVIOUS STAGING (this scene continues it): {previous}"] if previous.strip() else []),
        "Scene text:", scene_text[:max_chars].strip(), "",
        *(["LATER TEXT of the same chapter (the place only):", lookahead[:1200].strip(), ""] if lookahead.strip() else []),
        "Return only JSON with keys set, blocking, light.",
    ])
    try:
        result = client.complete(Task.PANEL_DIRECTION, prompt, SceneStaging, system=STAGING_SYSTEM, novel_id=novel_id)  # type: ignore[attr-defined]
    except Exception as exc:
        log.warning("scene staging failed: %s", exc)
        return None
    if not isinstance(result.value, SceneStaging):  # a client that answers every task with one canned object
        return None
    cleaned, rejects = validate_staging(result.value, scene_text=scene_text, cast=list(cast))
    if rejects:
        log.info("scene staging cleaned: %s", rejects)
    return cleaned if cleaned.text() else None


# A small affect lexicon, used only to FLAG a face for the director to redo, never to rewrite one. A flag can be wrong
# without damage; a rewrite could not. Measured trigger: a mocking laugh at enemies was drawn as a happy, child-like grin.
_HAPPY = re.compile(r"\b(happy|happily|cheerful|cheerfully|joyful|joyous|bright smile|warm smile|beaming|delighted|"
                    r"innocent|sweet smile|gleeful|grinning (?:happily|brightly))\b", re.I)
_HOSTILE_CONTEXT = re.compile(r"\b(contempt\w*|scorn\w*|mock\w*|sneer\w*|cold(?:ly)?|merciless|ruthless|enem(?:y|ies)|"
                              r"hostil\w*|threat\w*|cornered|furious|rage|hatred|despise\w*|arrogan\w*|ultimatum|kill\w*)\b", re.I)
_HOSTILE_FACE = re.compile(r"\b(mock\w*|sneer\w*|cold\w*|contempt\w*|scorn\w*|smirk\w*|cruel|merciless|narrowed|icy|cynical|"
                           r"disdain\w*|menacing|sinister)\b", re.I)


def expression_conflicts(expression: str, context: str) -> str:
    """A reason when a happy-reading face is written on a hostile or contemptuous line, else ''."""
    if _HAPPY.search(expression) and _HOSTILE_CONTEXT.search(context) and not _HOSTILE_FACE.search(expression):
        return "positive expression on a hostile line"
    return ""
