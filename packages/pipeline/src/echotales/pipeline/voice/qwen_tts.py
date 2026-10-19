"""Qwen3-TTS client with natural emotion instruction compiler.

Interfaces with RunPod Qwen3-TTS worker contract to generate expressive,
natural dialogue and narrative speech across emotion and intensity spectra.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from echotales.pipeline.workers_contract import TTSWorkerRequest, TTSWorkerResponse, run_tts_worker


@dataclass(slots=True)
class TTSResult:
    """The result of speech synthesis."""

    audio_bytes: bytes
    duration_s: float
    sample_rate: int = 24000
    path: str | None = None
    voice_id: str = ""
    emotion: str = "neutral"
    intensity: int = 1


def build_emotion_instruction(emotion: str, intensity: int = 1) -> str:
    """Compile natural language performance instruction for Qwen3-TTS."""
    clean_emotion = emotion.strip().lower()

    if intensity <= 0:
        return "speak in a flat, monotone, emotionless voice"

    instructions = {
        "neutral": {
            1: "speak naturally with balanced cadence and clear diction",
            2: "speak with focused intent and measured pace",
            3: "speak with solemn, resonant gravity",
        },
        "angry": {
            1: "speak with sharp irritation and clipped consonants",
            2: "speak with venomous anger, tense jaw, and biting emphasis",
            3: "shout with explosive fury, maximum volume, and ragged rage",
        },
        "shocked": {
            1: "speak with mild surprise, pitch rising slightly",
            2: "speak with breathless astonishment and stunned hesitation",
            3: "shout with wide-eyed terror and gasping shock",
        },
        "fearful": {
            1: "speak with nervous hesitation and rapid pace",
            2: "speak with trembling anxiety and shallow breaths",
            3: "whisper in terrified panic, voice cracking with horror",
        },
        "crying": {
            1: "speak with subtle sorrow and downturned inflection",
            2: "speak with a cracking voice, choked with rising tears",
            3: "sob brokenly, gasping between tearful words",
        },
        "smirking": {
            1: "speak with a slight hint of amusement",
            2: "speak with arrogant condescension and dry amusement",
            3: "laugh haughtily while delivering sharp mockery",
        },
        "shouting": {
            1: "speak loudly with strong vocal projection",
            2: "shout with commanding authority across distance",
            3: "scream at the top of lungs with desperate urgency",
        },
        "in_pain": {
            1: "speak through gritted teeth with mild discomfort",
            2: "groan in acute pain with strained breathing",
            3: "screaming in agony, ragged and agonized gasps",
        },
    }

    bucket = instructions.get(clean_emotion, instructions["neutral"])
    clamped_intensity = max(1, min(3, intensity))
    return bucket.get(clamped_intensity, "speak naturally with clear diction")


def save_tts_response(
    resp: TTSWorkerResponse,
    voice_id: str,
    emotion: str,
    intensity: int,
    output_path: Path | str | None = None,
) -> TTSResult:
    """Save synthesized audio bytes to file if requested and return TTSResult."""
    out_file = None
    if output_path is not None:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(resp.audio_bytes)
        out_file = str(p)

    return TTSResult(
        audio_bytes=resp.audio_bytes,
        duration_s=resp.duration_s,
        sample_rate=resp.sample_rate,
        path=out_file,
        voice_id=voice_id,
        emotion=emotion,
        intensity=intensity,
    )


def synthesize_qwen_tts(
    text: str,
    voice_id: str,
    *,
    emotion: str = "neutral",
    intensity: int = 1,
    language: str = "en",
    reference_audio_b64: str | None = None,
    output_path: Path | str | None = None,
    run_worker: Callable[[TTSWorkerRequest], TTSWorkerResponse] = run_tts_worker,
) -> TTSResult:
    """Synthesize speech using Qwen3-TTS contract with natural emotion instructions."""
    instruction = build_emotion_instruction(emotion, intensity)

    req = TTSWorkerRequest(
        text=text,
        voice_id=voice_id,
        reference_audio_b64=reference_audio_b64,
        emotion_instruction=instruction,
        intensity=intensity,
        language=language,
    )
    resp = run_worker(req)
    return save_tts_response(resp, voice_id, emotion, intensity, output_path)
