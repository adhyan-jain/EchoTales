"""Automated Gold QA Annotation Builder for Web Novels.

Generates DRAFT (Provenance.MODEL, unconfirmed) GoldMention records for:
- reverend-insanity     (sources.toml: chapters 1-199)
- lord-of-the-mysteries (sources.toml: chapters 1-213, Vol. 1 "Clown")
- omniscient-readers-viewpoint (sources.toml: chapters 1-188)

These are candidates to be audited, never ground truth on their own -- see
eval/gold.py's module docstring.

**`identity_map`'s self-ids are only valid for the exact db_path they were
looked up against.** A `self<N>` id is assigned by a specific resolve run,
not a stable identifier -- rerunning ingest/resolve on the same novel (even
against the same source text) renumbers them. Reusing an identity_map built
for one DB against a different one does not fail loudly: `_extract_gold_from_db`
silently skips any target_id not in the map, so a stale map quietly produces
an empty or wrong-character gold set with no error (this happened here twice:
LOTM/ORV's original map, built against the small `det-*.db` runs, resolved to
unrelated entities -- e.g. "self3" was a location, not a character -- against
the full-volume DBs; and two of RI's five ids drifted after `data/echotales.db`
was rebuilt the same day). Before pointing a build_*_gold() function at a new
db_path, re-derive identity_map by looking up each character's current
self-id (`SELECT target_id, text, COUNT(*) FROM mention WHERE text LIKE
'%<name>%' GROUP BY target_id, text ORDER BY 3 DESC`), don't assume the old
map still applies.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from echotales.core.enums import AliasType
from echotales.core.store import Store
from echotales.pipeline.eval.coref_score import _block_starts
from echotales.pipeline.eval.gold import GoldMention, GoldSet, MentionKind, Provenance, read_gold, write_gold


def _extract_gold_from_db(
    db_path: Path | str,
    novel_id: str,
    identity_map: dict[str, str],
    kind_map: dict[str, MentionKind] | None = None,
) -> GoldSet:
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Database not found at {db_file}")

    store = Store(str(db_file))
    conn = sqlite3.connect(str(db_file))

    mentions: list[GoldMention] = []

    chapters = [row[0] for row in conn.execute("SELECT DISTINCT chapter FROM mention ORDER BY chapter").fetchall()]

    for ch_val in chapters:
        ch = float(ch_val)
        block_starts = _block_starts(store, novel_id, ch)

        rows = conn.execute(
            "SELECT text, target_id, block_index, offset, alias_type FROM mention WHERE chapter=? AND target_id IS NOT NULL AND target_id!=''",
            (ch,),
        ).fetchall()

        for text, target_id, block_idx, block_offset, alias_type_raw in rows:
            if target_id not in identity_map:
                continue

            identity_name = identity_map[target_id]
            abs_offset = block_starts.get(block_idx, 0) + block_offset

            alias_enum = AliasType.RIGID_NAME
            if alias_type_raw:
                try:
                    alias_enum = AliasType(alias_type_raw)
                except ValueError:
                    alias_enum = AliasType.RIGID_NAME

            kind = MentionKind.CHARACTER
            if kind_map and target_id in kind_map:
                kind = kind_map[target_id]

            mentions.append(
                GoldMention(
                    novel_id=novel_id,
                    chapter=ch,
                    offset=abs_offset,
                    surface=text,
                    identity=identity_name,
                    kind=kind,
                    alias_type=alias_enum,
                    context=f"{text} mentioned in chapter {ch:g}.",
                    # Extracted straight from the pipeline's own resolved `mention`
                    # table (target_id/offset/alias_type are all pipeline output) --
                    # it is a draft to be audited, never ground truth. See
                    # eval/gold.py's module docstring: a label expressed in the
                    # system's own ids can only ever agree with it, and a recall
                    # number computed from model-drafted labels stops being a
                    # measurement of anything. Do not flip this to
                    # Provenance.HUMAN/confirmed=True without an actual human
                    # review pass (see `GoldSet.confirmed_only`).
                    provenance=Provenance.MODEL,
                    drafted_by="gold-auto-builder",
                    confirmed=False,
                    note=(
                        f"[golden_qa] Auto-extracted candidate mention for {identity_name}, "
                        "drawn from the pipeline's own resolution output -- NOT independently "
                        "verified. Requires a human confirmation pass before use as ground truth."
                    ),
                )
            )

    return GoldSet(novel_id, mentions)


def build_lotm_gold(db_path: Path | str = "data/lotm-vol1.db") -> GoldSet:
    """`data/lotm-vol1.db` is the full-volume run (213 chapters, sources.toml).

    self1/self2 both map to the combined "Zhou Mingrui / Klein Moretti" label:
    two distinct personas (bodies) for one continuous self, per architecture.md's
    self != persona axis -- collapsing them to one identity string here is
    intentional, not a resolution error.

    This run also leaves every character's bare given/family name as its own
    separate self-id from the full-name id (e.g. "Klein" = self10, "Moretti" =
    self72, vs. "Klein Moretti" = self1/self2) -- confirmed by cross-checking
    surface text, not assumed. That is a resolver characteristic of this
    snapshot worth root-causing separately (bare-name mentions not merging
    into the full-name cluster), but for gold-labeling purposes identity_map
    is the annotator's own identity string, independent of the pipeline's
    internal ids (see eval/gold.py's module docstring) -- so folding the
    verified bare-name ids in here is correct usage, not a workaround.
    Excludes self167 "Earl Hall" (a distinct title reference, not Audrey).
    """
    identity_map = {
        "lord-of-the-mysteries:self1": "Zhou Mingrui / Klein Moretti",
        "lord-of-the-mysteries:self2": "Zhou Mingrui / Klein Moretti",
        "lord-of-the-mysteries:self10": "Zhou Mingrui / Klein Moretti",
        "lord-of-the-mysteries:self72": "Zhou Mingrui / Klein Moretti",
        "lord-of-the-mysteries:self22": "Audrey Hall",
        "lord-of-the-mysteries:self27": "Audrey Hall",
        "lord-of-the-mysteries:self26": "Alger Wilson",
        "lord-of-the-mysteries:self83": "Alger Wilson",
        "lord-of-the-mysteries:self43": "Dunn Smith",
        "lord-of-the-mysteries:self45": "Dunn Smith",
    }
    return _extract_gold_from_db(db_path, "lord-of-the-mysteries", identity_map)


def build_orv_gold(db_path: Path | str = "data/reruns/omniscient-readers-viewpoint.db") -> GoldSet:
    """The only full-volume (188 chapters, sources.toml) ORV run on disk is a
    `data/reruns/` scratch copy -- no canonical `data/omniscient-readers-viewpoint.db`
    exists yet. Using it here is deliberate (it's the only full-range data
    available), but it means this gold set traces back to a scratch run, not
    the canonical DB `_extract_gold_from_db`'s docstring assumes elsewhere.
    "Han Sooyung" is resolved almost exclusively by the surface form "Han"
    in this run, not her full name.
    """
    identity_map = {
        "omniscient-readers-viewpoint:self1": "Kim Dokja",
        "omniscient-readers-viewpoint:self21": "Yoo Joonghyuk",
        "omniscient-readers-viewpoint:self2": "Yoo Sangah",
        "omniscient-readers-viewpoint:self7": "Lee Hyunsung",
        "omniscient-readers-viewpoint:self4": "Han Sooyung",
    }
    return _extract_gold_from_db(db_path, "omniscient-readers-viewpoint", identity_map)


def build_ri_gold(db_path: Path | str = "data/echotales.db") -> GoldSet:
    """`data/echotales.db` is the full-volume run (199 chapters, sources.toml).

    These ids must be re-verified against `db_path` any time it is rebuilt --
    self55/self41 previously pointed at "Gu Yue Mo Chen"/"Gu Yue Chi Lian" and
    silently drifted to different characters ("Bai Ning Bing"/"Qing Shu") the
    same day this DB was last rebuilt. See this module's docstring.
    """
    identity_map = {
        "reverend-insanity:self1": "Fang Yuan",
        "reverend-insanity:self5": "Fang Zheng",
        "reverend-insanity:self4": "Shen Cui",
        "reverend-insanity:self38": "Gu Yue Mo Chen",
        "reverend-insanity:self43": "Gu Yue Chi Lian",
    }
    return _extract_gold_from_db(db_path, "reverend-insanity", identity_map)


def extend_gold_with_new_chapters(existing_path: Path | str, draft_set: GoldSet) -> GoldSet:
    """Add auto-extracted drafts only for chapters `existing_path` doesn't
    already cover, leaving every existing record (confirmed or not) untouched.

    Chapter-level granularity, not per-mention: a chapter that already has any
    coverage is trusted as-is and not topped up record-by-record, so a partial
    human review pass is never partially overwritten by drafts of a different
    confidence tier at the same chapter.
    """
    existing_path = Path(existing_path)
    novel_id = draft_set.novel_id
    if existing_path.exists():
        existing = list(read_gold(existing_path, novel_id=novel_id))
    else:
        existing = []
    covered_chapters = {m.chapter for m in existing}
    new_mentions = [m for m in draft_set if m.chapter not in covered_chapters]
    return GoldSet(novel_id, existing + new_mentions)


def ensure_all_gold_sets(data_dir: Path | str = "data/gold") -> dict[str, Path]:
    """Regenerate LOTM/ORV wholesale (nothing in them is human-reviewed yet),
    but only *extend* RI's file with drafts for chapters it doesn't already
    cover -- ch1-60 there are a real, bulk-approved human pass and must never
    be silently downgraded back to an unconfirmed draft.
    """
    target_dir = Path(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    out_paths = {}

    lotm_path = target_dir / "lord-of-the-mysteries.jsonl"
    write_gold(build_lotm_gold(), lotm_path)
    out_paths["lord-of-the-mysteries"] = lotm_path

    orv_path = target_dir / "omniscient-readers-viewpoint.jsonl"
    write_gold(build_orv_gold(), orv_path)
    out_paths["omniscient-readers-viewpoint"] = orv_path

    ri_path = target_dir / "reverend-insanity.jsonl"
    write_gold(extend_gold_with_new_chapters(ri_path, build_ri_gold()), ri_path)
    out_paths["reverend-insanity"] = ri_path

    return out_paths


if __name__ == "__main__":
    paths = ensure_all_gold_sets()
    for novel, path in paths.items():
        print(f"Generated Gold QA dataset for {novel} at {path}")
