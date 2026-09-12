"""Baseline A -- long-context LLM, no graph, no gazetteer (plans.md Section 11/13).

The comparison plans.md asks for: one call per volume section, given raw
chapter text plus a running entity list, asked to do the same coreference
task the resolver does -- no incremental evidence accumulation, no
gazetteer, no temporal scoping. This module is that baseline, run for real
against Reverend Insanity and scored with the project's own B-cubed scorer
(`eval/coref_score.py`) against the same `data/gold/reverend-insanity.jsonl`
the resolver is measured against. See EVOLUTION.md's "gold-set comparison
wired into `eval`" entry for the resolver's own last-measured number on this
file (precision=100% recall=95% f1=97.4% over 1,816 entity mentions,
ch1-60) -- that number predates the gold set's confirmation pass, and
`data/gold/reverend-insanity.jsonl` is 100% human-confirmed as of this
writing, so it is now both the draft and the confirmed-tier number
(`GoldSet.confirmed_only` is a no-op on this file today).

**Local Ollama only, zero API spend** -- this reuses `OllamaProvider`
directly (`pipeline/llm/ollama.py`) rather than `LLMRouter`
(`pipeline/llm/router.py`): the router's whole reason to exist is deciding
*when* to escalate to the paid tier, and this baseline is a measurement of
what the unaided local tier alone can do, so routing to the API would
defeat the point, not just cost money.

**Section size is capped by the model's real context window, not by
plans.md's "30 chapters" figure.** `ollama show qwen2.5:7b` reports a
32768-token architecture limit, and it is a hard ceiling, not a request
knob: a 30-chapter section measured at prompt_eval_count=32768 regardless
of whether `num_ctx` in the request was 32768 or 65536 -- the model
silently truncates rather than raising it. Measured directly (see
`_MODEL_CTX_CEILING`'s call site in `main`): RI runs ~2,300 input tokens
per chapter, so 10 chapters is ~23,300 input tokens, and 15 already clamps
at the ceiling. `num_ctx` covers *input + output combined* in ollama, so a
10-chapter section (not 30) is the largest that leaves real headroom for
the growing roster and an output budget large enough for a chapter with
hundreds of mentions -- the default section size below reflects that
measurement, not plans.md's figure taken at face value.

Offset recovery: the model is not asked for a character offset (LLMs count
tokens, not characters, and would fabricate one). It is asked for the exact
surface string plus a short verbatim context window, and this module finds
the literal offset itself via substring search + local context matching
(`_locate`) -- the same problem `coref_score._system_partition` solves for
the pipeline's own mentions, at a coarser tolerance since a local model's
"verbatim" quotes are not always exact.

Deliberately NOT importing anything from `resolve/` -- no incremental
evidence accumulation, no gazetteer, no alias-type classification. It
reuses only `packages/core` (Chapter/Mention models + Store) and the real
ingest stage to get the exact same `story_text` the gold offsets were
computed against, then round-trips its own output through the real
`Mention` table so the existing `score_b3` runs completely unmodified.
"""

from __future__ import annotations

import argparse
import difflib
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from echotales.core.enums import AliasType, Provenance, ReferenceMode, SpanType
from echotales.core.models import Mention
from echotales.core.store import Store
from echotales.pipeline.eval.coref_score import _block_starts, score_b3
from echotales.pipeline.eval.gold import GoldSet, read_gold
from echotales.pipeline.ingest.adapters import ChapterRange
from echotales.pipeline.ingest.runner import ingest_novel
from echotales.pipeline.llm.base import LLMRequest, LLMUnavailable
from echotales.pipeline.llm.ollama import OllamaProvider

log = logging.getLogger(__name__)

# qwen2.5:7b's architecture ceiling (`ollama show qwen2.5:7b`), not a tunable
# knob -- num_ctx above this is silently clamped by the model, not honored.
_MODEL_CTX_CEILING = 32768


# ---- structured-output schema --------------------------------------------
# Mirrors OllamaProvider's contract: a Pydantic schema is rendered into
# `format` for constrained decoding AND into the prompt itself
# (`schema_instructions`) since constrained decoding fixes syntax, not
# comprehension, for a 7B model.


class EntityOut(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""


class MentionOut(BaseModel):
    chapter: float
    surface: str
    context: str = ""
    entity_id: str


class SectionOut(BaseModel):
    entities: list[EntityOut] = Field(default_factory=list)
    mentions: list[MentionOut] = Field(default_factory=list)


_INSTRUCTIONS = """\
You are performing pure in-context character coreference resolution for a \
serialized web novel. You have NO external knowledge graph, NO gazetteer, and \
NO memory beyond what is given to you in this single request -- this is \
Baseline A from EchoTales' evaluation plan: the honest measure of what a \
long-context LLM achieves completely unaided.

You are given the raw text of several consecutive chapters of "Reverend \
Insanity", plus (if this is not the first section) a running list of \
characters already identified in earlier chapters.

TASK: find every mention of a character -- a specific, individually \
identifiable person -- in the chapter text, and assign each mention a \
canonical entity id.
- Reuse an id from the running list whenever the mention denotes a character \
already in that list, even under a different name, alias, title, or epithet \
-- resolving exactly that ambiguity is the task.
- Mint a new id ("e1", "e2", ... continuing from the highest existing number) \
when the mention denotes someone not yet in the list.
- Do NOT tag pronouns, generic role nouns ("the elder", "a guard"), \
locations, organizations, or items -- only specific individual people.
- Be exhaustive: if a character is named 30 times in a chapter, report all \
30 occurrences with their own context, not just the first.

For every mention report:
- "chapter": the chapter number (float, e.g. 4.0)
- "surface": the exact literal text of the mention, copied character-for-\
character from the source -- no paraphrasing
- "context": roughly 10-15 characters of source text immediately before AND \
after the mention, copied verbatim (needed to tell apart repeated identical \
surface forms in the same chapter)
- "entity_id": the id you assigned

Also return the complete, updated roster of every character identified so \
far (including ones from the running list, even if not mentioned in this \
section) as {id, name, aliases, description}. description is one sentence.
"""


@dataclass(slots=True)
class SectionResult:
    section: str
    chapters: tuple[int, int]
    entities: list[dict]
    mentions: list[dict]
    prompt_tokens: int
    output_tokens: int
    wall_seconds: float


def _build_prompt(store: Store, novel_id: str, lo: int, hi: int, roster: list[dict]) -> str:
    parts = [_INSTRUCTIONS]
    if roster:
        parts.append(
            "\nRUNNING CHARACTER LIST FROM EARLIER SECTIONS:\n"
            + json.dumps(roster, ensure_ascii=False)
        )
    else:
        parts.append("\nThis is the first section -- the running list is empty.")
    parts.append(f"\nCHAPTER TEXT, chapters {lo}-{hi}:\n")
    for n in range(lo, hi + 1):
        chapter = store.get_chapter(novel_id, float(n))
        if chapter is None:
            continue
        parts.append(f"\n=== Chapter {n} ===\n{chapter.story_text}")
    return "".join(parts)


def run_section(
    store: Store,
    novel_id: str,
    lo: int,
    hi: int,
    roster: list[dict],
    provider: OllamaProvider,
    num_ctx: int,
) -> SectionResult:
    prompt = _build_prompt(store, novel_id, lo, hi, roster)
    request = LLMRequest(
        stage="baseline_a",
        prompt=prompt,
        # Output shares the same num_ctx budget as the input in ollama, so
        # this is sized against a 10-chapter section's measured ~23k input
        # tokens (see module docstring), not set independently -- 4096 here
        # plus a growing roster still leaves headroom under the 32768 hard
        # ceiling for the later, roster-heavy sections.
        max_tokens=4096,
        temperature=0.0,
    )
    start = time.monotonic()
    result = provider.complete(request, SectionOut)
    wall = time.monotonic() - start
    log.info(
        "section ch%d-%d done in %.0fs: %d entities, %d mentions, "
        "prompt_tokens=%d output_tokens=%d",
        lo, hi, wall, len(result.value.entities), len(result.value.mentions),
        result.prompt_tokens, result.completion_tokens,
    )
    return SectionResult(
        section=f"ch{lo}-{hi}",
        chapters=(lo, hi),
        entities=[e.model_dump() for e in result.value.entities],
        mentions=[m.model_dump() for m in result.value.mentions],
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.completion_tokens,
        wall_seconds=wall,
    )


def _locate(story_text: str, surface: str, context: str, used: set[int]) -> int | None:
    """Find `surface`'s offset in `story_text`, disambiguating repeats via `context`.

    The model is never asked for a character offset -- it would fabricate one,
    the way any LLM asked to "count characters" does. It quotes the surface and
    a small verbatim window instead, and this reconstructs the offset the same
    way `coref_score._system_partition` matches the pipeline's own mentions:
    literal occurrence search, tie-broken by the best-matching local context,
    never reusing an offset already claimed by an earlier mention in the same
    chapter (repeated identical surfaces are repeated distinct occurrences).
    """
    lo_text = story_text.casefold()
    lo_surface = surface.casefold()
    candidates = []
    start = 0
    while True:
        idx = lo_text.find(lo_surface, start)
        if idx == -1:
            break
        candidates.append(idx)
        start = idx + 1
    if not candidates:
        return None
    unused = [c for c in candidates if c not in used] or candidates
    if not context:
        return unused[0]
    best, best_score = unused[0], -1.0
    for idx in unused:
        window = story_text[max(0, idx - 25) : idx + len(surface) + 25]
        score = difflib.SequenceMatcher(None, window.casefold(), context.casefold()).ratio()
        if score > best_score:
            best, best_score = idx, score
    return best


def _to_block_local(
    starts: dict[int, int], lengths: dict[int, int], abs_offset: int
) -> tuple[int, int]:
    for idx in sorted(starts):
        start = starts[idx]
        end = start + lengths.get(idx, 0)
        if start <= abs_offset < end:
            return idx, abs_offset - start
    # Past the last block's nominal end (join-separator rounding) -- clamp to
    # the last block rather than raise, since scoring should degrade to a
    # near-miss, not crash the whole run over one boundary mention.
    idx = max(starts) if starts else 0
    return idx, max(0, abs_offset - starts.get(idx, 0))


def materialize_mentions(store: Store, novel_id: str, sections: list[SectionResult]) -> int:
    """Insert the baseline's mention->entity assignments as real `Mention` rows.

    This is the point of going through `Store` at all instead of scoring in a
    one-off dict: `score_b3` is reused completely unmodified this way, rather
    than re-deriving B-cubed's precision/recall math for a baseline that isn't
    supposed to prove anything about the scorer, only about the resolution
    quality feeding it.
    """
    inserted = 0
    by_chapter: dict[float, list[dict]] = {}
    for section in sections:
        for m in section.mentions:
            by_chapter.setdefault(float(m["chapter"]), []).append(m)

    for chapter, mention_dicts in by_chapter.items():
        chapter_obj = store.get_chapter(novel_id, chapter)
        if chapter_obj is None:
            log.warning("baseline referenced chapter %.1f, not in store -- skipping", chapter)
            continue
        starts = _block_starts(store, novel_id, chapter)
        lengths = {
            b.index: len(b.text) for b in chapter_obj.blocks if b.block_type.is_story_content
        }
        story_text = chapter_obj.story_text
        used: set[int] = set()
        rows: list[Mention] = []
        unmatched = 0
        for i, m in enumerate(mention_dicts):
            offset = _locate(story_text, m["surface"], m.get("context", ""), used)
            if offset is None:
                unmatched += 1
                continue
            used.add(offset)
            block_index, local_offset = _to_block_local(starts, lengths, offset)
            rows.append(
                Mention(
                    id=f"baseline-{chapter:g}-{i}",
                    novel_id=novel_id,
                    segment_id="baseline_a",
                    chapter=chapter,
                    offset=local_offset,
                    text=m["surface"],
                    alias_type=AliasType.RIGID_NAME,
                    span_type=SpanType.NARRATION_ACTION,
                    reference_mode=ReferenceMode.PRESENT,
                    target_id=f"baseline_{m['entity_id']}",
                    provenance=Provenance.MACHINE,
                    block_index=block_index,
                )
            )
        store.add_mentions(rows)
        inserted += len(rows)
        if unmatched:
            log.warning(
                "ch%.1f: %d/%d baseline mentions could not be located in story_text "
                "(model quoted a surface that doesn't literally occur -- likely a "
                "paraphrase or a hallucinated mention)",
                chapter, unmatched, len(mention_dicts),
            )
    return inserted


def run_baseline(
    novel_id: str,
    section_bounds: list[tuple[int, int]],
    model: str,
    host: str,
    num_ctx: int,
    timeout: float,
    sources_path: str = "data/sources.toml",
) -> tuple[Store, list[SectionResult]]:
    store = Store(":memory:")
    lo_all, hi_all = section_bounds[0][0], section_bounds[-1][1]
    ingest_novel(
        novel_id, store, sources_path=sources_path, chapters=ChapterRange(lo_all, hi_all)
    )

    provider = OllamaProvider(model=model, host=host, timeout=timeout, num_ctx=num_ctx)
    if not provider.available():
        raise LLMUnavailable(
            f"ollama at {host} does not report model {model!r} pulled -- "
            "run `ollama pull` / `ollama serve` first"
        )

    roster: list[dict] = []
    sections: list[SectionResult] = []
    for lo, hi in section_bounds:
        # Sequential, single call at a time -- this machine runs other GPU/CPU
        # work concurrently, and a baseline run is not worth contending with
        # it for a comparison number that isn't time-critical.
        result = run_section(store, novel_id, lo, hi, roster, provider, num_ctx)
        sections.append(result)
        roster = result.entities

    materialize_mentions(store, novel_id, sections)
    return store, sections


def score(store: Store, novel_id: str, gold: GoldSet, max_chapter: int) -> None:
    sub = GoldSet(novel_id, [m for m in gold.mentions if m.chapter <= max_chapter])
    # Same two-tier report cli.py's `cmd_eval` uses for the real resolver
    # (draft vs. `GoldSet.confirmed_only`) -- this file is 100% confirmed as
    # of this writing, so the two happen to coincide, but printing both keeps
    # this baseline's output shape identical to the resolver's for an
    # apples-to-apples diff.
    for label, g in (
        ("draft (entities_only)", gold.entities_only),
        ("confirmed (entities_only)", gold.confirmed_only.entities_only),
    ):
        sub_g = GoldSet(novel_id, [m for m in g.mentions if m.chapter <= max_chapter])
        if not sub_g.mentions:
            continue
        r = score_b3(store, novel_id, sub_g)
        print(f"\n--- baseline A, ch1-{max_chapter}, {label} ---")
        print(r.summary())


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--novel", default="reverend-insanity")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--gold", default="data/gold/reverend-insanity.jsonl")
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=_MODEL_CTX_CEILING,
        help="capped at the model's real architecture ceiling regardless of value passed",
    )
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument(
        "--sections",
        default="1-10,11-20,21-30,31-40,41-50,51-60",
        help="comma-separated lo-hi chapter ranges, one ollama call each "
        "(10 chapters/section, not 30 -- see module docstring)",
    )
    args = parser.parse_args()

    num_ctx = min(args.num_ctx, _MODEL_CTX_CEILING)
    if args.num_ctx > _MODEL_CTX_CEILING:
        log.warning(
            "--num-ctx %d exceeds qwen2.5:7b's %d-token architecture ceiling; "
            "clamping (ollama would silently do the same)",
            args.num_ctx, _MODEL_CTX_CEILING,
        )

    bounds = []
    for part in args.sections.split(","):
        lo_s, hi_s = part.split("-")
        bounds.append((int(lo_s), int(hi_s)))

    store, sections = run_baseline(
        args.novel, bounds, args.model, args.host, num_ctx, args.timeout
    )

    total_prompt = sum(s.prompt_tokens for s in sections)
    total_output = sum(s.output_tokens for s in sections)
    total_wall = sum(s.wall_seconds for s in sections)
    print("\n=== Baseline A run summary (local ollama, zero-cost) ===")
    for s in sections:
        print(
            f"  {s.section}: {len(s.mentions)} mentions, {len(s.entities)} entities, "
            f"{s.prompt_tokens} prompt tok, {s.output_tokens} output tok, "
            f"{s.wall_seconds:.0f}s"
        )
    print(
        f"  TOTAL: prompt_tokens={total_prompt} output_tokens={total_output} "
        f"wall={total_wall:.0f}s num_ctx={num_ctx}"
    )

    gold = read_gold(args.gold, novel_id=args.novel)
    if not gold.mentions:
        print(f"no gold at {args.gold}", file=sys.stderr)
        return 1

    cumulative_hi = 0
    for lo, hi in bounds:
        cumulative_hi = hi
        score(store, args.novel, gold, cumulative_hi)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
