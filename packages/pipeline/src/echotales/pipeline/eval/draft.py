"""Expand a hand/model-readable TOML draft into per-occurrence gold JSONL.

The TOML format groups by *identity* ("Fang Yuan: surfaces = [...]"), which is
how a reader (human or model) naturally thinks about a chapter. The scorer
needs one record per *occurrence*, because two occurrences of one surface can
in principle denote different people and a coreference metric is defined over
mentions, not over surface forms.

This module is the seam between the two, and it is where a drafting error would
hide: expanding "Fang Yuan" to every occurrence of that string in the source
text is only correct because chapters 1-5 of this novel happen to use each
surface for exactly one referent (stated as a scope note in the draft file
itself). A later chapter range with a recurring "the elder" would need
occurrence-level drafting instead, and this expander would need to fail loudly
on an ambiguous surface rather than silently pick the first match.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.eval.gold import GoldMention, GoldSet, MentionKind, Provenance


def _find_all(text: str, surface: str) -> list[int]:
    """Word-boundary occurrences of `surface` in `text`."""
    pattern = re.compile(r"(?<!\w)" + re.escape(surface) + r"(?!\w)")
    return [m.start() for m in pattern.finditer(text)]


def expand_draft(path: Path | str, store: Store) -> GoldSet:
    """Read a TOML identity draft and expand it against the ingested chapters.

    Requires the novel to already be ingested (`echotales run` or `ingest`),
    since offsets are found by scanning the stored chapter text -- gold offsets
    must agree with whatever the pipeline itself considers chapter text, not
    with a copy pasted into the draft file.
    """
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    novel_id = raw["novel_id"]
    drafted_by = raw.get("drafted_by", "")
    chapters = raw.get("chapters", [])

    texts: dict[float, str] = {}
    for chapter in chapters:
        ch = store.get_chapter(novel_id, float(chapter))
        if ch is None:
            raise ValueError(
                f"{path}: chapter {chapter} not found for {novel_id!r} -- ingest first"
            )
        texts[float(chapter)] = ch.story_text

    mentions: list[GoldMention] = []
    warnings: list[str] = []

    for entry in raw.get("identity", []):
        identity = entry["name"]
        kind = MentionKind(entry.get("kind", "character"))
        for surface in entry["surfaces"]:
            hits_total = 0
            for chapter, text in texts.items():
                for offset in _find_all(text, surface):
                    hits_total += 1
                    mentions.append(
                        GoldMention(
                            novel_id=novel_id,
                            chapter=chapter,
                            offset=offset,
                            surface=surface,
                            identity=identity,
                            kind=kind,
                            context=text[max(0, offset - 60) : offset + len(surface) + 60],
                            provenance=Provenance.MODEL,
                            drafted_by=drafted_by,
                            confirmed=False,
                            note=entry.get("note", ""),
                        )
                    )
            if hits_total == 0:
                warnings.append(f"{identity!r} surface {surface!r}: zero occurrences found")

    for entry in raw.get("not_entity", []):
        reason = entry.get("reason", "")
        for surface in entry["surfaces"]:
            hits_total = 0
            for chapter, text in texts.items():
                for offset in _find_all(text, surface):
                    hits_total += 1
                    mentions.append(
                        GoldMention(
                            novel_id=novel_id,
                            chapter=chapter,
                            offset=offset,
                            surface=surface,
                            identity="",
                            kind=MentionKind.NOT_AN_ENTITY,
                            context=text[max(0, offset - 60) : offset + len(surface) + 60],
                            provenance=Provenance.MODEL,
                            drafted_by=drafted_by,
                            confirmed=False,
                            note=reason,
                        )
                    )
            if hits_total == 0:
                warnings.append(f"not_entity surface {surface!r}: zero occurrences found")

    if warnings:
        import sys

        print(f"warning: {path} — surfaces with zero matches in source text:", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)

    return GoldSet(novel_id, sorted(mentions, key=lambda m: (m.chapter, m.offset)))
