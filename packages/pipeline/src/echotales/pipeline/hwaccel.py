"""Where heavy work runs: the CUDA device for models, and the NVENC encoder for video.

The owner's rule (2026-11-22): every heavy task runs on the GPU (RTX 4060, 8 GB); the CPU is for work that is extremely
light and will not spike its use. Two decisions were scattered and wrong before this module:

  * `libx264` was hard-coded in the ffmpeg calls, and the stills-to-video step (one ffmpeg call per shot, no `-c:v`, so
    ffmpeg's default libx264) pinned every core for the length of a chapter render. The machine's ffmpeg has
    `h264_nvenc`; `h264_args` picks it when an actual encode works, and libx264 otherwise.
  * `voice/qa.py` loaded whisper with `device="cpu"` so the check "never competes for the GPU". Jobs run one at a time,
    so there is no one to compete with; `pick_device` puts it on CUDA when there is one.

A listed encoder is not enough to trust NVENC: an ffmpeg built with it still fails on a box with no NVIDIA driver or with
the encode sessions used up, and that would surface as a chapter render dying at the first shot. So the probe encodes one
tiny frame, and the answer is cached for the process.

`ECHOTALES_VIDEO_ENCODER=libx264` forces the CPU encoder (a bit-comparable run, or an NVENC fault); unset leaves the
probe in charge.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess

NVENC = "h264_nvenc"
LIBX264 = "libx264"


def cuda_available() -> bool:
    """True when torch is importable and sees a CUDA device. Never raises: no torch means no CUDA here."""
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # a missing or broken torch is "no GPU", not a crash in a light code path
        return False


def pick_device(requested: str | None = None) -> str:
    """`requested` when given and usable, else cuda when available, else cpu.

    An explicit `cpu` is honoured (a test, or a caller that knows better); an explicit `cuda*` with no CUDA falls back to
    cpu instead of dying inside the model loader with a driver error."""
    if requested and requested != "auto":
        if requested.startswith("cuda") and not cuda_available():
            return "cpu"
        return requested
    return "cuda" if cuda_available() else "cpu"


def free_cuda_cache() -> None:
    """Return a finished model's VRAM to the card. Safe without torch or CUDA."""
    try:
        import gc

        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


@functools.lru_cache(maxsize=1)
def video_encoder() -> str:
    """`h264_nvenc` when ffmpeg can really encode with it right now, else `libx264`. Probed once per process."""
    forced = os.environ.get("ECHOTALES_VIDEO_ENCODER", "").strip().lower()
    if forced == LIBX264 or shutil.which("ffmpeg") is None:
        return LIBX264
    try:
        probe = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
             "-frames:v", "1", "-c:v", NVENC, "-f", "null", "-"],
            capture_output=True, timeout=20,
        )
    except (subprocess.SubprocessError, OSError):
        return LIBX264
    return NVENC if probe.returncode == 0 else LIBX264


def h264_args(*, crf: int = 20, preset: str = "medium") -> list[str]:
    """ffmpeg output arguments for H.264 at roughly constant quality, yuv420p so every player opens it.

    NVENC: `-rc vbr -cq 19 -b:v 0` is its constant-quality mode (`-b:v 0` is what stops it capping at the default
    bitrate), preset p5 the slow-and-good end of the fast presets. `preset` is an x264 name and means nothing to NVENC."""
    if video_encoder() == NVENC:
        return ["-c:v", NVENC, "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", LIBX264, "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p"]
