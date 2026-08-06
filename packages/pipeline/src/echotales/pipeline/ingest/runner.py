"""Phase 0 orchestration: EPUB in, chapters and blocks in the store.

Streams chapter by chapter and commits in batches. The machine this runs on
has roughly 4.5 GB of free RAM and will later hold an NER model alongside this
work, so nothing here accumulates a whole novel in memory.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import BlockType
from echotales.core.models import Chapter
from echotales.core.store import Store
from echotales.pipeline.ingest.adapters import ChapterRange
from echotales.pipeline.ingest.normalize import HandoffReport, detect_translator_handoffs
from echotales.pipeline.ingest.sources import SourceConfig, get_source

log = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestReport:
    novel_id: str
    chapters: int = 0
    blocks: int = 0
    block_types: dict[str, int] = field(default_factory=dict)
    system_windows: int = 0
    italic_blocks: int = 0
    missing_chapters: list[float] = field(default_factory=list)
    handoffs: list[HandoffReport] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"{self.novel_id}: {self.chapters} chapters, {self.blocks} blocks",
            "  blocks by type: "
            + ", ".join(f"{k}={v}" for k, v in sorted(self.block_types.items())),
        ]
        if self.system_windows:
            lines.append(f"  system windows: {self.system_windows}")
        if self.italic_blocks:
            lines.append(f"  blocks carrying emphasis: {self.italic_blocks}")
        if self.missing_chapters:
            preview = ", ".join(f"{c:g}" for c in self.missing_chapters[:10])
            more = "" if len(self.missing_chapters) <= 10 else f" (+{len(self.missing_chapters) - 10})"
            lines.append(f"  MISSING chapters: {preview}{more}")
        for handoff in self.handoffs:
            lines.append(f"  possible translator handoff at ch {handoff.chapter:g}: {handoff.detail}")
        return "\n".join(lines)


def ingest_novel(
    novel_id: str,
    store: Store,
    *,
    sources_path: Path | str = "data/sources.toml",
    chapters: ChapterRange | None = None,
    commit_every: int = 25,
) -> IngestReport:
    """Ingest one novel into the store."""
    config = get_source(novel_id, sources_path)
    wanted = chapters or config.chapters
    return ingest_config(config, store, chapters=wanted, commit_every=commit_every)


def ingest_config(
    config: SourceConfig,
    store: Store,
    *,
    chapters: ChapterRange | None = None,
    commit_every: int = 25,
) -> IngestReport:
    # A SourceConfig that declares its own range is honoured unless the caller
    # overrides it explicitly. Ignoring it silently ingested all 500 chapters
    # of a novel configured for 199.
    wanted = chapters if chapters is not None else config.chapters

    report = IngestReport(novel_id=config.id)
    store.add_novel(config.id, config.title, str(config.path), config.adapter)

    epub, adapter = config.open_adapter()
    seen: list[float] = []
    try:
        for i, chapter in enumerate(adapter.chapters(wanted), start=1):
            store.add_chapter(chapter)
            _tally(report, chapter)
            seen.append(chapter.number)
            if i % commit_every == 0:
                store.conn.commit()
        store.conn.commit()
    finally:
        epub.close()

    report.chapters = len(seen)
    report.missing_chapters = _find_gaps(seen, wanted)
    report.handoffs = detect_translator_handoffs(store, config.id)
    return report


def _tally(report: IngestReport, chapter: Chapter) -> None:
    for block in chapter.blocks:
        report.blocks += 1
        key = block.block_type.value
        report.block_types[key] = report.block_types.get(key, 0) + 1
        if block.block_type is BlockType.SYSTEM_WINDOW:
            report.system_windows += 1
        if block.italic_ranges:
            report.italic_blocks += 1


def _find_gaps(seen: list[float], wanted: ChapterRange | None) -> list[float]:
    """Report chapters the range asked for but ingestion did not produce.

    Worth surfacing loudly: a silently skipped chapter is a hole in the
    discourse timeline, and every downstream position becomes subtly wrong
    rather than obviously broken.
    """
    if not seen:
        return []
    present = set(seen)
    lo = int(min(present)) if wanted is None else int(max(wanted.start, min(present)))
    hi = int(max(present)) if wanted is None else int(min(wanted.end, max(present)))
    if hi - lo > 100_000:
        return []
    return [float(n) for n in range(lo, hi + 1) if float(n) not in present]


def iter_ingested(store: Store, novel_id: str) -> Iterator[Chapter]:
    """Convenience re-export so callers need not import the store directly."""
    return store.iter_chapters(novel_id)
