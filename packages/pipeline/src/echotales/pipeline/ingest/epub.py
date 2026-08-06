"""EPUB container reading.

Deliberately implemented over `zipfile` + `lxml` rather than a reader library.
An EPUB is a zip holding an OPF manifest, an NCX (or nav) table of contents,
and XHTML documents; the parts this pipeline needs are the spine order and the
TOC labels, both of which are a few lines of XPath. A reader library would add
a dependency and, more importantly, would normalise away the per-source quirks
that the adapters exist to handle.

The TOC is the authority on chapter identity. Filenames are not: the RI export
names Chapter 1 ``page-0.html``, and split chapters (45.1) have no filename
representation at all.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "xhtml": "http://www.w3.org/1999/xhtml",
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
}


@dataclass(slots=True)
class TocEntry:
    """One table-of-contents entry."""

    label: str
    href: str
    play_order: int

    @property
    def path(self) -> str:
        """Href without its fragment."""
        return self.href.split("#", 1)[0]


@dataclass(slots=True)
class EpubDocument:
    """One XHTML document from the spine."""

    href: str
    html: bytes


class Epub:
    """Read-only view of an EPUB container."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"EPUB not found: {self.path}")
        self._zip = zipfile.ZipFile(self.path)
        self._opf_path = self._find_opf()
        self._opf_dir = posixpath.dirname(self._opf_path)
        self._opf = etree.fromstring(self._zip.read(self._opf_path))

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> Epub:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- container plumbing -------------------------------------------

    def _find_opf(self) -> str:
        """Locate the OPF via META-INF/container.xml, falling back to a scan.

        Some hand-rolled exports (the RI one included) put the OPF at the root
        with a non-standard name and ship no container.xml, so the fallback is
        load-bearing rather than defensive.
        """
        try:
            container = etree.fromstring(self._zip.read("META-INF/container.xml"))
            rootfile = container.find(".//container:rootfile", NS)
            if rootfile is not None:
                full_path = rootfile.get("full-path")
                if full_path:
                    return full_path
        except (KeyError, etree.XMLSyntaxError):
            pass

        for name in self._zip.namelist():
            if name.endswith(".opf"):
                return name
        raise ValueError(f"no OPF manifest found in {self.path}")

    def _resolve(self, href: str, relative_to: str | None = None) -> str:
        """Resolve an href against the OPF directory (or another document)."""
        base = self._opf_dir if relative_to is None else posixpath.dirname(relative_to)
        joined = posixpath.normpath(posixpath.join(base, href)) if base else href
        return joined.lstrip("./")

    def read(self, href: str) -> bytes:
        try:
            return self._zip.read(href)
        except KeyError:
            # Zip entries and hrefs disagree on leading "./" and on percent
            # encoding often enough that a direct lookup alone is unreliable.
            from urllib.parse import unquote

            target = unquote(href).lstrip("/")
            for name in self._zip.namelist():
                if name == target or name.endswith("/" + target):
                    return self._zip.read(name)
            raise

    # ---- metadata ------------------------------------------------------

    @property
    def title(self) -> str:
        node = self._opf.find(".//dc:title", NS)
        return (node.text or "").strip() if node is not None else self.path.stem

    @property
    def author(self) -> str:
        node = self._opf.find(".//dc:creator", NS)
        return (node.text or "").strip() if node is not None else ""

    # ---- spine and manifest ---------------------------------------------

    def manifest(self) -> dict[str, str]:
        """id -> resolved href."""
        out: dict[str, str] = {}
        for item in self._opf.findall(".//opf:manifest/opf:item", NS):
            item_id, href = item.get("id"), item.get("href")
            if item_id and href:
                out[item_id] = self._resolve(href)
        return out

    def spine(self) -> list[str]:
        """Reading-order hrefs."""
        manifest = self.manifest()
        return [
            manifest[idref]
            for ref in self._opf.findall(".//opf:spine/opf:itemref", NS)
            if (idref := ref.get("idref")) and idref in manifest
        ]

    # ---- table of contents -----------------------------------------------

    def toc(self) -> list[TocEntry]:
        """Chapter labels in play order.

        Tries the NCX first (EPUB 2, what both current sources ship), then the
        EPUB 3 nav document.
        """
        ncx = self._find_ncx()
        if ncx is not None:
            return self._parse_ncx(ncx)
        nav = self._find_nav()
        if nav is not None:
            return self._parse_nav(nav)
        raise ValueError(f"no table of contents found in {self.path}")

    def _find_ncx(self) -> str | None:
        for item in self._opf.findall(".//opf:manifest/opf:item", NS):
            if item.get("media-type") == "application/x-dtbncx+xml":
                href = item.get("href")
                if href:
                    return self._resolve(href)
        for name in self._zip.namelist():
            if name.endswith(".ncx"):
                return name
        return None

    def _parse_ncx(self, ncx_path: str) -> list[TocEntry]:
        tree = etree.fromstring(self.read(ncx_path))
        entries: list[TocEntry] = []
        for i, nav in enumerate(tree.findall(".//ncx:navPoint", NS)):
            label_node = nav.find("./ncx:navLabel/ncx:text", NS)
            content = nav.find("./ncx:content", NS)
            if label_node is None or content is None:
                continue
            src = content.get("src") or ""
            order = nav.get("playOrder")
            entries.append(
                TocEntry(
                    label=(label_node.text or "").strip(),
                    href=self._resolve(src, relative_to=ncx_path),
                    play_order=int(order) if order and order.isdigit() else i,
                )
            )
        entries.sort(key=lambda e: e.play_order)
        return entries

    def _find_nav(self) -> str | None:
        for item in self._opf.findall(".//opf:manifest/opf:item", NS):
            props = item.get("properties") or ""
            if "nav" in props.split():
                href = item.get("href")
                if href:
                    return self._resolve(href)
        return None

    def _parse_nav(self, nav_path: str) -> list[TocEntry]:
        parser = etree.HTMLParser()
        tree = etree.fromstring(self.read(nav_path), parser)
        entries: list[TocEntry] = []
        for i, a in enumerate(tree.xpath("//nav//a[@href]")):
            label = " ".join("".join(a.itertext()).split())
            if label:
                entries.append(
                    TocEntry(
                        label=label,
                        href=self._resolve(a.get("href"), relative_to=nav_path),
                        play_order=i,
                    )
                )
        return entries

    # ---- documents ---------------------------------------------------------

    def documents(self) -> Iterator[EpubDocument]:
        """Stream spine documents in reading order.

        A generator: a 500-chapter EPUB's decompressed XHTML is large enough
        that materialising it whole competes with the models this pipeline
        loads later.
        """
        for href in self.spine():
            try:
                yield EpubDocument(href=href, html=self.read(href))
            except KeyError:
                continue


CHAPTER_LABEL = re.compile(
    r"""
    ^\s*
    (?:chapter|ch\.?|episode|ep\.?)   # keyword
    \s*
    (?P<number>\d+(?:\.\d+)?)         # 45 or 45.1
    \s*
    (?:[:\-–—.]\s*(?P<title>.*))?   # optional ": Title"
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Bonus/side chapters carry no number and must not silently collide with the
# main sequence, so they are detected explicitly rather than defaulted to 0.
SIDE_LABEL = re.compile(
    r"^\s*(?:side\s*story|extra|interlude|bonus|prologue|epilogue|afterword)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ParsedLabel:
    number: float | None
    title: str
    is_side: bool


def parse_chapter_label(label: str) -> ParsedLabel:
    """Extract a chapter number and title from a TOC label.

    Regex-first per plans.md §6 Phase 0; callers escalate to an LLM only when
    this returns no number for something that looks like a chapter.
    """
    match = CHAPTER_LABEL.match(label)
    if match:
        title = (match.group("title") or "").strip()
        return ParsedLabel(
            number=float(match.group("number")),
            title=title or label.strip(),
            is_side=False,
        )
    return ParsedLabel(number=None, title=label.strip(), is_side=bool(SIDE_LABEL.match(label)))
