"""Studio wiring routes (roadmap M5 surface): language note, run estimate, packs, companion, gender, delivery, voices.

One real `HTTPServer` per test over a small built book ("t", three chapters), run from a temporary working directory
because `paths.DATA_ROOT` is relative.
"""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.webview_server import LANGUAGE_SUPPORT, NovelSource, Registry, make_handler
from test_reader_cast import _book


class Server:
    def __init__(self, port: int, registry: Registry, root: Path, queue: JobQueue) -> None:
        self.port, self.registry, self.root, self.queue = port, registry, root, queue

    def run_job(self, kind: str, params: dict | None = None) -> dict:
        """Queue `kind` over HTTP, start the worker, and wait for the job to end."""
        status, queued = self.call("POST", f"/api/projects/t/{kind}", params or {})
        assert status == 202, queued
        self.queue.start()
        deadline = time.time() + 20
        while time.time() < deadline:
            _, job = self.call("GET", f"/api/projects/t/jobs/{queued['job_id']}")
            if job["status"] not in ("PENDING", "RUNNING"):
                return job
            time.sleep(0.05)
        raise AssertionError("job did not finish")

    def call(self, method: str, path: str, body: object = None, *, raw: bytes | None = None, headers: dict | None = None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        data = raw
        if raw is None and body is not None:
            data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
        conn.request(method, path, body=data, headers=h)
        resp = conn.getresponse()
        payload = resp.read()
        ctype = resp.getheader("Content-Type") or ""
        conn.close()
        return resp.status, (json.loads(payload) if payload and "json" in ctype else payload)


def multipart(filename: str, data: bytes) -> tuple[bytes, dict]:
    boundary = "XBOUNDARYX"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


@pytest.fixture
def srv(tmp_path, monkeypatch):
    yield from _serve(tmp_path, monkeypatch)


@pytest.fixture
def srv_password(tmp_path, monkeypatch):
    monkeypatch.setenv("ECHOTALES_WEBVIEW_PASSWORD", "hunter2")
    yield from _serve(tmp_path, monkeypatch)


def _serve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    book = _book(tmp_path, 3, "t")
    registry = Registry([NovelSource(novel_id="t", label="T", db_path=book.path)], corrections_dir=tmp_path / "corrections")
    queue = JobQueue()
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, queue))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield Server(httpd.server_address[1], registry, tmp_path, queue)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def test_project_status_carries_the_language_statement(srv) -> None:
    status, projects = srv.call("GET", "/api/projects")
    assert status == 200
    assert projects[0]["language"]["statement"] == LANGUAGE_SUPPORT["statement"]
    assert projects[0]["language"]["supported"] == ["en"]


def test_a_queued_pipeline_job_keeps_its_estimate_in_the_job_list(srv) -> None:
    status, queued = srv.call("POST", "/api/projects/t/pipeline", {})
    assert status == 202
    assert queued["estimate"]["stages"] and queued["estimate"]["seconds"] > 0
    status, jobs = srv.call("GET", "/api/projects/t/jobs")
    assert status == 200
    listed = next(j for j in jobs if j["job_id"] == queued["job_id"])
    # The Studio reads this while the job runs, so it must survive past the 202 reply.
    assert listed["estimate"] == queued["estimate"]
    assert {r["basis"] for r in listed["estimate"]["stages"]} <= {"measured", "estimate"}


def test_other_job_kinds_carry_no_estimate(srv) -> None:
    status, queued = srv.call("POST", "/api/projects/t/pack_export", {})
    assert status == 202
    _, jobs = srv.call("GET", "/api/projects/t/jobs")
    assert "estimate" not in next(j for j in jobs if j["job_id"] == queued["job_id"])


# --- packs ------------------------------------------------------------------------------------------------------------


def _pack_bytes(srv) -> bytes:
    from echotales.pipeline import packs

    out = srv.root / "made.etpack"
    packs.export_pack(srv.registry.handles["t"].store, "t", out)
    return out.read_bytes()


def test_packs_list_is_names_only_and_empty_at_first(srv) -> None:
    status, body = srv.call("GET", "/api/projects/t/packs")
    assert status == 200 and body == {"packs": []}
    assert srv.call("GET", "/api/projects/nope/packs")[0] == 404


def test_an_uploaded_pack_is_listed_by_name_and_never_by_path(srv) -> None:
    raw, headers = multipart("../../sneaky name.etpack", _pack_bytes(srv))
    status, body = srv.call("POST", "/api/projects/t/packs", raw=raw, headers=headers)
    assert status == 201, body
    assert body["name"] == "sneaky_name.etpack"
    stored = srv.root / "data" / "novels" / "t" / "packs" / "sneaky_name.etpack"
    assert stored.is_file() and not (srv.root / "sneaky name.etpack").exists()
    status, listed = srv.call("GET", "/api/projects/t/packs")
    assert [p["name"] for p in listed["packs"]] == ["sneaky_name.etpack"]
    assert listed["packs"][0]["bytes"] > 0 and listed["packs"][0]["report"] is None
    assert str(srv.root) not in json.dumps(listed)


def test_a_pack_upload_must_be_a_readable_etpack(srv) -> None:
    raw, headers = multipart("notes.txt", b"hello")
    status, body = srv.call("POST", "/api/projects/t/packs", raw=raw, headers=headers)
    assert status == 400 and ".etpack" in body["error"]
    raw, headers = multipart("fake.etpack", b"this is not a zip")
    status, body = srv.call("POST", "/api/projects/t/packs", raw=raw, headers=headers)
    assert status == 400
    assert not (srv.root / "data" / "novels" / "t" / "packs" / "fake.etpack").exists()
    assert srv.call("POST", "/api/projects/t/packs", {"x": 1})[0] == 400  # not multipart


def test_a_pack_upload_over_the_cap_is_refused(srv, monkeypatch) -> None:
    from echotales.pipeline import webview_server

    monkeypatch.setattr(webview_server, "_MAX_PACK_BODY", 1000)
    raw, headers = multipart("big.etpack", b"x" * 5000)
    status, _ = srv.call("POST", "/api/projects/t/packs", raw=raw, headers=headers)
    assert status == 413


def test_exporting_then_importing_leaves_a_report_beside_the_pack(srv) -> None:
    done = srv.run_job("pack_export", {"name": "mine"})
    assert done["status"] == "SUCCEEDED", done
    _, listed = srv.call("GET", "/api/projects/t/packs")
    assert [p["name"] for p in listed["packs"]] == ["mine.etpack"]
    done = srv.run_job("pack_import", {"name": "mine"})
    assert done["status"] == "SUCCEEDED", done
    _, listed = srv.call("GET", "/api/projects/t/packs")
    report = listed["packs"][0]["report"]
    assert set(report) >= {"applied", "skipped"} and isinstance(report["applied"], dict)
    # The report file is not itself a pack.
    assert [p["name"] for p in listed["packs"]] == ["mine.etpack"]


# --- companion --------------------------------------------------------------------------------------------------------


def test_the_companion_job_builds_into_the_projects_companion_folder(srv) -> None:
    done = srv.run_job("companion", {"through": 2})
    assert done["status"] == "SUCCEEDED", done
    site = srv.root / "data" / "novels" / "t" / "companion" / "through_2"
    assert (site / "index.html").is_file() and (site / "style.css").is_file()
    # Spoiler safety is companion.py's own tested rule; here only that chapter 3's name stays out of a through-2 page.
    assert "Arthur Vane" not in (site / "index.html").read_text(encoding="utf-8")


def test_a_companion_needs_a_positive_finite_chapter(srv) -> None:
    for bad in ({}, {"through": 0}, {"through": -1}, {"through": "x"}, {"through": "nan"}, {"through": True}):
        status, body = srv.call("POST", "/api/projects/t/companion", bad)
        assert status == 400 and "through" in body["error"], bad


def test_a_built_companion_is_listed_and_served_page_and_stylesheet(srv) -> None:
    assert srv.call("GET", "/api/projects/t/companions") == (200, {"companions": []})
    assert srv.run_job("companion", {"through": 3})["status"] == "SUCCEEDED"
    status, listed = srv.call("GET", "/api/projects/t/companions")
    assert status == 200 and [c["through"] for c in listed["companions"]] == [3]
    status, page = srv.call("GET", "/api/novels/t/companion/through_3/index.html")
    assert status == 200 and b"<h1>T</h1>" in page
    status, css = srv.call("GET", "/api/novels/t/companion/through_3/style.css")
    assert status == 200 and b"--bg" in css


def test_a_password_protected_server_opens_the_companion_page_with_the_session_token_in_the_link(srv_password) -> None:
    srv = srv_password
    site = srv.root / "data" / "novels" / "t" / "companion" / "through_3"
    site.mkdir(parents=True)
    (site / "index.html").write_text("<h1>T</h1>", encoding="utf-8")
    page = "/api/novels/t/companion/through_3/index.html"
    assert srv.call("GET", page)[0] == 401  # a link opened in a new tab cannot send a header...
    _, login = srv.call("POST", "/api/auth/login", {"password": "hunter2"})
    assert srv.call("GET", f"{page}?access_token={login['token']}")[0] == 200  # ...so the link carries the token
    assert srv.call("GET", f"{page}?access_token=wrong")[0] == 401
    assert srv.call("GET", f"/api/projects/t/packs?access_token={login['token']}")[0] == 401  # JSON API: header only


def test_the_companion_route_serves_nothing_outside_the_built_site(srv) -> None:
    assert srv.run_job("companion", {"through": 3})["status"] == "SUCCEEDED"
    secret = srv.root / "data" / "novels" / "t" / "companion" / "secret.txt"
    secret.write_text("no", encoding="utf-8")
    for path in (
        "/api/novels/t/companion/through_3/..%2Fsecret.txt",
        "/api/novels/t/companion/..%2Fsecret.txt/index.html",
        "/api/novels/t/companion/through_3/%2e%2e/secret.txt",
        "/api/novels/t/companion/through_3/other.txt",
        "/api/novels/t/companion/through_9/index.html",
        "/api/novels/t/companion/through_x/index.html",
    ):
        status, _ = srv.call("GET", path)
        assert status in (400, 404), path
    assert srv.call("GET", "/api/novels/nope/companion/through_3/index.html")[0] == 404
