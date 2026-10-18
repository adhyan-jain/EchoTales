"""RunPod Serverless worker request and response contracts.

Each worker family (Image, Video, Voice/TTS, Vision Judge) exposes a consistent
JSON protocol over RunPod's POST /v2/<endpoint>/run polling interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ImageWorkerRequest:
    """Request payload for Qwen-Image-2512 / Qwen-Image-Edit-2511 / Z-Image."""

    prompt: str
    negative_prompt: str = ""
    width: int = 1080
    height: int = 1920
    reference_images_b64: list[str] = field(default_factory=list)  # character sheet, location plate
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


@dataclass(slots=True)
class VideoWorkerRequest:
    """Request payload for Wan 2.2 S2V / A14B and LTX-2.5."""

    keyframe_b64: str
    last_frame_b64: str | None = None
    audio_wav_b64: str | None = None  # for S2V lip-sync
    prompt: str = ""
    num_frames: int = 81
    fps: int = 24
    mode: str = "s2v"  # "s2v" | "i2v" | "first_last" | "animate"

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

    video_b64: str  # mp4 encoded bytes in base64
    duration_s: float
    status: str = "COMPLETED"


@dataclass(slots=True)
class TTSWorkerRequest:
    """Request payload for Qwen3-TTS / Dia2 / Chatterbox Multilingual."""

    text: str
    voice_id: str
    reference_audio_b64: str | None = None
    emotion_instruction: str = "neutral"
    intensity: int = 1  # 0 to 3
    nonverbal: list[str] = field(default_factory=list)
    language: str = "en"  # "en" | "hi"

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
