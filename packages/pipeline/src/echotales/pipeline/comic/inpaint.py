"""Clean plates: remove lettering so the art can move, and keep the original text as a subtitle track.

`CvInpainter` (OpenCV Telea) is the default: deterministic, CPU, no weights. It is honest about its ceiling: it
smears across busy art, which is invisible on flat bubble fills and visible behind sound effects drawn over
detailed painting. `LamaInpainter` (big-lama, Apache-2.0) loads the TorchScript model directly (no extra package)
and is used when its weights are present under data/models/lama/; it runs on the GPU, so callers wrap it in the
project GPU lock.
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


class LamaInpainter:
    name = "lama"

    def __init__(self, weights: Path | str = LAMA_WEIGHTS, device: str = "cuda") -> None:
        import torch

        if not Path(weights).is_file():
            raise FileNotFoundError(f"LaMa weights not found at {weights}")
        self._torch = torch
        self.device = device
        self.model = torch.jit.load(str(weights), map_location=device).eval()

    def inpaint(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        torch = self._torch
        rgb = image.convert("RGB")
        m = (np.asarray(mask.convert("L")) > 0)
        if not m.any():
            return rgb
        w, h = rgb.size
        pw, ph = (-w) % 8, (-h) % 8
        img = torch.from_numpy(np.asarray(rgb)).permute(2, 0, 1).float().div(255)[None]
        msk = torch.from_numpy(m.astype(np.float32))[None, None]
        img = torch.nn.functional.pad(img, (0, pw, 0, ph), mode="reflect")
        msk = torch.nn.functional.pad(msk, (0, pw, 0, ph), mode="reflect")
        with torch.no_grad():
            out = self.model(img.to(self.device), (msk > 0).float().to(self.device))
        arr = (out[0, :, :h, :w].permute(1, 2, 0).clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
        arr = np.where(m[:, :, None], arr, np.asarray(rgb))
        return Image.fromarray(arr)


def get_inpainter(name: str = "cv") -> Inpainter:
    if name == "cv":
        return CvInpainter()
    if name == "lama":
        return LamaInpainter()
    raise ValueError(f"unknown inpainter {name!r}; choose cv or lama")


def _ts(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_text(cues: list[tuple[float, float, str]]) -> str:
    """SubRip text for `(start, end, text)` cues. The original lettering rides along as an optional track."""
    return "".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(cues, 1))
