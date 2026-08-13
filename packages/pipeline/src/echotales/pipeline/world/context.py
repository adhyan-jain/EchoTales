"""Context assembly: everything relevant at one position, as a short brief.

Storing facts is half the job. The half that decides whether any of it
matters is **retrieval**: a consumer standing at chapter 40, block 12 needs
to be handed who is here, what they look like, where "here" is, and what
they know -- without being handed the other 9,500 facts in the novel.

**This is the interface the rest of the pipeline should have been using all
along.** `render/direction.py` currently receives a beat's raw text plus a
dictionary of appearance strings, and so writes prompts that know what a
character looks like but not that he is a Rank 2 Gu Master, that the village
he is standing in belongs to the clan hunting him, or that he died an hour
ago in story time. Every one of those is already in the graph.

**Everything is filtered by position, not by existence.** A fact attested in
chapter 90 must not appear in a chapter 12 brief -- that is the whole reason
`Attribute` carries `learned_at_pos` and an interval, and the reason
appearance extraction was changed to date its facts (§4.24). A brief that
ignored position would leak the ending into the opening, which for a novel
built on reveals is the single worst thing this layer could do.

The output is deliberately **text, not a data structure**, at the boundary:
its consumer is a language model, and a compact labelled brief is both
cheaper and more legible to one than nested JSON. `StoryContext` keeps the
structure for callers that want it; `to_brief()` is what goes in a prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from echotales.core.enums import ReferenceMode, TargetKind
from echotales.core.store import Store
from echotales.pipeline.world.schema import keys_for

#: Per-entity fact cap in a brief. A brief is a *summary*: past a handful of
#: facts per entity it stops helping a model and starts burying the ones
#: that matter.
_MAX_FACTS_PER_ENTITY = 6

#: Facts worth leading with, in order. A character's rank and faction change
#: how a scene reads far more than their reputation does, and a location's
#: terrain matters more to a panel than its hierarchy.
_PRIORITY = (
    "place_type",
    "terrain",
    "architecture",
    "atmosphere",
    "role",
    "cultivation_rank",
    "faction",
    "status",
    "titles",
    "abilities",
    "org_type",
    "colors_attire",
    "territory",
    "item_type",
    "appearance",
    "powers",
)


@dataclass(slots=True)
class EntityBrief:
    """One entity, as much as a consumer needs and no more."""

    label: str
    kind: str
    facts: dict[str, str] = field(default_factory=dict)
    appearance: str = ""

    def render(self) -> str:
        bits = [f"{k}: {v}" for k, v in self.facts.items()]
        if self.appearance:
            bits.insert(0, f"appearance: {self.appearance}")
        return f"{self.label} ({self.kind.lower()})" + (
            " -- " + "; ".join(bits) if bits else ""
        )


@dataclass(slots=True)
class StoryContext:
    """Everything relevant at one position in the story."""

    novel_id: str
    chapter: float
    block_index: int
    characters: list[EntityBrief] = field(default_factory=list)
    location: EntityBrief | None = None
    organizations: list[EntityBrief] = field(default_factory=list)
    items: list[EntityBrief] = field(default_factory=list)
    recent_events: list[str] = field(default_factory=list)

    def to_brief(self, *, max_chars: int = 1800) -> str:
        """A compact brief for a language model.

        Ordered by how much each section changes what a consumer should do:
        who is here first, then where, then the wider world, then what just
        happened. Truncation therefore drops background before it drops
        cast.
        """
        lines: list[str] = []
        if self.characters:
            lines.append("PRESENT:")
            lines += [f"  {c.render()}" for c in self.characters]
        if self.location:
            lines.append("SETTING:")
            lines.append(f"  {self.location.render()}")
        if self.organizations:
            lines.append("FACTIONS IN PLAY:")
            lines += [f"  {o.render()}" for o in self.organizations]
        if self.items:
            lines.append("ITEMS:")
            lines += [f"  {i.render()}" for i in self.items]
        if self.recent_events:
            lines.append("RECENTLY:")
            lines += [f"  {e}" for e in self.recent_events]

        brief = "\n".join(lines)
        return brief if len(brief) <= max_chars else brief[:max_chars].rsplit("\n", 1)[0]


def _facts_as_of(
    store: Store, kind: TargetKind, target_id: str, chapter: float
) -> dict[str, str]:
    """Standing facts known by `chapter`, latest attestation winning.

    The position filter is the point: a fact the novel states in chapter 90
    is not available to a chapter 12 brief. Later attestations of the same
    key overwrite earlier ones, which is how a rank advancing or a status
    changing to "dead" reaches the brief without the earlier row being
    deleted -- it is still in the graph, still queryable at its own
    position.
    """
    out: dict[str, str] = {}
    seen_at: dict[str, float] = {}
    for attr in store.get_attributes(kind, target_id):
        if not attr.is_standing or not attr.value:
            continue
        at = attr.learned_at_pos.chapter
        if at > chapter:
            continue
        if attr.key not in seen_at or at >= seen_at[attr.key]:
            out[attr.key] = attr.value
            seen_at[attr.key] = at
    return out


def _ranked(facts: dict[str, str], kind: TargetKind) -> dict[str, str]:
    allowed = set(keys_for(kind))
    picked = {k: v for k, v in facts.items() if k in allowed}
    ordered = sorted(
        picked.items(),
        key=lambda kv: (_PRIORITY.index(kv[0]) if kv[0] in _PRIORITY else 99, kv[0]),
    )
    return dict(ordered[:_MAX_FACTS_PER_ENTITY])


def story_context(
    novel_id: str,
    store: Store,
    chapter: float,
    blocks: list[int],
    *,
    include_appearance: bool = True,
) -> StoryContext:
    """Assemble the brief for a position, from the graph alone.

    `blocks` is a beat's block span rather than a single index, because the
    character a moment is *about* is often named in one block of it and
    acted in another -- the same reason `panels.py::present_beat_entities`
    reads across the beat.
    """
    context = StoryContext(
        novel_id=novel_id, chapter=chapter, block_index=blocks[0] if blocks else 0
    )
    wanted = set(blocks)

    present: list[str] = []
    referenced: list[str] = []
    for mention in store.get_mentions(novel_id, chapter):
        if mention.block_index not in wanted or not mention.target_id:
            continue
        bucket = (
            present
            if mention.reference_mode is ReferenceMode.PRESENT
            else referenced
        )
        if mention.target_id not in bucket:
            bucket.append(mention.target_id)

    for target_id in present + referenced:
        entity = store.get_self(target_id)
        if entity is None:
            continue
        kind = entity.kind
        facts = _ranked(_facts_as_of(store, kind, target_id, chapter), kind)
        brief = EntityBrief(label=entity.canonical_label, kind=kind.value, facts=facts)

        if kind is TargetKind.SELF:
            if target_id not in present:
                # Mentioned but not here. Named in the brief only through
                # its own section would be misleading, so it is simply not
                # added -- panels must not draw absent characters, which is
                # what `ReferenceMode` exists for.
                continue
            if include_appearance:
                brief.appearance = _appearance_brief(store, novel_id, target_id, chapter)
            context.characters.append(brief)
        elif kind is TargetKind.LOCATION and context.location is None:
            context.location = brief
        elif kind is TargetKind.ORGANIZATION:
            context.organizations.append(brief)
        elif kind is TargetKind.ITEM:
            context.items.append(brief)

    return context


def _appearance_brief(
    store: Store, novel_id: str, entity_id: str, chapter: float
) -> str:
    """A character's look as of this chapter, phrased for a prompt.

    Position-filtered like everything else here: a body described after a
    transformation must not describe them before it.
    """
    from echotales.pipeline.persona.attire import resolve_appearance
    from echotales.pipeline.persona.canon import apply_canon
    from echotales.pipeline.persona.reference_gen import (
        _demographics,
        build_reference_prompt,
    )
    from echotales.pipeline.resolve.appearance_extract import STANDING_KEYS

    entity = store.get_self(entity_id)
    if entity is None:
        return ""

    facts = _facts_as_of(store, TargetKind.PERSONA, f"{entity_id}:body1", chapter)
    appearance = {k: v for k, v in facts.items() if k in STANDING_KEYS}
    appearance = apply_canon(novel_id, entity.canonical_label, appearance)
    appearance = resolve_appearance(novel_id, appearance)
    if not appearance:
        return ""
    # Gender has to be passed, not defaulted: omitting it renders every
    # character as "androgynous person", which is how the male protagonist
    # came out drawn as a woman the first time this leaked (§4.24).
    gender, age_band = _demographics(
        store, f"{entity_id}:body1", novel_id=novel_id, entity_id=entity_id
    )
    return build_reference_prompt(
        entity.canonical_label,
        appearance,
        gender=gender,
        age_band=age_band,
        with_style=False,
    )
