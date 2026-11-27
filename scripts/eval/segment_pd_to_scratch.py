"""Build a scratch database of a public-domain Project Gutenberg novel for the scene-cut benchmark.

Usage: python scripts/eval/segment_pd_to_scratch.py data/raw/pd_gutenberg/pg244.txt a-study-in-scarlet data/scratch/segment/a-study-in-scarlet.db

Chapters are the book's own `CHAPTER <roman>.` headings numbered 1..N across parts; blocks are blank-line
separated paragraphs with their hard line wraps joined. This is a benchmark fixture, not the production ingest:
it exists because the real ingest has no plain-text adapter and the benchmark needs a novel whose text may be
quoted in the repository (it is public domain).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter
from echotales.core.store import Store

_HEAD = re.compile(r"^CHAPTER [IVXLC]+\.\s*$")


def main() -> None:
    src, novel, db = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    lines = src.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("*** START OF"))
    end = next(i for i, ln in enumerate(lines) if ln.startswith("*** END OF"))
    body = lines[start + 1 : end]
    heads = [i for i, ln in enumerate(body) if _HEAD.match(ln)]
    store = Store(db)
    store.add_novel(novel, novel, src.name, "gutenberg-txt")
    for n, h in enumerate(heads, start=1):
        stop = heads[n] if n < len(heads) else len(body)
        paras = [" ".join(p.split()) for p in "\n".join(body[h + 1 : stop]).split("\n\n")]
        paras = [p for p in paras if p and not p.startswith("PART ")]
        title = paras[0] if paras and paras[0].isupper() else ""
        blocks = [
            Block(index=i, block_type=BlockType.PROSE, text=t)
            for i, t in enumerate(p for p in paras if p != title)
        ]
        store.add_chapter(Chapter(novel_id=novel, number=float(n), title=title, source_href=src.name, blocks=blocks))
    store.conn.commit()
    print(novel, len(heads), "chapters ->", db)


if __name__ == "__main__":
    main()
