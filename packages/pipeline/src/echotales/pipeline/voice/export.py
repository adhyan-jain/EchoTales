"""From per-line clips to something a listener plays: paced chapter tracks and one M4B per book.

Two complaints this answers. **Pacing:** `chapter_track` butted every line against the next with the same 0.35 s, so a
speaker answering, a new paragraph and a scene change all sounded identical -- a listener hears structure in the
pauses, and there was none. **No audiobook:** the product promise (decisions D27) is an M4B with chapter markers, and
the pipeline stopped at one WAV per chapter.

Loudness is normalised once over the whole book, not per line: per-line normalisation flattens exactly the loud/quiet
contrast the emotion work adds (a whisper raised to the level of a shout). -18 LUFS integrated with a -3 dBTP ceiling
sits inside the usual audiobook range (ACX asks for -23 to -18 dB RMS) at the loud end, for phone speakers.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

#: Seconds of silence after a line, by what comes next.
SAME_SPEAKER_GAP_S = 0.25
SPEAKER_CHANGE_GAP_S = 0.45
PARAGRAPH_GAP_S = 0.6
#: A jump of more than one block with nothing voiced between (a scene-break line, a skipped heading).
SCENE_GAP_S = 1.4
LOUDNESS_LUFS = -18.0
TRUE_PEAK_DB = -3.0


class _Line(Protocol):
    block_index: int
    voice: str
    span_type: str


def gaps_for(lines: Sequence[_Line]) -> list[float]:
    """The pause before each line after the first (`len(lines) - 1` values)."""
    out: list[float] = []
    for prev, line in zip(lines, lines[1:]):
        if line.block_index - prev.block_index > 1:
            out.append(SCENE_GAP_S)
        elif line.voice != prev.voice:
            out.append(SPEAKER_CHANGE_GAP_S)
        elif line.block_index != prev.block_index:
            out.append(PARAGRAPH_GAP_S)
        else:
            out.append(SAME_SPEAKER_GAP_S)
    return out


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as fh:
        return fh.getnframes() / float(fh.getframerate())


def chapter_metadata(titles: Sequence[str], durations: Sequence[float], *, title: str, author: str) -> str:
    """ffmetadata text with one chapter per track, in milliseconds."""
    lines = [";FFMETADATA1", f"title={title}", f"artist={author}", "genre=Audiobook"]
    start = 0
    for name, seconds in zip(titles, durations):
        end = start + round(seconds * 1000)
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}", f"title={name}"]
        start = end
    return "\n".join(lines) + "\n"


def _concat_escape(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def book_tracks(audio_dir: Path, titles_by_number: dict[float, str]) -> tuple[list[Path], list[str], list[float]]:
    """Every `ch<N>/chapter.wav` under `audio_dir` in chapter order, with a title for each.

    The CLI titled chapters "Chapter 1".."Chapter N" from the folder name, so an audiobook's chapter list never showed
    the book's own chapter titles."""
    found: list[tuple[float, Path]] = []
    for track in Path(audio_dir).glob("ch*/chapter.wav"):
        try:
            found.append((float(track.parent.name.removeprefix("ch")), track))
        except ValueError:
            continue
    found.sort()
    tracks = [t for _, t in found]
    numbers = [n for n, _ in found]
    titles = []
    for n in numbers:
        name = titles_by_number.get(n, "").strip()
        titles.append(f"Chapter {n:g}: {name}" if name and not name.lower().startswith("chapter") else name or f"Chapter {n:g}")
    return tracks, titles, numbers


def engine_of(audio_dir: Path) -> str:
    """The engine that wrote this directory's audio (`run.json`), or "" for audio from before the record existed."""
    try:
        return str(json.loads((Path(audio_dir) / "run.json").read_text(encoding="utf-8")).get("engine", ""))
    except (OSError, ValueError):
        return ""


def export_m4b(
    tracks: Sequence[Path],
    out_path: Path,
    *,
    titles: Sequence[str],
    title: str,
    author: str = "",
    cover: Path | None = None,
    bitrate: str = "64k",
) -> Path:
    """Concatenate chapter WAVs into one loudness-normalised AAC M4B with a chapter marker per track."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required for the M4B export and was not found on PATH")
    if len(titles) != len(tracks) or not tracks:
        raise ValueError("one title per chapter track, and at least one track")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        listing = Path(tmp) / "tracks.txt"
        # ffmpeg's concat list quotes with '...': a path containing an apostrophe ended the quote early and the whole
        # export failed ("Alice's Adventures/..."); the escape is close-quote, backslash-quote, reopen.
        listing.write_text("".join(f"file '{_concat_escape(Path(t).resolve())}'\n" for t in tracks), encoding="utf-8")
        meta = Path(tmp) / "chapters.txt"
        meta.write_text(
            chapter_metadata(titles, [wav_seconds(Path(t)) for t in tracks], title=title, author=author),
            encoding="utf-8",
        )
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(meta)]
        if cover is not None:
            cmd += ["-i", str(cover)]
        cmd += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
        if cover is not None:
            cmd += ["-map", "2:v", "-c:v", "copy", "-disposition:v", "attached_pic"]
        cmd += [
            "-af", f"loudnorm=I={LOUDNESS_LUFS}:TP={TRUE_PEAK_DB}:LRA=11",
            "-c:a", "aac", "-b:a", bitrate, "-ar", "44100", "-movflags", "+faststart", str(out_path),
        ]
        subprocess.run(cmd, check=True)
    return out_path
