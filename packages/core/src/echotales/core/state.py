"""``state_of()`` -- the central query (plans.md Section 6 Phase 7).

    state_of(target, timeline, position, observer=READER)
      -> {aliases, attributes, relationships, persona, truth_status}

Everything downstream consumes this: voice selection, prosody, reference
images, panel casting. Four filters compose to produce the answer, and each one
exists because a specific failure mode would otherwise occur.

**Story-time containment.** Does the fact's interval cover this position? Uses
the fuzzy interval algebra, so the answer is CERTAIN / PLAUSIBLE / EXCLUDED
rather than a boolean. Without this, a character's chapter-140 appearance
leaks into their chapter-10 panel.

**Knowledge time.** Was the fact learned at or before the observer's position?
This is what makes ``state_of(fang_yuan, observer=WU_CLAN)`` differ from
``state_of(fang_yuan, observer=READER)``. Without it, the narration spoils
every reveal the moment the graph knows it.

**Truth status.** ``FALSE`` facts are hidden from in-world observers but
visible to ``SYSTEM``, which is what makes evaluation and debugging possible.
Retraction is applied *positionally*: a claim retracted at chapter 200 is still
returned for an observer standing at chapter 150, because they did believe it
then. This is the difference between retraction and interval end, and getting
it wrong erases the reader's former beliefs from history.

**Canonicity.** Facts inside VOIDED segments are excluded from the canonical
timeline but stay reachable for "what did the reader believe at the time".
"""

from __future__ import annotations

from collections.abc import Iterable

from echotales.core.enums import (
    OBSERVER_READER,
    OBSERVER_SYSTEM,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import Certainty, StoryPos
from echotales.core.models import (
    MAIN_TIMELINE,
    AliasBinding,
    Attribute,
    DiscoursePosition,
    StateOfResult,
    TemporalFact,
)
from echotales.core.readset import ReadSetRecorder, alias_ref, entity_ref
from echotales.core.store import Store, normalize_alias


def observer_scope(observer_id: str) -> set[str] | None:
    """Which observers' facts are visible to this observer.

    ``None`` means "all", which only ``SYSTEM`` gets.

    A character observer sees only facts explicitly recorded as known to them.
    They deliberately do *not* inherit the reader's knowledge -- that
    inheritance is precisely the spoiler bug this model exists to prevent. Wu
    clan members never learn that Wu Yi Hai is Fang Yuan, even though the
    reader has known since chapter one.
    """
    if observer_id == OBSERVER_SYSTEM:
        return None
    return {observer_id}


def _visible_to_observer(
    fact: TemporalFact,
    observer_id: str,
    knowledge_pos: DiscoursePosition,
) -> bool:
    """Apply the knowledge-time and truth-status filters."""
    scope = observer_scope(observer_id)

    # SYSTEM is omniscient: it sees FALSE facts and ignores knowledge time,
    # which is what makes it usable as the evaluation oracle.
    if scope is None:
        return True

    if fact.observer_id not in scope:
        return False

    # The observer has not reached the point where this became known.
    if fact.learned_at_pos > knowledge_pos:
        return False

    if fact.retracted_at is not None:
        # A retracted fact was believed right up until the reveal, and not
        # after. Position alone decides, and the FALSE truth_status that
        # retraction stamps on the row must NOT also be applied below --
        # doing so would erase the belief from the observer's past, which is
        # exactly the difference between retraction and interval end.
        return knowledge_pos < fact.retracted_at

    # A fact asserted as false without ever having been believed (e.g. the
    # narrator flagging a rumour as untrue on arrival) is invisible in-world.
    return fact.truth_status is not TruthStatus.FALSE


def _temporal_certainty(fact: TemporalFact, timeline_id: str, position: StoryPos) -> Certainty:
    """Story-time containment, scoped to a timeline.

    Cross-timeline ordering is a partial order: a fact on
    ``DREAM_TU_SHI_CHENG`` says nothing about a position on
    ``MAIN_TIMELINE``. Mismatched timelines are EXCLUDED rather than compared,
    because comparing them would invent an ordering the text never provides.
    """
    if fact.timeline_id != timeline_id:
        return Certainty.EXCLUDED
    return fact.interval.contains(position)


class StateResolver:
    """Answers ``state_of`` against a store.

    Holds the set of VOIDED segment ids so canonicity filtering does not hit
    the database per fact.
    """

    def __init__(self, store: Store, novel_id: str) -> None:
        self.store = store
        self.novel_id = novel_id
        self._voided_timelines: set[str] = set()
        self._refresh_voided()

    def _refresh_voided(self) -> None:
        """Timelines that are wholly voided.

        Segment-level voiding is applied at fact level via story position; this
        cheap pre-pass catches the common case where an entire illusion
        timeline is retroactively invalidated.
        """
        from echotales.core.enums import Canonicity

        self._voided_timelines = {
            s.timeline_id
            for s in self.store.get_segments(self.novel_id)
            if s.canonicity is Canonicity.VOIDED
        }

    def state_of(
        self,
        target_id: str,
        *,
        target_kind: TargetKind = TargetKind.SELF,
        timeline_id: str = MAIN_TIMELINE,
        position: StoryPos | None = None,
        observer_id: str = OBSERVER_READER,
        knowledge_pos: DiscoursePosition | None = None,
        include_plausible: bool = True,
        recorder: ReadSetRecorder | None = None,
    ) -> StateOfResult:
        """Resolve an entity's state at a point in story time.

        ``position`` is story time; ``knowledge_pos`` is discourse position. For
        the READER they advance together, so ``knowledge_pos`` defaults to the
        chapter containing ``position``. For a character observer they diverge,
        and that divergence is the whole point.

        ``include_plausible`` controls whether facts that only PLAUSIBLY hold
        are returned. Generation wants them (a panel needs *some* appearance);
        evaluation usually does not.
        """
        if position is None:
            position = float("inf")
        if knowledge_pos is None:
            # Story position and discourse position coincide only on the main
            # timeline, where the default segmentation sets story_seq to the
            # chapter index. Inside a dream or flashback the story position is
            # an internal coordinate of that timeline and says nothing about
            # which chapter the reader has reached, so deriving knowledge time
            # from it there would filter out the entire timeline.
            if timeline_id == MAIN_TIMELINE and position != float("inf"):
                knowledge_pos = DiscoursePosition(chapter=int(position))
            else:
                knowledge_pos = DiscoursePosition(chapter=10**6)

        rec = recorder or ReadSetRecorder()
        rec.record(entity_ref(target_kind, target_id))

        accepted: list[Certainty] = []

        def keep(fact: TemporalFact) -> Certainty | None:
            if fact.timeline_id in self._voided_timelines:
                return None
            if not _visible_to_observer(fact, observer_id, knowledge_pos):
                return None
            cert = _temporal_certainty(fact, timeline_id, position)
            if cert is Certainty.EXCLUDED:
                return None
            if cert is Certainty.PLAUSIBLE and not include_plausible:
                return None
            return cert

        # ---- aliases --------------------------------------------------
        aliases: list[str] = []
        seen_alias: set[str] = set()
        for binding in self._alias_candidates(target_kind, target_id):
            cert = keep(binding)
            if cert is None:
                continue
            rec.record(alias_ref(self.novel_id, normalize_alias(binding.alias)))
            key = normalize_alias(binding.alias)
            if key not in seen_alias:
                seen_alias.add(key)
                aliases.append(binding.alias)
            accepted.append(cert)

        # ---- attributes -----------------------------------------------
        # Later-learned facts win on key collision: a character described as
        # "black-haired" in ch 3 and "white-haired" in ch 150 should render
        # white-haired when queried at 150.
        attributes: dict[str, str] = {}
        attr_learned: dict[str, DiscoursePosition] = {}
        for attr in self._attribute_candidates(target_kind, target_id):
            cert = keep(attr)
            if cert is None:
                continue
            prev = attr_learned.get(attr.key)
            if prev is None or attr.learned_at_pos >= prev:
                attributes[attr.key] = attr.value
                attr_learned[attr.key] = attr.learned_at_pos
            accepted.append(cert)

        # ---- relationships ---------------------------------------------
        relationships: list[tuple[str, str]] = []
        if target_kind is TargetKind.SELF:
            for rel in self.store.get_relations(target_id):
                cert = keep(rel)
                if cert is None:
                    continue
                rec.record(entity_ref(TargetKind.SELF, rel.dst_self))
                relationships.append((rel.type, rel.dst_self))
                accepted.append(cert)

        # ---- personas ---------------------------------------------------
        # Concurrent bindings are legitimate and are how clones, soul avatars
        # and simultaneous disguises are represented, so this is a list.
        persona_ids: list[str] = []
        if target_kind is TargetKind.SELF:
            for binding in self.store.get_self_persona_bindings(self_id=target_id):
                if binding.timeline_id != timeline_id:
                    continue
                if binding.observer_id not in (observer_scope(observer_id) or {binding.observer_id}):
                    continue
                if binding.learned_at_pos > knowledge_pos and observer_id != OBSERVER_SYSTEM:
                    continue
                cert = binding.interval.contains(position)
                if cert is Certainty.EXCLUDED:
                    continue
                if cert is Certainty.PLAUSIBLE and not include_plausible:
                    continue
                rec.record(entity_ref(TargetKind.PERSONA, binding.persona_id))
                persona_ids.append(binding.persona_id)
                accepted.append(cert)

        overall = Certainty.CERTAIN
        for c in accepted:
            overall = overall & c
        if not accepted:
            overall = Certainty.CERTAIN

        return StateOfResult(
            target_kind=target_kind,
            target_id=target_id,
            timeline_id=timeline_id,
            position=position,
            observer_id=observer_id,
            aliases=aliases,
            attributes=attributes,
            relationships=relationships,
            persona_ids=persona_ids,
            certainty=overall.value,
            read_set=rec.refs,
        )

    # ---- candidate fetch ------------------------------------------------

    def _alias_candidates(self, kind: TargetKind, target_id: str) -> Iterable[AliasBinding]:
        return self.store.get_aliases_for(kind, target_id)

    def _attribute_candidates(self, kind: TargetKind, target_id: str) -> Iterable[Attribute]:
        return self.store.get_attributes(kind, target_id)

    # ---- convenience -----------------------------------------------------

    def resolve_alias(
        self,
        alias: str,
        *,
        timeline_id: str = MAIN_TIMELINE,
        position: StoryPos,
        observer_id: str = OBSERVER_READER,
        knowledge_pos: DiscoursePosition | None = None,
    ) -> list[tuple[TargetKind, str, Certainty]]:
        """Who could this surface form denote at this point?

        Returns *all* temporally valid holders, not one answer. Alias->target
        is one-to-many at any given time -- "Elder" and "Senior Brother" have
        many simultaneous holders -- so this is a candidate-set filter that
        narrows the pool for contextual scoring, never a resolver.
        """
        if knowledge_pos is None:
            knowledge_pos = DiscoursePosition(chapter=int(position))
        out: list[tuple[TargetKind, str, Certainty]] = []
        for binding in self.store.find_alias_bindings(self.novel_id, alias, timeline_id):
            if binding.timeline_id in self._voided_timelines:
                continue
            if not _visible_to_observer(binding, observer_id, knowledge_pos):
                continue
            cert = _temporal_certainty(binding, timeline_id, position)
            if cert is Certainty.EXCLUDED:
                continue
            out.append((binding.target_kind, binding.target_id, cert))
        return out

    def concurrent_personas(
        self, self_id: str, timeline_id: str, position: StoryPos
    ) -> list[str]:
        """Personas simultaneously bound to one self.

        Used to suppress the co-presence penalty in the resolver: two mentions
        appearing at once is evidence of two distinct *personas*, which for a
        clone or avatar is not evidence of two distinct selves.
        """
        return [
            b.persona_id
            for b in self.store.get_self_persona_bindings(self_id=self_id)
            if b.timeline_id == timeline_id and b.interval.contains(position).is_possible
        ]


def state_of(
    store: Store,
    novel_id: str,
    target_id: str,
    **kwargs: object,
) -> StateOfResult:
    """Module-level convenience wrapper around `StateResolver`."""
    return StateResolver(store, novel_id).state_of(target_id, **kwargs)  # type: ignore[arg-type]
