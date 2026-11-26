"""Page understanding: panels, ordered bubbles with text and kind, speaker clusters, and a text mask per page.

Everything except the OCR engine is deterministic. The result is plain JSON (`understanding.json`) so a reviewer or a
later stage can read it without re-running a model, and `to_graph` needs nothing else.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from echotales.pipeline.comic.bubbles import (
    Bubble,
    cluster_speakers,
    detect_bubbles,
    trim_bubble_mask,
)
from echotales.pipeline.comic.ingest import PageImage
from echotales.pipeline.comic.ocr import OcrEngine
from echotales.pipeline.comic.panels import detect_panels
from PIL import Image
from scipy import ndimage

#: Half-L1 distance between tail-target colour signatures under which two tails point at the same character.
#: Tuned on Pepper&Carrot ep01, which has one speaker: it validates "same character merges", not "different
#: characters split" (reported in data/eval/comic/understand_bakeoff.json).
SPEAKER_THRESHOLD = 0.45
#: Pixels to grow the inpainting mask by: anti-aliased glyph and outline edges extend past the detected region.
MASK_GROW = 4


@dataclass(slots=True)
class PanelUnderstanding:
    index: int
    box: tuple[int, int, int, int]
    bubbles: list[Bubble] = field(default_factory=list)


@dataclass(slots=True)
class PageUnderstanding:
    page_index: int
    name: str
    size: tuple[int, int]
    panels: list[PanelUnderstanding]
    mask_file: str = ""
    ocr_seconds: float = 0.0


@dataclass(slots=True)
class ComicUnderstanding:
    pages: list[PageUnderstanding]
    ocr_engine: str = ""
    rtl: bool = False
    speakers: list[str] = field(default_factory=list)

    def bubbles(self) -> list[Bubble]:
        """Every bubble in reading order: page, then panel, then bubble."""
        return [b for pg in self.pages for pn in pg.panels for b in pn.bubbles]

    def to_dict(self) -> dict:
        d = asdict(self)
        for pg in d["pages"]:
            for pn in pg["panels"]:
                for b in pn["bubbles"]:
                    b.pop("mask", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ComicUnderstanding:
        pages = []
        for pg in d["pages"]:
            panels = [
                PanelUnderstanding(
                    pn["index"], tuple(pn["box"]),
                    [Bubble(**{**b, "text_box": tuple(b["text_box"]), "box": tuple(b["box"]),
                               "tail": tuple(b["tail"]) if b["tail"] else None}) for b in pn["bubbles"]],
                )
                for pn in pg["panels"]
            ]
            pages.append(PageUnderstanding(pg["page_index"], pg["name"], tuple(pg["size"]), panels,
                                           pg.get("mask_file", ""), pg.get("ocr_seconds", 0.0)))
        return cls(pages, d.get("ocr_engine", ""), d.get("rtl", False), d.get("speakers", []))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> ComicUnderstanding:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _letter(n: int) -> str:
    return f"Character {chr(ord('A') + n)}" if n < 26 else f"Character {n + 1}"


def _text_mask(size: tuple[int, int], bubbles: list[Bubble], *, mask_sfx: bool = False) -> np.ndarray:
    """What the clean plate removes: speech bubbles and caption boxes whole (fill region plus its outline ring), cleaned
    of colour-flood leaks. Sound effects are left in by default: they are painted into the art, are neither voiced nor
    subtitled (`story_bubbles`), and their only mask is the OCR rectangle, which over busy art removes the art with
    the lettering (Pepper&Carrot SPLASH lost its spray; SHH SHH sat in a window the flood had also swallowed)."""
    w, h = size
    mask = np.zeros((h, w), dtype=bool)
    for b in bubbles:
        if b.kind == "sfx" and not mask_sfx:
            continue
        if b.mask is not None:
            mask |= trim_bubble_mask(b.mask, b.text_box)
        else:
            x0, y0, x1, y1 = b.text_box
            mask[y0:y1, x0:x1] = True
    return ndimage.binary_dilation(mask, iterations=MASK_GROW)


def understand_pages(
    pages: list[PageImage],
    ocr: OcrEngine,
    *,
    rtl: bool = False,
    speaker_threshold: float = SPEAKER_THRESHOLD,
    out_dir: Path | None = None,
    mask_sfx: bool = False,
) -> ComicUnderstanding:
    result = ComicUnderstanding([], ocr_engine=ocr.name, rtl=rtl)
    embeddings: list = []
    for page in pages:
        t0 = time.perf_counter()
        lines = ocr.read(page.image)
        ocr_s = time.perf_counter() - t0
        panels = detect_panels(page.image, rtl=rtl)
        bubbles = detect_bubbles(page.image, lines, panels, rtl=rtl)
        pu = PageUnderstanding(
            page.index, page.name, page.image.size,
            [PanelUnderstanding(p.index, p.box, [b for b in bubbles if b.panel_index == p.index]) for p in panels],
            ocr_seconds=round(ocr_s, 3),
        )
        for b in bubbles:
            b.id = f"p{page.index + 1:03d}b{b.order + 1:02d}"
            embeddings.append(b.embedding if b.kind == "speech" else None)
        if out_dir is not None:
            pu.mask_file = f"masks/p{page.index + 1:03d}.png"
            (out_dir / "masks").mkdir(parents=True, exist_ok=True)
            Image.fromarray((_text_mask(page.image.size, bubbles, mask_sfx=mask_sfx) * 255).astype(np.uint8)).save(out_dir / pu.mask_file)
        result.pages.append(pu)
    flat = result.bubbles()
    labels = cluster_speakers(embeddings, threshold=speaker_threshold)
    for b, lab in zip(flat, labels, strict=True):
        b.speaker = _letter(lab) if lab is not None and b.kind == "speech" else None
    result.speakers = sorted({b.speaker for b in flat if b.speaker})
    if out_dir is not None:
        result.save(out_dir / "understanding.json")
    return result
