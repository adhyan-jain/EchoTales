"""Structural conditioning for the SDXL art worker (art bake-off v3): which ControlNet, how a reference becomes a control map.

Why a separate, torch-free module: the worker (`_sdxl_art_worker.py`) is a GPU subprocess nobody can run in CI, but the rules
about what is allowed (which kinds exist, which weights fit the 8 GB card next to a 5 GB SDXL UNet, that an openpose map is
never guessed) are plain data and are unit-tested here.

Sizing is the load-bearing fact: a full SDXL ControlNet is 2.5 GB in fp16, so UNet (5.1) + ControlNet (2.5) + activations does
not fit 8 GB without CPU offload, which the owner forbids (RAM spike 2026-10-02). The `-small` canny and depth ControlNets are
0.32 GB and do fit. The union ControlNet (openpose, lineart, ...) is 2.5 GB and is refused unless the caller opts in with
`allow_big` (a 12 GB+ card, or the cloud)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: kind -> (HF repo, weights file, approx fp16 GiB, union control_mode or None). `lineart` reuses the canny model on a line map.
CONTROLNETS: dict[str, tuple[str, str, float, int | None]] = {
    "canny": ("diffusers/controlnet-canny-sdxl-1.0-small", "diffusion_pytorch_model.fp16.safetensors", 0.32, None),
    "lineart": ("diffusers/controlnet-canny-sdxl-1.0-small", "diffusion_pytorch_model.fp16.safetensors", 0.32, None),
    "depth": ("diffusers/controlnet-depth-sdxl-1.0-small", "diffusion_pytorch_model.fp16.safetensors", 0.32, None),
    "openpose": ("xinsir/controlnet-union-sdxl-1.0", "diffusion_pytorch_model_promax.safetensors", 2.5, 0),
}
KINDS = tuple(CONTROLNETS)
#: Above this the ControlNet cannot be resident beside the UNet on an 8 GB card.
MAX_RESIDENT_GIB = 1.0


@dataclass(frozen=True, slots=True)
class ControlSpec:
    kind: str
    image: str
    #: ControlNet conditioning scale; 0.5-0.7 keeps the layout without flattening the style (SDXL ControlNet cards).
    scale: float = 0.6
    start: float = 0.0
    end: float = 0.8
    #: Turn `image` into a control map first (canny/lineart/depth). Never for openpose: a skeleton is drawn, not guessed.
    preprocess: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> ControlSpec:
        return cls(kind=d["kind"], image=d["image"], scale=float(d.get("scale", 0.6)), start=float(d.get("start", 0.0)),
                   end=float(d.get("end", 0.8)), preprocess=bool(d.get("preprocess", d["kind"] != "openpose")))


def validate(spec: ControlSpec, *, allow_big: bool = False) -> None:
    if spec.kind not in CONTROLNETS:
        raise ValueError(f"unknown control kind {spec.kind!r}; expected one of {list(KINDS)}")
    if spec.kind == "openpose" and spec.preprocess:
        raise ValueError("openpose has no preprocessor here: pass a pre-drawn skeleton image with preprocess=false")
    if not 0.0 <= spec.start < spec.end <= 1.0:
        raise ValueError(f"control window must satisfy 0 <= start < end <= 1, got {spec.start}..{spec.end}")
    if not 0.0 < spec.scale <= 2.0:
        raise ValueError(f"control scale {spec.scale} out of range (0, 2]")
    gib = CONTROLNETS[spec.kind][2]
    if gib > MAX_RESIDENT_GIB and not allow_big:
        raise ValueError(f"{spec.kind} needs the {gib} GiB union ControlNet, which does not fit beside the SDXL UNet on 8 GB "
                         f"without CPU offload; pass allow_big only on a larger card")


def control_map(spec: ControlSpec, size: tuple[int, int]):
    """The control image at `size`: the reference run through the kind's preprocessor (canny, lineart, depth), or as given."""
    from PIL import Image

    img = Image.open(spec.image).convert("RGB").resize(size, Image.Resampling.LANCZOS)
    if not spec.preprocess:
        return img
    if spec.kind in ("canny", "lineart"):
        import cv2
        import numpy as np

        grey = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        if spec.kind == "canny":
            edges = cv2.Canny(grey, 100, 200)
        else:  # a rough layout sketch: dark strokes on light paper -> white lines on black
            edges = 255 - cv2.adaptiveThreshold(cv2.GaussianBlur(grey, (3, 3), 0), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                                cv2.THRESH_BINARY, 15, 8)
        return Image.fromarray(np.stack([edges] * 3, axis=-1))
    if spec.kind == "depth":
        from transformers import pipeline

        local = Path(__file__).resolve().parents[6] / "data/models/depth-anything-v2-small"
        est = pipeline("depth-estimation", model=str(local) if local.exists() else "depth-anything/Depth-Anything-V2-Small-hf")
        depth = est(img)["depth"].convert("RGB").resize(size)
        return depth
    raise ValueError(spec.kind)
