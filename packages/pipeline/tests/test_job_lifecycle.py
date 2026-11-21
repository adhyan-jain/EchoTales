"""Job lifecycle: cancel vs. worker claim, interrupt sweeps, run bookkeeping, cache and delete safety."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from echotales.core.lifecycle import JobStatus, StageStatus
from echotales.core.models import Chapter, Job
from echotales.core.pipeline_run import ensure_pipeline_run, start_stage
from echotales.core.store import Store
from echotales.pipeline import jobs
from echotales.pipeline.corrections import Correction, CorrectionType
from echotales.pipeline.jobs import JobQueue, run_job, run_stage
from echotales.pipeline.version import PIPELINE_VERSION, staleness_reason
from echotales.pipeline.webview_server import Registry, make_handler
from test_webview_server_jobs import LivePort, TestUploadSafety, _request, live_server  # noqa: F401


def _job(store: Store, job_id: str = "n:bogus:1", kind: str = "bogus", novel_id: str = "n") -> Job:
    job = Job(job_id=job_id, novel_id=novel_id, kind=kind, created_at=time.time())
    store.add_job(job)
    return job


class TestCancelRace:
    def test_cancel_before_the_claim_means_the_job_is_never_run(self, tmp_path: Path, monkeypatch) -> None:
        store = Store(str(tmp_path / "t.db"))
        job = _job(store)
        ran: list[str] = []
        monkeypatch.setattr(jobs, "_dispatch", lambda *a, **k: ran.append("x") or "r")

        assert store.transition_job(job.job_id, [JobStatus.PENDING], JobStatus.CANCELLED, error_summary="cancelled by user")
        run_job(store, job, {})  # the worker arrives holding its stale PENDING copy

        assert ran == []
        assert store.get_job(job.job_id).status is JobStatus.CANCELLED

    def test_cancel_after_the_claim_loses_and_leaves_the_job_alone(self, live_server: LivePort) -> None:  # noqa: F811
        port = live_server
        assert TestUploadSafety._create(port, "rc")[0] == 201
        store = live_server.registry.handles["rc"].store
        store.add_job(Job(job_id="rc:ingest:1", novel_id="rc", kind="ingest", created_at=1.0))
        assert store.transition_job("rc:ingest:1", [JobStatus.PENDING], JobStatus.RUNNING, started_at=2.0)  # worker wins

        status, body = _request(port, "POST", "/api/projects/rc/jobs/rc:ingest:1/cancel", body=b"{}")

        assert status == 409 and "RUNNING" in body["error"]
        job = store.get_job("rc:ingest:1")
        assert job.status is JobStatus.RUNNING and job.error_summary == ""

    def test_a_cancel_cannot_be_overwritten_by_the_workers_terminal_write(self, tmp_path: Path) -> None:
        store = Store(str(tmp_path / "t.db"))
        job = _job(store)
        store.transition_job(job.job_id, [JobStatus.PENDING], JobStatus.CANCELLED)
        assert not store.transition_job(job.job_id, [JobStatus.RUNNING], JobStatus.SUCCEEDED)
        assert store.get_job(job.job_id).status is JobStatus.CANCELLED


class TestRunBookkeeping:
    def test_a_failed_non_pipeline_job_keeps_its_run_id_and_the_detail_route_lists_stages(
        self, live_server: LivePort, tmp_path: Path  # noqa: F811
    ) -> None:
        port = live_server
        assert TestUploadSafety._create(port, "fj")[0] == 201
        handle = live_server.registry.handles["fj"]
        job = Job(job_id="fj:ingest:1", novel_id="fj", kind="ingest", created_at=1.0)
        handle.store.add_job(job)
        worker = Store(handle.source.db_path)
        run_job(worker, job, {"sources_path": str(tmp_path / "missing-sources.toml")})
        worker.close()

        status, body = _request(port, "GET", "/api/projects/fj/jobs/fj:ingest:1")
        assert status == 200 and body["status"] == "FAILED"
        assert body["run_id"]
        assert [r["stage_name"] for r in body["stage_runs"]] == ["ingest"]
        assert body["stage_runs"][0]["status"] == "FAILED"

    def test_a_non_pipeline_jobs_run_row_is_finalised(self, tmp_path: Path) -> None:
        store = Store(str(tmp_path / "t.db"))
        ok = _job(store, "n:persona:ok", "persona")
        run_job(store, ok, {})
        done = store.get_job(ok.job_id)
        assert done.status is JobStatus.SUCCEEDED
        assert store.get_pipeline_run(done.run_id).status is StageStatus.SUCCEEDED

        # Another novel: a run id is keyed by novel and clock second, so the same novel would share the finished row.
        bad = _job(store, "m:render:bad", "render", novel_id="m")
        run_job(store, bad, {"engine": "no-such-engine"})
        failed = store.get_job(bad.job_id)
        assert failed.status is JobStatus.FAILED
        assert store.get_pipeline_run(failed.run_id).status is StageStatus.FAILED

    def test_an_interrupt_in_a_job_is_recorded_interrupted_and_reraised(self, tmp_path: Path, monkeypatch) -> None:
        store = Store(str(tmp_path / "t.db"))
        job = _job(store)

        def boom(store: Store, job: Job, params: dict) -> str:
            ensure_pipeline_run(store, novel_id="n", source_digest="s", run_id="r1")
            store.update_job(job.job_id, run_id="r1")
            raise KeyboardInterrupt

        monkeypatch.setattr(jobs, "_dispatch", boom)
        with pytest.raises(KeyboardInterrupt):
            run_job(store, job, {})
        assert store.get_job(job.job_id).status is JobStatus.INTERRUPTED
        assert store.get_pipeline_run("r1").status is StageStatus.FAILED

    def test_keyboard_interrupt_inside_run_stage_closes_the_stage(self, tmp_path: Path) -> None:
        store = Store(str(tmp_path / "t.db"))
        run = ensure_pipeline_run(store, novel_id="n", source_digest="s")

        def interrupted() -> None:
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            run_stage(store, run_id=run.run_id, stage_name="s", input_digest="d", fn=interrupted)
        assert store.list_stage_runs(run.run_id)[0].status is StageStatus.FAILED


class TestStartupSweep:
    def test_closes_job_stage_and_run_rows_and_staleness_says_the_build_did_not_finish(self, tmp_path: Path) -> None:
        projects = tmp_path / "projects"
        projects.mkdir()
        store = Store(str(projects / "b.db"))
        store.add_novel("b", "B", "x.epub", "generic")
        build = ensure_pipeline_run(
            store, novel_id="b", source_digest="s", run_id="b-build", pipeline_version=PIPELINE_VERSION, is_build=True
        )
        start_stage(store, run_id=build.run_id, stage_name="3 mentions", input_digest="d")
        store.add_job(Job(job_id="b:pipeline:1", novel_id="b", kind="pipeline", run_id=build.run_id,
                          status=JobStatus.RUNNING, created_at=1.0))
        assert "still running" in staleness_reason(store, "b")
        # A CLI build against the same database has RUNNING rows and no job row: live work the sweep must not close.
        cli = ensure_pipeline_run(store, novel_id="b", source_digest="s", run_id="b-cli")
        start_stage(store, run_id=cli.run_id, stage_name="cli stage", input_digest="c")
        store.close()

        registry = Registry([], corrections_dir=tmp_path / "c", projects_dir=projects)
        store = registry.handles["b"].store

        assert store.get_job("b:pipeline:1").status is JobStatus.INTERRUPTED
        (stage_row,) = store.list_stage_runs("b-build")
        assert stage_row.status is StageStatus.FAILED and "interrupted" in stage_row.error_summary
        assert store.get_pipeline_run("b-build").status is StageStatus.FAILED
        reason = staleness_reason(store, "b")
        assert "did not finish" in reason and "still running" not in reason
        assert store.get_pipeline_run("b-cli").status is StageStatus.RUNNING
        assert store.list_stage_runs("b-cli")[0].status is StageStatus.RUNNING


class TestServerSafety:
    def test_payload_after_a_job_completes_reflects_its_result_without_another_write(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        registry = Registry([], corrections_dir=tmp_path / "c", projects_dir=tmp_path / "projects")
        handle = registry.create_project("pc", "PC", "novel")
        queue = JobQueue()
        make_handler(registry, queue)  # wires the queue's completion callback to the handles
        assert not handle.payload().get("chapters")  # primes the cache

        def adds_a_chapter(store: Store, job: Job, params: dict) -> str:
            store.add_chapter(Chapter(novel_id="pc", number=1.0, title="One", source_href="p", blocks=[]))
            store.conn.commit()
            return "r"

        monkeypatch.setattr(jobs, "_dispatch", adds_a_chapter)
        handle.store.add_job(Job(job_id="pc:ingest:1", novel_id="pc", kind="ingest", created_at=1.0))
        queue.start()
        queue.submit(job_id="pc:ingest:1", novel_id="pc", db_path=handle.source.db_path, params={})
        queue._q.join()

        assert [c["number"] for c in handle.payload()["chapters"]] == [1.0]

    def test_delete_is_refused_while_a_job_is_queued(self, live_server: LivePort) -> None:  # noqa: F811
        port = live_server
        assert TestUploadSafety._create(port, "dq")[0] == 201
        handle = live_server.registry.handles["dq"]
        handle.store.add_job(Job(job_id="dq:ingest:1", novel_id="dq", kind="ingest", created_at=1.0))

        status, body = _request(port, "DELETE", "/api/projects/dq")

        assert status == 409 and "queued or running" in body["error"]
        assert Path(handle.source.db_path).exists() and "dq" in live_server.registry.handles
        handle.store.transition_job("dq:ingest:1", [JobStatus.PENDING], JobStatus.CANCELLED)
        assert _request(port, "DELETE", "/api/projects/dq")[0] == 200

    def test_a_job_whose_database_is_missing_never_creates_one(self, tmp_path: Path) -> None:
        db = tmp_path / "gone.db"
        queue = JobQueue()
        queue.start()
        queue.submit(job_id="gone:ingest:1", novel_id="gone", db_path=str(db), params={})
        queue._q.join()
        assert not list(tmp_path.glob("gone.db*"))

    def test_deleting_an_applied_correction_answers_409(self, live_server: LivePort) -> None:  # noqa: F811
        port = live_server
        assert TestUploadSafety._create(port, "ac")[0] == 201
        log = live_server.registry.handles["ac"].corrections
        log.add(Correction(novel_id="ac", type=CorrectionType.MERGE_ENTITIES, payload={}, id="c1"))
        log.mark_applied("c1")

        status, body = _request(port, "DELETE", "/api/novels/ac/corrections/c1")

        assert status == 409 and "already been applied" in body["error"]
        assert any(c.id == "c1" for c in log)


def test_a_wider_chapter_range_does_not_reuse_a_narrower_builds_stage_digest() -> None:
    narrow = jobs.pipeline_stage_digest("src", "0 ingest", {"chapters": "1-3"})
    assert narrow != jobs.pipeline_stage_digest("src", "0 ingest", {"chapters": "1-10"})
    assert narrow != jobs.pipeline_stage_digest("src", "0 ingest", {})
    # whole-book key unchanged, so a CLI-built book still resumes
    assert jobs.pipeline_stage_digest("src", "0 ingest", {}) == jobs.digest_text(f"src|0 ingest|v{PIPELINE_VERSION}")


def test_cost_route_says_when_the_episode_is_an_assumed_one(live_server: LivePort) -> None:  # noqa: F811
    assert TestUploadSafety._create(live_server, "cm")[0] == 201
    status, body = _request(live_server, "GET", "/api/novels/cm/episodes/ep1/cost?tier=path1")
    assert status == 200 and body["assumed_episode"] is True and body["num_shots"] == 12


def test_render_generate_drops_server_owned_params(live_server: LivePort) -> None:  # noqa: F811
    """`render/generate` handed the raw body to the job, so a request could name `panel_dir` (a server folder)."""
    assert TestUploadSafety._create(live_server, "sg")[0] == 201
    body = json.dumps({"engine": "stub", "panel_dir": "/tmp/echotales-escape"}).encode()
    status, queued = _request(live_server, "POST", "/api/novels/sg/render/generate", body=body)
    assert status == 202
    job = live_server.registry.handles["sg"].store.get_job(queued["job_id"])
    assert "panel_dir" not in json.loads(job.params_json)


class TestRenderJobOutcome:
    """What a Studio render job reports."""

    def test_a_render_with_an_undrawn_panel_is_partial_not_succeeded(self, tmp_path: Path, monkeypatch) -> None:
        from echotales.pipeline.render import panels
        from echotales.pipeline.render.plan import PANEL_PLAN_FILE

        store = Store(str(tmp_path / "t.db"))

        def fake(novel_id, store_, *, out_dir, version, **kw):  # type: ignore[no-untyped-def]
            vdir = Path(out_dir) / "ch1" / version
            vdir.mkdir(parents=True)
            row = {
                "schema_version": 1, "novel_id": novel_id, "chapter": 1.0, "panel_seq": 0, "panel_id": "n:1:0",
                "scene_index": 0, "slot_kind": "scene", "lead_block": 0, "block_indexes": [0], "prompt": "p",
                "engine": "x", "width": 8, "height": 8, "seed": 1, "image_path": "p0.png", "cache_key": "k",
                "provenance": "generated",
            }
            (vdir / PANEL_PLAN_FILE).write_text(json.dumps(row) + "\n", encoding="utf-8")  # no p0.png written

        monkeypatch.setattr(panels, "get_engine", lambda name: object())
        monkeypatch.setattr(panels, "render_panels", fake)
        params = {"engine": "stub", "panel_dir": str(tmp_path / "panels"), "chapters": [1.0]}
        run_job(store, _job(store, "n:render:1", "render"), params)
        job = store.get_job("n:render:1")
        assert job.status is JobStatus.PARTIAL and "1 panel(s) were not drawn" in job.error_summary
