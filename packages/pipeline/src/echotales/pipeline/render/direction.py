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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from echotales.pipeline.spans.scene import _MOB_ROLE_NOUNS

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

    "8. No film vocabulary. No 'close-up on', 'the shot' pans', 'into the camera'.\n\n"

    "9. FACIAL EXPRESSION IS INDEPENDENT OF PHYSICAL CONDITION. A wounded, "
    "bleeding, or exhausted character does not default to a pained "
    "expression -- report the face only as the passage actually states it, "
    "as one short tag ('calm_expression', 'blank_stare', 'pained_expression', "
    "'unmoved'), separate from wounds/blood/torn clothes. If the passage "
    "explicitly states the character's expression does NOT change, or stays "
    "calm/blank/unreadable despite what is happening to them, that contrast "
    "is exactly what to report -- it is real information, not a contradiction "
    "to resolve. If the passage says nothing about the face, leave this "
    "empty; do not infer one from the body's condition.\n\n"

    "10. OUTPUT TAGS, NOT SENTENCES. This checkpoint (NoobAI/Illustrious) is "
    "trained on Danbooru-style tag captions, not narrative English -- a "
    "controlled comparison on this novel measured tag-style prompts "
    "rendering the actual described action (torn clothes, blood, a crowd "
    "surrounding the subject) where narrative sentences describing the "
    "identical content rendered an unrelated calm scene, every time. Every "
    "field below is a short, comma-separated list of tags: lowercase, "
    "underscores for multi-word concepts, no articles ('a', 'the'), no "
    "conjugated verbs, no connecting words ('and', 'while', 'as'), no "
    "periods. Example tags: surrounded, weapons_drawn, fighting_stance, "
    "standing_alone, kneeling, running, torn_clothes, blood, disheveled, "
    "wounded, bruised, exhausted, mountain_background, stone_courtyard, "
    "siege, misty_hills, dusk, night. Do not include numeric headcount tags "
    "('1boy', '2boys', 'male focus') -- those are added separately. A "
    "character's name is the one exception to snake_case: write it exactly "
    "as given in CAST, with its normal spacing and capitalization ('Fang "
    "Yuan', not 'fang_yuan')."
)


class PanelDirection(BaseModel):
    """One shot, as the director specifies it."""

    #: "wide" | "medium" | "close" -- framing, in the storyboard sense.
    shot: str = Field(default="medium")
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
    #: Time of day / weather / light, as tags (e.g. "dusk, misty").
    lighting: str = Field(default="")
    #: Objects that must appear (a glowing cicada, a lantern). Not an
    #: excuse to invent a prop the passage never names -- see rule 1.
    key_objects: list[str] = Field(default_factory=list)
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
        "Return JSON with these keys. EVERY field is a comma-separated list "
        "of short tags -- lowercase, underscores for multi-word concepts, "
        "no sentences, no articles, no conjugated verbs, no periods:",
        '  shot          one of "wide", "medium", "close"',
        "  action        pose/action tags for the single moment to draw, "
        "using only what the passage states (do not add clothing colours "
        "or objects the passage does not mention; facial expression goes "
        "in its own 'expression' field below, not here). Example: "
        "\"weapons_drawn, fighting_stance\" or \"kneeling, exhausted\".",
        "  layout        the character's real name (exactly as written in "
        "CAST -- never the letter X or a placeholder), followed by "
        "spatial/count tags. Example when surrounded: \"Fang Yuan, "
        "surrounded\". Example when alone: \"Fang Yuan, solo, "
        "standing_alone\". If CAST is empty, use \"a figure\" instead of a name.",
        "  setting       location tags, concretely. Example: "
        "\"mountain_background, stone_courtyard, cliff\".",
        "  lighting      time of day / weather / light, as tags. Example: "
        "\"dusk, misty\" or \"day, bright_sunlight\".",
        "  key_objects   list of object tags that must be visible",
        "  mood          one or two mood tags",
        "  expression    ONE compact face tag, only if the passage states "
        "or clearly implies it, independent of physical condition -- a "
        "wounded character is not automatically pained. Example: "
        "\"calm_expression\" or \"blank_stare\" for a passage that says the "
        "expression did not change despite injury; \"pained_expression\" "
        "only if the passage actually describes pain on the face itself, "
        "not just an injury to the body. Leave empty if unstated.",
        "",
        "Only include characters the passage actually places in the scene. "
        "Do not include numeric headcount tags ('1boy', '2boys', 'male "
        "focus') -- those are added separately from your output. 'solo' "
        "and 'crowd' are fine as composition tags when the passage supports "
        "them.",
        "Return only JSON.",
    ]
    return "\n".join(lines)


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
        d = self.direction
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

        from echotales.pipeline.persona.prompt import (
            STYLE_ANCHOR,
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
        tier0: list[str] = [STYLE_ANCHOR, framing]

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
            if "white" in condition.lower() and "robe" in condition.lower():
                _has_white_robe = True
            elif "white" in compressed.lower() and "robe" in compressed.lower():
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

        return [*tier0, *tier1, *tier2, *tier3]


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
        direction,
        beat_text=beat_text,
        cast=cast,
        novel_id=novel_id,
        store=store,
        crowd_mood=crowd_mood,
    )
    return Direction(
        direction=direction, cast=cast, novel_style=novel_style, conditions=conditions or {}
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
