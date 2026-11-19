"""Episode composer: acts, cold open, spoiler-safe recap and next card, voice-timed vs fixed cuts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from _anime_helpers import build_chapter
from echotales.core.enums import OBSERVER_READER, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, DiscoursePosition, Relation, Self
from echotales.core.store import Store
from echotales.pipeline.render import episode
from echotales.pipeline.render.plan import load_panel_plan
from echotales.pipeline.render.shots import MotionLevel
from echotales.pipeline.screenplay.schema import CameraMove
from echotales.pipeline.voice.timing import build_timing

NOVEL = "t"


def _chapter(tmp_path: Path, spec: list[dict] | None = None):
    panels_dir, audio = build_chapter(tmp_path, spec=spec)
    panels = load_panel_plan(panels_dir)
    timing = build_timing(audio, 1.0)
    return panels_dir, audio, panels, timing


def test_voice_timing_cuts_only_on_line_boundaries(tmp_path: Path) -> None:
    _, _, panels, timing = _chapter(tmp_path)
    shots = episode.plan_episode_shots(panels, timing, mode="voice")
    assert shots[0].start == 0.0 and shots[-1].end == pytest.approx(timing[-1].end_gapless)
    assert episode.timing_stats(shots, timing)["mid_line_cuts"] == 0
    for a, b in zip(shots, shots[1:]):
        assert a.end == b.start  # gapless: the picture tiles the audio


def test_interleaved_panels_come_back_as_cut_backs(tmp_path: Path) -> None:
    """A real render reuses an image for a later block (RI ch1 v55: blocks [1, 3] on one panel, [2] on another)."""
    _, _, panels, timing = _chapter(tmp_path)
    panels[0].block_indexes, panels[1].block_indexes = [0, 2], [1]
    shots = episode.plan_episode_shots(panels, timing, mode="voice")
    assert [s.panel_id for s in shots[:3]] == [panels[0].panel_id, panels[1].panel_id, panels[0].panel_id]
    assert shots[-1].end == pytest.approx(timing[-1].end_gapless)


def test_fixed_timing_tiles_the_same_audio_with_equal_windows(tmp_path: Path) -> None:
    _, _, panels, timing = _chapter(tmp_path)
    shots = episode.plan_episode_shots(panels, timing, mode="fixed", fixed_seconds=2.0)
    assert shots[-1].end == pytest.approx(timing[-1].end_gapless)
    assert all(s.duration == pytest.approx(2.0) for s in shots[:-1])
    assert episode.timing_stats(shots, timing)["mid_line_cuts"] > 0


def test_long_panel_is_split_at_a_line_boundary(tmp_path: Path) -> None:
    spec = [dict(scene=0, cast=["a"], slot="scene",
                 lines=[(0, "DIALOGUE", "a", 5.0), (1, "DIALOGUE", "a", 5.0), (2, "DIALOGUE", "a", 5.0)])]
    _, _, panels, timing = _chapter(tmp_path, spec)
    shots = episode.plan_episode_shots(panels, timing, mode="voice", max_hold=8.0)
    assert len(shots) >= 2 and all(s.duration <= 10.0 + 1e-6 for s in shots)
    assert episode.timing_stats(shots, timing)["mid_line_cuts"] == 0


def test_motion_follows_delivery(tmp_path: Path) -> None:
    _, _, panels, timing = _chapter(tmp_path)
    emotions = {t.span_id: ("anger", 3) for t in timing if t.block_index == 3}
    shots = episode.plan_episode_shots(panels, timing, mode="voice", emotions=emotions)
    by_block = {b: s for s in shots for b in s.block_indexes}
    assert by_block[3].level is MotionLevel.STRONG and by_block[3].move is CameraMove.IMPACT_SHAKE
    calm = by_block[0]
    assert calm.level is MotionLevel.SUBTLE and calm.move is not CameraMove.IMPACT_SHAKE
    assert by_block[3].gain >= calm.gain


def test_acts_split_only_at_scene_boundaries(tmp_path: Path) -> None:
    _, _, panels, timing = _chapter(tmp_path)
    shots = episode.plan_episode_shots(panels, timing, mode="voice")
    acts = episode.plan_acts(shots, panels, n_acts=2)
    assert len(acts) == 2
    scene_of = {p.panel_id: p.scene_index for p in panels}
    first, second = acts
    assert not ({scene_of[s.panel_id] for s in shots[first.first:first.last + 1]}
                & {scene_of[s.panel_id] for s in shots[second.first:second.last + 1]})
    assert first.first == 0 and second.last == len(shots) - 1 and second.first == first.last + 1


def test_cold_open_is_the_highest_intensity_scene_excerpt(tmp_path: Path) -> None:
    _, _, panels, timing = _chapter(tmp_path)
    shots = episode.plan_episode_shots(panels, timing, mode="voice")
    emotions = {t.span_id: ("fear", 3) for t in timing if t.block_index == 3}
    cold = episode.pick_cold_open(shots, panels, timing, emotions, max_seconds=4.0)
    assert cold is not None and cold.peak_block == 3
    assert cold.start == pytest.approx(next(t.start_gapless for t in timing if t.block_index == 3))
    assert cold.end > cold.start


def test_cold_open_absent_when_nothing_is_intense(tmp_path: Path) -> None:
    _, _, panels, timing = _chapter(tmp_path)
    shots = episode.plan_episode_shots(panels, timing, mode="voice")
    assert episode.pick_cold_open(shots, panels, timing, {}, max_seconds=4.0) is None


def _recap_store() -> Store:
    s = Store(":memory:")
    s.add_novel("n", "N", "x.epub", "n")
    for sid, label, ch in (("a", "Alice", 1), ("b", "Bob", 1), ("c", "Cara", 3)):
        s.add_self(Self(id=sid, novel_id="n", canonical_label=label, first_attested_pos=DiscoursePosition(chapter=ch)))

    def attr(sid: str, key: str, value: str, ch: int) -> None:
        s.add_attribute("n", Attribute(
            target_kind=TargetKind.SELF, target_id=sid, key=key, value=value,
            interval=FuzzyInterval.open_ended(ch, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=ch), observer_id=OBSERVER_READER))

    attr("a", "role", "village healer", 1)
    attr("a", "status", "secretly the king in disguise", 3)  # a ch3 reveal
    s.add_relation("n", Relation(
        src_self="a", dst_self="b", type="SISTER_OF", interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
        learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER))
    s.add_relation("n", Relation(
        src_self="b", dst_self="c", type="MURDERER_OF", interval=FuzzyInterval.open_ended(3, last_evidence=1e6),
        learned_at_pos=DiscoursePosition(chapter=3), observer_id=OBSERVER_READER))
    s.conn.commit()
    return s


def test_recap_uses_only_facts_before_the_chapter() -> None:
    store = _recap_store()
    text = " | ".join(episode.recap_lines(store, "n", 3))
    assert "village healer" in text and "sister of" in text.lower()
    assert "king in disguise" not in text and "murderer" not in text.lower() and "Cara" not in text
    # once the viewer reaches chapter 4 the earlier plant is allowed
    later = " | ".join(episode.recap_lines(store, "n", 4))
    assert "king in disguise" in later and "murderer" in later.lower()


def test_recap_of_chapter_one_is_empty() -> None:
    assert episode.recap_lines(_recap_store(), "n", 1) == []


def test_next_card_names_only_number_and_title() -> None:
    lines = episode.next_card_lines([(1.0, "One"), (2.0, "The Ball"), (3.0, "Elizabeth Dies")], 1.0)
    assert lines == ["Next time", "Episode 2", "The Ball"]
    assert episode.next_card_lines([(1.0, "One")], 1.0) == []


def test_compose_episode_end_to_end_stills(tmp_path: Path) -> None:
    panels_dir, audio, panels, timing = _chapter(tmp_path)
    store = Store(":memory:")
    store.add_novel(NOVEL, "Test Book", "x.epub", "t")
    store.set_span_emotions(NOVEL, 1.0, {t.span_id: ("fear", 3) for t in timing if t.block_index == 3})
    out_root = tmp_path / "video" / "ch1"
    res = episode.compose_episode(
        store, NOVEL, 1.0, panels_dir=panels_dir, audio_dir=audio, out_root=out_root,
        timing="voice", motion="stills", size=(108, 192), fps=8, suffix="test",
        chapter_titles=[(1.0, "One"), (2.0, "Two")], book_title="Test Book",
    )
    assert res.video.name == "episode.mp4" and res.video.parent.name.endswith("_test")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(res.video)], capture_output=True, text=True).stdout
    assert abs(float(probe) - res.summary["duration"]) < 0.6
    assert (out_root / "VERSIONS.md").read_text().count(f"## {res.video.parent.name}") == 1
    assert res.summary["cold_open"]["peak_block"] == 3 and (res.out_dir / "tile.png").is_file()
    # cold open + title + body + next card, all from one frame count
    assert res.summary["duration"] == pytest.approx(
        res.summary["body_seconds"] + 3.0 + 4.0 + (res.summary["cold_open"]["end"] - res.summary["cold_open"]["start"]), abs=0.3)
    assert res.summary["body_seconds"] == pytest.approx(timing[-1].end_gapless, abs=0.01)


class TestCliAndJob:
    def _db(self, tmp_path: Path) -> Path:
        db = tmp_path / "x.db"
        Store(str(db)).add_novel(NOVEL, "Test Book", "x.epub", "t")
        return db

    def test_cli_makes_an_episode_into_a_versioned_folder(self, tmp_path: Path, capsys) -> None:
        from echotales.pipeline.cli import main

        build_chapter(tmp_path)
        args = ["--db", str(self._db(tmp_path)), "episode", "--novel", NOVEL, "--chapter", "1",
                "--panel-dir", str(tmp_path / "panels"), "--audio-dir", str(tmp_path / "audio"),
                "--out", str(tmp_path / "video"), "--timing", "fixed", "--suffix", "ab", "--json"]
        assert main(args) == 0
        import json

        data = json.loads(capsys.readouterr().out)
        assert data["timing"] == "fixed" and Path(data["video"]).is_file()
        assert Path(data["video"]).parent.parent.name == "ch1" and Path(data["video"]).parent.name == "v1_ab"

    def test_cli_refuses_without_panels_naming_the_fix(self, tmp_path: Path, capsys) -> None:
        from echotales.pipeline.cli import main

        args = ["--db", str(self._db(tmp_path)), "episode", "--novel", NOVEL, "--chapter", "1",
                "--panel-dir", str(tmp_path / "panels"), "--audio-dir", str(tmp_path / "audio"), "--out", str(tmp_path)]
        assert main(args) == 2
        assert "echotales render --novel t --chapters 1" in capsys.readouterr().err

    def test_ltx_with_fixed_timing_is_refused(self, tmp_path: Path) -> None:
        panels_dir, audio, _, _ = _chapter(tmp_path)
        with pytest.raises(episode.EpisodeRefusal, match="--timing voice"):
            episode.compose_episode(Store(":memory:"), NOVEL, 1.0, panels_dir=panels_dir, audio_dir=audio,
                                    out_root=tmp_path / "v", timing="fixed", motion="ltx-local")

    def test_job_kind_and_refusals(self) -> None:
        import json

        from echotales.core.models import Job, JobStatus
        from echotales.pipeline import jobs

        assert "episode" in jobs.JOB_KINDS
        store = Store(":memory:")
        store.add_novel("n", "N", "x.epub", "generic")
        job = Job(job_id="n:episode:1", novel_id="n", kind="episode", status=JobStatus.PENDING, created_at=1.0,
                  params_json=json.dumps({}))
        store.add_job(job)
        jobs.run_job(store, job, {})
        done = store.get_job("n:episode:1")
        assert done.status == JobStatus.FAILED and "chapters" in done.error_summary


def test_ltx_local_body_comes_from_the_anime_composer(tmp_path: Path, monkeypatch) -> None:
    """The ltx-local body is the anime composer's video, decoded into the episode; a fake engine stands in for the GPU."""
    from _anime_helpers import FAKE_CAP, FakeEngine
    from echotales.pipeline.render import shots as shots_mod
    from echotales.pipeline.video import local as local_mod

    panels_dir, audio, _, timing = _chapter(tmp_path)
    monkeypatch.setattr(shots_mod, "LOCAL_LTX", FAKE_CAP)
    monkeypatch.setattr(local_mod, "LocalLTXEngine", lambda work_dir=None: FakeEngine())
    from echotales.pipeline.render import anime

    monkeypatch.setattr(anime, "ClipImageEmbedder", _FakeEmbedder)
    store = Store(":memory:")
    store.add_novel(NOVEL, "Test Book", "x.epub", "t")
    res = episode.compose_episode(
        store, NOVEL, 1.0, panels_dir=panels_dir, audio_dir=audio, out_root=tmp_path / "video" / "ch1",
        timing="voice", motion="ltx-local", size=(108, 192), fps=8, suffix="ltx", chapter_titles=[(1.0, "One")],
    )
    assert res.video.is_file() and Path(res.summary["body_video"]).is_file()
    assert res.summary["body_seconds"] == pytest.approx(timing[-1].end_gapless, abs=0.01)


class _FakeEmbedder:
    def __call__(self, images):
        import numpy as np

        return np.ones((len(images), 4), dtype="float32")

    def close(self) -> None:
        pass
