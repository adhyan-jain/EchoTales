"""Eased camera motion paths and 2.5D parallax projection math.

Provides smooth cubic Bézier easing for camera push-ins, pull-outs, pans, and tilts,
with depth-proportional scaling to eliminate subpixel micro-stutter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from echotales.pipeline.compositor.layers import ImageLayer
from echotales.pipeline.screenplay.schema import CameraMove


@dataclass(slots=True)
class CameraKeyframe:
    """Camera state at a specific point in time."""

    time_s: float
    zoom: float  # Scale factor >= 1.0
    pan_x: float  # Normalized horizontal offset [-0.5, 0.5]
    pan_y: float  # Normalized vertical offset [-0.5, 0.5]
    blur_radius: float = 0.0  # Rack focus blur in pixels

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_s": round(self.time_s, 4),
            "zoom": round(self.zoom, 4),
            "pan_x": round(self.pan_x, 4),
            "pan_y": round(self.pan_y, 4),
            "blur_radius": round(self.blur_radius, 2),
        }


@dataclass(slots=True)
class CameraTrajectory:
    """Full time-indexed camera trajectory for a shot."""

    camera_move: CameraMove
    duration_s: float
    fps: int
    keyframes: list[CameraKeyframe]

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_move": str(self.camera_move),
            "duration_s": self.duration_s,
            "fps": self.fps,
            "keyframes": [kf.to_dict() for kf in self.keyframes],
        }


def cubic_bezier(
    t: float,
    p1: tuple[float, float] = (0.42, 0.0),
    p2: tuple[float, float] = (0.58, 1.0),
) -> float:
    """Evaluate cubic Bézier easing curve at normalized progress t in [0.0, 1.0].
    
    Default curve is standard ease-in-out.
    """
    t_clamped = max(0.0, min(1.0, t))
    # Approximation of cubic bezier progress for monotonic ease curve
    # B(t) = 3(1-t)^2 t y1 + 3(1-t) t^2 y2 + t^3
    y1 = p1[1]
    y2 = p2[1]
    one_minus_t = 1.0 - t_clamped
    val = (
        3.0 * (one_minus_t**2) * t_clamped * y1
        + 3.0 * one_minus_t * (t_clamped**2) * y2
        + (t_clamped**3)
    )
    return max(0.0, min(1.0, val))


def compute_camera_trajectory(
    camera_move: CameraMove,
    duration_s: float,
    fps: int = 30,
) -> CameraTrajectory:
    """Compute per-frame camera keyframes for a shot motion primitive."""
    total_frames = max(1, int(round(duration_s * fps)))
    keyframes: list[CameraKeyframe] = []

    for f in range(total_frames):
        t_sec = f / float(fps)
        prog = f / float(max(1, total_frames - 1))
        eased = cubic_bezier(prog)

        zoom = 1.0
        pan_x = 0.0
        pan_y = 0.0
        blur = 0.0

        if camera_move == CameraMove.SLOW_PUSH_IN:
            # Eases from 1.00 to 1.12
            zoom = 1.0 + 0.12 * eased
        elif camera_move == CameraMove.PULL_OUT:
            # Eases from 1.12 to 1.00
            zoom = 1.12 - 0.12 * eased
        elif camera_move == CameraMove.PAN_LEFT:
            # Eases from +0.05 to -0.05
            pan_x = 0.05 - 0.10 * eased
            zoom = 1.06
        elif camera_move == CameraMove.PAN_RIGHT:
            # Eases from -0.05 to +0.05
            pan_x = -0.05 + 0.10 * eased
            zoom = 1.06
        elif camera_move == CameraMove.TILT_UP:
            # Eases from +0.05 to -0.05
            pan_y = 0.05 - 0.10 * eased
            zoom = 1.06
        elif camera_move == CameraMove.TILT_DOWN:
            # Eases from -0.05 to +0.05
            pan_y = -0.05 + 0.10 * eased
            zoom = 1.06
        elif camera_move == CameraMove.RACK_FOCUS:
            zoom = 1.04
            # Rack blur transitions from 4.0px to 0.0px
            blur = 4.0 * (1.0 - eased)
        elif camera_move == CameraMove.IMPACT_SHAKE:
            # Fast decaying high-frequency oscillation
            decay = math.exp(-6.0 * prog)
            oscillation = math.sin(prog * 40.0 * math.pi)
            pan_x = 0.03 * decay * oscillation
            pan_y = 0.03 * decay * math.cos(prog * 30.0 * math.pi)
            zoom = 1.08 + 0.04 * decay
        else:  # STATIC
            zoom = 1.0
            pan_x = 0.0
            pan_y = 0.0

        keyframes.append(
            CameraKeyframe(
                time_s=t_sec,
                zoom=zoom,
                pan_x=pan_x,
                pan_y=pan_y,
                blur_radius=blur,
            )
        )

    return CameraTrajectory(
        camera_move=camera_move,
        duration_s=duration_s,
        fps=fps,
        keyframes=keyframes,
    )


def apply_parallax_transform(
    layer: ImageLayer,
    keyframe: CameraKeyframe,
) -> tuple[float, float, float]:
    """Calculate effective (zoom, pan_x, pan_y) for a layer given its z_depth.
    
    Depth scaling:
    - Foreground (z < 1.0) moves faster than subject.
    - Subject (z = 1.0) moves at base camera speed.
    - Background (z > 1.0) moves slower than subject.
    """
    z = max(0.1, layer.z_depth)
    eff_pan_x = keyframe.pan_x / z
    eff_pan_y = keyframe.pan_y / z
    eff_zoom = 1.0 + (keyframe.zoom - 1.0) / z
    return (eff_zoom, eff_pan_x, eff_pan_y)
