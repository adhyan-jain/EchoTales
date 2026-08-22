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
budget discipline Section 3 applies everywhere, and is only affordable because
`render/beats.py` cut panels from 89 to ~14.

The director is told the canonical appearance of whoever is present
(`persona/canon.py`) and instructed to restate it verbatim, because the
hosted image model takes no reference-image conditioning -- repeating the
description in every prompt is the only consistency lever left.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from echotales.core.store import Store

log = logging.getLogger(__name__)

#: **Written for 199 chapters, not for one.** Every rule below replaces a
#: failure that was previously patched downstream in `panels.py`'s negative
#: prompts, where the fix costs scarce CLIP tokens on every panel forever.
#: The director's output is prose the budget then has to carry, so a
#: specification stated correctly here is free and the same specification
#: enforced later is not -- at chapter scale that difference compounds.
SYSTEM = (
    "You are the art director for a Chinese xianxia web-novel adaptation. "
    "Given a passage, decide the single most striking image to draw for it. "
    "Think like a storyboard artist: one clear subject, one clear action, a "
    "real setting, a definite time of day. Never describe several moments at "
    "once.\n\n"

    "STRICT RULES — violations produce unusable panels:\n\n"

    "1. ONLY describe what the passage explicitly shows. If clothing colour, "
    "an object, or a character's expression is not stated in the passage, do "
    "not invent it. The cast appearance block is reference only -- never put "
    "appearance details into 'action' unless the passage itself mentions them.\n\n"

    "2. EVERY person you name must have their sex stated. 'A man' or 'a woman' "
    "or the character's name (if male, write it). Anything unstated is drawn "
    "female by default. If the passage names no one, draw the setting only.\n\n"

    "3. NEVER invent people. No 'warriors', 'guards', 'warrior women', "
    "'onlookers', 'soldiers', 'elders' unless those words appear in the "
    "passage. Dialogue is one person addressing another -- not a crowd. "
    "An empty or one-person scene is correct information, not a gap to fill.\n\n"

    "4. Ancient China only. Use concrete detail: hanfu, sashes, upturned tiled "
    "roofs, stone courtyards. No kimono, obi, torii, paper screens, cherry "
    "blossom.\n\n"

    "5. You may only reference characters whose names appear in the CAST list below. "
    "If CAST is empty, describe the scene without naming any character — use 'a figure', 'someone', 'the observer', or describe the environment alone. "
    "Never invent character names. Never draw on external knowledge of the source novel. "
    "Names outside CAST are forbidden even if they seem appropriate to the setting.\n\n"

    "6. If a character's gender is unstated, do not draw them as a specific character; "
    "render as a silhouette, back-turned figure, or environmental element.\n\n"

    "7. One place per shot. One ground plane, one building, one horizon.\n\n"

    "8. No film vocabulary. No 'close-up on', 'the shot' pans', 'into the camera'."
)


class PanelDirection(BaseModel):
    """One shot, as the director specifies it."""

    #: "wide" | "medium" | "close" -- framing, in the storyboard sense.
    shot: str = Field(default="medium")
    #: What is happening, as a single visual sentence.
    action: str = Field(default="")
    #: **Experimental** (2026-08-20): who is where in frame, as a short,
    #: literal spatial sentence -- "Fang Yuan stands alone at centre;
    #: attackers surround him at the edges of frame, left, right and
    #: behind." `action` alone left composition entirely to the image
    #: model's own prior, which is measurably the failure mode a checkpoint
    #: swap does not fix (HANDOFF 4.42/4.43): asked for "surrounded by
    #: armed opponents" with no spatial commitment, both `refined` and
    #: `noobai` composed an unrelated calm two-person scene. A `layout`
    #: instruction forces the director to commit to concrete positions
    #: rather than leaving the diffusion model to invent a composition
    #: wholesale. Not yet proven to move the number -- an experiment to
    #: verify against real panels, not a settled fix.
    layout: str = Field(default="")
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
    context_brief: str = "",
    max_chars: int = 2400,
) -> str:
    """Ask the director for one shot.

    `cast` maps a present character's name to their canonical appearance;
    it is quoted into the request so the director can name people rather
    than inventing "a young man", and can restate their look.
    """
    lines = [f"Novel setting: {novel_style}", ""]
    if context_brief:
        # The graph's own answer to "what is relevant here" -- who is
        # present with their rank and faction, where this is, which
        # factions are in play -- filtered to what is known by this
        # position. See `world/context.py`.
        lines += ["What the story knows at this point:", context_brief, ""]
    cast_list = list(cast.keys()) if cast else "EMPTY"
    lines.append(f"CAST for this beat: {cast_list}")
    lines.append("")
    
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
        "  action        one sentence: the single moment to draw, "
        "using only what the passage states (do not add clothing "
        "colours, expressions, or objects the passage does not mention)",
        "  layout        one sentence: where each person is in frame. "
        "Use the character's real name, never the letter X or a "
        "placeholder. Example when surrounded: 'Fang Yuan stands at "
        "centre; enemies ring him on all sides.' Example when alone: "
        "'Fang Yuan stands alone; no one else is present.'",
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

    def to_image_prompt(self, *, scene_locale: str = "") -> str:
        """Compose the final text-to-image prompt.

        Canonical appearances are restated in full here rather than
        referred to, because the hosted image model has no memory between
        panels and no reference-image input -- the description *is* the
        continuity mechanism.

        `scene_locale` is the pipeline-computed location vocabulary shared
        by every panel in this scene. It comes after the director's own
        setting in the priority order so the director's specific description
        wins when both compete for tokens; it supplements when there is room,
        providing the consistent background anchor that stops consecutive
        panels of the same scene rendering in five unrelated places.
        """
        d = self.direction
        shot = d.shot if d.shot in _SHOTS else "medium"
        framing = {
            "wide": "wide establishing shot, full scene, strong depth",
            "medium": "medium shot, characters and setting both visible",
            "close": "close-up, tight framing on the subject's face",
        }[shot]

        from echotales.pipeline.persona.prompt import (
            STYLE_ANCHOR,
            condense_clause,
            fit_to_budget,
        )

        # Style anchor always leads — it is the first thing CLIP reads and the
        # last thing truncation drops. Without it this path produces generic
        # anime; with it the checkpoint's own guofeng/xianxia weights activate.
        parts: list[str] = [STYLE_ANCHOR]
        if d.action:
            parts.append(d.action)
        if d.layout:
            parts.append(d.layout)
        # Setting and lighting come right after the action/layout description
        # and before character appearance. Background should read in every
        # panel; a character appearance that crowds it out is too long --
        # condense_clause below trims the appearance to the most discriminating
        # features, freeing the tokens that setting and lighting need.
        if d.setting:
            parts.append(d.setting)
        if d.lighting:
            parts.append(d.lighting)
        _director_text = f"{d.action or ''} {d.layout or ''}".lower()
        _has_white_robe = False
        for name, look in self.cast.items():
            # Check both action and layout: the director sometimes names the
            # character in layout ("Fang Yuan stands alone") while using a
            # pronoun in action ("He watches the enemies"). Either occurrence
            # is enough evidence the character is in frame.
            if name.lower() in _director_text:
                # condense_clause strips headcount tags (already in cast_tags)
                # and drops the least-discriminating features, freeing ~15
                # tokens that would otherwise crowd out setting/lighting.
                condensed = condense_clause(look)
                parts.append(f"{name} ({condensed})")
                if "white robe" in condensed.lower():
                    _has_white_robe = True
        # Reinforce white robe colour when the character appearance calls for it.
        # Measured v38: negative suppression of teal shifted the model to dark
        # charcoal (the checkpoint's next preferred colour) rather than white.
        # A standalone "pure white outer robe" after the character clause adds
        # explicit colour direction that survives as a separate CLIP token group.
        if _has_white_robe:
            parts.append("pure white outer robe")
        # Score tags immediately after character appearance so they survive when
        # scene_locale and key_objects push the prompt to 77 tokens. Measured
        # v37: 19/24 prompts had no score tags because the character clause used
        # ~20 tokens and scene_locale + key_objects then filled the budget,
        # leaving nothing for quality tags. Character appearance is mandatory;
        # scene_locale is a helpful supplement but not as critical as quality.
        parts.append("score_9, score_8_up, highly detailed, cinematic lighting")
        if scene_locale:
            # Scene-level location anchor: same string for every panel in
            # the scene, so consecutive panels don't render as different places.
            # Placed after score tags so quality survives the budget before locale.
            parts.append(scene_locale)
        if d.key_objects:
            parts.append(", ".join(str(o) for o in d.key_objects if o))
        if d.mood:
            parts.append(f"{d.mood} mood")
        parts.append(framing)

        # **Budget-fit, highest priority first.** This path never did, while
        # the mechanical assembler (`persona/prompt.py::build_image_prompt`)
        # always has -- so director-written prompts ran 150+ tokens against
        # CLIP's 77 and lost everything after the halfway point, silently.
        # Order is a priority ranking, not reading order: what the panel is
        # *of* has to survive; scenery and quality tags are what should fall
        # off the end.
        return fit_to_budget(parts)


def direct_beat(
    beat_text: str,
    *,
    cast: dict[str, str],
    novel_style: str,
    client: object,
    novel_id: str = "",
    context_brief: str = "",
    store: Store | None = None,
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
            build_prompt(
                beat_text,
                cast=cast,
                novel_style=novel_style,
                context_brief=context_brief,
            ),
            PanelDirection,
            system=SYSTEM,
            novel_id=novel_id,
        )
    except Exception as exc:
        log.warning("panel direction failed: %s", exc)
        return None

    direction = result.value
    direction = _validate_direction(
        direction, beat_text=beat_text, cast=cast, novel_id=novel_id, store=store
    )
    return Direction(direction=direction, cast=cast, novel_style=novel_style)


#: Comma-separated phrases that must never appear in a final image prompt.
#: These are model hallucinations that survive prompt-level validation because
#: they appear in the assembled string (after `to_image_prompt`) rather than
#: in a specific direction field. Listed as literal substrings (lower-cased);
#: a comma-clause containing one of these is excised rather than the whole prompt.
_BANNED_PROMPT_PHRASES: tuple[str, ...] = (
    "warrior women",
    "warrior woman",
    "female warrior",
    "female warriors",
    "women warriors",
    "woman warrior",
    "armed women",
    "armed woman",
)


def sanitize_prompt(prompt: str) -> str:
    """Remove known hallucinated phrases from a final image prompt string.

    Operates at the comma-clause level: strips the whole clause containing
    a banned phrase rather than leaving a dangling comma or truncated word.
    Called on the final assembled prompt just before it enters the cache and
    the image engine, so it catches whatever the field-level validator missed.
    """
    lower = prompt.lower()
    for phrase in _BANNED_PROMPT_PHRASES:
        if phrase not in lower:
            continue
        # Split on commas, drop any clause that contains the phrase,
        # rejoin. Preserves clause order and avoids regex on freeform text.
        parts = prompt.split(",")
        parts = [p for p in parts if phrase not in p.lower()]
        prompt = ",".join(parts)
        lower = prompt.lower()
        print(
            f"[direction] sanitized hallucinated phrase {phrase!r} from prompt",
            flush=True,
        )
    return prompt


#: Groups the director must never invent. Any of these appearing in action or
#: layout when the word is absent from both the passage and the cast list is a
#: hallucination. The fix is to strip the offending field back to the safe
#: fallback rather than pass invented content to the image engine.
_HALLUCINATED_GROUP_RE = re.compile(
    r"\b(warrior\s+women?|female\s+warriors?|woman\s+warrior|"
    r"armed\s+women?|women\s+soldiers?|"
    r"guards?|soldiers?|onlookers?|bystanders?|spectators?)\b",
    re.IGNORECASE,
)


def _validate_direction(
    d: PanelDirection, *, beat_text: str, cast: dict[str, str], novel_id: str = "", store: Store | None = None
) -> PanelDirection:
    """Post-call guardrails that catch what the prompt rules could not.

    Three checks:
    1. Hallucinated groups: if 'action' or 'layout' contains a group noun
       that does not appear in the passage text or the cast list, blank the
       offending field. The image prompt falls back to the assembled
       mechanical prompt, which is worse but does not put invented people
       in frame.
    2. Literal 'X' placeholder: if layout still says 'X alone' or 'X stands',
       blank it. The layout instruction example used X as a variable and
       some models copy it verbatim.
    3. Character name validation: parse the director's output for character names
       using the gazetteer logic. Log violations for out-of-scene leakage or
       fabricated names.
    """
    combined_source = beat_text.lower() + " " + " ".join(cast.keys()).lower()

    def _has_hallucinated_group(text: str) -> bool:
        m = _HALLUCINATED_GROUP_RE.search(text)
        if m is None:
            return False
        # If the exact word appears in the passage or cast list, it is not
        # invented -- the passage itself placed them there.
        return m.group(0).lower() not in combined_source

    if _has_hallucinated_group(d.action or ""):
        log.warning("director hallucinated group in action: %r -- blanked", d.action)
        d = d.model_copy(update={"action": ""})
    if _has_hallucinated_group(d.layout or ""):
        log.warning("director hallucinated group in layout: %r -- blanked", d.layout)
        d = d.model_copy(update={"layout": ""})

    # Literal placeholder the model copies from the layout example.
    if re.search(r"\bX\s+(alone|stands|is\b)", d.layout or "", re.IGNORECASE):
        log.warning("director used literal 'X' placeholder in layout: %r -- blanked", d.layout)
        d = d.model_copy(update={"layout": ""})

    # Character name validation
    if store and novel_id:
        _validate_character_names(d, cast, novel_id, store)

    return d


def _validate_character_names(
    d: PanelDirection, cast: dict[str, str], novel_id: str, store: Store
) -> None:
    """Parse the director's output for character names and validate against the cast and entity table.

    For each detected name:
    1. If the name is in the cast dict → keep.
    2. If the name is in the novel's entity table but not in the cast dict →
       strip it from the director output, replace with 'a figure', and log as
       'out-of-scene leakage'.
    3. If the name is not in the entity table at all → strip, log as 'fabricated_name'.
    """
    from echotales.core.enums import AliasType
    from echotales.pipeline.mentions.gazetteer import Gazetteer
    from echotales.pipeline.mentions.ner import HeuristicDetector

    text_to_scan = f"{d.action or ''} {d.layout or ''}".strip()
    if not text_to_scan:
        return

    # `cast` maps a present character's *name* to their appearance clause
    # (see `build_prompt`) -- there is no entity id here, so the cast check
    # below is by name, not id.
    cast_names = {name.lower() for name in cast}

    gazetteer = Gazetteer()
    for entity in store.all_selves(novel_id):
        if entity.canonical_label:
            gazetteer.add(entity.canonical_label, AliasType.RIGID_NAME, target_id=entity.id)

    def _strip(name: str) -> None:
        if d.action:
            d.action = d.action.replace(name, "a figure")
        if d.layout:
            d.layout = d.layout.replace(name, "a figure")

    known_hits = gazetteer.find(text_to_scan)
    for hit in known_hits:
        if hit.surface.lower() in cast_names:
            continue  # Named character is in the cast for this beat -- keep it.

        entity = store.get_self(hit.target_id) if hit.target_id else None
        if entity is not None and entity.kind.is_person:
            log.warning(
                "director referenced out-of-scene character %r (id=%s) -- stripped",
                hit.surface, hit.target_id,
            )
        else:
            log.warning(
                "director referenced a non-person entity as a character: %r -- stripped",
                hit.surface,
            )
        _strip(hit.surface)

    # A name the gazetteer has never heard of at all cannot be found by
    # lookup -- it has to be *found*, with the same heuristic capitalised-name
    # detector `mentions/ner.py` uses for offline runs. Anything it flags that
    # is neither in the cast nor a known entity is an invented name.
    known_surfaces = {hit.surface for hit in known_hits}
    for span in HeuristicDetector().detect(text_to_scan):
        # The heuristic regex captures a trailing possessive ("Fang Yuan's")
        # as part of the span; compare the bare name so a cast/known member
        # referenced possessively isn't misread as an unrecognised one.
        bare = re.sub(r"[’']s$", "", span.text)
        if bare.lower() in cast_names or bare in known_surfaces:
            continue
        log.warning("director fabricated character name: %r -- stripped", span.text)
        _strip(span.text)
