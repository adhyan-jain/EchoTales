"""Derive and persist `SceneState` -- scene-level ground truth (location,
crowd mood, transient-condition floor) -- from the same per-scene
computation `render/panels.py` already does, so it exists in one place
instead of being silently re-derived by every caller.

**Why this module, not a new heuristic.** `location` is literally
`persona/attire.py::scene_locale`, already called once per `Scene` in
`panels.py`; `crowd_mood` is the same `detect_mobs` gate `panels.py` already
uses to decide whether a dedicated crowd slot exists. This module's only
new logic is `classify_transient_severity` (2.4) -- everything else is
"compute once, store it, let the second consumer read the stored row
instead of re-deriving a possibly-different answer."
"""

from __future__ import annotations

from echotales.core.models import DiscoursePosition, SceneState
from echotales.core.store import Store
from echotales.pipeline.persona.attire import scene_locale
from echotales.pipeline.render.scenes import Scene
from echotales.pipeline.spans.scene import MobDescriptor

#: Weakest-to-strongest, consumer-owned ordering -- this module interprets
#: the tag, `SceneState` itself stays opaque to it (see its docstring).
_SEVERITY_TIERS: tuple[str, ...] = ("unharmed", "roughed_up", "wounded", "gravely_wounded")

_GRAVE_QUALIFIERS = ("gravely", "dying", "critically")


def classify_transient_severity(text: str) -> str:
    """Nearest fixed tier for a scene's overall physical-condition floor,
    reusing `apply_transient_overrides`'s own keyword sets rather than a
    second, possibly-inconsistent vocabulary. Never raw prose -- one of
    `_SEVERITY_TIERS`, always."""
    if not text:
        return "unharmed"

    low = text.lower()
    has_blood = any(w in low for w in ("blood", "bloodied", "bloody", "bleeding"))
    has_wounded = any(w in low for w in ("wounded", "injured", "wound", "injury"))
    has_torn = any(
        w in low for w in ("torn", "shredded", "tattered", "ragged", "ripped", "shreds", "damaged")
    )
    has_grave = any(w in low for w in _GRAVE_QUALIFIERS)

    if has_grave or (has_wounded and has_blood):
        return "gravely_wounded"
    if has_wounded:
        return "wounded"
    if has_torn or has_blood:
        return "roughed_up"
    return "unharmed"


def derive_scene_state(
    store: Store,
    novel_id: str,
    scene: Scene,
    scene_text: str,
    scene_narration: str,
    mobs: list[MobDescriptor],
    story_scene_block_count: int,
    position: DiscoursePosition,
) -> SceneState:
    """Compute a `SceneState` for one `Scene`. Does not persist it -- see
    `get_or_derive_scene_state` for the store-then-read wrapper callers
    should actually use."""
    location = scene_locale(novel_id, scene_text, block_index=scene.blocks[0])
    # Same gate `panels.py` already uses to decide whether a `_crowd_slot`
    # gets allocated at all -- reused, not reinvented.
    crowd_mood = "crowd" if (mobs and story_scene_block_count > 1) else None
    default_severity = classify_transient_severity(scene_narration)

    return SceneState(
        id=f"{novel_id}:{scene.segment_id}:{scene.index}",
        novel_id=novel_id,
        segment_id=scene.segment_id,
        location=location,
        crowd_mood=crowd_mood,
        default_severity=default_severity,
        set_at_position=position,
    )


def get_or_derive_scene_state(
    store: Store,
    novel_id: str,
    scene: Scene,
    scene_text: str,
    scene_narration: str,
    mobs: list[MobDescriptor],
    story_scene_block_count: int,
    position: DiscoursePosition,
) -> SceneState:
    """Idempotent: a second render pass over the same chapter reuses the
    stored row instead of re-deriving and drifting. `scene.segment_id`
    empty (the `ActiveScene`-coverage gap `Scene.segment_id`'s own docstring
    notes) falls through to deriving without a store round-trip, since
    there is no segment key to store or look up against."""
    if not scene.segment_id:
        return derive_scene_state(
            store, novel_id, scene, scene_text, scene_narration, mobs,
            story_scene_block_count, position,
        )

    existing = store.get_scene_state(novel_id, scene.segment_id)
    if existing is not None and not existing.closed:
        return existing

    state = derive_scene_state(
        store, novel_id, scene, scene_text, scene_narration, mobs,
        story_scene_block_count, position,
    )
    store.add_scene_state(state)
    return state
