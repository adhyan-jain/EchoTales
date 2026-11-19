"""Text recognition behind one small interface so the engine can be swapped by measurement.

Engines import lazily: a missing package raises `OcrUnavailable` naming the install, so the rest of the comic path
(panels, graph, video) works without any OCR package. Optional libraries installed outside the project venv (the
bake-off kept easyocr/rapidocr off the shared venv because easyocr drags in a different torch) are found through
`ECHOTALES_COMIC_LIBS`, an os.pathsep-separated list of extra site directories.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PIL import Image


class OcrUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TextLine:
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 in page pixels
    text: str
    confidence: float


class OcrEngine(Protocol):
    name: str

    def read(self, image: Image.Image) -> list[TextLine]: ...


def _extra_paths() -> None:
    for p in filter(None, os.environ.get("ECHOTALES_COMIC_LIBS", "").split(os.pathsep)):
        if p not in sys.path:
            sys.path.append(p)


def _bbox(quad) -> tuple[int, int, int, int]:
    pts = np.asarray(quad, dtype=float).reshape(-1, 2)
    return int(pts[:, 0].min()), int(pts[:, 1].min()), int(pts[:, 0].max()), int(pts[:, 1].max())


class RapidOcr:
    """PaddleOCR models through onnxruntime (rapidocr-onnxruntime, Apache-2.0). CPU, no torch."""

    name = "rapidocr"

    def __init__(self) -> None:
        _extra_paths()
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise OcrUnavailable("pip install rapidocr-onnxruntime (Apache-2.0)") from exc
        self._ocr = RapidOCR()

    def read(self, image: Image.Image) -> list[TextLine]:
        result, _ = self._ocr(np.asarray(image.convert("RGB"))[:, :, ::-1])
        return [TextLine(_bbox(q), t.strip(), float(c)) for q, t, c in (result or []) if t.strip()]


class EasyOcr:
    """easyocr (Apache-2.0), English recogniser; runs on the GPU only when asked to."""

    name = "easyocr"

    def __init__(self, *, gpu: bool = False, langs: tuple[str, ...] = ("en",)) -> None:
        _extra_paths()
        try:
            import easyocr
        except ImportError as exc:
            raise OcrUnavailable("pip install easyocr (Apache-2.0)") from exc
        self._reader = easyocr.Reader(list(langs), gpu=gpu, verbose=False)

    def read(self, image: Image.Image) -> list[TextLine]:
        out = self._reader.readtext(np.asarray(image.convert("RGB")))
        return [TextLine(_bbox(q), t.strip(), float(c)) for q, t, c in out if t.strip()]


ENGINES = {"rapidocr": RapidOcr, "easyocr": EasyOcr}


def get_ocr(name: str = "rapidocr") -> OcrEngine:
    try:
        return ENGINES[name]()
    except KeyError as exc:
        raise OcrUnavailable(f"unknown OCR engine {name!r}; choose from {sorted(ENGINES)}") from exc
