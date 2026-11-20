"""World knowledge: structured facts about every entity, not just people.

The graph types its entities (`TargetKind.LOCATION`/`ORGANIZATION`/`ITEM`)
and stores temporal facts about them, and until this package existed nothing
populated either for anything that was not a character's face. On a real
Reverend Insanity database that left 10 locations and 35 organisations
resolved, named, and entirely undescribed.

`schema.py` defines what is worth knowing per kind. The per-entity model
extraction that once filled it in (`extract.py`) was removed as unreferenced
(EVOLUTION 4.168); `context.py` builds the story context.
"""

from __future__ import annotations

from echotales.pipeline.world.context import (
    EntityBrief,
    StoryContext,
    story_context,
)
from echotales.pipeline.world.schema import KEYS_BY_KIND, keys_for

__all__ = [
    "KEYS_BY_KIND",
    "EntityBrief",
    "StoryContext",
    "keys_for",
    "story_context",
]
