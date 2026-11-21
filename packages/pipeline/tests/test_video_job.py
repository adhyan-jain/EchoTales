"""The Studio `video` job: the chapter video the CLI's `anime` and `render` composition produce, behind a job kind.

The job is only a thin caller of `render/anime.py::compose_chapter_video` and `render/runner.py::render_videos`; what
is tested here is what a Studio user would otherwise hit as a stack trace -- the refusals -- and that the CLI code
path (not a copy of it) is the one that runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from echotales.core.models import Job, JobStatus
from echotales.core.store import Store
from echotales.pipeline import jobs
from echotales.pipeline.render import anime


def _run(store: Store, params: dict) -> Job:
    job = Job(job_id=f"n:video:{len(params)}{sorted(params)}", novel_id="n", kind="video",
              status=JobStatus.PENDING, created_at=1.0, params_json=json.dumps(params))
    store.add_job(job)
    jobs.run_job(store, job, params)
    return store.get_job(job.job_id)


@pytest.fixture()
def store(tmp_path: Path, monkeypatch) -> Store:
    monkeypatch.setattr("echotales.pipeline.paths.asset_dir", lambda novel_id, kind: tmp_path / kind)
    s = Store(":memory:")
    s.add_novel("n", "N", "x.epub", "generic")
    return s


def _panel_plan(tmp_path: Path, chapter: str = "ch1") -> None:
    d = tmp_path / "panels" / chapter / "v1_x"
    d.mkdir(parents=True)
    (d / "panel_plan.jsonl").write_text("", encoding="utf-8")


def test_video_is_a_job_kind() -> None:
    assert "video" in jobs.JOB_KINDS


def test_no_chapters_is_refused_with_the_fix(store: Store) -> None:
    job = _run(store, {})
    assert job.status == JobStatus.FAILED
    assert "chapters" in job.error_summary


def test_unknown_engine_is_refused(store: Store) -> None:
    job = _run(store, {"chapters": [1], "engine": "sora"})
    assert job.status == JobStatus.FAILED
    assert "stills" in job.error_summary and "ltx-local" in job.error_summary


def test_no_panels_names_the_render_command(store: Store) -> None:
    job = _run(store, {"chapters": [1]})
    assert job.status == JobStatus.FAILED
    assert "render" in job.error_summary and "panel" in job.error_summary


def test_no_voiced_audio_names_the_voice_step(store: Store, tmp_path: Path) -> None:
    _panel_plan(tmp_path)
    job = _run(store, {"chapters": [1]})
    assert job.status == JobStatus.FAILED
    assert "voice" in job.error_summary


def test_ltx_local_honours_the_compute_video_refusal(store: Store, monkeypatch) -> None:
    monkeypatch.setattr("echotales.pipeline.compute.resource_refusal", lambda engine, *a, **k: "the GPU is busy")
    job = _run(store, {"chapters": [1], "engine": "ltx-local"})
    assert job.status == JobStatus.FAILED
    assert "GPU is busy" in job.error_summary


def test_stills_does_not_consult_the_video_refusal(store: Store, monkeypatch) -> None:
    called: list[str] = []
    monkeypatch.setattr("echotales.pipeline.compute.resource_refusal", lambda engine, *a, **k: called.append(engine))
    _run(store, {"chapters": [1]})
    assert called == []


def test_runs_the_cli_composer_once_per_chapter_and_succeeds(store: Store, tmp_path: Path, monkeypatch) -> None:
    _panel_plan(tmp_path, "ch1")
    _panel_plan(tmp_path, "ch2")
    seen: list[tuple[float, str]] = []

    def fake(novel_id, chapter, **kw):
        seen.append((chapter, kw["engine"]))

    monkeypatch.setattr(anime, "compose_chapter_video", fake)
    job = _run(store, {"chapters": [1, 2]})
    assert job.status == JobStatus.SUCCEEDED, job.error_summary
    assert seen == [(1.0, "stills"), (2.0, "stills")]


def test_an_identical_rerun_is_not_skipped_as_already_done(store: Store, tmp_path: Path, monkeypatch) -> None:
    """Panels and audio change between runs while the params do not; a stale 'already succeeded' skip would hide that."""
    _panel_plan(tmp_path)
    calls: list[int] = []
    monkeypatch.setattr(anime, "compose_chapter_video", lambda *a, **k: calls.append(1))
    p = {"chapters": [1]}
    for i in range(2):
        job = Job(job_id=f"n:video:{i}", novel_id="n", kind="video", status=JobStatus.PENDING, created_at=1.0,
                  params_json=json.dumps(p))
        store.add_job(job)
        jobs.run_job(store, job, p)
    assert len(calls) == 2


def test_prune_uses_the_motion_comic_path_and_needs_its_manifests(store: Store) -> None:
    job = _run(store, {"chapters": [1], "prune_visual_narration": True})
    assert job.status == JobStatus.FAILED
    assert "manifest" in job.error_summary


def test_prune_with_ltx_local_is_refused(store: Store) -> None:
    job = _run(store, {"chapters": [1], "engine": "ltx-local", "prune_visual_narration": True})
    assert job.status == JobStatus.FAILED
    assert "prune" in job.error_summary


@pytest.mark.parametrize("kind", ["video", "episode"])
def test_stub_audio_is_refused_outside_stub_mode(store: Store, tmp_path: Path, monkeypatch, kind: str) -> None:
    """Silent stub audio must not finish SUCCEEDED as a video (EVOLUTION 4.183); the M4B export refuses it too."""
    from echotales.pipeline.config import LLMMode, get_settings

    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "run.json").write_text(json.dumps({"engine": "stub"}), encoding="utf-8")
    monkeypatch.setattr(get_settings(), "llm_mode", LLMMode.LOCAL)
    job = Job(job_id=f"n:{kind}:1", novel_id="n", kind=kind, status=JobStatus.PENDING, created_at=1.0,
              params_json=json.dumps({"chapters": [1]}))
    store.add_job(job)
    jobs.run_job(store, job, {"chapters": [1]})
    got = store.get_job(job.job_id)
    assert got.status == JobStatus.FAILED and "chatterbox" in got.error_summary
