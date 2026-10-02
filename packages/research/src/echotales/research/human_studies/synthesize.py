"""Render stimulus scripts to audio with the product's own TTS engine.

Uses `pipeline/voice/engine.py` unchanged (same Chatterbox wrapper, same PCM16
write the product depends on), so a stimulus sounds exactly like EchoTales
output. Segments are cached by (voice, text): across a factorial most
segments recur -- every narration line, and every correctly attributed quote
-- so the number of TTS calls is the number of *distinct* (voice, text) pairs,
not segments x conditions.
"""

from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path

from echotales.pipeline.paths import VOICE_BANK_DIR
from echotales.pipeline.voice.engine import SynthesisRequest, get_engine

#: Silence between segments. Long enough to mark a turn, short enough that a
#: listener hears one continuous passage rather than a list of clips.
GAP_SECONDS = 0.35


def _clip_for(voice_id: str) -> Path | None:
    # EARS ids are "ears<speaker dir>"; reference = that speaker's neutral read.
    d = VOICE_BANK_DIR / "ears" / voice_id.removeprefix("ears")
    clip = d / "emo_neutral_sentences.wav"
    return clip if clip.exists() else None


def _concat(parts: list[Path], out: Path, gap: float = GAP_SECONDS) -> None:
    with wave.open(str(parts[0]), "rb") as first:
        params = first.getparams()
    silence = b"\x00\x00" * int(params.framerate * gap) * params.nchannels
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setparams(params)
        for i, p in enumerate(parts):
            with wave.open(str(p), "rb") as r:
                w.writeframes(r.readframes(r.getnframes()))
            if i < len(parts) - 1:
                w.writeframes(silence)


def synthesize_stimuli(manifest: Path, out_dir: Path, *, engine: str = "chatterbox",
                       only: set[str] | None = None) -> str:
    data = json.loads(Path(manifest).read_text())
    tts = get_engine(engine)
    seg_dir = out_dir / "segments"
    calls = 0
    for st in data["stimuli"]:
        if only and st["id"] not in only:
            continue
        parts = []
        for seg in st["script"]:
            key = hashlib.sha256(f"{seg['voice']}|{seg['text']}".encode()).hexdigest()[:16]
            path = seg_dir / f"{key}.wav"
            if not path.exists():
                tts.synthesize(SynthesisRequest(text=seg["text"], out_path=path,
                                                reference_clip=_clip_for(seg["voice"])))
                calls += 1
            parts.append(path)
        _concat(parts, out_dir / f"{st['id']}.wav")
    return f"{calls} TTS calls ({engine}) -> {out_dir}"
