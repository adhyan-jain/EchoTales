"""The director: deciding what a panel should actually show.

DEPRECATED: Legacy illustrated-audiobook direction module.
Superseded by `echotales.pipeline.screenplay.compiler` and `echotales.pipeline.keyframes.engine`
in the Path 1 / Path 2 modernization architecture. Retained for backward compatibility.

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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from echotales.pipeline.spans.scene import _MOB_ROLE_NOUNS
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
#: The owner's hand-written probe prompts (`data/scratch/image_probe/prompts.py`), with their style lead removed because the
#: compiler writes the lead itself. They were themselves written by a language model and drew the panels he asked to match,
#: so they are the director's few-shot STYLE: one composed scene, who stands where relative to whom, what each does and
#: shows on the face, wounds and clothing state, the setting's concrete detail, the light and the camera. Structure only --
#: the system prompt forbids reusing their people, places or objects.
_PROBE_EXAMPLES: tuple[str, ...] = (
    "A wide shot on a narrow mountain cliff edge at dusk, jagged rock, twisted pines, a sea of clouds far below. In the "
    "centre stands a lone demonic cultivator, a tall lean young man with long black hair and torn dark green robes, "
    "bleeding from many wounds, standing straight with an icy, contemptuous calm. Facing him from the right of the frame, "
    "across a stretch of empty rock, stand dozens of martial artists of the righteous sects in white and blue robes with "
    "drawn swords and spears, banners behind them, in rows that fan out along the path. Cold blue dusk light, mist, dramatic scale.",
    "Close-up portrait of a cold, ruthless demonic cultivator, a young man with long black hair, pale skin, blood running "
    "from his temple and the corner of his mouth, torn green robe collar. His expression is calm and merciless, a faint "
    "mocking smile, eyes half-lidded and utterly unafraid. Behind him, out of focus, a mountain cliff at dusk and the "
    "blurred shapes of many robed swordsmen.",
    "A stern old sect elder in white robes at the front of a crowd of armed martial artists on a mountain ledge points his "
    "sword forward and shouts an ultimatum; in the foreground, back to the viewer and slightly out of focus, the lone "
    "wounded figure in torn green robes he is addressing. Dusk, mist, pines, cliffs.",
)


def system_prompt(novel_id: str = "") -> str:
    """The director's rules for this novel's world.

    Rule 4 and the examples used to be hardcoded Chinese xianxia ("hanfu ... Ancient China only"), so a Regency novel
    (the Pride and Prejudice demo book) was told to draw hanfu. The world comes from the same genre profile every other
    prompt reads (`persona/genre.py`); only an xianxia project (or no project, which `genre_of` treats as xianxia)
    keeps the xianxia rule. Every other rule is about passages, not genres, and is unchanged.
    """
    from echotales.pipeline.persona.genre import genre_of

    if genre_of(novel_id) == "xianxia":
        world = (
            "4. Ancient China only. Clothing is hanfu with sashes and wide sleeves. The place comes ONLY from the "
            "passage and the scene staging: never add any building or ornament the text does not "
            "name. No kimono, obi, torii, paper screens, cherry blossom.\n\n"
        )
        kind = "a Chinese xianxia web-novel adaptation"
    else:
        world = (
            "4. Stay inside the novel's own world and period, given as 'Novel setting' in the request. "
            "Use concrete detail the passage or that setting supports (clothes, rooms, furniture, vehicles of that "
            "time and place); nothing anachronistic and nothing borrowed from another culture.\n\n"
        )
        kind = "a novel adaptation"
    return (
        f"You are the art director for {kind}. "
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

        + world +

        "5. You may only reference characters whose names appear in the CAST list below. "
        "If CAST is empty, describe the scene without naming any character — use 'a figure', 'someone', 'the observer', or describe the environment alone. "
        "Never invent character names. Never draw on external knowledge of the source novel. "
        "Names outside CAST are forbidden even if they seem appropriate to the setting.\n\n"

        "6. If a character's gender is unstated, do not draw them as a specific character; "
        "render as a silhouette, back-turned figure, or environmental element.\n\n"

        "7. One place per shot. One ground plane, one building, one horizon.\n\n"

        "8. No film vocabulary. No 'close-up on', 'the shot' pans', 'into the camera'.\n\n"

        "9. FACIAL EXPRESSION IS INDEPENDENT OF PHYSICAL CONDITION. A wounded, "
        "bleeding, or exhausted character does not default to a pained "
        "expression -- report the face only as the passage actually states it, "
        "as one short phrase ('calm', 'blank stare', 'pained', 'unmoved'), "
        "separate from wounds/blood/torn clothes. If the passage "
        "explicitly states the character's expression does NOT change, or stays "
        "calm/blank/unreadable despite what is happening to them, that contrast "
        "is exactly what to report -- it is real information, not a contradiction "
        "to resolve. If the passage says nothing about the face, infer it from the "
        "line spoken and the situation (an enemy's ultimatum is a furious glare, a victor's laugh is mocking), never from "
        "the body's condition.\n\n"

        "10. SHORT PLAIN PHRASES, NOT SENTENCES AND NOT DATABASE TAGS. The image "
        "prompt is written afterwards from your fields, so each field is a short "
        "plain-English phrase (or a few, comma-separated) saying what is visible: "
        "lowercase, two to five words each, spaces not underscores, no articles, "
        "no connecting words ('and', 'while', 'as'), no periods. Examples: "
        "'standing alone', 'hands clasped', 'torn sleeve', 'facing left', "
        "'crowd watching'. Do not include numeric headcount tags "
        "('1boy', '2boys', 'male focus') -- those are added separately. A "
        "character's name is written exactly as given in CAST, with its normal "
        "spacing and capitalization.\n\n"

        "11. The structured fields ('characters', 'others', 'camera_angle', "
        "'location_detail', 'props') follow the same rules: 'characters' lists "
        "only people in CAST who are in the shot, 'others' is null unless the "
        "passage itself names a group, and 'props' holds only objects the "
        "passage names.\n\n"

        "12. 'composition' is the one field written as flowing English, not short phrases (rule 10 does not apply to it): "
        "one paragraph of three to five sentences that composes the single picture, in the style of the examples below. "
        "Say where the camera is, who stands where relative to whom (a crowd in rows on one side of the frame facing the lone hero, never a ring), what "
        "each visible person is doing, the expression on each face, the state of clothing and body (blood, wounds, torn "
        "cloth) exactly as the passage states them, the setting's concrete details, and the light. Do not write a style "
        "line, quality words or the person's hair and eye colour; those are added separately. Name people exactly as in "
        "CAST, never anyone else, and name no person, place or object that the passage does not contain. If the passage "
        "has a crowd or a group, draw it and say how it stands around the others. If it describes someone's appearance or "
        "age in this moment, say it plainly (a boy of fifteen, an old man). WRITE EACH FACE IN ANIME EMOTION WORDS taken from "
        "this line AND the situation around it, not from the words alone: a cold mocking smile with narrowed eyes and a "
        "raised chin, a contemptuous sneer, blood at the corner of the lips, a furious glare with clenched teeth, wide "
        "shocked eyes, tears running down. A man who laughs at his enemies is contemptuous and mocking, never cheerful "
        "and never childlike. If the request gives SCENE STAGING, the set, blocking and light are already fixed: do not "
        "restate or change them, and keep every person on the side of the frame the staging gives; your paragraph adds "
        "only the camera, this line's action and the faces.\n\n"

        "13. THIN PASSAGES. When the passage shows nothing visible (inner monologue, exposition, backstory, a list of "
        "names), still compose a picture, but only from the passage's own referents: an establishing shot of the place it "
        "is set in, a symbolic close-up of an object it mentions, or the speaker's face reacting. Set 'visual_source' to "
        "\"inferred\" in that case, and to \"text\" whenever the passage itself shows what you drew.\n\n"

        "14. SHOT CHOICE follows the beat: close for an emotional peak, wide for a confrontation with a crowd, an "
        "over-the-shoulder view (say so in the composition) for a face-off between two people, a wide establishing shot "
        "when the place changes. Do not give the same 'shot' value as the previous two panels unless the passage demands "
        "it.\n\n"

        "15. SPOKEN LINES. When the request lists SPOKEN LINES, each line's emotion belongs to the face of the person who SAYS it, "
        "not to whoever is the lead of the shot. If the lead is only addressed by a line, his face is his REACTION to it (a "
        "threat at a man who does not fear it is cold and unmoved, not a smile), and the speaker's emotion goes on the speaker "
        "among the others in 'composition'. The attribution is usually right but not always: if the words talk about the "
        "supposed speaker in the third person ('the demon is going to attack', said of him) or call him by name, someone "
        "else is speaking. A line marked as someone not in CAST is drawn as one of the others, never given a name.\n\n"

        "EXAMPLES OF THE STYLE OF 'composition' (structure only: never reuse their people, places, objects or colours; "
        "your paragraph comes from the passage below and nothing else):\n"
        + "\n".join(f"  - {x}" for x in _PROBE_EXAMPLES)
    )


#: Kept for callers that import the constant; an empty novel id is treated as xianxia by `genre_of`.
SYSTEM = system_prompt("")


class CharacterDirection(BaseModel):
    """Direction for an individual character in frame."""

    name: str = Field(description="Character's name matching CAST")
    position: str = Field(default="center", description="Position in frame: center, left, right, foreground, background")
    pose: str = Field(default="standing", description="Physical pose: standing, sitting, kneeling, running, fighting stance")
    expression: str = Field(default="", description="Facial expression tag: calm_expression, sneering, cold_expression")
    condition: str = Field(default="", description="Physical state/condition: wounded, bloodied, torn robes")


class OthersDirection(BaseModel):
    """Secondary people or crowd present in the shot."""

    kind: str = Field(default="crowd", description="Group category: crowd, righteous sect elders, disciples, guards, onlookers")
    count: int = Field(default=0, description="Approximate count (e.g. 10) or 0 for uncounted group")
    relation_to_lead: str = Field(default="surrounding", description="Relation to lead: surrounding, kneeling before, watching from afar")


class PanelDirection(BaseModel):
    """One shot, as the director specifies it."""

    #: "wide" | "medium" | "close" -- framing, in the storyboard sense.
    shot: str = Field(default="medium")
    #: Camera angle: "eye-level" | "low-angle" | "high-angle" | "dutch-angle" | "birds-eye"
    camera_angle: str = Field(default="eye-level")
    #: Structured per-character direction (Director v2).
    characters: list[CharacterDirection] = Field(default_factory=list)
    #: Others / crowd in frame (Director v2).
    others: OthersDirection | None = Field(default=None)
    #: What is happening, as comma-separated Danbooru-style tags (e.g.
    #: "weapons_drawn, fighting_stance"), not a sentence. Kept as `str`
    #: rather than `list[str]` on purpose: the fabrication guardrail
    #: (`_validate_character_names`) scans this as free text for character
    #: names via the gazetteer/heuristic detector, and a comma-joined string
    #: is exactly what that scanning already expects -- splitting into a
    #: list would need every validator rewritten for no assembly benefit,
    #: since `to_image_prompt_parts` joins fields with commas either way.
    action: str = Field(default="")
    #: Who is in frame and where, as tags -- the character's real name
    #: (exactly as given in CAST) plus spatial/count tags, e.g. "Fang Yuan,
    #: surrounded" or "Fang Yuan, solo, standing_alone". Keeping the literal
    #: name in here (rather than moving presence to a separate structured
    #: field) is deliberate: `to_image_prompt_parts`'s cast-presence check
    #: is a substring scan over `action + layout`, and the fabrication
    #: guardrail already validates names found in this same text -- tags
    #: replacing prose didn't need either mechanism touched.
    #: Originally added 2026-08-20 as a spatial-composition experiment
    #: (HANDOFF 4.42/4.43: `action` alone left composition to the image
    #: model's own prior, which produced an unrelated calm scene for
    #: "surrounded by armed opponents" with no spatial commitment); still
    #: the field that carries presence/position.
    layout: str = Field(default="")
    #: Where it happens, as location tags (e.g. "mountain_background,
    #: stone_courtyard, cliff"), not a prose description.
    setting: str = Field(default="")
    #: Concrete location detail taken from the text (Director v2).
    location_detail: str = Field(default="")
    #: Time of day / weather / light, as tags (e.g. "dusk, misty").
    lighting: str = Field(default="")
    #: Objects that must appear (a glowing cicada, a lantern). Not an
    #: excuse to invent a prop the passage never names -- see rule 1.
    key_objects: list[str] = Field(default_factory=list)
    #: Props explicitly called for in the shot (Director v2).
    props: list[str] = Field(default_factory=list)
    #: One or two mood tags.
    mood: str = Field(default="")
    #: **The subject's face, as one compact tag -- independent of their
    #: physical condition.** Added because a wounded/bleeding character's
    #: face was being drawn pained by default, even on beats where the
    #: passage explicitly says the opposite: RI ch1 blocks 9-13 state
    #: four separate times that Fang Yuan's expression "did not change,
    #: it was calm" despite his wounds, and no prompt ever carried that --
    #: `condition` (blood, torn robes) was the only face-adjacent signal
    #: reaching the checkpoint, whose own prior reads visible injury as a
    #: pained expression. A single tag, not a phrase (`calm_expression`,
    #: not "his expression did not change") -- this has to survive
    #: `to_image_prompt_parts`'s tier-1 budget the same way identity and
    #: condition tags do, and a phrase-length clause is exactly what tier
    #: 1's own fix (see its docstring) exists to stop happening again.
    #: Empty when the passage states nothing about the face -- an
    #: unstated expression is not "neutral", it is unknown, and inventing
    #: one violates rule 1 same as any other detail.
    expression: str = Field(default="")
    #: The composed paragraph in the probe style (see `system_prompt` rule 12): spatial arrangement, each visible person's
    #: action, face, wounds and clothing, setting detail, light and camera, all from this panel's own text. Empty means the
    #: structured fields above are used as before. The Z-Image compiler builds its prompt around it.
    composition: str = Field(default="")
    #: The scene's staging sheet (`render/staging.py`), set by code and never by the model, repeated verbatim on every panel of
    #: the scene so the set, light and blocking cannot drift between panels.
    staging: str = Field(default="")
    #: "text" when the panel's own text shows what is drawn, "inferred" when the passage showed nothing and the director
    #: chose a visual from its referents (rule 13). Kept so `audit` can count how many panels were not text-grounded.
    visual_source: str = Field(default="text")
    #: The framing sentence and focus (`render/framing.py`), set by code from the passage and never by the model: the director's
    #: own `shot` was "medium" for 16 of 16 LotM panels and never reached the Z-Image prompt.
    frame: str = Field(default="")
    frame_focus: str = Field(default="")
    #: The prop an insert shows, so the staging Set is cut to the clauses that name it.
    frame_subject: str = Field(default="")
    #: What `_validate_direction` removed from the paragraph (names and groups the text does not contain), not a model field.
    grounding_rejects: list[str] = Field(default_factory=list)


_SHOTS = {"wide", "medium", "close"}


def build_prompt(
    beat_text: str,
    *,
    cast: dict[str, str],
    novel_style: str,
    context_brief: str = "",
    max_chars: int = 2400,
    recent_shots: list[str] | None = None,
    staging: str = "",
    spoken: str = "",
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
    if recent_shots:
        lines.append(f"Shots of the previous panels, oldest first: {', '.join(recent_shots)}")
    lines.append("")
    if staging:
        lines += ["SCENE STAGING (fixed for every panel of this scene; do not change it, do not restate it):", staging, ""]

    if cast:
        lines.append("Characters who may appear, with their fixed appearance:")
        for name, look in cast.items():
            lines.append(f"  - {name}: {look}" if look else f"  - {name}")
        lines.append("")
    if spoken:
        lines += ["SPOKEN LINES in this passage (who says each one comes from the story graph):", spoken, ""]
    lines += [
        "Passage:",
        beat_text[:max_chars].strip(),
        "",
        "Return JSON with these keys. Text fields are short plain-English "
        "phrases (comma-separated if several): lowercase, spaces not "
        "underscores, no sentences, no articles, no periods:",
        '  shot          one of "wide", "medium", "close"',
        '  camera_angle  one of "eye-level", "low-angle", "high-angle", '
        '"dutch-angle", "birds-eye"; "eye-level" unless the passage gives a reason',
        "  action        what the single moment to draw looks like, "
        "using only what the passage states (do not add clothing colours "
        "or objects the passage does not mention; facial expression goes "
        "in its own field below, not here). Example: "
        "\"weapons drawn, fighting stance\" or \"kneeling, exhausted\".",
        "  layout        the character's real name (exactly as written in "
        "CAST -- never the letter X or a placeholder), followed by "
        "spatial/count phrases. Example when surrounded: \"Fang Yuan, "
        "surrounded\". Example when alone: \"Fang Yuan, alone, "
        "standing\". If CAST is empty, use \"a figure\" instead of a name.",
        "  characters    list with one object per CAST member who is in the shot "
        '(empty list if none): {"name": exactly as in CAST, "position": '
        '"center", "left", "right", "foreground" or "background", "pose": '
        'e.g. "standing", "sitting", "kneeling", "walking", "expression": the '
        'face as one short phrase, only if the passage states it, "condition": '
        'visible state such as "wounded" or "torn sleeve", empty if none}. '
        "Never a name outside CAST.",
        "  others        null, unless the passage itself names other people in "
        'the shot; then {"kind": the group as the passage names it, "count": '
        'a number if stated else 0, "relation_to_lead": e.g. "surrounding", '
        '"watching from afar"}',
        "  setting       the room or place and its notable furniture or "
        "landmarks, taken from the passage or from the "
        "scene setting given above. Leave it empty rather than invent a "
        "place; never reuse wording from these instructions.",
        "  location_detail  one short phrase of concrete place detail the "
        "passage states (a named piece of furniture, a named kind of ground); empty if none",
        "  lighting      time of day / weather / light, ONLY if the "
        "passage or the scene setting states it (night, midnight, dawn, "
        "named lights or weather). Leave it empty if it does not -- do not guess "
        "daylight.",
        "  key_objects   list of objects that must be visible",
        "  props         list of objects the characters handle or that the "
        "passage singles out (only objects the text names); only ones the passage names",
        "  mood          one or two mood words",
        "  composition   the paragraph of system rule 12, plain flowing English from this passage alone; "
        "never empty",
        '  visual_source "text" or "inferred" (system rule 13)',
        "  expression    ONE short anime-emotion face phrase for the lead, ALWAYS filled, drawn from this line AND the "
        "situation around it (who is speaking to whom, who is winning), independent of physical condition -- a wounded "
        "character is not automatically pained. Examples of the vocabulary: \"cold mocking smile, narrowed eyes\", "
        "\"contemptuous sneer\", \"furious glare, clenched teeth\", \"wide shocked eyes\", \"calm unreadable stare\". "
        "A man laughing at his enemies is mocking, never cheerful. If SPOKEN LINES show someone else speaking to the lead, "
        "this is the lead's reaction, not the speaker's emotion.",
        "",
        "Only include characters the passage actually places in the scene. "
        "Do not include numeric headcount tags ('1boy', '2boys', 'male "
        "focus') -- those are added separately from your output. 'alone' "
        "and 'crowd' are fine as composition words when the passage supports "
        "them.",
        "Return only JSON.",
    ]
    return "\n".join(lines)


def _as_tags(text: str, names: list[str]) -> str:
    """Plain phrases back to the underscore tags the NoobAI/Illustrious path was tuned on.

    The director now writes short plain phrases because the prompt compiler writes sentences from them; this legacy
    path (compiler off, `render.prompt_compiler=false`) still wants Danbooru-style tags (HANDOFF 4.42/4.43: sentences
    rendered an unrelated calm scene). A clause naming a cast member keeps its spacing, so the substring checks on
    names below still match; clauses longer than four words are left as written, they are not tags."""
    out = []
    for clause in (c.strip() for c in text.split(",")):
        if not clause:
            continue
        low = clause.lower()
        if any(n.lower() in low for n in names) or len(clause.split()) > 4:
            out.append(clause)
        else:
            out.append(re.sub(r"\s+", "_", clause))
    return ", ".join(out)


@dataclass(slots=True)
class Direction:
    """A director's shot, rendered down to an image prompt."""

    direction: PanelDirection
    cast: dict[str, str]
    novel_style: str
    #: Per-character attire/condition, kept separate from `cast`'s identity
    #: clause so `fit_to_budget` can drop it independently. Folding a beat's
    #: torn-and-bloodied override into the same string as hair/eyes made one
    #: oversized part that got skipped wholesale -- identity and all --
    #: instead of just losing the condition detail. See HANDOFF v44 fix.
    conditions: dict[str, str] = field(default_factory=dict)
    #: **Needed so `to_image_prompt_parts` can pick the right
    #: `style_anchor()` (`persona/attire.py`).** Previously the tier-0 style
    #: anchor was one hardcoded xianxia string shared by every novel --
    #: confirmed as the reason an LOTM render came out xianxia-styled
    #: despite `novel_style`/`WORLD_CONTEXT` already being novel-specific.
    novel_id: str = ""

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
        from echotales.pipeline.persona.prompt import fit_to_budget
        return fit_to_budget(self.to_image_prompt_parts(scene_locale=scene_locale))

    def to_image_prompt_parts(
        self, *, scene_locale: str = "", world_context: str = ""
    ) -> list[str]:
        """Construct the prompt components, prioritizing what the panel shows."""
        names = [*self.cast, "a figure"]  # the unnamed-subject marker is matched verbatim below
        d = self.direction.model_copy(update={
            f: _as_tags(getattr(self.direction, f) or "", names)
            for f in ("action", "layout", "setting", "lighting", "mood", "expression")
        })
        shot = d.shot if d.shot in _SHOTS else "medium"
        # 2-3 tokens, not a full sentence: this used to read "wide
        # establishing shot, full scene, strong depth" etc, and giving it a
        # full clause here (rather than at the very end, where it used to
        # sit and almost never survived anyway) measurably starved the
        # identity clause of budget -- see the priority-order comment below.
        framing = {
            "wide": "wide shot",
            "medium": "medium shot",
            "close": "close-up",
        }[shot]

        from echotales.pipeline.persona.attire import style_anchor
        from echotales.pipeline.persona.prompt import (
            compress_identity_tags,
            condense_clause,
            fit_to_budget,
        )

        # **Tiered, not flat.** `fit_to_budget` tests parts independently
        # against a running total, in list order -- so tier order here *is*
        # priority order, and it is the only thing enforcing it. Before this
        # fix all fields sat in one flat list (layout, action, setting,
        # lighting, *then* identity/condition, *then* mood/key_objects), and
        # measured directly on RI ch1's opening beats: the character's own
        # identity clause and the beat's torn-robes/blood condition clause
        # were dropped *entirely*, while setting and lighting tags placed
        # earlier in that flat list survived -- scene-critical content
        # losing to boilerplate scenery just because of list position, not
        # because it mattered less. Tier 0 (style/framing) is fixed
        # boilerplate the caller has already reserved budget for elsewhere
        # (`render_panels`'s `_prompt_limit` reserves `quality_prefix`; cast
        # tags are prepended by the caller). Tier 1 is identity + physical
        # condition -- decomposed into single-attribute fragments, not two
        # atomic clauses, specifically so a tight budget drops the least
        # essential *attribute* (or the reinforcement line) rather than the
        # entire clause; the character's name and a couple of core traits
        # survive even under real pressure. Tier 2 is what is happening and
        # its register. Tier 3 is where and when -- the first content cut
        # when the budget is tight, because it is real information but the
        # least essential in a genre where the character carries the panel.
        tier0: list[str] = [style_anchor(self.novel_id), framing]

        _director_text = f"{d.action or ''} {d.layout or ''}".lower()
        _has_white_robe = False
        _expression_placed = False
        tier1: list[str] = []
        for name, look in self.cast.items():
            # Check both action and layout: the director sometimes names the
            # character in layout ("Fang Yuan stands alone") while using a
            # pronoun in action ("He watches the enemies"). Either occurrence
            # is enough evidence the character is in frame.
            if name.lower() not in _director_text:
                continue
            # condense_clause strips headcount tags and picks which
            # attributes survive; compress_identity_tags controls how many
            # *words* each one costs -- "midnight black very long straight
            # hair down to the waist, cold and narrow eyes" (measured ~24
            # tokens alone) becomes "long_black_hair, cold_narrow_eyes"
            # (~8), which is what actually leaves tier 1 enough room for
            # tier 2 to survive instead of consuming the whole budget by
            # itself. See its docstring for the full rationale.
            compressed = compress_identity_tags(condense_clause(look))
            comp_tags = [t.strip() for t in compressed.split(",") if t.strip()]
            condition = self.conditions.get(name, "")
            cond_tags = [c.strip() for c in condition.split(",") if c.strip()] if condition else []
            # **Hair before eyes/build, within tier 1 itself.** condense_clause
            # re-emits survivors in the clause's *original* order (build,
            # then hair, then eyes, for this pipeline's own phrasing), not
            # rank order -- so without this split, a tight tier-1 cap would
            # trim hair (the single feature that makes a character
            # recognisable in silhouette, per condense_clause's own
            # docstring) before it trimmed build, which is backwards.
            # Condition/damage state is highest priority within tier 1
            # after the name and hair -- it is the one thing this session's
            # fix exists to guarantee actually shows up.
            hair_tags = [t for t in comp_tags if t.endswith("hair")]
            other_tags = [t for t in comp_tags if t not in hair_tags]
            tier1.append(name)
            tier1.extend(hair_tags)
            tier1.extend(cond_tags)
            # **Same priority tier as condition, right after it -- one tag,
            # once.** Placed inside the cast loop (not appended after it)
            # so it sits ahead of the eyes/build tags `fit_to_budget`
            # trims first, per this docstring's own priority-order
            # rationale. Guarded to fire once even when several named
            # characters share a beat: `expression` describes one face,
            # repeating it per cast member would spend budget for nothing.
            if d.expression and not _expression_placed:
                tier1.append(d.expression)
                _expression_placed = True
            if ("white" in condition.lower() and "robe" in condition.lower()) or ("white" in compressed.lower() and "robe" in compressed.lower()):
                _has_white_robe = True
            tier1.extend(other_tags)
        # **Section 4.4: an untracked figure's presence needs the same
        # tier-1 priority a named character's identity already gets.**
        # `tier1` stays empty whenever no cast member's name matches the
        # director's text -- true for any subject with no resolved
        # persona/reference sheet (e.g. "the clan head" in RI ch1 block 75,
        # who has no tracked entity). The only subject-presence content for
        # that beat was `d.layout`'s own "a figure" marker, stuck in tier 3
        # behind setting/lighting -- exactly the environment-over-subject
        # imbalance the real block-75 render showed (a rendered background
        # with no person in it). Promoting the bare marker into tier 1 when
        # there is otherwise nothing there costs at most a couple of
        # tokens and guarantees *some* subject-presence content survives
        # budget pressure ahead of scenery, mirroring `cast_tags`'s own
        # silhouette fallback for the same "a figure" signal.
        if not tier1 and "a figure" in _director_text:
            tier1.append("a figure")
        if _has_white_robe:
            # Reinforce white robe colour when the character appearance calls
            # for it. Measured v38: negative suppression of teal shifted the
            # model to dark charcoal (the checkpoint's next preferred
            # colour) rather than white.
            tier1.append("pure white outer robe")
        # **Hard cap, as a backstop -- not the primary mechanism.**
        # Compression is what should keep tier 1 small; this exists for a
        # character whose canon distinguishing-features list is long enough
        # to blow the budget even compressed. `fit_to_budget` drops from the
        # *end* of the list first, which is exactly the eyes/build tags
        # appended last above -- name, hair and condition survive a cap
        # that has to cut something.
        tier1 = fit_to_budget(tier1, limit=24).split(", ") if tier1 else tier1

        tier2: list[str] = []
        if d.action:
            tier2.append(d.action)
        # Quality tags in tier 2, not tier 1: they used to sit right after
        # the character clause specifically to outlive scene content, which
        # is the opposite of what this tiering now guarantees on purpose.
        tier2.append("score_9, score_8_up, highly detailed, cinematic lighting")
        if d.key_objects:
            tier2.append(", ".join(str(o) for o in d.key_objects if o))
        if d.mood:
            tier2.append(f"{d.mood} mood")

        tier3: list[str] = []
        if d.layout:
            tier3.append(d.layout)
        if d.setting:
            tier3.append(d.setting)
        if d.lighting:
            tier3.append(d.lighting)
        if world_context:
            # **The novel's own visual signature, grounded in its text --
            # see `persona/attire.py::WORLD_CONTEXT` for the citation
            # trail.** Ranked between the director's own setting and the
            # generic locale rotation: it is more specific than
            # `scene_locale`'s block-index fallback (which knows nothing
            # about this particular novel beyond a scenery word list), but
            # never displaces what the director actually extracted from
            # the beat itself. This is what stops an empty-cast beat --
            # the case with the most budget headroom, and measured as the
            # case that most needed it -- from defaulting to whatever
            # genre-typical prop the checkpoint's own prior fills in.
            tier3.append(world_context)
        if scene_locale:
            # Scene-level location anchor: same string for every panel in
            # the scene, so consecutive panels don't render as different
            # places. Lowest priority in tier 3: it supplements the
            # director's own setting when there is room, never displaces it.
            tier3.append(scene_locale)

        from echotales.pipeline.persona.attire import setting_first

        if setting_first(self.novel_id):
            # **Where and with what, before mood and the quality boilerplate.** The tiering above puts the place last
            # because on Reverend Insanity the character carries the panel. On LotM it threw away the room, the low
            # wooden bed and the revolver, which were the beat (2026-10-18 render review: 22 of 73 prompts named any
            # place at all). `score_9, score_8_up` is dropped from the prompt because the engine already prepends it
            # as its `quality_prefix`; the duplicate cost about 8 of the ~70 tokens. Everything is still subject to
            # `fit_to_budget` in list order, so this changes what is cut, not how much is kept.
            action = [d.action] if d.action else []
            objects = [", ".join(str(o) for o in d.key_objects if o)] if d.key_objects else []
            place = [t for t in tier3 if t != d.layout]
            layout = [d.layout] if d.layout else []
            mood = [f"{d.mood} mood"] if d.mood else []
            return [*tier0, *tier1, *action, *objects, *place, *layout, *mood, "highly detailed"]
        return [*tier0, *tier1, *tier2, *tier3]


#: Words that say where a scene is or when. Generic on purpose: no genre, no book.
_PLACE_WORDS = frozenset(
    ["room", "bedroom", "bed", "door", "window", "floor", "wall", "ceiling", "roof", "stairs", "staircase", "corridor", "hallway", "hall", "house", "cottage", "kitchen", "cabinet", "drawer", "drawers", "desk", "table", "chair", "shelf", "shelves", "mirror", "curtain", "fireplace", "lamp", "candle", "street", "road", "alley", "square", "courtyard", "garden", "yard", "gate", "bridge", "shop", "tavern", "inn", "church", "chapel", "cathedral", "station", "platform", "carriage", "cave", "forest", "field", "river", "shore", "beach", "mountain", "cliff", "village", "town", "city", "tower", "castle", "cellar", "attic", "office", "apartment", "elevator", "lobby", "tunnel", "subway"]
)
_TIME_WORDS = frozenset(
    ["night", "midnight", "dawn", "dusk", "sunset", "sunrise", "evening", "morning", "afternoon", "noon", "moonlight", "sunlight", "starlight", "candlelight", "gaslight", "lamplight", "darkness", "dark", "dim", "rain", "snow", "fog", "mist", "storm"]
)


def scene_setting_note(passages: list[str], *, max_chars: int = 420) -> str:
    """The sentences of a scene that say where it is and when, for the director's "what the story knows" brief.

    The director sees one beat's passage at a time, so the room described in block 30 was invisible when block 8
    was drawn, and every panel of the scene got its own setting (the 2026-10-18 LotM render: a bedroom scene drawn
    on grass, in a study, in front of a mirror). Taken from the whole scene, not only what precedes the beat: this is
    a rendering of the chapter's pictures, not an answer to "what does the reader know here". Sentences are ranked by
    how many place and time words they hold; the best few are kept, in reading order, within `max_chars`.
    """
    import re

    scored: list[tuple[int, int, str]] = []
    order = 0
    for passage in passages:
        for sentence in re.split(r"(?<=[.!?])\s+", passage.strip()):
            words = set(re.findall(r"[a-z]+", sentence.lower()))
            score = len(words & _PLACE_WORDS) + len(words & _TIME_WORDS)
            if score and len(sentence) > 12:
                scored.append((score, order, sentence.strip()))
            order += 1
    chosen: list[tuple[int, str]] = []
    used = 0
    for _score, idx, sentence in sorted(scored, key=lambda t: (-t[0], t[1])):
        if used + len(sentence) + 1 > max_chars:
            continue
        chosen.append((idx, sentence))
        used += len(sentence) + 1
    return " ".join(sentence for _idx, sentence in sorted(chosen))


def direct_beat(
    beat_text: str,
    *,
    cast: dict[str, str],
    novel_style: str,
    client: object,
    novel_id: str = "",
    context_brief: str = "",
    store: Store | None = None,
    conditions: dict[str, str] | None = None,
    crowd_mood: str | None = None,
    recent_shots: list[str] | None = None,
    staging: str = "",
    spoken: str = "",
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
                recent_shots=recent_shots,
                staging=staging,
                spoken=spoken,
            ),
            PanelDirection,
            system=system_prompt(novel_id),
            novel_id=novel_id,
        )
    except Exception as exc:
        log.warning("panel direction failed: %s", exc)
        return None

    from echotales.pipeline.render.staging import expression_conflicts, place_conflicts

    def _again(note: str) -> PanelDirection | None:
        """One corrective retry with the reason named; None when the call fails."""
        try:
            retry = client.complete(  # type: ignore[attr-defined]
                Task.PANEL_DIRECTION,
                build_prompt(beat_text, cast=cast, novel_style=novel_style, context_brief=context_brief,
                             recent_shots=recent_shots, staging=staging, spoken=spoken) + "\n" + note,
                PanelDirection, system=system_prompt(novel_id), novel_id=novel_id,
            )
        except Exception as exc:
            log.warning("director retry failed: %s", exc)
            return None
        retry.value.staging = staging
        return _validate_direction(retry.value, beat_text=beat_text, cast=cast, novel_id=novel_id, store=store,
                                   crowd_mood=crowd_mood)

    direction = result.value
    direction.staging = staging
    direction = _validate_direction(
        direction, beat_text=beat_text, cast=cast, novel_id=novel_id, store=store, crowd_mood=crowd_mood,
    )
    if not direction.composition and direction.grounding_rejects:
        # A blanked paragraph drops the panel to the structured-tag fallback, which drew nothing of the line (gemma2:9b on RI
        # ch1: 7 of 9 paragraphs blanked, mostly for "a lone figure" in a scene with a crowd). Name the fault and ask once more.
        fixed = _again(
            "Your previous paragraph was rejected: " + "; ".join(direction.grounding_rejects) + ". Rewrite it. Never write "
            "'alone' or 'a lone figure' while others are in the scene (put them in rows on their side of the frame, or just "
            "outside it), and name only people in CAST exactly as written."
        )
        if fixed is not None and fixed.composition:
            fixed.grounding_rejects = [*direction.grounding_rejects, "retried"]
            direction = fixed
    if direction.composition and (
        reason := expression_conflicts(f"{direction.expression}. {direction.composition}", f"{beat_text} {context_brief}")
    ):
        # A mocking laugh drawn as a happy grin (owner, 2026-11-19): one retry with the contradiction named, then flag.
        fixed = _again("Your previous faces read as happy on a hostile line. Rewrite them as cold, mocking or contemptuous "
                       "as the situation requires.")
        if fixed is not None and fixed.composition and not expression_conflicts(
            f"{fixed.expression}. {fixed.composition}", f"{beat_text} {context_brief}"
        ):
            fixed.grounding_rejects = [*fixed.grounding_rejects, "expression retried"]
            direction = fixed
        else:
            direction = direction.model_copy(update={"grounding_rejects": [*direction.grounding_rejects, reason]})
    if direction.composition and (bad := place_conflicts(direction.composition, staging, f"{beat_text} {context_brief}")):
        # The paragraph put the scene somewhere the staging sheet and the text do not: one retry naming the words, else flag.
        fixed = _again(f"Your paragraph names places the scene does not have: {', '.join(bad)}. The place is only what the SCENE STAGING "
                       "says; rewrite the paragraph without them.")
        if fixed is not None and fixed.composition and not place_conflicts(fixed.composition, staging, f"{beat_text} {context_brief}"):
            fixed.grounding_rejects = [*fixed.grounding_rejects, "place retried"]
            direction = fixed
        else:
            direction = direction.model_copy(update={
                "composition": drop_place_conflicts(direction.composition, bad),
                "grounding_rejects": [*direction.grounding_rejects, "place:" + ",".join(bad)]})
    return Direction(
        direction=direction, cast=cast, novel_style=novel_style, conditions=conditions or {},
        novel_id=novel_id,
    )


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


#: HANDOFF Section 4.48 root cause 2, measured: 36/52 v39 prompts contained
#: one of these when the director over-applied "never invent people" to a
#: scene the source text explicitly describes as a crowd (the 500+-member
#: Awakening Ceremony chief among them).
_SOLO_COLLAPSE_PHRASES: tuple[str, ...] = (
    "stands alone",
    "stand alone",
    "no one else is present",
    "no one else present",
    "alone in the frame",
    # Danbooru-tag form, not prose: `direction.py`'s own SYSTEM instruction
    # (below, "If CAST is empty...") tells the director to write these
    # literal tags when the cast is unresolved, so a real director output
    # is far more likely to say "standing_alone"/"solo" than any of the
    # prose phrases above -- confirmed on a real chapter-1 render, where
    # this prose-only list let a genuine crowd/solo contradiction through.
    "standing_alone",
    "solo",
)


def _layout_contradicts_crowd(direction: PanelDirection, crowd_mood: str | None) -> bool:
    """True when `SceneState` independently confirms this scene is a crowd
    scene, but the director's own `layout` erases everyone from it anyway.

    Fires only when `crowd_mood == "crowd"` -- `SceneState`'s own
    `detect_mobs`-backed signal, not a guess from this field's own text --
    so a genuinely solo scene can never trip this check.
    """
    if crowd_mood != "crowd":
        return False
    text = (direction.layout or "").lower()
    if not any(p in text for p in _SOLO_COLLAPSE_PHRASES):
        return False
    # If layout already names a group noun, it isn't actually erasing the
    # crowd -- e.g. "elders surround him" mentioning "alone in the frame"
    # as a *negation* would be an odd false positive this guards against.
    return not any(noun in text for noun in _MOB_ROLE_NOUNS)


def _rewrite_layout_for_crowd(direction: PanelDirection) -> str:
    """Mechanically strip the solo-collapse phrase and append a crowd
    clause, rather than re-querying the LLM -- the same model that erased
    the crowd once has no guarantee of fixing it on retry, while a
    deterministic rewrite using data already computed elsewhere in the
    render path is cheap and testable without an LLM in the loop.

    Strips the offending phrase first: appending a crowd clause *alongside*
    "stands alone" would leave both assertions in the final prompt string,
    which is the same self-contradiction this check exists to fix, only
    with an extra clause bolted on rather than resolved.
    """
    layout = direction.layout or ""
    low = layout.lower()
    for phrase in _SOLO_COLLAPSE_PHRASES:
        idx = low.find(phrase)
        if idx == -1:
            continue
        layout = layout[:idx] + layout[idx + len(phrase) :]
        low = layout.lower()
    # Clean up whatever punctuation the removed phrase leaves dangling
    # (a leading/trailing "; ", doubled "; ;", etc.) before appending.
    layout = re.sub(r"[;,]\s*[;,]", ";", layout)
    layout = layout.strip(" ;,")
    clause = "figures fill the scene around him"
    return f"{layout}; {clause}".strip("; ").strip() if layout else clause


def _layout_invents_second_subject(direction: PanelDirection, crowd_mood: str | None) -> bool:
    """Text-prompt-level check only -- this cannot see the rendered pixels,
    so it cannot catch a checkpoint that ignores a clean solo prompt and
    paints a second figure anyway (the `p001_b0000.png` failure mode). It
    confirms the *prompt itself* never asserts or implies two figures when
    `SceneState` says the scene is not a crowd: True when `layout`/`action`
    together mention more than one distinct named-or-generic figure while
    `crowd_mood` is not "crowd"."""
    if crowd_mood == "crowd":
        return False
    text = f"{direction.action or ''} {direction.layout or ''}".lower()
    figure_mentions = text.count("a figure") + text.count("another figure")
    return figure_mentions > 1


def _validate_direction(
    d: PanelDirection,
    *,
    beat_text: str,
    cast: dict[str, str],
    novel_id: str = "",
    store: Store | None = None,
    crowd_mood: str | None = None,
) -> PanelDirection:
    """Post-call guardrails that catch what the prompt rules could not.

    Five checks:
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
    4. Crowd/layout contradiction (Section 4.1): `SceneState.crowd_mood`
       says this scene is a crowd scene, but layout erases everyone from
       frame -- mechanically rewritten rather than blanked, since blanking
       would just fall back to the same mechanical assembler that already
       has its own crowd-slot handling and lose the director's real
       action/mood content for the beat.
    5. Invented second subject (Section 4.1 extension): the inverse case --
       `SceneState.crowd_mood` says this is not a crowd scene, but
       layout/action still imply two figures. Logged, not corrected: unlike
       the crowd case there is no single mechanical rewrite that reliably
       picks the *right* one figure to keep, so this is flagged for the
       pixel-review pass (Section 5) rather than silently patched.
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

    # Director v2 lists: the same "cast-only names, never invent people" rules the prompt states for action/layout. A
    # name outside CAST would otherwise reach `brief_from_direction` as an extra, unresolvable figure.
    if d.characters:
        cast_keys = {n.casefold() for n in cast}
        kept = [c for c in d.characters if c.name.casefold() in cast_keys or any(
            c.name.casefold() in k.split() for k in cast_keys)]
        if len(kept) != len(d.characters):
            log.warning("director listed characters outside CAST: %r -- dropped",
                        [c.name for c in d.characters if c not in kept])
            d = d.model_copy(update={"characters": kept})
    if d.others is not None and _has_hallucinated_group(d.others.kind or ""):
        log.warning("director hallucinated group in others: %r -- dropped", d.others.kind)
        d = d.model_copy(update={"others": None})

    d = _validate_composition(d, beat_text=beat_text, cast=cast, novel_id=novel_id, store=store, crowd_mood=crowd_mood)

    # Literal placeholder the model copies from the layout example -- either
    # the old sentence form ("X alone") or the tag form ("X, surrounded" /
    # a bare "X" tag in the comma list).
    if re.search(r"\bX\s+(alone|stands|is\b)", d.layout or "", re.IGNORECASE) or re.search(
        r"(^|,)\s*X\s*(,|$)", d.layout or ""
    ):
        log.warning("director used literal 'X' placeholder in layout: %r -- blanked", d.layout)
        d = d.model_copy(update={"layout": ""})

    # Character name validation
    if store and novel_id:
        _validate_character_names(d, cast, novel_id, store)

    # Crowd/layout contradiction (Section 4.1): SceneState confirms a crowd,
    # director's own layout erased it anyway.
    if _layout_contradicts_crowd(d, crowd_mood):
        log.warning(
            "director erased a SceneState-confirmed crowd in layout: %r -- rewritten",
            d.layout,
        )
        d = d.model_copy(update={"layout": _rewrite_layout_for_crowd(d)})

    # Invented second subject (Section 4.1 extension): flagged only, see
    # this check's own docstring for why it isn't auto-corrected.
    if _layout_invents_second_subject(d, crowd_mood):
        log.warning(
            "director's layout/action implies a second figure on a "
            "SceneState-confirmed non-crowd scene: action=%r layout=%r",
            d.action, d.layout,
        )

    return d


_ITEM_OF = re.compile(r"\bof\s+$", re.I)
_ITEM_HELD = re.compile(
    r"\b(?:his|her|their|its|the|a|an|with|holds?|holding|wields?|wielding|draws?|raises?|grips?|gripping|carr(?:y|ies|ying)|"
    r"clutch\w*)\s+$", re.I)


def _replace_fabricated(text: str, start: int, length: int, who: str) -> str:
    """Put `who` where a name the story never says stood, unless the name sits where an object goes.

    A name after "of", "his", "a" or a holding verb is an item the model named (the Gu worm "Spring Autumn Cicada" became "a
    vial of Fang Yuan" and "holds his Fang Yuan in one hand" in the RI rebirth panels, round 3): the lead's name there corrupted the
    prompt, so "of <name>" is dropped and any other object position becomes "a small object"."""
    before, after = text[:start], text[start + length:]
    if _ITEM_OF.search(before):
        return _ITEM_OF.sub("", before).rstrip() + after
    held = _ITEM_HELD.search(before)
    if held:
        verb_like = held.group(0).strip().lower() in ("with", "a", "an", "the", "his", "her", "their", "its")
        head = before[: held.start()] + (before[held.start():held.end()] if not verb_like or held.group(0).strip().lower() == "with" else "")
        return head + "a small object" + after
    return before + who + after


def _validate_composition(
    d: PanelDirection, *, beat_text: str, cast: dict[str, str], novel_id: str, store: Store | None, crowd_mood: str | None,
) -> PanelDirection:
    """Ground the composed paragraph in the passage: no invented people, groups or names, and the crowd stays a crowd.

    A paragraph is long enough that the field checks written for tag strings fire wrongly on it (every capitalised
    sentence start looks like a name), so this works on the paragraph: a named person outside CAST becomes "a figure", a
    capitalised name the passage never says is replaced the same way, and an invented group or a paragraph that empties a
    confirmed crowd is blanked so the compiler falls back to the structured fields instead of drawing it."""
    visual = d.visual_source.strip().lower()
    updates: dict[str, object] = {"visual_source": visual if visual in ("text", "inferred") else "text"}
    text = (d.composition or "").strip()
    rejects: list[str] = []
    if text:
        # The director's own "a lone figure" next to the one person it could be, before the name checks below put a "a figure" of
        # their own (a real out-of-cast person) into the paragraph: that one must stay a second person.
        text, figs = scrub_unstated(text, allowed=f"{beat_text} {d.staging} {' '.join(cast)}",
                                    lead=next(iter(cast)) if len(cast) == 1 else "", sky=False)
        rejects.extend(figs)
    if text:
        source = beat_text.lower() + " " + " ".join(cast).lower()
        group = _HALLUCINATED_GROUP_RE.search(text)
        if group is not None and group.group(0).lower() not in source:
            rejects.append(f"group:{group.group(0)}")
            text = ""
        elif crowd_mood and any(p in text.lower() for p in _SOLO_COLLAPSE_PHRASES):
            rejects.append("crowd erased")
            text = ""
        else:
            cast_names = {n.lower() for n in cast}
            cast_words = {w for n in cast_names for w in n.split()}
            known: dict[str, str | None] = {}
            if store is not None and novel_id:
                for entity in store.all_selves(novel_id):
                    if entity.canonical_label:
                        known[entity.canonical_label.lower()] = entity.id
            for name in sorted(known, key=len, reverse=True):
                if name in cast_names or not re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
                    continue
                rejects.append(f"out of cast:{name}")
                text = re.sub(rf"\b{re.escape(name)}\b", "a figure", text, flags=re.IGNORECASE)
            from echotales.pipeline.mentions.ner import HeuristicDetector

            for span in sorted(HeuristicDetector().detect(text), key=lambda s: -s.start):
                bare = re.sub(r"[’']s$", "", span.text)
                low = bare.lower()
                words = low.split()
                if low in cast_names or all(w in cast_words or w in source for w in words):
                    continue
                at_sentence_start = span.start == 0 or text[: span.start].rstrip().endswith((".", "!", "?"))
                if len(words) == 1 and at_sentence_start:
                    continue
                rejects.append(f"fabricated:{bare}")
                # With one person in CAST a name the story never says is almost always that person misspelt ("Zhou Yuan" for Zhou
                # Mingrui, LotM ch1 block 24); "a figure" drew a second, unnamed person beside him, and the scene's crimson light
                # made that figure glow red. Only when the paragraph does not already name him.
                lone = next(iter(cast)) if len(cast) == 1 else ""
                who = lone if lone and lone.lower() not in text.lower() else "a figure"
                text = _replace_fabricated(text, span.start, len(bare), who)
    if text:
        text, scrubbed = scrub_unstated(text, allowed=f"{beat_text} {d.staging} {' '.join(cast)}", lead="")
        rejects.extend(scrubbed)
    updates["composition"] = text
    allowed_all = f"{beat_text} {d.staging} {' '.join(cast)}"
    props, objects = unstated_weapon_props(list(d.props), allowed_all), unstated_weapon_props(list(d.key_objects), allowed_all)
    if len(props) != len(d.props) or len(objects) != len(d.key_objects):
        rejects.append("weapon prop not in the text")
        updates["props"], updates["key_objects"] = props, objects
    updates["grounding_rejects"] = rejects
    return d.model_copy(update=updates)


# An unnamed person the paragraph adds beside the named lead. gemma2:9b opened 6 of 13 RI cliff paragraphs with "A lone figure stands
# on the mountaintop ..." and the picture grew a silhouetted figure on a distant cliff top in 9 of 13 (round 3, EVOLUTION 4.171).
_FIGURE_RE = re.compile(
    r"\b(?:a|an|the|one)\s+(?:(?:lone|solitary|single|distant|small|tiny|dark|shadowy|silhouetted|mysterious|faint|hooded|cloaked|"
    r"robed|solitary)\s+){0,2}(?:figure|silhouette|stranger|shape)\b", re.I)

#: Sky and weather families: (name, how the paragraph words it, how the passage or staging may word it). A paragraph's sky that
#: neither states is the model's own: the rebirth room was lit "by moonlight" while the sheet said rain (a full moon in heavy rain).
_SKY: list[tuple[str, re.Pattern[str], re.Pattern[str]]] = [
    ("sun", re.compile(r"\b(?:sun|sunset|sunrise|sunlight|sundown|setting sun|rising sun)\b", re.I),
     re.compile(r"\b(?:sun\w*|dusk|dawn|twilight|evening|morning|noon|daylight|afternoon|day)\b", re.I)),
    ("moon", re.compile(r"\b(?:moon\w*|full moon|crescent)\b", re.I), re.compile(r"\bmoon\w*\b", re.I)),
    ("stars", re.compile(r"\b(?:stars?|starry|starlit|starlight)\b", re.I), re.compile(r"\b(?:stars?|starry|starlit|starlight)\b", re.I)),
    ("rain", re.compile(r"\b(?:rain\w*|drizzl\w*|downpour|raindrops?)\b", re.I), re.compile(r"\b(?:rain\w*|drizzl\w*|downpour|storm\w*)\b", re.I)),
    ("snow", re.compile(r"\b(?:snow\w*|blizzard|frost\w*)\b", re.I), re.compile(r"\b(?:snow\w*|blizzard|frost\w*|winter)\b", re.I)),
    ("storm", re.compile(r"\b(?:storm\w*|thunder\w*|lightning)\b", re.I), re.compile(r"\b(?:storm\w*|thunder\w*|lightning)\b", re.I)),
    ("mist", re.compile(r"\b(?:fog\w*|mist\w*|haze|hazy)\b", re.I), re.compile(r"\b(?:fog\w*|mist\w*|haze|hazy|cloud\w*)\b", re.I)),
    ("silhouette", re.compile(r"\bsilhouett\w*", re.I), re.compile(r"\bsilhouett\w*", re.I)),
]
_SEG_SPLIT = re.compile(r"(,\s*|;\s*|\s+(?:as|while|under|beneath|against|lit by|bathed in|with|and|casting)\s+)")
_TRAILING_PREP = re.compile(r"^(?:against|under|beneath|above|over|in)\b", re.I)


def _drop_segments(sentence: str, cue: re.Pattern[str]) -> str:
    """The sentence without the comma, 'as' or preposition segments that match `cue` (and a preposition segment right after one);
    '' when nothing of it is left."""
    parts = _SEG_SPLIT.split(sentence)
    segs = [("", parts[0])] + [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    kept: list[tuple[str, str]] = []
    dropped_last = False
    for delim, seg in segs:
        dropped_last = bool(cue.search(seg)) or (dropped_last and bool(_TRAILING_PREP.match(seg.strip())))
        if not dropped_last:
            kept.append((delim, seg))
    if not kept:
        return ""
    text = "".join(seg if j == 0 else delim + seg for j, (delim, seg) in enumerate(kept)).strip(" ,;")
    # What is left must still be a sentence: "The mountaintop is" (its moon clause cut) or a 3-word stub is dropped whole.
    if len(text.split()) < 5 or re.search(r"\b(?:is|are|was|were|be|been|being|in|on|by|with|of|the|a|an|and|as|while|at|to|from)$", text, re.I):
        return ""
    if kept[0] != segs[0]:  # the opening segment went ("Under the pale moon, Fang smirks."): the next one opens the sentence
        text = text[:1].upper() + text[1:]
    return text + ("." if sentence.rstrip().endswith(".") and not text.endswith(".") else "")


_WEAPON_RE = re.compile(r"\b(sword|blade|dagger|knife|spear|axe|halberd|saber|sabre|rapier|bow|arrow|gun|revolver|pistol|rifle|musket|cannon)s?\b", re.I)


def unstated_weapon_props(items: list[str], allowed: str) -> list[str]:
    """`items` without any prop that names a weapon the passage and staging never name."""
    low = allowed.lower()
    keep = []
    for item in items:
        m = _WEAPON_RE.search(item)
        if m is None or re.search(rf"\b{re.escape(m.group(1).lower())}", low):
            keep.append(item)
    return keep


def drop_place_conflicts(text: str, bad: list[str]) -> str:
    """The paragraph without the clauses that name a place the staging sheet does not have. A retry that still wrote "a dark damp
    cave" against a staged mountaintop only flagged it (round 4), so the cave reached the prompt."""
    if not bad:
        return text
    cue = re.compile(r"\b(?:" + "|".join(re.escape(b) for b in bad) + r")s?\b", re.I)
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        if cue.search(sent):
            sent = _drop_segments(sent, cue)
        if sent:
            out.append(sent)
    return " ".join(out)


def scrub_unstated(text: str, *, allowed: str, lead: str, sky: bool = True) -> tuple[str, list[str]]:
    """Remove from the director's paragraph an unnamed extra person and any sky or weather that neither the passage nor the
    staging sheet (`allowed`) states. Returns the new text and one reject label per fault.

    An unstated "a lone figure" next to a named lead is that lead (renamed); an unstated silhouette, moon, sun or rain is cut out
    with only its own clause, so the faces and wounds around it survive. Conservative on purpose: an object the text states is
    never touched, and with no lead named a figure is left alone (it may be the CAST-free scenery shot's own subject)."""
    rejects: list[str] = []
    low_allowed = allowed.lower()
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if lead and not re.search(r"\b(?:figure|silhouette|stranger|shape)\b", low_allowed):
        fixed: list[str] = []
        for sent in sentences:
            def _who(m: re.Match[str], _sent: str = sent) -> str:
                rejects.append(f"figure:{m.group(0).lower()}")
                return lead
            fixed.append(_FIGURE_RE.sub(_who, sent))
        sentences = fixed
    out_sentences: list[str] = []
    for sent in sentences:
        # A held or worn weapon the passage never names is the model's prior for the genre (RI cliff r4: a sword in the hand or at
        # the hip in 5 of 13 panels, the text gave him none). Only the clause is cut.
        for m in _WEAPON_RE.finditer(sent):
            word = m.group(1).lower()
            if sent and not re.search(rf"\b{re.escape(word)}", low_allowed):
                cleaned = _drop_segments(sent, re.compile(rf"\b{re.escape(word)}", re.I))
                tag = f"weapon:{word}"
                if tag not in rejects:
                    rejects.append(tag)
                sent = cleaned
        if not sent:
            continue
        for name, in_text, in_allowed in (_SKY if sky else []):
            if in_text.search(sent) and not in_allowed.search(allowed):
                cleaned = _drop_segments(sent, in_text)
                tag = f"sky:{name}"
                if tag not in rejects:
                    rejects.append(tag)
                sent = cleaned
                if not sent:
                    break
        if sent:
            out_sentences.append(sent)
    return " ".join(out_sentences), rejects


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


@dataclass(slots=True)
class DirectionConservationAudit:
    """Audit comparing what the text stated against what the director preserved."""

    captured_people: list[str] = field(default_factory=list)
    dropped_people: list[str] = field(default_factory=list)
    captured_places: list[str] = field(default_factory=list)
    dropped_places: list[str] = field(default_factory=list)
    captured_props: list[str] = field(default_factory=list)
    dropped_props: list[str] = field(default_factory=list)

    @property
    def total_captured(self) -> int:
        return len(self.captured_people) + len(self.captured_places) + len(self.captured_props)

    @property
    def total_dropped(self) -> int:
        return len(self.dropped_people) + len(self.dropped_places) + len(self.dropped_props)

    @property
    def conservation_rate(self) -> float:
        total = self.total_captured + self.total_dropped
        return (self.total_captured / total) if total > 0 else 1.0


#: Genre-neutral nouns on top of the xianxia ones: the audit was written against RI, so a Regency drawing room or a
#: letter on a table was never counted as captured or dropped and the conservation rate read 1.0 for P&P.
#: Multi-word entries come first so "drawing room" is one place, not "room".
_COMMON_PLACE_KEYWORDS = re.compile(
    r"\b(drawing\s*room|dining\s*room|cliff|mountain|peak|hall|room|cave|courtyard|pavilion|forest|lake|river|village|street|terrace|chamber|palace|path|gate|ruins|bridge|altar|shrine"
    r"|parlou?r|ballroom|garden|library|study|kitchen|bedroom|staircase|corridor|church|inn|lane|road|park|field|house|cottage|window|doorway|balcony|shop|market|harbou?r|beach|city|town)\b",
    re.IGNORECASE,
)
_COMMON_PROP_KEYWORDS = re.compile(
    r"\b(sword|blade|talisman|lantern|scroll|tea\s*cup|jar|carriage|cicada|stone|ring|fan|pill|gu|mirror|spear|bow|dagger|chain"
    r"|letter|book|table|fire|horse|candle|chair|piano|umbrella|newspaper|bonnet|handkerchief|basket|pistol|revolver|key|lamp|cup|bottle|glass|coat|hat)\b",
    re.IGNORECASE,
)


def check_direction_conservation(
    beat_text: str,
    direction: PanelDirection,
    cast_names: list[str] | None = None,
) -> DirectionConservationAudit:
    """Audit whether people, places, and props in beat_text were captured or dropped in direction."""
    text_lower = beat_text.lower()

    # 1. People
    target_names = [n for n in (cast_names or []) if n.lower() in text_lower]
    mob_nouns = ["elders", "disciples", "guards", "crowd", "warriors", "soldiers", "enemies"]
    for m in mob_nouns:
        if m in text_lower and m not in target_names:
            target_names.append(m)

    dir_people_text = (
        " ".join(c.name for c in direction.characters)
        + " " + (direction.others.kind if direction.others else "")
        + " " + direction.layout + " " + direction.action
    ).lower()

    captured_people = []
    dropped_people = []
    for p in target_names:
        if p.lower() in dir_people_text:
            captured_people.append(p)
        else:
            dropped_people.append(p)

    # 2. Places
    found_places = list(set(_COMMON_PLACE_KEYWORDS.findall(text_lower)))
    dir_setting_text = (
        direction.setting + " " + direction.location_detail + " " + direction.layout
    ).lower()
    captured_places = []
    dropped_places = []
    for place in found_places:
        if place.lower() in dir_setting_text:
            captured_places.append(place)
        else:
            dropped_places.append(place)

    # 3. Props
    found_props = list(set(_COMMON_PROP_KEYWORDS.findall(text_lower)))
    all_props = list(direction.key_objects) + list(direction.props) + [direction.action]
    dir_props_text = " ".join(all_props).lower()
    captured_props = []
    dropped_props = []
    for prop in found_props:
        if prop.lower() in dir_props_text:
            captured_props.append(prop)
        else:
            dropped_props.append(prop)

    return DirectionConservationAudit(
        captured_people=captured_people,
        dropped_people=dropped_people,
        captured_places=captured_places,
        dropped_places=dropped_places,
        captured_props=captured_props,
        dropped_props=dropped_props,
    )


def enforce_shot_variety(directions: list[PanelDirection]) -> list[PanelDirection]:
    """Enforce the shot-variety rule: no two consecutive panels share the same shot size and subject.

    When two consecutive panels share the same shot size (e.g. medium, medium) and the same
    primary subject (e.g. Fang Yuan, Fang Yuan):
    - If the shot is 'medium', alternate to 'close' (if there is dialogue/expression/props) or 'wide'.
    - If the shot is 'close', alternate to 'medium'.
    - If the shot is 'wide', alternate to 'medium'.
    Also alternates camera angles if consecutive panels share the same camera angle on the same subject.
    """
    if len(directions) <= 1:
        return directions

    angles = ["eye-level", "low-angle", "high-angle"]
    out: list[PanelDirection] = []

    def _subject(d: PanelDirection) -> str:
        if d.characters:
            return d.characters[0].name.lower()
        if d.others or "crowd" in d.layout.lower():
            return "crowd"
        words = re.findall(r"[a-zA-Z]+(?:\s+[a-zA-Z]+)?", d.layout)
        return words[0].lower() if words else "scenery"

    for i, d in enumerate(directions):
        if i == 0:
            out.append(d)
            continue
        prev = out[-1]
        prev_sub = _subject(prev)
        curr_sub = _subject(d)

        d_copy = d.model_copy()

        # Check shot size and subject collision
        if d_copy.shot == prev.shot and curr_sub == prev_sub:
            if d_copy.shot == "medium":
                if d_copy.expression or d_copy.key_objects or d_copy.props:
                    d_copy.shot = "close"
                else:
                    d_copy.shot = "wide"
            elif d_copy.shot == "close":
                d_copy.shot = "medium"
            elif d_copy.shot == "wide":
                d_copy.shot = "medium"

        # Also check camera angle collision on same subject
        if d_copy.camera_angle == prev.camera_angle and curr_sub == prev_sub:
            curr_idx = angles.index(d_copy.camera_angle) if d_copy.camera_angle in angles else 0
            d_copy.camera_angle = angles[(curr_idx + 1) % len(angles)]

        out.append(d_copy)

    return out

