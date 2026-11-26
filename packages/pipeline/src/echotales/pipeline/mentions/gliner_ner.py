"""GLiNER-backed mention detector (label-prompted, no roster, no LLM server).

Not the default: a bake-off decides that. It exists so unfamiliar romanized
names (Fang Yuan, Kim Dokja, Satoru Gojo, invented names) can be found by a
small encoder that runs on the same 8 GB GPU as everything else, in its own
pass, and is unloaded before ollama starts (`unload`).
"""

from __future__ import annotations

import re

from echotales.pipeline.mentions.ner import MentionDetector, NerSpan, _outranks

#: GLiNER label text -> project label. The model is prompted with the natural-
#: language side, so "person" works and "character" would not.
DEFAULT_GLINER_LABELS: dict[str, str] = {
    "person": "character",
    "title or epithet of a person": "character",
    "location": "location",
    "organization": "organization",
    "named object or artifact": "item",
}

#: GLiNER truncates past ~384 tokens, silently dropping the tail of a chunk.
#: 1200 characters is ~300 tokens of English prose, leaving headroom for the
#: label prompt that shares the same budget.
GLINER_MAX_CHARS = 1_200

#: Free GPU memory needed before GLiNER goes to CUDA; below it the model would
#: contend with a resident diffusion/ollama process on the 8 GB card.
MIN_FREE_GPU_BYTES = int(1.5 * 1024**3)

_SENTENCE_END = re.compile(r"(?<=[.!?”\"])\s+|\n+")


def resolve_device(device: str = "auto") -> str:
    if device != "auto":
        return device
    try:
        import torch

        if torch.cuda.is_available():
            free, _total = torch.cuda.mem_get_info()
            if free >= MIN_FREE_GPU_BYTES:
                return "cuda"
    except Exception:
        pass
    return "cpu"


def _sentence_chunks(text: str, max_chars: int) -> list[tuple[int, int]]:
    """Sentence-aligned (start, end) chunks, each overlapping the last by one sentence.

    The overlap means a name split across a seam is whole in one of the two
    chunks. A single sentence longer than `max_chars` is hard-split rather than
    sent over-long, since GLiNER would truncate it silently.
    """
    sentences: list[tuple[int, int]] = []
    pos = 0
    for m in _SENTENCE_END.finditer(text):
        if m.start() > pos:
            sentences.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        sentences.append((pos, len(text)))
    pieces: list[tuple[int, int]] = []
    for s, e in sentences:
        while e - s > max_chars:
            pieces.append((s, s + max_chars))
            s += max_chars
        pieces.append((s, e))

    chunks: list[tuple[int, int]] = []
    i = 0
    while i < len(pieces):
        j = i
        while j + 1 < len(pieces) and pieces[j + 1][1] - pieces[i][0] <= max_chars:
            j += 1
        chunks.append((pieces[i][0], pieces[j][1]))
        if j + 1 >= len(pieces):
            break
        i = max(j, i + 1)  # restart at the last sentence taken: the one-sentence overlap
    return chunks


class GlinerDetector(MentionDetector):
    def __init__(
        self,
        model_id: str = "urchade/gliner_medium-v2.1",
        labels: dict[str, str] | None = None,
        *,
        threshold: float = 0.5,
        device: str = "auto",
        model: object | None = None,
        max_chars: int = GLINER_MAX_CHARS,
    ) -> None:
        self.model_id = model_id
        self.labels = dict(labels or DEFAULT_GLINER_LABELS)
        self.threshold = threshold
        self.device = device
        self.max_chars = max_chars
        self._model = model
        self.model_version: str | None = self._read_version(model) if model is not None else None

    @property
    def name(self) -> str:
        return f"gliner:{self.model_id}"

    @staticmethod
    def _read_version(model: object) -> str | None:
        cfg = getattr(model, "config", None)
        rev = getattr(cfg, "_commit_hash", None) or getattr(cfg, "revision", None)
        return rev if isinstance(rev, str) and rev else None

    def _ensure_model(self) -> object:
        if self._model is None:
            from gliner import GLiNER  # lazy: the ml extra is optional

            model = GLiNER.from_pretrained(self.model_id)
            self._model = model.to(resolve_device(self.device))
            self.model_version = self._read_version(self._model)
        return self._model

    def unload(self) -> None:
        """Free the model so ollama can have the GPU in the next pass."""
        self._model = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def detect(self, text: str) -> list[NerSpan]:
        if not text.strip():
            return []
        model = self._ensure_model()
        best: dict[tuple[int, int], NerSpan] = {}
        for c_start, c_end in _sentence_chunks(text, self.max_chars):
            chunk = text[c_start:c_end]
            raw = model.predict_entities(  # type: ignore[attr-defined]
                chunk, list(self.labels), threshold=self.threshold
            )
            for ent in raw:
                label = self.labels.get(ent["label"])
                if label is None:
                    continue
                start, end = c_start + int(ent["start"]), c_start + int(ent["end"])
                span = NerSpan(text[start:end], start, end, label, float(ent["score"]))
                prev = best.get((start, end))
                if prev is None or _outranks(span, prev):
                    best[(start, end)] = span
        return sorted(best.values(), key=lambda s: (s.start, s.end))

    def detect_with_context(self, text: str, known_names: list[str]) -> list[NerSpan]:
        # GLiNER is prompted by label, not by roster; handing it names would
        # need a different model input and would bias it toward the known cast,
        # the opposite of finding unfamiliar names.
        return self.detect(text)
