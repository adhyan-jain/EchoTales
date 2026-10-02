"""Controlled speaker-attribution errors for perceptual stimuli.

The error *types* are the ones that occur, not a uniform swap: on PDNC human
gold the product ladder's errors are 52% addressee capture and 41-43%
cross-gender (H-CAL / H-GATE runs). Each type is a separate level so a
listening study can estimate its cost separately -- the "not all errors cost
the same" question (lit pass G3).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

ERROR_TYPES = ("addressee", "same_gender", "cross_gender")


@dataclass(frozen=True, slots=True)
class Injection:
    quote_index: int
    gold: str
    rendered_as: str
    error_type: str


def inject(quotes: list[dict], cast_genders: dict[str, str], *, rate: float,
           error_type: str, seed: int, eligible: set[int] | None = None) -> list[Injection]:
    """Swap the speaker of round(rate * n) eligible quotes.

    `quotes`: dicts with `speaker` and `addressees`. A quote is eligible for a
    type only if a substitute of that type exists among the passage's cast,
    so a requested rate can come out lower; the realised rate is what the
    stimulus manifest records.
    """
    rng = random.Random(seed)
    cast = sorted(cast_genders)
    pool = sorted(eligible) if eligible is not None else list(range(len(quotes)))
    rng.shuffle(pool)
    k = round(rate * len(quotes))
    out: list[Injection] = []
    for i in pool:
        if len(out) >= k:
            break
        q = quotes[i]
        gold = q["speaker"]
        g = cast_genders.get(gold, "U")
        if error_type == "addressee":
            cands = [a for a in q.get("addressees", []) if a in cast_genders and a != gold]
        elif error_type == "same_gender":
            cands = [c for c in cast if c != gold and cast_genders[c] == g]
        elif error_type == "cross_gender":
            cands = [c for c in cast if c != gold and cast_genders[c] in ("M", "F")
                     and g in ("M", "F") and cast_genders[c] != g]
        else:
            raise ValueError(error_type)
        if cands:
            out.append(Injection(i, gold, rng.choice(sorted(cands)), error_type))
    return out
