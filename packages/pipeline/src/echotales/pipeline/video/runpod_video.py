"""Image-to-video on a RunPod serverless worker (Wan 2.2 / AniSora class). Optional, off by default, mock-tested only.

Selected as `wan-runpod` in the registry (surface `cloud-video`, so it never appears in the local `anime --engine`
choices). Needs `ECHOTALES_RUNPOD_API_KEY` and `ECHOTALES_RUNPOD_VIDEO_ENDPOINT`; every submit goes through the cloud
ledger (`cloud_ledger.py`) and is refused before sending if it would pass the budget.

Worker contract (the owner's handler must speak it; nothing is deployed yet):
    request   {"input": workers_contract.VideoWorkerRequest.to_input_dict() + {"model": "wan2.2-i2v"}}
    response  {"status": "COMPLETED", "output": {"video": "<b64 mp4>", "duration_s": <float>}}
"""

from __future__ import annotations

from typing import Any

from echotales.pipeline import cloud_ledger, workers_contract
from echotales.pipeline.render.runpod import RunPodClient


class RunPodVideoEngine:
    name = "wan-runpod"

    def __init__(self, client: RunPodClient | None = None) -> None:
        self.client = client or RunPodClient.from_settings("runpod_video_endpoint", "ECHOTALES_RUNPOD_VIDEO_ENDPOINT")

    @staticmethod
    def estimate_usd(clips: int = 1) -> float:
        return float(cloud_ledger.estimate_job_usd("video", clips))

    def generate(self, req: workers_contract.VideoWorkerRequest) -> workers_contract.VideoWorkerResponse:
        payload: dict[str, Any] = {**req.to_input_dict(), "model": "wan2.2-i2v"}
        job = self.client.submit(payload, kind="video", estimated_usd=self.estimate_usd(), note=f"{req.num_frames}f")
        state = self.client.wait(job)
        out = state.get("output")
        video = out.get("video") if isinstance(out, dict) else None
        if not isinstance(video, str) or not video:
            raise RuntimeError(f"runpod video job {job.job_id} completed with no video in its output")
        duration = float(out.get("duration_s") or req.num_frames / max(1, req.fps))
        return workers_contract.VideoWorkerResponse(video_b64=video, duration_s=duration)

    def cancel(self, job: Any) -> None:
        self.client.cancel(job)
