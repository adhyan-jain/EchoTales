"""Depth parallax for a still: shift each pixel sideways in proportion to how near it is.

The depth map comes from Depth Anything V2 Small (Apache-2.0, 25M parameters) when its weights are present under
`data/models/depth-anything-v2-small/`; without it the builder keeps the plain camera move. A depth map is relative
inverse depth (bigger = nearer), normalised to [0, 1] here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

DEPTH_WEIGHTS = Path("data/models/depth-anything-v2-small")


_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def prepare_depth_input(image: Image.Image, target: int = 518, multiple: int = 14) -> np.ndarray:
    """What `DPTImageProcessor` does for this model (preprocessor_config.json), without torchvision: resize keeping the
    aspect with the scale nearer 1, both sides rounded to a multiple of 14, scale to [0, 1], ImageNet-normalise.
    Returns (3, H, W) float32."""
    w, h = image.size
    sh, sw = target / h, target / w
    scale = sw if abs(1 - sw) < abs(1 - sh) else sh
    nh, nw = (max(multiple, round(v * scale / multiple) * multiple) for v in (h, w))
    arr = np.asarray(image.convert("RGB").resize((nw, nh), Image.Resampling.BICUBIC), dtype=np.float32) / 255.0
    return ((arr - _MEAN) / _STD).transpose(2, 0, 1)


class DepthEstimator(Protocol):
    name: str

    def depth(self, image: Image.Image) -> np.ndarray: ...


class DepthAnythingSmall:
    name = "depth-anything-v2-small"

    def __init__(self, weights: Path | str = DEPTH_WEIGHTS, device: str = "cuda") -> None:
        import torch
        from transformers import AutoModelForDepthEstimation

        if not Path(weights).is_dir():
            raise FileNotFoundError(f"Depth Anything V2 Small weights not found at {weights}")
        self._torch, self.device = torch, device
        self.model = AutoModelForDepthEstimation.from_pretrained(str(weights)).to(device).eval()

    def depth(self, image: Image.Image) -> np.ndarray:
        torch = self._torch
        pixels = torch.from_numpy(prepare_depth_input(image))[None].to(self.device)
        with torch.no_grad():
            pred = self.model(pixel_values=pixels).predicted_depth
        pred = torch.nn.functional.interpolate(pred[None], size=image.size[::-1], mode="bicubic", align_corners=False)[0, 0]
        d = pred.float().cpu().numpy()
        return ((d - d.min()) / max(float(d.max() - d.min()), 1e-6)).astype(np.float32)


def parallax_warp(image: Image.Image, depth: np.ndarray, shift_px: float) -> Image.Image:
    """Backward-warp `image` horizontally: a pixel at depth 1 (near) moves `shift_px`, depth 0 (far) moves none.

    Pixels are never stretched across more than `shift_px`, so edges between layers smear by at most that much,
    which is why callers keep it to a few pixels at output size.
    """
    if shift_px == 0:
        return image.convert("RGB")
    import cv2

    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    d = np.asarray(Image.fromarray(depth).resize((w, h), Image.Resampling.BILINEAR)) if depth.shape != (h, w) else depth
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    out = cv2.remap(rgb, xs - d.astype(np.float32) * shift_px, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(out)
