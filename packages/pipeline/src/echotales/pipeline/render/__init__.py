"""Video assembly: panel images, reusable motion clips, and the compositor
that cuts them to the voice track (xyz.md Step 4, video-assembly revision).

`panels.py` renders one cached image per `(chapter, block_index)` from
`persona/prompt.py::build_image_prompt`. `motion.py` builds a small, reused
library of short motion clips. `director.py` decides, per block, whether the
camera pans/zooms on the still panel or cuts to a motion clip. `timeline.py`
turns that decision list into real start/end timestamps by reading the
already-rendered voice-line WAVs (`voice/runner.py`'s `manifest.jsonl`).
`compose.py` composites the result into one mp4 per chapter. `runner.py`
lands next -- see this module's docstring grow as it does.
"""

from __future__ import annotations

from echotales.pipeline.render.compose import ComposeEngine, get_engine as get_compose_engine
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
from echotales.pipeline.render.timeline import TimedShot, build_timeline

__all__ = [
    "ComposeEngine",
    "MotionClip",
    "MotionLibraryReport",
    "PanelImage",
    "PanelReport",
    "ShotPlan",
    "TimedShot",
    "build_motion_library",
    "build_shot_plan",
    "build_timeline",
    "get_compose_engine",
    "get_motion_engine",
    "get_panel_engine",
    "load_motion_library",
    "match_tag",
    "render_panels",
]
