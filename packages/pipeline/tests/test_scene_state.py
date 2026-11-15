"""Tests for `render/scene_state.py`: the transient-severity classifier and
`SceneState` derivation/storage from a `Scene`."""

from __future__ import annotations

from echotales.core.models import DiscoursePosition, NarrativeSegment
from echotales.core.store import Store
from echotales.pipeline.render.scene_state import (
    classify_transient_severity,
    derive_scene_state,
    get_or_derive_scene_state,
)
from echotales.pipeline.render.scenes import Scene
from echotales.pipeline.spans.scene import MobDescriptor


def test_classify_transient_severity_tiers() -> None:
    assert classify_transient_severity("") == "unharmed"
    assert classify_transient_severity("he walked calmly into the hall") == "unharmed"
    assert classify_transient_severity("his robes were torn") == "roughed_up"
    assert classify_transient_severity("blood dripped from his sleeve") == "roughed_up"
    assert classify_transient_severity("he was wounded in the arm") == "wounded"
    assert classify_transient_severity("wounded and covered in blood") == "gravely_wounded"
    assert classify_transient_severity("he was gravely injured") == "gravely_wounded"
    assert classify_transient_severity("critically wounded, dying") == "gravely_wounded"


def _scene(segment_id: str = "seg1") -> Scene:
    return Scene(index=0, blocks=[0, 1, 2], segment_id=segment_id)


def test_derive_scene_state_mob_scene_sets_crowd_mood() -> None:
    scene = _scene()
    mobs = [MobDescriptor(text="a crowd of cultivators", role="cultivators", offset=0, block_index=0)]
    state = derive_scene_state(
        store=Store(":memory:"),
        novel_id="n",
        scene=scene,
        scene_text="a crowd of cultivators gathered around Fang Yuan",
        scene_narration="a crowd of cultivators gathered around Fang Yuan",
        mobs=mobs,
        story_scene_block_count=3,
        position=DiscoursePosition(chapter=1, offset=0),
    )
    assert state.crowd_mood == "crowd"
    assert state.segment_id == "seg1"


def test_derive_scene_state_dialogue_scene_has_no_crowd_mood() -> None:
    scene = _scene()
    state = derive_scene_state(
        store=Store(":memory:"),
        novel_id="n",
        scene=scene,
        scene_text="Fang Yuan spoke quietly to the elder.",
        scene_narration="Fang Yuan spoke quietly to the elder.",
        mobs=[],
        story_scene_block_count=3,
        position=DiscoursePosition(chapter=1, offset=0),
    )
    assert state.crowd_mood is None


def test_derive_scene_state_single_block_mob_scene_has_no_crowd_slot() -> None:
    """Mirrors panels.py's own gate: a mob phrase alone isn't enough -- the
    scene also needs more than one block, matching `_crowd_slot`'s
    allocation condition exactly so `SceneState` never disagrees with it."""
    scene = _scene()
    mobs = [MobDescriptor(text="a crowd", role="crowd", offset=0, block_index=0)]
    state = derive_scene_state(
        store=Store(":memory:"),
        novel_id="n",
        scene=scene,
        scene_text="a crowd gathered",
        scene_narration="a crowd gathered",
        mobs=mobs,
        story_scene_block_count=1,
        position=DiscoursePosition(chapter=1, offset=0),
    )
    assert state.crowd_mood is None


def _segment(seg_id: str) -> NarrativeSegment:
    return NarrativeSegment(
        id=seg_id,
        novel_id="n",
        chapter_from=1,
        offset_from=0,
        chapter_to=1,
        offset_to=100,
        story_seq_from=1,
        story_seq_to=1,
    )


def test_get_or_derive_scene_state_is_idempotent() -> None:
    """A second call for the same segment must reuse the stored row, not
    re-derive -- the whole point of persisting it."""
    store = Store(":memory:")
    store.add_segments([_segment("seg1")])
    scene = _scene("seg1")

    first = get_or_derive_scene_state(
        store, "n", scene, "a quiet courtyard", "a quiet courtyard", [], 3,
        DiscoursePosition(chapter=1, offset=0),
    )
    store.conn.commit()

    # Different text on the second call -- if this were re-derived, the
    # location/severity would change. It must not.
    second = get_or_derive_scene_state(
        store, "n", scene, "a bloodied battlefield", "a bloodied battlefield", [], 3,
        DiscoursePosition(chapter=1, offset=50),
    )
    assert second.id == first.id
    assert second.default_severity == first.default_severity


def test_get_or_derive_scene_state_without_segment_id_still_returns_a_state() -> None:
    """`Scene.segment_id` empty (no `ActiveScene` covered these blocks) must
    still return a usable `SceneState`. It is stored too, keyed by its own id
    (see `test_scene_without_segment_id_is_persisted_and_reused`)."""
    store = Store(":memory:")
    scene = _scene(segment_id="")
    state = get_or_derive_scene_state(
        store, "n", scene, "a quiet courtyard", "a quiet courtyard", [], 3,
        DiscoursePosition(chapter=1, offset=0),
    )
    assert state.segment_id == ""
    assert store.get_scene_state_by_id(state.id) is not None


def test_two_scenes_in_one_segment_each_get_their_own_state() -> None:
    """Looked up by segment alone, every scene after the first reused scene 0's
    location, crowd mood and severity (the row id carried the scene index but
    the lookup did not)."""
    store = Store(":memory:")
    store.add_segments([_segment("seg1")])
    pos = DiscoursePosition(chapter=1, offset=0)
    crowd = [MobDescriptor(text="a crowd", role="crowd", offset=0, block_index=0)]
    first = get_or_derive_scene_state(
        store, "n", Scene(index=0, blocks=[0, 1, 2], segment_id="seg1"),
        "his robes were torn", "his robes were torn", crowd, 3, pos,
    )
    second = get_or_derive_scene_state(
        store, "n", Scene(index=1, blocks=[3, 4], segment_id="seg1"),
        "a quiet courtyard", "a quiet courtyard", [], 2, pos,
    )
    assert first.crowd_mood == "crowd" and first.default_severity == "roughed_up"
    assert second.id != first.id
    assert second.crowd_mood is None
    assert second.default_severity == "unharmed"


def test_same_scene_index_in_two_chapters_of_one_segment_does_not_collide() -> None:
    """A segment can span chapters, and `Scene.index` restarts at 0 per chapter."""
    store = Store(":memory:")
    store.add_segments([_segment("seg1")])
    a = get_or_derive_scene_state(
        store, "n", _scene(), "his robes were torn", "his robes were torn", [], 3,
        DiscoursePosition(chapter=1, offset=0), chapter_number=1.0,
    )
    b = get_or_derive_scene_state(
        store, "n", _scene(), "a quiet courtyard", "a quiet courtyard", [], 3,
        DiscoursePosition(chapter=1, offset=0), chapter_number=1.5,
    )
    assert a.id != b.id
    assert (a.default_severity, b.default_severity) == ("roughed_up", "unharmed")


def test_scene_without_segment_id_is_persisted_and_reused() -> None:
    """It used to be re-derived on every call, so a second pass could drift."""
    store = Store(":memory:")
    scene = _scene(segment_id="")
    pos = DiscoursePosition(chapter=1, offset=0)
    first = get_or_derive_scene_state(
        store, "n", scene, "his robes were torn", "his robes were torn", [], 3, pos
    )
    second = get_or_derive_scene_state(
        store, "n", scene, "a quiet courtyard", "a quiet courtyard", [], 3, pos
    )
    assert second.id == first.id
    assert second.default_severity == "roughed_up"
