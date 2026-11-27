"""Merge hand labels into data/gold/segment/scene_boundaries.json, filling 5-word anchors from the scratch DBs.

Labels are (block, cut_type, time_relation) per chapter plus `negatives` (blocks that look like a break and are
not: ellipsis pauses, topic changes, a separator inside one scene) and `ambiguous`. Silver, not owner-checked,
except RI ch1 which is owner gold. Only anchors of at most 5 words are stored; source text never is.
`coverage` says how much of the chapter was read: "full" or "candidates" (separators and the top-scored
boundaries only, so an unmarked cut elsewhere in the chapter may be missing).
"""

from __future__ import annotations

import json
from pathlib import Path

from echotales.core.store import Store

GOLD = Path("data/gold/segment/scene_boundaries.json")
N = "NEW_SCENE"
LABELS = {
    "reverend-insanity": {
        "4": dict(cuts=[], ambiguous=[3], negatives=[], coverage="full"),
        "6": dict(cuts=[], ambiguous=[], negatives=[22, 59], coverage="full"),
        "7": dict(cuts=[], ambiguous=[], negatives=[41], coverage="full"),
        "8": dict(cuts=[(18, N, "SAME")], ambiguous=[32, 45], negatives=[28], coverage="full"),
        "9": dict(cuts=[(33, N, "LATER"), (41, N, "SAME"), (56, N, "SAME")], ambiguous=[24, 32], negatives=[], coverage="full"),
        "10": dict(cuts=[], ambiguous=[], negatives=[45], coverage="full"),
        "12": dict(cuts=[], ambiguous=[], negatives=[29, 68], coverage="full"),
        "14": dict(cuts=[], ambiguous=[], negatives=[24, 38], coverage="full"),
    },
    "lord-of-the-mysteries": {
        "5": dict(cuts=[(50, N, "LATER"), (84, N, "SAME"), (93, N, "SAME"), (99, N, "SAME")], ambiguous=[], negatives=[87, 89, 91, 96, 100], coverage="candidates"),
        "6": dict(cuts=[], ambiguous=[], negatives=[22, 38, 41, 45, 51, 74], coverage="candidates"),
        "9": dict(cuts=[], ambiguous=[12], negatives=[25, 47, 51, 54, 56, 64, 74, 80], coverage="candidates"),
        "10": dict(cuts=[], ambiguous=[], negatives=[9, 25, 29, 45, 52], coverage="candidates"),
    },
    "omniscient-readers-viewpoint": {
        "14": dict(cuts=[], ambiguous=[28], negatives=[], coverage="candidates"),
        "16": dict(cuts=[], ambiguous=[13], negatives=[], coverage="candidates"),
        "17": dict(cuts=[(97, N, "UNKNOWN")], ambiguous=[], negatives=[], coverage="candidates"),
        "18": dict(cuts=[(113, N, "LATER")], ambiguous=[], negatives=[], coverage="candidates"),
        "20": dict(cuts=[(30, N, "LATER")], ambiguous=[], negatives=[], coverage="candidates"),
        "23": dict(cuts=[(74, N, "LATER")], ambiguous=[], negatives=[], coverage="candidates"),
        "26": dict(cuts=[(79, N, "LATER"), (127, N, "LATER")], ambiguous=[], negatives=[], coverage="candidates"),
        "27": dict(cuts=[], ambiguous=[78], negatives=[], coverage="candidates"),
        "28": dict(cuts=[(44, N, "LATER")], ambiguous=[], negatives=[], coverage="candidates"),
        "29": dict(cuts=[(105, N, "LATER")], ambiguous=[], negatives=[], coverage="candidates"),
        "30": dict(cuts=[], ambiguous=[41], negatives=[], coverage="candidates"),
        "32": dict(cuts=[(48, N, "UNKNOWN"), (118, N, "LATER"), (160, N, "LATER")], ambiguous=[], negatives=[], coverage="candidates"),
        "39": dict(cuts=[(20, "POV_SWITCH", "SAME"), (103, N, "LATER")], ambiguous=[], negatives=[], coverage="candidates"),
        "40": dict(cuts=[], ambiguous=[51], negatives=[], coverage="candidates"),
    },
}
DBS = {
    "reverend-insanity": "data/scratch/segment/reverend-insanity.db",
    "lord-of-the-mysteries": "data/scratch/segment/lord-of-the-mysteries.db",
    "omniscient-readers-viewpoint": "data/scratch/segment/omniscient-readers-viewpoint.db",
}


def anchor(chapter, block: int) -> str:
    return " ".join(chapter.blocks[block].text.split()[:5])


def main() -> None:
    gold = json.loads(GOLD.read_text())
    for novel, chapters in LABELS.items():
        store = Store(DBS[novel])
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
    print("cuts total", n)


if __name__ == "__main__":
    main()
