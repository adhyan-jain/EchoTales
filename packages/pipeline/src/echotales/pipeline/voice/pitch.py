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


def shift_pitch(path: Path, semitones: float) -> None:
    """Shift `path`'s pitch by `semitones` in place, duration preserved.

    A no-op when `semitones` is ~0 or ffmpeg isn't on `PATH` -- callers
    (`voice/runner.py`) are expected to check `ffmpeg_available()` once up
    front and warn, not fail a whole render over a missing optional tool.
    """
    if abs(semitones) < 0.01 or not ffmpeg_available():
        return
    ratio = 2 ** (semitones / 12.0)
    tmp = path.with_suffix(".pitch_tmp.wav")
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(path),
            "-af", f"rubberband=pitch={ratio}",
            str(tmp),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not tmp.exists():
        # Same "degraded, not fatal" posture as a failed direction call
        # (render/direction.py): the unshifted line is still a real,
        # audible line, just not pitched the way delivery.py asked for.
        if tmp.exists():
            tmp.unlink()
        return
    tmp.replace(path)
