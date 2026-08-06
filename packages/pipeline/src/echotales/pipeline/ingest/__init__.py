"""Phase 0: ingestion and cleaning.

EPUB in, classified blocks out. Deterministic -- no LLM is involved at this
stage, and everything here runs over the full novel in one streaming pass.
"""

from echotales.pipeline.ingest.adapters import (
    ChapterRange,
    SourceAdapter,
    get_adapter,
)
from echotales.pipeline.ingest.classify import (
    classify_block,
    is_system_window,
    parse_system_window,
)
from echotales.pipeline.ingest.epub import Epub, TocEntry, parse_chapter_label
from echotales.pipeline.ingest.normalize import (
    are_variants,
    comparison_key,
    detect_translator_handoffs,
    normalize_romanization,
    strip_honorifics,
)
from echotales.pipeline.ingest.runner import IngestReport, ingest_config, ingest_novel
from echotales.pipeline.ingest.sources import SourceConfig, get_source, load_sources

__all__ = [
    "ChapterRange",
    "Epub",
    "IngestReport",
    "SourceAdapter",
    "SourceConfig",
    "TocEntry",
    "are_variants",
    "classify_block",
    "comparison_key",
    "detect_translator_handoffs",
    "get_adapter",
    "get_source",
    "ingest_config",
    "ingest_novel",
    "is_system_window",
    "load_sources",
    "normalize_romanization",
    "parse_chapter_label",
    "parse_system_window",
    "strip_honorifics",
]
