"""`POST /api/projects/<id>/comic` (multipart) stores an uploaded comic safely; `GET` lists sources and built videos.
Each refusal is a 400 that leaves no file behind. Runs against a real server on an ephemeral port, from a temporary
working directory because `paths.DATA_ROOT` is relative."""

from __future__ import annotations

import io
import json
import zipfile
from http.client import HTTPConnection
from pathlib import Path

import pytest
from PIL import Image
from test_webview_server_jobs import _request, live_server  # noqa: F401  (fixture)

BOUNDARY = "COMICBOUNDARY"


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 14), (10, 200, 10)).save(buf, "PNG")
    return buf.getvalue()


def _cbz(members: dict[str, bytes], symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = 0o120777 << 16
            z.writestr(info, "/etc/passwd")
    return buf.getvalue()


def _multipart(filename: str, data: bytes) -> tuple[bytes, dict]:
    body = (
        f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + f"\r\n--{BOUNDARY}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}


@pytest.fixture
def project(live_server, tmp_path: Path, monkeypatch):  # noqa: F811
    monkeypatch.chdir(tmp_path)
    status, body = _request(live_server, "POST", "/api/projects",
                            body=json.dumps({"id": "pc", "title": "Pepper"}).encode(),
                            headers={"Content-Type": "application/json"})
    assert status == 201, body
    return live_server, tmp_path / "data" / "novels" / "pc" / "comic" / "source"


def _post(port, filename: str, data: bytes, pid: str = "pc"):
    body, headers = _multipart(filename, data)
    return _request(port, "POST", f"/api/projects/{pid}/comic", body=body, headers=headers)


def test_a_cbz_is_extracted_into_the_project_and_listed(project) -> None:
    port, src = project
    status, out = _post(port, "ep1.cbz", _cbz({"2.png": _png(), "1.png": _png(), "ComicInfo.xml": b"<x/>"}))
    assert status == 201 and out == {"name": "ep1", "pages": 2, "bytes": out["bytes"], "kind": "images"}
    assert sorted(p.name for p in (src / "ep1").iterdir()) == ["0001_1.png", "0002_2.png"]
    status, listing = _request(port, "GET", "/api/projects/pc/comic")
    assert status == 200 and listing["sources"] == [{"name": "ep1", "pages": 2, "kind": "images"}]
    assert listing["videos"] == []


def test_a_built_motion_comic_is_listed_with_a_path_the_output_route_serves(project) -> None:
    port, _ = project
    vdir = project[1].parent.parent / "video" / "ch1" / "v1_motion-comic"
    vdir.mkdir(parents=True)
    (vdir / "episode.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (vdir / "comic.json").write_text("{}")
    other = vdir.parent / "v2_episode-voice-stills"  # an episode-composer folder has no comic.json
    other.mkdir()
    (other / "episode.mp4").write_bytes(b"x")
    status, listing = _request(port, "GET", "/api/projects/pc/comic")
    assert [v["path"] for v in listing["videos"]] == ["video/ch1/v1_motion-comic/episode.mp4"]
    conn = HTTPConnection("127.0.0.1", int(port), timeout=10)
    conn.request("GET", "/api/novels/pc/output/file?path=video/ch1/v1_motion-comic/episode.mp4")
    resp = conn.getresponse()
    assert resp.status == 200 and resp.read().endswith(b"mp42")
    conn.close()


@pytest.mark.parametrize("name,data,fragment", [
    ("evil.cbz", _cbz({"../../escape.png": _png()}), "unsafe path"),
    ("abs.cbz", _cbz({"/tmp/escape.png": _png()}), "unsafe path"),
    ("link.cbz", _cbz({"1.png": _png()}, symlink="2.png"), "symlink"),
    ("text.cbz", _cbz({"readme.txt": b"hello"}), "no page images"),
    ("fake.cbz", _cbz({"1.png": b"not an image"}), "not a readable image"),
    ("bad.cbz", b"not a zip at all", "valid .cbz"),
    ("run.exe", b"MZ", "only .cbz"),
    ("fake.pdf", b"<html>", "not a PDF"),
])
def test_each_refusal_is_a_400_and_writes_nothing(project, name: str, data: bytes, fragment: str) -> None:
    port, src = project
    status, out = _post(port, name, data)
    assert status == 400 and fragment in out["error"]
    assert not src.exists() or not list(src.iterdir())
    assert not (src.parent.parent.parent.parent / "escape.png").exists()


def test_too_many_files_and_too_large_unpacked_size_are_400(project, monkeypatch) -> None:
    from echotales.pipeline.comic import upload

    port, src = project
    monkeypatch.setattr(upload, "MAX_FILES", 2)
    status, out = _post(port, "many.cbz", _cbz({f"{i}.png": _png() for i in range(3)}))
    assert status == 400 and "limit is 2" in out["error"]
    monkeypatch.setattr(upload, "MAX_FILES", 500)
    monkeypatch.setattr(upload, "MAX_UNPACKED_BYTES", 10)
    status, out = _post(port, "big.cbz", _cbz({"1.png": _png()}))
    assert status == 400 and "unpacks to more" in out["error"]
    assert not src.exists() or not list(src.iterdir())


def test_the_upload_name_is_a_basename_only(project) -> None:
    port, src = project
    status, out = _post(port, "../../../outside.cbz", _cbz({"1.png": _png()}))
    assert status == 201 and out["name"] == "outside" and (src / "outside").is_dir()


def test_a_pdf_is_stored_and_unknown_project_and_non_multipart_are_refused(project) -> None:
    port, src = project
    status, out = _post(port, "book.pdf", b"%PDF-1.4\n%%EOF")
    assert status == 201 and out["kind"] == "pdf" and (src / "book" / "source.pdf").is_file()
    status, out = _post(port, "x.cbz", _cbz({"1.png": _png()}), pid="nope")
    assert status == 404
    # JSON on the same path is still the job trigger, not an upload
    status, out = _request(port, "POST", "/api/projects/pc/comic", body=b"{}", headers={"Content-Type": "application/json"})
    assert status in (202, 400, 409) and status != 201
