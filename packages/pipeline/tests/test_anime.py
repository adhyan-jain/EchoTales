"""The shot composer, with a fake video engine that writes real MP4s: modes, sync, cache, fallback, CLI."""

from __future__ import annotations

import json
import shutil
import subprocess

import numpy as np
import pytest
from _anime_helpers import (
    FAKE_CAP,
    OUT_H,
    OUT_W,
    FakeEngine,
    build_chapter,
    drifting_embedder,
    same_content_embedder,
)
from echotales.pipeline.cli import main
from echotales.pipeline.render import anime
from echotales.pipeline.render.plan import PANEL_PLAN_FILE, load_panel_plan
from echotales.pipeline.render.shots import (
    STILLS,
    DerivedEnd,
    ShotBudget,
    ShotMode,
    load_shots,
    plan_shots,
)
from echotales.pipeline.video.local import VideoEnvError
from echotales.pipeline.voice.timing import build_timing
from PIL import Image

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def _compose(tmp_path, engine, *, cap=FAKE_CAP, captions=False, panels=None, audio=None, **kw):
    if panels is None:
        panels, audio = build_chapter(tmp_path)
    return anime.render_shots(
        panels_dir=panels, audio_dir=audio, out_root=tmp_path / "video" / "ch1", capability=cap,
        budget=kw.pop("budget", ShotBudget()), engine=engine, captions=captions, width=OUT_W, height=OUT_H,
        embedder=kw.pop("embedder", same_content_embedder), **kw,
    )


def _duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _final(result) -> dict[int, str]:
    return {o.shot_index: o.final for o in result.outcomes}


class TestPlanFixture:
    def test_the_fixture_chapter_has_all_three_modes(self, tmp_path) -> None:
        panels, audio = build_chapter(tmp_path)
        shots = plan_shots(load_panel_plan(panels), build_timing(audio, 1.0), FAKE_CAP, ShotBudget())
        assert [s.mode for s in shots] == [
            ShotMode.INTERPOLATE, ShotMode.INTERPOLATE, ShotMode.ANIMATE, ShotMode.HOLD, ShotMode.HOLD,
        ]
        assert shots[0].end_panel_id and shots[1].end_derived


class TestDerivedEnd:
    def _gradient(self) -> Image.Image:
        row = np.tile(np.arange(100, dtype=np.uint8)[None, :], (50, 1))
        return Image.fromarray(np.stack([row] * 3, axis=-1))

    def test_same_size_and_centred_crop(self) -> None:
        out = anime.render_derived_end(self._gradient(), DerivedEnd(scale=2.0))
        assert out.size == (100, 50)
        # The centre half of a 0..99 ramp spans about 25..75, so the mean stays near 50 and the range halves.
        arr = np.asarray(out)[..., 0].astype(int)
        assert arr.min() >= 24 and arr.max() <= 76 and abs(arr.mean() - 49.5) < 2

    def test_a_crop_centred_off_frame_is_clamped_inside(self) -> None:
        out = np.asarray(anime.render_derived_end(self._gradient(), DerivedEnd(scale=2.0, cx=0.0, cy=0.0)))
        assert out[..., 0].min() == 0 and out[..., 0].max() <= 50  # left half of the ramp, not black padding

    def test_scale_one_is_the_start_frame(self) -> None:
        img = self._gradient()
        assert np.array_equal(np.asarray(anime.render_derived_end(img, DerivedEnd(scale=1.0))), np.asarray(img))

    def test_fit_image_crops_to_the_aspect_rather_than_stretching(self) -> None:
        wide = Image.fromarray(np.tile(np.arange(200, dtype=np.uint8)[None, :, None], (100, 1, 3)))
        out = np.asarray(anime.fit_image(wide, 50, 100))
        assert out.shape == (100, 50, 3) and out[..., 0].min() >= 74  # centre quarter of the ramp


class TestCompose:
    def test_chapter_composes_and_picture_matches_audio_to_the_frame(self, tmp_path) -> None:
        panels, audio = build_chapter(tmp_path)
        timing = build_timing(audio, 1.0)
        result = _compose(tmp_path, FakeEngine(), panels=panels, audio=audio)
        total = timing[-1].end_gapped
        s = result.summary
        assert s["final"] == {"hold": 2, "generated": 3, "cached": 0, "fallback": 0}
        assert s["expected_frames"] == round(total * 30) == s["segment_frames"] == s["video_frames"]
        assert abs(_duration(result.video) - total) < 0.1
        shots = plan_shots(load_panel_plan(panels), timing, FAKE_CAP, ShotBudget(), clock="gapped")
        for shot, o in zip(shots, result.outcomes, strict=True):
            assert o.frames == round(shot.end * 30) - round(shot.start * 30)
            assert o.looped or o.clip_frames + o.hold_frames == o.frames

    def test_video_carries_the_chapter_pauses_so_it_is_as_long_as_chapter_wav(self, tmp_path) -> None:
        """P&P e2e (defect 7): the picture was timed on the line WAVs butted together, so every chapter video lost the
        inter-line pauses `chapter.wav` and the M4B carry (22 s of 290 s on ch1)."""
        panels, audio = build_chapter(tmp_path)
        timing = build_timing(audio, 1.0)
        gapped = timing[-1].end_gapped
        assert gapped > sum(t.duration for t in timing) + 0.5  # the fixture has pauses, or this proves nothing
        result = _compose(tmp_path, FakeEngine(), panels=panels, audio=audio)
        assert result.summary["expected_frames"] == round(gapped * 30)
        assert abs(_duration(result.video) - gapped) < 0.1
        shots = result.summary
        assert abs(shots["audio_seconds"] - gapped) < 1e-6

    def test_interleaved_panel_blocks_compose_as_cut_backs(self, tmp_path) -> None:
        """RI v55: one image holds blocks 0 and 2, another block 1. The planner used to refuse the chapter."""
        spec = [
            dict(scene=0, cast=["a"], slot="scene", lines=[(0, "DIALOGUE", "a", 2.0), (2, "DIALOGUE", "a", 2.0)]),
            dict(scene=0, cast=["a"], slot="scene", lines=[(1, "DIALOGUE", "b", 2.0)]),
        ]
        panels, audio = build_chapter(tmp_path, spec=spec)
        manifest = audio / "manifest.jsonl"  # the fixture writes rows panel by panel; a real manifest is in block order
        rows = sorted((json.loads(r) for r in manifest.read_text().splitlines()), key=lambda r: r["block_index"])
        manifest.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        result = _compose(tmp_path, FakeEngine(), panels=panels, audio=audio)
        assert [o.panel_id for o in result.outcomes] == ["t:1:0", "t:1:1", "t:1:0"]
        s = result.summary
        gapped = build_timing(audio, 1.0)[-1].end_gapped
        assert s["expected_frames"] == s["segment_frames"] == s["video_frames"] == round(gapped * 30)

    def test_each_mode_is_laid_out_as_designed(self, tmp_path) -> None:
        # The gapless clock: the frame counts below are the shots' own audio, without the pause each shot now also holds.
        result = _compose(tmp_path, FakeEngine(), loop_subtle=False, clock="gapless")
        o = result.outcomes
        # INTERPOLATE to the next panel: a hold first, then the clip ends the shot.
        assert o[0].clip_frames > 0 and o[0].hold_frames > 0
        segs = sorted(p.name for p in (result.out_dir / "segments").glob("s0000_*.mp4"))
        assert segs == ["s0000_clip.mp4", "s0000_head.mp4"]
        # ANIMATE (shot 2: 2.51 s of audio, 57-frame clip): the clip, then its last frame held.
        tail = sorted(p.name for p in (result.out_dir / "segments").glob("s0002_*.mp4"))
        assert tail == ["s0002_clip.mp4", "s0002_tail.mp4"] and o[2].hold_frames > 0
        # INTERPOLATE to a derived end (shot 1: the 73-frame clip covers its whole 3.04 s): no hold needed.
        assert o[1].clip_frames == o[1].frames and o[1].hold_frames == 0
        assert [x.final for x in o[3:]] == ["hold", "hold"]

    def test_the_shots_file_carries_each_outcome_and_still_loads_as_a_plan(self, tmp_path) -> None:
        result = _compose(tmp_path, FakeEngine())
        rows = [json.loads(ln) for ln in (result.out_dir / "shots.jsonl").read_text().splitlines()]
        assert [r["outcome"]["final"] for r in rows] == ["generated", "generated", "generated", "hold", "hold"]
        assert rows[0]["outcome"]["gate"]["passed"] is True and rows[0]["outcome"]["gate"]["start_ssim"] > 0.9
        assert rows[1]["outcome"]["dissolve_downgraded"] is True  # P1 -> P2 is a scene change
        assert next(s.mode for s in load_shots(result.out_dir)) is ShotMode.INTERPOLATE

    def test_a_new_versioned_directory_and_a_versions_line_written_by_the_code(self, tmp_path) -> None:
        first = _compose(tmp_path, FakeEngine())
        assert first.out_dir.name.startswith("v1_anime-fake-3clips")
        text = (tmp_path / "video" / "ch1" / "VERSIONS.md").read_text()
        assert first.out_dir.name in text and "not yet watched by a person" in text and "3 generated" in text
        second = _compose(tmp_path, FakeEngine(), panels=first_panels(tmp_path), audio=tmp_path / "audio")
        assert second.out_dir.name.startswith("v2_") and (tmp_path / "video/ch1/VERSIONS.md").read_text().count("## v") == 2

    def test_stills_engine_needs_no_engine_and_holds_everything(self, tmp_path) -> None:
        result = _compose(tmp_path, None, cap=STILLS)
        assert result.summary["final"]["hold"] == 5 and result.summary["video_frames"] == result.summary["expected_frames"]

    def test_captions_are_burned_when_asked(self, tmp_path) -> None:
        result = _compose(tmp_path, None, cap=STILLS, captions=True)
        assert (result.out_dir / "ch1.ass").exists() and result.video.stat().st_size > 0


def first_panels(tmp_path):
    return tmp_path / "panels" / "ch1" / "v1_test"


class TestCache:
    def test_a_rerun_regenerates_nothing(self, tmp_path) -> None:
        panels, audio = build_chapter(tmp_path)
        e1 = FakeEngine()
        _compose(tmp_path, e1, panels=panels, audio=audio)
        assert e1.requested == 3
        e2 = FakeEngine()
        again = _compose(tmp_path, e2, panels=panels, audio=audio)
        assert e2.requested == 0 and again.summary["final"]["cached"] == 3

    def test_a_changed_prompt_regenerates_only_that_clip(self, tmp_path) -> None:
        panels, audio = build_chapter(tmp_path)
        _compose(tmp_path, FakeEngine(), panels=panels, audio=audio)
        plan = panels / PANEL_PLAN_FILE
        rows = [json.loads(ln) for ln in plan.read_text().splitlines()]
        rows[2]["direction"]["action"] = "draws a sword"  # shot 2 is the ANIMATE shot
        plan.write_text("".join(json.dumps(r) + "\n" for r in rows))
        e = FakeEngine()
        result = _compose(tmp_path, e, panels=panels, audio=audio)
        assert e.requested == 1 and result.summary["final"]["cached"] == 2 and result.summary["final"]["generated"] == 1

    def test_a_different_model_file_changes_every_key(self, tmp_path) -> None:
        panels, audio = build_chapter(tmp_path)
        _compose(tmp_path, FakeEngine(), panels=panels, audio=audio)
        e = FakeEngine(identity="fake-model-2")
        _compose(tmp_path, e, panels=panels, audio=audio)
        assert e.requested == 3

    def test_key_covers_every_input(self) -> None:
        base = dict(start=b"a", end=None, derived=None, prompt="p", seed=1, frames=17, fps=24, width=64,
                    height=96, engine_id="e", model_identity="m")
        k = anime.clip_key(**base)
        assert anime.clip_key(**base) == k
        for change in [dict(start=b"b"), dict(end=b"x"), dict(derived=DerivedEnd(scale=1.1)), dict(prompt="q"),
                       dict(seed=2), dict(frames=25), dict(fps=12), dict(width=96), dict(height=64),
                       dict(engine_id="f"), dict(model_identity="n")]:
            assert anime.clip_key(**{**base, **change}) != k, change


class TestFailClosed:
    @pytest.mark.parametrize("behaviour", ["raise", "fail"])
    def test_a_failing_engine_falls_back_and_the_chapter_still_composes(self, tmp_path, behaviour) -> None:
        result = _compose(tmp_path, FakeEngine(behaviour))
        assert result.summary["final"] == {"hold": 2, "generated": 0, "cached": 0, "fallback": 3}
        assert all(o.reason.startswith("engine:") for o in result.outcomes[:3])
        assert result.summary["video_frames"] == result.summary["expected_frames"]

    @pytest.mark.parametrize(("behaviour", "reason"), [
        ("still", "still"), ("garbled", "jump"), ("wrong_end", "end frame"),
    ])
    def test_a_clip_the_gate_rejects_plays_as_a_held_still(self, tmp_path, behaviour, reason) -> None:
        result = _compose(tmp_path, FakeEngine(behaviour))
        rejected = [o for o in result.outcomes if o.final == "fallback"]
        assert rejected and all(reason in o.reason and o.gate["passed"] is False for o in rejected)
        assert result.summary["video_frames"] == result.summary["expected_frames"]
        for o in rejected:
            assert o.clip_frames == 0 and o.hold_frames == o.frames

    def test_content_drift_rejects_the_clip_and_the_chapter_still_composes(self, tmp_path) -> None:
        result = _compose(tmp_path, FakeEngine(), embedder=drifting_embedder)
        rejected = [o for o in result.outcomes if o.final == "fallback"]
        assert len(rejected) == 3 and all("content drift" in o.reason for o in rejected)
        assert result.summary["video_frames"] == result.summary["expected_frames"]

    def test_an_embedder_that_cannot_load_rejects_every_clip(self, tmp_path) -> None:
        def broken(images):
            raise OSError("clip-vit-large-patch14 is not in the local cache")

        result = _compose(tmp_path, FakeEngine(), embedder=broken)
        assert result.summary["final"]["fallback"] == 3
        assert all("drift check cannot run" in o.reason for o in result.outcomes[:3])

    def test_a_missing_panel_image_is_a_loud_error_not_a_blank_hold(self, tmp_path) -> None:
        panels, audio = build_chapter(tmp_path)
        (panels / "p2.png").unlink()
        with pytest.raises(FileNotFoundError, match=r"p2\.png"):
            _compose(tmp_path, FakeEngine(), panels=panels, audio=audio)

    def test_a_misconfigured_engine_is_not_swallowed_as_a_fallback(self, tmp_path) -> None:
        class Broken(FakeEngine):
            def generate_clips(self, requests):
                raise VideoEnvError("ECHOTALES_VIDEO_PYTHON is not set")

        with pytest.raises(VideoEnvError, match="VIDEO_PYTHON"):
            _compose(tmp_path, Broken())
        assert not list((tmp_path / "video" / "ch1").glob("v*"))  # no empty version left behind

    def test_the_sync_check_raises_when_picture_and_audio_disagree(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(anime, "count_frames", lambda p: 5)
        with pytest.raises(anime.AnimeSyncError, match="frames"):
            _compose(tmp_path, None, cap=STILLS)


class TestRefusals:
    def test_no_panel_plan(self, tmp_path) -> None:
        panels, audio = build_chapter(tmp_path)
        (panels / PANEL_PLAN_FILE).unlink()
        with pytest.raises(anime.AnimeRefusal, match="render the chapter again"):
            _compose(tmp_path, None, cap=STILLS, panels=panels, audio=audio)

    def test_no_voiced_audio(self, tmp_path) -> None:
        panels, audio = build_chapter(tmp_path)
        (audio / "manifest.jsonl").write_text("")
        with pytest.raises(anime.AnimeRefusal, match="echotales voice"):
            _compose(tmp_path, None, cap=STILLS, panels=panels, audio=audio)
        (audio / "manifest.jsonl").unlink()
        with pytest.raises(anime.AnimeRefusal, match="echotales voice"):
            _compose(tmp_path, None, cap=STILLS, panels=panels, audio=audio)

    def test_latest_version_skips_directories_without_a_plan(self, tmp_path) -> None:
        panels, _ = build_chapter(tmp_path)
        (panels.parent / "v9_old-render").mkdir()
        assert anime.latest_panels_version(panels.parent.parent, 1.0) == panels

    def test_a_capability_that_generates_needs_an_engine(self, tmp_path) -> None:
        with pytest.raises(anime.AnimeRefusal, match="no engine"):
            _compose(tmp_path, None)


class TestCli:
    def _args(self, tmp_path, *extra) -> list[str]:
        return ["--db", str(tmp_path / "x.db"), "anime", "--novel", "t", "--chapter", "1",
                "--panel-dir", str(tmp_path / "panels"), "--audio-dir", str(tmp_path / "audio"),
                "--out", str(tmp_path / "video"), *extra]

    def test_refuses_without_a_panel_plan_naming_the_fix(self, tmp_path, capsys) -> None:
        panels, _ = build_chapter(tmp_path)
        (panels / PANEL_PLAN_FILE).unlink()
        assert main(self._args(tmp_path)) == 2
        err = capsys.readouterr().err
        assert "refusing" in err and "echotales render --novel t --chapters 1" in err

    def test_refuses_without_audio_naming_the_fix(self, tmp_path, capsys) -> None:
        build_chapter(tmp_path)
        (tmp_path / "audio" / "manifest.jsonl").write_text("")
        assert main(self._args(tmp_path)) == 2
        assert "echotales voice" in capsys.readouterr().err

    def test_stills_run_prints_json(self, tmp_path, capsys) -> None:
        build_chapter(tmp_path)
        assert main(self._args(tmp_path, "--json", "--no-captions", "--max-clips", "2", "--seed", "3")) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["summary"]["final"]["hold"] == 5 and len(data["shots"]) == 5
        assert data["summary"]["video_frames"] == data["summary"]["expected_frames"]

    def test_ltx_local_without_the_environment_refuses_with_the_setup_script(self, tmp_path, monkeypatch, capsys) -> None:
        build_chapter(tmp_path)
        monkeypatch.delenv("ECHOTALES_VIDEO_PYTHON", raising=False)
        monkeypatch.chdir(tmp_path)
        # Real LOCAL_LTX capability with a 512x768 plan input: the panel fixture is 64x96, so the plan is
        # unchanged and only the engine's interpreter check matters here.
        assert main(self._args(tmp_path, "--engine", "ltx-local", "--panels-version", "v1_test")) == 2
        assert "setup_video.sh" in capsys.readouterr().err


class TestLooping:
    def test_a_subtle_animate_shot_is_filled_by_the_looped_clip_not_a_frozen_tail(self, tmp_path) -> None:
        result = _compose(tmp_path, FakeEngine())
        o = result.outcomes[2]
        assert o.looped and o.hold_frames == 0 and o.clip_frames < o.frames  # the clip repeats to fill the shot
        names = sorted(p.name for p in (result.out_dir / "segments").glob("s0002_*.mp4"))
        assert "s0002_loop.mp4" in names and "s0002_tail.mp4" not in names
        # Derived-end push-ins and panel-to-panel clips keep their old layout.
        assert not result.outcomes[0].looped and not result.outcomes[1].looped
        assert result.summary["looped_shots"] == 1
        assert result.summary["video_frames"] == result.summary["expected_frames"]

    def test_the_loop_can_be_switched_off(self, tmp_path) -> None:
        result = _compose(tmp_path, FakeEngine(), loop_subtle=False)
        assert not result.outcomes[2].looped and result.outcomes[2].hold_frames > 0

    def test_a_rejected_clip_is_never_looped(self, tmp_path) -> None:
        result = _compose(tmp_path, FakeEngine("still"))
        assert not any(o.looped for o in result.outcomes)

    def test_the_turnaround_has_no_jump_and_no_repeated_frame(self, tmp_path) -> None:
        from echotales.pipeline.video.clip_gate import decode_gray

        # Gapless so the shot is shorter than one loop period; a longer shot reaches the 24 -> 30 fps resampling, which
        # repeats a frame on its own and is not the turnaround this test is about.
        result = _compose(tmp_path, FakeEngine(), clock="gapless")
        o = result.outcomes[2]
        frames = decode_gray(result.out_dir / "segments" / "s0002_loop.mp4", OUT_W, OUT_H)
        d = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
        assert len(frames) == o.frames and d.min() > 0  # nothing is shown twice in a row
        turn = d[o.clip_frames - 3 : o.clip_frames + 3].max()
        assert turn < 3 * np.median(d)
