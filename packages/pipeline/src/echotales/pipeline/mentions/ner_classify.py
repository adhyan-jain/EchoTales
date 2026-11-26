"""LLM tie-breaker for the hybrid detector's mid-confidence candidates (decisions D69).

One call per batch of up to `BATCH` candidates -- never per mention -- so it stays inside the "no per-span model
call" rule (`chapter_ner.py`). The model sees the SENTENCE each candidate sits in, because "Will" is a name in
"Will bowed" and a word in "Will you go?", and nothing about the bare surface says which.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from echotales.pipeline.llm.tasks import Task
from echotales.pipeline.mentions.candidate import NameCandidate
from echotales.pipeline.mentions.chapter_ner import NameCache
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

#: Candidates per call. 40 verdicts fit `Task.NER_CLASSIFY`'s max_tokens; more than that go in further calls rather
#: than being dropped, because a dropped candidate would be silently rejected.
BATCH = 40

#: A sentence longer than this is a run-on or a missing full stop; the window around the candidate is cut to it.
MAX_SENTENCE_CHARS = 300

LABELS = ("character", "location", "organization", "item")

_SENTENCE_END = re.compile(r"(?<=[.!?”\"])\s+|\n+")


@dataclass(frozen=True, slots=True)
class Verdict:
    is_name: bool
    label: str
    reason: str = ""


class ClassifyItem(BaseModel):
    id: int = Field(description="the number of the candidate this verdict is for")
    is_name: bool
    label: str = Field(default="character", description="one of: character, location, organization, item")
    reason: str = Field(default="", description="one short phrase")


class NerClassifyResponse(BaseModel):
    items: list[ClassifyItem] = Field(default_factory=list)


_SYSTEM = (
    "You decide whether a capitalised phrase in a novel names a specific character, place, organization or named "
    "item. Translated web novels name people with epithets and compound forms, so an unfamiliar phrase is not "
    "evidence against it. A common word that merely starts a sentence, a pronoun, an interjection, a generic role "
    "(a guard, an innkeeper) or a title with no name attached is NOT a name. Judge from the sentence given."
)

_PROMPT = (
    "For each numbered candidate, answer whether it is a name in its sentence.\n"
    "Return JSON {{\"items\": [{{\"id\": n, \"is_name\": true|false, \"label\": "
    "\"character|location|organization|item\", \"reason\": \"...\"}}]}} with one entry per candidate.\n\n"
    "{items}"
)


def sentence_around(text: str, start: int, end: int, *, max_chars: int = MAX_SENTENCE_CHARS) -> str:
    """The sentence containing [start, end), found with a simple splitter and capped at `max_chars`."""
    lo = 0
    hi = len(text)
    for m in _SENTENCE_END.finditer(text):
        if m.end() <= start:
            lo = m.end()
        elif m.start() >= end:
            hi = m.start()
            break
    sentence = text[lo:hi].strip()
    if len(sentence) <= max_chars:
        return sentence
    # Keep the window centred on the candidate rather than its first max_chars, or a name late in a run-on is cut off.
    mid = (start + end) // 2 - lo
    left = max(0, min(mid - max_chars // 2, len(text[lo:hi]) - max_chars))
    return text[lo:hi][left : left + max_chars].strip()


class ClassifyCache(NameCache):
    """`NameCache` machinery keyed on the classify prompt instead of the NER one.

    The value is a candidate-in-context's verdict, so the key text is `surface + sentence`; a changed prompt or model
    invalidates it by the same mechanism that protects the NER cache from a stale entry.
    """

    def _key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return f"{self.model}:{classify_fingerprint()}:{digest}"


def classify_fingerprint() -> str:
    return hashlib.sha256("\x00".join([_SYSTEM, _PROMPT, ",".join(LABELS), str(BATCH)]).encode()).hexdigest()[:8]


class LlmNameClassifier:
    """Callable `(text, candidates, chapter=...) -> list[Verdict | None]`; None is "the call failed".

    Cached per (model, candidate, sentence). With no client the hybrid detector is built without one of these at all
    and its classifier route rejects (precision over recall).
    """

    def __init__(self, client: object, *, novel_id: str = "", cache: ClassifyCache | None = None) -> None:
        self.client = client
        self.novel_id = novel_id
        self.cache = cache
        self.calls = 0

    def __call__(
        self, text: str, candidates: Sequence[NameCandidate], *, chapter: float | None = None
    ) -> list[Verdict | None]:
        verdicts: list[Verdict | None] = [None] * len(candidates)
        pending: list[tuple[int, str, str]] = []  # (index into candidates, surface, sentence)
        for i, c in enumerate(candidates):
            sentence = sentence_around(text, c.start, c.end)
            hit = self.cache.get(f"{c.surface}\x00{sentence}") if self.cache is not None else None
            if hit is not None:
                verdicts[i] = Verdict(hit["is_name"] == "1", hit["label"], hit.get("reason", ""))
            else:
                pending.append((i, c.surface, sentence))
        for lo in range(0, len(pending), BATCH):
            batch = pending[lo : lo + BATCH]
            lines = "\n".join(f'{n}. candidate: "{s}" | sentence: "{sent}"' for n, (_i, s, sent) in enumerate(batch))
            try:
                result = self.client.complete(  # type: ignore[attr-defined]
                    Task.NER_CLASSIFY,
                    _PROMPT.format(items=lines),
                    NerClassifyResponse,
                    system=_SYSTEM,
                    novel_id=self.novel_id,
                    chapter=chapter,
                )
            except Exception as exc:
                log.warning("name classification failed on chapter %s: %s", chapter, exc)
                continue
            self.calls += 1
            for item in result.value.items:
                if not 0 <= item.id < len(batch):
                    continue
                index, surface, sentence = batch[item.id]
                label = item.label.strip().lower()
                verdict = Verdict(item.is_name, label if label in LABELS else "character", item.reason)
                verdicts[index] = verdict
                if self.cache is not None:
                    self.cache.put(
                        f"{surface}\x00{sentence}",
                        {"is_name": "1" if verdict.is_name else "0", "label": verdict.label, "reason": verdict.reason},
                    )
        return verdicts
