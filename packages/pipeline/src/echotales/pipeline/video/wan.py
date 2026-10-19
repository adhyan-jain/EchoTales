"""Wan 2.2 Video Engine integration (S2V, A14B, and First-and-Last-Frame modes).

Enables:
1. Wan 2.2 S2V (Sound-to-Video): Audio-driven natural lip-sync on seed keyframes.
2. Wan 2.2 A14B + LightX2V: High-efficiency image-to-video for ambient & establishing scenes.
3. Wan 2.2 First-and-Last-Frame: Seamless interpolation between key narrative anchors.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from workers.common.contract import VideoWorkerRequest, VideoWorkerResponse
from workers.common.stub import run_video_worker


class WanMode(StrEnum):
    """Wan 2.2 generation pipeline mode."""

    S2V = "s2v"  # Audio-driven lip sync
    I2V = "i2v"  # Ambient image-to-video
    FIRST_LAST = "first_last"  # Bounded interpolation between two frames
    ANIMATE = "animate"  # Dynamic camera animation


@dataclass(slots=True)
class WanVideoResult:
    """The result of a Wan 2.2 video render."""

    video_path: str
    duration_s: float
    fps: int
    num_frames: int
    mode: WanMode
    status: str = "COMPLETED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_path": self.video_path,
            "duration_s": round(self.duration_s, 3),
            "fps": self.fps,
            "num_frames": self.num_frames,
            "mode": str(self.mode),
            "status": self.status,
        }


def _file_to_b64(path: str | Path | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return base64.b64encode(p.read_bytes()).decode("ascii")


def generate_wan_video(
    keyframe_path: str | Path,
    output_path: str | Path,
    *,
    prompt: str = "",
    mode: WanMode = WanMode.I2V,
    last_frame_path: str | Path | None = None,
    audio_path: str | Path | None = None,
    num_frames: int = 81,
    fps: int = 24,
    run_worker: Callable[[VideoWorkerRequest], VideoWorkerResponse] = run_video_worker,
) -> WanVideoResult:
    """Generate AI video clip via Wan 2.2 worker contract."""
    kf_b64 = _file_to_b64(keyframe_path)
    if not kf_b64:
        raise FileNotFoundError(f"Keyframe not found: {keyframe_path}")

    last_b64 = _file_to_b64(last_frame_path)
    audio_b64 = _file_to_b64(audio_path)

    req = VideoWorkerRequest(
        keyframe_b64=kf_b64,
        last_frame_b64=last_b64,
        audio_wav_b64=audio_b64,
        prompt=prompt,
        num_frames=num_frames,
        fps=fps,
        mode=str(mode),
    )
    resp = run_worker(req)

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_bytes(resp.video_bytes)

    return WanVideoResult(
        video_path=str(out_p),
        duration_s=resp.duration_s,
        fps=fps,
        num_frames=num_frames,
        mode=mode,
        status=resp.status,
    )


def generate_wan_s2v_dialogue(
    keyframe_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
    *,
    prompt: str = "character speaking expressively with accurate lip sync",
    fps: int = 24,
    run_worker: Callable[[VideoWorkerRequest], VideoWorkerResponse] = run_video_worker,
) -> WanVideoResult:
    """Synthesize audio-driven talking keyframe video using Wan 2.2 S2V."""
    # Estimate frame count based on audio duration if available
    audio_p = Path(audio_path)
    if not audio_p.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Determine frame count from audio file
    import wave

    try:
        with wave.open(str(audio_p), "rb") as wf:
            dur = wf.getnframes() / float(wf.getframerate())
    except Exception:
        dur = 3.5

    num_frames = max(24, int(round(dur * fps)))

    return generate_wan_video(
        keyframe_path=keyframe_path,
        output_path=output_path,
        prompt=prompt,
        mode=WanMode.S2V,
        audio_path=audio_path,
        num_frames=num_frames,
        fps=fps,
        run_worker=run_worker,
    )
