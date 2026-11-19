"""The server-side half of M4's long-series and languages items: the pipeline job carries its estimate, a finished
build records the chapter baseline, and the upload route states the language support the Studio shows."""

from __future__ import annotations

import json

from echotales.pipeline import long_series
from test_webview_server_jobs import (  # noqa: F401  (live_server is a pytest fixture)
    TestPipelineJob,
    TestUploadSafety,
    _request,
    live_server,
)

_JSON = {"Content-Type": "application/json"}


def test_the_upload_reply_states_that_only_english_is_supported(live_server) -> None:  # noqa: F811
    assert TestUploadSafety._create(live_server, "lang", "Lang")[0] == 201
    status, body = TestUploadSafety._upload(live_server, "lang")
    assert status == 201, body
    assert body["language"]["supported"] == ["en"]
    assert "English" in body["language"]["statement"]


def test_the_project_status_carries_the_same_language_statement(live_server) -> None:  # noqa: F811
    assert TestUploadSafety._create(live_server, "lang2", "Lang")[0] == 201
    _, listed = _request(live_server, "GET", "/api/projects")
    project = next(p for p in listed if p["id"] == "lang2")
    assert project["language"]["supported"] == ["en"]


def test_a_pipeline_job_returns_and_keeps_its_estimate_and_records_the_baseline(live_server) -> None:  # noqa: F811
    port = live_server
    assert TestUploadSafety._create(port, "est", "Est")[0] == 201
    assert TestUploadSafety._upload(port, "est")[0] == 201

    status, body = _request(port, "POST", "/api/projects/est/pipeline", body=json.dumps({"no_llm": True}).encode(),
                            headers=_JSON)
    assert status == 202, body
    assert body["estimate"]["stages"] and body["estimate"]["measured"] is False
    job = TestPipelineJob._wait(port, "est", body["job_id"])
    assert job["status"] == "SUCCEEDED", job

    store = live_server.registry.handles["est"].store
    assert json.loads(store.get_job(body["job_id"]).params_json)["estimate"]["chapters"] == body["estimate"]["chapters"]
    # The finished build is the baseline later edits are compared against.
    assert long_series.changed_chapters(store, "est") == []
    assert store.conn.execute("SELECT COUNT(*) FROM derived_artifact WHERE id LIKE 'chapterhash:est:%'").fetchone()[0] == 1
