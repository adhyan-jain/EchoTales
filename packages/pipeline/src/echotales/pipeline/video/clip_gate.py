"""Quality gate for generated clips. It fails closed.

`video/qa.py` is not used for these clips: its "identity" score is a colour histogram and its
`fallback_to_2_5d=False` path hands a failing clip back as "video". Here a clip that fails a check,
cannot be decoded, or whose check cannot run is REJECTED and the shot falls back to a held still.

None of these scores is identity. They are frame-fidelity (does the first/last frame still look like
the panel it was asked to start/end on), temporal stability (is it moving, and without a jump) and
length. A clip can pass all of them and still have drifted a face: the probe's strong-motion clips
(EVOLUTION 4.146) lost wounds and aged a face while keeping a normal frame difference.

Everything is computed on greyscale frames at the clip's own size, decoded with ffmpeg, using only numpy
and Pillow (scikit-image is not in the main environment). Native size is deliberate: on frames shrunk to
128 or 256 px every probe clip scored SSIM 0.95-0.98 and the bad pair (end 0.85 at full size) was
indistinguishable from the good one (measured 2026-11-15 on the probe MP4s).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

#: THRESHOLDS. Every number comes from a handful of clips (the EVOLUTION 4.146 probe: three good
#: 512x768x97 clips, one bad pair, a few smaller ones), re-scored with THIS module on the probe MP4s
#: (`data/scratch/anime_probe/out`): start SSIM 0.85-0.94, end SSIM 0.914 good / 0.851 bad (512x768), spike
#: 1.1-2.6 good / 5.4 bad, mean difference 1.0-6.3 for usable clips. They separate those clips and nothing
#: more: expect to retune on the first fifty real clips.
#:
#: First-frame SSIM. The lowest usable probe clip scored 0.85; 0.75 leaves room for a lighter start frame
#: while still catching a clip that did not start on its panel.
MIN_START_SSIM = 0.75
#: End frame of a first-last clip: 0.914 for the good same-shot pair and 0.851 for the bad one, a 0.06 gap on
#: ONE pair at 512x768 (the good 384x576 pair scored 0.879, so this is wrong for other sizes). The least
#: trustworthy threshold of the set.
MIN_END_SSIM = 0.88
#: Mean absolute difference between consecutive frames, 0-255. A frozen frame is 0; the stillest probe clip
#: that read as usable ("a living still", 768x1152x49) was 1.04. Below this the clip is a still image and the
#: camera-move hold is the better picture.
MIN_MOTION = 0.4
#: max/mean of the per-pair differences. Clean probe clips measured 1.1-1.9 (2.6 for a strong-motion
#: prompt); the unusable hold-garble-snap clip measured 5.4 (the 49-frame bad pair only 2.3, so it is caught
#: by its end frame, not by this).
MAX_SPIKE_RATIO = 3.5


#: Content drift: CLIP image-embedding cosine similarity between the start image and DRIFT_FRAMES evenly
#: spaced frames. Pixel SSIM cannot see a new subject (a photographic face grew out of a silhouette and scored
#: SSIM 0.43 against a good clip's 0.31, because camera motion alone lowers it); an embedding can.
#:
#: Calibrated on 15 clips (10 probe MP4s + the 5 clips of the first real run), minimum over 8 frames:
#: good 0.857-0.974 (lowest: a real ANIMATE clip, 0.857); bad: photographic face 0.634, cross-composition
#: pair 0.713 and 0.575, strong-motion p005 0.793, strong-motion p006 (wounds vanish, face drifts) 0.842.
#: 0.80 sits in the gap between 0.793 and 0.857 and catches five of the six known-bad clips. It does NOT
#: separate the p006 strong-motion clip (0.842, inside the range of good clips), and the margin on the good
#: side is 0.057 from one clip. A content check, not an identity score.
DRIFT_FRAMES = 8
CLIP_MODEL = "openai/clip-vit-large-patch14"
MIN_DRIFT_SIM = 0.80

Embedder = Callable[[list[Image.Image]], np.ndarray]


class ClipImageEmbedder:
    """CLIP ViT-L/14 image embeddings from the local Hugging Face cache, loaded on first use and freed by `close`.

    GPU only when nothing else holds the card (`gpu.gpu_status()` under the owner's 500 MiB line; the gate runs
    after the video worker process has exited), otherwise CPU. Never downloads.
    """

    def __init__(self) -> None:
        self._model = None
        self._proc = None
        self.device = "cpu"

    def _load(self) -> None:
        import torch
        from echotales.pipeline import gpu
        from transformers import CLIPModel, CLIPProcessor

        status = gpu.gpu_status()
        self.device = "cuda" if status is not None and status.used_mb <= 500 and torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self._proc = CLIPProcessor.from_pretrained(CLIP_MODEL, local_files_only=True)
        self._model = CLIPModel.from_pretrained(CLIP_MODEL, local_files_only=True, torch_dtype=dtype).to(self.device).eval()

    def __call__(self, images: list[Image.Image]) -> np.ndarray:
        import torch

        if self._model is None:
            self._load()
        inputs = self._proc(images=[i.convert("RGB") for i in images], return_tensors="pt").to(self.device)
        with torch.no_grad():
            feats = self._model.get_image_features(pixel_values=inputs["pixel_values"].to(self._model.dtype))
        feats = feats.pooler_output if hasattr(feats, "pooler_output") else feats
        return torch.nn.functional.normalize(feats.float(), dim=-1).cpu().numpy()

    def close(self) -> None:
        self._model = self._proc = None
        try:
            import gc

            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


def decode_rgb_frames(path: str | Path, indices: list[int], width: int, height: int) -> list[Image.Image]:
    """Just the frames at `indices`, in order, as RGB images."""
    sel = "+".join(f"eq(n\\,{i})" for i in indices)
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"select='{sel}',scale={width}:{height}",
           "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
    size = width * height * 3
    if proc.returncode != 0 or len(proc.stdout) != size * len(indices):
        raise ClipDecodeError(f"could not read frames {indices} of {path}: {proc.stderr.decode(errors='replace')[:200]}")
    data = np.frombuffer(proc.stdout, dtype=np.uint8).reshape(len(indices), height, width, 3)
    return [Image.fromarray(f) for f in data]


def drift_scores(
    clip: str | Path, start_image: Image.Image, n_frames: int, width: int, height: int, embedder: Embedder
) -> tuple[float, float]:
    """(minimum, last-frame) cosine similarity of DRIFT_FRAMES evenly spaced frames to the start image."""
    idx = sorted({round(i * (n_frames - 1) / (DRIFT_FRAMES - 1)) for i in range(DRIFT_FRAMES)})
    emb = np.asarray(embedder([start_image, *decode_rgb_frames(clip, idx, width, height)]), dtype=np.float32)
    emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
    sims = emb[1:] @ emb[0]
    return float(sims.min()), float(sims[-1])


class ClipDecodeError(RuntimeError):
    """The clip could not be read as video."""


@dataclass(slots=True)
class GateReport:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    frames: int = 0
    expected_frames: int = 0
    start_ssim: float | None = None
    end_ssim: float | None = None
    mean_diff: float | None = None
    spike_ratio: float | None = None
    drift_min: float | None = None
    drift_last: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def decode_gray(path: str | Path, width: int, height: int) -> np.ndarray:
    """All frames as float32 (n, h, w), 0-255. Raises `ClipDecodeError`, never returns a partial clip."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={width}:{height}:flags=area,format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ClipDecodeError(f"ffmpeg could not run: {exc}") from exc
    if proc.returncode != 0:
        raise ClipDecodeError(f"ffmpeg failed: {proc.stderr.decode(errors='replace').strip()[:300]}")
    data = np.frombuffer(proc.stdout, dtype=np.uint8)
    size = width * height
    if data.size == 0 or data.size % size:
        raise ClipDecodeError(f"{path}: decoded {data.size} bytes, not a whole number of {width}x{height} frames")
    return data.reshape(-1, height, width).astype(np.float32)


def image_gray(image: Image.Image, width: int, height: int) -> np.ndarray:
    return np.asarray(image.convert("L").resize((width, height), Image.LANCZOS), dtype=np.float32)


def _box_mean(a: np.ndarray, win: int) -> np.ndarray:
    """Mean over every full win x win window, via an integral image (valid region only)."""
    c = np.pad(a.astype(np.float64), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    s = c[win:, win:] - c[:-win, win:] - c[win:, :-win] + c[:-win, :-win]
    return s / (win * win)


def ssim(a: np.ndarray, b: np.ndarray, *, win: int = 7, data_range: float = 255.0) -> float:
    """Mean structural similarity of two greyscale images.

    The standard definition with scikit-image's defaults (uniform 7x7 window, K1=0.01, K2=0.03, sample
    covariance), so values are comparable with the probe's. Needs an image at least `win` px each way.
    """
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch {a.shape} vs {b.shape}")
    if min(a.shape) < win:
        raise ValueError(f"image {a.shape} is smaller than the {win}px window")
    c1, c2 = (0.01 * data_range) ** 2, (0.03 * data_range) ** 2
    n = win * win
    cov_norm = n / (n - 1)
    ma, mb = _box_mean(a, win), _box_mean(b, win)
    va = cov_norm * (_box_mean(a * a, win) - ma * ma)
    vb = cov_norm * (_box_mean(b * b, win) - mb * mb)
    vab = cov_norm * (_box_mean(a * b, win) - ma * mb)
    s = ((2 * ma * mb + c1) * (2 * vab + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2))
    return float(s.mean())


def temporal_stats(frames: np.ndarray) -> tuple[float, float]:
    """(mean consecutive-frame difference, max/mean). A one-frame clip has no motion to measure."""
    if len(frames) < 2:
        return 0.0, 0.0
    d = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    mean = float(d.mean())
    return mean, float(d.max() / mean) if mean > 1e-6 else 0.0


def gate_clip(
    clip: str | Path,
    start_image: Image.Image,
    end_image: Image.Image | None,
    *,
    expected_frames: int,
    width: int,
    height: int,
    embedder: Embedder | None = None,
) -> GateReport:
    """Score one clip. `start_image` / `end_image` are the images the engine was given (already fitted to
    width x height). Any error while scoring is a rejection, including a drift check that cannot run: with no
    `embedder` the gate loads CLIP itself, and if that fails the clip is rejected with the reason."""
    try:
        gw, gh = width, height
        frames = decode_gray(clip, gw, gh)
        report = GateReport(passed=False, frames=len(frames), expected_frames=expected_frames)
        if len(frames) != expected_frames:
            report.reasons.append(f"length: {len(frames)} frames, asked for {expected_frames}")
        report.start_ssim = round(ssim(frames[0], image_gray(start_image, gw, gh)), 4)
        if report.start_ssim < MIN_START_SSIM:
            report.reasons.append(f"start frame: ssim {report.start_ssim} < {MIN_START_SSIM}")
        if end_image is not None:
            report.end_ssim = round(ssim(frames[-1], image_gray(end_image, gw, gh)), 4)
            if report.end_ssim < MIN_END_SSIM:
                report.reasons.append(f"end frame: ssim {report.end_ssim} < {MIN_END_SSIM}")
        mean, spike = temporal_stats(frames)
        report.mean_diff, report.spike_ratio = round(mean, 3), round(spike, 3)
        if mean < MIN_MOTION:
            report.reasons.append(f"still: mean frame difference {mean:.2f} < {MIN_MOTION}")
        if spike > MAX_SPIKE_RATIO:
            report.reasons.append(f"jump: spike ratio {spike:.2f} > {MAX_SPIKE_RATIO}")
        try:
            owned = embedder is None
            emb = ClipImageEmbedder() if owned else embedder
            try:
                report.drift_min, report.drift_last = (round(v, 4) for v in drift_scores(
                    clip, start_image, len(frames), gw, gh, emb))
            finally:
                if owned:
                    emb.close()
            if report.drift_min < MIN_DRIFT_SIM:
                report.reasons.append(f"content drift: clip similarity {report.drift_min} < {MIN_DRIFT_SIM}")
        except Exception as exc:
            report.reasons.append(f"drift check cannot run: {type(exc).__name__}: {exc}")
        report.passed = not report.reasons
        return report
    except Exception as exc:
        return GateReport(
            passed=False, expected_frames=expected_frames,
            reasons=[f"gate could not run: {type(exc).__name__}: {exc}"],
        )
