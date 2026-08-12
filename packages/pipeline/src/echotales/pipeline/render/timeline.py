"""Shot decisions + real audio durations -> a timed shot list (xyz.md Step 4,
video revision).

**Image duration is locked to speech, never the reverse.** `director.py`
decides *what* to show per block; this module decides *when*, by reading
each line's already-rendered WAV (`voice/runner.py::render_novel`'s
`manifest.jsonl`) and summing every line spoken over a block into that
block's on-screen time. Nothing here estimates timing -- the audio is
already rendered by the time this stage runs, so its duration is a fact,
not a guess.

**A block with no shot plan does not create a silent gap in the picture.**
`director.py::build_shot_plan` only emits a shot for a block that has both a
panel and audible spans; a block that reaches audio without a panel (should
not happen in steady state, but a partial run -- `panels.py` interrupted, a
block filtered differently between stages -- can produce one) instead
carries the previous shot forward, `carried_over=True`, rather than
dropping that block's audio or leaving a hole `compose.py` would have to
paper over silently. The flag exists so a review pass can see exactly where
that happened, same spirit as `AttributionMethod.ANONYMOUS_SLOT` making a
gap visible instead of invented.
"""

from __future__ import annotations

import itertools
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from echotales.pipeline.render.director import ShotPlan


class _AudioLineLike(Protocol):
    block_index: int
    audio_path: str


@dataclass(slots=True)
class TimedShot:
    chapter: float
    block_index: int
    kind: str  # "pan" | "clip"
    asset_path: str
    start: float
    end: float
    pan_direction: str | None = None
    tag: str | None = None
    #: True when no `ShotPlan` existed for this block and the previous
    #: shot's asset was carried forward -- see the module docstring.
    carried_over: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start


def read_wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as fh:
        return fh.getnframes() / float(fh.getframerate())


def build_timeline(
    chapter: float,
    audio_lines: list[_AudioLineLike],
    shots: list[ShotPlan],
) -> list[TimedShot]:
    """One `TimedShot` per contiguous run of audio lines sharing a block.

    `audio_lines` must already be in reading order with same-block lines
    contiguous -- exactly the order `voice/runner.py::render_novel` writes
    `manifest.jsonl` in, since it iterates `store.get_spans`, which is
    itself ordered `(block_index, start)` (see `Store.get_spans`'s
    docstring on why that ordering is load-bearing).
    """
    shot_by_block = {s.block_index: s for s in shots}
    timeline: list[TimedShot] = []
    cursor = 0.0
    last_shot: ShotPlan | None = None

    for block_index, group in itertools.groupby(audio_lines, key=lambda line: line.block_index):
        duration = sum(
            read_wav_duration(Path(line.audio_path)) for line in group if line.audio_path
        )
        if duration <= 0:
            continue

        shot = shot_by_block.get(block_index)
        carried = shot is None
        if shot is None:
            if last_shot is None:
                # Nothing has been shown yet, so there is no asset to carry
                # forward -- this block's audio plays with no matching
                # video, which `compose.py` must not silently patch over.
                cursor += duration
                continue
            shot = last_shot

        timeline.append(
            TimedShot(
                chapter=chapter,
                block_index=block_index,
                kind=shot.kind,
                asset_path=shot.asset_path,
                pan_direction=shot.pan_direction,
                tag=shot.tag,
                start=cursor,
                end=cursor + duration,
                carried_over=carried,
            )
        )
        cursor += duration
        last_shot = shot

    return timeline
