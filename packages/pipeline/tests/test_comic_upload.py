"""The comic upload is untrusted input: every way an archive can write outside its folder or exhaust the disk is refused,
and a refused upload leaves nothing behind."""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest
from echotales.pipeline.comic import upload
from echotales.pipeline.comic.ingest import load_pages
from PIL import Image


def _png(color=(200, 30, 30), size=(12, 16), noise: bool = False) -> bytes:
    buf = io.BytesIO()
    img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)) if noise else Image.new("RGB", size, color)
    img.save(buf, "PNG")
    return buf.getvalue()


def _zip(members: dict[str, bytes], *, symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "/etc/passwd")
    return buf.getvalue()


def test_cbz_pages_land_in_natural_order_and_load(tmp_path: Path) -> None:
    data = _zip({"p10.png": _png(), "p2.png": _png((1, 2, 3)), "ComicInfo.xml": b"<x/>", "p1.png": _png()})
    out = upload.store_comic_upload("My Comic!.cbz", data, tmp_path)
    assert out["name"] == "My_Comic_" and out["pages"] == 3
    names = sorted(p.name for p in (tmp_path / "My_Comic_").iterdir())
    assert names == ["0001_p1.png", "0002_p2.png", "0003_p10.png"]  # ComicInfo.xml is not a page
    assert len(load_pages(upload.source_input(tmp_path / "My_Comic_"))) == 3


def test_same_basename_in_two_folders_does_not_overwrite(tmp_path: Path) -> None:
    out = upload.store_comic_upload("c.zip", _zip({"a/1.png": _png(), "b/1.png": _png()}), tmp_path)
    assert out["pages"] == 2 and len(list((tmp_path / "c").iterdir())) == 2


def test_the_client_file_name_is_reduced_to_a_basename(tmp_path: Path) -> None:
    out = upload.store_comic_upload("../../etc/evil.cbz", _zip({"1.png": _png()}), tmp_path / "src")
    assert out["name"] == "evil" and (tmp_path / "src" / "evil").is_dir() and not (tmp_path / "etc").exists()
    out = upload.store_comic_upload("C:\\x\\y\\win.cbz", _zip({"1.png": _png()}), tmp_path / "src")
    assert out["name"] == "win"


@pytest.mark.parametrize("member", ["/abs/1.png", "../up/1.png", "a/../../1.png", "C:/x/1.png", "\\evil\\1.png"])
def test_unsafe_member_paths_are_refused_and_nothing_is_written(tmp_path: Path, member: str) -> None:
    with pytest.raises(upload.ComicUploadError, match="unsafe path"):
        upload.store_comic_upload("c.cbz", _zip({"ok.png": _png(), member: _png()}), tmp_path / "src")
    assert not [p for p in (tmp_path / "src").iterdir()] and not (tmp_path / "up").exists()


def test_a_symlink_member_is_refused(tmp_path: Path) -> None:
    with pytest.raises(upload.ComicUploadError, match="symlink"):
        upload.store_comic_upload("c.cbz", _zip({"1.png": _png()}, symlink="2.png"), tmp_path)


def test_too_many_files_is_refused(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(upload, "MAX_FILES", 3)
    with pytest.raises(upload.ComicUploadError, match="limit is 3"):
        upload.store_comic_upload("c.cbz", _zip({f"{i}.png": _png() for i in range(4)}), tmp_path)


def test_declared_unpacked_size_past_the_cap_is_refused(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(upload, "MAX_UNPACKED_BYTES", 1000)
    with pytest.raises(upload.ComicUploadError, match="unpacks to more"):
        upload.store_comic_upload("c.cbz", _zip({"1.png": _png(size=(200, 200), noise=True)}), tmp_path)


def test_a_member_that_unpacks_past_the_member_cap_is_refused(tmp_path: Path, monkeypatch) -> None:
    """A zip header can lie about its size; the read itself is capped."""
    monkeypatch.setattr(upload, "MAX_MEMBER_BYTES", 200)
    with pytest.raises(upload.ComicUploadError, match="more than the allowed"):
        upload.store_comic_upload("c.cbz", _zip({"1.png": _png(size=(300, 300))}), tmp_path)


def test_only_image_members_count(tmp_path: Path) -> None:
    with pytest.raises(upload.ComicUploadError, match="no page images"):
        upload.store_comic_upload("c.cbz", _zip({"notes.txt": b"hi", "run.sh": b"rm -rf /"}), tmp_path)
    with pytest.raises(upload.ComicUploadError, match="not a readable image"):
        upload.store_comic_upload("c.cbz", _zip({"1.png": b"not an image"}), tmp_path)


def test_wrong_suffix_and_corrupt_archive_are_refused(tmp_path: Path) -> None:
    with pytest.raises(upload.ComicUploadError, match="only .cbz"):
        upload.store_comic_upload("c.exe", b"MZ", tmp_path)
    with pytest.raises(upload.ComicUploadError, match="valid .cbz"):
        upload.store_comic_upload("c.cbz", b"PK nope", tmp_path)
    with pytest.raises(upload.ComicUploadError, match="not a PDF"):
        upload.store_comic_upload("c.pdf", b"<html>", tmp_path)


def test_a_refused_reupload_keeps_the_earlier_comic(tmp_path: Path) -> None:
    upload.store_comic_upload("c.cbz", _zip({"1.png": _png()}), tmp_path)
    with pytest.raises(upload.ComicUploadError):
        upload.store_comic_upload("c.cbz", _zip({"x.txt": b"no"}), tmp_path)
    assert [p.name for p in (tmp_path / "c").iterdir()] == ["0001_1.png"]
    assert not any(p.name.startswith(".") for p in tmp_path.iterdir())


def test_pdf_is_kept_as_one_file_and_read_through_source_input(tmp_path: Path) -> None:
    out = upload.store_comic_upload("book.pdf", b"%PDF-1.4\n%%EOF", tmp_path)
    assert out["kind"] == "pdf" and upload.source_input(tmp_path / "book") == tmp_path / "book" / "source.pdf"
