"""Find and read the public-domain texts locally; the repository never holds them.

A reference stores `(offset, length, sha256 of the slice)` into a *canonical text*, never the text. The hash is how a
reader's copy is checked: if the slice at that offset hashes differently, the copy is a different edition or was
extracted differently, and scoring against it would be silent nonsense, so `verify_slice` fails instead.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

#: Where each source lives under `--sources-dir` (default `data/raw`). Only the path of a local file is recorded.
SOURCES: dict[str, dict[str, Any]] = {
    "pride-and-prejudice": {
        "kind": "epub", "candidates": ["gutenberg/pride-and-prejudice.epub"],
        "licence": "Public domain (Project Gutenberg #1342)",
    },
    "sherlock-holmes-adventures": {
        "kind": "gutenberg-txt", "candidates": ["pd_gutenberg/pg1661.txt"],
        "licence": "Public domain (Project Gutenberg #1661)",
    },
    "pepper-carrot": {
        "kind": "images", "candidates": ["comics/pepper-carrot"],
        "licence": "CC BY 4.0 (David Revoy, peppercarrot.com)",
    },
}


def slice_hash(text: str) -> str:
    """SHA-256 of `text` with every whitespace run collapsed, so re-wrapping a hard-wrapped edition does not break it."""
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()


def verify_slice(canonical: str, item: dict[str, Any]) -> bool:
    start, length = int(item["offset"]), int(item["length"])
    if start < 0 or start + length > len(canonical):
        return False
    return slice_hash(canonical[start:start + length]) == item["text_sha256"]


def locate(source_id: str, sources_dir: Path | str = "data/raw") -> Path:
    spec = SOURCES.get(source_id)
    if spec is None:
        raise KeyError(f"unknown benchmark source {source_id!r}; known: {', '.join(sorted(SOURCES))}")
    root = Path(sources_dir)
    tried = [root / c for c in spec["candidates"]]
    for p in tried:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"{source_id}: not found under {root} (tried {', '.join(str(t) for t in tried)}). "
        f"Download it yourself ({spec['licence']}) and pass --sources-dir."
    )


def canonical_gutenberg_txt(path: Path) -> str:
    """The body between Project Gutenberg's START and END markers, newlines normalised to `\\n`."""
    raw = Path(path).read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    start = re.search(r"\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*\*\*\*\n", raw)
    end = re.search(r"\n\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", raw)
    body = raw[start.end():end.start() if end else None] if start else raw
    return body.strip("\n")


class _Paragraphs(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paras: list[str] = []
        self._buf: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("p", "h1", "h2", "h3"):
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("p", "h1", "h2", "h3") and self._buf is not None:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if text:
                self.paras.append(text)
            self._buf = None

    def handle_data(self, data: str) -> None:
        if self._buf is not None:
            self._buf.append(data)


def canonical_epub(path: Path) -> str:
    """Paragraph text of every HTML file in the EPUB's reading order, one blank line between paragraphs."""
    with zipfile.ZipFile(path) as z:
        opf_name = next(n for n in z.namelist() if n.endswith(".opf"))
        opf = z.read(opf_name).decode("utf-8")
        base = opf_name.rsplit("/", 1)[0] + "/" if "/" in opf_name else ""
        hrefs: dict[str, str] = {}
        for tag in re.findall(r"<item\b[^>]*>", opf):
            ident = re.search(r'\bid="([^"]+)"', tag)
            href = re.search(r'\bhref="([^"]+)"', tag)
            if ident and href:
                hrefs[ident.group(1)] = href.group(1)
        paras: list[str] = []
        for idref in re.findall(r'<itemref\b[^>]*?idref="([^"]+)"', opf):
            href = hrefs.get(idref)
            if not href or not href.lower().endswith((".htm", ".html", ".xhtml")):
                continue
            parser = _Paragraphs()
            parser.feed(z.read(base + href).decode("utf-8", errors="replace"))
            paras.extend(parser.paras)
    return "\n\n".join(paras)


def canonical_text(source_id: str, sources_dir: Path | str = "data/raw") -> str:
    spec = SOURCES[source_id]
    path = locate(source_id, sources_dir)
    if spec["kind"] == "epub":
        return canonical_epub(path)
    if spec["kind"] == "gutenberg-txt":
        return canonical_gutenberg_txt(path)
    raise ValueError(f"{source_id} is not a text source")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
