"""`comic/fetch.py`: a chapter URL to a folder of page images, against a local http.server (no network).

The SSRF guard blocks loopback, so the fixture server is reached through `AllowLoopback`, a test-only guard passed as
an argument; the module has no environment switch that could turn the guard off by accident."""

from __future__ import annotations

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from echotales.pipeline.comic import fetch
from echotales.pipeline.comic.fetch import FetchError, PublicOnlyGuard, fetch_chapter
from PIL import Image


class AllowLoopback(PublicOnlyGuard):
    """Everything the real guard enforces except that 127.0.0.1 is reachable, so redirects to other private
    addresses are still refused."""

    def ip_allowed(self, ip) -> bool:  # type: ignore[no-untyped-def]
        return str(ip) == "127.0.0.1" or super().ip_allowed(ip)


def _img(w: int, h: int, shade: int, fmt: str = "JPEG") -> bytes:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            px[x, y] = ((x * 7 + shade) % 256, (y * 5 + shade * 3) % 256, shade)
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


class Site:
    """Routes: path -> (status, headers, body). Records the headers of every request."""

    def __init__(self) -> None:
        self.routes: dict[str, tuple[int, dict, bytes]] = {}
        self.seen: list[tuple[str, dict]] = []
        self.flaky: dict[str, int] = {}
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                outer.seen.append((self.path, dict(self.headers)))
                if outer.flaky.get(self.path, 0) > 0:
                    outer.flaky[self.path] -= 1
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status, headers, body = outer.routes.get(self.path, (404, {}, b"nope"))
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:  # noqa: ANN002
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def page(self, path: str, html: str) -> None:
        self.routes[path] = (200, {"Content-Type": "text/html"}, html.encode())

    def image(self, path: str, w: int, h: int, shade: int, fmt: str = "JPEG") -> None:
        ctype = "image/png" if fmt == "PNG" else "image/jpeg"
        self.routes[path] = (200, {"Content-Type": ctype}, _img(w, h, shade, fmt))


@pytest.fixture
def site():
    s = Site()
    yield s
    s.httpd.shutdown()


def _fetch(url: str, out: Path, **kw):
    kw.setdefault("guard", AllowLoopback())
    kw.setdefault("delay", 0)
    kw.setdefault("backoff", 0)
    kw.setdefault("sleep", lambda s: None)
    return fetch_chapter(url, out, **kw)


def _chapter(site: Site) -> str:
    """A chapter page using every extraction route, with noise images between the real pages."""
    for n, (w, fmt, ext) in enumerate([(600, "JPEG", "jpg"), (600, "PNG", "png"), (600, "JPEG", "jpg"),
                                       (600, "JPEG", "jpg"), (600, "JPEG", "jpg")], 1):
        site.image(f"/series/img/p{n}.{ext}", w, 900, n * 30, fmt)
    site.image("/series/img/p3_small.jpg", 300, 450, 90)
    site.image("/assets/logo.png", 120, 40, 5, "PNG")
    site.image("/assets/icon.png", 64, 64, 6, "PNG")
    site.image("/avatars/u1.jpg", 100, 100, 7)
    site.image("/ads/banner.jpg", 728, 90, 8)
    site.routes["/pixel.gif"] = (200, {"Content-Type": "image/gif"}, b"GIF89a\x01\x00\x01\x00\x00\x00\x00;")
    html = """<html><head><title>Chapter 1</title></head><body>
    <img src="/assets/logo.png"><img src="/pixel.gif" width="1" height="1">
    <div class="reader">
      <img src="/series/img/p1.jpg">
      <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" data-src="/series/img/p2.png" class="lazy">
      <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw="
           srcset="/series/img/p3_small.jpg 300w, /series/img/p3.jpg 600w">
      <img class="lazy" data-original="/series/img/p4.jpg"><noscript><img src="/series/img/p4.jpg"></noscript>
      <img src="../img/p5.jpg">
    </div>
    <img src="/avatars/u1.jpg"><img src="/assets/icon.png"><img src="/ads/banner.jpg">
    </body></html>"""
    site.page("/series/ch1/", html)
    return site.base + "/series/ch1/"


def test_pages_come_out_in_reading_order_and_noise_is_dropped(site, tmp_path) -> None:
    res = _fetch(_chapter(site), tmp_path / "out", rights_confirmed=True)
    out = tmp_path / "out"
    assert [p.name for p in res.images] == ["0001.jpg", "0002.png", "0003.jpg", "0004.jpg", "0005.jpg"]
    assert sorted(p.name for p in out.iterdir()) == ["0001.jpg", "0002.png", "0003.jpg", "0004.jpg", "0005.jpg",
                                                     "source.json"]
    assert all(d == (600, 900) for d in res.dims)
    # the srcset picked the larger candidate, not p3_small (300 wide would also have been filtered, so check bytes)
    assert Image.open(out / "0003.jpg").size == (600, 900)
    info = json.loads((out / "source.json").read_text())
    assert info["url"].endswith("/series/ch1/") and info["image_count"] == 5 and info["rights_confirmed"] is True
    assert info["fetched_at"].endswith("Z") and len(info["images"]) == 5


def test_rights_flag_defaults_to_false_and_is_only_a_stamp(site, tmp_path) -> None:
    _fetch(_chapter(site), tmp_path / "out")
    assert json.loads((tmp_path / "out" / "source.json").read_text())["rights_confirmed"] is False


def test_a_redirect_is_followed_and_images_carry_the_page_as_referer(site, tmp_path) -> None:
    chapter = _chapter(site)
    site.routes["/go"] = (302, {"Location": "/series/ch1/"}, b"")
    _fetch(site.base + "/go", tmp_path / "out")
    img_requests = [h for p, h in site.seen if p.startswith("/series/img/p1")]
    assert img_requests and img_requests[0]["Referer"] == chapter
    assert "Mozilla" in img_requests[0]["User-Agent"]


def test_image_urls_in_a_script_blob_are_found_when_the_markup_has_none(site, tmp_path) -> None:
    for n in range(1, 4):
        site.image(f"/blob/{n}.jpg", 600, 900, n * 40)
    escaped = json.dumps([f"{site.base}/blob/{n}.jpg" for n in range(1, 4)]).replace("/", "\\/")
    site.page("/c", f"<html><body><div id='app'></div><script>window.__DATA__ = {{\"pages\": {escaped}}};</script></body></html>")
    res = _fetch(site.base + "/c", tmp_path / "out")
    assert len(res.images) == 3


def test_same_url_twice_is_downloaded_once(site, tmp_path) -> None:
    site.image("/a.jpg", 600, 900, 1)
    site.image("/b.jpg", 600, 900, 2)
    site.page("/d", '<img src="/a.jpg"><img src="/a.jpg"><img src="/b.jpg">')
    res = _fetch(site.base + "/d", tmp_path / "out")
    assert len(res.images) == 2
    assert sum(1 for p, _ in site.seen if p == "/a.jpg") == 1


def test_a_page_of_a_different_width_than_the_strip_is_dropped(site, tmp_path) -> None:
    for n in range(1, 5):
        site.image(f"/s{n}.jpg", 800, 1400, n * 20)
    site.image("/other.jpg", 500, 700, 99)
    site.page("/w", "".join(f'<img src="/s{n}.jpg">' for n in range(1, 3)) + '<img src="/other.jpg">'
              + "".join(f'<img src="/s{n}.jpg">' for n in range(3, 5)))
    res = _fetch(site.base + "/w", tmp_path / "out")
    assert [d[0] for d in res.dims] == [800] * 4


# --- SSRF -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:9/", "http://10.1.2.3/x", "http://192.168.1.10/", "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/", "http://localhost:9/", "http://0.0.0.0/", "http://172.16.0.1/", "http://[::ffff:127.0.0.1]/",
    "file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)", "http:///nohost",
])
def test_the_default_guard_refuses_local_and_non_http_urls(url, tmp_path) -> None:
    with pytest.raises(FetchError):
        fetch_chapter(url, tmp_path / "out", delay=0, sleep=lambda s: None)
    assert not (tmp_path / "out").exists()


def test_a_redirect_to_a_private_address_is_refused(site, tmp_path) -> None:
    site.routes["/r"] = (302, {"Location": "http://169.254.169.254/latest/"}, b"")
    with pytest.raises(FetchError, match="not allowed|private|refus"):
        _fetch(site.base + "/r", tmp_path / "out")


def test_an_image_on_a_private_address_is_never_requested(site, tmp_path) -> None:
    for n in (1, 2):
        site.image(f"/g{n}.jpg", 600, 900, n * 50)
    site.page("/p", '<img src="/g1.jpg"><img src="http://10.9.9.9/secret.jpg"><img src="/g2.jpg">')
    res = _fetch(site.base + "/p", tmp_path / "out")
    assert len(res.images) == 2
    assert any("10.9.9.9" in s["url"] and "not allowed" in s["reason"] for s in res.skipped)


def test_an_image_that_redirects_to_a_private_address_is_skipped(site, tmp_path) -> None:
    for n in (1, 2):
        site.image(f"/g{n}.jpg", 600, 900, n * 50)
    site.routes["/hop.jpg"] = (302, {"Location": "http://192.168.0.1/x.jpg"}, b"")
    site.page("/p", '<img src="/g1.jpg"><img src="/hop.jpg"><img src="/g2.jpg">')
    res = _fetch(site.base + "/p", tmp_path / "out")
    assert len(res.images) == 2 and any("hop.jpg" in s["url"] for s in res.skipped)


# --- caps and verification ----------------------------------------------------------------------------------------

def test_an_oversize_image_is_skipped_not_saved(site, tmp_path) -> None:
    site.image("/ok1.jpg", 600, 900, 1)
    site.image("/ok2.jpg", 600, 900, 2)
    site.routes["/big.jpg"] = (200, {"Content-Type": "image/jpeg"}, _img(600, 900, 3) + b"\0" * 400_000)
    site.page("/p", '<img src="/ok1.jpg"><img src="/big.jpg"><img src="/ok2.jpg">')
    res = _fetch(site.base + "/p", tmp_path / "out", max_image_bytes=300_000)
    assert len(res.images) == 2
    assert any("big.jpg" in s["url"] and "larger than" in s["reason"] for s in res.skipped)
    assert len(list((tmp_path / "out").glob("0*"))) == 2


def test_too_many_images_on_a_page_is_refused(site, tmp_path) -> None:
    site.page("/many", "".join(f'<img src="/m{n}.jpg">' for n in range(12)))
    with pytest.raises(FetchError, match="12 images"):
        _fetch(site.base + "/many", tmp_path / "out", max_images=10)
    assert not (tmp_path / "out").exists()


def test_the_total_download_cap_stops_the_fetch(site, tmp_path) -> None:
    for n in range(1, 6):
        site.image(f"/t{n}.jpg", 600, 900, n * 10)
    site.page("/t", "".join(f'<img src="/t{n}.jpg">' for n in range(1, 6)))
    with pytest.raises(FetchError, match="total"):
        _fetch(site.base + "/t", tmp_path / "out", max_total_bytes=len(_img(600, 900, 10)) * 2)
    assert not (tmp_path / "out").exists()


def test_bytes_that_are_not_an_image_are_not_saved(site, tmp_path) -> None:
    site.image("/ok1.jpg", 600, 900, 1)
    site.image("/ok2.jpg", 600, 900, 2)
    site.routes["/fake.jpg"] = (200, {"Content-Type": "image/jpeg"}, b"<html>" + b"x" * 5000)
    site.page("/p", '<img src="/ok1.jpg"><img src="/fake.jpg"><img src="/ok2.jpg">')
    res = _fetch(site.base + "/p", tmp_path / "out")
    assert len(res.images) == 2
    assert any("fake.jpg" in s["url"] and "not a readable image" in s["reason"] for s in res.skipped)


def test_saved_names_never_come_from_the_remote(site, tmp_path) -> None:
    site.image("/..%2f..%2fevil.jpg", 600, 900, 1)
    site.image("/x/ok.jpg", 600, 900, 2)
    site.page("/p", '<img src="/..%2f..%2fevil.jpg"><img src="/x/ok.jpg">')
    res = _fetch(site.base + "/p", tmp_path / "out")
    assert [p.name for p in res.images] == ["0001.jpg", "0002.jpg"]
    assert not (tmp_path / "evil.jpg").exists()


# --- blocked pages, retries, rendering ----------------------------------------------------------------------------

def test_a_blocked_page_is_reported_plainly_and_not_worked_around(site, tmp_path) -> None:
    site.routes["/locked"] = (403, {}, b"forbidden")
    with pytest.raises(FetchError, match=r"HTTP 403.*(login|refus|block)"):
        _fetch(site.base + "/locked", tmp_path / "out")


def test_a_page_with_no_images_says_so(site, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fetch, "playwright_available", lambda: False)
    site.page("/empty", "<html><body><p>Chapter locked</p></body></html>")
    with pytest.raises(FetchError, match=r"no page images.*--render"):
        _fetch(site.base + "/empty", tmp_path / "out")


def test_a_temporary_503_is_retried(site, tmp_path) -> None:
    chapter = _chapter(site)
    site.flaky["/series/img/p2.png"] = 2
    res = _fetch(chapter, tmp_path / "out")
    assert len(res.images) == 5


def test_render_without_playwright_says_how_to_enable_it(site, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fetch, "playwright_available", lambda: False)
    with pytest.raises(FetchError, match=r"pip install .*playwright"):
        _fetch(_chapter(site), tmp_path / "out", render=True)


def test_too_few_static_images_keeps_them_and_points_at_render(site, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fetch, "playwright_available", lambda: False)
    site.image("/only.jpg", 600, 900, 1)
    site.page("/one", '<img src="/only.jpg">')
    res = _fetch(site.base + "/one", tmp_path / "out")
    assert len(res.images) == 1 and any("--render" in n for n in res.notes)


def test_a_failed_fetch_keeps_an_earlier_result(site, tmp_path) -> None:
    out = tmp_path / "out"
    _fetch(_chapter(site), out)
    site.routes["/series/ch1/"] = (403, {}, b"")
    with pytest.raises(FetchError):
        _fetch(site.base + "/series/ch1/", out)
    assert (out / "0001.jpg").is_file()


def test_comic_id_is_derived_from_the_url() -> None:
    assert fetch.default_comic_id("https://www.example.com/en/webcomic/ep-12_the.start/?x=1") == "example.com-ep-12_the.start"
    assert fetch.default_comic_id("https://example.com/") == "example.com"
