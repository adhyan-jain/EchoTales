"""`SceneState`: scene-level ground truth (location/crowd_mood/severity),
stored as a floor a consumer reads and may refine locally without mutating
the stored row. See models.py::SceneState's own docstring for why the
fields are deliberately vocabulary-free.
"""

from __future__ import annotations

from echotales.core.models import DiscoursePosition, NarrativeSegment, SceneState
from echotales.core.store import Store

NOVEL = "n"


def _segment(seg_id: str = "seg1") -> NarrativeSegment:
    return NarrativeSegment(
        id=seg_id,
        novel_id=NOVEL,
        chapter_from=1,
        offset_from=0,
        chapter_to=1,
        offset_to=100,
        story_seq_from=1,
        story_seq_to=1,
    )


def test_round_trip() -> None:
    store = Store(":memory:")
    store.add_segments([_segment()])

    state = SceneState(
        id="ss1",
        novel_id=NOVEL,
        segment_id="seg1",
        location="devil lair, mountain siege",
        crowd_mood="crowd",
        default_severity="wounded",
        extra={"note": "opening siege"},
        set_at_position=DiscoursePosition(chapter=1, offset=0),
    )
    store.add_scene_state(state)
    store.conn.commit()

    got = store.get_scene_state(NOVEL, "seg1")
    assert got is not None
    assert got == state


def test_none_crowd_mood_round_trips() -> None:
    store = Store(":memory:")
    store.add_segments([_segment()])

    state = SceneState(
        id="ss1",
        novel_id=NOVEL,
        segment_id="seg1",
        location="quiet study",
        crowd_mood=None,
        default_severity="unharmed",
        set_at_position=DiscoursePosition(chapter=1, offset=0),
    )
    store.add_scene_state(state)
    store.conn.commit()

    got = store.get_scene_state(NOVEL, "seg1")
    assert got is not None
    assert got.crowd_mood is None


def test_closed_state_is_superseded_by_the_newer_row() -> None:
    """Two states for the same segment, older one closed: `get_scene_state`
    must return the newer, not-closed row -- "what do we currently believe"
    semantics, not "the first thing ever recorded"."""
    store = Store(":memory:")
    store.add_segments([_segment()])

    old = SceneState(
        id="ss_old",
        novel_id=NOVEL,
        segment_id="seg1",
        location="courtyard",
        set_at_position=DiscoursePosition(chapter=1, offset=0),
    )
    new = SceneState(
        id="ss_new",
        novel_id=NOVEL,
        segment_id="seg1",
        location="mountain path",
        set_at_position=DiscoursePosition(chapter=1, offset=50),
    )
    store.add_scene_state(old)
    store.add_scene_state(new)
    store.close_scene_state("ss_old")
    store.conn.commit()

    got = store.get_scene_state(NOVEL, "seg1")
    assert got is not None
    assert got.id == "ss_new"
    assert got.location == "mountain path"


def test_all_closed_falls_back_to_the_latest_row() -> None:
    """If every row for a segment has been closed (an edge case, not the
    expected steady state), return the latest one rather than nothing --
    a stale-but-present answer beats a silent None a caller has to special-
    case."""
    store = Store(":memory:")
    store.add_segments([_segment()])

    state = SceneState(
        id="ss1",
        novel_id=NOVEL,
        segment_id="seg1",
        location="courtyard",
        set_at_position=DiscoursePosition(chapter=1, offset=0),
    )
    store.add_scene_state(state)
    store.close_scene_state("ss1")
    store.conn.commit()

    got = store.get_scene_state(NOVEL, "seg1")
    assert got is not None
    assert got.id == "ss1"
    assert got.closed is True


def test_missing_segment_returns_none() -> None:
    store = Store(":memory:")
    assert store.get_scene_state(NOVEL, "no-such-segment") is None
