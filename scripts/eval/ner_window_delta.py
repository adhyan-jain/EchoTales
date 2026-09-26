"""Measure what the NER windowing fix changed, against a before/after pair of DBs.

Written for COMPLETION_PLAN Track 1 item 3. The prediction recorded *before*
the run was: CEAF-e recall rises well above 32.1%, mentions per chapter roughly
doubles, speaker-attribution identifiability rises from 45.5%. This script
reports those three plus the direct check -- Bai Ning Bing has chapter-1
mentions past offset 6,000, where she was previously invisible -- so the delta
is produced the same way on both sides rather than eyeballed from two printouts.

Usage:
    python3 scripts/eval/ner_window_delta.py <before.db> <after.db> [novel_id]
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys


def _connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def chapter_text(conn: sqlite3.Connection, novel: str, number: float) -> tuple[str, dict[int, int]]:
    """Chapter text and per-block start offsets, joined exactly as the blocks
    were stored -- `mention.offset` is block-local, so an absolute position
    needs the block start added. This is the same translation `coref_score.
    _block_starts` does, and getting it wrong is a documented past bug."""
    row = conn.execute(
        "select blocks_json from chapter where novel_id=? and number=?", (novel, number)
    ).fetchone()
    if row is None:
        return "", {}
    blocks = json.loads(row[0])
    parts: list[str] = []
    starts: dict[int, int] = {}
    pos = 0
    for block in blocks:
        starts[block["index"]] = pos
        parts.append(block["text"])
        pos += len(block["text"]) + 1
    return "\n".join(parts), starts


def measure(path: str, novel: str) -> dict[str, object]:
    conn = _connect(path)
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731

    out: dict[str, object] = {}
    out["chapters"] = one("select count(*) from chapter where novel_id=?", novel)
    out["mentions"] = one("select count(*) from mention where novel_id=?", novel)
    out["chapters_with_mentions"] = one(
        "select count(distinct chapter) from mention where novel_id=?", novel
    )
    out["mentions_per_chapter"] = round(
        float(out["mentions"]) / max(1, int(out["chapters"])), 1
    )
    out["entities"] = one("select count(*) from self_entity where novel_id=?", novel)
    out["entity_kinds"] = dict(
        conn.execute(
            "select coalesce(kind,'(unset)'), count(*) from self_entity "
            "where novel_id=? group by 1 order by 2 desc",
            (novel,),
        ).fetchall()
    )
    out["ner_labels"] = dict(
        conn.execute(
            "select coalesce(entity_label,'(null)'), count(*) from mention "
            "where novel_id=? group by 1 order by 2 desc",
            (novel,),
        ).fetchall()
    )

    # Mentions past the old 6,000-character cut, in chapter-absolute terms.
    # Not zero before the fix -- `_locate` searches the whole chapter, so a
    # name introduced early is found late too. The number that matters is how
    # many *entities* are first named past the cut.
    past, total = 0, 0
    per_chapter_halves: list[float] = []
    for (number,) in conn.execute(
        "select number from chapter where novel_id=? order by number", (novel,)
    ):
        text, starts = chapter_text(conn, novel, number)
        if not text:
            continue
        per_chapter_halves.append(len(text))
        for block_index, offset in conn.execute(
            "select block_index, offset from mention where novel_id=? and chapter=?",
            (novel, number),
        ):
            total += 1
            if starts.get(block_index or 0, 0) + (offset or 0) >= 6000:
                past += 1
    out["mentions_past_6000"] = past
    out["mentions_located"] = total
    out["pct_mentions_past_6000"] = round(100.0 * past / max(1, total), 1)
    out["median_chapter_chars"] = (
        int(statistics.median(per_chapter_halves)) if per_chapter_halves else 0
    )

    # The named check from the plan's Verification section.
    bnb = conn.execute(
        "select chapter, count(*) from mention where novel_id=? and text like ? "
        "group by chapter order by chapter limit 5",
        (novel, "%Bai Ning Bing%"),
    ).fetchall()
    out["bai_ning_bing_first_chapters"] = bnb
    text, starts = chapter_text(conn, novel, 1.0)
    out["bai_ning_bing_ch1_text_offsets"] = [
        i for i in range(len(text)) if text.startswith("Bai Ning Bing", i)
    ]
    out["bai_ning_bing_ch1_mentions"] = [
        starts.get(bi or 0, 0) + (off or 0)
        for bi, off in conn.execute(
            "select block_index, offset from mention "
            "where novel_id=? and chapter=1 and text like ?",
            (novel, "%Bai Ning Bing%"),
        )
    ]

    # Speaker attribution identifiability, recomputed with the exact rule
    # `speakers/runner.py::attribute_novel` tallies at its end -- eligible
    # types are DIALOGUE/INNER_MONOLOGUE/CROWD_REACTION, ANONYMOUS_SLOT is
    # never counted as attributed, and UNATTRIBUTED_CHORUS is. Read off the
    # `span` table, not `mention`: `mention.speaker_self_id` is unpopulated
    # on every shipped database, so the obvious query returns a flat 0%.
    eligible_sql = (
        "from span where novel_id=? and span_type in "
        "('DIALOGUE','INNER_MONOLOGUE','CROWD_REACTION')"
    )
    dialogue = one("select count(*) " + eligible_sql, novel)
    identified = one(
        "select count(*) "
        + eligible_sql
        + " and attribution_method!='ANONYMOUS_SLOT'"
        " and ((speaker_self_id is not null and speaker_self_id!='')"
        " or attribution_method='UNATTRIBUTED_CHORUS')",
        novel,
    )
    out["dialogue_spans"] = dialogue
    out["dialogue_identified"] = identified
    out["identifiable_pct"] = round(100.0 * identified / max(1, dialogue), 1)
    out["attribution_methods"] = dict(
        conn.execute(
            "select attribution_method, count(*) " + eligible_sql + " group by 1 order by 2 desc",
            (novel,),
        ).fetchall()
    )

    conn.close()
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    before_path, after_path = sys.argv[1], sys.argv[2]
    novel = sys.argv[3] if len(sys.argv) > 3 else "reverend-insanity"

    before = measure(before_path, novel)
    after = measure(after_path, novel)

    print(f"novel: {novel}")
    print(f"before: {before_path}")
    print(f"after:  {after_path}\n")
    width = max(len(k) for k in before)
    for key in before:
        b, a = before[key], after.get(key)
        arrow = ""
        if isinstance(b, (int, float)) and isinstance(a, (int, float)) and b:
            arrow = f"   ({(a - b) / b * 100:+.1f}%)"
        print(f"{key:<{width}}  before={b!r}\n{'':<{width}}  after ={a!r}{arrow}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
