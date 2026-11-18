"""A second, narrower look at speakers the reader named without a speech tag in the line's own block.

Why this exists (speaker_diag REPORT 6.7): after the reader every accepted answer sits at a flat 0.8, so there is nothing to
rank by, and 40 of v13's 57 misses were lines whose baseline row was an anonymous slot or a chorus, i.e. lines the model
named although the block names nobody. The reader answers 15-40 tags in one call; this asks one yes/no question per line
about one person, with a small passage around it, which is an easier task than picking a name from a list. A "no" returns
the line to unresolved (voiced as an unnamed speaker), the same precision-over-recall trade as the vocative and gender checks
(non-negotiable 9). It runs after the reader and changes only CONTEXTUAL_LLM rows; a reviewer's HUMAN decision and a tag in
the block itself are never questioned.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from echotales.core.enums import AttributionMethod, SpanType
from echotales.core.models import Chapter
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.tasks import Task
from echotales.pipeline.reader.quotes import QUOTE, quote_starts
from echotales.pipeline.reader.speakers_pass import first_person_tag, own_explicit_tag

#: Characters of context kept on each side of the block holding the line.
CONTEXT_CHARS = 700
_QUOTE_SPANS = frozenset({SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE, SpanType.CROWD_REACTION})

#: When a list, one dict per question (chapter, tag, person, verdict, kept), for the run log.
TRACE: list[dict] | None = None  # type: ignore[type-arg]


class VerifyAnswer(BaseModel):
    verdict: str = "unclear"


@dataclass(slots=True)
class VerifyReport:
    asked: int = 0
    yes: int = 0
    no: int = 0
    unclear: int = 0
    rejected: int = 0
    skipped_tagged: int = 0


def _passage(chapter: Chapter, block_index: int, q: int) -> str:
    """Previous block, the block with the asked line marked, next block: enough turn-taking evidence, little else."""
    blocks = {b.index: b.text for b in chapter.blocks}
    parts: list[str] = []
    before = blocks.get(block_index - 1, "")
    if before:
        parts.append(before[-CONTEXT_CHARS:])
    counter = iter(range(10_000))
    parts.append(QUOTE.sub(lambda m: f">>>{m.group(0)}<<<" if next(counter) == q else m.group(0), blocks.get(block_index, "")))
    after = blocks.get(block_index + 1, "")
    if after:
        parts.append(after[:CONTEXT_CHARS])
    return "\n\n".join(parts)


def _prompt(name: str, passage: str) -> str:
    return (
        "Below is a passage of a novel. One quoted line is marked >>> like this <<<.\n\n"
        f"{passage}\n\n"
        f"Question: is the marked line spoken by {name}?\n"
        f"Answer yes only if the passage shows it: a speech tag naming {name}, an action by {name} right next to the line, or "
        f"two people clearly taking turns with {name} as the one whose turn it is. Answer no if the line is spoken by "
        f"someone else, by a group or an unnamed person, or if {name} is only the person spoken to or talked about. "
        "Answer unclear if the passage does not settle it.\n"
        'Answer as JSON: {"verdict": "yes" or "no" or "unclear"}'
    )


def verify_chapter(
    store: Store, client: ModelClient, chapter: Chapter, *, reject_unclear: bool = False,
) -> VerifyReport:
    """Ask once per model-named, untagged line; send the lines that fail back to unresolved."""
    report = VerifyReport()
    novel_id, number = chapter.novel_id, chapter.number
    blocks = {b.index: b.text for b in chapter.blocks}
    spans = [s for s in store.get_spans(novel_id, number) if s.span_type in _QUOTE_SPANS]
    for span in spans:
        if span.attribution_method is not AttributionMethod.CONTEXTUAL_LLM or not span.speaker_self_id:
            continue
        if ":anon:" in span.speaker_self_id:
            continue
        text = blocks.get(span.block_index, "")
        starts = quote_starts(text)
        q = next((i for i, st in enumerate(starts) if span.start <= st < span.end), None)
        if q is None:
            continue
        if own_explicit_tag(store, span.speaker_self_id, text, q) or first_person_tag(text, q):
            report.skipped_tagged += 1
            continue
        entity = store.get_self(span.speaker_self_id)
        name = entity.canonical_label if entity else span.speaker_self_id
        answer = client.complete(
            Task.READER, _prompt(name, _passage(chapter, span.block_index, q)), VerifyAnswer, novel_id=novel_id, chapter=number
        ).value.verdict.strip().lower()
        verdict = "yes" if answer.startswith("yes") else "no" if answer.startswith("no") else "unclear"
        report.asked += 1
        setattr(report, verdict, getattr(report, verdict) + 1)
        reject = verdict == "no" or (verdict == "unclear" and reject_unclear)
        if TRACE is not None:
            TRACE.append({"chapter": number, "tag": f"{span.block_index}.{q}", "person": name, "verdict": verdict, "rejected": reject})
        if reject:
            store.set_span_speaker(novel_id, span.id, None, AttributionMethod.UNRESOLVED.value, 0.0)
            report.rejected += 1
    store.conn.commit()
    return report
