"""Add A Study in Scarlet and more Pride and Prejudice silver labels to data/gold/segment/scene_boundaries.json.

Same format as segment_gold_add.py. Silver: read by Claude 2026-11-28 (first pass: every Scarlet block, first nine
words; second pass: each cut and ambiguous boundary re-read with the last and first words around it). Both novels
are public domain; only 5-word anchors are stored anyway. Scarlet is learned on chapters 1-7 (Part I, London) and
read held-out on 8-14 (Part II opens in a different country and time, so it is a genuine transfer test).
"""

from __future__ import annotations

import json
from pathlib import Path

from echotales.core.store import Store

GOLD = Path("data/gold/segment/scene_boundaries.json")
N = "NEW_SCENE"
LABELS = {
    "a-study-in-scarlet": {
        "1": dict(cuts=[(33, N, "LATER")], ambiguous=[4, 23, 63], negatives=[], coverage="full"),
        "2": dict(cuts=[(17, N, "LATER")], ambiguous=[16], negatives=[41], coverage="full"),
        "3": dict(cuts=[(26, N, "LATER"), (31, N, "LATER")], ambiguous=[43, 44], negatives=[11, 83], coverage="full"),
        "4": dict(cuts=[(18, N, "LATER")], ambiguous=[19, 52, 56], negatives=[], coverage="full"),
        "5": dict(cuts=[(2, N, "LATER")], ambiguous=[24, 47], negatives=[32], coverage="full"),
        "6": dict(cuts=[], ambiguous=[40, 42], negatives=[18, 85], coverage="full"),
        "7": dict(cuts=[], ambiguous=[32], negatives=[8, 48], coverage="full"),
        "8": dict(cuts=[(39, N, "LATER")], ambiguous=[5, 37], negatives=[], coverage="full"),
        "9": dict(cuts=[(7, N, "LATER"), (22, N, "LATER")], ambiguous=[21], negatives=[], coverage="full"),
        "10": dict(cuts=[(5, N, "LATER")], ambiguous=[23], negatives=[17], coverage="full"),
        "11": dict(cuts=[(28, N, "LATER"), (54, N, "SAME")], ambiguous=[21, 26, 46], negatives=[42], coverage="full"),
        "12": dict(cuts=[(4, N, "SAME"), (12, N, "LATER"), (25, N, "LATER")], ambiguous=[3, 13, 26], negatives=[], coverage="full"),
        "13": dict(cuts=[], ambiguous=[6, 15, 21], negatives=[27, 34, 47], coverage="full"),
        "14": dict(cuts=[], ambiguous=[21], negatives=[], coverage="full"),
    },
    "pride-and-prejudice": {
        "10": dict(cuts=[], ambiguous=[], negatives=[67], coverage="candidates"),
        "13": dict(cuts=[], ambiguous=[], negatives=[12], coverage="candidates"),
        "15": dict(cuts=[(10, N, "SAME")], ambiguous=[], negatives=[], coverage="candidates"),
        "20": dict(cuts=[], ambiguous=[], negatives=[26], coverage="candidates"),
        "23": dict(cuts=[(14, N, "LATER")], ambiguous=[], negatives=[], coverage="candidates"),
    },
}
DBS = {
    "a-study-in-scarlet": "data/scratch/segment/a-study-in-scarlet.db",
    "pride-and-prejudice": "data/scratch/segment/pp.db",
}


def anchor(chapter, block: int) -> str:
    return " ".join(chapter.blocks[block].text.split()[:5])


def main() -> None:
    gold = json.loads(GOLD.read_text())
    gold["dbs"].update(DBS)
    for novel, chapters in LABELS.items():
        store = Store(DBS[novel])
        gold["novels"].setdefault(novel, {})
        for ch, spec in chapters.items():
            c = store.get_chapter(novel, float(ch))
            gold["novels"][novel][ch] = {
                "cuts": [
                    {"block": b, "anchor": anchor(c, b), "cut_type": t, "time_relation": r} for b, t, r in spec["cuts"]
                ],
                "ambiguous": spec["ambiguous"],
                "negatives": [{"block": b, "anchor": anchor(c, b)} for b in spec["negatives"]],
                "n_blocks": len(c.blocks),
                "coverage": spec["coverage"],
            }
    GOLD.write_text(json.dumps(gold, indent=1, ensure_ascii=False))
    n = sum(len(v["cuts"]) for nv in gold["novels"].values() for v in nv.values())
    print("cuts total", n, "novels", len(gold["novels"]))


if __name__ == "__main__":
    main()
