"""Receive an uploaded comic (.cbz, .zip of images, or .pdf) into `comic/source/<name>/` without trusting it.

The Studio's upload route hands the bytes here. Everything an archive can do to a naive extractor is refused before a
byte lands: absolute and `..` member paths and symlinks (write outside the folder), a member list past `MAX_FILES` or
declared sizes past `MAX_UNPACKED_BYTES` (zip bomb), a header that lies about its size (each member is read through a
hard cap, not trusted), and non-images (ignored, except that an archive with no image at all is refused). Names inside
the folder are rewritten to `0001_<basename>` so two members with the same basename in different folders cannot
overwrite one another and the natural page order survives the flattening.
"""

from __future__ import annotations

import io
import re
import shutil
import stat
import zipfile
from pathlib import Path

from PIL import Image

from echotales.pipeline.comic.ingest import IMAGE_SUFFIXES, natural_key

MAX_FILES = 500
MAX_UNPACKED_BYTES = 400 * 1024 * 1024
MAX_MEMBER_BYTES = 60 * 1024 * 1024
ARCHIVE_SUFFIXES = (".cbz", ".zip")
PDF_NAME = "source.pdf"


class ComicUploadError(ValueError):
    """The upload is refused; the message is safe to show the person who sent it."""


def source_name(filename: str) -> str:
    """A folder name from the client's file name: its last path component only, stem only, a narrow alphabet."""
    stem = Path(filename.replace("\\", "/")).stem
    name = re.sub(r"[^A-Za-z0-9._-]", "_", stem).lstrip(".")
    if not name:
        raise ComicUploadError("the file needs a name made of letters or digits")
    return name[:80]


def _unsafe(member: str) -> bool:
    parts = member.replace("\\", "/").split("/")
    return member.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", member) is not None or ".." in parts


def _read_capped(z: zipfile.ZipFile, info: zipfile.ZipInfo, budget: int) -> bytes:
    limit = min(MAX_MEMBER_BYTES, budget)
    with z.open(info) as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise ComicUploadError(f"{info.filename!r} unpacks to more than the allowed size")
    return data


def _check_image(data: bytes, member: str) -> None:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except Exception as exc:  # PIL raises many types, including its decompression-bomb error
        raise ComicUploadError(f"{member!r} is not a readable image") from exc


def _extract_archive(data: bytes, dest: Path) -> int:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ComicUploadError("not a valid .cbz or .zip file") from exc
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > MAX_FILES:
            raise ComicUploadError(f"the archive holds {len(infos)} files; the limit is {MAX_FILES}")
        for i in infos:
            if _unsafe(i.filename):
                raise ComicUploadError(f"unsafe path in the archive: {i.filename!r}")
            mode = i.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ComicUploadError(f"the archive contains a symlink: {i.filename!r}")
        if sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES:
            raise ComicUploadError(f"the archive unpacks to more than {MAX_UNPACKED_BYTES // (1024 * 1024)} MB")
        images = [
            i for i in infos
            if Path(i.filename).suffix.lower() in IMAGE_SUFFIXES
            and "__MACOSX" not in i.filename and not Path(i.filename).name.startswith("._")
        ]
        if not images:
            raise ComicUploadError("no page images (.png .jpg .webp ...) found in the archive")
        images.sort(key=lambda i: natural_key(i.filename))
        budget = MAX_UNPACKED_BYTES
        for n, info in enumerate(images, 1):
            blob = _read_capped(z, info, budget)
            budget -= len(blob)
            _check_image(blob, info.filename)
            base = re.sub(r"[^A-Za-z0-9._-]", "_", Path(info.filename.replace("\\", "/")).name)
            (dest / f"{n:04d}_{base}").write_bytes(blob)
    return len(images)


def store_comic_upload(filename: str, data: bytes, source_root: Path) -> dict:
    """Write the upload to `source_root/<name>/` (replacing a same-named earlier upload) and describe it.

    Built in a sibling temp folder and renamed in, so a refused upload never leaves half a comic or destroys the
    previous one."""
    suffix = Path(filename.replace("\\", "/")).suffix.lower()
    if suffix not in (*ARCHIVE_SUFFIXES, ".pdf"):
        raise ComicUploadError("only .cbz, .zip (of images) or .pdf comics are accepted")
    name = source_name(filename)
    source_root.mkdir(parents=True, exist_ok=True)
    tmp = source_root / f".{name}.upload"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        if suffix == ".pdf":
            if not data.lstrip().startswith(b"%PDF-"):
                raise ComicUploadError("not a PDF file")
            (tmp / PDF_NAME).write_bytes(data)
            pages = 0
        else:
            pages = _extract_archive(data, tmp)
        final = source_root / name
        shutil.rmtree(final, ignore_errors=True)
        tmp.replace(final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return {"name": name, "pages": pages, "bytes": len(data), "kind": "pdf" if suffix == ".pdf" else "images"}


def source_input(folder: Path) -> Path:
    """What `load_pages` should read for an uploaded source folder: the folder of images, or its single PDF."""
    pdf = folder / PDF_NAME
    return pdf if pdf.is_file() else folder
