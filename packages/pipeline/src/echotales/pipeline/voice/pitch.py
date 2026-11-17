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


def modulate_prosody(path: Path, semitones: float = 0.0, tempo: float = 1.0) -> None:
    """Shift pitch and adjust tempo in place.

    A no-op when both semitones ~0 and tempo ~1.0, or when ffmpeg isn't available.
    Uses ffmpeg rubberband (or atempo fallback).
    """
    if (abs(semitones) < 0.01 and abs(tempo - 1.0) < 0.01) or not ffmpeg_available():
        return
    ratio = 2 ** (semitones / 12.0)
    tmp = path.with_suffix(".prosody_tmp.wav")
    filter_expr = f"rubberband=pitch={ratio}:tempo={tempo}"
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(path),
            "-af", filter_expr,
            str(tmp),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not tmp.exists():
        if abs(tempo - 1.0) >= 0.01:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", str(path),
                    "-af", f"atempo={tempo}",
                    str(tmp),
                ],
                capture_output=True,
                text=True,
            )
        if result.returncode != 0 or not tmp.exists():
            if tmp.exists():
                tmp.unlink()
            return
    tmp.replace(path)


def shift_pitch(path: Path, semitones: float) -> None:
    """Shift `path`'s pitch by `semitones` in place, duration preserved."""
    modulate_prosody(path, semitones=semitones, tempo=1.0)

