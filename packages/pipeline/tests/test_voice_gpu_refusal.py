"""The voice and voice_audition jobs refuse a busy GPU before loading Chatterbox (security review follow-up).

Without the check an external process holding the card made Chatterbox crash mid-chapter; the render and video jobs
already refuse cleanly, so these two must too. The stub and hosted engines never touch the GPU and are unaffected.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from echotales.core.models import Job, JobStatus
from echotales.core.store import Store
from echotales.pipeline import compute, gpu, jobs


class _Busy:
    free = False
    used_mb = 7000

    def describe(self) -> str:
        return "7000 of 8188 MiB in use"


def _run(store: Store, kind: str, params: dict) -> Job:
    job = Job(job_id=f"n:{kind}:{sorted(params)}", novel_id="n", kind=kind,
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


@pytest.fixture()
def busy(monkeypatch) -> None:
    monkeypatch.setattr(gpu, "gpu_status", lambda: _Busy())


def test_voice_refuses_a_busy_gpu_before_synthesis(store: Store, busy, monkeypatch) -> None:
    started: list[str] = []
    monkeypatch.setattr("echotales.pipeline.voice.render_novel", lambda *a, **k: started.append("x"))
    job = _run(store, "voice", {"engine": "chatterbox"})
    assert job.status == JobStatus.FAILED
    assert "GPU is busy" in job.error_summary
    assert started == []


def test_voice_audition_refuses_a_busy_gpu_before_loading_the_engine(store: Store, busy, monkeypatch) -> None:
    loaded: list[str] = []
    monkeypatch.setattr("echotales.pipeline.voice.get_engine", lambda name: loaded.append(name))
    job = _run(store, "voice_audition", {"engine": "chatterbox", "target": "narrator"})
    assert job.status == JobStatus.FAILED
    assert "GPU is busy" in job.error_summary
    assert loaded == []


def test_only_local_gpu_voice_engines_are_gated(busy) -> None:
    assert compute.voice_refusal("stub") is None
    assert compute.voice_refusal("elevenlabs") is None
    assert "GPU is busy" in compute.voice_refusal("chatterbox")


def test_no_gpu_refuses_chatterbox_with_a_clear_message(monkeypatch) -> None:
    monkeypatch.setattr(gpu, "gpu_status", lambda: None)
    assert "NVIDIA GPU" in compute.voice_refusal("chatterbox")


def test_stub_voice_job_never_consults_the_gpu(store: Store, monkeypatch) -> None:
    def boom():
        raise AssertionError("gpu consulted")

    monkeypatch.setattr(gpu, "gpu_status", boom)
    job = _run(store, "voice_audition", {"engine": "stub", "target": "bogus"})
    # Fails for its own reason (bad target), not for the GPU.
    assert job.status == JobStatus.FAILED
    assert "target" in job.error_summary
