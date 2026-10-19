"""Offline deterministic stubs for all RunPod model workers.

Allows CI and local dev machines to test end-to-end pipelines without GPUs or network calls.
"""

from __future__ import annotations

import base64
import io
import math
import struct
import wave

from workers.common.contract import (
    ImageWorkerRequest,
    ImageWorkerResponse,
    TTSWorkerRequest,
    TTSWorkerResponse,
    VideoWorkerRequest,
    VideoWorkerResponse,
)


def _generate_solid_png_b64(width: int = 1080, height: int = 1920, color: tuple[int, int, int] = (40, 44, 52)) -> str:
    """Generate a minimal valid PNG using pure Python stdlib (no PIL/cv2 required)."""
    import zlib

    # Minimal uncompressed/deflated raw RGBA PNG
    r, g, b = color
    row_bytes = bytes([0] + [r, g, b, 255] * width)
    raw_data = row_bytes * height
    compressed = zlib.compress(raw_data)

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return length + chunk_type + data + crc

    png_header = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)
    idat = _chunk(b"IDAT", compressed)
    iend = _chunk(b"IEND", b"")

    png_bytes = png_header + ihdr + idat + iend
    return base64.b64encode(png_bytes).decode("ascii")


def _generate_sine_wav_b64(duration_s: float = 2.0, sample_rate: int = 24000, freq: float = 440.0) -> str:
    """Generate a valid WAV audio file using stdlib wave and math."""
    num_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = []
        for i in range(num_samples):
            val = int(16000.0 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
            frames.append(struct.pack("<h", val))
        wf.writeframes(b"".join(frames))
    return base64.b64encode(buf.getvalue()).decode("ascii")


class StubImageWorker:
    """Offline deterministic image generator stub."""

    def __call__(self, request: ImageWorkerRequest) -> ImageWorkerResponse:
        b64 = _generate_solid_png_b64(request.width, request.height)
        return ImageWorkerResponse(
            image_b64=b64,
            seed=request.seed,
            duration_s=0.05,
            status="COMPLETED",
        )


class StubTTSWorker:
    """Offline deterministic speech synthesis stub."""

    def __call__(self, request: TTSWorkerRequest) -> TTSWorkerResponse:
        # Pacing: ~15 characters per second
        char_count = max(len(request.text), 10)
        dur = max(1.0, char_count / 15.0)
        b64 = _generate_sine_wav_b64(duration_s=dur)
        return TTSWorkerResponse(
            audio_wav_b64=b64,
            duration_s=dur,
            sample_rate=24000,
            status="COMPLETED",
        )


class StubVideoWorker:
    """Offline deterministic video generator stub."""

    def __call__(self, request: VideoWorkerRequest) -> VideoWorkerResponse:
        dur = request.num_frames / float(request.fps)
        # Dummy base64 payload representing mp4
        dummy_mp4_bytes = b"ftypisom" + b"\x00" * 128
        return VideoWorkerResponse(
            video_b64=base64.b64encode(dummy_mp4_bytes).decode("ascii"),
            duration_s=dur,
            status="COMPLETED",
        )


_default_image_stub = StubImageWorker()
_default_tts_stub = StubTTSWorker()
_default_video_stub = StubVideoWorker()


def run_image_worker(request: ImageWorkerRequest) -> ImageWorkerResponse:
    """Run image generation request through deterministic offline stub."""
    return _default_image_stub(request)


def run_tts_worker(request: TTSWorkerRequest) -> TTSWorkerResponse:
    """Run TTS request through deterministic offline stub."""
    return _default_tts_stub(request)


def run_video_worker(request: VideoWorkerRequest) -> VideoWorkerResponse:
    """Run video generation request through deterministic offline stub."""
    return _default_video_stub(request)

