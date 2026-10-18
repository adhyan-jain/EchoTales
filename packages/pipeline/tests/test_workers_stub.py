"""Tests for RunPod worker contracts and offline stubs."""

from __future__ import annotations

import base64
import wave
import io
import pytest

from workers.common.contract import (
    ImageWorkerRequest,
    TTSWorkerRequest,
    VideoWorkerRequest,
)
from workers.common.stub import (
    StubImageWorker,
    StubTTSWorker,
    StubVideoWorker,
)


def test_stub_image_worker() -> None:
    worker = StubImageWorker()
    req = ImageWorkerRequest(
        prompt="Klein Moretti in Victorian suit holding revolver",
        width=1080,
        height=1920,
    )
    resp = worker(req)
    assert resp.status == "COMPLETED"
    assert resp.seed == 42
    png_bytes = base64.b64decode(resp.image_b64)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_stub_tts_worker() -> None:
    worker = StubTTSWorker()
    req = TTSWorkerRequest(
        text="A bullet... through my head?",
        voice_id="scholar_male",
        emotion_instruction="shocked",
        intensity=3,
        nonverbal=["gasp"],
    )
    resp = worker(req)
    assert resp.status == "COMPLETED"
    assert resp.duration_s > 0.0
    wav_bytes = base64.b64decode(resp.audio_wav_b64)
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 24000
        assert wf.getnframes() > 0


def test_stub_video_worker() -> None:
    worker = StubVideoWorker()
    req = VideoWorkerRequest(
        keyframe_b64="dummy_keyframe",
        num_frames=72,
        fps=24,
        mode="s2v",
    )
    resp = worker(req)
    assert resp.status == "COMPLETED"
    assert resp.duration_s == 3.0
    assert len(resp.video_b64) > 0
