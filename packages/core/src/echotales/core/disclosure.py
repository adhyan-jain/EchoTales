"""Minimal Disclosure Compiler -- task-conditioned evidence minimization.

`state_of()`/`compile_generation_state()` (`state.py`) answer "what CAN this
observer know at this position" -- the observer- and temporally-valid
*candidate* set. Nothing downstream of that call answers the narrower
question a specific generation task actually needs. Confirmed by reading the
one production consumer directly: `render/panels.py::character_looks` reads
only `gen_state.persona_for(...)` and `gen_state.appearance_for(...)`
(`panels.py:1369-1373`) -- it never touches `TargetState.self_attributes` or
relationships at all, yet `compile_generation_state` compiles and hashes
every observer-valid self attribute and relationship into every
`GenerationState` regardless (`state.py::_fold_target`, called unfiltered).
That gap -- a real candidate set systematically larger than what any given
task reads -- is what this module closes.

This module never re-derives observer/temporal/truth-status filtering; that
is `StateResolver.state_of()`'s job and it is already correct and tested. It
only ever *narrows* an already-valid candidate set, per a `TaskSpec`'s
declared requirements, via greedy coverage plus dependency closure -- not
top-k truncation. `world/context.py::_MAX_FACTS_PER_ENTITY` is that, already
shipped, and is the baseline this module is measured against (see
`scripts/eval/mdc_disclosure_ablation.py`), not a building block reused here.

The hard invariant, asserted in `packages/core/tests/test_disclosure.py`:
a `DisclosureResult`'s `allowed_facts`/`read_set` are always subsets of what
`compile_generation_state` would have produced for the same inputs. This
module removes facts; it never adds one `state_of` did not already clear.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from echotales.core.enums import OBSERVER_READER, TargetKind
from echotales.core.interval import StoryPos
from echotales.core.models import DiscoursePosition
from echotales.core.state import (
    GenerationState,
    PersonaReader,
    StateResolver,
    _fold_target,
)
from echotales.core.store import Store


@dataclass(slots=True, frozen=True)
class TaskSpec:
    """Declares what a generation task needs, not what it is allowed to see.

    `required_keys` is looked up by `TargetKind`; a required key with no
    matching candidate fact lands in `DisclosureResult.unsatisfied_keys`
    rather than being treated as an error -- that is a graph-content gap,
    not a filtering bug, and reporting it (rather than silently proceeding
    without it) is the point of surfacing it at all.

    Deliberately does not import `world/schema.py::keys_for` -- that lives in
    `packages/pipeline`, and `packages/core` (this module's home) must import
    nothing from it. A pipeline-layer caller is free to pass `keys_for(...)`'s
    output in as `required_keys`.
    """

    task_id: str
    required_keys: Mapping[TargetKind, frozenset[str]] = field(default_factory=dict)
    #: Whether the task needs a bound persona at all (render does; a task
    #: that only reasons about a Self's standing facts may not).
    require_persona: bool = True
    #: Whether a relationship to another *selected* target is in-scope for
    #: this task. `compile_generation_state` includes every SELF
    #: relationship unconditionally (`state.py`); this flag is the actual
    #: task-conditioned coverage decision MDC makes instead.
    require_relationships: bool = False
    #: Whether the task needs at least one name-bearing fact per target.
    #: True for almost everything -- a generation task that cannot name its
    #: subject is a rare, deliberate exception.
    require_name: bool = True
    #: Safety valve only. Every production call in this codebase leaves this
    #: unset (None); it exists so the experiment harness can force a capped
    #: variant for comparison against the top-k baseline.
    max_facts_per_target: int | None = None


@dataclass(slots=True, frozen=True)
class DisclosureResult:
    """`GenerationState`-shaped, narrower in content than the candidate set."""

    state: GenerationState
    #: Refs present in the observer-valid candidate set but not selected --
    #: the material for computing evidence-reduction % and for checking
    #: whether the drop was ever load-bearing.
    dropped_facts: tuple[str, ...]
    #: Required keys with no candidate fact at all, per target.
    unsatisfied_keys: tuple[str, ...]
    source_candidate_count: int
    selected_count: int


def _disambiguating_aliases(
    aliases_by_target: Mapping[str, tuple[str, ...]],
) -> dict[str, set[str]]:
    """Which of each target's aliases are needed to name it unambiguously
    within this batch.

    Every target keeps one name-bearing alias unconditionally: its *primary*
    pick, the first by the store's own ordering (the same "take the first"
    convention `compile_generation_state`/`build_render_plan` already use for
    personas). When two or more targets in this batch share the same
    normalized primary pick (a transferable title held by both, an epithet
    that collides), each of those targets additionally keeps the first
    further alias of its own that the *other* colliding targets do not also
    hold -- the minimum needed to break the tie. A target whose primary pick
    is already unique gets nothing more, even if a later alias happens to be
    unique too: an alias that was never needed to disambiguate anything is
    not naming evidence, just more text, so this is scoped to the current
    batch rather than a whole-novel `resolve_alias` lookup -- "ambiguous"
    here means "ambiguous among the entities this generation call actually
    names," which is the only ambiguity a downstream prompt can be confused
    by.
    """
    from echotales.core.readset import normalize as normalize_alias

    kept: dict[str, set[str]] = {tid: set() for tid in aliases_by_target}
    primary: dict[str, str] = {}
    for tid, aliases in aliases_by_target.items():
        if not aliases:
            continue
        primary[tid] = aliases[0]
        kept[tid].add(aliases[0])

    primary_groups: dict[str, set[str]] = {}
    for tid, a in primary.items():
        primary_groups.setdefault(normalize_alias(a), set()).add(tid)

    for group in primary_groups.values():
        if len(group) <= 1:
            continue
        for tid in group:
            others_aliases = {a for other in group - {tid} for a in aliases_by_target[other]}
            for a in aliases_by_target[tid][1:]:
                if a not in others_aliases:
                    kept[tid].add(a)
                    break
    return kept


def compile_minimal_disclosure(
    store: Store,
    novel_id: str,
    target_ids: Iterable[str],
    task_spec: TaskSpec,
    *,
    position: StoryPos,
    observer_id: str = OBSERVER_READER,
    knowledge_pos: DiscoursePosition | None = None,
    resolver: StateResolver | None = None,
    persona_reader: PersonaReader | None = None,
) -> DisclosureResult:
    """Compile the minimum sufficient `GenerationState` for `task_spec`.

    Calls `resolver.state_of()` directly per target (the same call
    `compile_generation_state` makes internally) rather than calling
    `compile_generation_state()` itself, because its fold-in already
    collapses attribute-key collisions before this function would get a
    chance to select among them. `StateResolver`'s voided-timeline pre-pass
    and observation cache are still shared/reused when a resolver is passed
    in, so this costs no extra queries relative to
    `compile_generation_state` for the same batch.
    """
    resolver = resolver or StateResolver(store, novel_id, default_observer=observer_id)
    targets = list(dict.fromkeys(target_ids))

    obs_results = {
        tid: resolver.state_of(
            tid, position=position, observer_id=observer_id, knowledge_pos=knowledge_pos
        )
        for tid in targets
    }

    kept_aliases = (
        _disambiguating_aliases({tid: tuple(res.aliases) for tid, res in obs_results.items()})
        if task_spec.require_name
        else {tid: set() for tid in targets}
    )

    target_set = set(targets)

    visible_ids: list[str] = []
    persona_ids: list[str] = []
    allowed: set[str] = set()
    forbidden: set[str] = set()
    provenance: set[str] = set()
    deps: set[str] = set()
    compiled = []
    unsatisfied: list[str] = []
    candidate_count = 0
    selected_count = 0

    for tid in targets:
        obs_res = obs_results[tid]
        provenance.update(obs_res.read_set)
        candidate_count += len(obs_res.aliases) + len(obs_res.attributes) + len(obs_res.relationships)

        target_kind = TargetKind.SELF
        required = task_spec.required_keys.get(target_kind, frozenset())
        attribute_keys = frozenset(k for k in obs_res.attributes if k in required)
        for k in required:
            if k not in obs_res.attributes:
                unsatisfied.append(f"{tid}:{k}")

        relation_dsts = (
            frozenset(dst for _rel, dst in obs_res.relationships if dst in target_set)
            if task_spec.require_relationships
            else frozenset()
        )

        alias_values = frozenset(kept_aliases.get(tid, set()))

        persona_reader_for_target = persona_reader if task_spec.require_persona else None

        fold = _fold_target(
            tid,
            obs_res,
            store,
            position,
            persona_reader_for_target,
            attribute_keys=attribute_keys,
            alias_values=alias_values,
            relation_dsts=relation_dsts,
        )
        if obs_res.persona_ids:
            # An identity is "visible" (present, nameable) whether or not
            # this task draws/voices its persona -- `covers()` tracks
            # identity presence, not persona-attribute presence.
            visible_ids.append(tid)
        if task_spec.require_persona:
            persona_ids.extend(fold.persona_ids)
        allowed.update(fold.allowed)
        forbidden.update(fold.forbidden)
        deps.update(fold.deps)
        compiled.append(fold.target)
        selected_count += len(fold.allowed)

    k_pos = (
        knowledge_pos
        if knowledge_pos is not None
        else DiscoursePosition(chapter=int(position) if position != float("inf") else 10**6)
    )

    state = GenerationState(
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

    return DisclosureResult(
        state=state,
        dropped_facts=tuple(sorted(forbidden)),
        unsatisfied_keys=tuple(sorted(unsatisfied)),
        source_candidate_count=candidate_count,
        selected_count=selected_count,
    )
