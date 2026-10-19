"""RunPod Serverless worker request, response, and protocol contracts for EchoTales.

Internal pipeline definition that decouples pipeline modules from root-level workers/.
Exposes typed protocols and offline deterministic stubs for testing and CI.
"""

from __future__ import annotations

import base64
import io
import math
import struct
import wave
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ImageWorkerRequest:
    """Request payload for Qwen-Image-2512 / Qwen-Image-Edit-2511 / Z-Image."""

    prompt: str
    negative_prompt: str = ""
    width: int = 1080
    height: int = 1920
    reference_images_b64: list[str] = field(default_factory=list)
    seed: int = 42
    steps: int = 25
    guidance_scale: float = 6.0
    model_family: str = "qwen-image-edit"

    def to_input_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "width": self.width,
            "height": self.height,
            "references": self.reference_images_b64,
            "seed": self.seed,
            "steps": self.steps,
            "guidance_scale": self.guidance_scale,
            "model_family": self.model_family,
        }


@dataclass(slots=True)
class ImageWorkerResponse:
    """Completed image generation payload."""

    image_b64: str
    seed: int
    duration_s: float = 0.0
    status: str = "COMPLETED"

    @property
    def image_bytes(self) -> bytes:
        return base64.b64decode(self.image_b64)


@dataclass(slots=True)
class VideoWorkerRequest:
    """Request payload for Wan 2.2 S2V / A14B and LTX-2.5."""

    keyframe_b64: str
    last_frame_b64: str | None = None
    audio_wav_b64: str | None = None
    prompt: str = ""
    num_frames: int = 81
    fps: int = 24
    mode: str = "s2v"

    def to_input_dict(self) -> dict[str, Any]:
        return {
            "keyframe": self.keyframe_b64,
            "last_frame": self.last_frame_b64,
            "audio": self.audio_wav_b64,
            "prompt": self.prompt,
            "num_frames": self.num_frames,
            "fps": self.fps,
            "mode": self.mode,
        }


@dataclass(slots=True)
class VideoWorkerResponse:
    """Completed video generation payload."""

    video_b64: str
    duration_s: float
    status: str = "COMPLETED"

    @property
    def video_bytes(self) -> bytes:
        return base64.b64decode(self.video_b64)


@dataclass(slots=True)
class TTSWorkerRequest:
    """Request payload for Qwen3-TTS / Dia2 dialogue synthesis."""

    text: str
    voice_id: str
    reference_audio_b64: str | None = None
    emotion_instruction: str = "neutral"
    intensity: int = 1
    nonverbal: list[str] = field(default_factory=list)
    language: str = "en"

    def to_input_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "voice_id": self.voice_id,
            "reference_audio": self.reference_audio_b64,
            "emotion_instruction": self.emotion_instruction,
            "intensity": self.intensity,
            "nonverbal": list(self.nonverbal),
            "language": self.language,
        }


@dataclass(slots=True)
class TTSWorkerResponse:
    """Completed speech synthesis payload."""

    audio_wav_b64: str
    duration_s: float
    sample_rate: int = 24000
    status: str = "COMPLETED"

    @property
    def audio_bytes(self) -> bytes:
        return base64.b64decode(self.audio_wav_b64)


class ImageEngineProtocol(Protocol):
    """Protocol for image generator backends."""

    def generate(self, req: ImageWorkerRequest) -> ImageWorkerResponse: ...


class VideoEngineProtocol(Protocol):
    """Protocol for video generator backends."""

    def generate(self, req: VideoWorkerRequest) -> VideoWorkerResponse: ...


class TTSEngineProtocol(Protocol):
    """Protocol for speech/TTS generator backends."""

    def synthesize(self, req: TTSWorkerRequest) -> TTSWorkerResponse: ...


def _generate_solid_png_b64(width: int = 1080, height: int = 1920, color: tuple[int, int, int] = (40, 44, 52)) -> str:
    """Generate a minimal valid PNG using pure Python stdlib."""
    import zlib

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


def _generate_stub_mp4_b64(duration_s: float = 3.0) -> str:
    """Generate a valid minimal MP4 container using stdlib struct."""
    buf = io.BytesIO()

    def _box(box_type: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload) + 8) + box_type + payload

    ftyp = _box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2avc1mp41")
    mvhd = _box(
        b"mvhd",
        struct.pack(">BBBB", 0, 0, 0, 0)
        + struct.pack(">IIII", 0, 0, 1000, int(duration_s * 1000))
        + struct.pack(">I", 0x00010000)
        + struct.pack(">H", 0x0100)
        + b"\x00" * 10
        + struct.pack(">IIIIII", 0x00010000, 0, 0, 0, 0x00010000, 0)
        + struct.pack(">III", 0, 0, 0x40000000)
        + b"\x00" * 24
        + struct.pack(">I", 2),
    )
    moov = _box(b"moov", mvhd)
    mdat = _box(b"mdat", b"\x00" * 64)

    buf.write(ftyp + moov + mdat)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def run_image_worker(req: ImageWorkerRequest) -> ImageWorkerResponse:
    """Deterministic offline stub image worker."""
    b64 = _generate_solid_png_b64(req.width, req.height)
    return ImageWorkerResponse(image_b64=b64, seed=req.seed, duration_s=1.2, status="COMPLETED")


def run_video_worker(req: VideoWorkerRequest) -> VideoWorkerResponse:
    """Deterministic offline stub video worker."""
    dur = float(req.num_frames) / float(req.fps)
    b64 = _generate_stub_mp4_b64(dur)
    return VideoWorkerResponse(video_b64=b64, duration_s=dur, status="COMPLETED")


def run_tts_worker(req: TTSWorkerRequest) -> TTSWorkerResponse:
    """Deterministic offline stub speech worker."""
    word_count = max(1, len(req.text.split()))
    dur = max(0.5, word_count * 0.28)
    b64 = _generate_sine_wav_b64(dur)
    return TTSWorkerResponse(audio_wav_b64=b64, duration_s=dur, sample_rate=24000, status="COMPLETED")
