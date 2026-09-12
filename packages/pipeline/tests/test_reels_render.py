import pytest
from echotales.pipeline.render.reels import (
    CameraMotionType,
    ReelStylePreset,
    build_reel_plan_for_chapter,
    derive_reel_pacing,
    select_reel_style,
)


def test_select_reel_style_per_novel():
    assert select_reel_style("reverend-insanity") == ReelStylePreset.EPIC_CULTIVATION
    assert select_reel_style("lord-of-the-mysteries") == ReelStylePreset.MYSTIC_NOIR
    assert select_reel_style("omniscient-readers-viewpoint") == ReelStylePreset.MANHWA_ACTION


def test_derive_reel_pacing_action_fast():
    pacing = derive_reel_pacing("ACTION", 30)
    assert 1.2 <= pacing <= 2.0


def test_build_reel_plan_generates_916_aspect_specs():
    beats = [
        {"type": "ACTION", "text": "Fang Yuan slashed his blade forward with demonic qi!"},
        {"type": "INNER_MONOLOGUE", "text": "With the Spring Autumn Cicada, I have been reborn..."},
    ]
    plan = build_reel_plan_for_chapter("reverend-insanity", 1.0, beats)
    assert plan.target_aspect_ratio == "9:16"
    assert len(plan.beats) == 2
    assert plan.beats[0].aspect_ratio == "9:16"
    assert plan.beats[0].camera_motion in (CameraMotionType.DUTCH_ANGLE_SHAKE, CameraMotionType.QUICK_PAN_RIGHT)
    assert plan.beats[1].camera_motion == CameraMotionType.SLOW_ZOOM_IN
    assert plan.total_duration > 2.0
