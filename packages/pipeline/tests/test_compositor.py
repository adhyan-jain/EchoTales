"""Unit tests for Path 1 Layered Parallax Compositor and Manga Grammar."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from echotales.pipeline.compositor.camera import (
    apply_parallax_transform,
    compute_camera_trajectory,
    cubic_bezier,
)
from echotales.pipeline.compositor.engine import (
    CompositionShotSpec,
    compose_episode,
    compose_shot_2_5d,
)
from echotales.pipeline.compositor.layers import (
    LayerType,
    separate_image_layers,
)
from echotales.pipeline.compositor.manga import (
    create_impact_frame,
    create_radial_speedlines,
    generate_camera_shake_offsets,
    render_onomatopoeia_overlay,
)
from echotales.pipeline.screenplay.schema import CameraMove


@pytest.fixture
def sample_keyframe(tmp_path: Path) -> Path:
    img_path = tmp_path / "test_keyframe.png"
    # Create valid 720x1280 image for fast testing
    img = Image.new("RGB", (720, 1280), (60, 80, 120))
    img.save(img_path, "PNG")
    return img_path


def test_cubic_bezier_easing() -> None:
    assert cubic_bezier(0.0) == pytest.approx(0.0)
    assert cubic_bezier(1.0) == pytest.approx(1.0)
    # Midpoint should have eased smoothly
    mid = cubic_bezier(0.5)
    assert 0.0 < mid < 1.0


def test_camera_trajectory_and_parallax_depth() -> None:
    traj = compute_camera_trajectory(CameraMove.SLOW_PUSH_IN, duration_s=1.0, fps=10)
    assert len(traj.keyframes) == 10
    assert traj.keyframes[0].zoom == pytest.approx(1.0)
    assert traj.keyframes[-1].zoom > 1.10

    # Test parallax transform with foreground, subject, and background depths
    kf = traj.keyframes[-1]
    from echotales.pipeline.compositor.layers import ImageLayer

    subj_layer = ImageLayer(LayerType.SUBJECT, "subj.png", z_depth=1.0)
    bg_layer = ImageLayer(LayerType.BACKGROUND, "bg.png", z_depth=2.0)
    fg_layer = ImageLayer(LayerType.FOREGROUND, "fg.png", z_depth=0.5)

    s_zoom, _, _ = apply_parallax_transform(subj_layer, kf)
    bg_zoom, _, _ = apply_parallax_transform(bg_layer, kf)
    fg_zoom, _, _ = apply_parallax_transform(fg_layer, kf)

    # Foreground moves fastest / scales most, background moves least
    assert fg_zoom > s_zoom > bg_zoom


def test_layer_separation(sample_keyframe: Path, tmp_path: Path) -> None:
    layers = separate_image_layers(
        sample_keyframe,
        tmp_path / "layers",
        shot_index=1,
    )

    assert Path(layers.subject_layer.image_path).exists()
    assert Path(layers.background_layer.image_path).exists()

    # Verify subject has alpha channel
    with Image.open(layers.subject_layer.image_path) as s_img:
        assert s_img.mode == "RGBA"


def test_manga_grammar_renders() -> None:
    w, h = 360, 640

    impact = create_impact_frame(w, h)
    assert impact.size == (w, h)
    assert impact.mode == "RGBA"

    speedlines = create_radial_speedlines(w, h, num_lines=16)
    assert speedlines.size == (w, h)
    assert speedlines.mode == "RGBA"

    shakes = generate_camera_shake_offsets([0.5], duration_s=1.0, fps=10)
    assert len(shakes) == 10
    # Shake at frame 5 should be non-zero
    assert shakes[5] != (0.0, 0.0)

    onomatopoeia = render_onomatopoeia_overlay("BOOM!", w, h, position=(180, 200), font_size=32)
    assert onomatopoeia.size == (w, h)


def test_compose_shot_and_episode(sample_keyframe: Path, tmp_path: Path) -> None:
    spec1 = CompositionShotSpec(
        shot_index=1,
        duration_s=0.2,
        keyframe_path=str(sample_keyframe),
        camera_move=CameraMove.SLOW_PUSH_IN,
        audio_peaks=[0.1],
        onomatopoeia="CRASH!",
    )
    spec2 = CompositionShotSpec(
        shot_index=2,
        duration_s=0.2,
        keyframe_path=str(sample_keyframe),
        camera_move=CameraMove.PAN_LEFT,
    )

    # Render shot 1 (using low frame count for fast test execution)
    shot1_mp4 = compose_shot_2_5d(
        spec1,
        tmp_path / "shot1",
        fps=10,
        width=360,
        height=640,
        max_frames_override=3,
    )
    assert Path(shot1_mp4).exists()
    assert Path(shot1_mp4).stat().st_size > 0

    # Render episode combining spec1 and spec2
    ep_out = compose_episode(
        [spec1, spec2],
        tmp_path / "episode.mp4",
        fps=10,
        width=360,
        height=640,
        max_frames_per_shot=3,
    )
    assert Path(ep_out.output_video_path).exists()
    assert Path(ep_out.output_video_path).stat().st_size > 0
    assert ep_out.num_shots == 2
