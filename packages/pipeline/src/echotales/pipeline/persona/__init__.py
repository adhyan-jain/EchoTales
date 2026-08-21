"""Phase 8 (partial): panel-casting data for image generation (xyz.md Step 4).

See `attire.py` for the 4-tier prompt-infilling fallback and `runner.py` for
`get_panel_cast`, which assembles one panel's worth of visual casting data
(foreground characters, background mobs, environment) from what the graph
and `spans/scene.py`'s active-scene registry already know.

`build.py` is the persona-construction stage (Section 10 item 4): it mints one
`Persona` per character entity, binds it to its `Self`, and writes a trait
profile as `Attribute` rows under `TargetKind.PERSONA`. `traits.py` defines
the vocabulary those profiles use, and `extract.py` is the optional model
read that refines a deterministic profile.

**Scope note, still true:** one persona per self. The self/persona split
exists so reincarnation and sustained disguise can put *two* personas on one
self, and deciding that a second body exists is an identity-resolution
question this stage sits downstream of -- `resolve/` decides who is whom.
What is built here makes the common case real, not the flagship case.
"""

from __future__ import annotations

from echotales.pipeline.persona.attire import resolve_attire
from echotales.pipeline.persona.build import (
    PersonaReport,
    build_personas,
    load_trait_profiles,
)
from echotales.pipeline.persona.runner import CharacterCast, MobCast, PanelCast, get_panel_cast
from echotales.pipeline.persona.traits import TraitProfile, infer_traits_deterministic

__all__ = [
    "CharacterCast",
    "MobCast",
    "PanelCast",
    "PersonaReport",
    "TraitProfile",
    "build_personas",
    "get_panel_cast",
    "infer_traits_deterministic",
    "load_trait_profiles",
    "resolve_attire",
]
