"""Loading `data/sources.toml`.

Registering a novel is a config block naming an adapter, a path and a chapter
range. Nothing about adding a source should require touching code -- the third
novel in this project arrived after the ingestion layer was written, and that
is the normal case rather than the exception.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from echotales.pipeline.ingest.adapters import ChapterRange, SourceAdapter, get_adapter
from echotales.pipeline.ingest.epub import Epub


@dataclass(slots=True)
class SourceConfig:
    id: str
    title: str
    path: Path
    adapter: str
    chapters: ChapterRange | None = None
    lexicon: Path | None = None

    def open_adapter(self) -> tuple[Epub, SourceAdapter]:
        """Open the EPUB and build its adapter.

        Returns both so the caller can close the container when finished; the
        adapter holds a live zip handle.
        """
        epub = Epub(self.path)
        return epub, get_adapter(self.adapter)(epub, self.id)


def load_sources(path: Path | str = "data/sources.toml") -> dict[str, SourceConfig]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"sources config not found: {config_path}")

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    out: dict[str, SourceConfig] = {}
    for entry in data.get("novel", []):
        chapters = entry.get("chapters")
        lexicon = entry.get("lexicon")
        cfg = SourceConfig(
            id=entry["id"],
            title=entry.get("title", entry["id"]),
            path=Path(entry["path"]),
            adapter=entry.get("adapter", "generic"),
            chapters=ChapterRange.parse(chapters) if chapters else None,
            lexicon=Path(lexicon) if lexicon else None,
        )
        out[cfg.id] = cfg
    return out


def get_source(novel_id: str, path: Path | str = "data/sources.toml") -> SourceConfig:
    sources = load_sources(path)
    try:
        return sources[novel_id]
    except KeyError:
        known = ", ".join(sorted(sources)) or "(none configured)"
        raise KeyError(f"unknown novel {novel_id!r}; configured novels: {known}") from None
