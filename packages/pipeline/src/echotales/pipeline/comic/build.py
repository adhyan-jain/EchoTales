"""Motion comic: a clean-plate panel per shot, camera moves, the voiced lines timed to their panels.

Each panel in reading order is one shot. A shot lasts as long as the lines voiced in it (plus a short lead and tail);
a panel with no lines holds for a fixed beat. The camera is a cover-window over the panel: the window always has the
output aspect, so a wide panel pans along its long axis and a tall one tilts, and a push-in is a smaller window. The
moves come from the project's own `compute_camera_trajectory`, so easing matches the rest of the compositor.
"""

from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from echotales.pipeline.comic.ingest import PageImage
from echotales.pipeline.comic.inpaint import Inpainter, srt_text
from echotales.pipeline.comic.parallax import DepthEstimator, parallax_warp
from echotales.pipeline.comic.to_graph import story_bubbles
from echotales.pipeline.comic.understand import ComicUnderstanding
from echotales.pipeline.compositor.camera import compute_camera_trajectory
from echotales.pipeline.hwaccel import h264_args
from echotales.pipeline.screenplay.schema import CameraMove

#: Silence before a shot's first line, after its last, and the length of a panel nobody speaks in.
LEAD, TAIL, HOLD = 0.3, 0.4, 2.0
TITLE_SECONDS, CREDIT_SECONDS = 2.0, 3.0
#: Output aspect panels are covered to. A panel wider than this pans, taller tilts.
WIDE_PAN_ASPECT = 2.2


@dataclass(slots=True)
class PlacedLine:
    block_index: int
    offset: float  # seconds after the shot starts
    duration: float


@dataclass(slots=True)
class Shot:
    page_index: int
    panel_index: int
    box: tuple[int, int, int, int]
    duration: float
    lines: list[PlacedLine] = field(default_factory=list)
    move: CameraMove = CameraMove.SLOW_PUSH_IN


def plan_shots(und: ComicUnderstanding, timings: list[Any], *, lead: float = LEAD, tail: float = TAIL,
               hold: float = HOLD) -> list[Shot]:
    """Shots in reading order, durations from the voiced lines of each panel."""
    by_block = {t.block_index: t for t in timings}
    block_of: dict[str, int] = {b.id: i for i, b in enumerate(story_bubbles(und))}
    shots: list[Shot] = []
    for pg in und.pages:
        for pn in pg.panels:
            lines, t = [], lead
            for b in pn.bubbles:
                idx = block_of.get(b.id)
                if idx is None or idx not in by_block:
                    continue
                d = float(by_block[idx].duration)
                lines.append(PlacedLine(idx, round(t, 4), d))
                t += d
            duration = round(t + tail, 4) if lines else hold
            shots.append(Shot(pg.page_index, pn.index, pn.box, duration, lines, _move(pn.box, len(shots), und.rtl)))
    return shots


def _move(box, n: int, rtl: bool) -> CameraMove:
    w, h = box[2] - box[0], box[3] - box[1]
    if w / h >= WIDE_PAN_ASPECT:
        return CameraMove.PAN_LEFT if rtl else CameraMove.PAN_RIGHT
    return CameraMove.SLOW_PUSH_IN if n % 2 == 0 else CameraMove.PULL_OUT


def camera_window(box: tuple[int, int, int, int], aspect: float, zoom: float, pan: float) -> tuple[float, float, float, float]:
    """The crop of `box` the camera sees: output aspect, `zoom` >= 1 shrinks it, `pan` in [-1, 1] slides it along the
    axis the panel has spare room on. Always inside the panel."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w / h >= aspect:
        ch, cw = h / zoom, h / zoom * aspect
    else:
        cw, ch = w / zoom, w / zoom / aspect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    spare_x, spare_y = (w - cw) / 2, (h - ch) / 2
    if w / h >= aspect:
        cx += pan * spare_x
    else:
        cy += pan * spare_y
    # Clamp: `cx + pan * spare_x - cw / 2` is mathematically >= x0 but the float sum lands at about -1e-14 for a
    # full-width panel at x0 = 0, and PIL's `resize(box=...)` refuses a negative offset ("box offset can't be
    # negative"): the LotNB ch100 webtoon build died on exactly that at the first pan across a page-wide panel.
    left, top = max(float(x0), cx - cw / 2), max(float(y0), cy - ch / 2)
    return left, top, min(float(x1), cx + cw / 2), min(float(y1), cy + ch / 2)


def _font(size: int):
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _card(size: tuple[int, int], lines: list[str]) -> Image.Image:
    img = Image.new("RGB", size, (12, 12, 16))
    d = ImageDraw.Draw(img)
    y = size[1] * 0.3
    for i, text in enumerate(lines):
        f = _font(int(size[1] * (0.09 if i == 0 else 0.045)))
        wd = d.textlength(text, font=f)
        # Long credit lines wrap by halving the font until they fit the width.
        while wd > size[0] * 0.92 and f.size > 8:
            f = _font(f.size - 2)
            wd = d.textlength(text, font=f)
        d.text(((size[0] - wd) / 2, y), text, fill=(235, 235, 235), font=f)
        y += f.size * 1.8
    return img


def _pan_value(move: CameraMove, kf) -> float:
    # compute_camera_trajectory expresses pan as +-0.05 of the frame; normalise to [-1, 1] of the spare room so a
    # pan sweeps the whole panel instead of nudging it 5%.
    if move in (CameraMove.PAN_LEFT, CameraMove.PAN_RIGHT):
        return max(-1.0, min(1.0, kf.pan_x / 0.05))
    return 0.0


def shot_frame_counts(shots: list[Shot], fps: int) -> list[int]:
    """Frames per shot such that every shot starts on the frame its audio does. Rounding each shot's own length
    (`round(duration * fps)`) lost up to half a frame per shot, so 60 shots of 2.31 s ended about a second early
    against the mixed audio and subtitles, which are placed in seconds (EVOLUTION 4.183)."""
    counts, t, done = [], 0.0, 0
    for shot in shots:
        t += shot.duration
        end = max(done + 1, round(t * fps))
        counts.append(end - done)
        done = end
    return counts


def _shot_frames(plate: Image.Image, shot: Shot, size: tuple[int, int], fps: int,
                 depth: np.ndarray | None = None, parallax_px: float = 0.0, frames: int | None = None):
    """Frames of one shot. With a depth map (relative to the full page) near pixels also slide sideways across the
    shot, so a still gains layers; without one this is the plain camera move."""
    traj = compute_camera_trajectory(shot.move, (frames / fps) if frames else shot.duration, fps)
    aspect = size[0] / size[1]
    last = max(1, len(traj.keyframes) - 1)
    depth_img = Image.fromarray(depth) if depth is not None else None
    for i, kf in enumerate(traj.keyframes):
        win = camera_window(shot.box, aspect, kf.zoom, _pan_value(shot.move, kf))
        frame = plate.resize(size, Image.Resampling.BICUBIC, box=win)
        if depth_img is not None:
            d = np.asarray(depth_img.resize(size, Image.Resampling.BILINEAR, box=win))
            frame = parallax_warp(frame, d, parallax_px * (2.0 * i / last - 1.0))
        yield frame


@dataclass(slots=True)
class BuildResult:
    video: Path
    srt: Path
    duration: float
    shots: int
    cues: list[tuple[float, float, str]]


def _mix_audio(shots: list[Shot], timings: list[Any], offset: float, total: float, path: Path, rate: int = 24000) -> None:
    import soundfile as sf

    out = np.zeros(int(total * rate) + rate, dtype=np.float32)
    by_block = {t.block_index: t for t in timings}
    t0 = offset
    for shot in shots:
        for ln in shot.lines:
            data, sr = sf.read(by_block[ln.block_index].audio_path, dtype="float32", always_2d=True)
            mono = data.mean(axis=1)
            if sr != rate:
                mono = np.interp(np.linspace(0, len(mono), int(len(mono) * rate / sr), endpoint=False),
                                 np.arange(len(mono)), mono).astype(np.float32)
            a = int((t0 + ln.offset) * rate)
            out[a:a + len(mono)] += mono[: len(out) - a]
        t0 += shot.duration
    sf.write(str(path), out, rate)


def build_episode(
    und: ComicUnderstanding,
    pages: list[PageImage],
    timings: list[Any],
    out_dir: Path,
    *,
    title: str,
    credit: str,
    inpainter: Inpainter | None = None,
    masks_dir: Path | None = None,
    size: tuple[int, int] = (1280, 720),
    fps: int = 24,
    video_name: str = "episode.mp4",
    depth: DepthEstimator | None = None,
    parallax_px: float = 14.0,
) -> BuildResult:
    """Render the motion comic to `out_dir/<video_name>` with a sidecar `.srt` of the original lettering."""
    out_dir.mkdir(parents=True, exist_ok=True)
    plates: dict[int, Image.Image] = {}
    for pg in und.pages:
        img = next(p.image for p in pages if p.index == pg.page_index).convert("RGB")
        if inpainter is not None and pg.mask_file and masks_dir is not None:
            img = inpainter.inpaint(img, Image.open(masks_dir / pg.mask_file))
        plates[pg.page_index] = img
    depth_maps = {i: depth.depth(img) for i, img in plates.items()} if depth is not None else {}
    shots = plan_shots(und, timings)
    title_card = _card(size, [title])
    end_card = _card(size, ["Credits", *credit.split("\n")])
    body = sum(s.duration for s in shots)
    total = TITLE_SECONDS + body + CREDIT_SECONDS

    video = out_dir / video_name
    wav = out_dir / "episode_audio.wav"
    _mix_audio(shots, timings, TITLE_SECONDS, total, wav)
    cues: list[tuple[float, float, str]] = []
    by_block = {b.id: b for b in story_bubbles(und)}
    ordered_ids = [b.id for b in story_bubbles(und)]
    t0 = TITLE_SECONDS
    for shot in shots:
        for ln in shot.lines:
            b = by_block[ordered_ids[ln.block_index]]
            cues.append((t0 + ln.offset, t0 + ln.offset + ln.duration, b.text))
        t0 += shot.duration
    srt = out_dir / video.with_suffix(".srt").name
    srt.write_text(srt_text(cues), encoding="utf-8")

    # Encode to a temporary name and rename on success so a failed build never leaves a finished-looking, truncated
    # episode.mp4 in the version folder.
    partial = video.with_name(f"{video.stem}.partial{video.suffix}")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
           "-r", str(fps), "-i", "-", "-i", str(wav), "-i", str(srt), "-map", "0:v", "-map", "1:a", "-map", "2:s",
           *h264_args(), "-c:a", "aac", "-b:a", "160k", "-c:s", "mov_text",
           "-metadata", f"title={title}", "-metadata", f"comment={credit}", "-metadata", f"copyright={credit}",
           "-t", f"{total:.3f}", str(partial)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for _ in range(int(TITLE_SECONDS * fps)):
            proc.stdin.write(title_card.tobytes())
        for shot, n_frames in zip(shots, shot_frame_counts(shots, fps), strict=True):
            plate = plates[shot.page_index]
            for frame in _shot_frames(plate, shot, size, fps, depth_maps.get(shot.page_index), parallax_px, n_frames):
                proc.stdin.write(frame.tobytes())
        for _ in range(int(CREDIT_SECONDS * fps)):
            proc.stdin.write(end_card.tobytes())
    except BaseException:
        proc.stdin.close()
        proc.wait()
        partial.unlink(missing_ok=True)
        raise
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed with exit code {rc}")
    partial.replace(video)
    wav.unlink(missing_ok=True)
    return BuildResult(video, srt, total, len(shots), cues)
