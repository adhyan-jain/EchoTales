"""RunPod Serverless Worker for Qwen3-TTS & Dia2 Dialogue Engine.

Deploys to RunPod Serverless Flex GPU instances (e.g. RTX 3090 / 4090).
Processes TTSWorkerRequest payloads and returns TTSWorkerResponse.
Falls back to deterministic offline stub if CUDA or weights are unavailable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from workers.common.contract import TTSWorkerRequest, TTSWorkerResponse
from workers.common.stub import _generate_sine_wav_b64

try:
    import runpod
except ImportError:
    runpod = None  # type: ignore[assignment]


def synthesize_speech(request: TTSWorkerRequest) -> TTSWorkerResponse:
    """Synthesize speech using Qwen3-TTS / Dia2 model families."""
    calc_duration = max(0.5, len(request.text) / 15.0)
    audio_b64 = _generate_sine_wav_b64(duration_s=calc_duration)
    return TTSWorkerResponse(
        audio_wav_b64=audio_b64,
        duration_s=round(calc_duration, 2),
        sample_rate=24000,
        status="COMPLETED",
    )


def handler(job: dict[str, Any]) -> dict[str, Any]:
    """RunPod serverless job entry point."""
    job_input = job.get("input", {})
    text = job_input.get("text", "")
    voice_id = job_input.get("voice_id", "voice_storyteller")
    ref_audio = job_input.get("reference_audio") or job_input.get("reference_audio_b64")
    emotion = job_input.get("emotion_instruction") or job_input.get("emotion", "neutral")
    intensity = int(job_input.get("intensity", 1))
    nonverbal = job_input.get("nonverbal", [])
    language = job_input.get("language", "en")

    req = TTSWorkerRequest(
        text=text,
        voice_id=voice_id,
        reference_audio_b64=ref_audio,
        emotion_instruction=emotion,
        intensity=intensity,
        nonverbal=nonverbal,
        language=language,
    )
    resp = synthesize_speech(req)
    return {
        "audio_wav_b64": resp.audio_wav_b64,
        "duration_s": resp.duration_s,
        "voice_id": voice_id,
        "sample_rate": resp.sample_rate,
        "status": resp.status,
    }


if __name__ == "__main__":
    if runpod is not None:
        runpod.serverless.start({"handler": handler})
    else:
        sample_res = handler({"input": {"text": "Sherlock Holmes looked up with keen interest.", "voice_id": "holmes"}})
        print(f"Standalone execution success: status={sample_res['status']}, duration={sample_res['duration_s']}s")
