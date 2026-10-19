"""Dia2 Expressive Dialogue Client.

Specializes in natural conversational dialogue synthesis with embedded non-verbal
actions (gasps, sighs, chuckles, interruptions, and coughs).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from echotales.pipeline.voice.qwen_tts import TTSResult
from workers.common.contract import TTSWorkerRequest, TTSWorkerResponse
from workers.common.stub import run_tts_worker

VALID_NONVERBAL_TAGS = {"gasp", "sigh", "chuckle", "laughter", "cough", "groan", "sob", "shout"}


def format_dia2_dialogue_text(text: str, nonverbal: list[str]) -> str:
    """Embed non-verbal action tags into dialogue text appropriately."""
    if not nonverbal:
        return text.strip()

    valid_tags = [tag.lower() for tag in nonverbal if tag.lower() in VALID_NONVERBAL_TAGS]
    if not valid_tags:
        return text.strip()

    # Prepend primary nonverbal cue or wrap appropriately
    primary = valid_tags[0]
    return f"[{primary}] {text.strip()}"


def synthesize_dia2(
    text: str,
    voice_id: str,
    *,
    nonverbal: list[str] | None = None,
    intensity: int = 1,
    language: str = "en",
    output_path: Path | str | None = None,
    run_worker: Callable[[TTSWorkerRequest], TTSWorkerResponse] = run_tts_worker,
) -> TTSResult:
    """Synthesize expressive dialogue using Dia2 specification."""
    nonverbal_list = list(nonverbal or [])
    formatted_text = format_dia2_dialogue_text(text, nonverbal_list)

    req = TTSWorkerRequest(
        text=formatted_text,
        voice_id=voice_id,
        emotion_instruction="natural dramatic conversation",
        intensity=intensity,
        nonverbal=nonverbal_list,
        language=language,
    )
    resp = run_worker(req)

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
        emotion="dialogue",
        intensity=intensity,
    )
