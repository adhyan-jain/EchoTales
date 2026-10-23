"""CLI dispatch — the layer that makes `echotales` a usable tool.

One entry point per verb, each returning a POSIX exit code. The `run` verb
executes the whole pipeline in order, because the phases have hard
dependencies: mentions need segments, attribution needs mentions, resolution
needs local groups. Running them out of order silently produces empty output
rather than failing, so the ordering lives here rather than in a README.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from echotales.core.enums import OBSERVER_READER, TargetKind
from echotales.core.models import StageStatus
from echotales.core.pipeline_run import (
    PartialStageFailure,
    digest_text,
    ensure_pipeline_run,
    source_digest_of,
)
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.pipeline.config import get_settings
from echotales.pipeline.version import PIPELINE_VERSION

log = logging.getLogger(__name__)


@dataclass(slots=True)
class StageTiming:
    name: str
    seconds: float
    detail: str = ""


@dataclass(slots=True)
class RunReport:
    novel_id: str
    stages: list[StageTiming] = field(default_factory=list)
    failed: str | None = None

    @property
    def total_seconds(self) -> float:
        return sum(s.seconds for s in self.stages)

    def render(self) -> str:
        lines = [f"\n=== pipeline run: {self.novel_id} ==="]
        for stage in self.stages:
            lines.append(f"  {stage.name:<24} {stage.seconds:7.1f}s   {stage.detail}")
        lines.append(f"  {'TOTAL':<24} {self.total_seconds:7.1f}s")
        if self.failed:
            lines.append(f"  FAILED at: {self.failed}")
        return "\n".join(lines)


def _open_store(args: argparse.Namespace) -> Store:
    return Store(getattr(args, "db", None) or get_settings().db_path)


def _build_client(store: Store, *, no_llm: bool = False, tasks=None):  # type: ignore[no-untyped-def]
    """Construct the run's `ModelClient`, or None for a deterministic run.

    Returns None rather than a stub client when the backend is `stub`, because
    stages branch on `client is None` to pick their deterministic path — a stub
    client would make them take the model path and get canned answers, which
    reads as a working LLM run in the report and is not one.
    """
    from echotales.pipeline.config import ModelBackend
    from echotales.pipeline.llm.client import ModelClient

    if no_llm:
        return None
    client = ModelClient(store=store)
    if client.backend is ModelBackend.STUB:
        print("note: ECHOTALES_MODEL_BACKEND=stub — running deterministic, no model calls.")
        return None
    client.require_ready(tasks)
    print(f"model backend: {client.backend.value}")
    return client


def _chapter_range(spec: str | None):  # type: ignore[no-untyped-def]
    from echotales.pipeline.ingest.adapters import ChapterRange

    return ChapterRange.parse(spec) if spec else None


# ---------------------------------------------------------------------------
# run — the whole pipeline
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    """Execute every phase in dependency order."""
    from echotales.pipeline.anaphora import resolve_anaphora_for_novel as anaphora_resolve
    from echotales.pipeline.ingest import get_source, ingest_novel
    from echotales.pipeline.mentions import detect_mentions, load_or_seed
    from echotales.pipeline.persona import build_personas
    from echotales.pipeline.resolve import resolve_novel as global_resolve
    from echotales.pipeline.segment import segment_novel
    from echotales.pipeline.speakers import attribute_novel

    novel = args.novel
    store = _open_store(args)
    chapters = _chapter_range(args.chapters)

    try:
        config = get_source(novel, args.sources)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    lexicon = load_or_seed(config.lexicon)
    report = RunReport(novel_id=novel)

    # One client for the whole run, threaded into every stage that can use a
    # model. Preflight here rather than per stage: discovering a missing model
    # on chapter 140 of a 199-chapter run wastes the run, and the failure mode
    # is a silent quality drop, not a crash.
    client = _build_client(store, no_llm=getattr(args, "no_llm", False))

    # Core Pipeline Hardening #5: `RunReport`/`StageTiming` above are
    # in-memory only and lost on crash -- this is the actual persisted
    # record. `source_digest` keys off the EPUB's real bytes (not the novel
    # id alone), so a re-run against unchanged source text can eventually be
    # recognised as such; per-stage `input_digest` here is deliberately
    # coarse (source_digest + stage name + this pipeline_version) rather than
    # a full per-stage data-dependency hash -- genuine per-chapter incremental
    # resume is explicitly out of scope for this phase (see the approved
    # plan's Resumability strategy section), so this only ever answers "did
    # this stage run at all against this exact source, this run" rather than
    # "did any upstream input actually change".
    source_digest = source_digest_of(config.path)
    pipeline_run = ensure_pipeline_run(
        store, novel_id=novel, source_digest=source_digest, pipeline_version=PIPELINE_VERSION
    )

    def stage(name: str, fn):  # type: ignore[no-untyped-def]
        """Timing/report wrapper around `jobs.run_stage` -- the one code
        path this and `jobs.py::run_job` both go through for StageRun
        bookkeeping, rather than each keeping its own copy."""
        from echotales.pipeline.jobs import run_stage

        started = time.perf_counter()
        input_digest = digest_text(f"{source_digest}|{name}|v{PIPELINE_VERSION}")
        try:
            # `skip_if_succeeded=False`: `echotales run` has always executed
            # every phase unconditionally (its coarse digest doesn't depend
            # on upstream output, only source+stage-name+version); the new
            # skip-on-matching-digest behaviour is for HTTP-triggered jobs
            # (`jobs.py::_dispatch`'s finer per-stage digests), not a change
            # to this command's existing behaviour.
            result = run_stage(
                store, run_id=pipeline_run.run_id, stage_name=name,
                input_digest=input_digest, fn=fn, skip_if_succeeded=False,
            )
        except PartialStageFailure as exc:
            report.failed = name
            print(report.render())
            print(f"\npartial failure in {name}: {exc}", file=sys.stderr)
            raise
        except Exception as exc:
            report.failed = name
            print(report.render())
            print(f"\nerror in {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            raise
        elapsed = time.perf_counter() - started
        detail = getattr(result, "summary", lambda: "")()
        first_line = detail.splitlines()[0] if detail else ""
        report.stages.append(StageTiming(name, elapsed, first_line))
        if args.verbose and detail:
            print(detail)
        return result

    try:
        stage("0 ingest", lambda: ingest_novel(novel, store, sources_path=args.sources, chapters=chapters))
        stage("2 segment", lambda: segment_novel(novel, store))
        stage("3 mentions", lambda: detect_mentions(novel, store, lexicon=lexicon, client=client))
        stage(
            "4 speakers",
            lambda: attribute_novel(
                novel,
                store,
                client=client,
                llm_chapter_cutoff=getattr(args, "llm_attribution_chapters", 0.0),
            ),
        )
        stage(
            "5 anaphora",
            lambda: anaphora_resolve(
                novel,
                store,
                recover_pronoun_speakers=getattr(args, "recover_pronoun_speakers", False),
            ),
        )
        from echotales.pipeline.corrections import CorrectionLog

        # Keyed by the *database's* stem, not just the novel id. Entity ids are
        # now a stable function of (novel_id, first alias surface, first
        # discourse position) rather than an in-process counter (Core Pipeline
        # Hardening #9.1, resolve/runner.py::_stable_entity_id) -- a rerun over
        # *identical* upstream input reproduces the same ids. A scratch --db run
        # over different or partial chapter data can still legitimately mint
        # different first-attested positions than the canonical
        # data/db/<novel>.db for the same character, so this
        # per-DB-stem keying stays as a safety measure: auto-flags referencing
        # those ids must never land in that novel's real corrections log. A
        # canonical run's db stem already equals the novel id, so this is a
        # no-op there.
        corrections_log = CorrectionLog(Path("data/corrections") / f"{Path(store.path).stem}.jsonl")
        stage(
            "6 resolve",
            lambda: global_resolve(
                novel,
                store,
                lexicon=lexicon,
                corrections_log=corrections_log,
                force_rewipe=getattr(args, "force_rewipe", False),
            ),
        )
        # 6b reader pass: a model shown the cast names every quoted line's speaker and reads appearance, ages and
        # new names, each with an evidence quote (decisions D11-D13). After resolve because it needs the cast;
        # before personas so a code name it links (Fool -> Klein) is an alias when personas are built.
        if client is not None and not getattr(args, "skip_reader", False):
            from echotales.pipeline.reader.runner import read_novel

            stage("6b reader", lambda: read_novel(novel, store, client))
        # Phase 7 runs last because it reads what every earlier phase produced:
        # resolved entities, their attributed dialogue, and the NER-derived kind
        # that says which of them are people at all.
        stage("7 personas", lambda: build_personas(novel, store, client=client, prefix_causal=get_settings().persona_prefix_causal))
        # 7b reads the personas 7 just minted and needs a model: appearance is
        # never stated by an honorific the way age is, so there is no
        # deterministic path to fall back to (see appearance_extract's docstring).
        if client is not None and not getattr(args, "skip_appearance", False):
            from echotales.pipeline.resolve.appearance_extract import extract_appearance

            stage("7b appearance", lambda: extract_appearance(novel, store, client=client))
    except Exception:
        store.update_pipeline_run_status(pipeline_run.run_id, StageStatus.FAILED)
        store.close()
        raise

    store.update_pipeline_run_status(pipeline_run.run_id, StageStatus.SUCCEEDED)
    print(report.render())
    print(f"\ngraph written to: {store.path}")
    print(f"review it with:   uv run echotales review --novel {novel}")
    store.close()
    return 0


# ---------------------------------------------------------------------------
# review — human inspection
# ---------------------------------------------------------------------------


def cmd_review(args: argparse.Namespace) -> int:
    """Produce human-readable review artifacts."""
    from echotales.pipeline.review import build_review, write_html, write_jsonl

    store = _open_store(args)
    if store.chapter_count(args.novel) == 0:
        print(
            f"error: no chapters for {args.novel!r} in {store.path}.\n"
            f"Run first:  uv run echotales run --novel {args.novel}",
            file=sys.stderr,
        )
        return 2

    script_chapters = None
    if getattr(args, "script", None):
        script_range = _chapter_range(args.script)
        if script_range is not None:
            script_chapters = [
                c.number for c in store.iter_chapters(args.novel) if c.number in script_range
            ]

    review = build_review(
        store, args.novel, top_n=args.top, samples=args.samples, script_chapters=script_chapters
    )
    print(review.render_console(limit=args.top))

    out_dir = Path(args.out)
    if not args.no_files:
        html_path = write_html(review, out_dir / f"{args.novel}-review.html")
        jsonl_path = write_jsonl(review, out_dir / f"{args.novel}-entities.jsonl")
        print(f"\nHTML report : {html_path}")
        print(f"JSONL export: {jsonl_path}")
        print("\nOpen the HTML in a browser to review entities with their evidence.")
    store.close()
    return 0


# ---------------------------------------------------------------------------
# query — state_of
# ---------------------------------------------------------------------------


def cmd_query(args: argparse.Namespace) -> int:
    if args.query_command == "attributes":
        return _query_attributes(args)
    if args.query_command != "state-of":
        print(f"unknown query: {args.query_command}", file=sys.stderr)
        return 2

    store = _open_store(args)
    resolver = StateResolver(store, args.novel)

    target = args.target
    # Accept a human-readable label as well as an id, since ids are generated.
    if not store.get_self(target):
        matches = [
            e
            for e in store.all_selves(args.novel)
            if e.canonical_label.casefold() == target.casefold()
        ]
        if matches:
            target = matches[0].id
        else:
            print(f"error: no entity {args.target!r} in {args.novel}", file=sys.stderr)
            print("       list them with: uv run echotales review", file=sys.stderr)
            return 2

    result = resolver.state_of(
        target,
        target_kind=TargetKind(args.kind),
        timeline_id=args.timeline,
        position=args.chapter,
        observer_id=args.observer,
    )
    print(json.dumps(result.model_dump(), indent=2, default=str))
    store.close()
    return 0


# ---------------------------------------------------------------------------
# export / eval
# ---------------------------------------------------------------------------


def cmd_export(args: argparse.Namespace) -> int:
    from echotales.pipeline.review import build_review, write_jsonl

    store = _open_store(args)
    review = build_review(store, args.novel, top_n=10**6, samples=args.samples)
    path = write_jsonl(review, Path(args.out) / f"{args.novel}-entities.jsonl")
    print(f"exported {len(review.entities):,} entities to {path}")
    store.close()
    return 0



if TYPE_CHECKING:  # `GoldSet` is imported lazily inside cmd_eval at runtime
    from echotales.pipeline.eval.gold import GoldSet


def _recall_at_k_report(
    store: Store, novel_id: str, tier_gold: GoldSet, args: object, *, tier: str
) -> dict[str, object]:
    """Retriever recall@k for one gold tier, broken down by alias type.

    Factored out of `cmd_eval` when the SILVER tier arrived, because the block
    it replaces sat inside `if confirmed.mentions:` and confirmed gold has been
    empty corpus-wide since EVOLUTION 4.74 -- so the only recall number this
    tool ever printed was the self-retrieval smoke test, which hardcodes
    RIGID_NAME and cannot exercise the TRANSFERABLE_TITLE gate at all.

    The retriever is rebuilt here from resolved mentions rather than reused
    from resolution, and it is given each mention's real surrounding text.
    Passing `""` as context -- as this code did until 2026-09-24 -- silently
    zeroes the 0.35 contextual half of `CandidateRetriever.retrieve`'s blend,
    so the reported number described a lexical-only retriever that no
    production path uses.
    """
    from echotales.pipeline.eval.retriever_eval import (
        DEFAULT_KS,
        EvalMode,
        build_gold_retrieval_cases,
        evaluate_recall,
        miss_report,
    )
    from echotales.pipeline.resolve.retrieve import CandidateRetriever

    # Context must be built exactly as production builds it, or the number
    # describes a retriever no path uses. Production (`resolve/runner.py`)
    # calls `_context_for(mention, chapter.story_text)` -- a fixed window
    # around the surface in the whole chapter. An earlier fix here passed the
    # mention's block text instead: better than the empty string it replaced,
    # but still not what resolution sees. Reusing the function is the only way
    # the two cannot drift again.
    from echotales.pipeline.resolve.runner import _context_for

    chapter_text: dict[float, str] = {}

    def _production_context(mention: object) -> str:
        chapter = mention.chapter  # type: ignore[attr-defined]
        if chapter not in chapter_text:
            chapter_obj = store.get_chapter(novel_id, chapter)
            chapter_text[chapter] = chapter_obj.story_text if chapter_obj else ""
        return _context_for(mention, chapter_text[chapter])  # type: ignore[arg-type]

    retriever = CandidateRetriever()
    for mention in store.get_mentions(novel_id, resolved_only=True):
        if not mention.target_id:
            continue
        retriever.observe(
            mention.target_id,
            mention.text,
            _production_context(mention),
            mention.chapter,
            label=mention.text,
        )
    cases, unmapped = build_gold_retrieval_cases(tier_gold, store, novel_id)
    print(
        f"\n  -- {tier} retriever recall@k "
        f"({len(cases):,} cases, {unmapped} identities unmapped) --"
    )
    if not cases:
        print("  no gold mention mapped to a system target_id -- recall@k untested.")
        return {"cases": 0, "unmapped": unmapped}
    result = evaluate_recall(retriever, cases, mode=EvalMode.GOLD)
    print("  " + result.summary().replace("\n", "\n  "))
    if getattr(args, "report", False):
        print("  " + miss_report(result).replace("\n", "\n  "))
    return {
        "cases": len(cases),
        "unmapped": unmapped,
        "overall": {str(k): result.recall_at(k) for k in DEFAULT_KS},
        "by_alias_type": {
            alias: {str(k): result.recall_at_by_type(alias, k) for k in DEFAULT_KS}
            for alias in sorted(result.by_alias_type_total)
        },
        "by_alias_type_n": dict(result.by_alias_type_total),
    }


def cmd_eval(args: argparse.Namespace) -> int:
    from echotales.pipeline.eval import (
        EvalMode,
        build_gold_retrieval_cases,
        build_self_retrieval_cases,
        evaluate_recall,
        miss_report,
    )
    from echotales.pipeline.eval.coref_score import score_all, score_b3
    from echotales.pipeline.eval.gold import SILVER_BANNER, read_gold
    from echotales.pipeline.resolve.retrieve import CandidateRetriever

    store = _open_store(args)
    retriever = CandidateRetriever()
    for mention in store.get_mentions(args.novel, resolved_only=True):
        if mention.target_id:
            retriever.observe(
                mention.target_id, mention.text, "", mention.chapter, label=mention.text
            )

    # Escalation rate, printed first because it describes the run being
    # scored rather than the scoring. Non-negotiable #7 calls this "a reported
    # metric, not a failure mode" and `docs/design/architecture.md` Section 7 calls it a
    # claimed contribution; until 2026-09-23 nothing called the function that
    # computed it (EVOLUTION 4.79).
    escalation = store.escalation_summary()
    print("=== LLM escalation (from the persisted llm_call table) ===")
    if not escalation["calls"]:
        print(
            "  no LLM calls recorded for this database -- a deterministic or "
            "stub-mode run, or a database whose calls predate llm_call logging."
        )
    else:
        print(
            f"  calls={escalation['calls']:,}  escalations={escalation['escalations']:,}"
            f"  rate={escalation['escalation_rate']:.1%}"
            f"  tokens={escalation['tokens']:,}"
            f"  avg latency={escalation['avg_latency_ms']:,.0f}ms"
        )
        for row in escalation["by_stage"]:
            calls = row.get("calls") or 0
            esc = row.get("escalations") or 0
            print(
                f"    {row.get('stage', '?'):<22} tier={row.get('tier', '?'):<10}"
                f" calls={calls:>6,} escalated={esc:>5,}"
                f" ({(esc / calls if calls else 0):.1%})"
            )

    metrics: dict[str, object] = {"escalation": escalation}

    cases = build_self_retrieval_cases(retriever)
    result = evaluate_recall(retriever, cases, mode=EvalMode.SELF_RETRIEVAL)
    print(result.summary())
    print(
        "\nNote: this is the self-retrieval smoke test, not a recall@k result. "
        "See the gold comparison below for that."
    )

    # Gold comparison: automatic whenever data/gold/<novel>.jsonl exists, so
    # every eval run against an annotated novel is a regression check against
    # the same fixed reference, not a one-off number. Reported in two tiers --
    # draft (provenance=model, includes every record) and confirmed-only
    # (`GoldSet.confirmed_only`) -- because a number computed from unconfirmed
    # drafts is not a "result" per gold.py's own contract, and silently
    # blending the two would make that distinction invisible in the printout.
    gold_path = Path(getattr(args, "gold", None) or f"data/gold/{args.novel}.jsonl")
    gold = read_gold(gold_path, novel_id=args.novel)

    # Structural validation before scoring, not after: a file with colliding
    # keys or spans that do not sit at their offsets produces a number that
    # looks fine and means nothing, and that number is what gets quoted.
    if getattr(args, "validate_gold", False):
        from echotales.pipeline.eval.validate_gold import validate_gold, write_report

        report = validate_gold(gold, str(gold_path), store)
        print("\n" + report.summary())
        out = write_report(report, Path("data/eval/validation") / f"{gold_path.stem}.json")
        print(f"\nvalidation report: {out}")
        store.close()
        return 0 if report.ok else 1

    print(f"\n=== gold comparison: {gold_path} ===")
    if not gold.mentions:
        print(f"  no gold file at {gold_path} -- skipping. See `echotales export`/eval/draft.py.")
    else:
        print(f"  {gold.coverage()}")
        draft_score = score_b3(store, args.novel, gold.entities_only)
        print("\n  -- all drafted annotations (not a result, see confirmed-only below) --")
        print("  " + draft_score.summary().replace("\n", "\n  "))
        # Standard metrics alongside the project's own B-cubed variant. They
        # answer the same question under the textbook definitions (an unlinked
        # mention is a singleton, not a penalty), which is the only form
        # comparable to BookNLP/LitBank/LINK-KG numbers. Printed together so
        # nobody has to guess which convention a reported figure used.
        print("\n  -- standard metrics, same mentions, textbook definitions --")
        for metric in score_all(store, args.novel, gold.entities_only):
            print("  " + metric.summary())
        # Recall@1 with a 95% bootstrap interval, so a difference between two
        # runs can be read as a difference rather than as noise. Computed over
        # the same mentions `score_all` used.
        from echotales.pipeline.eval.coref_score import _system_partition
        from echotales.pipeline.eval.stats import bootstrap_ci, rate

        # `_system_partition`, not a fresh lookup: a gold offset is
        # chapter-absolute and `mention.offset` is block-local, so keying on
        # the raw pair silently matches almost nothing. Writing that lookup a
        # third time is how `score_b3`'s documented "silently matches nothing
        # past the chapter's first block" bug happened; there is one
        # translation and this uses it.
        entities_only = gold.entities_only
        partition = _system_partition(store, args.novel, entities_only)
        linked = [bool(partition.get(m.key)) for m in entities_only.mentions]
        if linked:
            interval = bootstrap_ci(
                linked, rate, seed=getattr(args, "global_seed", 20260923)
            )
            print(
                f"\n  gold mentions the system linked at all: "
                f"{interval.summary()} (n={len(linked):,}, "
                f"{interval.resamples:,} resamples)"
            )
            metrics["linked_share"] = {
                "point": interval.point,
                "ci_low": interval.low,
                "ci_high": interval.high,
                "n": len(linked),
                "resamples": interval.resamples,
            }

        # Held-out conformal coverage: the (1-alpha) guarantee validated on a
        # LATER chapter range than it was calibrated on. `calibrate_from_gold`
        # fits and reports on the same samples, which is a fit statistic.
        from echotales.pipeline.eval.calibrate import held_out_coverage

        coverage = held_out_coverage(args.novel, store, gold.confirmed_only.entities_only)
        print("\n  -- held-out conformal coverage --")
        print("  " + coverage.summary().replace("\n", "\n  "))
        metrics["held_out_coverage"] = {
            "split_chapter": coverage.split_chapter,
            "calibration_size": coverage.calibration_size,
            "test_size": coverage.test_size,
            "empirical": coverage.empirical_coverage,
            "target": coverage.target_coverage,
            "false_links": coverage.false_links,
        }

        # SILVER tier. The honest middle ground between the draft tier (which
        # includes records the pipeline drafted from its own output, so it
        # cannot score that pipeline) and the confirmed tier (empty, and
        # staying empty until a person adjudicates record by record). These
        # were drafted by a different model family than the one under test,
        # reading chapter text rather than the `mention` table.
        #
        # This is the tier every number in docs/ is computed from as of
        # 2026-09-24, and the banner travels with the number precisely because
        # the retracted B-cubed result (EVOLUTION 4.74) was quoted for six
        # weeks by people reading a printout rather than the provenance note
        # beside it.
        silver = gold.silver_only.entities_only
        if silver.mentions:
            print(f"\n  -- SILVER tier ({len(silver.mentions):,} records) --")
            print(f"  {SILVER_BANNER}")
            silver_score = score_b3(store, args.novel, silver)
            print("  " + silver_score.summary().replace("\n", "\n  "))
            silver_metrics: dict[str, object] = {
                "banner": SILVER_BANNER,
                "records": len(silver.mentions),
                "b3_project_variant": {
                    "precision": silver_score.precision,
                    "recall": silver_score.recall,
                    "f1": silver_score.f1,
                },
            }
            for metric in score_all(store, args.novel, silver):
                print("  " + metric.summary())
                silver_metrics[metric.name.lower().replace("-", "_")] = {
                    "precision": metric.precision,
                    "recall": metric.recall,
                    "f1": metric.f1,
                }
            silver_metrics["recall_at_k"] = _recall_at_k_report(
                store, args.novel, silver, args, tier="SILVER"
            )
            metrics["silver"] = silver_metrics
        else:
            print("\n  -- SILVER tier: 0 records (every record here is circular) --")

        confirmed = gold.confirmed_only.entities_only
        if confirmed.mentions:
            confirmed_score = score_b3(store, args.novel, confirmed)
            print("\n  -- confirmed only (this is the reportable result) --")
            print("  " + confirmed_score.summary().replace("\n", "\n  "))
            for metric in score_all(store, args.novel, confirmed):
                print("  " + metric.summary())
            if args.report:
                print(confirmed_score.worst_report())

            # Real retriever recall@k (HANDOFF defect #4): confirmed gold
            # identities mapped to system target_ids, so the retriever gate
            # (recall@10 on TRANSFERABLE_TITLE) is measured against something
            # other than the self-retrieval smoke test above.
            from echotales.pipeline.resolve.retrieve import CandidateRetriever

            gold_retriever = CandidateRetriever()
            for mention in store.get_mentions(args.novel, resolved_only=True):
                if mention.target_id:
                    gold_retriever.observe(
                        mention.target_id, mention.text, "", mention.chapter,
                        label=mention.text,
                    )
            gold_cases, unmapped = build_gold_retrieval_cases(confirmed, store, args.novel)
            print(f"\n=== gold recall@k ({len(gold_cases):,} cases, {unmapped} identities unmapped) ===")
            if gold_cases:
                gold_result = evaluate_recall(gold_retriever, gold_cases, mode=EvalMode.GOLD)
                print("  " + gold_result.summary().replace("\n", "\n  "))
                if args.report:
                    print("  " + miss_report(gold_result).replace("\n", "\n  "))
            else:
                print("  no gold mention mapped to a system target_id -- recall@k untested.")
        else:
            print(
                "\n  0 confirmed records -- nothing here is a reportable result yet."
            )
        if args.report:
            print(draft_score.worst_report())

    # Persist so a reported number traces back to a database, a gold file, a
    # seed and a commit -- `pipeline_run.py` has had this machinery with zero
    # callers outside `cmd_run` since it was written.
    from echotales.pipeline.eval.persist import persist_eval

    try:
        out_dir = persist_eval(
            store,
            args.novel,
            metrics=metrics,
            gold_path=str(gold_path),
            seed=getattr(args, "global_seed", 20260923),
        )
        print(f"\nresults persisted: {out_dir}")
    except (OSError, ValueError) as exc:
        print(f"\nwarning: could not persist results: {exc}", file=sys.stderr)

    store.close()
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from echotales.pipeline.ingest import ingest_novel

    store = _open_store(args)
    # `--sources` was parsed but never passed on, so a book outside data/sources.toml could not be ingested.
    report = ingest_novel(args.novel, store, sources_path=args.sources, chapters=_chapter_range(args.chapters))
    print(report.summary())
    store.close()
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    from echotales.pipeline.ingest import get_source
    from echotales.pipeline.mentions import load_or_seed
    from echotales.pipeline.resolve import resolve_novel

    store = _open_store(args)
    if getattr(args, "title_holders_only", False):
        from echotales.pipeline.resolve.title_holders import link_title_holders

        report = link_title_holders(store, args.novel)
        print(report.summary())
        store.conn.commit()
        store.close()
        return 0
    if getattr(args, "kinds_only", False):
        from pathlib import Path

        from echotales.pipeline.config import get_settings
        from echotales.pipeline.resolve.kind_backfill import backfill_kinds

        cfg = get_settings()
        cache_path = Path(cfg.lexicon_path) / f"{args.novel}-ner-cache.json"
        stats = backfill_kinds(store, args.novel, cache_path)
        from echotales.pipeline.resolve.class_nouns import type_class_nouns

        categories = type_class_nouns(store, args.novel)
        print(f"class nouns: {', '.join(categories) or 'none'}")
        print(
            f"kind backfill: checked={stats['checked']} "
            f"classified={stats['classified']} left_default={stats['left_default']}"
        )
        store.conn.commit()
        store.close()
        return 0
    lexicon = load_or_seed(get_source(args.novel).lexicon)
    print(
        resolve_novel(
            args.novel,
            store,
            lexicon=lexicon,
            strict_kind_check=getattr(args, "strict_kind_check", False),
            force_rewipe=getattr(args, "force_rewipe", False),
            capture_evidence=getattr(args, "capture_evidence", False),
            evidence_run_tag=getattr(args, "evidence_run_tag", ""),
            # B2: `--chapters` was accepted and ignored; it now selects the chapters to resolve.
            chapters=_chapter_range(getattr(args, "chapters", None)),
        ).summary()
    )
    store.close()
    return 0


def cmd_annotate(args: argparse.Namespace) -> int:
    from echotales.pipeline.eval.blind_review import (
        build_tasks,
        read_answers,
        write_tasks,
    )
    from echotales.pipeline.eval.gold import write_gold

    store = _open_store(args)
    try:
        if args.emit:
            tasks = build_tasks(
                store,
                args.novel,
                chapters=_chapter_range(args.chapters),
                sample=args.sample,
                seed=args.seed,
            )
            path = write_tasks(tasks, args.tasks)
            print(f"{len(tasks):,} blind tasks written to {path}")
            print(
                "Fill in `identity` (your own name for the referent) or set "
                "`not_an_entity` to true.\nLeave a task blank to skip it -- a "
                "blank is 'nobody looked', never agreement."
            )
            return 0

        if not args.confirmed_by:
            print(
                "error: --confirmed-by is required when reading answers back. A "
                "confirmation that names nobody is how 6,952 machine-drafted "
                "records became 'human' provenance (EVOLUTION 4.74).",
                file=sys.stderr,
            )
            return 2
        gold = read_answers(
            args.tasks, novel_id=args.novel, confirmed_by=args.confirmed_by, store=store
        )
        out = Path(args.out or f"data/gold/{args.novel}-blind.jsonl")
        write_gold(gold, out)
        print(f"{len(gold.mentions):,} confirmed records written to {out}")
        print(f"  {gold.coverage()}")
        return 0
    finally:
        store.close()


def cmd_observations(args: argparse.Namespace) -> int:
    from echotales.pipeline.resolve.detect_observations import detect_observations

    store = _open_store(args)
    report = detect_observations(
        store, args.novel, include_revealed_self=args.include_revealed_self
    )
    print(report.summary())
    if not report.observations_written and not store.count_observations():
        # Said plainly: an empty observer axis makes every character-observer
        # query return nothing, which looks identical to "this character knows
        # nothing" and is the state every shipped database was in before
        # EVOLUTION 4.80.
        print(
            "\nno observations recorded -- every `--observer <character>` query will\n"
            "return an empty result, which is not the same claim as 'they know less'."
        )
    store.close()
    return 0


def cmd_ablate(args: argparse.Namespace) -> int:
    from echotales.pipeline.eval.ablate import REQUIRES_RERESOLVE, run_ablations

    store = _open_store(args)
    tag = getattr(args, "run_tag", "")
    captured = store.count_scoring_evidence(args.novel, tag)
    if not captured:
        print(
            f"no cached evidence for {args.novel!r} (run tag {tag!r}).\n"
            "Capture it first:\n"
            f"  echotales --db <db> resolve --novel {args.novel} --capture-evidence",
            file=sys.stderr,
        )
        store.close()
        return 2

    print(f"=== ablations: {args.novel} ({captured:,} cached evidence vectors) ===")
    rows = run_ablations(
        store,
        args.novel,
        run_tag=tag,
        conditions=getattr(args, "condition", None),
        link_threshold=getattr(args, "link_threshold", 0.8),
    )
    for row in rows:
        print(row.summary())

    out = getattr(args, "out", None)
    if out:
        import dataclasses
        import json
        from pathlib import Path

        payload = {
            "novel_id": args.novel,
            "db": getattr(args, "db", None) or get_settings().db_path,
            "run_tag": tag,
            "cached_evidence_vectors": captured,
            "link_threshold": getattr(args, "link_threshold", 0.8),
            "rows": [dataclasses.asdict(r) for r in rows],
            "requires_reresolve": dict(REQUIRES_RERESOLVE),
        }
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\nablation rows written: {out}")

    # Printed every run, not buried in a docstring: a reader comparing
    # conditions needs to know which ones are missing and why, or the absence
    # reads as "this axis did not matter".
    print("\nNot answerable from the cache (would need a real re-resolve):")
    for name, why in REQUIRES_RERESOLVE.items():
        print(f"  {name}: {why}")
    store.close()
    return 0


def cmd_webview(args: argparse.Namespace) -> int:
    from echotales.pipeline.webview import NovelSource, write_webview, write_webview_json

    sources: list[NovelSource] = []
    for raw in args.source:
        parts = raw.split(":", 2)
        if len(parts) < 2:
            print(f"error: --source must be DB_PATH:NOVEL_ID[:LABEL], got {raw!r}", file=sys.stderr)
            return 2
        db_path, novel_id = parts[0], parts[1]
        label = parts[2] if len(parts) > 2 else ""
        if not Path(db_path).exists():
            print(f"error: no database at {db_path!r}", file=sys.stderr)
            return 2
        sources.append(NovelSource(db_path=db_path, novel_id=novel_id, label=label))

    if args.format == "react":
        path = write_webview_json(sources, args.out)
        print(f"data written: {path}")
        print("start the React app with: cd webview && npm start")
        return 0

    path = write_webview(sources, args.out)
    print(f"viewer written: {path}")
    print(f"open it directly in a browser (file://{path.resolve()}), no server needed")
    return 0


def cmd_webview_server(args: argparse.Namespace) -> int:
    from echotales.pipeline.webview import NovelSource
    from echotales.pipeline.webview_server import serve

    sources: list[NovelSource] = []
    for raw in args.source:
        parts = raw.split(":", 2)
        if len(parts) < 2:
            print(f"error: --source must be DB_PATH:NOVEL_ID[:LABEL], got {raw!r}", file=sys.stderr)
            return 2
        db_path, novel_id = parts[0], parts[1]
        label = parts[2] if len(parts) > 2 else ""
        if not Path(db_path).exists():
            print(f"error: no database at {db_path!r}", file=sys.stderr)
            return 2
        sources.append(NovelSource(db_path=db_path, novel_id=novel_id, label=label))

    static_dir = Path(args.static_dir) if getattr(args, "static_dir", None) else None
    if static_dir is not None and not (static_dir / "index.html").is_file():
        print(f"error: no index.html in --static-dir {str(static_dir)!r} (run `npm run build` first)", file=sys.stderr)
        return 2
    serve(
        sources,
        host=args.host,
        port=args.port,
        static_dir=static_dir,
        corrections_dir=Path(getattr(args, "corrections_dir", "data/corrections")),
    )
    return 0


def cmd_voice(args: argparse.Namespace) -> int:
    """Phase 8: cast voices and render the script."""
    from echotales.pipeline.voice import get_engine, load_vctk, render_novel
    from echotales.pipeline.voice.bank import load_cremad, load_ears

    store = _open_store(args)
    kind = getattr(args, "bank_kind", "vctk")
    try:
        if kind == "cremad":
            bank = load_cremad(args.bank)
        elif kind == "ears":
            bank = load_ears(args.bank)
        else:
            bank = load_vctk(args.bank)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "the voice bank is CSTR VCTK 0.92; download and extract it under "
            f"{args.bank!r} (see HANDOFF Section 7)",
            file=sys.stderr,
        )
        return 2

    print(bank.bucket_report())
    if not bank.voices:
        print("error: voice bank is empty", file=sys.stderr)
        return 2

    # Filter the novel's real chapter numbers rather than generating a range:
    # `ChapterRange` is float-valued so split chapters (45.1) fall inside it
    # naturally, and enumerating integers would silently drop them.
    wanted = None
    if selected := _chapter_range(args.chapters):
        wanted = [n for n in store.chapter_numbers(args.novel) if n in selected]

    engine_name = args.engine
    if not get_settings().enable_tts and engine_name != "stub":
        print(
            f"note: ECHOTALES_ENABLE_TTS=false overrides --engine {engine_name!r} -> stub "
            "(iterating on image generation only; flip the flag back on when done)"
        )
        engine_name = "stub"

    report = render_novel(
        args.novel,
        store,
        bank,
        out_dir=args.out,
        engine=get_engine(engine_name),
        chapters=wanted,
        seed=args.seed,
        synthesize=not args.dry_run,
        min_character_confidence=getattr(args, "min_character_confidence", 0.7),
    )
    print(report.summary())
    print(f"\nmanifest: {Path(args.out) / 'manifest.jsonl'}")
    store.close()
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """Phase 9: panel images, the motion-clip library, and per-chapter video.

    Three sub-stages run in dependency order, each individually skippable
    (`--skip-panels`/`--skip-motion`/`--skip-compose`) since they are
    independently expensive and a rerun should not have to redo all three
    just to pick up a change in one -- mirrors `render_panels`'s own
    on-disk caching for the same reason.
    """
    from echotales.pipeline.render import (
        build_motion_library,
        get_compose_engine,
        get_motion_engine,
        get_panel_engine,
        render_panels,
        render_videos,
    )

    store = _open_store(args)
    wanted = None
    if selected := _chapter_range(args.chapters):
        wanted = [n for n in store.chapter_numbers(args.novel) if n in selected]

    from echotales.pipeline.compute import policy as _compute_policy
    from echotales.pipeline.compute import resource_refusal as _resource_refusal

    pol = _compute_policy()
    # No `--image-engine`: the stub for the local provider (a bare render never loads a model, as before), the
    # configured provider's engine when a hosted one was chosen in `.env` -- that choice is the opt-in.
    image_engine_name = args.image_engine or ("stub" if pol.image_provider in ("local", "stub") else pol.image_provider)
    max_panels = args.max_panels if args.max_panels is not None else pol.scenes_for(getattr(args, "tier", None))
    print(f"compute: {pol.mode}; images: {image_engine_name}; language: {pol.llm_provider}; scenes per chapter: {max_panels}")
    if not get_settings().enable_image_gen and image_engine_name != "stub":
        print(
            f"note: ECHOTALES_ENABLE_IMAGE_GEN=false overrides --image-engine "
            f"{image_engine_name!r} -> stub (iterating on voice/TTS only; flip "
            "the flag back on when done)"
        )
        image_engine_name = "stub"

    if not getattr(args, "ignore_resource_guard", False):
        refusal = _resource_refusal(image_engine_name, pol)
        if refusal:
            print(f"refusing to render: {refusal}\n(--ignore-resource-guard overrides this)", file=sys.stderr)
            store.close()
            return 2

    block_range = None
    if args.block_range:
        lo_s, _, hi_s = args.block_range.partition("-")
        try:
            block_range = (int(lo_s), int(hi_s))
        except ValueError:
            print(f"error: --block-range must be LO-HI, got {args.block_range!r}", file=sys.stderr)
            store.close()
            return 2

    # **Every render gets its own version directory.** Writing into the root
    # of `panels/` meant a run silently overwrote the previous one -- the
    # exact failure that destroyed the reference video an earlier review was
    # written against. `next_version` continues from the highest existing vN,
    # so deleting an old version never causes a new run to land on a
    # survivor. `--panel-dir` still wins if given explicitly.
    from echotales.pipeline.paths import next_version

    _version = None
    if not getattr(args, "no_versioned_output", False):
        _tag = f"ch{wanted[0]:g}" if wanted else "all"
        _version = next_version(Path(args.panel_dir) / _tag)
        _suffix = re.sub(r"[^A-Za-z0-9-]+", "-", getattr(args, "version_suffix", "") or "").strip("-")
        if _suffix:
            _version = f"{_version}_{_suffix}"
        args.out = str(Path(args.out) / _tag / _version)
        args.motion_dir = str(Path(args.motion_dir) / _tag / _version)
        print(f"output version: {_version}")

    if not args.skip_panels:
        image_engine = (
            get_panel_engine(image_engine_name, palette=args.palette, accent_hue=args.accent_hue)
            if image_engine_name == "manga"
            else get_panel_engine(image_engine_name)
        )
        from echotales.pipeline.llm.tasks import Task as _Task

        # Only the panel director runs here; checking every task's model refused a render over llama3:latest.
        director_client = _build_client(store, tasks={_Task.PANEL_DIRECTION}) if not args.no_director else None
        # `local-low` always runs the director to completion and unloads it before the image model loads, whatever
        # render.direction_first says: two models resident at once is what ran this machine out of memory.
        two_phase = director_client is not None and (get_settings().render_direction_first or pol.force_sequential)

        if two_phase:
            # Direction and image generation split into two passes so an
            # LLM backend that needs the local GPU (ollama) never has to
            # share it with the local diffusion engine in the same process
            # -- see render_panels's own docstring on prompt_cache_path and
            # docs/EVOLUTION.md section 9 for the measured OOM this avoids.
            # Phase 1 uses a stub image engine deliberately: no GPU cost,
            # every beat's director call still runs and gets cached.
            #
            # **Phase 1 writes to a separate scratch directory, not
            # args.panel_dir.** A real, caught bug: StubImageEngine writes
            # a real (placeholder) PNG to request.out_path, and
            # render_panels's own cross-run cache checks `image_path.
            # exists()` -- so a phase 1 run against the *same* directory
            # phase 2 uses left every image path already "existing" by the
            # time phase 2 ran, and phase 2 silently skipped real SDXL
            # generation for all 39 panels, reporting them "reused from
            # cache" when every one was actually the stub's blank
            # placeholder. Only prompt_cache_path needs to persist between
            # the two phases; the image files themselves must not.
            import tempfile

            direction_scratch = tempfile.mkdtemp(prefix="echotales-direction-")
            # Shared between the two phases of *this* version only.
            # Inside the version it belongs to: at the panels/ root these piled
            # up as prompt_cache_v10..v51.json beside the chapter folders.
            cache_path = (
                Path(args.panel_dir) / _tag / _version / "prompt_cache.json"
                if _version else Path(args.panel_dir) / "prompt_cache.json"
            )
            print(f"phase 1/2: directing panels via {director_client.backend.value} ...")
            direction_report = render_panels(
                args.novel,
                store,
                out_dir=direction_scratch,
                engine=get_panel_engine("stub"),
                # **The real engine's `quality_prefix` budget, not the stub's.**
                # This phase writes the prompt every later phase-2 panel uses
                # verbatim -- reserving against the stub (which has none)
                # would size every prompt to the full 75 tokens and let
                # phase 2's real prefix silently truncate it anyway. See
                # `render_panels`'s `target_engine` docstring.
                target_engine=image_engine,
                chapters=wanted,
                seed=args.seed,
                width=args.width,
                height=args.height,
                client=director_client,
                max_panels=max_panels,
                block_range=block_range,
                prompt_cache_path=cache_path,
                version=_version,
                observer_id=getattr(args, "observer", OBSERVER_READER),
            )
            print(direction_report.summary())

            from echotales.pipeline.config import ModelBackend as _ModelBackend

            if director_client.backend is _ModelBackend.OLLAMA:
                unload_ollama_models(prefix="phase 1/2: ")

            print(f"phase 2/2: generating images ({image_engine_name}) ...")
            report = render_panels(
                args.novel,
                store,
                out_dir=args.panel_dir,
                engine=image_engine,
                chapters=wanted,
                seed=args.seed,
                width=args.width,
                height=args.height,
                client=None,
                max_panels=max_panels,
                block_range=block_range,
                prompt_cache_path=cache_path,
                version=_version,
                observer_id=getattr(args, "observer", OBSERVER_READER),
            )
            import shutil as _shutil

            _shutil.rmtree(direction_scratch, ignore_errors=True)
        else:
            report = render_panels(
                args.novel,
                store,
                out_dir=args.panel_dir,
                engine=image_engine,
                chapters=wanted,
                seed=args.seed,
                width=args.width,
                height=args.height,
                client=director_client,
                max_panels=max_panels,
                block_range=block_range,
                observer_id=getattr(args, "observer", OBSERVER_READER),
            )
        print(report.summary())

    if not args.skip_motion:
        report = build_motion_library(
            args.novel,
            out_dir=args.motion_dir,
            engine=get_motion_engine(args.motion_engine),
        )
        print(report.summary())

    if not args.skip_compose:
        report = render_videos(
            args.novel,
            store,
            panel_dir=args.panel_dir,
            motion_dir=args.motion_dir,
            voice_dir=args.voice_dir,
            out_dir=args.out,
            engine=get_compose_engine(
                args.compose_engine,
                width=args.video_width,
                height=args.video_height,
                speed=args.speed,
            ),
            captions=not args.no_captions,
            chapters=wanted,
            clips_per_chapter=args.clips_per_chapter,
        )
        print(report.summary())
        print(f"\nvideos written under: {args.out}")

    store.close()
    return 0


def _query_attributes(args: argparse.Namespace) -> int:
    """List an entity's stored attributes.

    Accepts a bare id (`self1`), a fully-qualified one
    (`reverend-insanity:self1`) or a canonical label, because the id scheme
    is generated and nobody types it from memory.
    """
    store = _open_store(args)
    kind = TargetKind(args.kind)

    target = args.entity
    if not store.get_self(target):
        qualified = f"{args.novel}:{target}"
        if store.get_self(qualified):
            target = qualified
        else:
            matches = [
                e
                for e in store.all_selves(args.novel)
                if e.canonical_label.casefold() == target.casefold()
            ]
            if not matches:
                print(f"error: no entity {args.entity!r} in {args.novel}", file=sys.stderr)
                store.close()
                return 2
            target = matches[0].id

    entity = store.get_self(target)
    label = entity.canonical_label if entity else target

    if kind is not TargetKind.PERSONA:
        lookups = [target]
    else:
        # **Every body, not just the first.** A regressor or transmigrator
        # has more than one persona (Fang Yuan: body1, body2), and printing
        # only `f"{target}:body1"` silently hid every later body's
        # attributes from this command -- there was no way to see them
        # without querying the store directly.
        from echotales.pipeline.persona.split import bodies_of

        bodies = bodies_of(store, target)
        lookups = [persona_id for persona_id, _interval in bodies] or [f"{target}:body1"]

    for lookup in lookups:
        attrs = store.get_attributes(kind, lookup)
        print(f"{label}  ({target}, {kind.value} {lookup})")
        if not attrs:
            print("  no attributes stored")
            continue
        for attr in sorted(attrs, key=lambda a: (a.key, a.learned_at_pos.chapter)):
            standing = "" if attr.is_standing else "  [retracted]"
            print(
                f"  {attr.key:<28} {attr.value}"
                f"   ({attr.truth_status.value}, ch{attr.learned_at_pos.chapter:g}){standing}"
            )

    store.close()
    return 0


def cmd_appearance(args: argparse.Namespace) -> int:
    """Phase 7b: extract physical appearance into PERSONA attributes."""
    from echotales.pipeline.resolve.appearance_extract import extract_appearance

    store = _open_store(args)
    client = _build_client(store)
    if client is None:
        print(
            "error: appearance extraction needs a model backend "
            "(set ECHOTALES_MODEL_BACKEND=ollama). There is no deterministic "
            "fallback -- no honorific states hair colour.",
            file=sys.stderr,
        )
        return 2

    wanted = None
    if selected := _chapter_range(getattr(args, "chapters", None)):
        wanted = [n for n in store.chapter_numbers(args.novel) if n in selected]

    report = extract_appearance(
        args.novel,
        store,
        client=client,
        chapters=wanted,
        max_chapters=args.max_chapters,
    )
    print(report.summary())
    store.close()
    return 0


def cmd_reader(args: argparse.Namespace) -> int:
    """Chapter reader pass: speaker attribution by a model that is shown the cast list."""
    from echotales.pipeline.reader.runner import read_novel

    store = _open_store(args)
    client = _build_client(store)
    if client is None:
        print("error: the reader pass needs a model backend (set ECHOTALES_MODEL_BACKEND=ollama).", file=sys.stderr)
        return 2
    wanted = None
    if selected := _chapter_range(getattr(args, "chapters", None)):
        wanted = [n for n in store.chapter_numbers(args.novel) if n in selected]
    report = read_novel(args.novel, store, client, chapters=wanted)
    print(report.summary())
    store.close()
    return 0


def unload_ollama_models(*, prefix: str = "") -> None:
    """Evict ollama's resident models from VRAM before a local-GPU stage.

    ollama is a persistent server: finishing a stage's calls does not free
    the ~5 GB its model holds, so any diffusion stage that runs afterwards
    in the same session has to share an 8 GB card with it and OOMs.
    `keep_alive: 0` unloads the weights without killing the server, so the
    next ollama-backed command still works with no manual restart.

    **Every model the backend could use, not just the ones this process
    called.** A cached stage can make zero model calls and still find
    ollama holding weights from an *earlier command* -- which is exactly
    how the reference-sheet generator OOM'd immediately after an appearance
    run that had already exited. `models_required` is the fixed, correct
    set regardless of what ran.

    Best-effort by design: a failure here is a warning, not a stage abort.
    """
    import httpx as _httpx
    from echotales.pipeline.config import get_settings
    from echotales.pipeline.llm.tasks import models_required

    host = get_settings().llm_local_host
    for model_name in models_required("ollama"):
        try:
            _httpx.post(
                f"{host}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=10.0,
            )
            print(f"{prefix}unloaded {model_name} from ollama to free VRAM")
        except Exception as exc:
            print(f"warning: failed to unload ollama model {model_name!r}: {exc}")


def cmd_persona(args: argparse.Namespace) -> int:
    """Persona-level operations: reference sheets, wiki canon import."""
    from echotales.pipeline.persona.reference_gen import generate_references
    from echotales.pipeline.render.panels import get_engine

    sub = getattr(args, "persona_command", "")
    if sub == "wiki-canon":
        return _cmd_wiki_canon(args)
    if sub in (
        "refimg-search", "refimg-list", "refimg-select", "refimg-register",
        "refimg-sheets", "refimg-approve", "refimg-reject",
    ):
        return _cmd_refimg(args, sub)

    store = _open_store(args)
    # The reference engine is a local diffusion pipeline; anything ollama
    # still holds from a previous command competes with it for the same
    # 8 GB. Verified: this OOM'd at 4.95 GiB resident straight after an
    # `appearance` run.
    unload_ollama_models()
    report = generate_references(
        args.novel,
        store,
        engine=get_engine(args.engine),
        out_dir=args.out,
        top=args.top,
        include_recurring=not args.principals_only,
        seed=args.seed,
        reference_transition_mode=getattr(args, "reference_transition_mode", "txt2img"),
    )
    print(report.summary())
    for label, path in sorted(report.paths.items()):
        print(f"  {label:<28} {path}")
    store.close()
    return 0


def _cmd_wiki_canon(args: argparse.Namespace) -> int:
    """Import appearance from a fandom wiki into the canon cache.

    Deliberately a separate command rather than a pipeline stage: it is the
    only part of the system that reaches the open internet, and a render
    must never depend on that succeeding. It writes a file; everything
    downstream only ever reads what it wrote.
    """
    from echotales.pipeline.persona.wiki_canon import build_wiki_canon, save_wiki_canon

    store = _open_store(args)
    # Ranked by mention count, the same ordering `reference_gen` uses to
    # decide who is worth GPU time -- one request per character, so the
    # cast has to be cut somewhere, and "who the novel talks about most"
    # is the same answer here as there.
    people = [e for e in store.all_selves(args.novel) if e.kind.is_person]
    labels = [
        entity.canonical_label
        for entity in sorted(
            people, key=lambda e: -store.mention_count_for(args.novel, e.id)
        )[: args.top]
    ]
    report = build_wiki_canon(args.novel, labels)
    print(report.summary())
    for label, traits in sorted(report.entries.items()):
        print(f"  {label:<28} " + ", ".join(f"{k}={v}" for k, v in sorted(traits.items())))
    if not args.dry_run and report.entries:
        print(f"  written to {save_wiki_canon(report, data_root=args.data_root)}")
    store.close()
    return 0


def _cmd_refimg(args: argparse.Namespace, sub: str) -> int:
    """Opt-in reference-image candidate search and review-queue CLI.

    This is the second part of the system that reaches the open internet
    (`_cmd_wiki_canon` was the first) -- same reasoning applies: it is a
    standalone command, never a pipeline stage a render depends on, and a
    failed/empty search degrades to "no candidates" rather than aborting
    anything. Nothing this command does is wired into image generation;
    see `persona/refimg.py` module docstring and HANDOFF 4.47.
    """
    from echotales.pipeline.persona import refimg

    store = _open_store(args)
    try:
        if sub == "refimg-search":
            novel_row = store.conn.execute(
                "SELECT title FROM novel WHERE id=?", (args.novel,)
            ).fetchone()
            title = args.title or (novel_row["title"] if novel_row else args.novel)
            results = refimg.search_batch(
                store, args.novel, title,
                self_ids=args.characters, max_results=args.max_results,
            )
            for r in results:
                if r.error:
                    print(f"{r.character_label} ({r.self_id}): SEARCH FAILED: {r.error}")
                    continue
                print(f"{r.character_label} ({r.self_id}) -- query: {r.query!r}")
                if not r.candidates:
                    print("  no candidates found")
                for c in r.candidates:
                    print(f"  [{c.id}] {c.source_url}")
                    if c.title:
                        print(f"      title: {c.title}")
                    if c.source_page:
                        print(f"      page:  {c.source_page}")
            return 0

        if sub == "refimg-list":
            candidates = refimg.list_candidates(store, args.novel, args.character)
            if not candidates:
                print(f"no candidates stored for {args.character}")
                return 0
            for c in candidates:
                mark = "*" if c.selected else " "
                origin = "user-upload" if c.user_uploaded else c.backend
                print(f"[{mark}] {c.id}  ({origin})")
                print(f"      {c.source_url}")
                if c.title:
                    print(f"      title: {c.title}")
            return 0

        if sub == "refimg-select":
            candidate = refimg.select_candidate(
                store, args.novel, args.character, args.candidate,
                actor=args.actor, note=args.note,
            )
            print(f"selected {candidate.id} for {args.character}: {candidate.source_url}")
            return 0

        if sub == "refimg-register":
            candidate = refimg.register_user_image(
                store, args.novel, args.character, args.path,
                actor=args.actor, note=args.note,
            )
            print(f"registered and selected {candidate.id} for {args.character}: {candidate.source_url}")
            return 0

        if sub == "refimg-sheets":
            import hashlib
            from pathlib import Path

            if getattr(args, "character", None):
                candidates = refimg.list_sheets(
                    store, args.novel, args.character, persona_id=getattr(args, "persona", None)
                )
            else:
                cur = store.conn.execute(
                    "SELECT * FROM ref_image_candidate WHERE novel_id=? AND role='sheet'"
                    " ORDER BY character_label, found_at DESC",
                    (args.novel,),
                )
                from echotales.core.store import _refimg_from_row

                candidates = [_refimg_from_row(r) for r in cur]

            if not candidates:
                print(f"no reference sheets stored for {args.novel}")
                return 0

            for c in candidates:
                fpath = Path(c.source_url.removeprefix("file://")) if c.source_url.startswith("file://") else None
                file_exists = fpath.is_file() if fpath else False
                is_stale = False
                if file_exists and ":sheet:" in c.id and fpath:
                    expected_sha = c.id.rsplit(":sheet:", 1)[-1]
                    try:
                        actual_sha = hashlib.sha1(fpath.read_bytes()).hexdigest()[:10]
                        if actual_sha != expected_sha:
                            is_stale = True
                    except OSError:
                        is_stale = True

                if c.selected and not is_stale and file_exists:
                    status = "APPROVED (conditions panels)"
                    mark = "x"
                elif is_stale or (c.selected and not file_exists):
                    status = "STALE (file modified or missing; approval revoked)"
                    mark = "!"
                else:
                    status = "UNAPPROVED (inert)"
                    mark = " "

                print(f"[{mark}] {c.character_label} ({c.self_id}) | persona: {c.persona_id}")
                print(f"    id:     {c.id}")
                print(f"    status: {status}")
                print(f"    file:   {c.source_url}")
            return 0

        if sub == "refimg-approve":
            candidate = refimg.approve_sheet(
                store, args.novel, args.character, args.candidate,
                actor=args.actor, note=args.note,
            )
            print(f"approved sheet {candidate.id} for {args.character}: {candidate.source_url}")
            return 0

        if sub == "refimg-reject":
            candidate = refimg.reject_sheet(
                store, args.novel, args.character, args.candidate,
                actor=args.actor, note=args.note,
            )
            print(f"rejected sheet {candidate.id} for {args.character}")
            return 0

        raise ValueError(f"unknown refimg subcommand {sub!r}")
    finally:
        store.close()


def cmd_relevance(args: argparse.Namespace) -> int:
    """Rank rendered panels by how little of their prompt the source says."""
    from echotales.pipeline.render.relevance import audit

    store = _open_store(args)
    block_text: dict[tuple[float, int], str] = {}
    for number in store.chapter_numbers(args.novel):
        chapter = store.get_chapter(args.novel, number)
        if chapter is None:
            continue
        for block in chapter.blocks:
            block_text[(number, block.index)] = block.text

    report = audit(args.manifest, block_text, novel_id=args.novel, store=store)
    print(report.summary())
    print("\n  weakest panels (score, blocks, file, words shared with the passage):")
    for panel in report.worst(args.worst):
        print("  " + panel.line())

    cast_failures = [p for p in report.panels if p.cast_missing]
    if cast_failures:
        print(f"\n  panels that dropped an expected cast member ({len(cast_failures)}):")
        for panel in cast_failures[: args.worst]:
            print("  " + panel.line())

    condition_failures = [p for p in report.panels if p.condition_missing]
    if condition_failures:
        print(f"\n  panels that dropped a narrated condition ({len(condition_failures)}):")
        for panel in condition_failures[: args.worst]:
            print("  " + panel.line())

    store.close()
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    """Render the graph itself, browsable, with a position slider."""
    from echotales.pipeline.graphview import write_graphview

    store = _open_store(args)
    path = write_graphview(store, args.novel, args.out, top=args.top)
    print(f"knowledge graph written to {path}")
    store.close()
    return 0


def cmd_faithfulness(args: argparse.Namespace) -> int:
    """Exit 1 when anything a reader at a cut is served depends on chapters after it (eval/faithfulness.py)."""
    import json
    from pathlib import Path

    from echotales.pipeline import paths
    from echotales.pipeline.eval.faithfulness import check_reader_faithfulness

    db = getattr(args, "db", None) or get_settings().db_path
    if not Path(db).exists():
        print(f"no database at {db}", file=sys.stderr)
        return 2
    import sqlite3

    # Read-only: opening a `Store` writes schema metadata, and this command promises never to touch the source.
    con = sqlite3.connect(f"file:{Path(db).resolve()}?mode=ro", uri=True)
    try:
        (top,) = con.execute("SELECT MAX(number) FROM chapter WHERE novel_id=?", (args.novel,)).fetchone()
    finally:
        con.close()
    if top is None:
        print(f"{args.novel!r} has no chapters in {db}", file=sys.stderr)
        return 2
    last = int(top)
    if args.cuts:
        cuts = sorted({int(c) for c in args.cuts.split(",")})
    else:
        # A tenth, a quarter and half of the book: early cuts are where a whole-volume value differs most from what
        # the reader has seen (the audit's 23/289 divergent facts were concentrated at chapters 5-10).
        cuts = sorted({max(1, round(last * f)) for f in (0.1, 0.25, 0.5)} - {last})
    bad = [c for c in cuts if c < 1 or c >= last]
    if bad:
        print(f"cuts must be between 1 and {last - 1} (the book has {last} chapters): {bad}", file=sys.stderr)
        return 2
    prefix_causal = not args.whole_volume_personas and get_settings().persona_prefix_causal
    work_dir = Path(args.work_dir) if args.work_dir else paths.SCRATCH_DIR / "faithfulness" / args.novel
    print(f"=== reader faithfulness: {args.novel}, cuts {cuts}, prefix-causal personas {'on' if prefix_causal else 'off'} ===")
    report = check_reader_faithfulness(db, args.novel, cuts, work_dir=work_dir, prefix_causal=prefix_causal)
    for cut in report.cuts:
        print(cut.summary())
        for sid, key in cut.persona_divergent[:5]:
            print(f"    persona  {sid}  {key}")
        for eid, f in cut.cast_divergent[:5]:
            print(f"    cast     {eid}  {f}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({
            "novel_id": report.novel_id, "prefix_causal": report.prefix_causal, "ok": report.ok,
            "cuts": [{"chapter": c.chapter, "people_compared": c.people_compared, "seconds": c.seconds,
                      "persona_divergent": c.persona_divergent, "cast_divergent": c.cast_divergent} for c in report.cuts],
        }, indent=1))
    print("faithful at every cut" if report.ok else "NOT faithful: a reader at some cut is served later chapters")
    return 0 if report.ok else 1


_DISPATCH = {
    "faithfulness": cmd_faithfulness,
    "graph": cmd_graph,
    "relevance": cmd_relevance,
    "run": cmd_run,
    "appearance": cmd_appearance,
    "reader": cmd_reader,
    "persona": cmd_persona,
    "voice": cmd_voice,
    "render": cmd_render,
    "review": cmd_review,
    "ingest": cmd_ingest,
    "resolve": cmd_resolve,
    "query": cmd_query,
    "eval": cmd_eval,
    "ablate": cmd_ablate,
    "observations": cmd_observations,
    "annotate": cmd_annotate,
    "export": cmd_export,
    "webview": cmd_webview,
    "webview-server": cmd_webview_server,
}


def dispatch(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    handler = _DISPATCH.get(args.command)
    if handler is None:
        print(f"unknown command: {args.command}", file=sys.stderr)
        return 2
    return handler(args)
