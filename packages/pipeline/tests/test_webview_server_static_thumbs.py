"""Frontend serving and panel thumbnails on the webview backend.

Two routes added in the 2026-09-26 webview QA pass, each guarding a failure
found in review rather than a hypothetical:

- `--static-dir` SPA serving: the first version joined the raw request path
  onto the build directory unchecked (`/../x` escaped it) and ran after the
  auth check, which would have 401'd the login screen itself.
- `?w=` thumbnails: the landing page pulled ~23 MB of full-size PNGs to fill
  480px tiles.

Runs a real `HTTPServer` on an ephemeral port, like test_webview_server_jobs.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from io import BytesIO
from pathlib import Path

import pytest
from echotales.pipeline import webview_server
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.webview_server import Registry, make_handler
from PIL import Image


def _start(tmp_path: Path, **kwargs):
    registry = Registry([], corrections_dir=tmp_path / "corrections", projects_dir=tmp_path / "projects")
    queue = JobQueue()
    queue.start()
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, queue, **kwargs))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def _get(port: int, path: str) -> tuple[int, dict[str, str], bytes]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    headers = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    return resp.status, headers, body


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A backend with one project ("toy") whose output root is inside tmp_path.

    The server resolves `data/<novel>` relative to the working directory,
    so the test runs from tmp_path -- nothing lands in the repo's data/.
    """
    monkeypatch.chdir(tmp_path)
    static = tmp_path / "build"
    (static / "static").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><div id=root></div>")
    (static / "static" / "app.js").write_text("console.info('app')")
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    httpd, thread = _start(tmp_path, static_dir=static, thumb_cache=tmp_path / "thumbs")
    port = httpd.server_address[1]

    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(
        "POST", "/api/projects",
        body=json.dumps({"id": "toy", "title": "Toy"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    assert conn.getresponse().status == 201
    conn.close()

    panels = tmp_path / "data" / "novels" / "toy" / "panels"
    panels.mkdir(parents=True)
    Image.new("RGB", (1200, 1600), (120, 80, 200)).save(panels / "p001.png")
    (panels / "notes.md").write_text("not an image")
    try:
        yield port, tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


class TestStaticFrontend:
    def test_client_route_falls_back_to_index(self, server) -> None:
        port, _ = server
        status, _, body = _get(port, "/p/toy/read/3")
        assert status == 200 and b"id=root" in body

    def test_real_asset_is_served(self, server) -> None:
        port, _ = server
        status, headers, body = _get(port, "/static/app.js")
        assert status == 200 and b"console.info" in body
        assert "javascript" in headers["content-type"]

    def test_null_byte_in_the_path_is_not_a_500(self, server) -> None:
        port, _ = server
        status, _, _ = _get(port, "/static/app%00.js")
        assert status in (200, 404)  # falls to the SPA index or 404; never a server error

    @pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/static/../../secret.txt"])
    def test_traversal_never_escapes_the_build_dir(self, server, path: str) -> None:
        port, _ = server
        _, _, body = _get(port, path)
        assert b"TOP SECRET" not in body

    def test_missing_asset_is_404_not_index_html(self, server) -> None:
        port, _ = server
        status, headers, _ = _get(port, "/static/js/missing.js")
        assert status == 404 and "html" not in headers["content-type"]

    def test_api_paths_are_not_swallowed_by_the_fallback(self, server) -> None:
        port, _ = server
        status, _, body = _get(port, "/api/manifest")
        assert status == 200 and body.startswith(b"[")

    def test_frontend_loads_before_login(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(webview_server._AUTH_ENV_VAR, "hunter2")
        static = tmp_path / "build"
        static.mkdir()
        (static / "index.html").write_text("<!doctype html><div id=root></div>")
        httpd, thread = _start(tmp_path, static_dir=static)
        try:
            port = httpd.server_address[1]
            assert _get(port, "/projects")[0] == 200  # the login screen is part of the app
            assert _get(port, "/api/manifest")[0] == 401  # the data is not
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


class TestThumbnails:
    def test_resizes_to_webp_and_caches(self, server) -> None:
        port, tmp = server
        status, headers, body = _get(port, "/api/novels/toy/output/file?path=panels/p001.png&w=480")
        assert status == 200 and headers["content-type"] == "image/webp"
        assert "max-age" in headers.get("cache-control", "")
        with Image.open(BytesIO(body)) as img:
            assert img.size == (480, 640)
        cached = list((tmp / "thumbs").rglob("*.webp"))
        assert len(cached) == 1
        _get(port, "/api/novels/toy/output/file?path=panels/p001.png&w=480")
        assert list((tmp / "thumbs").rglob("*.webp")) == cached  # the second hit reuses it

    def test_thumbnail_is_much_smaller_than_the_original(self, server) -> None:
        port, _ = server
        full = _get(port, "/api/novels/toy/output/file?path=panels/p001.png")[2]
        thumb = _get(port, "/api/novels/toy/output/file?path=panels/p001.png&w=320")[2]
        assert len(thumb) < len(full) / 3

    @pytest.mark.parametrize("w", ["100", "abc", "-480", "4800", "\u0664\u0668\u0660", "\u00b2"])
    def test_width_outside_the_allowed_set_is_rejected(self, server, w: str) -> None:
        port, _ = server
        from urllib.parse import quote

        assert _get(port, f"/api/novels/toy/output/file?path=panels/p001.png&w={quote(w)}")[0] == 400

    def test_thumbnails_are_not_publicly_cacheable_and_revalidate(self, server) -> None:
        """Media can be behind a password; a shared cache must not keep it."""
        port, _ = server
        url = "/api/novels/toy/output/file?path=panels/p001.png&w=480"
        _, headers, _ = _get(port, url)
        assert headers["cache-control"].startswith("private")
        assert _get_h(port, url, {"If-None-Match": headers["etag"]})[0] == 304

    def test_a_corrupt_image_is_served_unresized(self, server) -> None:
        port, tmp = server
        (tmp / "data" / "novels" / "toy" / "panels" / "bad.png").write_bytes(b"\x89PNG not really")
        status, _, body = _get(port, "/api/novels/toy/output/file?path=panels/bad.png&w=320")
        assert status == 200 and body == b"\x89PNG not really"

    def test_a_symlink_out_of_the_output_tree_is_rejected(self, server) -> None:
        port, tmp = server
        (tmp / "data" / "novels" / "toy" / "panels" / "link.png").symlink_to(tmp / "secret.txt")
        status, _, body = _get(port, "/api/novels/toy/output/file?path=panels/link.png")
        assert status == 400 and b"TOP SECRET" not in body

    def test_non_image_is_served_unchanged(self, server) -> None:
        port, _ = server
        status, _, body = _get(port, "/api/novels/toy/output/file?path=panels/notes.md&w=480")
        assert status == 200 and body == b"not an image"

    def test_path_escape_is_still_rejected_with_w(self, server) -> None:
        port, _ = server
        assert _get(port, "/api/novels/toy/output/file?path=../../secret.txt&w=480")[0] == 400

    def test_thumbnails_never_appear_in_the_output_listing(self, server) -> None:
        port, _ = server
        _get(port, "/api/novels/toy/output/file?path=panels/p001.png&w=480")
        listing = json.loads(_get(port, "/api/novels/toy/output")[2])
        paths = [i["path"] for items in listing["kinds"].values() for i in items]
        assert not any(p.endswith(".webp") for p in paths)


class TestChapterList:
    def test_unknown_novel_is_404(self, server) -> None:
        port, _ = server
        assert _get(port, "/api/novels/nope/chapters")[0] == 404

    def test_list_is_small_and_has_numbers(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Uses a registry handle with a stubbed payload: the route must return
        only number/title, never the spans that make the full payload large."""
        monkeypatch.chdir(tmp_path)
        registry = Registry([], corrections_dir=tmp_path / "corrections", projects_dir=tmp_path / "projects")

        class _Handle:
            def payload(self):
                return {"chapters": [{"number": 1.0, "spans": ["x" * 10000]}, {"number": 12.5, "title": "Half", "spans": []}]}

        registry.handles["toy"] = _Handle()  # type: ignore[assignment]
        queue = JobQueue()
        queue.start()
        httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, queue))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            status, _, body = _get(httpd.server_address[1], "/api/novels/toy/chapters")
        finally:
            httpd.shutdown()
            thread.join(timeout=5)
        assert status == 200
        assert json.loads(body) == [{"number": 1.0, "title": ""}, {"number": 12.5, "title": "Half"}]
        assert len(body) < 200


def _get_h(port: int, path: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    body = resp.read()
    out = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    return resp.status, out, body


class TestByteRanges:
    URL = "/api/novels/toy/output/file?path=panels/notes.md"  # 12 bytes: "not an image"

    def test_full_response_advertises_ranges(self, server) -> None:
        port, _ = server
        status, headers, body = _get(port, self.URL)
        assert status == 200 and body == b"not an image"
        assert headers["accept-ranges"] == "bytes"

    def test_partial_content(self, server) -> None:
        port, _ = server
        status, headers, body = _get_h(port, self.URL, {"Range": "bytes=4-5"})
        assert status == 206 and body == b"an"
        assert headers["content-range"] == "bytes 4-5/12" and headers["content-length"] == "2"

    def test_open_ended_and_suffix_ranges(self, server) -> None:
        port, _ = server
        assert _get_h(port, self.URL, {"Range": "bytes=8-"})[2] == b"mage"
        assert _get_h(port, self.URL, {"Range": "bytes=-5"})[2] == b"image"

    def test_end_past_the_file_is_clamped(self, server) -> None:
        port, _ = server
        status, headers, body = _get_h(port, self.URL, {"Range": "bytes=10-999"})
        assert status == 206 and body == b"ge" and headers["content-range"] == "bytes 10-11/12"

    @pytest.mark.parametrize("rng", ["bytes=99-", "bytes=-0"])
    def test_unsatisfiable_ranges_are_416(self, server, rng: str) -> None:
        port, _ = server
        status, headers, _ = _get_h(port, self.URL, {"Range": rng})
        assert status == 416 and headers["content-range"] == "bytes */12"

    @pytest.mark.parametrize("rng", ["bytes=0-1,4-5", "bytes=abc-", "bytes=5-2", "bytes=-", "items=0-1"])
    def test_malformed_or_multi_ranges_are_ignored(self, server, rng: str) -> None:
        """RFC 9110: an unsupported Range is ignored -- the full body, not a 416."""
        port, _ = server
        status, _, body = _get_h(port, self.URL, {"Range": rng})
        assert status == 200 and body == b"not an image"

    def test_head_has_headers_and_no_body(self, server) -> None:
        port, _ = server
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("HEAD", self.URL)
        resp = conn.getresponse()
        assert resp.status == 200 and resp.read() == b""
        assert resp.getheader("Content-Length") == "12"
        conn.close()

    def test_head_on_a_json_route_has_no_body(self, server) -> None:
        port, _ = server
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("HEAD", "/api/novels/toy/chapters")
        resp = conn.getresponse()
        assert resp.read() == b""
        conn.close()

    def test_conditional_get_is_304(self, server) -> None:
        port, _ = server
        etag = _get(port, self.URL)[1]["etag"]
        status, _, body = _get_h(port, self.URL, {"If-None-Match": etag})
        assert status == 304 and body == b""

    def test_empty_file_with_a_range_is_an_empty_200(self, server) -> None:
        port, tmp = server
        (tmp / "data" / "novels" / "toy" / "panels" / "empty.md").write_bytes(b"")
        status, _, body = _get_h(
            port, "/api/novels/toy/output/file?path=panels/empty.md", {"Range": "bytes=0-"}
        )
        assert status == 200 and body == b""

    def test_a_large_file_is_streamed_in_chunks(self, server) -> None:
        port, tmp = server
        big = tmp / "data" / "novels" / "toy" / "video"
        big.mkdir(parents=True)
        payload = bytes(range(256)) * 2048  # 512 KiB, several 64 KiB chunks
        (big / "v.mp4").write_bytes(payload)
        status, _, body = _get(port, "/api/novels/toy/output/file?path=video/v.mp4")
        assert status == 200 and body == payload
        status, _, body = _get_h(
            port, "/api/novels/toy/output/file?path=video/v.mp4", {"Range": "bytes=100000-200000"}
        )
        assert status == 206 and body == payload[100000:200001]


class TestSlowClient:
    def test_a_stalled_download_does_not_block_other_requests(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The server is single-threaded. A client that reads 1 KB of a big
        file and then stops used to hold every other request until the OS
        gave up (Python review, 2026-09-26). The handler's socket timeout
        releases it; the test shortens it to 1 s."""
        import socket
        import time

        monkeypatch.chdir(tmp_path)
        registry = Registry([], corrections_dir=tmp_path / "corrections", projects_dir=tmp_path / "projects")
        queue = JobQueue()
        queue.start()
        handler = make_handler(registry, queue)
        handler.timeout = 1
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_address[1]
        stalled = None
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("POST", "/api/projects", body=json.dumps({"id": "toy", "title": "T"}).encode(),
                         headers={"Content-Type": "application/json"})
            assert conn.getresponse().status == 201
            conn.close()
            big = tmp_path / "data" / "novels" / "toy" / "video"
            big.mkdir(parents=True)
            (big / "big.mp4").write_bytes(b"\0" * (64 << 20))  # far beyond the socket buffers

            stalled = socket.create_connection(("127.0.0.1", port), timeout=10)
            stalled.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            stalled.sendall(b"GET /api/novels/toy/output/file?path=video/big.mp4 HTTP/1.1\r\nHost: x\r\n\r\n")
            stalled.recv(1024)  # then stop reading

            t0 = time.monotonic()
            assert _get(port, "/api/manifest")[0] == 200
            assert time.monotonic() - t0 < 8
        finally:
            if stalled is not None:
                stalled.close()
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


class TestMediaAuth:
    def test_media_route_accepts_a_session_token_in_the_query_and_nothing_else_does(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(webview_server._AUTH_ENV_VAR, "hunter2")
        monkeypatch.chdir(tmp_path)
        httpd, thread = _start(tmp_path)
        port = httpd.server_address[1]
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("POST", "/api/auth/login", body=json.dumps({"password": "hunter2"}).encode(),
                         headers={"Content-Type": "application/json"})
            token = json.loads(conn.getresponse().read())["token"]
            conn.close()
            hdr = {"Authorization": f"Bearer {token}"}
            conn = HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("POST", "/api/projects", body=json.dumps({"id": "toy", "title": "T"}).encode(),
                         headers={"Content-Type": "application/json", **hdr})
            assert conn.getresponse().status == 201
            conn.close()
            out = tmp_path / "data" / "novels" / "toy" / "panels"
            out.mkdir(parents=True)
            (out / "a.md").write_text("hello")
            media = "/api/novels/toy/output/file?path=panels/a.md"
            assert _get(port, media)[0] == 401
            assert _get(port, media + "&access_token=wrong")[0] == 401
            assert _get(port, media + f"&access_token={token}")[2] == b"hello"
            assert _get(port, f"/api/manifest?access_token={token}")[0] == 401  # JSON API: header only
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
