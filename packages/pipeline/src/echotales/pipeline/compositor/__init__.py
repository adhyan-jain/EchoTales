"""Path 1 Layered Parallax & Manga Grammar Compositor (2.5D)."""

from echotales.pipeline.compositor.camera import (
    CameraKeyframe,
    CameraTrajectory,
    apply_parallax_transform,
    compute_camera_trajectory,
    cubic_bezier,
)
from echotales.pipeline.compositor.engine import (
    CompositionShotSpec,
    RenderedEpisodeOutput,
    compose_episode,
    compose_shot_2_5d,
)
from echotales.pipeline.compositor.layers import (
    ImageLayer,
    LayerType,
    SeparatedLayers,
    separate_image_layers,
)
from echotales.pipeline.compositor.manga import (
    create_impact_frame,
    create_radial_speedlines,
    generate_camera_shake_offsets,
    render_onomatopoeia_overlay,
)

__all__ = [
    "CameraKeyframe",
    "CameraTrajectory",
    "CompositionShotSpec",
    "ImageLayer",
    "LayerType",
    "RenderedEpisodeOutput",
    "SeparatedLayers",
    "apply_parallax_transform",
    "compose_episode",
    "compose_shot_2_5d",
    "compute_camera_trajectory",
    "create_impact_frame",
    "create_radial_speedlines",
    "cubic_bezier",
    "generate_camera_shake_offsets",
    "render_onomatopoeia_overlay",
    "separate_image_layers",
]
