"""Text recognition behind one small interface so the engine can be swapped by measurement.

Engines import lazily: a missing package raises `OcrUnavailable` naming the install, so the rest of the comic path
(panels, graph, video) works without any OCR package. `rapidocr` ships in the `comic` extra and is the default;
`easyocr` is an optional adapter (it pulls in its own torch, so it is not in the extra) that is simply unavailable
when it is not importable.
"""

from __future__ import annotations

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


def _bbox(quad) -> tuple[int, int, int, int]:
    pts = np.asarray(quad, dtype=float).reshape(-1, 2)
    return int(pts[:, 0].min()), int(pts[:, 1].min()), int(pts[:, 0].max()), int(pts[:, 1].max())


def _ort_providers() -> list[str]:
    try:
        import onnxruntime  # type: ignore[import-untyped]

        return list(onnxruntime.get_available_providers())
    except ImportError:
        return []


class RapidOcr:
    """PaddleOCR models through onnxruntime (rapidocr-onnxruntime, Apache-2.0), no torch.

    Runs on the CUDA execution provider when onnxruntime has one (`pip install onnxruntime-gpu` in place of
    `onnxruntime`), else on the CPU: the stock wheel is CPU-only, and asking it for CUDA only logs a warning and
    falls back, so the flag is set from what the provider list says rather than assumed (owner rule 2026-11-22)."""

    name = "rapidocr"

    def __init__(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise OcrUnavailable("pip install 'echotales-pipeline[comic]' (rapidocr-onnxruntime, Apache-2.0)") from exc
        self.device = "cuda" if "CUDAExecutionProvider" in _ort_providers() else "cpu"
        use_cuda = self.device == "cuda"
        self._ocr = RapidOCR(det_use_cuda=use_cuda, cls_use_cuda=use_cuda, rec_use_cuda=use_cuda)

    def read(self, image: Image.Image) -> list[TextLine]:
        result, _ = self._ocr(np.asarray(image.convert("RGB"))[:, :, ::-1])
        return [TextLine(_bbox(q), t.strip(), float(c)) for q, t, c in (result or []) if t.strip()]


class EasyOcr:
    """easyocr (Apache-2.0), English recogniser; on the GPU whenever CUDA is there unless `gpu=False` is passed."""

    name = "easyocr"

    def __init__(self, *, gpu: bool | None = None, langs: tuple[str, ...] = ("en",)) -> None:
        try:
            import easyocr
        except ImportError as exc:
            raise OcrUnavailable("pip install easyocr (Apache-2.0)") from exc
        from echotales.pipeline.hwaccel import cuda_available

        self._reader = easyocr.Reader(list(langs), gpu=cuda_available() if gpu is None else gpu, verbose=False)

    def read(self, image: Image.Image) -> list[TextLine]:
        out = self._reader.readtext(np.asarray(image.convert("RGB")))
        return [TextLine(_bbox(q), t.strip(), float(c)) for q, t, c in out if t.strip()]


ENGINES = {"rapidocr": RapidOcr, "easyocr": EasyOcr}


def get_ocr(name: str = "rapidocr") -> OcrEngine:
    try:
        return ENGINES[name]()
    except KeyError as exc:
        raise OcrUnavailable(f"unknown OCR engine {name!r}; choose from {sorted(ENGINES)}") from exc
