"""Per-line audio timing: how long each voiced line lasts and when it starts, on both clocks.

**Why this exists.** Nothing stored a duration or a start time. The video path read WAV lengths on the
fly and butted the lines together, while `chapter.wav` inserts the `gaps_for` pauses, so a shot planned
against one clock drifts against the other (a 100-line chapter differs by tens of seconds). This record
puts both clocks next to each other, derived from the same `gaps_for` call `render_novel` uses so they
cannot disagree.
"""

from __future__ import annotations

import json
import wave
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from echotales.pipeline.voice.export import gaps_for, wav_seconds
from pydantic import BaseModel

TIMING_SCHEMA_VERSION = 1
TIMING_FILE = "timing.jsonl"

Clock = Literal["gapless", "gapped"]


class TimingError(ValueError):
    """A voiced line whose WAV cannot be timed, or a timing file this code cannot read."""


class LineTiming(BaseModel):
    schema_version: int = TIMING_SCHEMA_VERSION
    chapter: float
    #: Position in the chapter's voiced lines.
    order: int
    span_id: str
    block_index: int
    speaker_id: str = ""
    speaker_label: str = ""
    voice: str = ""
    span_type: str = ""
    text: str = ""
    emotion: str = "neutral"
    audio_path: str
    duration: float
    #: What the video path plays: line WAVs back to back.
    start_gapless: float
    end_gapless: float
    #: What `chapter.wav` plays: `gaps_for` pauses between lines.
    start_gapped: float
    end_gapped: float
    #: Silence `chapter.wav` puts before this line (0 for the first).
    gap_before: float = 0.0

    def start(self, clock: Clock) -> float:
        return self.start_gapless if clock == "gapless" else self.start_gapped

    def end(self, clock: Clock) -> float:
        return self.end_gapless if clock == "gapless" else self.end_gapped


def chapter_dir(audio_dir: str | Path, chapter: float) -> Path:
    return Path(audio_dir) / f"ch{chapter:g}"


def _resolve(audio_dir: Path, chapter: float, audio_path: str) -> Path:
    # The manifest stores the path as written at synthesis time, relative to that run's cwd.
    p = Path(audio_path)
    if p.exists():
        return p
    moved = chapter_dir(audio_dir, chapter) / p.name
    return moved if moved.exists() else p


def build_timing(audio_dir: str | Path, chapter: float, *, write: bool = False) -> list[LineTiming]:
    """One record per voiced line of `chapter`, in the order `chapter.wav` plays them.

    Raises `TimingError` naming the span for a missing or zero-length WAV: a silent 0 s line would
    shorten every later shot instead of failing where the audio is actually wrong.
    """
    audio_dir = Path(audio_dir)
    manifest = audio_dir / "manifest.jsonl"
    if not manifest.exists():
        raise FileNotFoundError(f"no manifest.jsonl in {audio_dir}")
    rows = [json.loads(ln) for ln in manifest.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # Same filter `render_novel` applies before `chapter_track`, so the gap list lines up.
    voiced = [r for r in rows if r["chapter"] == chapter and r.get("audio_path")]
    gaps = gaps_for([
        SimpleNamespace(**{k: r.get(k, "") for k in ("block_index", "voice", "span_type")})
        for r in voiced
    ])

    out: list[LineTiming] = []
    g_start = 0.0
    p_start = 0.0
    for i, r in enumerate(voiced):
        path = _resolve(audio_dir, chapter, r["audio_path"])
        span = r.get("span_id", "")
        if not path.exists():
            raise TimingError(f"line {span!r} (block {r['block_index']}): missing WAV {path}")
        try:
            dur = wav_seconds(path)
            with wave.open(str(path), "rb") as fh:
                rate = fh.getframerate()
        except (wave.Error, EOFError) as exc:
            raise TimingError(f"line {span!r}: unreadable WAV {path}: {exc}") from exc
        if dur <= 0.0:
            raise TimingError(f"line {span!r} (block {r['block_index']}): zero-length WAV {path}")
        gap = 0.0
        if i:
            # `chapter_track` writes int(rate * pause) silent frames, so the gapped clock must truncate too
            # or it drifts one sample per line against the real file.
            gap = int(rate * gaps[i - 1]) / rate
            p_start = out[-1].end_gapped + gap
            g_start = out[-1].end_gapless
        out.append(LineTiming(
            chapter=chapter, order=i, span_id=span, block_index=r["block_index"],
            speaker_id=r.get("speaker_id", ""), speaker_label=r.get("speaker_label", ""),
            voice=r.get("voice", ""), span_type=r.get("span_type", ""), text=r.get("text", ""),
            emotion=r.get("emotion", "neutral"), audio_path=str(path), duration=dur,
            start_gapless=g_start, end_gapless=g_start + dur,
            start_gapped=p_start, end_gapped=p_start + dur, gap_before=gap,
        ))
    if write:
        d = chapter_dir(audio_dir, chapter)
        d.mkdir(parents=True, exist_ok=True)
        (d / TIMING_FILE).write_text(
            "".join(t.model_dump_json() + "\n" for t in out), encoding="utf-8"
        )
    return out


def load_timing(audio_dir: str | Path, chapter: float) -> list[LineTiming]:
    path = chapter_dir(audio_dir, chapter) / TIMING_FILE
    if not path.exists():
        raise FileNotFoundError(f"no {TIMING_FILE} in {path.parent}")
    rows: list[LineTiming] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if raw.get("schema_version") != TIMING_SCHEMA_VERSION:
            raise TimingError(
                f"{path} line {n}: timing schema_version {raw.get('schema_version')!r}, "
                f"this code reads {TIMING_SCHEMA_VERSION}"
            )
        rows.append(LineTiming.model_validate(raw))
    return rows


def duration_of_blocks(
    timing: Sequence[LineTiming], blocks: Iterable[int], clock: Clock = "gapless"
) -> float:
    """Seconds of audio the given blocks occupy.

    A pause counts only when the line before it is also in `blocks`, so one block's duration is its
    own first-start to last-end and a contiguous run includes the pauses inside it, not the ones at
    its edges.
    """
    wanted = set(blocks)
    total = 0.0
    prev_in = False
    for t in timing:
        inside = t.block_index in wanted
        if inside:
            total += t.duration + (t.gap_before if clock == "gapped" and prev_in else 0.0)
        prev_in = inside
    return total
