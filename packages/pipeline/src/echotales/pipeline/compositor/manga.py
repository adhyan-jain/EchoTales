"""Manga Grammar Renderer: Impact frames, radial speedlines, screen shake, and onomatopoeia.

Provides high-energy comic action language synced with exclamation audio peaks:
1. High-contrast inverted impact frames (flash cuts for 2-3 frames).
2. Radial speed lines drawing focus to impact centers.
3. Audio peak triggered camera screen shake.
4. Bold manga onomatopoeia graphic overlays.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def create_impact_frame(
    width: int = 1080,
    height: int = 1920,
    style: str = "high_contrast_inverted",
) -> Image.Image:
    """Generate a high-contrast monochrome impact frame."""
    frame = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(frame)

    cx, cy = width // 2, height // 2
    # Draw intense dynamic jagged polygon explosion
    points: list[tuple[int, int]] = []
    n_spikes = 24
    for i in range(n_spikes):
        angle = i * (2 * math.pi / n_spikes)
        radius = (
            min(width, height) * 0.45
            if (i % 2 == 0)
            else min(width, height) * 0.15
        )
        x = int(cx + radius * math.cos(angle))
        y = int(cy + radius * math.sin(angle))
        points.append((x, y))

    draw.polygon(points, fill=(255, 255, 255, 255))
    # Inverted central core
    draw.ellipse(
        [cx - 60, cy - 60, cx + 60, cy + 60],
        fill=(0, 0, 0, 255),
    )
    return frame


def create_radial_speedlines(
    width: int = 1080,
    height: int = 1920,
    *,
    num_lines: int = 64,
    center: tuple[int, int] | None = None,
    inner_radius_ratio: float = 0.25,
) -> Image.Image:
    """Generate dynamic radial speed lines converging on a focal point."""
    lines_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(lines_img)

    cx = center[0] if center else width // 2
    cy = center[1] if center else height // 2
    diag = math.hypot(width, height)
    r_inner = diag * inner_radius_ratio
    r_outer = diag * 0.65

    rng = np.random.RandomState(42)
    for _ in range(num_lines):
        angle = rng.uniform(0.0, 2.0 * math.pi)
        line_w = rng.randint(2, 6)
        # Random outer offset
        r1 = r_inner * rng.uniform(0.9, 1.3)
        r2 = r_outer * rng.uniform(0.9, 1.2)

        x1 = int(cx + r1 * math.cos(angle))
        y1 = int(cy + r1 * math.sin(angle))
        x2 = int(cx + r2 * math.cos(angle))
        y2 = int(cy + r2 * math.sin(angle))

        # Alpha transparency for speedline
        alpha = rng.randint(180, 240)
        draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, alpha), width=line_w)

    return lines_img


def generate_camera_shake_offsets(
    peak_times: list[float],
    duration_s: float,
    fps: int = 30,
    *,
    shake_duration_s: float = 0.25,
    intensity_px: float = 24.0,
) -> list[tuple[float, float]]:
    """Compute per-frame screen shake offsets triggered at audio peak timestamps."""
    total_frames = max(1, int(round(duration_s * fps)))
    offsets: list[tuple[float, float]] = [(0.0, 0.0)] * total_frames

    for peak_t in peak_times:
        start_frame = int(round(peak_t * fps))
        shake_frames = int(round(shake_duration_s * fps))
        for sf in range(shake_frames):
            idx = start_frame + sf
            if 0 <= idx < total_frames:
                prog = sf / float(max(1, shake_frames))
                decay = math.exp(-5.0 * prog)
                dx = intensity_px * decay * math.sin(sf * 1.5 * math.pi)
                dy = intensity_px * decay * math.cos(sf * 1.8 * math.pi)
                cur_dx, cur_dy = offsets[idx]
                offsets[idx] = (cur_dx + dx, cur_dy + dy)

    return offsets


def render_onomatopoeia_overlay(
    text: str,
    width: int = 1080,
    height: int = 1920,
    *,
    position: tuple[int, int] = (540, 400),
    font_size: int = 96,
    angle_deg: float = -12.0,
) -> Image.Image:
    """Render stylized manga SFX text with thick outline and dynamic angle."""
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # Render text onto temporary transparent canvas
    txt_canvas = Image.new("RGBA", (width, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_canvas)

    try:
        # Try loading default font or PIL builtin
        font = ImageFont.load_default(size=font_size)
    except Exception:
        font = ImageFont.load_default()

    tx, ty = width // 4, 150
    # Bold black outline (8-directional shadow)
    outline_color = (0, 0, 0, 255)
    outline_thickness = 6
    for ox in range(-outline_thickness, outline_thickness + 1, 2):
        for oy in range(-outline_thickness, outline_thickness + 1, 2):
            draw.text((tx + ox, ty + oy), text, fill=outline_color, font=font)

    # Vibrant core fill (red/orange dynamic action color)
    fill_color = (255, 60, 40, 255)
    draw.text((tx, ty), text, fill=fill_color, font=font)

    # Rotate text by angle_deg
    rotated = txt_canvas.rotate(
        angle_deg,
        resample=Image.Resampling.BILINEAR,
        expand=True,
    )

    # Paste rotated onomatopoeia at desired target position
    paste_x = position[0] - rotated.width // 2
    paste_y = position[1] - rotated.height // 2
    overlay.paste(rotated, (paste_x, paste_y), rotated)

    return overlay
