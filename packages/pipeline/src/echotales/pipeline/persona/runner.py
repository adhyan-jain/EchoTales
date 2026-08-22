"""`get_panel_cast` -- one panel's visual casting data (xyz.md Step 4).

Assembles foreground characters, background mobs and an environment style
for a single block, reusing `spans/scene.py`'s active-scene registry (Step
2) rather than re-deriving presence. See the package docstring for why
`persona_id_by_self`/explicit attire are usually empty today -- there is no
persona-construction stage yet to populate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from echotales.core.enums import TargetKind
from echotales.core.models import Chapter, Mention, NarrativeSegment, Span
from echotales.pipeline.anaphora.local import present_cast
from echotales.pipeline.persona.attire import resolve_attire
from echotales.pipeline.spans.scene import build_active_scenes


@dataclass(slots=True)
class CharacterCast:
    self_label: str
    attire: str


@dataclass(slots=True)
class MobCast:
    role: str
    description: str
    attire: str


@dataclass(slots=True)
class PanelCast:
    foreground_characters: list[CharacterCast] = field(default_factory=list)
    background_mobs: list[MobCast] = field(default_factory=list)
    environment: str = ""


def get_panel_cast(
    novel_id: str,
    chapter: Chapter,
    block_index: int,
    *,
    mentions: list[Mention],
    segments: list[NarrativeSegment],
    spans: list[Span],
    store: object | None = None,
    persona_id_by_self: dict[str, str] | None = None,
    faction_by_self: dict[str, str] | None = None,
    mob_faction: dict[str, str] | None = None,
    region: str | None = None,
    block_window: tuple[int, int] | None = None,
) -> PanelCast:
    """Who's in frame at `block_index`, and what they should look like.

    `store`/`persona_id_by_self` are optional: if given, an explicit
    `Attribute(target_kind=PERSONA, key="attire")` row wins over the
    faction/regional/style defaults, same tier-1 slot `attire.py` reserves
    for it. `faction_by_self`/`mob_faction`/`region` are plain caller-
    supplied names (the graph has nowhere to store them yet -- see
    `attire.py`'s docstring) looked up against the seeded tables.

    Returns an empty cast (environment only) when `block_index` falls
    outside every tracked scene -- e.g. a chapter with no detected
    `NarrativeSegment` boundaries yet.

    **Foreground presence is scoped to `block_window` (defaulting to just
    `block_index`), not to the whole `NarrativeSegment`, and that distinction
    is load-bearing.** A `NarrativeSegment` marks *story-time* continuity --
    a dream, a flashback, a time skip -- and a chapter with none of those
    is correctly exactly one segment covering all of it (Section 3's own design).
    Reading that as "the scene" for panel casting means every panel in a
    92-block chapter gets the same cast: measured on RI ch1, clan elders
    discussing the harvest got Fang Yuan in their foreground because he
    appears *somewhere* in the chapter's one segment, and vice versa. A
    beat's own block range is the right unit -- it is already how
    `render/panels.py::present_beat_entities` scopes appearance and
    reference conditioning, so this brings casting into agreement with
    them instead of quietly using a coarser window for one and not the
    other.

    `store` (when given) also filters non-person entities out of the cast
    via `Self.kind` -- `Mention.target_kind` cannot be used for this; it is
    written once at linking time and goes stale when the resolver's typing
    pass later reclassifies an entity (verified against real data: a
    LOCATION's every mention still reads `target_kind=SELF`). Without
    `store`, presence is reported unfiltered, same as before this existed.
    """
    scenes = build_active_scenes(chapter, mentions, segments, spans)
    scene = next(
        (s for s in scenes if s.block_from <= block_index <= s.block_to), None
    )
    if scene is None:
        return PanelCast(environment=resolve_attire(novel_id, region=region))

    lo, hi = block_window or (block_index, block_index)
    lo, hi = max(lo, scene.block_from), min(hi, scene.block_to)
    person_ids = None
    if store is not None:
        person_ids = frozenset(
            e.id for e in store.all_selves(novel_id) if e.kind.is_person  # type: ignore[attr-defined]
        )
    local_mentions = [m for m in mentions if lo <= m.block_index <= hi]
    local_cast = present_cast(local_mentions, person_ids)

    # A narrator reveal logged for this exact block hands the reader (not
    # the characters in the scene) an identity that no resolved mention
    # carries -- the placeholder surface ("the immortal zombie") is what
    # `present_cast` found, not the name the reveal just gave the reader.
    # Added to the cast rather than replacing the placeholder, since the
    # placeholder mention is still real evidence of *someone* being present
    # even where the revealed label doesn't already have a
    # `persona_id_by_self`/`faction_by_self` entry of its own -- see
    # `detect_reveals.reveal_target_for_block`'s docstring on why this is
    # block-scoped, not chapter- or scene-scoped.
    if store is not None:
        from echotales.pipeline.resolve.detect_reveals import reveal_target_for_block

        revealed_id = reveal_target_for_block(store, novel_id, chapter.number, block_index)
        if revealed_id is not None:
            revealed = store.get_self(revealed_id)  # type: ignore[attr-defined]
            if revealed is not None and revealed.canonical_label not in local_cast:
                local_cast = local_cast | {revealed.canonical_label}

    foreground: list[CharacterCast] = []
    for name in sorted(local_cast):
        explicit = None
        rank = None
        persona_id = (persona_id_by_self or {}).get(name)
        if store is not None and persona_id:
            attrs = store.get_attributes(TargetKind.PERSONA, persona_id)  # type: ignore[attr-defined]
            explicit = next(
                (a.value for a in attrs if a.key == "attire" and a.is_standing), None
            )
            # `rank_insignia` is the appearance extractor's own vocabulary
            # for this (e.g. "... Rank two Gu Master") -- reused here rather
            # than adding a second rank source, so a character with no
            # attire of their own but a known title still gets something
            # closer than the novel's generic drawing style.
            rank = next(
                (a.value for a in attrs if a.key == "rank_insignia" and a.is_standing),
                None,
            )
        faction = (faction_by_self or {}).get(name)
        foreground.append(
            CharacterCast(
                self_label=name,
                attire=resolve_attire(
                    novel_id, explicit=explicit, faction=faction, rank=rank, region=region
                ),
            )
        )

    background: list[MobCast] = []
    for mob in scene.mobs:
        # Foreground persons above are correctly scoped to the whole
        # `block_window` (lo..hi), not just `block_index` (a slot's
        # single lead block) -- this loop used to check the single block
        # only, so a mob description landing on a different block of the
        # same scene (e.g. "the clan's elders" a few blocks after the
        # panel's lead block) was silently dropped, and a genuine group
        # scene rendered as one isolated figure with nobody else in
        # frame. Match the foreground scoping.
        if not (lo <= mob.block_index <= hi):
            continue
        faction = (mob_faction or {}).get(mob.role)
        background.append(
            MobCast(
                role=mob.role,
                description=mob.text,
                attire=resolve_attire(novel_id, faction=faction, region=region),
            )
        )

    return PanelCast(
        foreground_characters=foreground,
        background_mobs=background,
        environment=resolve_attire(novel_id, region=region),
    )
