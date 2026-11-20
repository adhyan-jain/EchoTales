"""ElevenLabs text to speech, using the USER's own API key. Optional, never the default, mock-tested only.

Terms and consent: the key is yours (`ECHOTALES_ELEVENLABS_API_KEY`, `.env`), the account's terms and plan limits
apply, and the voice (`ECHOTALES_ELEVENLABS_VOICE_ID`) must be one from the ElevenLabs library or one you recorded or
uploaded yourself with the right to use it. EchoTales does not clone real people, famous voice actors included, and
this engine takes no reference clip: `SynthesisRequest.reference_clip` is ignored on purpose so a stray clip can never
become a clone. Text is sent to ElevenLabs' servers; local-only users should not select this engine.

Each line is recorded in the cloud ledger before it is sent, so the budget hard stop applies here too (the per
character figure is a plan-dependent guess, `ELEVENLABS_USD_PER_1K_CHARS`).
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from echotales.pipeline.cloud_ledger import (  # type: ignore[import-untyped]
    ELEVENLABS_USD_PER_1K_CHARS,
    CloudLedger,
)
from echotales.pipeline.voice.engine import SynthesisRequest  # type: ignore[import-untyped]

API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
SAMPLE_RATE = 24000


@dataclass(slots=True)
class ElevenLabsEngine:
    name: str = "elevenlabs"
    sample_rate: int = SAMPLE_RATE
    api_key: str = ""
    voice_id: str = ""
    model_id: str = "eleven_multilingual_v2"
    ledger: Any = None
    client: httpx.Client | None = None

    def _config(self) -> tuple[str, str]:
        key, voice = self.api_key, self.voice_id
        if not (key and voice):
            from echotales.pipeline.config import get_settings  # type: ignore[import-untyped]

            s = get_settings()
            key, voice = key or s.elevenlabs_api_key, voice or s.elevenlabs_voice_id
        missing = [n for n, v in (("ECHOTALES_ELEVENLABS_API_KEY", key), ("ECHOTALES_ELEVENLABS_VOICE_ID", voice)) if not v]
        if missing:
            raise RuntimeError(f"the elevenlabs engine needs {', '.join(missing)}; set them in .env (gitignored)")
        return key, voice

    def synthesize(self, request: SynthesisRequest) -> Path:
        key, voice = self._config()
        if self.ledger is None:
            self.ledger = CloudLedger()
        entry = self.ledger.reserve(
            "elevenlabs", "tts", round(len(request.text) / 1000 * ELEVENLABS_USD_PER_1K_CHARS, 4), voice)
        http = self.client or httpx.Client(timeout=120.0)
        try:
            resp = http.post(
                f"{API_URL}/{voice}", params={"output_format": f"pcm_{self.sample_rate}"},
                headers={"xi-api-key": key}, json={"text": request.text, "model_id": self.model_id})
            if resp.status_code in (401, 403):
                raise RuntimeError("elevenlabs rejected the API key (check ECHOTALES_ELEVENLABS_API_KEY)")
            resp.raise_for_status()
            pcm = resp.content
        except Exception:
            self.ledger.settle(entry, 0.0, "failed")
            raise
        finally:
            if self.client is None:
                http.close()
        self.ledger.settle(entry, None)
        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        # PCM16 mono WAV, the one format `wave` (render/timeline.py, compose.py) can read; see ChatterboxEngine.
        with wave.open(str(request.out_path), "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(self.sample_rate)
            fh.writeframes(pcm)
        return Path(request.out_path)
