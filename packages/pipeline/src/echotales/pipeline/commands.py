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
    # 7b reads the personas 7 just minted and needs a model: appearance is
    # never stated by an honorific the way age is, so there is no
    # deterministic path to fall back to (see appearance_extract's docstring).
    if client is not None and not getattr(args, "skip_appearance", False):
        from echotales.pipeline.resolve.appearance_extract import extract_appearance

        stage("7b appearance", lambda: extract_appearance(novel, store, client=client))

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


def cmd_eval(args: argparse.Namespace) -> int:
    from echotales.pipeline.eval import (
        EvalMode,
        build_gold_retrieval_cases,
        build_self_retrieval_cases,
        evaluate_recall,
        miss_report,
    )
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
            print("\n  -- confirmed only (this is the reportable result) --")
            print("  " + confirmed_score.summary().replace("\n", "\n  "))
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
    if getattr(args, "kinds_only", False):
        from pathlib import Path

        from echotales.pipeline.config import get_settings
        from echotales.pipeline.resolve.kind_backfill import backfill_kinds

        cfg = get_settings()
        cache_path = Path(cfg.lexicon_path) / f"{args.novel}-ner-cache.json"
        stats = backfill_kinds(store, args.novel, cache_path)
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
        ).summary()
    )
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
    from echotales.pipeline.voice.bank import load_cremad

    store = _open_store(args)
    try:
        bank = (
            load_cremad(args.bank)
            if getattr(args, "bank_kind", "vctk") == "cremad"
            else load_vctk(args.bank)
        )
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

    image_engine_name = args.image_engine
    if not get_settings().enable_image_gen and image_engine_name != "stub":
        print(
            f"note: ECHOTALES_ENABLE_IMAGE_GEN=false overrides --image-engine "
            f"{image_engine_name!r} -> stub (iterating on voice/TTS only; flip "
            "the flag back on when done)"
        )
        image_engine_name = "stub"

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
        args.out = str(Path(args.out) / _tag / _version)
        args.motion_dir = str(Path(args.motion_dir) / _tag / _version)
        print(f"output version: {_version}")

    if not args.skip_panels:
        image_engine = (
            get_panel_engine(image_engine_name, palette=args.palette, accent_hue=args.accent_hue)
            if image_engine_name == "manga"
            else get_panel_engine(image_engine_name)
        )
        director_client = _build_client(store) if not args.no_director else None
        two_phase = director_client is not None and get_settings().render_direction_first

        if two_phase:
            # Direction and image generation split into two passes so an
            # LLM backend that needs the local GPU (ollama) never has to
            # share it with the local diffusion engine in the same process
            # -- see render_panels's own docstring on prompt_cache_path and
            # EVOLUTION.md section 9 for the measured OOM this avoids.
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
            cache_path = Path(args.panel_dir) / f"prompt_cache_{_version or 'x'}.json"
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
                max_panels=args.max_panels,
                block_range=block_range,
                prompt_cache_path=cache_path,
                version=_version,
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
                max_panels=args.max_panels,
                block_range=block_range,
                prompt_cache_path=cache_path,
                version=_version,
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
                max_panels=args.max_panels,
                block_range=block_range,
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
        print(f"\nvideos written under: {Path(args.out) / args.novel}")

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
    if sub in ("refimg-search", "refimg-list", "refimg-select", "refimg-register"):
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


_DISPATCH = {
    "graph": cmd_graph,
    "relevance": cmd_relevance,
    "run": cmd_run,
    "appearance": cmd_appearance,
    "persona": cmd_persona,
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
