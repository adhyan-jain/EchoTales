from typing import Protocol

from echotales.pipeline.video.ltx import (
    LTXVideoResult,
    generate_ltx_video,
)
from echotales.pipeline.video.qa import (
    VideoQAGate,
    VideoQAReport,
    render_shot_with_video_or_fallback,
)
from echotales.pipeline.video.wan import (
    WanMode,
    WanVideoResult,
    generate_wan_s2v_dialogue,
    generate_wan_video,
)
from echotales.pipeline.workers_contract import (
    VideoWorkerRequest,
    VideoWorkerResponse,
    run_video_worker,
)


class VideoEngine(Protocol):
    """Abstract capability interface for video generation backends (docs/design/architecture.md Section 8)."""

    def generate(self, req: VideoWorkerRequest) -> VideoWorkerResponse: ...


class WanVideoEngine:
    """Wan 2.2 S2V / A14B video generation engine."""

    def generate(self, req: VideoWorkerRequest) -> VideoWorkerResponse:
        return run_video_worker(req)


class LTXVideoEngine:
    """LTX-2.5 landscape / ambient video generation engine."""

    def generate(self, req: VideoWorkerRequest) -> VideoWorkerResponse:
        return run_video_worker(req)


class StubVideoEngine:
    """Deterministic offline video generation engine."""

    def generate(self, req: VideoWorkerRequest) -> VideoWorkerResponse:
        return run_video_worker(req)


def get_video_engine(name: str = "stub") -> VideoEngine:
    """Factory selecting video engine backend by capability rather than vendor."""
    normalized = name.lower().strip()
    if normalized == "wan":
        return WanVideoEngine()
    if normalized == "ltx":
        return LTXVideoEngine()
    return StubVideoEngine()


__all__ = [
    "LTXVideoResult",
    "VideoEngine",
    "VideoQAGate",
    "VideoQAReport",
    "WanMode",
    "WanVideoEngine",
    "LTXVideoEngine",
    "StubVideoEngine",
    "WanVideoResult",
    "generate_ltx_video",
    "generate_wan_s2v_dialogue",
    "generate_wan_video",
    "get_video_engine",
    "render_shot_with_video_or_fallback",
]
