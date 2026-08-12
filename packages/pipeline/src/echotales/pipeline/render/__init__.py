"""Video assembly: panel images, reusable motion clips, and the compositor
that cuts them to the voice track (xyz.md Step 4, video-assembly revision).

`panels.py` renders one cached image per `(chapter, block_index)` from
`persona/prompt.py::build_image_prompt`. Later stages (`motion.py`,
`director.py`, `timeline.py`, `compose.py`, `runner.py`) land incrementally
-- see this module's docstring grow as they do.
"""

from __future__ import annotations

from echotales.pipeline.render.panels import (
    PanelImage,
    PanelReport,
    get_engine as get_panel_engine,
    render_panels,
)

__all__ = [
    "PanelImage",
    "PanelReport",
    "get_panel_engine",
    "render_panels",
]
