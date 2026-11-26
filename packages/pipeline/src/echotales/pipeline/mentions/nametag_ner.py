"""NameTag 3 detector -- evaluation only, never a default.

NameTag 3 checkpoints are CC BY-NC-SA 4.0: non-commercial. They may be used to
measure what a strong CoNLL-style tagger does on this corpus, and must not be
shipped in the product path.

The NameTag 3 Python API could not be confirmed offline, so this module takes
an injectable `tagger` callable, `tagger(text) -> [(start, end, label), ...]`
with CoNLL labels (PER/LOC/ORG/MISC), and wraps it. Adapt the real model to
that callable at the call site.
"""

from __future__ import annotations

from collections.abc import Callable

from echotales.pipeline.mentions.ner import MentionDetector, NerSpan

#: MISC is dropped: it is nationalities, events and products in one bucket and
#: cannot be mapped to a project label without inventing precision.
NAMETAG_LABELS: dict[str, str] = {
    "PER": "character",
    "LOC": "location",
    "ORG": "organization",
}

NAMETAG_FIXED_SCORE = 0.7


class NameTagDetector(MentionDetector):
    def __init__(self, tagger: Callable[[str], list[tuple[int, int, str]]] | None = None, *, model_path: str = "") -> None:
        if tagger is None:
            raise ImportError(
                "NameTagDetector needs a `tagger` callable wrapping a local NameTag 3 model "
                f"(model_path={model_path!r}); no NameTag 3 binding is bundled (CC BY-NC-SA, eval-only)."
            )
        self._tagger = tagger
        self.model_path = model_path
        self.model_version: str | None = None

    @property
    def name(self) -> str:
        return f"nametag:{self.model_path or 'injected'}"

    def detect(self, text: str) -> list[NerSpan]:
        out = []
        for start, end, tag in self._tagger(text):
            label = NAMETAG_LABELS.get(tag)
            if label is not None:
                out.append(NerSpan(text[start:end], start, end, label, NAMETAG_FIXED_SCORE))
        return out
