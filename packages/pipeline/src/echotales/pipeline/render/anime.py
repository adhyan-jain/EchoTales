"""The shot composer: a shot plan, generated clips and held stills -> one chapter video.

`shots.plan_shots` decides what each panel gets; this module carries it out. A shot is HOLD (today's
pan-and-zoom still), ANIMATE (a generated clip, then its last frame held), or INTERPOLATE (a clip toward
the next panel, or toward a push-in derived from the shot's own panel). Whatever the model does, a shot's
picture lasts exactly as long as its audio: the frames of shot i are `round(end_i * fps) - round(start_i *
fps)`, so rounding cannot accumulate, and the held part of a shot is "whatever the shot needs minus the
clip as actually measured". The sum is checked against the audio and the run raises if it is off.

Every generated clip goes through `video/clip_gate.py`, which fails closed: a rejected clip, a clip that
did not arrive, or a gate that could not run all mean the shot plays as a held still with its camera
move, and `shots.jsonl` says which and why. The plan's DISSOLVE is played as a cut for now (recorded
per shot): a dissolve needs an overlap, and the concat path used here has none.

Clips are cached across runs under `<video>/ch<N>/clips/<key>.mp4`, outside the versioned directories, so
a new version regenerates nothing whose inputs did not change.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from echotales.pipeline import paths
from echotales.pipeline.render.captions import build_captions, write_ass
from echotales.pipeline.render.compose import (
    OUTPUT_FPS,
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    FfmpegComposeEngine,
    _render_segment,
    _run_ffmpeg,
)
from echotales.pipeline.render.plan import PANEL_PLAN_FILE, PanelPlan, load_panel_plan
from echotales.pipeline.render.shots import (
    DerivedEnd,
    ShotBudget,
    ShotMode,
    ShotSpec,
    VideoCapability,
    plan_shots,
    summarise,
)
from echotales.pipeline.render.timeline import TimedShot
from echotales.pipeline.screenplay.schema import CameraMove, Transition
from echotales.pipeline.video.clip_gate import GateReport, gate_clip
from echotales.pipeline.video.local import ClipEngine, ClipRequest, ClipResult, VideoEnvError
from echotales.pipeline.voice.timing import (
    TIMING_FILE,
    LineTiming,
    build_timing,
    chapter_dir,
    load_timing,
)
from PIL import Image


class AnimeRefusal(ValueError):
    """The chapter cannot be composed as asked; the message names the fix."""


class AnimeSyncError(RuntimeError):
    """The picture is not as long as the audio."""


_PAN = {
    CameraMove.SLOW_PUSH_IN: "zoom_in", CameraMove.PULL_OUT: "zoom_out",
    CameraMove.PAN_LEFT: "pan_left", CameraMove.PAN_RIGHT: "pan_right",
}


def pan_direction(move: CameraMove) -> str:
    """`compose._zoompan_filter` has zoom and pan only; a static, tilt or shake move plays as a push-in."""
    return _PAN.get(move, "zoom_in")


# --------------------------------------------------------------------------- images


def fit_image(image: Image.Image, width: int, height: int) -> Image.Image:
    """Centre-crop to the target aspect, then resize: the model takes the exact size, not a stretched panel."""
    image = image.convert("RGB")
    target = width / height
    w, h = image.size
    if abs(w / h - target) > 1e-3:
        if w / h > target:
            new_w = round(h * target)
            image = image.crop(((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h))
        else:
            new_h = round(w / target)
            image = image.crop((0, (h - new_h) // 2, w, (h - new_h) // 2 + new_h))
    return image.resize((width, height), Image.LANCZOS)


def render_derived_end(image: Image.Image, derived: DerivedEnd) -> Image.Image:
    """The push-in end frame: a 1/scale crop centred on (cx, cy), kept inside the frame, at the same size.

    This is the one end frame the probe showed a first-and-last-frame model can reach (SSIM 0.91): a crop
    of the start frame, not another drawing.
    """
    w, h = image.size
    cw, ch = max(1, round(w / derived.scale)), max(1, round(h / derived.scale))
    left = min(max(round(derived.cx * w - cw / 2), 0), w - cw)
    top = min(max(round(derived.cy * h - ch / 2), 0), h - ch)
    return image.crop((left, top, left + cw, top + ch)).resize((w, h), Image.LANCZOS)


# --------------------------------------------------------------------------- cache


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clip_key(
    *, start: bytes, end: bytes | None, derived: DerivedEnd | None, prompt: str, seed: int, frames: int,
    fps: int, width: int, height: int, engine_id: str, model_identity: str,
) -> str:
    """Everything that changes the pixels of a clip, so a rerun regenerates only what changed."""
    payload = {
        "start": _digest(start), "end": _digest(end) if end is not None else None,
        "derived": derived.model_dump() if derived is not None else None, "prompt": prompt, "seed": seed,
        "frames": frames, "fps": fps, "size": [width, height], "engine": engine_id, "model": model_identity,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:32]


# --------------------------------------------------------------------------- ffmpeg helpers


def count_frames(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return int(out.stdout.strip().split(",")[0])


def _frame_budget(shots: list[ShotSpec], fps: int) -> list[int]:
    """Frames per shot from rounded cumulative boundaries: they tile the chapter with no drift."""
    return [round(s.end * fps) - round(s.start * fps) for s in shots]


# --------------------------------------------------------------------------- outcome


@dataclass(slots=True)
class ShotOutcome:
    shot_index: int
    panel_id: str
    planned_mode: str
    #: hold | generated | cached | fallback
    final: str
    reason: str = ""
    clip_key: str | None = None
    frames: int = 0
    clip_frames: int = 0
    hold_frames: int = 0
    gate: dict | None = None
    seconds: dict[str, float] = field(default_factory=dict)
    peak_vram_gb: float | None = None
    transition_applied: str = "cut"
    dissolve_downgraded: bool = False


@dataclass(slots=True)
class AnimeResult:
    out_dir: Path
    video: Path
    outcomes: list[ShotOutcome]
    summary: dict


def latest_panels_version(panels_root: str | Path, chapter: float, novel_id: str = "<novel>") -> Path:
    """The newest `vN*` panel directory of the chapter under `panels_root` that has a panel plan."""
    base = Path(panels_root) / f"ch{chapter:g}"
    found: list[tuple[int, Path]] = []
    for d in base.iterdir() if base.is_dir() else []:
        m = re.match(r"v(\d+)", d.name)
        if d.is_dir() and m and (d / PANEL_PLAN_FILE).exists():
            found.append((int(m.group(1)), d))
    if not found:
        raise AnimeRefusal(
            f"no panel version of chapter {chapter:g} has a {PANEL_PLAN_FILE} under {base}. "
            "Renders made before the panel plan existed have none: render the chapter again "
            f"(`echotales render --novel {novel_id} --chapters {chapter:g}`) to write one."
        )
    return max(found)[1]


def _load_timing(audio_dir: Path, chapter: float) -> list[LineTiming]:
    try:
        timing = load_timing(audio_dir, chapter) if (chapter_dir(audio_dir, chapter) / TIMING_FILE).exists() \
            else build_timing(audio_dir, chapter)
    except FileNotFoundError as exc:
        raise AnimeRefusal(
            f"no voiced audio for chapter {chapter:g}: {exc}. Run `echotales voice --novel <id> "
            f"--chapters {chapter:g}` first."
        ) from exc
    if not timing:
        raise AnimeRefusal(
            f"{audio_dir} has no voiced lines for chapter {chapter:g}. Run `echotales voice --novel <id> "
            f"--chapters {chapter:g}` first."
        )
    return timing


# --------------------------------------------------------------------------- composer


def render_shots(
    *,
    panels_dir: str | Path,
    audio_dir: str | Path,
    out_root: str | Path,
    capability: VideoCapability,
    budget: ShotBudget,
    engine: ClipEngine | None = None,
    captions: bool = True,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
    suffix: str | None = None,
    emotions: dict[str, tuple[str, int]] | None = None,
) -> AnimeResult:
    """Plan, generate, gate and compose one chapter. `out_root` is `<novel>/video/ch<N>`."""
    panels_dir, audio_dir, out_root = Path(panels_dir), Path(audio_dir), Path(out_root)
    try:
        panels = load_panel_plan(panels_dir)
    except FileNotFoundError as exc:
        raise AnimeRefusal(
            f"{exc}. Renders made before the panel plan existed have none: render the chapter again to write one."
        ) from exc
    if not panels:
        raise AnimeRefusal(f"{panels_dir / PANEL_PLAN_FILE} is empty")
    chapter = panels[0].chapter
    timing = _load_timing(audio_dir, chapter)
    shots = plan_shots(panels, timing, capability, budget, emotions=emotions)
    if capability.can_generate and engine is None:
        raise AnimeRefusal(f"capability {capability.engine_id} can generate clips but no engine was given")

    by_id: dict[str, PanelPlan] = {p.panel_id: p for p in panels}

    def panel_image(panel_id: str) -> Path:
        return panels_dir / by_id[panel_id].image_path

    # ---- version directory name; created after generation so a refused engine leaves no empty version behind.
    n_planned = sum(1 for s in shots if s.mode is not ShotMode.HOLD)
    tag = suffix or f"anime-{capability.engine_id if n_planned else 'stills'}-{n_planned}clips"
    tag = re.sub(r"[^a-z0-9-]+", "-", tag.lower()).strip("-")
    out_root.mkdir(parents=True, exist_ok=True)
    out_dir = out_root / f"{paths.next_version(out_root)}_{tag}"
    cache_dir, inputs_dir, work_dir = out_root / "clips", out_root / "clips" / "inputs", out_root / "clips" / "work"
    for d in (cache_dir, inputs_dir, work_dir):
        d.mkdir(parents=True, exist_ok=True)

    outcomes: dict[int, ShotOutcome] = {
        s.shot_index: ShotOutcome(
            shot_index=s.shot_index, panel_id=s.panel_id, planned_mode=s.mode.value, final="hold",
            reason="planned hold" if s.mode is ShotMode.HOLD else "",
            transition_applied="cut", dissolve_downgraded=s.transition_to_next is Transition.DISSOLVE,
        )
        for s in shots
    }

    # ---- clip requests for every generating shot; cache hits skip the engine.
    w, h = capability.sizes[0] if capability.sizes else (width, height)
    prepared: dict[int, tuple[Image.Image, Image.Image | None, Path, str]] = {}  # idx -> start, end, clip path, key
    pending: list[ClipRequest] = []
    for s in shots:
        if s.mode is ShotMode.HOLD:
            continue
        o = outcomes[s.shot_index]
        try:
            assert engine is not None
            start_bytes = panel_image(s.panel_id).read_bytes()
            start_img = fit_image(Image.open(panel_image(s.panel_id)), w, h)
            end_img: Image.Image | None = None
            end_bytes: bytes | None = None
            if s.end_panel_id:
                end_bytes = panel_image(s.end_panel_id).read_bytes()
                end_img = fit_image(Image.open(panel_image(s.end_panel_id)), w, h)
            elif s.end_derived:
                end_img = render_derived_end(start_img, s.end_derived)
            frames = engine.snap_frames(s.frames)
            key = clip_key(
                start=start_bytes, end=end_bytes, derived=s.end_derived, prompt=s.motion_prompt, seed=s.seed,
                frames=frames, fps=capability.fps, width=w, height=h, engine_id=engine.engine_id,
                model_identity=engine.model_identity(),
            )
        except Exception as exc:
            o.final, o.reason = "fallback", f"inputs: {type(exc).__name__}: {exc}"
            continue
        o.clip_key = key
        clip_path = cache_dir / f"{key}.mp4"
        prepared[s.shot_index] = (start_img, end_img, clip_path, key)
        if clip_path.exists():
            o.final = "cached"
            continue
        start_png = inputs_dir / f"{key}_start.png"
        start_img.save(start_png)
        end_png = None
        if end_img is not None:
            end_png = inputs_dir / f"{key}_end.png"
            end_img.save(end_png)
        pending.append(ClipRequest(
            clip_id=key, start_image=start_png, end_image=end_png, prompt=s.motion_prompt, frames=frames,
            fps=capability.fps, width=w, height=h, seed=s.seed, output=work_dir / f"{key}.mp4",
        ))

    results: dict[str, ClipResult] = {}
    run_info: dict = {}
    if pending:
        assert engine is not None
        t0 = time.time()
        try:
            for r in engine.generate_clips(pending):
                results[r.clip_id] = r
        except Exception as exc:
            if isinstance(exc, VideoEnvError):
                raise
            for r in pending:
                results.setdefault(r.clip_id, ClipResult(r.clip_id, False, f"engine: {type(exc).__name__}: {exc}"))
        run_info = {"engine_seconds": round(time.time() - t0, 1), **getattr(engine, "last_run", {})}
    for s in shots:
        o = outcomes[s.shot_index]
        res = results.get(o.clip_key or "")
        if res is None:
            continue
        o.seconds, o.peak_vram_gb = dict(res.seconds), res.peak_vram_gb
        dest = cache_dir / f"{o.clip_key}.mp4"
        if res.ok and res.output and Path(res.output).exists():
            os.replace(res.output, dest)
            o.final = "generated"
        else:
            o.final, o.reason = "fallback", f"engine: {res.error or 'no clip returned'}"

    # ---- gate, then build segments shot by shot.
    segs_dir = out_dir / "segments"
    segs_dir.mkdir(parents=True)
    budget_frames = _frame_budget(shots, OUTPUT_FPS)
    segment_paths: list[Path] = []
    measured: list[int] = []

    def still(panel: Path, move: str, n: int, name: str, shot: ShotSpec) -> None:
        if n <= 0:
            return
        if not panel.exists():  # a held still of nothing would be a silent blank frame run
            raise FileNotFoundError(f"panel image {panel} (shot {shot.shot_index}) does not exist")
        p = segs_dir / name
        _render_segment(
            TimedShot(chapter=shot.chapter, block_index=shot.block_indexes[0], kind="pan", asset_path=str(panel),
                      start=0.0, end=n / OUTPUT_FPS, pan_direction=move),
            p, width, height, frames=n,
        )
        segment_paths.append(p)
        measured.append(count_frames(p))

    for s in shots:
        o, n = outcomes[s.shot_index], budget_frames[s.shot_index]
        base = f"s{s.shot_index:04d}"
        generated_ok = False
        if o.final in ("generated", "cached"):
            start_img, end_img, clip_path, key = prepared[s.shot_index]
            expected = engine.snap_frames(s.frames)  # type: ignore[union-attr]
            report: GateReport = gate_clip(clip_path, start_img, end_img, expected_frames=expected, width=w, height=h)
            o.gate = report.to_dict()
            if report.passed:
                generated_ok = True
            else:
                o.reason = "gate rejected: " + "; ".join(report.reasons)
                o.final = "fallback"
        if not generated_ok:
            if o.final not in ("hold", "fallback"):
                o.final = "fallback"
            move = pan_direction(s.fallback.camera_move if o.final == "fallback" else s.camera_move)
            still(panel_image(s.panel_id), move, n, f"{base}_hold.mp4", s)
            o.frames, o.hold_frames = n, n
            continue

        # A generated clip: re-time it to the output rate, then fill the rest of the shot's frames.
        clip_seg = segs_dir / f"{base}_clip.mp4"
        want = min(n, int(o.gate["frames"] * OUTPUT_FPS / capability.fps))
        _run_ffmpeg([
            "-i", str(clip_path), "-an", "-frames:v", str(want),
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={OUTPUT_FPS}",
            "-pix_fmt", "yuv420p", str(clip_seg),
        ])
        got = count_frames(clip_seg)
        rest = n - got
        if rest < 0:  # the re-timed clip ran past its shot: cut it to the shot
            trimmed = segs_dir / f"{base}_clip_trim.mp4"
            _run_ffmpeg(["-i", str(clip_seg), "-frames:v", str(n), "-pix_fmt", "yuv420p", str(trimmed)])
            clip_seg, got, rest = trimmed, count_frames(trimmed), 0
        o.clip_frames, o.hold_frames, o.frames = got, rest, got + rest
        if s.mode is ShotMode.INTERPOLATE and s.end_panel_id:
            # Hold the start panel, then play the clip so it lands on the next panel at the cut. zoom_out
            # ends at scale 1.0, the framing of the clip's first frame, so the hand-over is continuous.
            still(panel_image(s.panel_id), "zoom_out", rest, f"{base}_head.mp4", s)
            segment_paths.append(clip_seg)
            measured.append(got)
        else:
            segment_paths.append(clip_seg)
            measured.append(got)
            if rest > 0:
                last = segs_dir / f"{base}_last.png"
                _run_ffmpeg(["-i", str(clip_path), "-vf", f"select=eq(n\\,{o.gate['frames'] - 1})",
                             "-frames:v", "1", "-update", "1", str(last)])
                # zoom_in starts at scale 1.0, the framing of the clip's last frame.
                still(last, "zoom_in", rest, f"{base}_tail.mp4", s)

    # ---- sync proof, before anything is muxed.
    total_target = round(shots[-1].end * OUTPUT_FPS)
    video_frames = sum(measured)
    audio_seconds = shots[-1].end
    if video_frames != total_target:
        raise AnimeSyncError(
            f"picture is {video_frames} frames, the audio needs {total_target} "
            f"({audio_seconds:.3f} s at {OUTPUT_FPS} fps)"
        )
    for s in shots:
        o = outcomes[s.shot_index]
        if o.frames != budget_frames[s.shot_index]:
            raise AnimeSyncError(f"shot {s.shot_index}: {o.frames} frames, its audio window needs {budget_frames[s.shot_index]}")

    # ---- captions and mux, through the existing compositor path.
    compose = FfmpegComposeEngine(width=width, height=height)
    if captions:
        per_span = {t.span_id: t.duration for t in timing}
        cards = build_captions(list(timing), per_span)
        if cards:
            compose.captions_path = write_ass(cards, out_dir / f"ch{chapter:g}.ass", width=width, height=height)
    video = compose.assemble(segment_paths, [Path(t.audio_path) for t in timing], out_dir / f"ch{chapter:g}.mp4", segs_dir)
    final_frames = count_frames(video)
    # `-shortest` against the audio can drop the last frame (4667 of 4668 on a 155.6 s chapter); more than one
    # frame would mean the mux, not the plan, broke sync.
    if abs(final_frames - total_target) > 1:
        raise AnimeSyncError(f"muxed video is {final_frames} frames, the audio needs {total_target}")

    # ---- records.
    with (out_dir / "shots.jsonl").open("w", encoding="utf-8") as fh:
        for s in shots:
            row = json.loads(s.model_dump_json())
            row["outcome"] = asdict(outcomes[s.shot_index])
            fh.write(json.dumps(row) + "\n")
    finals = [o.final for o in outcomes.values()]
    summary = {
        **summarise(shots, capability),
        "engine": capability.engine_id, "panels_version": panels_dir.name, "out_dir": str(out_dir),
        "video": str(video), "final": {k: finals.count(k) for k in ("hold", "generated", "cached", "fallback")},
        "video_frames": final_frames, "segment_frames": video_frames, "expected_frames": total_target,
        "audio_seconds": round(audio_seconds, 3), "fps": OUTPUT_FPS,
        "dissolve_downgraded": sum(1 for o in outcomes.values() if o.dissolve_downgraded),
        "run": run_info,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    _append_versions(out_root, out_dir.name, summary, panels_dir.name, budget)
    return AnimeResult(out_dir=out_dir, video=video, outcomes=[outcomes[s.shot_index] for s in shots], summary=summary)


def _append_versions(out_root: Path, name: str, summary: dict, panels_version: str, budget: ShotBudget) -> None:
    path = out_root / "VERSIONS.md"
    if not path.exists():
        path.write_text(
            "# video version index\n\nOne entry per `echotales anime` run, written by the code at the same time "
            "as the directory. The verdict line is for a person; it says so until someone has watched it.\n",
            encoding="utf-8",
        )
    f = summary["final"]
    entry = (
        f"\n## {name} - {date.today().isoformat()}\n\n"
        f"**What was tried:** engine `{summary['engine']}` over panels `{panels_version}`: {summary['shots']} shots "
        f"(planned {summary['modes']}), {summary['clips']} clips planned within {budget.max_generated_seconds:g} s / "
        f"{budget.max_clips} clips, seed {budget.base_seed}. Final: {f['generated']} generated, {f['cached']} cached, "
        f"{f['fallback']} fell back to a held still, {f['hold']} planned holds. "
        f"{summary['dissolve_downgraded']} dissolves played as cuts. Picture {summary['video_frames']} frames at "
        f"{summary['fps']} fps against {summary['audio_seconds']} s of audio.\n\n"
        "**Verdict:** not yet watched by a person.\n"
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry)

