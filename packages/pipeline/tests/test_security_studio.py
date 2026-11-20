"""Security review of the local Studio server (2026-11-21, EVOLUTION 4.176): one test per confirmed finding.

Each test names the exploit it closes. Real server on an ephemeral port, stub everything else; no network."""

from __future__ import annotations

import io
import json
import threading
import zipfile
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest
from echotales.pipeline import packs
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.voice.export import chapter_metadata
from echotales.pipeline.webview_server import (
    Registry,
    check_bind,
    make_handler,
    sanitize_job_params,
)
from PIL import Image
from test_webview_server_jobs import _request, live_server  # noqa: F401  (fixture)


class RecordingQueue(JobQueue):
    """Collects what the HTTP route would have run, so a test can see the params that reached the worker."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[dict] = []

    def submit(self, *, job_id, novel_id, db_path, params):  # type: ignore[no-untyped-def]
        self.seen.append(params)


@pytest.fixture
def recording_server(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    registry = Registry([], corrections_dir=tmp_path / "corrections", projects_dir=tmp_path / "projects")
    queue = RecordingQueue()
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, queue))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    port = httpd.server_address[1]
    status, _ = _request(port, "POST", "/api/projects", body=json.dumps({"id": "sec", "title": "S"}).encode())
    assert status == 201
    try:
        yield port, queue
    finally:
        httpd.shutdown()
        t.join(timeout=5)


def _post_job(port, kind: str, params: dict):
    return _request(port, "POST", f"/api/projects/sec/{kind}", body=json.dumps(params).encode())


# --- F1: job parameters naming server paths ---------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["pages", "episode", "render", "ingest", "resolve", "comic"])
def test_a_request_cannot_choose_where_a_job_reads_or_writes(recording_server, kind: str) -> None:
    """`panel_dir`/`out_dir` came straight from the body for pages, episode and render: a POST made them write (and
    append VERSIONS.md) into any folder the server's user owns; `sources_path` made ingest read any toml."""
    port, queue = recording_server
    evil = {"panel_dir": "/tmp/x", "audio_dir": "/tmp/x", "out_dir": "/tmp/x", "out_root": "/tmp/x",
            "sources_path": "/etc/passwd", "source_path": "/etc/passwd", "corrections_path": "/tmp/c.jsonl",
            "bank": "/", "chapters": [1], "engine": "stub", "tier": "preview"}
    _post_job(port, kind, evil)
    if not queue.seen:  # a route may refuse for another reason (engine, GPU); then nothing reached the worker
        return
    params = queue.seen[-1]
    for key in ("panel_dir", "audio_dir", "out_dir", "out_root", "bank", "source_path"):
        assert key not in params, key
    assert params.get("sources_path", "").endswith("sources.toml") or "sources_path" not in params
    assert params.get("corrections_path", "") != "/tmp/c.jsonl"


def test_sanitize_strips_paths_and_refuses_a_traversing_suffix() -> None:
    assert sanitize_job_params({"out_dir": "/etc", "chapters": [1]}) == {"chapters": [1]}
    for bad in ("../../../tmp/x", "a/b", "..", ".hidden", "x" * 41, 7):
        with pytest.raises(ValueError):
            sanitize_job_params({"suffix": bad})
    assert sanitize_job_params({"suffix": "motion-comic.v2"})["suffix"] == "motion-comic.v2"
    with pytest.raises(ValueError):
        sanitize_job_params(["not", "an", "object"])


def test_a_traversing_suffix_is_a_400_over_http(recording_server) -> None:
    port, queue = recording_server
    status, body = _post_job(port, "pages", {"chapters": [1], "suffix": "../../../../tmp/pwn"})
    assert status == 400 and "suffix" in body["error"]
    assert queue.seen == []


# --- F7: unbounded queueing -------------------------------------------------------------------------------------


def test_job_queue_is_bounded_per_project(recording_server, monkeypatch) -> None:
    import echotales.pipeline.webview_server as ws

    monkeypatch.setattr(ws, "MAX_UNFINISHED_JOBS", 3)
    port, _ = recording_server
    codes = [_post_job(port, "ingest", {})[0] for _ in range(5)]
    assert codes[:3] == [202, 202, 202] and codes[3:] == [429, 429]


# --- F2: DNS rebinding ------------------------------------------------------------------------------------------


def _raw(port, method: str, path: str, headers: dict, body: bytes = b""):
    conn = HTTPConnection("127.0.0.1", int(port), timeout=10)
    conn.putrequest(method, path, skip_host=True)
    for k, v in headers.items():
        conn.putheader(k, v)
    conn.putheader("Content-Length", str(len(body)))
    conn.endheaders(body)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_a_rebound_hostname_is_refused_when_auth_is_off(live_server) -> None:  # noqa: F811
    """attacker.example re-pointed at 127.0.0.1 is same-origin with the server (Origin == Host), so the Origin
    check alone let its page POST and read every response."""
    port = live_server
    host = f"attacker.example:{port}"
    status, _ = _raw(port, "GET", "/api/projects", {"Host": host})
    assert status == 403
    status, _ = _raw(port, "POST", "/api/projects", {"Host": host, "Origin": f"http://{host}"},
                     b'{"id":"x","title":"x"}')
    assert status == 403
    status, _ = _raw(port, "GET", "/api/projects", {"Host": f"localhost:{port}"})
    assert status == 200
    status, _ = _raw(port, "GET", "/api/projects", {"Host": f"[::1]:{port}"})
    assert status == 200


# --- F3: binding beyond loopback --------------------------------------------------------------------------------


def test_binding_beyond_loopback_needs_a_password(monkeypatch) -> None:
    monkeypatch.delenv("ECHOTALES_ALLOW_OPEN_BIND", raising=False)
    for host in ("0.0.0.0", "192.168.1.5", "::"):
        with pytest.raises(SystemExit):
            check_bind(host, None)
        check_bind(host, "hunter2")
    for host in ("127.0.0.1", "localhost", "::1"):
        check_bind(host, None)
    # The container image sets this: compose publishes its port on the host's loopback only.
    monkeypatch.setenv("ECHOTALES_ALLOW_OPEN_BIND", "1")
    check_bind("0.0.0.0", None)


# --- F6: login guessing -----------------------------------------------------------------------------------------


def test_login_is_throttled_after_repeated_failures(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECHOTALES_WEBVIEW_PASSWORD", "correct horse")
    registry = Registry([], corrections_dir=tmp_path / "c", projects_dir=tmp_path / "p")
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, JobQueue()))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    port = httpd.server_address[1]
    try:
        wrong = json.dumps({"password": "nope"}).encode()
        codes = [_request(port, "POST", "/api/auth/login", body=wrong)[0] for _ in range(7)]
        assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
        # Even the right password waits out the window, which is what makes guessing slow.
        assert _request(port, "POST", "/api/auth/login", body=json.dumps({"password": "correct horse"}).encode())[0] == 429
    finally:
        httpd.shutdown()
        t.join(timeout=5)


# --- F8: Content-Length --------------------------------------------------------------------------------------


def test_a_negative_content_length_does_not_hang_the_server(live_server) -> None:  # noqa: F811
    port = live_server
    status, _ = _raw(port, "POST", "/api/projects", {"Host": f"127.0.0.1:{port}"}, b"")
    assert status in (400, 413)  # empty body: id/title required
    conn = HTTPConnection("127.0.0.1", int(port), timeout=5)
    conn.putrequest("POST", "/api/projects")
    conn.putheader("Content-Length", "-5")
    conn.endheaders()
    resp = conn.getresponse()
    assert resp.status == 413
    conn.close()


# --- F5: files served from the app's origin ------------------------------------------------------------------


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (1, 2, 3)).save(buf, "PNG")
    return buf.getvalue()


def _multipart(filename: str, data: bytes):
    b = "SECBOUNDARY"
    body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{b}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={b}"}


def test_output_html_and_svg_are_sandboxed_and_nosniff(live_server, tmp_path: Path, monkeypatch) -> None:  # noqa: F811
    monkeypatch.chdir(tmp_path)
    port = live_server
    _request(port, "POST", "/api/projects", body=json.dumps({"id": "xs", "title": "X"}).encode())
    root = tmp_path / "data" / "novels" / "xs"
    root.mkdir(parents=True)
    (root / "evil.html").write_text("<script>fetch('/api/projects')</script>")
    (root / "evil.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>')
    for name in ("evil.html", "evil.svg"):
        conn = HTTPConnection("127.0.0.1", int(port), timeout=10)
        conn.request("GET", f"/api/novels/xs/output/file?path={name}")
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 200
        assert "sandbox" in resp.getheader("Content-Security-Policy", "")
        assert resp.getheader("X-Content-Type-Options") == "nosniff"
        conn.close()


def test_a_reference_upload_must_be_a_real_picture(live_server, tmp_path: Path, monkeypatch) -> None:  # noqa: F811
    """`x.html` was written under the project and later served back as text/html from the Studio's origin."""
    monkeypatch.chdir(tmp_path)
    port = live_server
    _request(port, "POST", "/api/projects", body=json.dumps({"id": "ru", "title": "R"}).encode())
    handle = live_server.registry.handles["ru"]
    from echotales.core.enums import TargetKind
    from echotales.core.models import DiscoursePosition, Self

    handle.store.add_self(Self(id="ru:mira", novel_id="ru", canonical_label="Mira", kind=TargetKind.SELF,
                               first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    handle.store.conn.commit()
    path = "/api/novels/ru/characters/ru%3Amira/reference/upload"
    for name, data in (("x.html", b"<script>1</script>"), ("x.svg", b"<svg/>"), ("x.png", b"<html>not a png</html>")):
        body, headers = _multipart(name, data)
        status, out = _request(port, "POST", path, body=body, headers=headers)
        assert status == 400, (name, status, out)
    body, headers = _multipart("x.png", _png())
    status, out = _request(port, "POST", path, body=body, headers=headers)
    assert status == 201, out


# --- F4 / F9 / F10: archives and metadata -------------------------------------------------------------------


def test_a_pack_that_unpacks_huge_is_refused_before_it_is_read(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(packs, "MAX_MEMBER_BYTES", 1000)
    p = tmp_path / "bomb.etpack"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"format": "etpack", "version": 1}) + " " * 5000)
        for k in packs._KINDS:
            z.writestr(f"{k}.json", "[]")
    with pytest.raises(packs.PackError, match="unpacks to more than"):
        packs.read_pack(p)


def test_an_epub_member_that_unpacks_huge_is_refused(tmp_path: Path, monkeypatch) -> None:
    from echotales.pipeline.ingest import epub

    monkeypatch.setattr(epub, "MAX_MEMBER_BYTES", 1000)
    from test_webview_server_jobs import _build_epub_bytes

    p = tmp_path / "b.epub"
    p.write_bytes(_build_epub_bytes())
    with zipfile.ZipFile(p, "a") as z:
        z.writestr("big.html", "x" * 5000)
    book = epub.Epub(p)
    with pytest.raises(ValueError, match="unpacks to more than"):
        book.read("big.html")
    book.close()


def test_a_chapter_title_cannot_inject_metadata_sections() -> None:
    meta = chapter_metadata(["Real\n[CHAPTER]\nSTART=0\ntitle=forged", "a=b;c#d"], [1.0, 1.0], title="T\nartist=x", author="A")
    lines = meta.splitlines()
    assert lines.count("[CHAPTER]") == 2
    assert not any(line.startswith(("artist=x", "title=forged")) for line in lines)
    assert "title=a\\=b\\;c\\#d" in lines
