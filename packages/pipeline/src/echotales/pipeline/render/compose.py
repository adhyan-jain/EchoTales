"""Compositor: a timed shot list + the rendered voice track -> one mp4 per
chapter (xyz.md Step 4, video revision -- the final stage).

**Same protocol/stub/real split as every other backend in this pipeline**
(`llm/`, `voice/engine.py`, `render/panels.py`, `render/motion.py`), and the
same reason: `StubComposeEngine` needs no `ffmpeg` on the machine and is
what CI runs, while `FfmpegComposeEngine` does the real encode. Unlike the
other stubs, this one cannot write a "real but placeholder" output in its
own format -- there is no dependency-free way to write an mp4 -- so instead
it does the one part of this stage that *is* dependency-free and worth
exercising for real: concatenating the actual WAV files into the chapter's
full audio track via the stdlib `wave` module, then writing a JSON sidecar
describing the shot list that would have been composited. That is still not
a no-op: `concatenate_audio` is exactly the audio half of what the real
engine does, and a broken concatenation would fail the same way in both.

**Still images become video via `zoompan`, one small ffmpeg call per shot,
then concatenated.** Concatenating first and applying one global filter
would be simpler, but each shot needs its own zoom/pan direction and its
own duration (locked to speech by `timeline.py`), so the filter graph has to
be per-shot regardless -- rendering each shot to its own segment first keeps
that filter graph simple enough to build as a plain string instead of a
single chapter-spanning `filter_complex`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from echotales.pipeline.render.timeline import TimedShot

#: **Portrait, because that is where this format is watched.** The reference
#: edits are all 9:16 phone-native; a 16:9 frame showing a portrait panel
#: pillarboxes it into a small rectangle in the middle of the screen and
#: throws away most of the display. Landscape stays available by passing the
#: dimensions through -- it is a preview format here, not the default.
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30

#: End-of-pan zoom factor. Modest on purpose -- a still illustration panned
#: too aggressively reveals its own resolution limits.
_MAX_ZOOM = 1.15


class ComposeEngine(Protocol):
    name: str

    def render(self, timeline: list[TimedShot], audio_paths: list[Path], out_path: Path) -> Path:
        """Composite `timeline` against the concatenation of `audio_paths`
        and write the result to `out_path`."""
        ...


def concatenate_audio(paths: list[Path], out_path: Path) -> Path:
    """Join WAV files at the sample level -- no `ffmpeg` needed for this part.

    Raises on mismatched format rather than resampling silently: every voice
    line in a run comes from the same engine at the same sample rate
    (`voice/engine.py`'s `TTSEngine.sample_rate`), so a mismatch here means
    the manifest points at files from two different runs, which is a bug
    worth surfacing, not papering over.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    real_paths = [p for p in paths if p.exists()]
    if not real_paths:
        with wave.open(str(out_path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(24000)
        return out_path

    with wave.open(str(real_paths[0]), "rb") as first:
        params = first.getparams()

    with wave.open(str(out_path), "wb") as out:
        out.setparams(params)
        for path in real_paths:
            with wave.open(str(path), "rb") as fh:
                if (fh.getnchannels(), fh.getsampwidth(), fh.getframerate()) != (
                    params.nchannels,
                    params.sampwidth,
                    params.framerate,
                ):
                    raise ValueError(
                        f"{path} has a different WAV format than {real_paths[0]} -- "
                        "manifest mixes audio from two different engine runs"
                    )
                out.writeframes(fh.readframes(fh.getnframes()))
    return out_path


@dataclass(slots=True)
class StubComposeEngine:
    name: str = "stub"
    # Same fields as the real engine so callers configure one interface. The
    # stub cannot burn captions into an mp4 it does not write, but it records
    # the path in its sidecar, which is what makes "were captions built at
    # all" checkable in CI without ffmpeg.
    width: int = OUTPUT_WIDTH
    height: int = OUTPUT_HEIGHT
    captions_path: Path | None = None

    def render(self, timeline: list[TimedShot], audio_paths: list[Path], out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        concatenate_audio(audio_paths, out_path.with_suffix(".wav"))
        if self.captions_path is not None:
            out_path.with_suffix(".captions.txt").write_text(
                str(self.captions_path), encoding="utf-8"
            )
        out_path.with_suffix(".shots.json").write_text(
            json.dumps([asdict(s) for s in timeline], indent=2), encoding="utf-8"
        )
        return out_path


def _zoompan_filter(
    shot: TimedShot,
    num_frames: int,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> str:
    direction = shot.pan_direction or "zoom_in"
    step = (_MAX_ZOOM - 1.0) / max(num_frames, 1)

    if direction == "zoom_in":
        z = f"min(zoom+{step:.6f},{_MAX_ZOOM})"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif direction == "zoom_out":
        z = f"if(eq(on,1),{_MAX_ZOOM},max(zoom-{step:.6f},1.0))"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    else:  # pan_left / pan_right at a constant, modest zoom
        z = f"{_MAX_ZOOM}"
        y = "ih/2-(ih/zoom/2)"
        progress = f"(on/{max(num_frames - 1, 1)})"
        x = (
            f"(iw-iw/zoom)*(1-{progress})" if direction == "pan_left"
            else f"(iw-iw/zoom)*{progress}"
        )

    # Scale-and-crop to the frame *before* the zoom/pan. A panel is
    # generated at 2:3 and the frame is 9:16, so the source is wider than
    # the frame: filling by height and cropping the sides is what gives a
    # horizontal pan somewhere to travel, instead of panning across bars.
    fill = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
    )
    return (
        f"{fill}zoompan=z='{z}':x='{x}':y='{y}':d={num_frames}:"
        f"s={width}x{height}:fps={OUTPUT_FPS}"
    )


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")


def _render_segment(
    shot: TimedShot,
    out_path: Path,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> None:
    num_frames = max(1, round(shot.duration * OUTPUT_FPS))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if shot.kind == "clip":
        frames_glob = str(Path(shot.asset_path) / "frame%04d.png")
        _run_ffmpeg(
            [
                "-stream_loop", "-1",
                "-framerate", "12",
                "-i", frames_glob,
                "-t", f"{shot.duration:.3f}",
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},fps={OUTPUT_FPS}",
                "-pix_fmt", "yuv420p",
                str(out_path),
            ]
        )
        return

    _run_ffmpeg(
        [
            "-loop", "1",
            "-i", shot.asset_path,
            "-vf", _zoompan_filter(shot, num_frames, width, height),
            "-t", f"{shot.duration:.3f}",
            "-pix_fmt", "yuv420p",
            str(out_path),
        ]
    )


@dataclass(slots=True)
class FfmpegComposeEngine:
    """The real compositor. Requires `ffmpeg` on `PATH`."""

    name: str = "ffmpeg"
    width: int = OUTPUT_WIDTH
    height: int = OUTPUT_HEIGHT
    #: Burnable subtitle track (`render/captions.py::write_ass`). The prose
    #: on screen is the point of this format, not an accessibility extra --
    #: see that module. Optional so a run without a voice manifest still
    #: composes.
    captions_path: Path | None = None

    def render(self, timeline: list[TimedShot], audio_paths: list[Path], out_path: Path) -> Path:
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg not found on PATH -- required by FfmpegComposeEngine")
        if not timeline:
            raise ValueError("empty timeline -- nothing to compose")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = out_path.parent / f"{out_path.stem}_segments"
        work_dir.mkdir(parents=True, exist_ok=True)

        segment_paths: list[Path] = []
        for i, shot in enumerate(timeline):
            segment_path = work_dir / f"seg{i:05d}.mp4"
            _render_segment(shot, segment_path, self.width, self.height)
            segment_paths.append(segment_path)

        concat_list = work_dir / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in segment_paths) + "\n", encoding="utf-8"
        )
        video_only = work_dir / "video.mp4"
        _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(video_only)])

        audio_path = work_dir / "audio.wav"
        concatenate_audio(audio_paths, audio_path)

        # Captions are burned in the same pass that muxes the audio, so the
        # chapter is encoded once rather than twice. Without them the video
        # stream is copied through untouched, which is why this is a branch
        # and not a filter that happens to be empty.
        mux: list[str] = ["-i", str(video_only), "-i", str(audio_path)]
        if self.captions_path is not None and Path(self.captions_path).exists():
            mux += ["-vf", f"ass={_escape_filter_path(Path(self.captions_path))}"]
            mux += ["-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p"]
        else:
            mux += ["-c:v", "copy"]
        mux += ["-c:a", "aac", "-shortest", str(out_path)]
        _run_ffmpeg(mux)
        return out_path


def _escape_filter_path(path: Path) -> str:
    """Quote a path for use inside an ffmpeg filter argument.

    Filter graphs treat `:`, `'`, `[`, `]` and `,` as syntax, and a
    scratch directory built from a novel id can contain any of them.
    """
    text = str(path.resolve())
    for char in ("\\", ":", "'", "[", "]", ","):
        text = text.replace(char, f"\\{char}")
    return f"'{text}'"


def get_engine(name: str = "stub", **kwargs: object) -> ComposeEngine:
    if name == "stub":
        return StubComposeEngine(**kwargs)  # type: ignore[arg-type]
    if name == "ffmpeg":
        return FfmpegComposeEngine(**kwargs)  # type: ignore[arg-type]
    raise ValueError(f"unknown compose engine {name!r}; expected 'stub' or 'ffmpeg'")
