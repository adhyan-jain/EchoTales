"""Clean plates: remove lettering so the art can move, and keep the original text as a subtitle track.

`get_inpainter("auto")` is the default: `LamaInpainter` (big-lama, Apache-2.0; the TorchScript model is loaded
directly, no extra package) when its weights are under data/models/lama/ and a GPU is there, else `CvInpainter`
(OpenCV Telea: deterministic, CPU, no weights). Telea smears across busy art, which is invisible on flat bubble
fills and visible where a bubble sat over a painted window; LaMa runs on the GPU, so callers wrap it in the project
GPU lock.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

LAMA_WEIGHTS = Path("data/models/lama/big-lama.pt")


class Inpainter(Protocol):
    name: str

    def inpaint(self, image: Image.Image, mask: Image.Image) -> Image.Image: ...


class CvInpainter:
    name = "cv"

    def __init__(self, radius: int = 5) -> None:
        self.radius = radius

    def inpaint(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        import cv2

        m = (np.asarray(mask.convert("L")) > 0).astype(np.uint8) * 255
        if not m.any():
            return image.convert("RGB")
        rgb = np.asarray(image.convert("RGB"))
        out = cv2.inpaint(rgb[:, :, ::-1].copy(), m, self.radius, cv2.INPAINT_TELEA)[:, :, ::-1]
        # cv2 only rewrites masked pixels, but re-compose anyway so "everything else is bit-identical" is
        # a guarantee of this function and not of the library version.
        keep = m == 0
        out = np.where(keep[:, :, None], rgb, out)
        return Image.fromarray(out.astype(np.uint8))


#: Grow each masked region by this many pixels to find the windows LaMa runs on: regions closer than this share one.
WINDOW_JOIN = 48
#: Context kept around a region inside its window. LaMa's receptive field is large, but what it copies from is the art
#: next to the hole; beyond this the extra pixels cost memory and time and change nothing visible.
WINDOW_MARGIN = 128


class LamaInpainter:
    """big-lama (Apache-2.0) as a TorchScript file, called as `model(image, mask) -> image` on [0, 1] tensors.

    It runs on windows around the masked regions, not on the whole page: a webtoon strip is 800 x 20000 and one tensor
    that size does not fit an 8 GB card, while the pages measured (1200 x 1660) take 1.7-2.3 s whole. Everything outside
    the mask is copied back from the input, so the rest of the page is bit-identical."""

    name = "lama"

    def __init__(self, weights: Path | str = LAMA_WEIGHTS, device: str | None = None) -> None:
        import torch

        if not Path(weights).is_file():
            raise FileNotFoundError(f"LaMa weights not found at {weights}")
        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = torch.jit.load(str(weights), map_location=self.device).eval()

    def _windows(self, m: np.ndarray) -> list[tuple[int, int, int, int]]:
        from scipy import ndimage

        h, w = m.shape
        labels, n = ndimage.label(ndimage.binary_dilation(m, iterations=WINDOW_JOIN))
        boxes = []
        for sl in ndimage.find_objects(labels)[:n]:
            ys, xs = sl
            boxes.append((max(0, xs.start - WINDOW_MARGIN + WINDOW_JOIN), max(0, ys.start - WINDOW_MARGIN + WINDOW_JOIN),
                          min(w, xs.stop + WINDOW_MARGIN - WINDOW_JOIN), min(h, ys.stop + WINDOW_MARGIN - WINDOW_JOIN)))
        return boxes

    def _run(self, rgb: np.ndarray, m: np.ndarray) -> np.ndarray:
        torch = self._torch
        h, w = m.shape
        # The net halves the image three times; a side that is not a multiple of 8 breaks its skip connections.
        pw, ph = (-w) % 8, (-h) % 8
        img = torch.from_numpy(rgb.copy()).permute(2, 0, 1).float().div(255)[None]
        msk = torch.from_numpy(m.astype(np.float32))[None, None]
        img = torch.nn.functional.pad(img, (0, pw, 0, ph), mode="reflect")
        msk = torch.nn.functional.pad(msk, (0, pw, 0, ph), mode="constant")
        with torch.no_grad():
            out = self.model(img.to(self.device), (msk > 0).float().to(self.device))
        return (out[0, :, :h, :w].permute(1, 2, 0).clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8)

    def inpaint(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        rgb = np.asarray(image.convert("RGB"))
        m = np.asarray(mask.convert("L")) > 0
        if not m.any():
            return image.convert("RGB")
        out = rgb.copy()
        for x0, y0, x1, y1 in self._windows(m):
            win_m = m[y0:y1, x0:x1]
            filled = self._run(rgb[y0:y1, x0:x1], win_m)
            out[y0:y1, x0:x1][win_m] = filled[win_m]
        return Image.fromarray(out)


def get_inpainter(name: str = "auto", *, weights: Path | str = LAMA_WEIGHTS, device: str | None = None) -> Inpainter:
    """`auto` is LaMa when its weights are on disk and a GPU (or an explicit `device`) is there, else OpenCV Telea.
    Measured on Pepper&Carrot ep01, Telea left grey smudges and cross-hatched streaks wherever a bubble sat over the
    bright window, which LaMa filled with plausible window; on flat fills the two are indistinguishable."""
    if name == "cv":
        return CvInpainter()
    if name == "lama":
        return LamaInpainter(weights, device or "cuda")
    if name == "auto":
        if Path(weights).is_file():
            try:
                import torch

                if device or torch.cuda.is_available():
                    return LamaInpainter(weights, device)
            except Exception:  # no torch, a bad file, a busy card: the plate is still worth having
                pass
        return CvInpainter()
    raise ValueError(f"unknown inpainter {name!r}; choose auto, cv or lama")


def _ts(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_text(cues: list[tuple[float, float, str]]) -> str:
    """SubRip text for `(start, end, text)` cues. The original lettering rides along as an optional track."""
    return "".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(cues, 1))
