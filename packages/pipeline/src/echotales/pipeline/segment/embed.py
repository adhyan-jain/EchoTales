"""Sentence embeddings for the topic-shift feature, from a local ollama embedding model.

Why not TF-IDF alone (docs/results/SCENE_INDUCTION.md, "Change score"): the v1
topic feature was IDF-weighted word overlap, which sees "the clan head spoke" and
"the elders spoke" as unrelated and a one-word scene cue as a topic change.
`nomic-embed-text` is small enough to share the 8 GB card with nothing else
loaded, and it is local, so it stays inside the project's local-first rule.

TF-IDF remains the fallback: `OllamaEmbedder.available()` is False when the
daemon is down or the model is not pulled, and the scorer then keeps v1's
behaviour instead of failing a segmentation run over an optional feature.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Any

import httpx

DEFAULT_MODEL = "nomic-embed-text"
DEFAULT_HOST = "http://localhost:11434"
#: One block is clipped to this many words before embedding. nomic's useful context is far larger, but a
#: long block is a stretch of one scene; its opening already carries the topic, and the clip keeps a
#: 200-block chapter to one request.
BLOCK_WORDS = 120


class OllamaEmbedder:
    """Batch embeddings with a per-process cache keyed by the clipped text."""

    def __init__(self, model: str = DEFAULT_MODEL, host: str | None = None, *, timeout: float = 120.0) -> None:
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self._client = httpx.Client(timeout=timeout)
        self._cache: dict[str, list[float]] = {}
        self._ok: bool | None = None

    def available(self) -> bool:
        if self._ok is None:
            try:
                r = self._client.get(f"{self.host}/api/tags", timeout=3.0)
                r.raise_for_status()
                names = {m.get("name", "") for m in r.json().get("models", [])}
                self._ok = any(n == self.model or n.startswith(f"{self.model}:") for n in names)
            except Exception:
                self._ok = False
        return self._ok

    @staticmethod
    def _clip(text: str) -> str:
        return " ".join(text.split()[:BLOCK_WORDS])

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """One vector per text, or None if the model cannot be reached (caller falls back)."""
        clipped = [self._clip(t) or "." for t in texts]
        keys = [hashlib.sha1(t.encode("utf-8")).hexdigest() for t in clipped]
        missing = [(k, t) for k, t in dict.fromkeys(zip(keys, clipped, strict=True)) if k not in self._cache]
        try:
            for i in range(0, len(missing), 64):
                chunk = missing[i : i + 64]
                r = self._client.post(
                    f"{self.host}/api/embed", json={"model": self.model, "input": [t for _, t in chunk]}
                )
                r.raise_for_status()
                vecs = r.json()["embeddings"]
                for (k, _), v in zip(chunk, vecs, strict=True):
                    self._cache[k] = v
        except Exception:
            self._ok = False
            return None
        return [self._cache[k] for k in keys]


def mean_vector(vectors: list[list[float]]) -> list[float]:
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(len(vectors[0]))]


def cosine_distance(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.5
    return 1.0 - sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


def get_embedder(model: str = DEFAULT_MODEL) -> Any | None:
    """An available embedder, or None."""
    e = OllamaEmbedder(model)
    return e if e.available() else None
