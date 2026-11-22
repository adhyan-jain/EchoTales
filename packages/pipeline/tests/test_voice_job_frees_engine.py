"""A finished voice job gives its VRAM back (P&P e2e 2026-11-22, defect 4).

The Studio server held Chatterbox (about 4.9 GB) after a voice job, so the next render job was refused with GPU_BUSY
until the server was restarted. The engine is released when the job ends, success or failure. Fake engine, no GPU.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from echotales.core.models import Job, JobStatus
from echotales.core.store import Store
from echotales.pipeline import jobs
from echotales.pipeline.voice.engine import ChatterboxEngine


class FakeEngine:
    name = "fake"
    closed = 0

    def close(self) -> None:
        FakeEngine.closed += 1


def _run(store: Store, kind: str, params: dict) -> Job:
    job = Job(job_id=f"n:{kind}", novel_id="n", kind=kind, status=JobStatus.PENDING, created_at=1.0,
              params_json=json.dumps(params))
    store.add_job(job)
    jobs.run_job(store, job, params)
    return store.get_job(job.job_id)


@pytest.fixture()
def store(tmp_path: Path, monkeypatch) -> Store:
    FakeEngine.closed = 0
    monkeypatch.setattr("echotales.pipeline.paths.asset_dir", lambda novel_id, kind: tmp_path / kind)
    monkeypatch.setattr("echotales.pipeline.compute.voice_refusal", lambda engine: None)
    monkeypatch.setattr("echotales.pipeline.voice.get_engine", lambda name, **k: FakeEngine())
    monkeypatch.setattr("echotales.pipeline.voice.bank.load_bank", lambda *a, **k: object())
    monkeypatch.setattr("echotales.pipeline.project_voices.with_project_voices", lambda bank, novel: bank)
    monkeypatch.setattr("echotales.pipeline.voice.qa.engine_reference_f0", lambda bank, name: None)
    s = Store(":memory:")
    s.add_novel("n", "N", "x.epub", "generic")
    return s


def test_voice_job_releases_the_engine_after_success(store: Store, monkeypatch) -> None:
    monkeypatch.setattr("echotales.pipeline.voice.render_novel", lambda *a, **k: None)
    assert _run(store, "voice", {"engine": "chatterbox"}).status == JobStatus.SUCCEEDED
    assert FakeEngine.closed == 1


def test_voice_job_releases_the_engine_after_a_failure(store: Store, monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("synthesis failed")

    monkeypatch.setattr("echotales.pipeline.voice.render_novel", boom)
    assert _run(store, "voice", {"engine": "chatterbox"}).status == JobStatus.FAILED
    assert FakeEngine.closed == 1


def test_audition_job_releases_the_engine_after_a_failure(store: Store, monkeypatch) -> None:
    # no bank on this machine: the job fails after the engine was built
    monkeypatch.setattr("echotales.pipeline.voice.bank.load_bank", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    assert _run(store, "voice_audition", {"engine": "chatterbox", "target": "narrator"}).status == JobStatus.FAILED
    assert FakeEngine.closed == 1


def test_chatterbox_close_drops_the_model_and_empties_the_cuda_cache(monkeypatch) -> None:
    emptied: list[int] = []
    monkeypatch.setattr("echotales.pipeline.hwaccel.free_cuda_cache", lambda: emptied.append(1))
    engine = ChatterboxEngine()
    engine._model = object()
    engine.close()
    assert engine._model is None
    assert emptied == [1]


def test_close_on_an_engine_that_never_loaded_is_harmless() -> None:
    ChatterboxEngine().close()
