"""Timeline-driven Compositor for Path 1 Parallax & Manga Episodes.

Assembles multi-layer 2.5D parallax, eased camera motion, manga action grammar,
synchronized dialogue speech, SFX, and ducked background audio into finished vertical reels.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from echotales.pipeline.compositor.camera import (
    apply_parallax_transform,
    compute_camera_trajectory,
)
from echotales.pipeline.compositor.layers import (
    separate_image_layers,
)
from echotales.pipeline.compositor.manga import (
    create_impact_frame,
    create_radial_speedlines,
    generate_camera_shake_offsets,
    render_onomatopoeia_overlay,
)
from echotales.pipeline.screenplay.schema import CameraMove


@dataclass(slots=True)
class CompositionShotSpec:
    """Storyboarded shot specification for 2.5D composition."""

    shot_index: int
    duration_s: float
    keyframe_path: str
    dialogue_audio_path: str | None = None
    sfx_paths: list[str] = field(default_factory=list)
    onomatopoeia: str | None = None
    camera_move: CameraMove = CameraMove.STATIC
    audio_peaks: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_index": self.shot_index,
            "duration_s": self.duration_s,
            "keyframe_path": self.keyframe_path,
            "dialogue_audio_path": self.dialogue_audio_path,
            "sfx_paths": list(self.sfx_paths),
            "onomatopoeia": self.onomatopoeia,
            "camera_move": str(self.camera_move),
            "audio_peaks": list(self.audio_peaks),
        }


@dataclass(slots=True)
class RenderedEpisodeOutput:
    """The result of episode timeline assembly."""

    output_video_path: str
    duration_s: float
    width: int
    height: int
    fps: int
    num_shots: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_video_path": self.output_video_path,
            "duration_s": round(self.duration_s, 3),
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "num_shots": self.num_shots,
        }


def _render_layer_transformed(
    img: Image.Image,
    width: int,
    height: int,
    zoom: float,
    pan_x: float,
    pan_y: float,
    dx_px: float = 0.0,
    dy_px: float = 0.0,
) -> Image.Image:
    """Scale, translate and crop a layer onto the target viewport."""
    scaled_w = max(width, int(round(width * zoom)))
    scaled_h = max(height, int(round(height * zoom)))

    # Resize layer
    scaled = img.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)

    # Base center crop
    base_cx = (scaled_w - width) // 2
    base_cy = (scaled_h - height) // 2

    # Apply pan offsets and shake
    offset_x = int(round(pan_x * width + dx_px))
    offset_y = int(round(pan_y * height + dy_px))

    crop_x1 = max(0, min(scaled_w - width, base_cx + offset_x))
    crop_y1 = max(0, min(scaled_h - height, base_cy + offset_y))

    return scaled.crop((crop_x1, crop_y1, crop_x1 + width, crop_y1 + height))


def compose_shot_2_5d(
    spec: CompositionShotSpec,
    output_dir: Path | str,
    *,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    max_frames_override: int | None = None,
) -> str:
    """Compose multi-plane 2.5D parallax motion with manga grammar and audio for a single shot."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / f"frames_shot_{spec.shot_index:03d}"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # 1. Layer Separation
    layers = separate_image_layers(
        spec.keyframe_path,
        out_dir / f"layers_shot_{spec.shot_index:03d}",
        shot_index=spec.shot_index,
    )

    bg_img = Image.open(layers.background_layer.image_path).convert("RGBA")
    subj_img = Image.open(layers.subject_layer.image_path).convert("RGBA")

    # 2. Camera Trajectory & Shakes
    trajectory = compute_camera_trajectory(spec.camera_move, spec.duration_s, fps=fps)
    shake_offsets = generate_camera_shake_offsets(
        spec.audio_peaks, spec.duration_s, fps=fps
    )

    # 2x Oversampling: render internally at 2x resolution and downscale to eliminate slow-pan stutter
    internal_w = width * 2
    internal_h = height * 2

    # Overlays at 2x
    speedlines_overlay = (
        create_radial_speedlines(internal_w, internal_h) if spec.audio_peaks else None
    )
    onomatopoeia_overlay = (
        render_onomatopoeia_overlay(spec.onomatopoeia, internal_w, internal_h)
        if spec.onomatopoeia
        else None
    )
    impact_frame_img = (
        create_impact_frame(internal_w, internal_h) if spec.audio_peaks else None
    )

    total_frames = len(trajectory.keyframes)
    if max_frames_override is not None:
        total_frames = min(total_frames, max_frames_override)

    peak_frames = {int(round(p * fps)) for p in spec.audio_peaks}

    for f_idx in range(total_frames):
        kf = trajectory.keyframes[f_idx]
        dx_shake, dy_shake = shake_offsets[f_idx] if f_idx < len(shake_offsets) else (0.0, 0.0)

        # Impact frame flash cut: 2 frames at peak
        if (
            impact_frame_img
            and (f_idx in peak_frames or (f_idx - 1) in peak_frames)
        ):
            frame_path = frames_dir / f"frame_{f_idx:05d}.png"
            impact_frame_img.resize((width, height), Image.Resampling.LANCZOS).save(frame_path, "PNG")
            continue

        # Parallax background at 2x
        bg_zoom, bg_pan_x, bg_pan_y = apply_parallax_transform(
            layers.background_layer, kf
        )
        frame_bg = _render_layer_transformed(
            bg_img, internal_w, internal_h, bg_zoom, bg_pan_x, bg_pan_y, dx_shake * 0.5, dy_shake * 0.5
        )

        # Parallax subject at 2x
        subj_zoom, subj_pan_x, subj_pan_y = apply_parallax_transform(
            layers.subject_layer, kf
        )
        frame_subj = _render_layer_transformed(
            subj_img, internal_w, internal_h, subj_zoom, subj_pan_x, subj_pan_y, dx_shake, dy_shake
        )

        # Composite subject over background
        composited = frame_bg.copy()
        composited.paste(frame_subj, (0, 0), frame_subj)

        # Overlay speed lines during peaks
        if speedlines_overlay and any(abs(f_idx - pf) <= 6 for pf in peak_frames):
            composited.paste(speedlines_overlay, (0, 0), speedlines_overlay)

        # Overlay onomatopoeia
        if onomatopoeia_overlay:
            composited.paste(onomatopoeia_overlay, (0, 0), onomatopoeia_overlay)

        # Downscale 2x render to target output resolution (eliminates panning stutter)
        frame_path = frames_dir / f"frame_{f_idx:05d}.png"
        final_frame = composited.resize((width, height), Image.Resampling.LANCZOS)
        final_frame.save(frame_path, "PNG")

    # 3. Assemble with FFmpeg into MP4 with SFX and dialogue audio mixing
    out_video_path = out_dir / f"shot_{spec.shot_index:03d}.mp4"

    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame_%05d.png"),
    ]

    has_audio = spec.dialogue_audio_path and Path(spec.dialogue_audio_path).exists()
    valid_sfx = [s for s in spec.sfx_paths if Path(s).exists()]

    if has_audio and valid_sfx:
        cmd.extend(["-i", str(spec.dialogue_audio_path)])
        for sfx in valid_sfx:
            cmd.extend(["-i", str(sfx)])
        n_inputs = 1 + len(valid_sfx)
        cmd.extend(["-filter_complex", f"amix=inputs={n_inputs}:duration=longest:dropout_transition=2", "-c:a", "aac", "-b:a", "192k"])
    elif has_audio:
        cmd.extend(["-i", str(spec.dialogue_audio_path)])
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
    elif valid_sfx:
        for sfx in valid_sfx:
            cmd.extend(["-i", str(sfx)])
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-t", str(spec.duration_s)])
    else:
        cmd.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=24000"])
        cmd.extend(["-c:a", "aac", "-t", str(spec.duration_s)])

    cmd.extend([
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "ultrafast",
        str(out_video_path),
    ])

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return str(out_video_path)


def compose_episode(
    shots: list[CompositionShotSpec],
    output_path: Path | str,
    *,
    bgm_path: str | None = None,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    max_frames_per_shot: int | None = None,
) -> RenderedEpisodeOutput:
    """Concatenate composed shots and apply audio mixing for the final episode."""
    if not shots:
        raise ValueError("Cannot compose episode: shots list is empty")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        shot_video_paths: list[str] = []
        total_duration = 0.0

        for shot_spec in shots:
            shot_mp4 = compose_shot_2_5d(
                shot_spec,
                tmp_path,
                fps=fps,
                width=width,
                height=height,
                max_frames_override=max_frames_per_shot,
            )
            shot_video_paths.append(shot_mp4)
            total_duration += shot_spec.duration_s

        # Concat list file for ffmpeg
        concat_txt = tmp_path / "concat.txt"
        with concat_txt.open("w") as f:
            for p in shot_video_paths:
                f.write(f"file '{p}'\n")

        # FFmpeg concatenation
        concat_video = tmp_path / "raw_concat.mp4" if (bgm_path and Path(bgm_path).exists()) else out_file
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-c",
            "copy",
            str(concat_video),
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # Mix and duck BGM under dialogue if provided
        if bgm_path and Path(bgm_path).exists():
            cmd_bgm = [
                "ffmpeg",
                "-y",
                "-i",
                str(concat_video),
                "-i",
                str(bgm_path),
                "-filter_complex",
                "[1:a]volume=0.20[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(out_file),
            ]
            subprocess.run(cmd_bgm, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    return RenderedEpisodeOutput(
        output_video_path=str(out_file),
        duration_s=total_duration,
        width=width,
        height=height,
        fps=fps,
        num_shots=len(shots),
    )
