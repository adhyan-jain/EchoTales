"""The episode composer (roadmap M3): one chapter as a TV-style episode, built from the graph and the voiced audio.

An episode is: a "previously" card (graph facts from BEFORE this chapter), a cold open (the most intense scene
excerpt of the chapter), the title card, the chapter in acts, and a next-episode card that names only the next
chapter's number and title. Everything here is a plan over data that already exists (panel plan, voice timing,
reader emotions, the story graph); the picture is drawn by `comic.build`'s camera window over the panel stills, or
taken from the existing `anime` composer when `motion="ltx-local"`.

Two timings are kept side by side so the choice is measured (`timing_stats`), not asserted. `voice` cuts where the
voiced lines end (one shot per panel, a long panel split at a line boundary); `fixed` cuts every N seconds whatever
is being said. The audio is identical in both.

Panel "approval": the repository stores approval for reference sheets and location plates (`assets/approval.py`),
not for rendered panels, so the keyframes here are the panels of the chosen panel-plan version, each checked to exist.
"""

from __future__ import annotations

import bisect
import json
import math
import re
import statistics
import subprocess
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image

from echotales.core.models import DiscoursePosition
from echotales.core.store import Store
from echotales.pipeline import paths
from echotales.pipeline.comic.build import _card, _pan_value, camera_window
from echotales.pipeline.comic.inpaint import srt_text
from echotales.pipeline.compositor.camera import compute_camera_trajectory
from echotales.pipeline.render.anime import AnimeRefusal, _load_timing, latest_panels_version
from echotales.pipeline.render.director import _delivery_intensity
from echotales.pipeline.render.plan import PanelPlan, load_panel_plan
from echotales.pipeline.render.shots import (
    MotionLevel,
    hold_camera_move,
    requested_motion,
)
from echotales.pipeline.screenplay.schema import CameraMove
from echotales.pipeline.voice.timing import LineTiming

TIMINGS = ("voice", "fixed")
MOTIONS = ("stills", "ltx-local")
#: Fixed-length baseline, and the longest a voice-timed shot may hold one camera move before it is split.
FIXED_SECONDS = 4.0
MAX_HOLD = 10.0
COLD_OPEN_SECONDS = 12.0
RECAP_SECONDS, TITLE_SECONDS, NEXT_SECONDS = 6.0, 3.0, 4.0
#: A cut closer than this to a line edge counts as on the line boundary (the line files are cut back to back).
EDGE_TOLERANCE = 0.05
#: A moderate beat pushes in this many times faster than a calm one (zoom amplitude over the same shot length).
MODERATE_GAIN = 1.8
RECAP_KEYS = ("role", "occupation", "status", "title")
DEFAULT_SIZE = (720, 1280)


class EpisodeRefusal(ValueError):
    """The episode cannot be composed as asked; the message names the fix."""


# --------------------------------------------------------------------------- shots


@dataclass(slots=True)
class EpShot:
    start: float
    end: float
    panel_id: str
    image_path: str
    scene_index: int
    block_indexes: list[int]
    span_ids: list[str]
    level: MotionLevel
    move: CameraMove
    #: Multiplies the camera move's zoom amplitude; > 1 reads as a faster move over the same time.
    gain: float = 1.0

    @property
    def duration(self) -> float:
        return self.end - self.start


def _motion_for(level: MotionLevel, calm_move: CameraMove) -> tuple[CameraMove, float]:
    """Calm -> the planner's slow move; moderate -> a faster push; strong -> impact shake (delivery, not scene mood)."""
    if level is MotionLevel.STRONG:
        return CameraMove.IMPACT_SHAKE, 1.0
    if level is MotionLevel.MODERATE:
        return CameraMove.SLOW_PUSH_IN, MODERATE_GAIN
    return calm_move, 1.0


def _lines_in(timing: Sequence[LineTiming], start: float, end: float) -> list[LineTiming]:
    return [t for t in timing if t.start_gapless < end - 1e-9 and t.end_gapless > start + 1e-9]


def _make_shot(panel: PanelPlan, lines: list[LineTiming], start: float, end: float,
               emotions: dict[str, tuple[str, int]] | None, calm: CameraMove) -> EpShot:
    level, _ = requested_motion(panel.direction, lines, emotions)
    move, gain = _motion_for(level, calm)
    return EpShot(
        start=start, end=end, panel_id=panel.panel_id, image_path=panel.image_path, scene_index=panel.scene_index,
        block_indexes=sorted({t.block_index for t in lines}) or list(panel.block_indexes),
        span_ids=[t.span_id for t in lines], level=level, move=move, gain=gain,
    )


def _split_at_line(lines: list[LineTiming], max_hold: float) -> list[list[LineTiming]]:
    """Halve a run of lines at the line boundary nearest its middle until every piece fits `max_hold`."""
    if len(lines) < 2 or lines[-1].end_gapless - lines[0].start_gapless <= max_hold:
        return [lines]
    mid = (lines[0].start_gapless + lines[-1].end_gapless) / 2
    cut = min(range(1, len(lines)), key=lambda i: abs(lines[i].start_gapless - mid))
    return _split_at_line(lines[:cut], max_hold) + _split_at_line(lines[cut:], max_hold)


def panel_runs(panels: list[PanelPlan], timing: Sequence[LineTiming]) -> list[tuple[PanelPlan, list[LineTiming]]]:
    """The voiced lines grouped into runs that share a panel, in play order.

    Not `shots.plan_shots`: that refuses panels whose blocks interleave, and a real render does produce them (RI ch1
    v55: panel 2 holds blocks 1 and 3, panel 1 holds block 2) because an image is reused for a later block. Here a
    panel simply returns to the screen as a cut-back. A voiced block no panel claims rides on the previous line's panel,
    or on the first panel when it leads the chapter."""
    owner = {b: p for p in panels for b in p.block_indexes}
    runs: list[tuple[PanelPlan, list[LineTiming]]] = []
    for t in timing:
        panel = owner.get(t.block_index) or (runs[-1][0] if runs else panels[0])
        if runs and runs[-1][0] is panel:
            runs[-1][1].append(t)
        else:
            runs.append((panel, [t]))
    return runs


def plan_episode_shots(
    panels: list[PanelPlan],
    timing: list[LineTiming],
    *,
    mode: str = "voice",
    emotions: dict[str, tuple[str, int]] | None = None,
    fixed_seconds: float = FIXED_SECONDS,
    max_hold: float = MAX_HOLD,
) -> list[EpShot]:
    """Shots that tile the chapter's gapless audio exactly. `voice` and `fixed` differ only in where the cuts fall."""
    if mode not in TIMINGS:
        raise EpisodeRefusal(f"timing {mode!r} is not one of {', '.join(TIMINGS)}")
    runs = panel_runs(panels, timing)
    total = timing[-1].end_gapless if timing else 0.0
    shots: list[EpShot] = []
    if mode == "voice":
        for panel, lines in runs:
            base = hold_camera_move(lines, lines[0].block_index)
            for i, piece in enumerate(_split_at_line(lines, max_hold)):
                # a split panel re-aims instead of repeating the same push
                calm = CameraMove.PULL_OUT if i % 2 == 1 and base is CameraMove.SLOW_PUSH_IN else base
                shots.append(_make_shot(panel, piece, piece[0].start_gapless, piece[-1].end_gapless, emotions, calm))
        return shots
    edges = [k * fixed_seconds for k in range(int(total // fixed_seconds) + 1)] or [0.0]
    if total - edges[-1] > fixed_seconds / 2 or len(edges) == 1:
        edges.append(total)
    else:
        edges[-1] = total
    starts = [lines[0].start_gapless for _, lines in runs]
    for a, b in zip(edges, edges[1:]):
        panel, lines = runs[max(bisect.bisect_right(starts, (a + b) / 2) - 1, 0)]
        shots.append(_make_shot(panel, _lines_in(timing, a, b), a, b, emotions, hold_camera_move(lines, lines[0].block_index)))
    return shots


def timing_stats(shots: Sequence[EpShot], timing: Sequence[LineTiming]) -> dict:
    """The numbers the A/B reads: how often the picture cuts, and whether a cut lands inside a spoken line."""
    total = shots[-1].end if shots else 0.0
    durations = [s.duration for s in shots]
    edges = [t.end_gapless for t in timing]
    cuts = [s.end for s in shots[:-1]]
    mid = sum(1 for c in cuts if min((abs(c - e) for e in edges), default=1.0) > EDGE_TOLERANCE)
    changes = sum(1 for a, b in zip(shots, shots[1:]) if a.panel_id != b.panel_id)
    return {
        "shots": len(shots), "cuts": len(cuts), "cuts_per_minute": round(len(cuts) / (total / 60), 2) if total else 0.0,
        "asl_mean": round(statistics.fmean(durations), 2) if durations else 0.0,
        "asl_median": round(statistics.median(durations), 2) if durations else 0.0,
        "asl_max": round(max(durations), 2) if durations else 0.0,
        "mid_line_cuts": mid, "picture_changes": changes, "same_panel_restarts": len(cuts) - changes,
    }


# --------------------------------------------------------------------------- acts and cold open


@dataclass(slots=True)
class Act:
    index: int
    first: int
    last: int
    start: float
    end: float
    scenes: list[int] = field(default_factory=list)


def plan_acts(shots: Sequence[EpShot], panels: list[PanelPlan], n_acts: int = 3) -> list[Act]:
    """Acts are runs of whole scenes of about equal length: a cut is only ever placed on a scene boundary."""
    if not shots:
        return []
    boundaries = [i for i in range(1, len(shots)) if shots[i].scene_index != shots[i - 1].scene_index]
    total = shots[-1].end
    chosen: list[int] = []
    for k in range(1, n_acts):
        left = [i for i in boundaries if i not in chosen and (not chosen or i > max(chosen))]
        if not left:
            break
        chosen.append(min(left, key=lambda i: abs(shots[i].start - total * k / n_acts)))
    firsts = [0, *sorted(chosen)]
    acts = []
    for n, first in enumerate(firsts):
        last = firsts[n + 1] - 1 if n + 1 < len(firsts) else len(shots) - 1
        acts.append(Act(n + 1, first, last, shots[first].start, shots[last].end,
                        sorted({s.scene_index for s in shots[first:last + 1]})))
    return acts


@dataclass(slots=True)
class ColdOpen:
    start: float
    end: float
    peak_block: int
    peak_span_id: str
    strength: int
    scene_index: int


def line_strength(t: LineTiming, emotions: dict[str, tuple[str, int]] | None) -> int:
    """Reader emotion intensity (1-3) or the line's own delivery markers (0-3), whichever is higher: delivery markers
    override scene sentiment (non-negotiable 10)."""
    return max((emotions or {}).get(t.span_id, ("", 0))[1], _delivery_intensity(t.text))


def pick_cold_open(shots: Sequence[EpShot], panels: list[PanelPlan], timing: Sequence[LineTiming],
                   emotions: dict[str, tuple[str, int]] | None, *, max_seconds: float = COLD_OPEN_SECONDS) -> ColdOpen | None:
    """The most intense line (first on a tie) and the lines after it in the same scene, up to `max_seconds`.
    None when no line carries any intensity: a flat chapter gets no cold open rather than a random one."""
    if not timing or not shots:
        return None
    peak = max(timing, key=lambda t: (line_strength(t, emotions), -t.order))
    strength = line_strength(peak, emotions)
    if strength == 0:
        return None
    starts = [s.start for s in shots]

    def scene_at(t: float) -> int:
        return shots[max(bisect.bisect_right(starts, t + 1e-9) - 1, 0)].scene_index

    scene, end = scene_at(peak.start_gapless), peak.end_gapless
    for t in timing:
        if t.order <= peak.order or scene_at(t.start_gapless) != scene or t.end_gapless - peak.start_gapless > max_seconds:
            continue
        end = max(end, t.end_gapless)
    return ColdOpen(peak.start_gapless, end, peak.block_index, peak.span_id, strength, scene)


# --------------------------------------------------------------------------- graph cards


def recap_lines(store: Store, novel_id: str, chapter: float, limit: int = 4) -> list[str]:
    """"Previously on" lines from graph facts the viewer already has: `state_of` at the end of the chapter before this
    one, with the knowledge position there too, so a fact learned in this chapter or later is absent by construction
    (and `test_episode.py` plants one to prove it). Names of entities first attested later are dropped as well."""
    prev = math.ceil(chapter) - 1
    if prev < 1:
        return []
    from echotales.core.state import state_of

    known_by = DiscoursePosition(chapter=prev, offset=10**6)
    counts: dict[str, int] = {}
    for m in store.get_mentions(novel_id):
        if m.target_id and m.chapter <= prev:
            counts[m.target_id] = counts.get(m.target_id, 0) + 1
    rank = {"PRINCIPAL": 0, "RECURRING": 1, "INCIDENTAL": 2}
    people = [s for s in store.all_selves(novel_id) if s.kind.is_person and s.first_attested_pos.chapter <= prev]
    people.sort(key=lambda s: (rank.get(str(s.prominence), 2), -counts.get(s.id, 0), s.canonical_label))
    lines: list[str] = []
    for entity in people[:25]:
        res = state_of(store, novel_id, entity.id, position=prev, knowledge_pos=known_by)
        parts = []
        for rel_type, dst in res.relationships:
            other = store.get_self(dst)
            if other is not None and other.first_attested_pos.chapter <= prev:
                parts.append(f"{rel_type.lower().replace('_', ' ')} {other.canonical_label}")
        parts += [res.attributes[k] for k in RECAP_KEYS if k in res.attributes]
        if parts:
            lines.append(f"{entity.canonical_label} - {'; '.join(parts[:3])}")
        if len(lines) == limit:
            break
    return lines


def next_card_lines(titles: Sequence[tuple[float, str]], chapter: float) -> list[str]:
    """Only the next chapter's number and title: nothing from its text or the graph."""
    later = [(n, t) for n, t in titles if n > chapter]
    if not later:
        return []
    n, title = min(later)
    return ["Next time", f"Episode {n:g}", *([title] if title.strip() else [])]


# --------------------------------------------------------------------------- picture and sound


def _shift(win: tuple[float, float, float, float], dx: float, dy: float, bounds: tuple[int, int]):
    x0, y0, x1, y1 = win
    dx = min(max(dx, -x0), bounds[0] - x1)
    dy = min(max(dy, -y0), bounds[1] - y1)
    return x0 + dx, y0 + dy, x1 + dx, y1 + dy


def shot_frames(plate: Image.Image, shot: EpShot, n: int, size: tuple[int, int], fps: int) -> Iterator[bytes]:
    """`n` frames of one shot: the planner's move with the zoom amplitude scaled by `gain`, shake as a window offset."""
    traj = compute_camera_trajectory(shot.move, n / fps, fps)
    box = (0, 0, plate.width, plate.height)
    aspect = size[0] / size[1]
    kfs = traj.keyframes
    for i in range(n):
        kf = kfs[min(i, len(kfs) - 1)]
        zoom = 1.0 + (kf.zoom - 1.0) * shot.gain
        win = camera_window(box, aspect, zoom, _pan_value(shot.move, kf))
        if shot.move is CameraMove.IMPACT_SHAKE:
            win = _shift(win, kf.pan_x * (win[2] - win[0]), kf.pan_y * (win[3] - win[1]), plate.size)
        yield plate.resize(size, Image.Resampling.BICUBIC, box=win).tobytes()


def _decode_frames(video: Path, size: tuple[int, int], fps: int, ss: float, n: int) -> Iterator[bytes]:
    """Frames of an existing video scaled and padded to `size`; the last frame repeats if the source runs short."""
    w, h = size
    cmd = ["ffmpeg", "-loglevel", "error", "-ss", f"{ss:.3f}", "-i", str(video), "-an", "-vf",
           f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
           "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    assert proc.stdout is not None
    got, last = 0, b""
    while got < n and len(buf := proc.stdout.read(w * h * 3)) == w * h * 3:
        last = buf
        got += 1
        yield buf
    proc.stdout.close()
    proc.wait()
    for _ in range(n - got):
        yield last or bytes(w * h * 3)


def _mix(placements: list[tuple[float, str]], total: float, path: Path, rate: int = 24000) -> None:
    import soundfile as sf

    out = np.zeros(int(total * rate) + rate, dtype=np.float32)
    for at, wav in placements:
        data, sr = sf.read(wav, dtype="float32", always_2d=True)
        mono = data.mean(axis=1)
        if sr != rate:
            mono = np.interp(np.linspace(0, len(mono), int(len(mono) * rate / sr), endpoint=False),
                             np.arange(len(mono)), mono).astype(np.float32)
        a = int(at * rate)
        out[a:a + len(mono)] += mono[: len(out) - a]
    sf.write(str(path), out, rate)


def write_frame_tile(video: Path, out: Path, *, cols: int = 6, rows: int = 4, width: int = 240) -> Path:
    """A contact sheet of evenly spaced frames, so a person can look at the episode without playing it."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True, check=True).stdout
    every = max(float(probe) / (cols * rows), 0.1)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf",
                    f"fps=1/{every:.3f},scale={width}:-2,tile={cols}x{rows}", "-frames:v", "1", "-update", "1", str(out)],
                   check=True)
    return out


# --------------------------------------------------------------------------- compose


@dataclass(slots=True)
class EpisodeResult:
    out_dir: Path
    video: Path
    summary: dict


def _frames_for(t0: float, t1: float, fps: int) -> int:
    return round(t1 * fps) - round(t0 * fps)


def compose_episode(
    store: Store,
    novel_id: str,
    chapter: float,
    *,
    panels_dir: Path,
    audio_dir: Path,
    out_root: Path,
    timing: str = "voice",
    motion: str = "stills",
    size: tuple[int, int] = DEFAULT_SIZE,
    fps: int = 30,
    suffix: str | None = None,
    chapter_titles: Sequence[tuple[float, str]] | None = None,
    book_title: str | None = None,
    n_acts: int = 3,
    fixed_seconds: float = FIXED_SECONDS,
    cold_open_seconds: float = COLD_OPEN_SECONDS,
    seed: int = 0,
    panels_root: Path | None = None,
) -> EpisodeResult:
    """Plan and render one episode. The audio is the chapter's voiced lines back to back; the cards are silent."""
    if motion not in MOTIONS:
        raise EpisodeRefusal(f"motion {motion!r} is not one of {', '.join(MOTIONS)}")
    if motion == "ltx-local" and timing != "voice":
        raise EpisodeRefusal("ltx-local clips are planned from the voiced lines; use --timing voice with it")
    try:
        panels = load_panel_plan(panels_dir)
    except FileNotFoundError as exc:
        raise AnimeRefusal(f"{exc}. Render the chapter again to write a panel plan.") from exc
    if not panels:
        raise AnimeRefusal(f"{panels_dir} has an empty panel plan")
    missing = [p.image_path for p in panels if not (panels_dir / p.image_path).is_file()]
    if missing:
        raise EpisodeRefusal(f"panel images missing from {panels_dir}: {missing[:3]}; the keyframes must exist")
    lines = _load_timing(audio_dir, chapter)
    emotions = store.span_emotions(novel_id, chapter)
    titles = list(chapter_titles) if chapter_titles is not None else store.chapter_titles(novel_id)
    title_of = dict(titles)
    book = book_title or (store.get_novel(novel_id) or {}).get("title") or novel_id

    shots = plan_episode_shots(panels, lines, mode=timing, emotions=emotions, fixed_seconds=fixed_seconds)
    stats = timing_stats(shots, lines)
    acts = plan_acts(shots, panels, n_acts)
    cold = pick_cold_open(shots, panels, lines, emotions, max_seconds=cold_open_seconds)
    recap = recap_lines(store, novel_id, chapter)
    nxt = next_card_lines(titles, chapter)
    body_seconds = lines[-1].end_gapless

    body_video: Path | None = None
    if motion == "ltx-local":
        from echotales.pipeline.render.anime import compose_chapter_video

        body_video = compose_chapter_video(
            novel_id, chapter, engine="ltx-local", panel_dir=panels_dir.parent.parent, audio_dir=audio_dir,
            out_dir=out_root.parent, panels_version=panels_dir.name, seed=seed, captions=False,
        ).video

    tag = re.sub(r"[^a-z0-9-]+", "-", (suffix or f"episode-{timing}-{motion}").lower()).strip("-")
    out_root.mkdir(parents=True, exist_ok=True)
    out_dir = out_root / f"{paths.next_version(out_root)}_{tag}"
    out_dir.mkdir()

    # ---- the timeline in frames, so audio and picture are laid out from the same integers.
    parts: list[tuple[str, int]] = []
    if recap:
        parts.append(("recap", round(RECAP_SECONDS * fps)))
    if cold:
        parts.append(("cold", round((cold.end - cold.start) * fps)))  # relative, as `still_body` counts
    parts.append(("title", round(TITLE_SECONDS * fps)))
    body_frames = round(body_seconds * fps)
    parts.append(("body", body_frames))
    if nxt:
        parts.append(("next", round(NEXT_SECONDS * fps)))
    at: dict[str, int] = {}
    cursor = 0
    for name, n in parts:
        at[name] = cursor
        cursor += n
    total_frames = cursor
    total = total_frames / fps

    placements: list[tuple[float, str]] = []
    cues: list[tuple[float, float, str]] = []
    for t in lines:
        placements.append((at["body"] / fps + t.start_gapless, t.audio_path))
        cues.append((at["body"] / fps + t.start_gapless, at["body"] / fps + t.end_gapless, t.text))
    if cold:
        for t in _lines_in(lines, cold.start, cold.end):
            off = at["cold"] / fps + max(t.start_gapless - cold.start, 0.0)
            placements.append((off, t.audio_path))
            cues.append((off, off + t.duration, t.text))
    wav, srt, meta = out_dir / "episode_audio.wav", out_dir / "episode.srt", out_dir / "chapters.ffmeta"
    _mix(placements, total, wav)
    srt.write_text(srt_text(sorted(cues)), encoding="utf-8")
    marks = [(n, at[n] / fps, (at[n] + dict(parts)[n]) / fps) for n, _ in parts if n != "body"]
    names = {"recap": "Previously", "cold": "Cold open", "title": "Title", "next": "Next time"}
    chapters = [(names[n], a, b) for n, a, b in marks if n != "next"]
    chapters += [(f"Act {a.index}", at["body"] / fps + a.start, at["body"] / fps + a.end) for a in acts]
    chapters += [(names[n], a, b) for n, a, b in marks if n == "next"]
    meta.write_text(";FFMETADATA1\n" + "".join(
        f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(a * 1000)}\nEND={int(b * 1000)}\ntitle={name}\n" for name, a, b in sorted(
            chapters, key=lambda c: c[1])), encoding="utf-8")

    ep_title = [book, f"Episode {chapter:g}", *([title_of[chapter]] if title_of.get(chapter, "").strip() else [])]
    cards = {
        "recap": _card(size, ["Previously", *recap]), "title": _card(size, ep_title),
        "next": _card(size, nxt) if nxt else None,
    }
    plates: dict[str, Image.Image] = {}

    def plate(rel: str) -> Image.Image:
        if rel not in plates:
            plates[rel] = Image.open(panels_dir / rel).convert("RGB")
        return plates[rel]

    def still_body(first: float, last: float) -> Iterator[bytes]:
        """Frames covering [first, last) of the body clock; a shot clipped by the window re-aims its move."""
        for s in shots:
            a, b = max(s.start, first), min(s.end, last)
            if b - a <= 1e-9:
                continue
            n = _frames_for(a - first, b - first, fps)
            if n > 0:
                yield from shot_frames(plate(s.image_path), s, n, size, fps)

    def stream() -> Iterator[bytes]:
        for name, n in parts:
            if name == "body":
                yield from (_decode_frames(body_video, size, fps, 0.0, n) if body_video else still_body(0.0, body_seconds))
            elif name == "cold":
                assert cold is not None
                yield from (_decode_frames(body_video, size, fps, cold.start, n) if body_video
                            else still_body(cold.start, cold.end))
            else:
                card = cards[name]
                assert card is not None
                data = card.tobytes()
                for _ in range(n):
                    yield data

    video = out_dir / "episode.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
           "-r", str(fps), "-i", "-", "-i", str(wav), "-i", str(srt), "-i", str(meta), "-map", "0:v", "-map", "1:a",
           "-map", "2:s", "-map_chapters", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac",
           "-b:a", "160k", "-c:s", "mov_text", "-metadata", f"title={book} - Episode {chapter:g}",
           "-frames:v", str(total_frames), "-t", f"{total:.3f}", str(video)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    written = 0
    try:
        for frame in stream():
            proc.stdin.write(frame)
            written += 1
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {rc}")
    if written != total_frames:
        raise RuntimeError(f"wrote {written} frames, the timeline needs {total_frames}")
    wav.unlink(missing_ok=True)
    tile = write_frame_tile(video, out_dir / "tile.png")

    summary = {
        "novel": novel_id, "chapter": chapter, "timing": timing, "motion": motion, "size": list(size), "fps": fps,
        "duration": round(total, 3), "body_seconds": round(body_seconds, 3), "panels_version": panels_dir.name,
        "stats": stats, "acts": [asdict(a) for a in acts], "cold_open": asdict(cold) if cold else None,
        "recap": recap, "next_card": nxt, "title_card": ep_title, "video": str(video), "tile": str(tile),
        "body_video": str(body_video) if body_video else None,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    with (out_dir / "shots.jsonl").open("w", encoding="utf-8") as fh:
        for s in shots:
            fh.write(json.dumps({**asdict(s), "level": s.level.value, "move": s.move.value}) + "\n")
    _append_version(out_root, out_dir.name, summary)
    return EpisodeResult(out_dir, video, summary)


def _append_version(out_root: Path, name: str, s: dict) -> None:
    path = out_root / "VERSIONS.md"
    if not path.exists():
        path.write_text("# video version index\n\nOne entry per run, written by the code with the directory.\n", encoding="utf-8")
    st = s["stats"]
    cold = "cold open " + f"{s['cold_open']['start']:.0f}-{s['cold_open']['end']:.0f}s" if s["cold_open"] else "no cold open"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(
            f"\n## {name} - {date.today().isoformat()}\n\n"
            f"**What was tried:** `echotales episode`, timing `{s['timing']}`, motion `{s['motion']}`, panels "
            f"`{s['panels_version']}`: {s['duration']:.1f} s, {st['shots']} shots ({st['cuts_per_minute']} cuts/min, mean shot "
            f"{st['asl_mean']} s, {st['mid_line_cuts']} cuts inside a spoken line), {len(s['acts'])} acts, {cold}, "
            f"{'recap of ' + str(len(s['recap'])) + ' facts' if s['recap'] else 'no recap'}.\n\n"
            "**Verdict:** not yet watched by a person.\n"
        )


def compose_chapter_episode(
    store: Store,
    novel_id: str,
    chapter: float,
    *,
    timing: str = "voice",
    motion: str = "stills",
    panel_dir: str | Path | None = None,
    audio_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    panels_version: str | None = None,
    suffix: str | None = None,
    size: tuple[int, int] = DEFAULT_SIZE,
    fps: int = 30,
    seed: int = 0,
) -> EpisodeResult:
    """One chapter's episode from a novel's default folders. `echotales episode` and the Studio `episode` job both call
    this, so the two cannot disagree on which panel version is used or where the output goes."""
    panel_dir = Path(panel_dir if panel_dir is not None else paths.asset_dir(novel_id, "panels"))
    audio_dir = Path(audio_dir if audio_dir is not None else paths.asset_dir(novel_id, "audio"))
    out_root = Path(out_dir if out_dir is not None else paths.asset_dir(novel_id, "video")) / f"ch{chapter:g}"
    panels_dir = (panel_dir / f"ch{chapter:g}" / panels_version if panels_version
                  else latest_panels_version(panel_dir, chapter, novel_id))
    return compose_episode(
        store, novel_id, chapter, panels_dir=panels_dir, audio_dir=audio_dir, out_root=out_root, timing=timing,
        motion=motion, size=size, fps=fps, suffix=suffix, seed=seed,
    )
