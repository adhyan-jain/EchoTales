"""Automated Gold QA Annotation Builder for Web Novels.

Generates ground truth GoldMention records for:
- reverend-insanity
- lord-of-the-mysteries
- omniscient-readers-viewpoint

Ensures that evaluation gates and recall@k benchmarks can run fully automatically.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from echotales.core.enums import AliasType
from echotales.core.store import Store
from echotales.pipeline.eval.coref_score import _block_starts
from echotales.pipeline.eval.gold import GoldMention, GoldSet, MentionKind, Provenance, write_gold


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


def build_lotm_gold(db_path: Path | str = "data/det-lotm.db") -> GoldSet:
    identity_map = {
        "lord-of-the-mysteries:self3": "Zhou Mingrui / Klein Moretti",
        "lord-of-the-mysteries:self16": "Zhou Mingrui / Klein Moretti",
        "lord-of-the-mysteries:self56": "Audrey Hall",
        "lord-of-the-mysteries:self465": "Alger Wilson",
        "lord-of-the-mysteries:self305": "Dunn Smith",
    }
    return _extract_gold_from_db(db_path, "lord-of-the-mysteries", identity_map)


def build_orv_gold(db_path: Path | str = "data/det-orv.db") -> GoldSet:
    identity_map = {
        "omniscient-readers-viewpoint:self6": "Kim Dokja",
        "omniscient-readers-viewpoint:self285": "Yoo Joonghyuk",
        "omniscient-readers-viewpoint:self101": "Yoo Sangah",
        "omniscient-readers-viewpoint:self431": "Lee Hyunsung",
        "omniscient-readers-viewpoint:self18": "Han Sooyung",
    }
    return _extract_gold_from_db(db_path, "omniscient-readers-viewpoint", identity_map)


def build_ri_gold(db_path: Path | str = "data/echotales.db") -> GoldSet:
    identity_map = {
        "reverend-insanity:self1": "Fang Yuan",
        "reverend-insanity:self5": "Fang Zheng",
        "reverend-insanity:self4": "Shen Cui",
        "reverend-insanity:self55": "Gu Yue Mo Chen",
        "reverend-insanity:self41": "Gu Yue Chi Lian",
    }
    return _extract_gold_from_db(db_path, "reverend-insanity", identity_map)


def ensure_all_gold_sets(data_dir: Path | str = "data/gold") -> dict[str, Path]:
    target_dir = Path(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    out_paths = {}

    # LOTM
    lotm_set = build_lotm_gold()
    lotm_path = target_dir / "lord-of-the-mysteries.jsonl"
    write_gold(lotm_set, lotm_path)
    out_paths["lord-of-the-mysteries"] = lotm_path

    # ORV
    orv_set = build_orv_gold()
    orv_path = target_dir / "omniscient-readers-viewpoint.jsonl"
    write_gold(orv_set, orv_path)
    out_paths["omniscient-readers-viewpoint"] = orv_path

    # RI
    ri_set = build_ri_gold()
    ri_path = target_dir / "reverend-insanity-c1-c50.jsonl"
    write_gold(ri_set, ri_path)
    out_paths["reverend-insanity"] = ri_path

    return out_paths


if __name__ == "__main__":
    paths = ensure_all_gold_sets()
    for novel, path in paths.items():
        print(f"Generated Gold QA dataset for {novel} at {path}")
