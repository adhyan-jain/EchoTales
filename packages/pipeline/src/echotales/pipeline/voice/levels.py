"""Per-line fixes applied while a chapter is voiced: one loudness target, and re-synthesis of a take that is
plainly the wrong length for its text.

Both exist because the first measurement of a real chapter (Lord of the Mysteries ch7, EVOLUTION audio-QA section)
found them: per-voice mean loudness spread over 18 LU (a quiet reference clip gave a character -37 LUFS beside a
-21 LUFS narrator), and a few lines that a speech recogniser heard as "No problem. No problem." or as a one-word line
plus an invented tail. The earlier note in `export.py` that per-line normalisation flattens emotion is true of lines
from *one* voice; the 18 LU was between voices, from reference-clip level, not from delivery.
"""

from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from echotales.pipeline.voice import qa
from echotales.pipeline.voice.engine import SynthesisRequest, TTSEngine

#: Where each line lands. The M4B step later takes the whole book to -18 LUFS, so this is relative headroom.
TARGET_LUFS = -20.0
MAX_GAIN_DB = 18.0
#: Peak ceiling after gain; a line that would exceed it is given less gain, not clipped.
PEAK_CEILING = 0.95
#: Typical Chatterbox speech rate (characters per second of speech) in the first measurement; a retry is judged by
#: distance from it.
EXPECTED_CPS = 16.0
MAX_RETRIES = 2


def normalise_file(path: Path, target_lufs: float = TARGET_LUFS) -> float | None:
    """Rewrite `path` (PCM16) so its integrated loudness is `target_lufs`; return the gain applied in dB.

    A silent file (the stub engine's output) is left alone and returns None.
    """
    import soundfile as sf

    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = x.mean(axis=1)
    current = qa.lufs(mono, sr)
    if current is None:
        return None
    gain_db = max(-MAX_GAIN_DB, min(MAX_GAIN_DB, target_lufs - current))
    peak = float(np.abs(x).max())
    if peak > 0:
        gain_db = min(gain_db, 20 * math.log10(PEAK_CEILING / peak))
    sf.write(str(path), np.clip(x * 10 ** (gain_db / 20), -1.0, 1.0), sr, subtype="PCM_16")
    return gain_db


@dataclass(slots=True)
class TakeResult:
    retries: int = 0
    #: True when the last allowed take was still outside the pace band.
    gave_up: bool = False


def _pace_error(text: str, path: Path) -> float | None:
    """0 for a line at the expected rate, growing with how far the take is from it; None when it cannot be judged."""
    try:
        x, sr = qa.read_mono(path)
    except Exception:  # noqa: BLE001 -- an unreadable file is the stub/other-format case; nothing to judge
        return None
    lead, trail = qa.edge_silence(x, sr)
    cps = qa.speech_rate(text, len(x) / sr - lead - trail)
    return None if cps is None else abs(math.log(cps / EXPECTED_CPS))


def _in_band(text: str, path: Path) -> bool | None:
    x, sr = qa.read_mono(path)
    lead, trail = qa.edge_silence(x, sr)
    cps = qa.speech_rate(text, len(x) / sr - lead - trail)
    return None if cps is None else qa.PACE_BAND[0] <= cps <= qa.PACE_BAND[1]


def synthesize_checked(engine: TTSEngine, request: SynthesisRequest, *, max_retries: int = MAX_RETRIES) -> TakeResult:
    """Synthesise, and re-synthesise up to `max_retries` times while the take's speech rate is outside the band
    (a truncated, repeated or runaway generation), keeping the take closest to the expected rate."""
    engine.synthesize(request)
    result = TakeResult()
    path = request.out_path
    err = _pace_error(request.text, path)
    if err is None or _in_band(request.text, path):
        return result
    best = path.with_suffix(".best.wav")
    shutil.copyfile(path, best)
    best_err = err
    try:
        for _ in range(max_retries):
            result.retries += 1
            engine.synthesize(request)
            e = _pace_error(request.text, path)
            if e is not None and e < best_err:
                best_err = e
                shutil.copyfile(path, best)
            if e is not None and _in_band(request.text, path):
                break
        else:
            result.gave_up = True
        shutil.copyfile(best, path)
    finally:
        best.unlink(missing_ok=True)
    return result
