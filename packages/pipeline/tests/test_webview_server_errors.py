"""Machine-readable error codes and job progress over a real HTTP server."""
# ruff: noqa: F811  (a pytest fixture imported by name is redefined by each test argument)

from __future__ import annotations

import time

from echotales.core.lifecycle import JobStatus
from echotales.core.models import Job
from echotales.core.pipeline_run import ensure_pipeline_run
from echotales.pipeline import gpu
from echotales.pipeline.errors import ErrorCode, Refusal
from echotales.pipeline.jobs import PIPELINE_STAGES, pipeline_stage_names
from test_webview_server_ids import NOVEL, _call, seeded  # noqa: F401  (fixture)
from test_webview_server_jobs import live_server  # noqa: F401  (fixture)


def test_not_found_and_bad_request_carry_codes_and_keep_error(seeded) -> None:
    status, body = _call(seeded, "GET", "/api/novels/nope/chapters")
    assert (status, body["code"]) == (404, "NOT_FOUND")
    assert body["error"].startswith("unknown novel")
    status, body = _call(seeded, "POST", f"/api/novels/{NOVEL}/characters/{NOVEL}%3Aself%3Aab12cd/voice", {})
    assert (status, body["code"]) == (400, "BAD_REQUEST")


def test_voice_job_refused_for_a_stale_build_carries_stale_build(seeded) -> None:
    status, body = _call(seeded, "POST", f"/api/projects/{NOVEL}/voice", {"engine": "chatterbox"})
    assert status == 409
    assert body["code"] == "STALE_BUILD"
    assert "no recorded build" in body["error"]


def test_project_busy_code(seeded) -> None:
    store = seeded.registry.handles[NOVEL].store
    store.add_job(Job(job_id="j-busy", novel_id=NOVEL, kind="ingest", created_at=time.time()))
    status, body = _call(seeded, "DELETE", f"/api/projects/{NOVEL}")
    assert (status, body["code"]) == (409, "PROJECT_BUSY")


def test_unhandled_exception_is_500_internal(seeded, monkeypatch) -> None:
    def boom() -> None:
        raise RuntimeError("disk exploded at /secret/path")

    monkeypatch.setattr(seeded.registry, "manifest", boom)
    status, body = _call(seeded, "GET", "/api/manifest")
    assert (status, body["code"]) == (500, "INTERNAL")


def test_refusal_is_a_plain_str_with_a_code() -> None:
    r = Refusal("msg", ErrorCode.GPU_BUSY)
    assert r == "msg" and isinstance(r, str) and r.code is ErrorCode.GPU_BUSY
    assert (r or "x") is r


def test_refusal_functions_carry_their_kind(monkeypatch) -> None:
    from echotales.pipeline import compute, review_gate
    from echotales.pipeline.voice.bank import noncommercial_refusal

    assert noncommercial_refusal("ears", m4b=True, allowed=False).code is ErrorCode.LICENCE_REFUSED

    monkeypatch.setattr(review_gate, "staleness_reason", lambda *_: None)
    monkeypatch.setattr(review_gate, "unlocked_reason", lambda *_: None)

    class Log:
        def summary(self) -> dict:
            return {"pending_actionable": 2}

    assert review_gate.voice_refusal(object(), "b", "chatterbox", Log()).code is ErrorCode.PENDING_CORRECTIONS

    class Busy:
        free = False

        def describe(self) -> str:
            return "in use"

    monkeypatch.setenv("ECHOTALES_IMAGE_PROVIDER", "local")
    monkeypatch.setattr(gpu, "gpu_status", lambda: Busy())
    assert compute.resource_refusal("noobai").code is ErrorCode.GPU_BUSY
    monkeypatch.setattr(gpu, "gpu_status", lambda: None)
    assert compute.resource_refusal("noobai").code is ErrorCode.RESOURCE_REFUSED


def test_unlocked_bible_refusal_code(seeded) -> None:
    from echotales.pipeline.review_gate import unlocked_reason

    store = seeded.registry.handles[NOVEL].store
    assert unlocked_reason(store, NOVEL).code is ErrorCode.BIBLE_UNLOCKED


def _stage_rows(store, run_id: str, rows: list[tuple[str, str]]) -> None:
    for i, (name, status) in enumerate(rows):
        store.conn.execute(
            "INSERT INTO stage_run(stage_run_id, run_id, stage_name, started_at, status) VALUES (?,?,?,?,?)",
            (f"{run_id}-{i}", run_id, name, 100.0 + i, status),
        )
    store.conn.commit()


def test_job_progress_for_pipeline_and_single_stage_jobs(seeded) -> None:
    store = seeded.registry.handles[NOVEL].store
    run = ensure_pipeline_run(store, novel_id=NOVEL, source_digest="d", pipeline_version="2", is_build=True)
    _stage_rows(store, run.run_id, [("0 ingest", "SUCCEEDED"), ("2 segment", "SUCCEEDED"), ("3 mentions", "RUNNING")])
    now = time.time()
    store.add_job(Job(job_id="p1", novel_id=NOVEL, kind="pipeline", run_id=run.run_id, status=JobStatus.RUNNING,
                      created_at=now - 20, started_at=now - 10))
    store.add_job(Job(job_id="v1", novel_id=NOVEL, kind="voice", status=JobStatus.SUCCEEDED,
                      created_at=now - 9, started_at=now - 8, finished_at=now - 3))
    store.add_job(Job(job_id="q1", novel_id=NOVEL, kind="render", created_at=now))

    status, jobs = _call(seeded, "GET", f"/api/projects/{NOVEL}/jobs")
    assert status == 200
    by = {j["job_id"]: j for j in jobs}
    assert (by["p1"]["stage"], by["p1"]["stage_index"], by["p1"]["stage_count"]) == (
        "3 mentions", 3, len(PIPELINE_STAGES)
    )
    assert 9 < by["p1"]["elapsed_s"] < 60 and by["p1"]["finished_at"] is None
    assert (by["v1"]["stage_index"], by["v1"]["stage_count"], by["v1"]["elapsed_s"]) == (1, 1, 5.0)
    assert (by["q1"]["stage"], by["q1"]["stage_index"], by["q1"]["elapsed_s"]) == (None, 0, None)

    status, detail = _call(seeded, "GET", f"/api/projects/{NOVEL}/jobs/p1")
    assert (detail["stage"], detail["stage_index"], detail["stage_count"]) == ("3 mentions", 3, 9)
    assert len(detail["stage_runs"]) == 3


def test_pipeline_stage_count_drops_skipped_optional_stages() -> None:
    assert len(pipeline_stage_names({"skip_reader": True, "skip_appearance": True})) == len(PIPELINE_STAGES) - 2


def test_job_list_query_count_does_not_grow_with_jobs(seeded) -> None:
    store = seeded.registry.handles[NOVEL].store
    for i in range(30):
        run = ensure_pipeline_run(store, novel_id=NOVEL, source_digest=f"d{i}", pipeline_version="2")
        store.add_job(Job(job_id=f"m{i}", novel_id=NOVEL, kind="pipeline", run_id=run.run_id, created_at=time.time()))
    seen: list[str] = []
    store.conn.set_trace_callback(lambda sql: seen.append(sql) if "stage_run" in sql else None)
    status, jobs = _call(seeded, "GET", f"/api/projects/{NOVEL}/jobs")
    store.conn.set_trace_callback(None)
    assert status == 200 and len(jobs) == 30
    assert len(seen) == 1, seen  # one batched query, not one per job on a 2 s poll
