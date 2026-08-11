"""Phase 8 (partial): panel-casting data for image generation (xyz.md Step 4).

See `attire.py` for the 4-tier prompt-infilling fallback and `runner.py` for
`get_panel_cast`, which assembles one panel's worth of visual casting data
(foreground characters, background mobs, environment) from what the graph
and `spans/scene.py`'s active-scene registry already know.

**Scope note, read before extending:** `Persona` (`core/models.py`) has no
runner anywhere in this codebase -- nothing ever constructs one, so there is
no `SelfPersonaBinding` data and no `Attribute` rows routed to
`TargetKind.PERSONA` to look up explicit appearance/attire. `get_panel_cast`
therefore accepts explicit-trait lookups as optional caller-supplied maps
(`persona_id_by_self`, `mob_faction`) rather than querying the store for
them directly -- the plumbing is real and forward-compatible, but tier 1 of
the fallback chain (`attire.py::resolve_attire`) is unreachable until a
persona-construction stage exists to populate it. Until then this module
only ever produces tier 2-4 output (faction / regional / novel-style
defaults), which is still useful for a background-heavy panel but is not
yet a substitute for a real character reference sheet.
"""

from __future__ import annotations

from echotales.pipeline.persona.attire import resolve_attire
from echotales.pipeline.persona.runner import CharacterCast, MobCast, PanelCast, get_panel_cast

__all__ = [
    "CharacterCast",
    "MobCast",
    "PanelCast",
    "get_panel_cast",
    "resolve_attire",
]
