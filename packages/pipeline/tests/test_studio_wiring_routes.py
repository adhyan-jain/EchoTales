"""Studio wiring routes (roadmap M5 surface): language note, run estimate, packs, companion, gender, delivery, voices.

One real `HTTPServer` per test over a small built book ("t", three chapters), run from a temporary working directory
because `paths.DATA_ROOT` is relative.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.webview_server import LANGUAGE_SUPPORT, NovelSource, Registry, make_handler
from test_reader_cast import _book


class Server:
    def __init__(self, port: int, registry: Registry, root: Path) -> None:
        self.port, self.registry, self.root = port, registry, root

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
    monkeypatch.chdir(tmp_path)
    book = _book(tmp_path, 3, "t")
    registry = Registry([NovelSource(novel_id="t", label="T", db_path=book.path)], corrections_dir=tmp_path / "corrections")
    queue = JobQueue()
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, queue))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield Server(httpd.server_address[1], registry, tmp_path)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def test_project_status_carries_the_language_statement(srv) -> None:
    status, projects = srv.call("GET", "/api/projects")
    assert status == 200
    assert projects[0]["language"]["statement"] == LANGUAGE_SUPPORT["statement"]
    assert projects[0]["language"]["supported"] == ["en"]
