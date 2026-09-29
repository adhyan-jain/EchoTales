"""``state_of()`` -- the central query (docs/design/plans.md Section 6 Phase 7).

    state_of(target, timeline, position, observer=READER)
      -> {aliases, attributes, relationships, persona, truth_status}

Panel casting and reference images consume this, through one compiled
`GenerationState` per beat. Voice casting does not: it is per character for the
whole volume and has no position- or observer-dependent input. Four filters compose to produce the answer, and each one
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

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

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
from echotales.core.readset import (
    ReadSetRecorder,
    alias_ref,
    entity_ref,
    fact_ref,
    hash_read_set,
    observable_ref,
)
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
    observations: Mapping[str, DiscoursePosition] | None = None,
) -> bool:
    """Apply the knowledge-time and truth-status filters.

    `observations` is the character observer's own record of what they
    witnessed (`Store.observations_for`). It is what makes a character
    observer able to see anything at all: every fact this pipeline writes is
    stamped `observer_id=READER`, so before 2026-09-23 a character scope
    matched nothing and `state_of(observer=WU_CLAN)` returned an empty result
    rather than a *smaller* one. Empty is not the claim -- "the Wu clan
    believes something different from what the reader knows" is
    (EVOLUTION 4.80).
    """
    scope = observer_scope(observer_id)

    # SYSTEM is omniscient: it sees FALSE facts and ignores knowledge time,
    # which is what makes it usable as the evaluation oracle.
    if scope is None:
        return True

    witnessed_at: DiscoursePosition | None = None
    if fact.observer_id not in scope:
        # A character observer may still hold a reader-stamped fact, but only
        # via an explicit observation. This is the one door: absent an
        # observation row, a character does not inherit the reader's
        # knowledge, which is the spoiler bug this whole model exists to
        # prevent.
        if observations is None or fact.observer_id != OBSERVER_READER:
            return False
        try:
            ref = observable_ref(fact)
        except TypeError:
            return False
        witnessed_at = observations.get(ref)
        if witnessed_at is None:
            return False

    # The observer has not reached the point where this became known. For a
    # witnessed fact that is when *they* saw it, not when the narrator told
    # the reader -- the two diverge, and that divergence is the whole point.
    learned = witnessed_at if witnessed_at is not None else fact.learned_at_pos
    if learned > knowledge_pos:
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

    def __init__(
        self,
        store: Store,
        novel_id: str,
        *,
        default_observer: str = OBSERVER_READER,
    ) -> None:
        self.store = store
        self.novel_id = novel_id
        # The observer belongs to the *viewing context*, not to each query.
        # Putting it here rather than threading `observer_id` through every
        # caller is what lets `render --observer` work at all: the render tree
        # makes `state_of` calls several layers below the CLI
        # (`plan_builder.build_render_plan`, `panels.character_looks`), and a
        # per-call parameter would have to be passed identically through all
        # of them, with any missed one silently falling back to READER and
        # quietly reintroducing the spoiler it was set to avoid.
        self.default_observer = default_observer
        self._voided_timelines: set[str] = set()
        self._observation_cache: dict[str, Mapping[str, DiscoursePosition]] = {}
        self._refresh_voided()

    def _observations_for(self, observer_id: str) -> Mapping[str, DiscoursePosition]:
        """Cached per resolver, since a render asks for many entities at once."""
        cached = self._observation_cache.get(observer_id)
        if cached is None:
            cached = self.store.observations_for(observer_id)
            self._observation_cache[observer_id] = cached
        return cached

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
        observer_id: str | None = None,
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
        observer_id = observer_id or self.default_observer
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

        # Loaded once per query, not per fact: `state_of` filters every
        # candidate fact of an entity and a per-fact round trip would put a
        # query inside the hot loop of the operation this project most wants
        # to be cheap. READER and SYSTEM never consult it.
        observations = (
            self._observations_for(observer_id)
            if observer_id not in (OBSERVER_READER, OBSERVER_SYSTEM)
            else None
        )

        accepted: list[Certainty] = []

        def keep(fact: TemporalFact) -> Certainty | None:
            if fact.timeline_id in self._voided_timelines:
                return None
            if not _visible_to_observer(fact, observer_id, knowledge_pos, observations):
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
            rec.record(observable_ref(attr))
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


#: Reads the attributes of one persona that a modality actually consumes when
#: it draws/voices that persona (position-scoped by the caller's closure).
PersonaReader = Callable[[str], Mapping[str, str]]


@dataclass(slots=True, frozen=True)
class TargetState:
    """What one generation target resolved to, in canonical (sorted) form."""

    self_id: str
    persona_ids: tuple[str, ...] = ()
    #: Attributes of the Self that the observer can see at the position.
    self_attributes: tuple[tuple[str, str], ...] = ()
    #: `(persona_id, ((key, value), ...))` for the persona that is drawn --
    #: the first bound one, matching the render path's "take the first" rule.
    persona_attributes: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()
    #: Every standing fact of the drawn persona valid at the position -- a
    #: superset of `persona_attributes`, hashed but never handed to a prompt.
    #: The prompt reads more than appearance (gender and age for the count
    #: tags, the reference path), so hashing only what `persona_reader`
    #: returns let a real prompt change through with an unchanged key (A7
    #: re-run, 2026-09-27: 23 stale reuses on an attire change).
    persona_facts: tuple[tuple[str, str], ...] = ()


@dataclass(slots=True, frozen=True)
class GenerationState:
    """Compiled epistemic state for multimodal generation.

    One compile is the single source of who is drawn/voiced and with which
    attributes: the render prompt, the render plan and the cache key all read
    this object instead of re-querying `state_of()` separately, so they cannot
    disagree (the panel prompt used the in-chapter position while the plan used
    the chapter start -- a mid-chapter body change was in the prompt but not in
    the cache key).

    `read_set` is the render-relevant dependency set: exactly the facts the
    compile consumed, as stable refs (`readset.fact_ref` strings). It is what
    `digest()` hashes, so a change to a consulted fact changes the digest and a
    change to an unconsulted fact (a relationship, an alias, an attribute the
    modality does not read) does not. `provenance_refs` is the wider set
    `state_of` touched while resolving, kept for audit and not hashed.
    """

    observer_id: str
    story_position: StoryPos
    knowledge_pos: DiscoursePosition
    visible_identities: tuple[str, ...]
    persona_bindings: tuple[str, ...]
    allowed_facts: tuple[str, ...]
    forbidden_facts: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    read_set: tuple[str, ...]
    targets: tuple[TargetState, ...] = ()

    def target(self, self_id: str) -> TargetState | None:
        for t in self.targets:
            if t.self_id == self_id:
                return t
        return None

    def covers(self, self_ids: Iterable[str]) -> bool:
        have = {t.self_id for t in self.targets}
        return all(sid in have for sid in self_ids)

    def persona_for(self, self_id: str) -> str | None:
        """The persona drawn for this Self: the first bound one."""
        t = self.target(self_id)
        return t.persona_ids[0] if t and t.persona_ids else None

    def appearance_for(self, persona_id: str) -> dict[str, str] | None:
        """The compiled attributes of a drawn persona, or None if not compiled."""
        for t in self.targets:
            for pid, attrs in t.persona_attributes:
                if pid == persona_id:
                    return dict(attrs)
        return None

    def to_dict(self) -> dict[str, object]:
        """JSON-safe and deterministic: tuples become lists, order is canonical."""
        return {
            "observer_id": self.observer_id,
            "story_position": self.story_position if self.story_position != float("inf") else "inf",
            "knowledge_chapter": self.knowledge_pos.chapter,
            "visible_identities": list(self.visible_identities),
            "persona_bindings": list(self.persona_bindings),
            "allowed_facts": list(self.allowed_facts),
            "forbidden_facts": list(self.forbidden_facts),
            "provenance_refs": list(self.provenance_refs),
            "read_set": list(self.read_set),
            "targets": [
                {
                    "self_id": t.self_id,
                    "persona_ids": list(t.persona_ids),
                    "self_attributes": [list(kv) for kv in t.self_attributes],
                    "persona_attributes": [[pid, [list(kv) for kv in attrs]] for pid, attrs in t.persona_attributes],
                    "persona_facts": [list(kv) for kv in t.persona_facts],
                }
                for t in self.targets
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: Mapping[str, object]) -> GenerationState:
        pos = d["story_position"]
        return cls(
            observer_id=str(d["observer_id"]),
            story_position=float("inf") if pos == "inf" else float(pos),  # type: ignore[arg-type]
            knowledge_pos=DiscoursePosition(chapter=int(d["knowledge_chapter"])),  # type: ignore[call-overload]
            visible_identities=tuple(d["visible_identities"]),  # type: ignore[call-overload]
            persona_bindings=tuple(d["persona_bindings"]),  # type: ignore[call-overload]
            allowed_facts=tuple(d["allowed_facts"]),  # type: ignore[call-overload]
            forbidden_facts=tuple(d["forbidden_facts"]),  # type: ignore[call-overload]
            provenance_refs=tuple(d["provenance_refs"]),  # type: ignore[call-overload]
            read_set=tuple(d["read_set"]),  # type: ignore[call-overload]
            targets=tuple(
                TargetState(
                    self_id=t["self_id"],
                    persona_ids=tuple(t["persona_ids"]),
                    self_attributes=tuple((k, v) for k, v in t["self_attributes"]),
                    persona_attributes=tuple(
                        (pid, tuple((k, v) for k, v in attrs)) for pid, attrs in t["persona_attributes"]
                    ),
                    persona_facts=tuple((k, v) for k, v in t.get("persona_facts", [])),
                )
                for t in d["targets"]  # type: ignore[attr-defined]
            ),
        )

    def digest(self) -> str:
        """Hash of what a modality consumes: per-target resolved state and the
        render-relevant read set.

        Deliberately excludes the observer (the per-target state already
        reflects what the observer can see; hashing the id itself re-rendered
        30 panels whose drawn state was identical when only the observer
        changed, A7 re-run), the story position (the resolved content reflects
        it, and the plan carries the chapter), and the allowed/forbidden and
        provenance lists (audit data, not inputs).
        """
        payload = {
            "targets": self.to_dict()["targets"],
            "read_set": hash_read_set(self.read_set),
        }
        return hashlib.blake2b(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            digest_size=16,
        ).hexdigest()


@dataclass(slots=True, frozen=True)
class _TargetFold:
    """One target's `state_of` result folded into a `GenerationState` shape."""

    target: TargetState
    persona_ids: tuple[str, ...]
    allowed: frozenset[str]
    forbidden: frozenset[str]
    deps: frozenset[str]


def _fold_target(
    tid: str,
    obs_res: StateOfResult,
    store: Store,
    position: StoryPos,
    persona_reader: PersonaReader | None,
    *,
    attribute_keys: frozenset[str] | None = None,
    alias_values: frozenset[str] | None = None,
    relation_dsts: frozenset[str] | None = None,
) -> _TargetFold:
    """Fold one target's already-filtered `state_of` result into allowed/
    forbidden/deps and a `TargetState`.

    `attribute_keys`/`alias_values`/`relation_dsts`, when given, restrict
    which of `obs_res`'s observer-valid facts are folded in -- this is the
    seam `disclosure.py::compile_minimal_disclosure` uses to select a task-
    sufficient subset without re-deriving observer/temporal filtering, which
    `state_of` already did correctly. `compile_generation_state` passes
    `None` for all three, folding in everything `state_of` returned (the
    original, unchanged behavior). A fact excluded by one of these filters
    lands in `forbidden` via the same "not in allowed" check used for facts
    the observer cannot see -- MDC's task-irrelevant exclusions and
    `state_of`'s epistemic exclusions are indistinguishable to
    `EpistemicLeakageValidator`, which is the point: both are things the
    generated text must not contain.
    """
    allowed: set[str] = set()
    forbidden: set[str] = set()
    deps: set[str] = set()
    persona_ids: list[str] = []

    # The omniscient view, to find what exists in the store but is hidden
    # from this observer at this position (or excluded by the task).
    all_aliases = store.get_aliases_for(TargetKind.SELF, tid)
    all_attrs = store.get_attributes(TargetKind.SELF, tid)

    deps.add(entity_ref(TargetKind.SELF, tid))

    if obs_res.persona_ids:
        persona_ids.extend(obs_res.persona_ids)
    for pid in obs_res.persona_ids:
        deps.add(entity_ref(TargetKind.PERSONA, pid))

    for a in obs_res.aliases:
        if alias_values is not None and a not in alias_values:
            continue
        allowed.add(f"alias:{a}")

    kept_attrs: dict[str, str] = {}
    for k, v in obs_res.attributes.items():
        if attribute_keys is not None and k not in attribute_keys:
            continue
        kept_attrs[k] = v
        allowed.add(f"attr:{k}={v}")
        deps.add(fact_ref("attr", tid, k, v))

    for rel_type, dst in obs_res.relationships:
        if relation_dsts is not None and dst not in relation_dsts:
            continue
        allowed.add(f"rel:{rel_type}:{dst}")

    persona_attrs: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()
    persona_facts: tuple[tuple[str, str], ...] = ()
    if persona_reader is not None and obs_res.persona_ids:
        drawn = obs_res.persona_ids[0]
        attrs = tuple(sorted(persona_reader(drawn).items()))
        persona_attrs = ((drawn, attrs),)
        persona_facts = tuple(sorted({
            (a.key, a.value)
            for a in store.get_attributes(TargetKind.PERSONA, drawn)
            if a.is_standing and a.interval.from_lb <= position
        } | set(attrs)))
        for k, v in persona_facts:
            deps.add(fact_ref("attr", drawn, k, v))

    target = TargetState(
        self_id=tid,
        persona_ids=tuple(obs_res.persona_ids),
        self_attributes=tuple(sorted(kept_attrs.items())),
        persona_attributes=persona_attrs,
        persona_facts=persona_facts,
    )

    # Facts in the store that the observer cannot see at this position, or
    # that were excluded by a task filter above -- either way, not allowed.
    for binding in all_aliases:
        if f"alias:{binding.alias}" not in allowed:
            forbidden.add(binding.alias)
    for attr in all_attrs:
        if f"attr:{attr.key}={attr.value}" not in allowed:
            forbidden.add(attr.value)
            forbidden.add(f"{attr.key}: {attr.value}")

    return _TargetFold(
        target=target,
        persona_ids=tuple(persona_ids),
        allowed=frozenset(allowed),
        forbidden=frozenset(forbidden),
        deps=frozenset(deps),
    )


def compile_generation_state(
    store: Store,
    novel_id: str,
    target_ids: Iterable[str],
    *,
    position: StoryPos,
    observer_id: str = OBSERVER_READER,
    knowledge_pos: DiscoursePosition | None = None,
    resolver: StateResolver | None = None,
    persona_reader: PersonaReader | None = None,
) -> GenerationState:
    """Compile an explicit GenerationState for a set of target entities.

    `resolver`, when given, is reused (its voided-timeline pre-pass is the
    expensive part of constructing one) and must already carry `observer_id`.
    `persona_reader` supplies the persona attributes the calling modality
    consumes at this position; without it no persona attributes are compiled
    and none enter the digest.
    """
    resolver = resolver or StateResolver(store, novel_id, default_observer=observer_id)
    targets = list(dict.fromkeys(target_ids))  # de-duplicated, order-preserving

    visible_ids: list[str] = []
    persona_ids: list[str] = []
    allowed: set[str] = set()
    forbidden: set[str] = set()
    provenance: set[str] = set()
    deps: set[str] = set()
    compiled: list[TargetState] = []

    for tid in targets:
        obs_res = resolver.state_of(
            tid, position=position, observer_id=observer_id, knowledge_pos=knowledge_pos
        )
        provenance.update(obs_res.read_set)

        fold = _fold_target(tid, obs_res, store, position, persona_reader)
        if obs_res.persona_ids:
            visible_ids.append(tid)
        persona_ids.extend(fold.persona_ids)
        allowed.update(fold.allowed)
        forbidden.update(fold.forbidden)
        deps.update(fold.deps)
        compiled.append(fold.target)

    k_pos = (
        knowledge_pos
        if knowledge_pos is not None
        else DiscoursePosition(chapter=int(position) if position != float("inf") else 10**6)
    )

    return GenerationState(
        observer_id=observer_id,
        story_position=position,
        knowledge_pos=k_pos,
        visible_identities=tuple(sorted(set(visible_ids))),
        persona_bindings=tuple(sorted(set(persona_ids))),
        allowed_facts=tuple(sorted(allowed)),
        forbidden_facts=tuple(sorted(forbidden)),
        provenance_refs=tuple(sorted(provenance)),
        read_set=tuple(sorted(deps)),
        targets=tuple(sorted(compiled, key=lambda t: t.self_id)),
    )
