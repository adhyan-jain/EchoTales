"""Video assembly: panel images, reusable motion clips, and the compositor
that cuts them to the voice track (xyz.md Step 4, video-assembly revision).

`panels.py` renders one cached image per `(chapter, block_index)` from
`persona/prompt.py::build_image_prompt`. `motion.py` builds a small, reused
library of short motion clips. `director.py` decides, per block, whether the
camera pans/zooms on the still panel or cuts to a motion clip. Later stages
(`timeline.py`, `compose.py`, `runner.py`) land incrementally -- see this
module's docstring grow as they do.
"""

from __future__ import annotations

from echotales.pipeline.render.director import ShotPlan, build_shot_plan
from echotales.pipeline.render.motion import (
    MotionClip,
    MotionLibraryReport,
    build_motion_library,
    get_engine as get_motion_engine,
    load_motion_library,
    match_tag,
)
from echotales.pipeline.render.panels import (
    PanelImage,
    PanelReport,
    get_engine as get_panel_engine,
    render_panels,
)

__all__ = [
    "MotionClip",
    "MotionLibraryReport",
    "PanelImage",
    "PanelReport",
    "ShotPlan",
    "build_motion_library",
    "build_shot_plan",
    "get_motion_engine",
    "get_panel_engine",
    "load_motion_library",
    "match_tag",
    "render_panels",
]
