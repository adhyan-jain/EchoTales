"""Character -> voice assignment under a controlled distinctiveness level.

The masking hypothesis needs distinctiveness as an *independent variable*,
so casting here is deterministic and parameterised rather than the product's
bucket lookup (`pipeline/voice/casting.py`), which optimises fit-to-character
and has no notion of spread:

- ``diverse``: greedy farthest-point assignment within each gender -- every
  new character gets the voice farthest from those already cast.
- ``homogeneous``: every character of a gender is cast from the few voices
  nearest that gender's centroid -- the "old near-identical bank" condition
  the 4.87 listening note described.
"""

from __future__ import annotations

import random

import numpy as np

from echotales.research.evaluators.voice_geometry import BankGeometry


def cast(characters: list[tuple[str, str]], geom: BankGeometry, *, mode: str,
         seed: int, homogeneous_pool: int = 2) -> dict[str, str]:
    """`characters`: (name, gender in M/F/other) in prominence order."""
    rng = random.Random(seed)
    by_g = {g: [i for i, x in enumerate(geom.genders) if x == g] for g in ("M", "F")}
    out: dict[str, str] = {}
    used: dict[str, list[int]] = {"M": [], "F": []}
    for name, gender in characters:
        g = gender if gender in ("M", "F") else rng.choice(["M", "F"])
        pool = by_g[g]
        if mode == "homogeneous":
            centre = geom.emb[pool].mean(axis=0)
            nearest = sorted(pool, key=lambda i: -float(geom.emb[i] @ centre))[:homogeneous_pool]
            pick = nearest[len(used[g]) % len(nearest)]
        elif mode == "diverse":
            if not used[g]:
                pick = rng.choice(pool)
            else:
                unused = [i for i in pool if i not in used[g]] or pool
                pick = max(unused, key=lambda i: min(1 - float(geom.emb[i] @ geom.emb[j])
                                                     for j in used[g]))
        else:
            raise ValueError(mode)
        used[g].append(pick)
        out[name] = geom.ids[pick]
    return out


def mean_pairwise_distance(assign: dict[str, str], geom: BankGeometry) -> float:
    vs = list(assign.values())
    ds = [geom.distance(a, b) for i, a in enumerate(vs) for b in vs[i + 1:]]
    return float(np.mean(ds)) if ds else 0.0
