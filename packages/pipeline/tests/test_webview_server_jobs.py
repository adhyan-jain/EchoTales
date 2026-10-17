"""Product Orchestration track: end-to-end HTTP coverage for
`webview_server.py`'s new routes -- project lifecycle, source upload,
ingestion trigger, job polling, and the output library.

Runs a real `HTTPServer` on an ephemeral port in a background thread (no
existing `test_webview_server.py` to extend -- the module had zero test
coverage before this track, per `docs/status/STATUS.md`'s own audit). Everything
here is local/stub: no GPU, no network, no real novel data.
"""

from __future__ import annotations

import json
import threading
import time
import zipfile
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.webview_server import Registry, make_handler


def _build_epub_bytes() -> bytes:
    import io

    docs = {
        "page-0.html": (
            '<div class="chapter type-1"><div class="chapter-title-wrap">'
            '<h2 class="chapter-title">Chapter 1: First</h2></div>'
            '<div class="ugc chapter-ugc"><p><strong>Chapter 1 - First</strong></p>'
            "<p>Opening narration.</p></div></div>"
        )
    }
    toc = [("Chapter 1: First", "page-0.html")]
    nav = "".join(
        f'<navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>{label}</text></navLabel>'
        f'<content src="{href}"/></navPoint>'
        for i, (label, href) in enumerate(toc)
    )
    ncx = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f"<docTitle><text>Test</text></docTitle><navMap>{nav}</navMap></ncx>"
    )
    manifest = "".join(
        f'<item id="d{i}" href="{href}" media-type="application/xhtml+xml"/>'
        for i, href in enumerate(docs)
    )
    spine = "".join(f'<itemref idref="d{i}"/>' for i in range(len(docs)))
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Test Novel</dc:title><dc:language>en</dc:language>"
        '<dc:identifier id="id">test</dc:identifier></metadata>'
        f'<manifest>{manifest}<item id="ncx" href="toc.ncx" '
        'media-type="application/x-dtbncx+xml"/></manifest>'
        f'<spine toc="ncx">{spine}</spine></package>'
    )
    container = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="book.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("book.opf", opf)
        z.writestr("toc.ncx", ncx)
        for href, body in docs.items():
            z.writestr(href, f"<html><body>{body}</body></html>")
    return buf.getvalue()


@pytest.fixture
def live_server(tmp_path: Path):
    registry = Registry(
        [], corrections_dir=tmp_path / "corrections", projects_dir=tmp_path / "projects"
    )
    job_queue = JobQueue()
    job_queue.start()
    handler = make_handler(registry, job_queue)
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        # Every `registry.handles` entry's `Store` was opened on the server
        # thread (each request that creates/discovers a project runs inside
        # `serve_forever`, which this fixture runs off-thread) -- sqlite3
        # forbids closing a connection from a different thread than the one
        # that created it, so this fixture leaves them for the OS/tmp_path
        # cleanup rather than cross-thread `close()`.


def _request(port: int, method: str, path: str, *, body: bytes = b"", headers: dict | None = None):
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, (json.loads(data) if data else None)


class TestProjectLifecycleAndJobs:
    def test_create_upload_ingest_poll_output(self, live_server: int) -> None:
        port = live_server

        status, body = _request(
            port, "POST", "/api/projects",
            body=json.dumps({"id": "toy", "title": "Toy Novel"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 201, body

        status, listed = _request(port, "GET", "/api/projects")
        assert status == 200
        assert any(p["id"] == "toy" for p in listed)
        toy = next(p for p in listed if p["id"] == "toy")
        assert toy["source_uploaded"] is False
        assert toy["ingested"] is False

        boundary = "TESTBOUNDARY"
        epub_bytes = _build_epub_bytes()
        multipart_body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="toy.epub"\r\n'
            "Content-Type: application/epub+zip\r\n\r\n"
        ).encode() + epub_bytes + f"\r\n--{boundary}--\r\n".encode()
        status, body = _request(
            port, "POST", "/api/projects/toy/source",
            body=multipart_body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert status == 201, body

        status, body = _request(port, "POST", "/api/projects/toy/ingest", body=b"{}")
        assert status == 202, body
        job_id = body["job_id"]

        deadline = time.time() + 10
        job_status = None
        while time.time() < deadline:
            status, job_body = _request(port, "GET", f"/api/projects/toy/jobs/{job_id}")
            assert status == 200
            job_status = job_body["status"]
            if job_status in ("SUCCEEDED", "FAILED", "PARTIAL"):
                break
            time.sleep(0.1)
        assert job_status == "SUCCEEDED", job_body

        status, listed = _request(port, "GET", "/api/projects")
        toy = next(p for p in listed if p["id"] == "toy")
        assert toy["ingested"] is True
        assert toy["chapter_count"] == 1

        status, output = _request(port, "GET", "/api/novels/toy/output")
        assert status == 200
        assert output["novel_id"] == "toy"

        # Resumability: re-POSTing /ingest with the same params must be a
        # fast no-op (the stage's skip-on-matching-digest check firing),
        # not a full rerun -- the concrete check the plan's Verification
        # section calls for, not just an aspirational claim. `run_id` can
        # collide with the first job's (both timestamp-keyed to the same
        # second), so the real signal is "exactly one 'ingest' StageRun
        # exists across both jobs," not "job2 has zero" -- a shared run_id
        # would otherwise list job1's own row under job2 too.
        status, first_job_detail = _request(port, "GET", f"/api/projects/toy/jobs/{job_id}")
        status, body2 = _request(port, "POST", "/api/projects/toy/ingest", body=b"{}")
        assert status == 202
        job2_id = body2["job_id"]
        deadline = time.time() + 5
        job2_status = None
        while time.time() < deadline:
            status, job2_body = _request(port, "GET", f"/api/projects/toy/jobs/{job2_id}")
            job2_status = job2_body["status"]
            if job2_status in ("SUCCEEDED", "FAILED", "PARTIAL"):
                break
            time.sleep(0.05)
        assert job2_status == "SUCCEEDED", job2_body
        ingest_stage_run_ids = {
            r["stage_run_id"]
            for body in (first_job_detail, job2_body)
            for r in body["stage_runs"]
            if r["stage_name"] == "ingest"
        }
        assert len(ingest_stage_run_ids) == 1

    def test_render_generate_rejects_paid_engine(self, live_server: int) -> None:
        port = live_server
        _request(
            port, "POST", "/api/projects",
            body=json.dumps({"id": "toy2", "title": "Toy Novel 2"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        status, body = _request(
            port, "POST", "/api/novels/toy2/render/generate",
            body=json.dumps({"engine": "gemini"}).encode(),
        )
        assert status == 400
        assert "gemini" in body["error"]

    def test_real_engine_is_refused_while_the_gpu_is_busy_but_stub_is_not(
        self, live_server: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from echotales.pipeline import gpu

        port = live_server
        _request(
            port, "POST", "/api/projects",
            body=json.dumps({"id": "toy3", "title": "Toy Novel 3"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        monkeypatch.setattr(gpu, "gpu_status", lambda: gpu.GpuStatus("RTX", 5200, 8188))
        status, body = _request(
            port, "POST", "/api/novels/toy3/render/generate", body=json.dumps({"engine": "noobai"}).encode()
        )
        assert status == 409 and "GPU is busy" in body["error"] and "5200 of 8188" in body["error"]
        assert _request(port, "GET", "/api/gpu")[1] == {
            "available": True, "free": False, "name": "RTX", "used_mb": 5200, "total_mb": 8188,
        }
        status, _ = _request(port, "POST", "/api/novels/toy3/render/generate", body=json.dumps({"engine": "stub"}).encode())
        assert status == 202

        monkeypatch.setattr(gpu, "gpu_status", lambda: None)
        status, body = _request(
            port, "POST", "/api/novels/toy3/render/generate", body=json.dumps({"engine": "noobai"}).encode()
        )
        assert status == 409 and "NVIDIA GPU" in body["error"]

        # The generic job route used to skip the guard (and the genre digest) for render and reference_gen.
        monkeypatch.setattr(gpu, "gpu_status", lambda: gpu.GpuStatus("RTX", 5200, 8188))
        for kind in ("render", "reference_gen"):
            status, body = _request(
                port, "POST", f"/api/projects/toy3/{kind}", body=json.dumps({"engine": "noobai"}).encode()
            )
            assert status == 409 and "GPU is busy" in body["error"], kind

        # A malformed genre body is a 400, not a server error.
        for payload in ({"genre": []}, {"genre": "klingon"}, ["x"]):
            status, _ = _request(port, "POST", "/api/projects/toy3/genre", body=json.dumps(payload).encode())
            assert status == 400, payload

    def test_delete_project(self, live_server: int) -> None:
        port = live_server
        _request(
            port, "POST", "/api/projects",
            body=json.dumps({"id": "toy3", "title": "Toy Novel 3"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        status, body = _request(port, "DELETE", "/api/projects/toy3")
        assert status == 200
        assert body["removed"] is True

        status, listed = _request(port, "GET", "/api/projects")
        assert all(p["id"] != "toy3" for p in listed)
