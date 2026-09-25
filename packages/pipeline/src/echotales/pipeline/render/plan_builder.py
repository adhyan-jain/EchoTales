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

from echotales.core.enums import OBSERVER_READER, TargetKind
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.pipeline.persona.reference_gen import reference_path_for
from echotales.pipeline.render.contract import (
    CharacterRenderSpec,
    CharacterRole,
    CompositionSpec,
    EnvironmentRenderSpec,
    VisualRenderPlan,
    _digest,
)


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
) -> VisualRenderPlan:
    """Build one panel's `VisualRenderPlan` from canonical state.

    `resolver`, when given, lets a caller rendering many panels in one run
    (`render_panels`'s per-chapter loop) share one `StateResolver` instead
    of re-running its voided-timeline pre-pass per panel -- constructing a
    fresh one here would be correct but wasteful across a whole chapter.

    A `self_id` whose `state_of()` returns no `persona_ids` (no body bound
    yet at this story position) is recorded in `state_digest` -- its
    presence still affects provenance -- but produces no
    `CharacterRenderSpec`, since there is no persona to draw. This is the
    concrete mechanism behind the invariant "a panel at position P must use
    state corresponding to P": `state_of(..., position=chapter)` is what
    prevents a panel from picking up a body bound only later in the story.
    """
    resolver = resolver or StateResolver(store, novel_id, default_observer=observer_id)

    characters: list[CharacterRenderSpec] = []
    state_parts: list[str] = []
    for self_id in cast_self_ids:
        result = resolver.state_of(self_id, position=chapter)
        # The drawn persona's own attributes are hashed too. `state_of` on a
        # Self returns only Self-targeted attributes, and every appearance
        # attribute in the corpus is Persona-targeted, so before this a hair
        # or attire change reached neither the digest nor the prompt: the A7
        # ablation measured 23/23 affected panels served stale by the shipped
        # key (EVOLUTION 4.91). All bound persona ids stay in the digest on
        # purpose -- it over-invalidates on a new concurrent body, but keeps a
        # multi-binding case auditable (see below).
        drawn_attrs: tuple[tuple[str, str], ...] = ()
        if result.persona_ids:
            drawn_attrs = tuple(sorted(
                (a.key, a.value)
                for a in store.get_attributes(TargetKind.PERSONA, result.persona_ids[0])
                if a.is_standing
            ))
        state_parts.append(
            _digest(
                self_id,
                tuple(result.persona_ids),
                tuple(sorted(result.attributes.items())),
                drawn_attrs,
            )
        )
        if not result.persona_ids:
            continue
        # Concurrent bindings (clones, disguises) are legitimate per
        # `StateOfResult.persona_ids`'s own docstring, but resolving which
        # one a panel should draw is a Phase 4+ decision -- take the first
        # and let `state_digest` (which hashes every id returned, not just
        # this one) make a multi-binding case auditable rather than silent.
        persona_id = result.persona_ids[0]
        role = (
            CharacterRole.PRINCIPAL
            if self_id == lead_self_id
            else CharacterRole.SUPPORT
        )
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
        state_digest=_digest(*state_parts),
        resolver="state_of",
    )
