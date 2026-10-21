"""Print a chapter with every quoted utterance tagged `[block.q]`, for drafting a reader-gold file by hand.

Usage: python scripts/eval/dump_for_labelling.py <db> <novel_id> <chapter>

Reads only the chapter text (`chapter.blocks_json`), never the pipeline's span or speaker tables: a label drafted
while looking at the system's answer is not independent of it (`eval/gold.py`). The quote pattern is the one the
scorer uses (`eval/reader_gold.py::_QUOTE`), so `block.q` here is the key the scorer looks up.
"""

from __future__ import annotations

import json
import sqlite3
import sys

from echotales.pipeline.eval.reader_gold import _QUOTE


def main(db: str, novel_id: str, chapter: float) -> None:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    row = conn.execute("SELECT blocks_json FROM chapter WHERE novel_id=? AND number=?", (novel_id, chapter)).fetchone()
    if row is None:
        raise SystemExit(f"{novel_id} chapter {chapter:g} not found")
    for block in json.loads(row[0]):
        counter = iter(range(1000))
        tagged = _QUOTE.sub(lambda m: f"[{block['index']}.{next(counter)}]{m.group(0)}", block["text"])
        print(f"#{block['index']}: {tagged}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]))
