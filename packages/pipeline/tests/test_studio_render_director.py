"""A Studio render job takes the CLI's default path: the configured engine and the panel director (P&P e2e 2026-11-22).

The Studio-queued render of P&P ch1 (`pnp-e2e:render:7bd33352`) called `render_panels` with no director client, so every panel's
`direction_reason` was "no director client" and 32 panels were drawn from the bare persona sentence (30 byte-identical images).
The CLI builds the director in `cmd_render`; the job never did. The mock below stands in for the model: nothing here loads one.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from echotales.core.models import Job
from echotales.core.store import Store
from echotales.pipeline import commands, compute, config
from echotales.pipeline.config import ModelBackend
from echotales.pipeline.jobs import run_job
from echotales.pipeline.llm.tasks import Task
from echotales.pipeline.render import panels


class _Director:
    backend = ModelBackend.GATEWAY


@pytest.fixture
def rig(tmp_path: Path, monkeypatch):
    """A store, a recording `render_panels`, and a `_build_client` that records its request and returns a mock director."""
    calls: list[dict] = []
    built: list[dict] = []
    director = _Director()

    def fake_render(novel_id, store, *, out_dir, version, engine=None, client=None, **kw):  # type: ignore[no-untyped-def]
        calls.append({"engine": engine, "client": client, "out_dir": out_dir, "version": version, **kw})
        return SimpleNamespace(summary=lambda: "ok", status="ok", failed=0, panels=0)

    def fake_build(store, *, no_llm=False, tasks=None):  # type: ignore[no-untyped-def]
        built.append({"tasks": tasks})
        return director

    monkeypatch.setattr(panels, "render_panels", fake_render)
    monkeypatch.setattr(panels, "get_engine", lambda name, **kw: SimpleNamespace(name=name))
    monkeypatch.setattr(commands, "_build_client", fake_build)
    monkeypatch.setattr(commands, "unload_ollama_models", lambda **kw: None)
    monkeypatch.setattr(compute, "resource_refusal", lambda *a, **k: None)
    store = Store(str(tmp_path / "t.db"))

    def run(params: dict, settings: config.Settings | None = None, job_id: str = "n:render:1"):
        monkeypatch.setattr(config, "_settings", settings or config.Settings(compute="local-high", render_direction_first=False))
        store.add_job(Job(job_id=job_id, novel_id="n", kind="render", created_at=time.time()))
        run_job(store, store.get_job(job_id), {"panel_dir": str(tmp_path / "panels"), "chapters": [1.0], **params})
        return store.get_job(job_id)

    return SimpleNamespace(run=run, calls=calls, built=built, director=director)


def test_default_params_use_the_configured_default_engine(rig) -> None:
    job = rig.run({})
    assert job.status.value in ("SUCCEEDED", "PARTIAL"), job.error_summary
    assert rig.calls[-1]["engine"].name == compute.default_image_engine()
    assert compute.default_image_engine() == config.get_settings().local_image_engine


def test_default_params_build_the_panel_director_and_hand_it_to_render_panels(rig) -> None:
    rig.run({})
    assert rig.built == [{"tasks": {Task.PANEL_DIRECTION}}]
    assert [c["client"] for c in rig.calls] == [rig.director]


def test_the_two_phase_path_directs_first_with_a_stub_engine_then_draws_without_the_director(rig) -> None:
    """`local-low` (the default mode) runs the director to completion and lets it go before the image model loads."""
    rig.run({}, config.Settings(compute="local-low"))
    direct, draw = rig.calls
    assert direct["client"] is rig.director and direct["engine"].name == "stub" and direct["target_engine"] is draw["engine"]
    assert draw["client"] is None and draw["engine"].name == compute.default_image_engine()
    assert direct["prompt_cache_path"] == draw["prompt_cache_path"]
    assert direct["out_dir"] != draw["out_dir"], "phase 1 must not write placeholder images into the real version folder"


def test_the_stub_engine_never_touches_a_model_so_it_builds_no_director(rig) -> None:
    rig.run({"engine": "stub"})
    assert rig.built == [] and [c["client"] for c in rig.calls] == [None]


def test_a_job_can_opt_out_of_the_director_as_the_cli_can(rig) -> None:
    rig.run({"no_director": True})
    assert rig.built == [] and [c["client"] for c in rig.calls] == [None]


def test_a_stub_backend_runs_deterministically_like_the_cli(rig, monkeypatch) -> None:
    monkeypatch.setattr(commands, "_build_client", lambda store, **kw: None)  # ECHOTALES_MODEL_BACKEND=stub
    rig.run({})
    assert [c["client"] for c in rig.calls] == [None]
