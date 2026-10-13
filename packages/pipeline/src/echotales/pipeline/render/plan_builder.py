"""Visual Rendering Track Phase 1c: build a `VisualRenderPlan` from real state.

Before this module, `render/contract.py`'s `VisualRenderPlan` existed only as
a typed shape -- nothing constructed one from actual novel data.
`build_render_plan` is the only place that should (per `VisualRenderPlan`'s
own docstring); it is a pure aggregator over functions that already exist
and already do the real resolution work:

- `core/state.py::StateResolver.state_of` for `persona_ids` -- never
  `persona/split.py::persona_at`, which `contract.py`'s `resolver` field
  exists specifically to distinguish from (the two can disagree; this
  module always uses `state_of` and records that fact rather than assuming
  it).
- `persona/reference_gen.py::reference_path_for` for the reference sheet,
  which already degrades a deleted file to `None` -- this module does not
  re-implement that check.
- `render/direction.py`'s already-computed `PanelDirection` fields
  (action/layout/expression/lighting/mood/shot) for pose/expression hints
  and composition -- reused verbatim, never recomputed.

Nothing here changes what a panel looks like. It packages data the render
loop already has into the typed shape `render/cache_key.py` needs to hash.
"""

from __future__ import annotations

from collections.abc import Sequence

from echotales.core.disclosure import TaskSpec, compile_minimal_disclosure
from echotales.core.enums import OBSERVER_READER
from echotales.core.models import DiscoursePosition
from echotales.core.state import GenerationState, StateResolver, compile_generation_state
from echotales.core.store import Store
from echotales.core.visual_memory import (
    DisclosurePolicy,
    VisualAssetRegistry,
    VisualMemorySelector,
    VisualRequest,
)
from echotales.pipeline.persona.reference_gen import appearance_of, reference_path_for
from echotales.pipeline.render.contract import (
    CharacterRenderSpec,
    CharacterRole,
    CompositionSpec,
    EnvironmentRenderSpec,
    VisualRenderPlan,
)

#: What the render task actually needs, confirmed by reading its one
#: consumer directly: `panels.py::character_looks` reads only
#: `gen_state.persona_for(...)` and `gen_state.appearance_for(...)`
#: (`panels.py:1369-1373`) -- it never reads `TargetState.self_attributes`,
#: relationships, or aliases from the compiled state at all (names in the
#: rendered prompt come from elsewhere, not from `GenerationState`). This is
#: the render task's honest sufficiency declaration for the Minimal
#: Disclosure Compiler experiment (`scripts/eval/mdc_disclosure_ablation.py`)
#: -- not a guess, and not the same as "render doesn't need much," which is
#: a separate, measured claim the experiment either confirms or refutes.
RENDER_TASK_SPEC = TaskSpec(
    task_id="render_panel",
    required_keys={},
    require_persona=True,
    require_relationships=False,
    require_name=False,
)


def compile_render_state(
    store: Store,
    novel_id: str,
    self_ids: Sequence[str],
    *,
    position: float,
    observer_id: str = OBSERVER_READER,
    resolver: StateResolver | None = None,
) -> GenerationState:
    """The one compile the image path reads.

    The persona reader is `appearance_of(position=..., standing_only=False)`,
    the same call the panel prompt's `character_looks` makes, so the attributes
    hashed into the cache key are the attributes the prompt was built from --
    by construction rather than by two call sites agreeing. Concurrent
    bindings keep all persona ids in the state, but only the drawn (first)
    persona's attributes are read: an appearance change on a persona nobody
    draws must not invalidate the panel.
    """
    return compile_generation_state(
        store,
        novel_id,
        self_ids,
        position=position,
        observer_id=observer_id,
        resolver=resolver,
        persona_reader=lambda pid: appearance_of(store, pid, position=position, standing_only=False),
    )


def compile_render_state_minimal(
    store: Store,
    novel_id: str,
    self_ids: Sequence[str],
    *,
    position: float,
    observer_id: str = OBSERVER_READER,
    resolver: StateResolver | None = None,
) -> GenerationState:
    """The Minimal Disclosure Compiler's compile for the render task.

    Experiment-only alternative to `compile_render_state`, gated behind
    `build_render_plan(..., use_mdc=True)`. Same `persona_reader` (so the
    drawn appearance a real panel would use is unchanged either way) but
    routed through `compile_minimal_disclosure` with `RENDER_TASK_SPEC`
    instead of `compile_generation_state`'s unconditional inclusion of every
    observer-valid self attribute and relationship.
    """
    return compile_minimal_disclosure(
        store,
        novel_id,
        self_ids,
        RENDER_TASK_SPEC,
        position=position,
        observer_id=observer_id,
        resolver=resolver,
        persona_reader=lambda pid: appearance_of(store, pid, position=position, standing_only=False),
    ).state


def build_render_plan(
    store: Store,
    novel_id: str,
    *,
    chapter: float,
    beat_id: str,
    panel_seq: int,
    cast_self_ids: Sequence[str],
    lead_self_id: str | None = None,
    location: str = "",
    lighting: str = "",
    time_of_day: str = "",
    mood: str = "",
    shot: str = "",
    layout: str = "",
    is_crowd_cut: bool = False,
    pose_hint: str = "",
    expression_hint: str = "",
    resolver: StateResolver | None = None,
    #: Only consulted when `resolver` is not supplied; a caller sharing a
    #: resolver has already chosen the observer on it.
    observer_id: str = OBSERVER_READER,
    #: Where in the story the panel is set. Defaults to `chapter` (the chapter
    #: start). `render_panels` passes the fractional in-chapter position its
    #: prompt was built at: a body change lands mid-chapter (RI's Fang Yuan is
    #: reborn partway through chapter 1), and resolving at the chapter start
    #: hashed the pre-rebirth body into the cache key of a panel that was
    #: drawn from the post-rebirth one.
    position: float | None = None,
    #: A state the caller already compiled for this cast at this position
    #: (the same one the prompt was built from). Recompiled when it does not
    #: cover `cast_self_ids`.
    gen_state: GenerationState | None = None,
    #: Experiment flag for `scripts/eval/mdc_disclosure_ablation.py`: routes
    #: the (re)compile through `compile_render_state_minimal` instead of
    #: `compile_render_state` when no `gen_state` is supplied. False by
    #: default, so every existing caller's behavior is unchanged byte for
    #: byte; not intended for use outside the ablation harness.
    use_mdc: bool = False,
    #: Optional Reveal-Aware Visual Memory registry. When supplied, character
    #: reference paths are selected via `VisualMemorySelector` under explicit
    #: provenance and disclosure cutoff gates rather than legacy flat reads.
    #: Default None preserves exact existing behavior byte for byte.
    visual_registry: VisualAssetRegistry | None = None,
    discourse_cutoff: DiscoursePosition | None = None,
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.IN_SEQUENCE,
) -> VisualRenderPlan:
    """Build one panel's `VisualRenderPlan` from a compiled `GenerationState`.

    A `self_id` with no bound persona at this position is recorded in the state
    (its presence still affects the digest) but produces no
    `CharacterRenderSpec`, since there is no persona to draw. The persona is
    the compiled state's first bound persona -- the same "take the first" rule
    `character_looks` uses; concurrent bindings stay in the state so a
    multi-binding case is auditable rather than silent.
    """
    from pathlib import Path

    resolver = resolver or StateResolver(store, novel_id, default_observer=observer_id)
    at = chapter if position is None else position
    if gen_state is None or not gen_state.covers(cast_self_ids):
        compile_fn = compile_render_state_minimal if use_mdc else compile_render_state
        gen_state = compile_fn(
            store, novel_id, cast_self_ids, position=at,
            observer_id=resolver.default_observer, resolver=resolver,
        )

    characters: list[CharacterRenderSpec] = []
    for self_id in cast_self_ids:
        persona_id = gen_state.persona_for(self_id)
        if persona_id is None:
            continue
        role = (
            CharacterRole.PRINCIPAL
            if self_id == lead_self_id
            else CharacterRole.SUPPORT
        )
        if visual_registry is not None:
            cutoff = discourse_cutoff or DiscoursePosition(chapter=int(at), offset=0)
            v_req = VisualRequest(
                self_id=self_id,
                story_pos=at,
                discourse_cutoff=cutoff,
                observer_id=resolver.default_observer,
                policy=disclosure_policy,
                target_persona_id=persona_id,
            )
            v_selector = VisualMemorySelector(store, novel_id=novel_id, resolver=resolver)
            v_res = v_selector.select(v_req, visual_registry)
            ref_path = (
                Path(v_res.selected_asset.image_path)
                if v_res.selected_asset and v_res.selected_asset.image_path
                else None
            )
        else:
            ref_path = reference_path_for(store, persona_id)
        characters.append(
            CharacterRenderSpec(
                persona_id=persona_id,
                self_id=self_id,
                role=role,
                reference_paths=(ref_path,) if ref_path is not None else (),
                pose_hint=pose_hint,
                expression_hint=expression_hint,
            )
        )

    return VisualRenderPlan(
        novel_id=novel_id,
        chapter=chapter,
        beat_id=beat_id,
        panel_seq=panel_seq,
        characters=tuple(characters),
        environment=EnvironmentRenderSpec(
            location=location,
            lighting=lighting,
            time_of_day=time_of_day,
            mood=mood,
        ),
        composition=CompositionSpec(
            shot=shot, layout=layout, is_crowd_cut=is_crowd_cut
        ),
        state_digest=gen_state.digest(),
        resolver="state_of",
    )
