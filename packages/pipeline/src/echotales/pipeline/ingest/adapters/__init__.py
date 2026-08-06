"""Per-source EPUB adapters, selected by name from `data/sources.toml`."""

from __future__ import annotations

from echotales.pipeline.ingest.adapters.base import (
    ChapterRange,
    RawBlock,
    SourceAdapter,
    extract_block,
    iter_block_elements,
)
from echotales.pipeline.ingest.adapters.calibre import CalibreAdapter
from echotales.pipeline.ingest.adapters.generic import GenericAdapter
from echotales.pipeline.ingest.adapters.lightnovelworld import LightNovelWorldAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    LightNovelWorldAdapter.name: LightNovelWorldAdapter,
    CalibreAdapter.name: CalibreAdapter,
    GenericAdapter.name: GenericAdapter,
}


def get_adapter(name: str) -> type[SourceAdapter]:
    """Look up an adapter class by its `sources.toml` name."""
    try:
        return ADAPTERS[name]
    except KeyError:
        known = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"unknown adapter {name!r}; known adapters: {known}") from None


__all__ = [
    "ADAPTERS",
    "CalibreAdapter",
    "ChapterRange",
    "GenericAdapter",
    "LightNovelWorldAdapter",
    "RawBlock",
    "SourceAdapter",
    "extract_block",
    "get_adapter",
    "iter_block_elements",
]
