"""Post-synthesis pitch shift, duration-preserving.

Neither Chatterbox nor VCTK expose age as a controllable dial (`engine.py`,
`bank.py`'s own docstrings). This is the lever for the gap: casting picks
the closest voice the bank actually has, and this shifts its *reading*
toward older/more authoritative or younger, independent of exaggeration/
cfg_weight (see `delivery.py::DeliverySettings.pitch_semitones`).

Uses ffmpeg's `rubberband` filter rather than the classic
`asetrate`+`atempo` trick: `asetrate` changes pitch by changing playback
speed, so preserving duration needs a compensating `atempo`, and `atempo`
itself measurably degrades quality past a semitone or two. `rubberband`
shifts pitch directly, at a real (if larger) CPU cost per line -- affordable
here since this runs after synthesis, not per-candidate during casting.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_HAS_FFMPEG: bool | None = None


def ffmpeg_available() -> bool:
    global _HAS_FFMPEG
    if _HAS_FFMPEG is None:
        _HAS_FFMPEG = shutil.which("ffmpeg") is not None
    return _HAS_FFMPEG


_HAS_RUBBERBAND: bool | None = None


def rubberband_available() -> bool:
    """Whether this ffmpeg build has the `rubberband` filter (needs --enable-librubberband). Checked, not assumed:
    a build without it makes every rubberband call exit non-zero, which the old code read as 'try atempo' only when
    a tempo was also requested and otherwise dropped the pitch shift without saying so."""
    global _HAS_RUBBERBAND
    if _HAS_RUBBERBAND is None:
        if not ffmpeg_available():
            return False
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
        _HAS_RUBBERBAND = " rubberband " in out.stdout
    return _HAS_RUBBERBAND


def _run_filter(path: Path, tmp: Path, expr: str) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-af", expr, str(tmp)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and tmp.exists()


def modulate_prosody(path: Path, semitones: float = 0.0, tempo: float = 1.0) -> None:
    """Shift pitch and adjust tempo in place (tempo changes the file's duration, so durations must be read after).

    A no-op when both are ~neutral or ffmpeg is missing. With rubberband both are applied. Without it, only the
    tempo is applied (`atempo`, which keeps pitch); a pitch-only request is left
    unshifted, the same "degraded, not fatal" posture as a failed direction call.
    """
    wants_tempo = abs(tempo - 1.0) >= 0.01
    if (abs(semitones) < 0.01 and not wants_tempo) or not ffmpeg_available():
        return
    tmp = path.with_suffix(".prosody_tmp.wav")
    try:
        if rubberband_available():
            ok = _run_filter(path, tmp, f"rubberband=pitch={2 ** (semitones / 12.0)}:tempo={tempo}")
        else:
            ok = wants_tempo and _run_filter(path, tmp, f"atempo={tempo}")
        if ok:
            tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def shift_pitch(path: Path, semitones: float) -> None:
    """Shift `path`'s pitch by `semitones` in place, duration preserved."""
    modulate_prosody(path, semitones=semitones, tempo=1.0)

