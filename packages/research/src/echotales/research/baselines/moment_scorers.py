"""Baselines for "which moments of a chapter deserve a picture".

Each scorer encodes one existing notion of importance, so their disagreement
is itself informative: if they all pick the same beats, moment selection is
easy and a learned selector has nothing to add; if they diverge, only reader
preference can say which notion is right (lit pass, visual G1).

- ``product_drama``: a text-only port of the product's own cutaway scoring
  (`render/director.py::score_blocks` -- content tag, delivery intensity,
  long-narration pacing), reusing its lexicons rather than copying them.
- ``dialogue_density``: share of the beat inside quotation marks (the product
  frames dialogue as close-ups; talk is a different picture than action).
- ``visual_lexicon``: density of concrete visual vocabulary -- a crude
  visualness proxy (Verma et al. learn this properly; we only need a foil).
- ``llm_zero_shot``: a local LLM's 1-10 rating (real runs only).
- ``random``.
"""

from __future__ import annotations

import random
import re

from echotales.pipeline.render.motion import match_tag
from echotales.pipeline.spans.delivery import (
    DeliveryPolarity,
    dominant_polarity,
    extract_delivery_markers,
)

_INTENSITY = {DeliveryPolarity.HEIGHTENED: 3, DeliveryPolarity.WARM: 2, DeliveryPolarity.COLD: 2,
              DeliveryPolarity.HUSHED: 1, DeliveryPolarity.HESITANT: 1, DeliveryPolarity.FLAT: 0}

_VISUAL = frozenset(
    "red blue green white black golden grey gray dark light bright shadow sun moon fire smoke rain "
    "snow river sea garden window door hall room table horse carriage road tree trees hill field "
    "dress coat hat hair eyes face hand hands blood sword knife gun ran fell struck threw climbed "
    "rode danced wept smiled kneeled knelt stood rose jumped burst crowd ball church house street".split()
)


def product_drama(text: str) -> float:
    content = 3.0 if match_tag(text) else 0.0
    pol = dominant_polarity(extract_delivery_markers(text))
    emotion = float(_INTENSITY.get(pol, 0)) if pol is not None else 0.0
    pacing = 1.0 if len(text.split()) > 150 else 0.0
    return content + emotion + pacing


def dialogue_density(text: str) -> float:
    quoted = sum(len(m) for m in re.findall(r"[“\"]([^”\"]*)[”\"]", text))
    return quoted / max(1, len(text))


def visual_lexicon(text: str) -> float:
    words = re.findall(r"[a-z]+", text.lower())
    return sum(w in _VISUAL for w in words) / max(1, len(words))


def random_scores(n: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.random() for _ in range(n)]


def llm_zero_shot(texts: list[str], *, model: str = "qwen2.5:7b") -> list[float]:
    import httpx

    prompt = ("You are planning illustrations for an illustrated edition of a novel. "
              "Rate from 1 to 10 how much a reader would want THIS passage illustrated "
              "with a picture. Reply with the number only.\n\nPASSAGE:\n")
    out = []
    for t in texts:
        r = httpx.post("http://localhost:11434/api/generate",
                       json={"model": model, "prompt": prompt + t[:1500], "stream": False,
                             "options": {"temperature": 0, "seed": 1}}, timeout=120)
        m = re.search(r"\d+", r.json().get("response", ""))
        out.append(float(m.group()) if m else 5.0)
    return out
