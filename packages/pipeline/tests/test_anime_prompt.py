"""The words the video engine gets. A wide silhouette sent only "slight breathing, hair moving" grew a photographic face."""

from __future__ import annotations

import json
import shutil

import pytest
from _anime_helpers import FAKE_CAP, OUT_H, OUT_W, FakeEngine, build_chapter, same_content_embedder
from echotales.pipeline.render import anime
from echotales.pipeline.render.plan import load_panel_plan
from echotales.pipeline.render.shots import ShotBudget, plan_shots
from echotales.pipeline.voice.timing import build_timing


def _shot_and_panel(tmp_path, **direction):
    panels, audio = build_chapter(tmp_path)
    plan = load_panel_plan(panels)
    shots = plan_shots(plan, build_timing(audio, 1.0), FAKE_CAP, ShotBudget())
    panel = plan[2]  # the ANIMATE shot
    d = panel.direction.model_copy(update=direction) if direction else panel.direction
    return shots[2], panel.model_copy(update={"direction": d})


def test_close_up_with_direction_keeps_face_motion_and_a_static_camera(tmp_path) -> None:
    shot, panel = _shot_and_panel(tmp_path, shot="close", layout="face fills the frame",
                                  setting="stone_courtyard", key_objects=["lantern"])
    p = anime.build_video_prompt(shot, panel)
    assert p.startswith(anime.STYLE_ANCHOR)
    assert "face fills the frame, stone courtyard, lantern, b" in p  # layout, de-tagged setting, objects, cast
    assert "turns slowly" in p and "calm" in p and p.endswith("static camera")


def test_wide_shot_is_ambient_only(tmp_path) -> None:
    shot, panel = _shot_and_panel(tmp_path, shot="wide", layout="lone figure far away")
    p = anime.build_video_prompt(shot, panel)
    assert anime.AMBIENT_MOTION in p and "turns slowly" not in p and "calm" not in p
    for word in ("breath", "blink", "hair", "face"):
        assert word not in p.lower()


def test_establishing_panel_is_ambient_only(tmp_path) -> None:
    shot, panel = _shot_and_panel(tmp_path)
    p = anime.build_video_prompt(shot, panel.model_copy(update={"slot_kind": "establishing"}))
    assert anime.AMBIENT_MOTION in p and "turns slowly" not in p


def test_planner_marked_ambient_is_ambient_only(tmp_path) -> None:
    shot, panel = _shot_and_panel(tmp_path)
    shot = shot.model_copy(update={"reasons": [*shot.reasons, "ambient motion only: no character motion"]})
    assert anime.AMBIENT_MOTION in anime.build_video_prompt(shot, panel)


def test_no_direction_uses_a_detagged_subject_from_the_image_prompt(tmp_path) -> None:
    shot, panel = _shot_and_panel(tmp_path)
    shot = shot.model_copy(update={"motion_prompt": ""})
    panel = panel.model_copy(update={"direction": None, "prompt": (
        "1boy, solo, male focus, guofeng illustration, score_9, medium shot, Fang_Yuan, long_black_hair, "
        "green_robe, stone_courtyard, highly detailed")})
    p = anime.build_video_prompt(shot, panel)
    assert "Fang Yuan, long black hair, green robe, stone courtyard" in p
    assert "score_9" not in p and "1boy" not in p and "subtle natural motion" in p


def test_derived_end_gets_the_push_in_and_panel_end_gets_camera_movement(tmp_path) -> None:
    panels, audio = build_chapter(tmp_path)
    plan = load_panel_plan(panels)
    shots = plan_shots(plan, build_timing(audio, 1.0), FAKE_CAP, ShotBudget())
    derived = anime.build_video_prompt(shots[1], plan[1])
    assert derived.endswith("slow steady push-in") and derived.count("push-in") == 1
    assert anime.build_video_prompt(shots[0], plan[0]).endswith("smooth continuous camera movement")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_the_prompt_sent_is_recorded_in_shots_jsonl(tmp_path) -> None:
    panels, audio = build_chapter(tmp_path)
    result = anime.render_shots(
        panels_dir=panels, audio_dir=audio, out_root=tmp_path / "video" / "ch1", capability=FAKE_CAP,
        budget=ShotBudget(), engine=FakeEngine(), captions=False, width=OUT_W, height=OUT_H,
        embedder=same_content_embedder,
    )
    rows = [json.loads(ln) for ln in (result.out_dir / "shots.jsonl").read_text().splitlines()]
    assert rows[2]["outcome"]["prompt"].startswith(anime.STYLE_ANCHOR)
    assert rows[3]["outcome"]["prompt"] is None  # a hold has none


def test_no_empty_clauses_in_the_prompt(tmp_path) -> None:
    panels, audio = build_chapter(tmp_path)
    plan = load_panel_plan(panels)
    shots = plan_shots(plan, build_timing(audio, 1.0), FAKE_CAP, ShotBudget())
    for shot, panel in zip(shots[:3], plan[:3], strict=True):
        assert ", ," not in anime.build_video_prompt(shot, panel)
