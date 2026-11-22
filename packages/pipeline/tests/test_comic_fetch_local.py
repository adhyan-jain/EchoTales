"""`comic/fetch.py` local mode: a browser-saved page ("Webpage, Complete") or a folder of images, no network at all.

Every test makes `httpx.Client` and DNS lookups fail, so a stray request would break the test rather than pass quietly."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import httpx
import pytest
from echotales.pipeline.comic import fetch
from echotales.pipeline.comic.fetch import FetchError, fetch_local
from PIL import Image


def _img(w: int, h: int, shade: int, fmt: str = "JPEG") -> bytes:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            px[x, y] = ((x * 7 + shade) % 256, (y * 5 + shade * 3) % 256, shade)
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def no_network(monkeypatch) -> None:
    def boom(*a, **k):
        raise AssertionError("local mode must not touch the network")

    monkeypatch.setattr(httpx.Client, "__init__", boom)
    monkeypatch.setattr(fetch.socket, "getaddrinfo", boom)


def _saved_page(root: Path, body: str, head: str = "", stamp: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    comment = "<!-- saved from url=(0040)https://reader.example/series/ch-1 -->\n" if stamp else ""
    (root / "ch.html").write_text(
        f"{comment}<html><head>{head}</head><body>{body}</body></html>", encoding="utf-8"
    )
    (root / "ch_files").mkdir(exist_ok=True)
    return root / "ch.html"


def _put(path: Path, w: int, h: int, shade: int, fmt: str = "JPEG") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_img(w, h, shade, fmt))


def _source(out: Path) -> dict:
    return json.loads((out / "source.json").read_text())


def test_saved_page_gives_pages_in_reading_order_without_noise(tmp_path) -> None:
    root = tmp_path / "saved"
    files = root / "ch_files"
    html = _saved_page(
        root,
        '<img src="ch_files/logo.png"><img src="ch_files/p%201.jpg">'
        '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" data-src="ch_files/p2.png">'
        '<img src="ch_files/p3.jpg" srcset="ch_files/p3.jpg 600w"><img src="ch_files/thumb.jpg">',
    )
    _put(files / "logo.png", 120, 40, 5, "PNG")
    _put(files / "p 1.jpg", 600, 900, 30)
    _put(files / "p2.png", 600, 900, 60, "PNG")
    _put(files / "p3.jpg", 600, 900, 90)
    _put(files / "thumb.jpg", 200, 300, 120)
    res = fetch_local(html, tmp_path / "out", rights_confirmed=True)
    assert [p.name for p in res.images] == ["0001.jpg", "0002.png", "0003.jpg"]
    assert (tmp_path / "out" / "0001.jpg").read_bytes() == (files / "p 1.jpg").read_bytes()
    info = _source(tmp_path / "out")
    assert info["source"] == "saved_page"
    assert info["url"] == "https://reader.example/series/ch-1"
    assert info["rights_confirmed"] is True
    assert info["image_count"] == 3


def test_page_url_falls_back_to_og_url_then_canonical_then_none(tmp_path) -> None:
    body = '<img src="ch_files/p1.jpg"><img src="ch_files/p2.jpg">'
    root = tmp_path / "a"
    html = _saved_page(root, body, head='<meta property="og:url" content="https://reader.example/og">', stamp=False)
    for n in (1, 2):
        _put(root / "ch_files" / f"p{n}.jpg", 600, 900, n * 40)
    fetch_local(html, tmp_path / "o1")
    assert _source(tmp_path / "o1")["url"] == "https://reader.example/og"
    html = _saved_page(root, body, head='<link rel="canonical" href="https://reader.example/canon">', stamp=False)
    fetch_local(html, tmp_path / "o2")
    assert _source(tmp_path / "o2")["url"] == "https://reader.example/canon"
    html = _saved_page(root, body, stamp=False)
    fetch_local(html, tmp_path / "o3")
    assert _source(tmp_path / "o3")["url"] is None


def test_escape_through_dotdot_absolute_path_or_symlink_is_refused(tmp_path) -> None:
    root = tmp_path / "saved"
    secret = tmp_path / "secret.jpg"
    _put(secret, 600, 900, 200)
    html = _saved_page(
        root,
        '<img src="ch_files/p1.jpg"><img src="ch_files/p2.jpg">'
        '<img src="../secret.jpg"><img src="ch_files/../../secret.jpg"><img src="ch_files/%2e%2e/%2e%2e/secret.jpg">'
        f'<img src="{secret}"><img src="ch_files/link.jpg">',
    )
    _put(root / "ch_files" / "p1.jpg", 600, 900, 30)
    _put(root / "ch_files" / "p2.jpg", 600, 900, 60)
    os.symlink(secret, root / "ch_files" / "link.jpg")
    res = fetch_local(html, tmp_path / "out")
    assert len(res.images) == 2
    for p in res.images:
        assert p.read_bytes() != secret.read_bytes()
    assert len(res.skipped) == 4  # the two plain `..` spellings join to the same path
    assert all("outside" in s["reason"] for s in res.skipped)


def test_a_remote_only_reference_is_reported_missing_and_not_fetched(tmp_path) -> None:
    root = tmp_path / "saved"
    html = _saved_page(
        root,
        '<img src="ch_files/p1.jpg"><img src="ch_files/p2.jpg">'
        '<img src="https://cdn.example/remote/p3.jpg"><img src="//cdn.example/remote/p4.jpg"><img src="ch_files/gone.jpg">',
    )
    _put(root / "ch_files" / "p1.jpg", 600, 900, 30)
    _put(root / "ch_files" / "p2.jpg", 600, 900, 60)
    res = fetch_local(html, tmp_path / "out")
    assert len(res.images) == 2
    reasons = {s["url"]: s["reason"] for s in res.skipped}
    assert len(reasons) == 3
    assert "not saved" in reasons["https://cdn.example/remote/p3.jpg"]
    assert any("not saved" in r for u, r in reasons.items() if "p4" in u)
    assert "not found" in reasons["ch_files/gone.jpg"]


def test_only_remote_references_is_an_error_and_writes_nothing(tmp_path) -> None:
    html = _saved_page(tmp_path / "saved", '<img src="https://cdn.example/a.jpg"><img src="https://cdn.example/b.jpg">')
    with pytest.raises(FetchError, match="none of the 2 images"):
        fetch_local(html, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_page_with_no_images_is_an_error(tmp_path) -> None:
    html = _saved_page(tmp_path / "saved", "<p>locked</p>")
    with pytest.raises(FetchError, match="no page images"):
        fetch_local(html, tmp_path / "out")


def test_a_non_image_file_is_skipped(tmp_path) -> None:
    root = tmp_path / "saved"
    html = _saved_page(root, '<img src="ch_files/p1.jpg"><img src="ch_files/p2.jpg"><img src="ch_files/fake.jpg">')
    _put(root / "ch_files" / "p1.jpg", 600, 900, 30)
    _put(root / "ch_files" / "p2.jpg", 600, 900, 60)
    (root / "ch_files" / "fake.jpg").write_text("<html>not an image</html>" * 50)
    res = fetch_local(html, tmp_path / "out")
    assert len(res.images) == 2
    assert res.skipped[0]["reason"] == "not a readable image"


def test_folder_takes_images_in_natural_order_and_ignores_other_files(tmp_path) -> None:
    src = tmp_path / "pages"
    for name, shade in [("p10.jpg", 10), ("p2.jpg", 20), ("p1.png", 30)]:
        _put(src / name, 600, 900, shade, "PNG" if name.endswith("png") else "JPEG")
    (src / "notes.txt").write_text("hello")
    res = fetch_local(src, tmp_path / "out")
    assert [p.name for p in res.images] == ["0001.png", "0002.jpg", "0003.jpg"]
    assert (tmp_path / "out" / "0002.jpg").read_bytes() == (src / "p2.jpg").read_bytes()
    info = _source(tmp_path / "out")
    assert info["source"] == "folder"
    assert info["url"] is None


def test_folder_symlink_pointing_outside_is_refused(tmp_path) -> None:
    src = tmp_path / "pages"
    outside = tmp_path / "elsewhere.jpg"
    _put(outside, 600, 900, 99)
    _put(src / "a.jpg", 600, 900, 10)
    _put(src / "b.jpg", 600, 900, 20)
    os.symlink(outside, src / "c.jpg")
    res = fetch_local(src, tmp_path / "out")
    assert len(res.images) == 2
    assert "outside" in res.skipped[0]["reason"]


def test_caps_are_the_same_as_the_network_mode(tmp_path) -> None:
    src = tmp_path / "pages"
    for n in range(3):
        _put(src / f"p{n}.jpg", 600, 900, n * 30)
    with pytest.raises(FetchError, match="limit is 2"):
        fetch_local(src, tmp_path / "out", max_images=2)
    with pytest.raises(FetchError, match="total limit"):
        fetch_local(src, tmp_path / "out", max_total_bytes=1000)
    with pytest.raises(FetchError, match="none of the 3 images"):
        fetch_local(src, tmp_path / "out", max_image_bytes=1000)


def test_a_missing_path_or_a_plain_file_is_refused(tmp_path) -> None:
    with pytest.raises(FetchError, match="no such"):
        fetch_local(tmp_path / "nope", tmp_path / "out")
    (tmp_path / "x.txt").write_text("hi")
    with pytest.raises(FetchError, match="saved page"):
        fetch_local(tmp_path / "x.txt", tmp_path / "out")


def test_cli_accepts_a_saved_page_and_help_says_so(tmp_path, monkeypatch, capsys) -> None:
    from echotales.pipeline.cli import build_parser, main

    root = tmp_path / "saved"
    html = _saved_page(root, '<img src="ch_files/p1.jpg"><img src="ch_files/p2.jpg">')
    for n in (1, 2):
        _put(root / "ch_files" / f"p{n}.jpg", 600, 900, n * 40)
    out = tmp_path / "cli_out"
    assert main(["comic", "fetch", str(html), "--id", "t1", "--out", str(out), "--i-own-rights"]) == 0
    assert (out / "0002.jpg").exists()
    assert "2 images" in capsys.readouterr().out
    assert main(["comic", "fetch", str(tmp_path / "missing"), "--out", str(out)]) == 2
    with pytest.raises(SystemExit):
        build_parser().parse_args(["comic", "fetch", "--help"])
    assert "saved page" in capsys.readouterr().out
