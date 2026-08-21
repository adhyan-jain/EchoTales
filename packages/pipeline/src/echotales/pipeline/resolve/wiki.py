"""Wiki-style entity summaries (plans.md Section 6 Phase 6).

Regenerated from the graph at each window boundary and used as LLM context in
the next window. The direction of authority matters and is easy to get
backwards: **the graph is the source of truth and the summary is a cache**, not
the other way round. A summary is never read back into the graph, so a
hallucinated detail in one cannot corrupt the store.

Summaries are compact by design. The point is to give the adjudicator enough to
tell two candidates apart -- who they are, what they are called, when they
appear, who they talk to -- not to retell the plot. Verbosity here costs
context window on an 8 GB card and buys nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from echotales.core.enums import OBSERVER_SYSTEM, TargetKind
from echotales.core.store import Store
from echotales.pipeline.resolve.retrieve import EntityProfile

#: Aliases listed per entity. Beyond this the summary stops discriminating and
#: starts consuming context.
_MAX_ALIASES = 8
_MAX_TERMS = 12


@dataclass(slots=True)
class EntitySummary:
    target_id: str
    label: str
    aliases: list[str]
    first_chapter: float
    last_chapter: float
    mention_count: int
    salient_terms: list[str]
    attributes: dict[str, str]

    def render(self) -> str:
        """One compact block per entity."""
        lines = [f"### {self.label}  (id: {self.target_id})"]
        if self.aliases:
            lines.append(f"- also called: {', '.join(self.aliases)}")
        lines.append(
            f"- appears: ch {self.first_chapter:g}-{self.last_chapter:g} "
            f"({self.mention_count} mentions)"
        )
        if self.attributes:
            attrs = ", ".join(f"{k}={v}" for k, v in sorted(self.attributes.items()))
            lines.append(f"- attributes: {attrs}")
        if self.salient_terms:
            lines.append(f"- associated with: {', '.join(self.salient_terms)}")
        return "\n".join(lines)


def summarise_entity(
    profile: EntityProfile,
    store: Store | None = None,
) -> EntitySummary:
    """Build a summary for one entity from its profile and the graph."""
    attributes: dict[str, str] = {}
    if store is not None:
        # SYSTEM observer: the summary is internal machinery, and hiding facts
        # from it would make the adjudicator worse at exactly the reveal cases
        # it exists to handle. It is never shown to a reader.
        for attribute in store.get_attributes(profile.target_kind, profile.target_id):
            if attribute.observer_id in (OBSERVER_SYSTEM, "READER"):
                attributes[attribute.key] = attribute.value

    aliases = sorted(profile.aliases, key=len, reverse=True)[:_MAX_ALIASES]
    salient = [term for term, _ in profile.context_terms.most_common(_MAX_TERMS)]

    return EntitySummary(
        target_id=profile.target_id,
        label=profile.label,
        aliases=aliases,
        first_chapter=profile.first_chapter,
        last_chapter=profile.last_chapter,
        mention_count=profile.mention_count,
        salient_terms=salient,
        attributes=attributes,
    )


def build_wiki(
    profiles: dict[str, EntityProfile],
    store: Store | None = None,
    *,
    min_mentions: int = 2,
    limit: int = 40,
) -> str:
    """Render a wiki for the most prominent entities.

    Capped at `limit`: an adjudication prompt that lists every walk-on
    character buries the two candidates that actually matter, and the whole
    point of the summary is discrimination.
    """
    ranked = sorted(
        (p for p in profiles.values() if p.mention_count >= min_mentions),
        key=lambda p: p.mention_count,
        reverse=True,
    )[:limit]
    if not ranked:
        return "(no entities established yet)"
    return "\n\n".join(summarise_entity(p, store).render() for p in ranked)


def build_focused_wiki(
    profiles: dict[str, EntityProfile],
    target_ids: list[str],
    store: Store | None = None,
) -> str:
    """Render summaries for just the candidates under consideration.

    Used for adjudication, where the model needs depth on a handful of
    entities rather than breadth across the cast.
    """
    chosen = [profiles[t] for t in target_ids if t in profiles]
    if not chosen:
        return "(no candidate profiles available)"
    return "\n\n".join(summarise_entity(p, store).render() for p in chosen)


def wiki_for_kind(
    profiles: dict[str, EntityProfile],
    kind: TargetKind,
    store: Store | None = None,
) -> str:
    """Wiki restricted to selves or to personas."""
    subset = {k: v for k, v in profiles.items() if v.target_kind is kind}
    return build_wiki(subset, store)
