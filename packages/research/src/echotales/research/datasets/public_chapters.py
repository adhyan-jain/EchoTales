"""Chapters and beats from public-domain novels (the PDNC texts).

Moment-selection research must not rest on the copyrighted web novels the
product targets -- a benchmark built on them cannot be released. PDNC's
novels are Gutenberg texts, so chapters cut from them are shareable as
offsets + a fetch script.

Beats here are text-only (paragraphs merged to a size band) because the
product's `render/beats.py` segments over typed spans and scene boundaries
that only exist after ingest; this is the comparable unit for plain text,
with the same 900-char ceiling the product uses (`_MAX_BEAT_CHARS`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from echotales.research.datasets import pdnc

_CHAPTER = re.compile(r"\n\s*(?:CHAPTER|Chapter|BOOK|Book)\s+[IVXLC\d]+[^\n]*\n")
MIN_BEAT, MAX_BEAT = 400, 900


@dataclass(frozen=True, slots=True)
class Beat:
    id: str
    novel: str
    chapter: int
    index: int
    text: str


def chapters(text: str) -> list[str]:
    parts = _CHAPTER.split(text)
    return [p.strip() for p in parts[1:] if len(p.strip()) > 3000]


def beats(chapter_text: str, novel: str, chapter: int) -> list[Beat]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", chapter_text) if p.strip()]
    out, buf = [], ""
    for p in paras:
        if buf and len(buf) + len(p) > MAX_BEAT:
            out.append(buf)
            buf = ""
        buf = f"{buf}\n\n{p}".strip()
        if len(buf) >= MIN_BEAT:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return [Beat(f"{novel}:c{chapter}:b{i}", novel, chapter, i, t) for i, t in enumerate(out)]


def sample(n_novels: int = 6, chapters_per_novel: int = 2) -> list[list[Beat]]:
    out = []
    for name in pdnc.available()[:n_novels]:
        nv = pdnc.load_novel(name)
        for ci, ch in enumerate(chapters(nv.text)[:chapters_per_novel]):
            bs = beats(ch, name, ci)
            if len(bs) >= 10:
                out.append(bs)
    return out
