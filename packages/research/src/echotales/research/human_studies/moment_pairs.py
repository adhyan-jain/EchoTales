"""Pair sampling and analysis for the "which moment would you draw" study.

Pairs are within-chapter (the decision a panel budget actually forces), and a
fixed overlap set is shown to every annotator so agreement can be measured --
the lit pass's first kill criterion for H-SELECT is inter-annotator agreement
too low for a learnable target.
"""

from __future__ import annotations

import itertools
import json
import random
from collections import defaultdict
from pathlib import Path

from scipy.stats import kendalltau

from echotales.research.stats import bradley_terry


def make_pairs(chapters: list[list[dict]], *, pairs_per_chapter: int = 30, overlap: int = 20,
               seed: int = 20261002) -> dict:
    rng = random.Random(seed)
    items, pairs = {}, []
    for ch in chapters:
        for b in ch:
            items[b["id"]] = b["text"]
        cand = list(itertools.combinations([b["id"] for b in ch], 2))
        rng.shuffle(cand)
        pairs.extend(cand[:pairs_per_chapter])
    rng.shuffle(pairs)
    return {"items": items, "overlap": pairs[:overlap], "pool": pairs[overlap:]}


def agreement(responses: list[dict], overlap: list[list[str]]) -> float:
    """Mean pairwise percent agreement on the shared overlap pairs."""
    key = {tuple(sorted(p)) for p in overlap}
    by_ann: dict[str, dict[tuple, str]] = defaultdict(dict)
    for r in responses:
        k = tuple(sorted((r["a"], r["b"])))
        if k in key:
            by_ann[r["annotator"]][k] = r["winner"]
    anns = sorted(by_ann)
    agree, total = 0, 0
    for x, y in itertools.combinations(anns, 2):
        for k in set(by_ann[x]) & set(by_ann[y]):
            total += 1
            agree += by_ann[x][k] == by_ann[y][k]
    return agree / total if total else float("nan")


def strengths(responses: list[dict]) -> dict[str, float]:
    wins = [(r["winner"], r["b"] if r["winner"] == r["a"] else r["a"]) for r in responses]
    items = sorted({i for w in wins for i in w})
    return bradley_terry(items, wins)


def scorer_alignment(bt: dict[str, float], scorer: dict[str, float]) -> float:
    ids = [i for i in bt if i in scorer]
    if len(ids) < 3:
        return float("nan")
    return float(kendalltau([bt[i] for i in ids], [scorer[i] for i in ids]).statistic)


if __name__ == "__main__":
    import sys
    data = json.loads(Path(sys.argv[1]).read_text())
    rs = [r for p in sys.argv[2:] for r in json.loads(Path(p).read_text())]
    print(json.dumps({"agreement_overlap": agreement(rs, data["overlap"]),
                      "n_responses": len(rs)}, indent=2))
