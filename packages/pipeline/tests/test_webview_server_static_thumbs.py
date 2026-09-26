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

    panels = tmp_path / "data" / "toy" / "panels"
    panels.mkdir(parents=True)
    Image.new("RGB", (1200, 1600), (120, 80, 200)).save(panels / "p001.png")
    (panels / "notes.md").write_text("not an image")
    try:
        yield port, tmp_path
    finally:
        httpd.shutdown()
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

    @pytest.mark.parametrize("w", ["100", "abc", "-480", "4800"])
    def test_width_outside_the_allowed_set_is_rejected(self, server, w: str) -> None:
        port, _ = server
        assert _get(port, f"/api/novels/toy/output/file?path=panels/p001.png&w={w}")[0] == 400

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
