"""How each line is performed: one emotion and an intensity per quoted line, and a mood per narration passage.

Why this exists: the audiobook had no emotion source except speech-tag adverbs ("said coldly"). On the last RI render
(2026-09-11, 245 lines) 169 lines were synthesised at the same narration setting and only 9 got anything but a
neutral reference clip, because most quoted lines carry no adverb at all -- the emotion is in what is said and what
just happened, which only a reader of the passage can see.

Why a separate pass rather than one more field in the speaker prompt: the speaker prompt is measured (85% overall,
EVOLUTION 4.123) and a second question in the same call is an untested change to that number. This pass writes its
own table (`span_emotion`) and nothing else.

The label set is EARS's own emotion names (`voice/bank.py::load_ears`), so a label picks that recording of the cast
voice directly; `BankVoice.clip_for` degrades it for banks without that recording. The model is shown plain words
("angry", "afraid") because a 9B model answers those more reliably than corpus names.

Non-negotiable 10 is not enforced here: an explicit delivery marker still overrides this label at synthesis time
(`voice/delivery.py::settings_for`), so "he said expressionlessly" stays flat whatever the passage feels like.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from echotales.core.enums import SpanType
from echotales.core.models import Chapter, Span
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.tasks import Task
from echotales.pipeline.reader.quotes import quote_starts
from echotales.pipeline.reader.speakers_pass import MAX_ATTEMPTS, _span_at, windows

#: Word shown to the model -> EARS emotion (or reading style) stored and voiced.
LABELS: dict[str, str] = {
    "neutral": "neutral",
    "calm": "serenity",
    "angry": "anger",
    "afraid": "fear",
    "desperate": "distress",
    "in pain": "pain",
    "sad": "sadness",
    "disappointed": "disappointment",
    "guilty": "guilt",
    "embarrassed": "embarassment",  # sic: the EARS file name
    "happy": "contentment",
    "amused": "amusement",
    "tender": "adoration",
    "relieved": "relief",
    "surprised": "amazement",
    "realizing": "realization",
    "confused": "confusion",
    "curious": "interest",
    "proud": "pride",
    "contemptuous": "disgust",
    "disgusted": "disgust",
    "whispering": "whisper",
    "shouting": "loud",
}

_NARRATION = frozenset({SpanType.NARRATION_ACTION, SpanType.NARRATION_DESCRIPTION, SpanType.NARRATION_EXPOSITION})
_QUOTED = frozenset({SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE, SpanType.CROWD_REACTION})


class LineEmotion(BaseModel):
    tag: str
    emotion: str = "neutral"
    intensity: int = 1


class DeliveryAnswers(BaseModel):
    #: The mood a narrator reads this passage in.
    mood: str = "neutral"
    mood_intensity: int = 1
    lines: list[LineEmotion] = Field(default_factory=list)


@dataclass(slots=True)
class DeliveryReport:
    windows: int = 0
    lines: int = 0
    narration: int = 0
    unknown_labels: int = 0
    missing: int = 0
    emotions: Counter[str] = field(default_factory=Counter)


def label(word: str) -> str | None:
    """The stored emotion for a model's answer, or None when it is not in the vocabulary."""
    return LABELS.get(" ".join(word.casefold().replace("_", " ").split()))


def _prompt(text: str, tags: list[str]) -> str:
    words = ", ".join(LABELS)
    tag_part = (
        f"Every quoted utterance is tagged [block.number] just before its opening quote mark. For EACH of these tags, "
        f"say how the line is spoken: {', '.join(tags)}.\n"
        if tags
        else ""
    )
    example = ", ".join(f'{{"tag": "{t}", "emotion": "angry", "intensity": 2}}' for t in tags)
    return (
        "Below is a passage of a novel that will be read aloud as an audiobook.\n"
        f"{tag_part}"
        "Also give the mood the narrator should read the passage's narration in.\n"
        f"Choose every emotion from exactly this list: {words}.\n"
        "Judge from what is said, why, and what just happened, not from punctuation alone. A character described as "
        "calm, cold or expressionless is calm or neutral even in a violent scene. Use whispering or shouting only when "
        "the text says the line is whispered or shouted. Intensity: 1 = slight, 2 = clear, 3 = overwhelming. Most "
        "narration is neutral or calm at intensity 1.\n\n"
        f"{text}\n\n"
        'Answer as JSON, like this: {"mood": "neutral", "mood_intensity": 1, "lines": [' + example + "]}"
    )


def _intensity(value: int) -> int:
    return max(1, min(3, int(value)))


def read_chapter_delivery(store: Store, client: ModelClient, chapter: Chapter) -> DeliveryReport:
    """Label every quoted line and narration span of one chapter, replacing any earlier labels for it."""
    report = DeliveryReport()
    novel_id, number = chapter.novel_id, chapter.number
    blocks = {b.index: b.text for b in chapter.blocks}
    spans = list(store.get_spans(novel_id, number))
    quoted = [s for s in spans if s.span_type in _QUOTED]
    rows: dict[str, tuple[str, int]] = {}

    for text in windows(chapter, require_quote=False):
        report.windows += 1
        wanted = re.findall(r"\[(\d+\.\d+)\]", text)
        answers: dict[str, LineEmotion] = {}
        mood: tuple[str, int] | None = None
        pending = list(wanted)
        for _ in range(MAX_ATTEMPTS):
            result = client.complete(Task.READER, _prompt(text, pending), DeliveryAnswers, novel_id=novel_id, chapter=number)
            if mood is None:
                mood = (label(result.value.mood) or "neutral", _intensity(result.value.mood_intensity))
            for entry in result.value.lines:
                if entry.tag in pending:
                    answers[entry.tag] = entry
            pending = [t for t in pending if t not in answers]
            if not pending:
                break
        report.missing += len(pending)

        for tag, entry in answers.items():
            block_index, q = (int(x) for x in tag.split("."))
            starts = quote_starts(blocks.get(block_index, ""))
            span = _span_at(quoted, block_index, starts[q]) if q < len(starts) else None
            if span is None:
                continue
            emotion = label(entry.emotion)
            if emotion is None:
                report.unknown_labels += 1
                emotion = "neutral"
            rows[span.id] = (emotion, _intensity(entry.intensity))
            report.lines += 1
            report.emotions[emotion] += 1

        window_blocks = {int(b) for b in re.findall(r"^#(\d+):", text, flags=re.MULTILINE)}
        for span in _narration_in(spans, window_blocks):
            rows[span.id] = mood or ("neutral", 1)
            report.narration += 1

    store.set_span_emotions(novel_id, number, rows)
    return report


def _narration_in(spans: list[Span], block_indexes: set[int]) -> list[Span]:
    return [s for s in spans if s.span_type in _NARRATION and s.block_index in block_indexes]
