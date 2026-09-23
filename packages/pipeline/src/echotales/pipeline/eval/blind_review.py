"""Blind annotation: show the reviewer the text, never the system's answer.

Built now, run later by the project owner (COMPLETION_PLAN Track 2 item 7).

**Why blind, specifically.** EVOLUTION 4.74 retracted a headline result whose
gold was `SELECT`ed from the pipeline's own `mention` table. The structural
guard added there (`gold.py::CIRCULAR_DRAFTERS`) catches that exact shape --
a record whose `drafted_by` names a pipeline-reading drafter -- but it cannot
catch the softer version: a human reviewer shown the system's `target_id`
alongside the text, who agrees with it because it is there. Anchoring is not
detectable from the record afterwards. The only defence is not showing it.

So a task carries the surface and a window of source text and nothing else:
no `target_id`, no system label, no cluster, and no ordering that reveals
grouping (tasks are shuffled by an explicit seed). Two occurrences of one
person must receive the same name from the reviewer because the reviewer
recognised them, not because the tool grouped them -- which is precisely what
coreference annotation is.

The round trip is deliberately two files: tasks out, answers back. A reviewer
edits a plain JSONL in any editor, and the answer file is the durable artifact
that `confirmed_by` points at.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.eval.gold import (
    GoldMention,
    GoldSet,
    MentionKind,
    Provenance,
    ReviewDepth,
)

#: Characters of source text either side of the surface. Wide enough to settle
#: an anaphor, narrow enough that a reviewer is not re-reading the chapter.
WINDOW_CHARS = 240

#: System-derived fields a task may never contain. Asserted in the writer
#: rather than left to review: the whole value of this format is the absence
#: of these, and a field added later "just for debugging" would silently void
#: every annotation made against that file.
#:
#: `identity` is deliberately NOT here -- it is the reviewer's own answer
#: slot, shipped empty. That distinction is the point: what must not leak is
#: the system's answer, not the existence of a place to put a human one.
FORBIDDEN_TASK_FIELDS = frozenset(
    {"target_id", "target_kind", "label", "canonical_label", "cluster", "method", "confidence"}
)

#: Answer slots, which must be empty in an emitted task file. A pre-filled
#: answer is an anchor whatever produced it.
ANSWER_FIELDS: tuple[str, ...] = ("identity", "not_an_entity")


@dataclass(slots=True)
class BlindTask:
    task_id: str
    novel_id: str
    chapter: float
    offset: int
    surface: str
    window: str

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "novel_id": self.novel_id,
            "chapter": self.chapter,
            "offset": self.offset,
            "surface": self.surface,
            "window": self.window,
            # The two fields the reviewer fills in. Present and empty so the
            # file is editable without the reviewer having to remember the
            # schema.
            "identity": "",
            "not_an_entity": False,
        }


def _task_id(novel_id: str, chapter: float, offset: int, surface: str) -> str:
    raw = f"{novel_id}|{chapter:g}|{offset}|{surface}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _window(text: str, offset: int, surface: str) -> str:
    start = max(0, offset - WINDOW_CHARS)
    end = min(len(text), offset + len(surface) + WINDOW_CHARS)
    return text[start:end]


def build_tasks(
    store: Store,
    novel_id: str,
    *,
    chapters: list[float] | None = None,
    sample: int = 0,
    seed: int = 20260923,
) -> list[BlindTask]:
    """One task per detected mention, shuffled, with no system answer attached.

    `sample` caps the count *after* shuffling, so a 150-task subset is a
    random sample of the volume rather than its first 150 mentions -- early
    chapters are the easy case (few entities, no aliases yet) and annotating
    only those would overstate agreement.
    """
    tasks: list[BlindTask] = []
    wanted = set(chapters) if chapters else None
    for chapter in store.iter_chapters(novel_id):
        if wanted is not None and chapter.number not in wanted:
            continue
        text = chapter.story_text
        for mention in store.get_mentions(novel_id, chapter.number):
            tasks.append(
                BlindTask(
                    task_id=_task_id(novel_id, chapter.number, mention.offset, mention.text),
                    novel_id=novel_id,
                    chapter=chapter.number,
                    offset=mention.offset,
                    surface=mention.text,
                    window=_window(text, mention.offset, mention.text),
                )
            )

    random.Random(seed).shuffle(tasks)
    return tasks[:sample] if sample else tasks


def write_tasks(tasks: list[BlindTask], path: Path | str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for task in tasks:
            row = task.as_dict()
            leaked = FORBIDDEN_TASK_FIELDS & set(row)
            if leaked:
                raise ValueError(
                    f"blind task would leak the system's answer: {sorted(leaked)}. "
                    "Every annotation made against such a file is anchored and "
                    "cannot be used as gold."
                )
            prefilled = [f for f in ANSWER_FIELDS if row.get(f)]
            if prefilled:
                raise ValueError(
                    f"blind task ships a pre-filled answer: {prefilled}. A "
                    "suggested answer anchors the reviewer just as the system's "
                    "own would."
                )
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return p


def read_answers(
    path: Path | str,
    *,
    novel_id: str,
    confirmed_by: str,
    store: Store | None = None,
) -> GoldSet:
    """Turn a reviewed task file into per-record confirmed gold.

    `confirmed_by` is required and must be a person. Every record comes back
    `ReviewDepth.PER_RECORD` because this format has no other mode -- a
    reviewer either answered a task or left it blank, and a blank one is
    skipped rather than counted as agreement. That is the distinction
    EVOLUTION 4.74's bulk approval erased.

    `provenance=HUMAN` with `drafted_by` left empty: a person read the window
    and wrote the name. Nothing about the pipeline's own answer was visible
    while they did it, which is the property that makes this gold and the
    retracted 6,952 records not.
    """
    if not confirmed_by.strip():
        raise ValueError(
            "confirmed_by is required: a confirmation that names nobody is how "
            "6,952 machine-drafted records became 'human' provenance "
            "(EVOLUTION 4.74)"
        )

    texts: dict[float, str] = {}
    if store is not None:
        for chapter in store.iter_chapters(novel_id):
            texts[chapter.number] = chapter.story_text

    mentions: list[GoldMention] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        identity = str(row.get("identity", "")).strip()
        not_entity = bool(row.get("not_an_entity", False))
        if not identity and not not_entity:
            # Unanswered. Skipped, never defaulted -- a blank is "nobody
            # looked", and counting it as agreement is the whole failure mode.
            continue
        chapter = float(row["chapter"])
        offset = int(row["offset"])
        surface = str(row["surface"])
        context = row.get("window", "")
        if store is not None and chapter in texts:
            context = _window(texts[chapter], offset, surface)
        mentions.append(
            GoldMention(
                novel_id=novel_id,
                chapter=chapter,
                offset=offset,
                surface=surface,
                identity="" if not_entity else identity,
                kind=MentionKind.NOT_AN_ENTITY if not_entity else MentionKind.CHARACTER,
                context=context,
                provenance=Provenance.HUMAN,
                confirmed=True,
                confirmed_by=confirmed_by,
                review_depth=ReviewDepth.PER_RECORD,
            )
        )
    return GoldSet(novel_id, sorted(mentions, key=lambda m: (m.chapter, m.offset)))
