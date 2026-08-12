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
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import TargetKind
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.pipeline.config import get_settings

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


def _build_client(store: Store, *, no_llm: bool = False):  # type: ignore[no-untyped-def]
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
    client.require_ready()
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
    from echotales.pipeline.anaphora import resolve_novel as anaphora_resolve
    from echotales.pipeline.ingest import get_source, ingest_novel
    from echotales.pipeline.mentions import detect_mentions, load_or_seed
    from echotales.pipeline.resolve import resolve_novel as global_resolve
    from echotales.pipeline.persona import build_personas
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

    def stage(name: str, fn):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        try:
            result = fn()
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

    stage("0 ingest", lambda: ingest_novel(novel, store, chapters=chapters))
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
    stage("5 anaphora", lambda: anaphora_resolve(novel, store))
    from echotales.pipeline.corrections import CorrectionLog

    # Keyed by the *database's* stem, not just the novel id: entity ids
    # (self1, self2, ...) are a fresh in-memory counter every resolve run
    # (see resolve/runner.py), never resumed from what's on disk, so a run
    # against a non-canonical --db (a throwaway rerun, an experiment) mints
    # ids that do not correspond to the same characters in the canonical
    # data/webview-working/<novel>.db. Auto-flags referencing those ids must
    # never land in that novel's real corrections log. A canonical run's db
    # stem already equals the novel id, so this is a no-op there.
    corrections_log = CorrectionLog(Path("data/corrections") / f"{Path(store.path).stem}.jsonl")
    stage(
        "6 resolve",
        lambda: global_resolve(novel, store, lexicon=lexicon, corrections_log=corrections_log),
    )
    # Phase 7 runs last because it reads what every earlier phase produced:
    # resolved entities, their attributed dialogue, and the NER-derived kind
    # that says which of them are people at all.
    stage("7 personas", lambda: build_personas(novel, store, client=client))

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


def cmd_eval(args: argparse.Namespace) -> int:
    from echotales.pipeline.eval import EvalMode, build_self_retrieval_cases, evaluate_recall
    from echotales.pipeline.eval.coref_score import score_b3
    from echotales.pipeline.eval.gold import read_gold
    from echotales.pipeline.resolve.retrieve import CandidateRetriever

    store = _open_store(args)
    retriever = CandidateRetriever()
    for mention in store.get_mentions(args.novel, resolved_only=True):
        if mention.target_id:
            retriever.observe(
                mention.target_id, mention.text, "", mention.chapter, label=mention.text
            )

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
    print(f"\n=== gold comparison: {gold_path} ===")
    if not gold.mentions:
        print(f"  no gold file at {gold_path} -- skipping. See `echotales export`/eval/draft.py.")
    else:
        print(f"  {gold.coverage()}")
        draft_score = score_b3(store, args.novel, gold.entities_only)
        print("\n  -- all drafted annotations (not a result, see confirmed-only below) --")
        print("  " + draft_score.summary().replace("\n", "\n  "))
        confirmed = gold.confirmed_only.entities_only
        if confirmed.mentions:
            confirmed_score = score_b3(store, args.novel, confirmed)
            print("\n  -- human-confirmed only (this is the reportable result) --")
            print("  " + confirmed_score.summary().replace("\n", "\n  "))
            if args.report:
                print(confirmed_score.worst_report())
        else:
            print(
                "\n  0 human-confirmed records -- nothing here is a reportable result yet."
            )
        if args.report:
            print(draft_score.worst_report())

    store.close()
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from echotales.pipeline.ingest import ingest_novel

    store = _open_store(args)
    report = ingest_novel(args.novel, store, chapters=_chapter_range(args.chapters))
    print(report.summary())
    store.close()
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    from echotales.pipeline.ingest import get_source
    from echotales.pipeline.mentions import load_or_seed
    from echotales.pipeline.resolve import resolve_novel

    store = _open_store(args)
    lexicon = load_or_seed(get_source(args.novel).lexicon)
    print(resolve_novel(args.novel, store, lexicon=lexicon).summary())
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

    serve(sources, host=args.host, port=args.port)
    return 0


def cmd_voice(args: argparse.Namespace) -> int:
    """Phase 8: cast voices and render the script."""
    from echotales.pipeline.voice import get_engine, load_vctk, render_novel

    store = _open_store(args)
    try:
        bank = load_vctk(args.bank)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "the voice bank is CSTR VCTK 0.92; download and extract it under "
            f"{args.bank!r} (see HANDOFF §7)",
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

    report = render_novel(
        args.novel,
        store,
        bank,
        out_dir=args.out,
        engine=get_engine(args.engine),
        chapters=wanted,
        seed=args.seed,
        synthesize=not args.dry_run,
    )
    print(report.summary())
    print(f"\nmanifest: {Path(args.out) / args.novel / 'manifest.jsonl'}")
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

    if not args.skip_panels:
        report = render_panels(
            args.novel,
            store,
            out_dir=args.panel_dir,
            engine=get_panel_engine(args.image_engine),
            chapters=wanted,
            seed=args.seed,
            width=args.width,
            height=args.height,
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
            engine=get_compose_engine(args.compose_engine),
            chapters=wanted,
        )
        print(report.summary())
        print(f"\nvideos written under: {Path(args.out) / args.novel}")

    store.close()
    return 0


_DISPATCH = {
    "run": cmd_run,
    "voice": cmd_voice,
    "render": cmd_render,
    "review": cmd_review,
    "ingest": cmd_ingest,
    "resolve": cmd_resolve,
    "query": cmd_query,
    "eval": cmd_eval,
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
