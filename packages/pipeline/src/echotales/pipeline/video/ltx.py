"""LTX-2.5 Video Engine for atmospheric B-roll, landscape shots, and continuous montages."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from echotales.pipeline.workers_contract import VideoWorkerRequest, VideoWorkerResponse, run_video_worker


@dataclass(slots=True)
class LTXVideoResult:
    """The result of an LTX-2.5 video generation."""

    video_path: str
    duration_s: float
    fps: int
    num_frames: int
    status: str = "COMPLETED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_path": self.video_path,
            "duration_s": round(self.duration_s, 3),
            "fps": self.fps,
            "num_frames": self.num_frames,
            "status": self.status,
        }


def generate_ltx_video(
    prompt: str,
    output_path: str | Path,
    *,
    keyframe_path: str | Path | None = None,
    num_frames: int = 97,
    fps: int = 24,
    run_worker: Callable[[VideoWorkerRequest], VideoWorkerResponse] = run_video_worker,
) -> LTXVideoResult:
    """Generate ambient B-roll or multi-shot sequence using LTX-2.5."""
    kf_b64 = None
    if keyframe_path is not None:
        p = Path(keyframe_path)
        if p.exists():
            kf_b64 = base64.b64encode(p.read_bytes()).decode("ascii")

    req = VideoWorkerRequest(
        keyframe_b64=kf_b64 or "",
        prompt=prompt,
        num_frames=num_frames,
        fps=fps,
        mode="animate",
    )
    resp = run_worker(req)

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_bytes(resp.video_bytes)

    return LTXVideoResult(
        video_path=str(out_p),
        duration_s=resp.duration_s,
        fps=fps,
        num_frames=num_frames,
        status=resp.status,
    )
