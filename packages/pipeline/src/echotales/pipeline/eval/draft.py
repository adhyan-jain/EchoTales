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

**That guard is now implemented** (`AmbiguousSurfaceError`, 2026-09-23,
EVOLUTION 4.79), because it is the blocking prerequisite for drafting gold
over a whole volume rather than five chapters: at volume scale "the clan head"
and a bare surname stop being unique, and a silent first-match pick would
mislabel every later occurrence while looking exactly like a clean expansion.
A surface listed under two identities, or under both `identity` and
`not_entity`, or marked `ambiguous = true`, raises instead of expanding.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.eval.gold import GoldMention, GoldSet, MentionKind, Provenance


class AmbiguousSurfaceError(ValueError):
    """A surface in the draft cannot be expanded to every occurrence.

    Raised rather than warned. A warning would leave a JSONL file on disk that
    looks like gold, scores like gold, and is wrong for every occurrence after
    the first referent -- and `eval/gold.py`'s provenance contract cannot
    detect it, because the records are perfectly well-formed
    (cf. EVOLUTION 4.74, where the only thing wrong with 6,952 records was a
    fact no scorer could see).
    """


def _assert_unambiguous(path: Path | str, raw: dict[str, object]) -> None:
    """Refuse any surface whose referent this format cannot express.

    Three ways a draft can be ambiguous, all of them real at volume scale:
    the same surface under two identities; the same surface claimed as both an
    identity and a non-entity; or a surface the drafter has explicitly flagged
    `ambiguous = true` because they saw it used for two people and had no way
    to say so.
    """
    owners: dict[str, list[str]] = {}
    flagged: list[tuple[str, str]] = []

    for entry in raw.get("identity", []):  # type: ignore[union-attr]
        identity = entry["name"]
        for surface in entry["surfaces"]:
            owners.setdefault(surface, []).append(identity)
            if entry.get("ambiguous"):
                flagged.append((surface, identity))
    for entry in raw.get("not_entity", []):  # type: ignore[union-attr]
        for surface in entry["surfaces"]:
            owners.setdefault(surface, []).append("(not_entity)")
            if entry.get("ambiguous"):
                flagged.append((surface, "(not_entity)"))

    problems = [
        f"surface {surface!r} is claimed by {len(claims)} referents: "
        + ", ".join(sorted(set(claims)))
        for surface, claims in sorted(owners.items())
        if len(set(claims)) > 1
    ]
    # Prefix collisions were fatal here until 2026-09-24. They were fatal for a
    # real reason -- they destroyed 55 of c1-c5's 343 records -- but the defect
    # was `GoldMention.key` dropping the surface, and that is now fixed, so two
    # records at one offset survive as two records. Listing both "Gu Yue" (the
    # clan) and "Gu Yue Fang Yuan" (a person) is a legitimate annotation of a
    # position where a clan name and a person's name genuinely both begin.
    # Still reported, because it is occasionally a slip, but no longer blocking.
    advisories = _prefix_collisions(owners)
    problems += [
        f"surface {surface!r} under {identity!r} is flagged ambiguous = true"
        for surface, identity in sorted(flagged)
    ]
    if advisories:
        for line in advisories:
            print(f"  note: {line}")
    if problems:
        raise AmbiguousSurfaceError(
            f"{path}: cannot expand to every occurrence -- "
            f"{len(problems)} ambiguous surface(s). This format assigns one "
            "referent per surface; these need occurrence-level drafting "
            "(explicit chapter+offset) instead.\n  " + "\n  ".join(problems)
        )


def _prefix_collisions(owners: dict[str, list[str]]) -> list[str]:
    """Surfaces that land two gold records on one offset. **Advisory since
    2026-09-24 -- no longer an error.**

    Two listed surfaces where one is a **word-boundary prefix** of the other
    ("Klein" and "Klein Moretti", "Sunday" and "Sunday school") both match at
    the same start offset. That used to be destructive: `GoldMention.key` was
    `(novel_id, chapter, offset)`, so the two records collapsed onto one key
    and the later silently overwrote the earlier -- 55 of c1-c5's 343
    annotations died that way at load time. The key now carries the
    normalised surface, so both records survive and the scorer's
    `_system_partition`, which already discriminated by surface, lines up
    with them.

    Kept as a report rather than deleted because the overlap is still worth a
    human glance -- usually deliberate (a clan name that prefixes its members'
    names), occasionally a slip.

    A *suffix* relation is harmless and common and is NOT flagged: "Fang Yuan"
    inside "Gu Yue Fang Yuan" starts 8 characters later, so the two records
    have different keys and both survive. That asymmetry is the whole reason
    this check is about prefixes specifically rather than about substrings.

    Found by drafting LOTM ch1-3 (2026-09-24): "Klein"/"Klein Moretti"
    produced 3 collisions and "Sunday"/"Sunday school" another 2, in a file
    that otherwise looked clean and expanded without a single warning.
    """
    surfaces = sorted(owners)
    out: list[str] = []
    for short in surfaces:
        for long in surfaces:
            if short == long or not long.startswith(short):
                continue
            # Only a *word-boundary* prefix collides. "Klein" prefixes "Kleiner"
            # as a string, but `_find_all`'s lookahead would never match it.
            if long[len(short)].isalnum() or long[len(short)] == "_":
                continue
            out.append(
                f"surface {short!r} is a word-boundary prefix of {long!r}: both "
                f"match at the same offset. Both records are kept (the gold key "
                f"carries the surface); check that annotating the same position "
                f"twice is what you meant."
            )
    return out


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
    # Before anything is read from the store: an ambiguous draft is a drafting
    # error, and reporting it should not depend on the novel being ingested.
    _assert_unambiguous(path, raw)
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
