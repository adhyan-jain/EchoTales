"""Baseline B -- LLMLINK-style dual-LLM memorisation (plans.md Section 11/13, item 7).

The second academic comparison point. Where Baseline A gives one long-context
model everything at once, this reproduces the **dual-LLM + reference-tracking**
architecture LLMLINK introduced and LINK-KG extends:

  LLM-1 (EXTRACTOR)  reads one small chunk and lists the character mentions in
                     it, with a short descriptor for each. It never sees the
                     entity memory, so it cannot be primed by it.
  LLM-2 (LINKER)     sees one mention plus its descriptor and the compact
                     entity MEMORY, and returns link-to-existing or mint-new.
                     It never sees the chapter text, so it decides from the
                     memory and the descriptor alone -- the whole point of a
                     memorisation architecture.

`docs/PRIOR_ART_LINKKG.md` verifies (2026-09-24, against the full paper) that
LINK-KG describes LLMLINK as "effective on structured, homogeneous datasets
like book chapters" while it "struggles with complex texts involving
multi-role entities, shifting aliases, and plural references". Those are this
project's exact subject, which is why LLMLINK -- not LINK-KG, a legal-document
system scored on node-duplication rates -- is the right comparison target.

**What this baseline deliberately does NOT have**, because their absence is
the comparison:
  - no temporal binding (no interval, no story time, no knowledge time)
  - no transferable-title detection: a title that changes holder is invisible
  - no correction loop, no DEFER queue, no escalation, no human review
  - no gazetteer, so nothing compounds as the volume progresses
  - no Self/Persona split, no truth status, no observer
The memory is a flat list of entities that only ever grows.

**Not a strawman.** Same model (`qwen2.5:7b`), same local Ollama, same zero
API spend, same offset-recovery code and the same `Mention` round-trip as
Baseline A, so all three systems are scored by one unmodified `score_b3`.
Where the architecture genuinely helps it should show: the linker sees a
compact memory rather than 23k tokens of raw text, so it should not degrade
with section length the way a long-context prompt does.

**Cost shape differs sharply from Baseline A, and that is a reported result,
not an inconvenience.** Baseline A is one call per ~10 chapters. This is one
extractor call per chunk plus one linker call per mention, so it is
O(mentions) rather than O(sections) -- hundreds of calls per chapter range
instead of one. Wall time and call counts are recorded per run for exactly
that reason.

Scored against an LLM-derived SILVER reference set, never human gold; see
`docs/GOLD_DATASET_README.md`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.eval.baseline_a import _locate, _to_block_local
from echotales.pipeline.eval.coref_score import _block_starts, score_b3
from echotales.pipeline.eval.gold import SILVER_BANNER, GoldSet, read_gold
from echotales.pipeline.ingest.runner import ingest_novel
from echotales.pipeline.llm.base import LLMRequest, LLMUnavailable
from echotales.pipeline.llm.ollama import OllamaProvider
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

#: Chunk size for the extractor, in characters. Deliberately small: a
#: memorisation architecture exists precisely so the model does not need the
#: whole document in context, and sizing this at Baseline A's ~10-chapter
#: window would erase the distinction being measured.
CHUNK_CHARS = 3_000

#: How many memory entries the linker sees. LLMLINK's contribution is a
#: *compact* running reference, not a growing transcript; leaving this
#: unbounded turns the linker into Baseline A with extra steps.
MEMORY_LIMIT = 60


class ExtractedMention(BaseModel):
    surface: str
    context: str = ""
    descriptor: str = ""


class ExtractionOut(BaseModel):
    mentions: list[ExtractedMention] = Field(default_factory=list)


class LinkOut(BaseModel):
    #: Existing entity id to link to, or "NEW" to mint one.
    entity_id: str = ""
    canonical_name: str = ""


@dataclass
class MemoryEntry:
    id: str
    name: str
    descriptors: list[str] = field(default_factory=list)

    def render(self) -> str:
        detail = "; ".join(self.descriptors[:3])
        return f"{self.id}: {self.name}" + (f" -- {detail}" if detail else "")


_EXTRACT_SYSTEM = """\
You extract character mentions from a passage of a serialized web novel.

Return every span in the passage that refers to a specific, individually \
identifiable person: personal names, titles used to denote a person, \
epithets, and relational references ("his father", "the elder"). Do NOT \
return generic plurals ("the villagers"), places, organizations, or items.

For each mention give:
  surface    -- the exact substring as it appears, copied character for character
  context    -- about 10 words of the passage around it, copied verbatim
  descriptor -- a SHORT neutral description of who this appears to be, from \
this passage alone (e.g. "young man being chased", "clan elder presiding"). \
Never guess a name that does not appear in the passage.

You have no memory of earlier passages and must not invent one.
"""

_LINK_SYSTEM = """\
You maintain a character memory for a serialized web novel.

You are given ONE mention -- its surface form and a short descriptor -- and \
the current MEMORY of characters already seen. Decide whether this mention \
refers to a character already in memory.

Return entity_id = the id of the matching memory entry if it refers to \
someone already there, even under a different name, title or epithet.
Return entity_id = "NEW" if it is someone not yet in memory.

Also return canonical_name: the best name for this character from what you \
know. If linking, you may keep the existing name.

You CANNOT see the novel text -- decide from the memory and the descriptor \
alone. Do not speculate beyond them.
"""


@dataclass
class BaselineBResult:
    chapters: tuple[int, int]
    mentions: list[dict]
    entities: list[dict]
    extractor_calls: int
    linker_calls: int
    prompt_tokens: int
    output_tokens: int
    wall_seconds: float

    def summary(self) -> str:
        return (
            f"baseline B ch{self.chapters[0]}-{self.chapters[1]}: "
            f"{len(self.mentions):,} mentions, {len(self.entities)} entities, "
            f"{self.extractor_calls} extractor + {self.linker_calls} linker calls "
            f"({self.extractor_calls + self.linker_calls} total), "
            f"{self.prompt_tokens:,} prompt + {self.output_tokens:,} output tokens, "
            f"{self.wall_seconds:.1f}s"
        )


def _chunks(text: str, size: int = CHUNK_CHARS) -> list[tuple[int, str]]:
    """Split on paragraph boundaries, never mid-sentence.

    Offsets are recovered against the full chapter text by `_locate`; the
    chunk's own start offset is carried only so a caller can keep the search
    local enough to stay unambiguous on repeated surfaces.
    """
    out: list[tuple[int, str]] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            para = text.rfind("\n\n", start + size // 2, end)
            if para != -1:
                end = para
        out.append((start, text[start:end]))
        start = end
    return out


def run_baseline_b(
    store: Store,
    novel_id: str,
    provider: OllamaProvider,
    lo: int,
    hi: int,
) -> BaselineBResult:
    memory: list[MemoryEntry] = []
    by_id: dict[str, MemoryEntry] = {}
    mentions: list[dict] = []
    extractor_calls = linker_calls = 0
    prompt_tokens = output_tokens = 0
    started = time.monotonic()

    for number in range(lo, hi + 1):
        chapter = store.get_chapter(novel_id, float(number))
        if chapter is None:
            continue
        story_text = "\n\n".join(b.text for b in chapter.blocks if b.block_type.is_story_content)
        used: set[int] = set()

        for chunk_start, chunk in _chunks(story_text):
            # --- LLM-1: extraction, memory-blind by construction ------------
            try:
                extracted = provider.complete(
                    LLMRequest(
                        stage="baseline_b_extract",
                        system=_EXTRACT_SYSTEM,
                        prompt=f"Passage (chapter {number}):\n\n{chunk}",
                        max_tokens=1536,
                    ),
                    ExtractionOut,
                )
            except LLMUnavailable:
                raise
            except Exception as exc:  # a malformed chunk must not kill the run
                log.warning("ch%d extraction failed at %d: %s", number, chunk_start, exc)
                continue
            extractor_calls += 1
            prompt_tokens += extracted.prompt_tokens
            output_tokens += extracted.completion_tokens

            for item in extracted.value.mentions:
                if not item.surface.strip():
                    continue
                # --- LLM-2: linking, text-blind by construction -------------
                rendered = "\n".join(e.render() for e in memory[-MEMORY_LIMIT:]) or "(empty)"
                try:
                    linked = provider.complete(
                        LLMRequest(
                            stage="baseline_b_link",
                            system=_LINK_SYSTEM,
                            prompt=(
                                f"MEMORY:\n{rendered}\n\n"
                                f"MENTION: {item.surface!r}\n"
                                f"DESCRIPTOR: {item.descriptor or '(none)'}"
                            ),
                            max_tokens=128,
                        ),
                        LinkOut,
                    )
                except LLMUnavailable:
                    raise
                except Exception as exc:
                    log.warning("link failed for %r: %s", item.surface, exc)
                    continue
                linker_calls += 1
                prompt_tokens += linked.prompt_tokens
                output_tokens += linked.completion_tokens

                target = linked.value.entity_id.strip()
                if target and target.upper() != "NEW" and target in by_id:
                    entry = by_id[target]
                    if item.descriptor and item.descriptor not in entry.descriptors:
                        entry.descriptors.append(item.descriptor)
                else:
                    entry = MemoryEntry(
                        id=f"b{len(memory) + 1}",
                        name=linked.value.canonical_name.strip() or item.surface.strip(),
                        descriptors=[item.descriptor] if item.descriptor else [],
                    )
                    memory.append(entry)
                    by_id[entry.id] = entry

                offset = _locate(story_text, item.surface, item.context, used)
                if offset is None:
                    continue
                used.add(offset)
                mentions.append(
                    {
                        "chapter": float(number),
                        "surface": item.surface,
                        "abs_offset": offset,
                        "entity_id": entry.id,
                    }
                )

    return BaselineBResult(
        chapters=(lo, hi),
        mentions=mentions,
        entities=[{"id": e.id, "name": e.name, "descriptors": e.descriptors} for e in memory],
        extractor_calls=extractor_calls,
        linker_calls=linker_calls,
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        wall_seconds=time.monotonic() - started,
    )


def materialize_mentions(store: Store, novel_id: str, result: BaselineBResult) -> int:
    """Insert this baseline's assignments as real `Mention` rows.

    Same round-trip as Baseline A, for the same reason: `score_b3` and
    `score_all` then run completely unmodified, so all three systems are
    measured by one scorer rather than three re-derivations of B-cubed.
    """
    from echotales.core.enums import AliasType, Provenance, ReferenceMode, SpanType
    from echotales.core.models import Mention

    by_chapter: dict[float, list[dict]] = {}
    for m in result.mentions:
        by_chapter.setdefault(m["chapter"], []).append(m)

    inserted = 0
    for chapter, rows in by_chapter.items():
        chapter_obj = store.get_chapter(novel_id, chapter)
        if chapter_obj is None:
            continue
        starts = _block_starts(store, novel_id, chapter)
        lengths = {
            b.index: len(b.text) for b in chapter_obj.blocks if b.block_type.is_story_content
        }
        for i, row in enumerate(rows):
            block_index, local = _to_block_local(starts, lengths, row["abs_offset"])
            store.add_mention(
                Mention(
                    id=f"{novel_id}:baseline_b:{chapter:g}:{i}",
                    novel_id=novel_id,
                    chapter=chapter,
                    block_index=block_index,
                    offset=local,
                    text=row["surface"],
                    alias_type=AliasType.RIGID_NAME,
                    span_type=SpanType.NARRATION,
                    reference_mode=ReferenceMode.DIRECT,
                    target_id=f"baseline_b_{row['entity_id']}",
                    confidence=1.0,
                    method="baseline_b",
                    provenance=Provenance.MODEL,
                )
            )
            inserted += 1
    return inserted


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description="Baseline B -- dual-LLM memorisation")
    parser.add_argument("--novel", default="reverend-insanity")
    parser.add_argument("--db", default="data/reruns/baseline-b.db")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--chapters", default="1-5", help="range, e.g. 1-5")
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--gold", default=None)
    parser.add_argument("--out", default=None, help="write the run record here as JSON")
    args = parser.parse_args()

    lo_s, _, hi_s = args.chapters.partition("-")
    lo, hi = int(lo_s), int(hi_s or lo_s)

    provider = OllamaProvider(
        model=args.model, host=args.host, timeout=args.timeout, num_ctx=args.num_ctx
    )
    if not provider.available():
        print(
            f"ollama unavailable at {args.host} (model {args.model}). "
            "Start it with `ollama serve` and pull the model.",
            file=sys.stderr,
        )
        return 2

    store = Store(args.db)
    ingest_novel(store, args.novel, sources_path="data/sources.toml", chapters=f"{lo}-{hi}")

    result = run_baseline_b(store, args.novel, provider, lo, hi)
    print("\n" + result.summary())
    inserted = materialize_mentions(store, args.novel, result)
    print(f"materialized {inserted:,} mentions into {args.db}")

    gold_path = Path(args.gold or f"data/gold/{args.novel}.jsonl")
    if gold_path.exists():
        gold = read_gold(gold_path, novel_id=args.novel)
        silver = GoldSet(
            args.novel,
            [m for m in gold.silver_only.entities_only.mentions if lo <= m.chapter <= hi],
        )
        if silver.mentions:
            print(f"\n--- baseline B vs SILVER, ch{lo}-{hi} ---")
            print(f"    {SILVER_BANNER}")
            print(score_b3(store, args.novel, silver).summary())
        else:
            print(f"\nno silver records in ch{lo}-{hi} of {gold_path} -- not scored.")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "baseline": "B",
                    "architecture": "dual-LLM memorisation (LLMLINK-style)",
                    "model": args.model,
                    "num_ctx": args.num_ctx,
                    "chunk_chars": CHUNK_CHARS,
                    "memory_limit": MEMORY_LIMIT,
                    "chapters": [lo, hi],
                    "extractor_calls": result.extractor_calls,
                    "linker_calls": result.linker_calls,
                    "prompt_tokens": result.prompt_tokens,
                    "output_tokens": result.output_tokens,
                    "wall_seconds": result.wall_seconds,
                    "mentions": len(result.mentions),
                    "entities": result.entities,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"run record: {out}")

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
