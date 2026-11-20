"""The Product Orchestration track's job queue.

`webview_server.py`'s HTTP routes need to trigger a real pipeline stage
(ingest, resolve, persona, render, ...) without blocking the request thread
for however long that stage takes -- minutes for `resolve`, potentially
hours for a full-chapter `render`. This module is the whole answer to that:
one in-process worker thread pulling `Job`s off a `queue.Queue` and running
them strictly sequentially, one at a time, process-wide.

Deliberately not a task queue library (Celery/RQ/etc.) or a second process --
this is a single-user, self-hosted tool, and the project's own
`config.json::render.direction_first` toggle already establishes the
precedent that this codebase runs local-model stages one at a time to avoid
two of them fighting over one GPU. A single worker thread generalizes that
same constraint to every stage, and needs no distributed infrastructure to
do it.

Each job gets its own `Store(db_path)` connection, opened on the worker
thread -- never the request thread's connection. `webview_server.py::serve`
already documents why: sqlite3 forbids using a connection from a thread
other than the one that created it.

Execution reuses `pipeline_run.py`'s `stage()` context manager for
bookkeeping (StageRun/StageArtifact, skip-on-`SUCCEEDED`-digest
resumability) rather than reimplementing it -- the same helper
`commands.py::cmd_run`'s dispatch now goes through (see `run_stage` below,
which both `cmd_run` and this module's `run_job` call).
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from echotales.core.lifecycle import JobStatus, StageStatus
from echotales.core.models import Job
from echotales.core.pipeline_run import (
    PartialStageFailure,
    digest_text,
    ensure_pipeline_run,
    finish_stage,
    start_stage,
)
from echotales.core.store import Store
from echotales.pipeline.engines import registry as engine_registry
from echotales.pipeline.version import PIPELINE_VERSION

log = logging.getLogger(__name__)

#: HTTP-triggered generation jobs never reach a paid API -- gemini/openrouter
#: stay CLI-only, operated by a human who opts in each time via the
#: existing `--image-engine` flag (approved plan, Product Orchestration
#: track: "Do not spend money"). Any other engine name a caller passes is a
#: 400, not a silent downgrade to stub -- a wrong request should look wrong,
#: not quietly succeed as something else.
ALLOWED_HTTP_ENGINES = engine_registry.http_image_engines()


def http_engine_known(name: str) -> bool:
    """Whether the HTTP API will consider this engine: the local set, plus the ONE hosted engine the operator chose.

    Paid engines are still never reachable by naming them in a request: a hosted engine is accepted only when
    `ECHOTALES_IMAGE_PROVIDER` (or the `cloud` preset) selected it in `.env`, which is the operator's opt-in to spend.
    """
    from echotales.pipeline.compute import policy

    return name in ALLOWED_HTTP_ENGINES or name in policy().http_engines()

#: The set of job kinds this module knows how to run. Mirrors the CLI's own
#: subcommand granularity (`cli.py`'s `ingest`/`resolve`/`persona`/
#: `appearance`/`render`/`voice`/`refimg-search`) rather than inventing a
#: different breakdown -- an HTTP-triggered `resolve` job behaves exactly
#: like `echotales resolve`, including that command's existing prerequisite
#: assumptions (segment/mentions/speakers/anaphora already having run,
#: normally via `echotales run` or their own prior jobs).
JOB_KINDS = (
    # Every stage from ingest to personas in one job (the `echotales run` chain). The per-stage kinds below assume
    # segment, mentions, speakers and anaphora already ran and no job kind ran them, so a freshly uploaded book could
    # not be built from the Studio at all (audit B4).
    "pipeline",
    "ingest",
    "resolve",
    "reader",
    "appearance",
    "persona",
    "render",
    "voice",
    # Listen before choosing: one sample for each shortlisted narrator, or one line in one voice with a delivery
    # emotion (the Studio's audition screen; `echotales voice-audition` is the CLI twin).
    "voice_audition",
    # Binds the finished chapter tracks into one M4B with chapter markers; the CLI had `voice --m4b` and the Studio
    # had no way to produce or download the audiobook (audit B3).
    "export_m4b",
    # One mp4 per chapter from the rendered panels and the voiced audio: `echotales anime` (stills / ltx-local) or,
    # with narration pruning, the motion-comic `render` path. The CLI was the only way to make the video.
    "video",
    # One chapter as an episode: recap, cold open, title card, acts, next-episode card (roadmap M3): `echotales episode`.
    "episode",
    # Manga, comic or webtoon pages from a chapter's rendered panels (roadmap M1): `echotales pages`.
    "pages",
    # Comic, manga or webtoon pages into the graph and a voiced motion-comic video (roadmap M2): `echotales comic`.
    "comic",
    "refimg_search",
    "reference_gen",
    # Adaptation packs (roadmap M4): the cast, descriptions, voices, direction and corrections as one .etpack file
    # that carries no book text; the importer only applies what matches the chapter hashes of its own copy of the book.
    "pack_export",
    "pack_import",
    # The spoiler-safe "who is this again?" page for a reader who has finished chapter N (`echotales export companion`).
    "companion",
)


#: The `pipeline` job's stages in run order. `_run_pipeline` names its stages from here, and the job JSON counts
#: progress against it, so the two cannot drift. The reader and appearance stages are skipped by params
#: (`skip_reader`, `skip_appearance`) or when no model client is built, so the count is an upper bound for those.
PIPELINE_STAGES = (
    "0 ingest", "2 segment", "3 mentions", "4 speakers", "5 anaphora", "6 resolve",
    "6b reader", "7 personas", "7a gender", "7b appearance",
)


def pipeline_stage_names(params: dict[str, Any]) -> tuple[str, ...]:
    skipped = {"6b reader"} if params.get("skip_reader") else set()
    if params.get("skip_appearance"):
        skipped.add("7b appearance")
    return tuple(n for n in PIPELINE_STAGES if n not in skipped)


def new_job_id(novel_id: str, kind: str) -> str:
    return f"{novel_id}:{kind}:{uuid.uuid4().hex[:8]}"


def run_stage(
    store: Store,
    *,
    run_id: str,
    stage_name: str,
    input_digest: str,
    fn: Callable[[], Any],
    skip_if_succeeded: bool = True,
) -> Any:
    """Invoke `fn()` wrapped in `StageRun` bookkeeping.

    The one code path both `commands.py::cmd_run` and this module's
    `run_job` go through -- previously `cmd_run` had its own ad hoc
    `stage()` closure duplicating exactly this. Returns `fn()`'s result on
    success; records and re-raises on `PartialStageFailure` or any other
    exception, same semantics as `pipeline_run.py::stage()`, expressed as
    a plain function (not a context manager) so a caller that already has
    its own timing/report bookkeeping around this -- `cmd_run`'s
    `RunReport` -- doesn't need two nested context managers to get one
    stage's outcome.

    Resumability: when a `SUCCEEDED` `StageRun` already exists for this
    exact `(stage_name, input_digest)` pair, `fn` is never called and this
    returns `None` immediately -- the same skip check
    `pipeline_run.py::stage()` implements, applied here too so an
    HTTP-triggered job that re-POSTs an already-completed stage is a fast
    no-op rather than redone work.
    """
    if skip_if_succeeded:
        existing = store.find_succeeded_stage_run(stage_name, input_digest)
        if existing is not None:
            log.info(
                "stage %s skipped: already SUCCEEDED at %s (input_digest=%s)",
                stage_name, existing.stage_run_id, input_digest,
            )
            return None
    handle = start_stage(store, run_id=run_id, stage_name=stage_name, input_digest=input_digest)
    try:
        result = fn()
    except PartialStageFailure as exc:
        finish_stage(
            store, handle, status=StageStatus.PARTIAL,
            error_summary=f"{exc} (progress: {exc.progress})",
        )
        raise
    except Exception as exc:
        finish_stage(store, handle, status=StageStatus.FAILED, error_summary=str(exc))
        raise
    except BaseException as exc:
        # Interrupts bypass `except Exception`; without this the stage stays RUNNING for good.
        finish_stage(store, handle, status=StageStatus.FAILED, error_summary=f"interrupted: {type(exc).__name__}")
        raise
    finish_stage(store, handle, status=StageStatus.SUCCEEDED)
    return result


def _studio_version(out_dir: Path, chapters: list[float], engine_name: str, density: str = "beat") -> str:
    from echotales.pipeline.paths import next_version

    highest = max((int(next_version(out_dir / f"ch{c:g}")[1:]) for c in chapters), default=1)
    # The tiers draw very different numbers of pictures; the name says which one a version is (repo rule: every
    # version gets a descriptive suffix).
    return f"v{highest}_{engine_name}-studio" + ("-dense" if density == "dense" else "")


def _record_studio_version(out_dir: Path, chapters: list[float], version: str, engine_name: str, job_id: str) -> None:
    what = (
        "placeholder panels from the stub engine, not a real render"
        if engine_name == "stub"
        else f"{engine_name} engine; not yet reviewed"
    )
    line = f"\n## {version}\nQueued from the Studio ({job_id}, {time.strftime('%Y-%m-%d')}): {what}.\n"
    for c in chapters:
        chapter_dir = out_dir / f"ch{c:g}"
        if (chapter_dir / version).is_dir():
            with open(chapter_dir / "VERSIONS.md", "a", encoding="utf-8") as fh:
                fh.write(line)


VIDEO_ENGINES = engine_registry.names("video", surface="anime-video")


def _run_voice_audition(novel_id: str, params: dict[str, Any]) -> None:
    """The audition job: `target` "narrator" shortlists the banks and voices one sample each; "line" voices one
    line in one voice (a bank voice or this project's own) performing an emotion."""
    from echotales.pipeline import paths
    from echotales.pipeline.project_voices import with_project_voices
    from echotales.pipeline.voice import audition, get_engine
    from echotales.pipeline.voice.bank import VoiceBank, load_bank

    engine = get_engine(str(params.get("engine") or "chatterbox"))
    root = paths.asset_dir(novel_id, "audition")
    bank_root = params.get("bank", "data/voice")
    target = params.get("target")
    # Each audiobook corpus on its own: the combined "audiobook" bank refuses to load unless both are present, and
    # a machine with only Hi-Fi TTS should still be able to audition it.
    banks = []
    for kind in ("hifitts", "libritts_r"):
        try:
            banks.append(load_bank(kind, bank_root))
        except FileNotFoundError:
            continue
    if target == "narrator":
        if not banks:
            raise ValueError(f"no voice bank found under {bank_root}; see data/voice/README.md")
        audition.run_narrator_audition(banks, engine, root, int(params.get("n") or 12))
    elif target == "line":
        voice_id, text = str(params.get("voice_id") or ""), str(params.get("text") or "").strip()
        emotion = str(params.get("emotion") or "neutral")
        if not text or len(text) > audition.MAX_SAMPLE_CHARS:
            raise ValueError(f"the line must be between 1 and {audition.MAX_SAMPLE_CHARS} characters")
        bank = VoiceBank([v for b in banks for v in b.voices], bank_id="audiobook", licence="CC BY 4.0")
        voice = next((v for v in with_project_voices(bank, novel_id).voices if v.speaker_id == voice_id), None)
        if voice is None:
            raise ValueError(f"voice {voice_id!r} is not in the voice bank or this project's own voices")
        out = audition.line_sample_path(root, voice_id, emotion, text)
        if not out.is_file():
            audition.synthesize_line(voice, engine, out, text, emotion)
    else:
        raise ValueError(f"voice_audition target must be 'narrator' or 'line', not {target!r}")


def _run_video(store: Store, novel_id: str, params: dict[str, Any]) -> list[str]:
    """Chapter videos from the same code the CLI runs: `echotales anime` (`render.anime.compose_chapter_video`) for the
    `stills` and `ltx-local` engines, `render_videos` (the motion-comic path behind `render --prune-visual-narration`)
    when narration pruning is asked for, because only that path has the cut. Refuses, naming the fix, rather than
    failing deep in ffmpeg: a Studio user cannot read a stack trace."""
    from echotales.pipeline import paths
    from echotales.pipeline.render import anime

    engine = str(params.get("engine") or "stills")
    if engine not in VIDEO_ENGINES:
        raise ValueError(f"video engine {engine!r} is not one of {', '.join(VIDEO_ENGINES)}; pick stills or ltx-local")
    prune = bool(params.get("prune_visual_narration"))
    if not params.get("chapters"):
        raise ValueError("no chapters chosen; pass chapters, e.g. [1], for the chapters to make a video of")
    chapters = [float(c) for c in params["chapters"]]
    if engine == "ltx-local":
        if prune:
            raise ValueError("prune_visual_narration is only available with the stills engine; turn prune off or pick stills")
        from echotales.pipeline.compute import resource_refusal

        # The same refusal the render route applies, checked again at run time: the card may have filled while queued.
        if refusal := resource_refusal(engine, http=True):
            raise ValueError(str(refusal))

    panel_dir = params.get("panel_dir") or paths.asset_dir(novel_id, "panels")
    audio_dir = params.get("audio_dir") or paths.asset_dir(novel_id, "audio")
    out_dir = params.get("out_dir") or paths.asset_dir(novel_id, "video")

    if prune:
        from echotales.pipeline.render.compose import get_engine as get_compose_engine
        from echotales.pipeline.render.runner import render_videos

        for what, root, fix in (
            ("panel", panel_dir, f"render the panels (`echotales render --novel {novel_id}`)"),
            ("voice", audio_dir, f"voice the chapters (`echotales voice --novel {novel_id}`)"),
        ):
            if not (Path(root) / "manifest.jsonl").is_file():
                raise ValueError(f"no {what} manifest.jsonl under {root}; {fix} first")
        report = render_videos(
            novel_id, store, panel_dir=panel_dir, voice_dir=audio_dir, out_dir=out_dir,
            engine=get_compose_engine("ffmpeg"), chapters=chapters, prune_visual_narration=True,
        )
        if not report.chapters_rendered:
            raise ValueError("no video was written; the chapters have no panels or voiced audio in the manifests")
        return [report.summary()]

    # Every chapter's panels are resolved before any is composed, so a missing render fails the job before a long
    # first chapter, not after it.
    for chapter in chapters:
        anime.latest_panels_version(panel_dir, chapter, novel_id)
    out: list[str] = []
    for chapter in chapters:
        result = anime.compose_chapter_video(
            novel_id, chapter, engine=engine, panel_dir=panel_dir, audio_dir=audio_dir, out_dir=out_dir,
        )
        out.append(str(result.video) if result is not None else "")
    return out


def _run_episode(store: Store, novel_id: str, params: dict[str, Any]) -> list[str]:
    """`echotales episode` from the same function. Refuses with the fix named, as `video` does."""
    from echotales.pipeline.render import anime, episode

    if not params.get("chapters"):
        raise ValueError("no chapters chosen; pass chapters, e.g. [1], for the chapters to make an episode of")
    timing, motion = str(params.get("timing") or "voice"), str(params.get("motion") or "stills")
    if timing not in episode.TIMINGS or motion not in episode.MOTIONS:
        raise ValueError(f"timing must be one of {', '.join(episode.TIMINGS)} and motion one of {', '.join(episode.MOTIONS)}")
    if motion == "ltx-local":
        from echotales.pipeline.compute import resource_refusal

        if refusal := resource_refusal(motion, http=True):
            raise ValueError(str(refusal))
    out: list[str] = []
    try:
        for c in params["chapters"]:
            res = episode.compose_chapter_episode(
                store, novel_id, float(c), timing=timing, motion=motion, panel_dir=params.get("panel_dir"),
                audio_dir=params.get("audio_dir"), out_dir=params.get("out_dir"), suffix=params.get("suffix"),
            )
            out.append(str(res.video))
    except (anime.AnimeRefusal, episode.EpisodeRefusal) as exc:
        raise ValueError(str(exc)) from exc
    return out


def _run_pages(store: Store, novel_id: str, params: dict[str, Any]) -> list[str]:
    """Pages from the same code `echotales pages` runs. Returns each chapter's `pages.json`, which lists the
    files written, so a UI can link them without scanning the folder."""
    from echotales.pipeline.pages.build import build_pages, parse_exports
    from echotales.pipeline.pages.composer import FORMATS

    if not params.get("chapters"):
        raise ValueError("no chapters chosen; pass chapters, e.g. [1], for the chapters to make pages of")
    fmt = str(params.get("format") or "manga")
    if fmt not in FORMATS:
        raise ValueError(f"page format {fmt!r} is not one of {', '.join(FORMATS)}; pick one of them")
    exports = parse_exports(params.get("export") or "png")
    built = build_pages(
        store, novel_id, [float(c) for c in params["chapters"]], fmt=fmt, exports=exports,
        panel_dir=params.get("panel_dir"), out_root=params.get("out_dir"), suffix=params.get("suffix"),
    )
    return [str(b.manifest) for b in built]


def _run_comic(store: Store, novel_id: str, params: dict[str, Any]) -> list[str]:
    """`echotales comic ingest|understand|build` from the same functions. The pages are read from
    `data/novels/<CODE>/comic/source/<name>`, a name and never a path: the server decides where uploads live (same
    rule as the pack and voice folders), so a request cannot point the reader at any file on the machine."""
    from echotales.pipeline.comic import runner, upload

    stage = str(params.get("stage") or "build")
    if stage not in ("ingest", "understand", "build"):
        raise ValueError(f"comic stage {stage!r} is not one of ingest, understand, build")
    root = runner.comic_root(novel_id)
    if stage == "ingest" or (stage == "build" and params.get("source")):
        name = Path(str(params.get("source") or "")).name
        source = root / "source" / name
        if not name or not source.exists():
            raise ValueError(f"no comic source named {name!r} in this project's comic/source folder; upload it first")
        runner.ingest_stage(upload.source_input(source), novel_id, webtoon=bool(params.get("webtoon")))
        if stage == "ingest":
            return [str(root / "pages.json")]
    if stage in ("understand", "build") and (stage == "understand" or params.get("source")):
        runner.understand_stage(novel_id, ocr=str(params.get("ocr") or "rapidocr"), rtl=bool(params.get("rtl")))
        if stage == "understand":
            return [str(root / "understanding.json")]
    built = runner.build_stage(
        store, novel_id, title=str(params.get("title") or novel_id), chapter=float(params.get("chapter") or 1.0),
        credit=str(params.get("credit") or runner.DEFAULT_CREDIT), engine=str(params.get("engine") or "stub"),
        inpaint=str(params.get("inpaint") or "auto"), suffix=str(params.get("suffix") or "motion-comic"),
        trust_speakers=bool(params.get("trust_speakers")),
    )
    return [str(built.video.video)]


def _run_pipeline(store: Store, job_id: str, novel_id: str, params: dict[str, Any], sources_path: str):  # type: ignore[no-untyped-def]
    """Ingest through personas as one resumable job: `commands.py::cmd_run`'s chain with `run_stage` bookkeeping.

    Stage names and digests match `cmd_run`'s, so a book built from the CLI resumes here and the reverse. Each stage
    writes a `StageRun` under the job's run id, which is the per-stage progress the Studio reads. A stage that already
    succeeded for this exact source is skipped unless `params["force"]` is set; a failure stops the chain and the
    next run picks up at the failed stage."""
    from echotales.core.pipeline_run import source_digest_of
    from echotales.pipeline import long_series
    from echotales.pipeline.anaphora import resolve_anaphora_for_novel as anaphora_resolve
    from echotales.pipeline.commands import _build_client
    from echotales.pipeline.config import get_settings
    from echotales.pipeline.corrections import CorrectionLog
    from echotales.pipeline.ingest import get_source, ingest_novel
    from echotales.pipeline.ingest.adapters import ChapterRange
    from echotales.pipeline.mentions import detect_mentions, load_or_seed
    from echotales.pipeline.persona import build_personas
    from echotales.pipeline.resolve import resolve_novel as global_resolve
    from echotales.pipeline.segment import segment_novel
    from echotales.pipeline.speakers import attribute_novel

    config = get_source(novel_id, sources_path)
    lexicon = load_or_seed(config.lexicon)
    chapters = ChapterRange.parse(params["chapters"]) if params.get("chapters") else None
    # None means a deterministic run (stub backend or `no_llm`); a real backend that is not reachable raises here, at
    # the start, instead of on chapter 140.
    client = _build_client(store, no_llm=bool(params.get("no_llm")))
    source_digest = source_digest_of(config.path)
    pipeline_run = ensure_pipeline_run(
        store, novel_id=novel_id, source_digest=source_digest, pipeline_version=PIPELINE_VERSION, is_build=True
    )
    # Stored now, not at the end: the job detail lists stage runs by this id, so a long build shows which stage it is
    # in instead of an empty list until it finishes.
    store.update_job(job_id, run_id=pipeline_run.run_id)
    corrections_path = params.get("corrections_path")
    corrections_log = CorrectionLog(Path(corrections_path)) if corrections_path else None
    skip = not params.get("force", False)
    (s_ingest, s_segment, s_mentions, s_speakers, s_anaphora, s_resolve,
     s_reader, s_personas, s_gender, s_appearance) = PIPELINE_STAGES

    def stage(name: str, fn: Callable[[], Any]) -> None:
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name=name,
            input_digest=digest_text(f"{source_digest}|{name}|v{PIPELINE_VERSION}"),
            fn=fn, skip_if_succeeded=skip,
        )

    try:
        stage(s_ingest, lambda: ingest_novel(novel_id, store, sources_path=sources_path, chapters=chapters))
        # A re-ingest of an edited book: name what the changed chapters invalidate before the later stages run, so
        # the job log says why those stages cannot be skipped. The baseline is re-recorded once the build finishes.
        stale = long_series.invalidate_changed(store, novel_id)
        if stale.chapters:
            log.info("chapters changed since the last build: %s; stale: %s", stale.chapters, stale.to_dict()["products"])
        stage(s_segment, lambda: segment_novel(novel_id, store))
        stage(s_mentions, lambda: detect_mentions(novel_id, store, lexicon=lexicon, client=client))
        stage(s_speakers, lambda: attribute_novel(novel_id, store, client=client, llm_chapter_cutoff=0.0))
        stage(s_anaphora, lambda: anaphora_resolve(novel_id, store, recover_pronoun_speakers=False))
        stage(s_resolve, lambda: global_resolve(
            novel_id, store, lexicon=lexicon, corrections_log=corrections_log, force_rewipe=False
        ))
        if client is not None and not params.get("skip_reader"):
            from echotales.pipeline.reader.runner import read_novel

            stage(s_reader, lambda: read_novel(novel_id, store, client))
        stage(s_personas, lambda: build_personas(
            novel_id, store, client=client, prefix_causal=get_settings().persona_prefix_causal
        ))
        from echotales.pipeline.persona.gender import infer_missing_genders

        stage(s_gender, lambda: infer_missing_genders(novel_id, store, client))
        if client is not None and not params.get("skip_appearance"):
            from echotales.pipeline.resolve.appearance_extract import extract_appearance

            stage(s_appearance, lambda: extract_appearance(novel_id, store, client=client))
    except Exception:
        store.update_pipeline_run_status(pipeline_run.run_id, StageStatus.FAILED)
        raise
    store.update_pipeline_run_status(pipeline_run.run_id, StageStatus.SUCCEEDED)
    long_series.record_baseline(store, novel_id)
    return pipeline_run


def _dispatch(store: Store, job: Job, params: dict[str, Any]) -> str:
    """Call the one real stage function `job.kind` names, wrapped by
    `run_stage`. Returns the `pipeline_run.run_id` the stage's bookkeeping
    landed under (stored back onto the `Job` row by the caller).

    Mirrors each CLI command's own body (`commands.py::cmd_ingest`,
    `cmd_resolve`, `cmd_persona`, `_cmd_refimg`, `cmd_appearance`,
    `cmd_render`) rather than reinventing stage-invocation logic -- an
    HTTP-triggered stage behaves the same as its CLI equivalent.
    """
    novel_id = job.novel_id
    source_path = params.get("source_path", "")
    source_digest = digest_text(source_path or novel_id)
    pipeline_run = ensure_pipeline_run(
        store, novel_id=novel_id, source_digest=source_digest, pipeline_version=PIPELINE_VERSION
    )
    input_digest = digest_text(f"{source_digest}|{job.kind}|v{PIPELINE_VERSION}|{job.params_json}")
    # Stored before any work: a job that fails keeps its run id, so the job detail still lists its stages,
    # and a restart can find the run rows this job left RUNNING.
    store.update_job(job.job_id, run_id=pipeline_run.run_id)

    #: A project created through `POST /api/projects` + `/source` (rather
    #: than one of the three research-canonical novels) is never added to
    #: the shared `data/sources.toml` -- that file is hand-curated, one
    #: block per known novel (`sources.py` module docstring). The upload
    #: route instead writes a per-project `data/projects/<id>/sources.toml`
    #: with exactly one entry, and every job kind that needs source config
    #: (`ingest`, `resolve`) accepts that path via `params["sources_path"]`,
    #: falling back to the shared file so canonical-novel jobs keep working
    #: unchanged.
    sources_path = params.get("sources_path", "data/sources.toml")

    if job.kind == "pipeline":
        pipeline_run = _run_pipeline(store, job.job_id, novel_id, params, sources_path)
    elif job.kind == "ingest":
        from echotales.pipeline.ingest import ingest_novel
        from echotales.pipeline.ingest.adapters import ChapterRange

        chapters = ChapterRange.parse(params["chapters"]) if params.get("chapters") else None
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="ingest",
            input_digest=input_digest,
            fn=lambda: ingest_novel(
                novel_id, store, sources_path=sources_path, chapters=chapters
            ),
        )
    elif job.kind == "resolve":
        from echotales.pipeline.ingest import get_source
        from echotales.pipeline.mentions import load_or_seed
        from echotales.pipeline.resolve import resolve_novel

        lexicon = load_or_seed(get_source(novel_id, sources_path).lexicon)
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="resolve",
            input_digest=input_digest,
            fn=lambda: resolve_novel(novel_id, store, lexicon=lexicon),
        )
    elif job.kind == "reader":
        from echotales.pipeline.llm.client import ModelClient
        from echotales.pipeline.reader.runner import read_novel

        client = ModelClient(store=store)
        client.require_ready()
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="reader",
            input_digest=input_digest,
            fn=lambda: read_novel(novel_id, store, client),
        )
    elif job.kind == "appearance":
        from echotales.pipeline.llm.client import ModelClient
        from echotales.pipeline.resolve.appearance_extract import extract_appearance

        client = ModelClient(store=store)
        client.require_ready()
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="appearance",
            input_digest=input_digest,
            fn=lambda: extract_appearance(novel_id, store, client=client),
        )
    elif job.kind == "persona":
        from echotales.pipeline.config import get_settings
        from echotales.pipeline.persona import build_personas

        client = None
        if params.get("use_llm"):
            from echotales.pipeline.llm.client import ModelClient

            client = ModelClient(store=store)
            client.require_ready()
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="persona",
            input_digest=input_digest,
            fn=lambda: build_personas(novel_id, store, client=client, prefix_causal=get_settings().persona_prefix_causal),
        )
    elif job.kind == "render":
        from echotales.pipeline import paths
        from echotales.pipeline.compute import default_image_engine
        from echotales.pipeline.render.panels import get_engine, render_panels

        engine_name = params.get("engine") or default_image_engine()
        if not http_engine_known(engine_name):
            raise ValueError(
                f"engine {engine_name!r} is not enabled over HTTP. Local: {sorted(ALLOWED_HTTP_ENGINES)}; a hosted engine only if ECHOTALES_IMAGE_PROVIDER selects it"
            )
        from echotales.pipeline.compute import policy as _policy
        from echotales.pipeline.compute import resource_refusal as _refusal

        # A second check at run time: the job may have waited in the queue while memory or the GPU filled up, and a
        # job enqueued by a route that skipped the server's check must not reach the model loader.
        refusal = _refusal(engine_name, http=True)
        if refusal:
            raise ValueError(refusal)
        # The tier sets how many scenes (each one to three images): a preview by default in `local-low`, the whole chapter otherwise.
        max_panels = int(params.get("max_panels") or _policy().scenes_for(params.get("tier")))
        chapters = params.get("chapters")
        out_dir = params.get("panel_dir") or str(paths.asset_dir(novel_id, "panels"))
        # The CLI gives every render its own version directory (`commands.py::cmd_render`); this job did not, so a
        # Studio stub render wrote 33 placeholder panels into the root of LotM's `panels/ch1/` next to the real v1
        # render and replaced the only manifest that render had (2026-10-18 browser pass). One version name, new for
        # every requested chapter, with the descriptive suffix and VERSIONS.md line the convention asks for.
        wanted = chapters or store.chapter_numbers(novel_id)
        density = str(params.get("density", "beat"))
        from echotales.pipeline.compute import density_error

        if (bad := density_error(density)) is not None:
            raise ValueError(bad)
        version = _studio_version(Path(out_dir), wanted, engine_name, density)
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="render",
            input_digest=input_digest,
            fn=lambda: render_panels(
                novel_id, store,
                out_dir=out_dir,
                engine=get_engine(engine_name),
                chapters=chapters,
                seed=params.get("seed", 20260812),
                max_panels=max_panels,
                version=version,
                density=density,
            ),
        )
        _record_studio_version(Path(out_dir), wanted, version, engine_name, job.job_id)
    elif job.kind == "voice":
        from echotales.pipeline import paths
        from echotales.pipeline.voice import get_engine as get_voice_engine
        from echotales.pipeline.voice import render_novel
        from echotales.pipeline.voice.qa import engine_reference_f0

        # Speech unless told otherwise, like the CLI: the stub writes silent files (decision D29).
        engine_name = params.get("engine") or "chatterbox"
        # Same bank selection as `cmd_voice`; the HTTP job path hardcoded VCTK
        # and so could never use an emotion-capable bank.
        from echotales.pipeline.voice.bank import DEFAULT_BANK_KIND, load_bank

        bank_root = params.get("bank", "data/voice")
        bank_kind = params.get("bank_kind", DEFAULT_BANK_KIND)
        # The Studio's voice output is what export_m4b later binds, and that job cannot see the bank, so the
        # non-commercial licence (EARS, CC BY-NC 4.0) is enforced here, as `cmd_voice` does for `--m4b`.
        from echotales.pipeline.voice.bank import noncommercial_refusal

        if reason := noncommercial_refusal(bank_kind, m4b=True, allowed=bool(params.get("allow_noncommercial"))):
            raise ValueError(reason)
        from echotales.pipeline.project_voices import with_project_voices

        # Voices the person uploaded to this project (with their consent record) are cast alongside the bank's.
        bank = with_project_voices(load_bank(bank_kind, bank_root), novel_id)
        out_dir = params.get("out_dir") or str(paths.asset_dir(novel_id, "audio"))
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="voice",
            input_digest=input_digest,
            fn=lambda: render_novel(
                novel_id, store, bank,
                out_dir=out_dir,
                engine=get_voice_engine(engine_name),
                chapters=params.get("chapters"),
                seed=params.get("seed", 20260812),
                synthesize=not params.get("dry_run", False),
                reference_f0=engine_reference_f0(bank, engine_name),
            ),
        )
    elif job.kind == "voice_audition":
        # Never skipped by digest: a rerun is how a person asks for a fresh take, and a finished line sample is
        # already reused through its deterministic path.
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="voice_audition",
            input_digest=f"{input_digest}|{time.time()}",
            fn=lambda: _run_voice_audition(novel_id, params),
            skip_if_succeeded=False,
        )
    elif job.kind == "export_m4b":
        from echotales.pipeline import paths
        from echotales.pipeline.voice.export import book_tracks, engine_of, export_m4b

        audio_dir = Path(paths.asset_dir(novel_id, "audio"))
        if engine_of(audio_dir) == "stub" and not params.get("allow_stub"):
            raise ValueError("the audio in this project was made by the stub engine and is silent; voice it with chatterbox first")
        titles_by_number = {
            float(r["number"]): r["title"]
            for r in store.conn.execute("SELECT number, title FROM chapter WHERE novel_id=?", (novel_id,))
        }
        tracks, titles, numbers = book_tracks(audio_dir, titles_by_number)
        if not tracks:
            raise ValueError("no chapter audio found; run the voice step first")
        missing = [n for n in store.chapter_numbers(novel_id) if n not in set(numbers)]
        if missing and not params.get("allow_partial"):
            raise ValueError(
                f"audio exists for {len(numbers)} of {len(numbers) + len(missing)} chapters; "
                "voice the rest or set allow_partial to export a partial book"
            )
        novel_row = store.get_novel(novel_id) or {}
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="export_m4b",
            input_digest=digest_text(f"{input_digest}|{len(tracks)}|{max(t.stat().st_mtime for t in tracks)}"),
            fn=lambda: export_m4b(
                tracks, audio_dir / f"{novel_id}.m4b", titles=titles, title=novel_row.get("title", novel_id)
            ),
        )
    elif job.kind == "video":
        # Not `run_stage`'s skip: its digest is the params, but what a video is made from (the newest panel version,
        # the voiced audio) changes between runs with the same params, and a skipped rerun would show the old video.
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="video",
            input_digest=f"{input_digest}|{time.time()}",
            fn=lambda: _run_video(store, novel_id, params),
            skip_if_succeeded=False,
        )
    elif job.kind == "episode":
        # Not skippable by digest, for the same reason as `video`: the newest panel version and the audio are inputs.
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="episode",
            input_digest=f"{input_digest}|{time.time()}", skip_if_succeeded=False,
            fn=lambda: _run_episode(store, novel_id, params),
        )
    elif job.kind == "pages":
        # Not skippable by digest: the newest panel version is an input that changes between identical params.
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="pages",
            input_digest=f"{input_digest}|{time.time()}",
            fn=lambda: _run_pages(store, novel_id, params),
            skip_if_succeeded=False,
        )
    elif job.kind == "comic":
        # Not skippable by digest: the pages under comic/source can change between identical params.
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="comic",
            input_digest=f"{input_digest}|{time.time()}", skip_if_succeeded=False,
            fn=lambda: _run_comic(store, novel_id, params),
        )
    elif job.kind in ("pack_export", "pack_import"):
        from echotales.pipeline import packs, paths
        from echotales.pipeline.corrections import CorrectionLog

        pack_dir = Path(paths.asset_dir(novel_id, "packs"))
        corrections_path = params.get("corrections_path")
        corrections_log = CorrectionLog(Path(corrections_path)) if corrections_path else None
        # A name, never a path: the server decides where packs live (same rule as the voice and video folders).
        name = Path(str(params.get("name") or novel_id)).name
        pack_file = pack_dir / (name if name.endswith(packs.PACK_SUFFIX) else name + packs.PACK_SUFFIX)
        if job.kind == "pack_export":
            run_stage(
                store, run_id=pipeline_run.run_id, stage_name="pack_export",
                input_digest=f"{input_digest}|{time.time()}", skip_if_succeeded=False,
                fn=lambda: packs.export_pack(store, novel_id, pack_file, corrections=corrections_log),
            )
        else:
            if not pack_file.is_file():
                raise ValueError(f"no pack named {pack_file.name!r} in this project's packs folder")
            report = run_stage(
                store, run_id=pipeline_run.run_id, stage_name="pack_import",
                input_digest=f"{input_digest}|{time.time()}", skip_if_succeeded=False,
                fn=lambda: packs.import_pack(store, novel_id, pack_file, corrections_log=corrections_log),
            )
            # A Job row has no result column, and the Studio shows what an import applied and skipped. Kept beside the
            # pack (`GET .../packs` reads it), so the answer outlives the job card and a reload.
            if report is not None:
                pack_file.with_name(pack_file.name + ".report.json").write_text(
                    json.dumps(report.to_dict(), ensure_ascii=False), encoding="utf-8")
    elif job.kind == "companion":
        from echotales.pipeline import paths
        from echotales.pipeline.companion import build_companion, parse_through, site_dir_name, write_companion_site

        through = parse_through(params.get("through"))
        # The folder comes from the project and the chapter, never from the request.
        out = Path(paths.asset_dir(novel_id, "companion")) / site_dir_name(through)
        # Not skippable by digest: the book can have changed since an identical earlier request.
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="companion",
            input_digest=f"{input_digest}|{time.time()}", skip_if_succeeded=False,
            fn=lambda: write_companion_site(build_companion(store, novel_id, through), out),
        )
    elif job.kind == "refimg_search":
        from echotales.pipeline.persona import refimg

        novel_row = store.conn.execute(
            "SELECT title FROM novel WHERE id=?", (novel_id,)
        ).fetchone()
        title = novel_row["title"] if novel_row else novel_id
        self_ids = params.get("self_ids")
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="refimg_search",
            input_digest=input_digest,
            fn=lambda: refimg.search_batch(store, novel_id, title, self_ids=self_ids),
        )
    elif job.kind == "reference_gen":
        from echotales.pipeline.persona.reference_gen import generate_references
        from echotales.pipeline.compute import default_image_engine
        from echotales.pipeline.render.panels import get_engine

        engine_name = params.get("engine") or default_image_engine()
        if not http_engine_known(engine_name):
            raise ValueError(
                f"engine {engine_name!r} is not enabled over HTTP. Local: {sorted(ALLOWED_HTTP_ENGINES)}; a hosted engine only if ECHOTALES_IMAGE_PROVIDER selects it"
            )
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="reference_gen",
            input_digest=input_digest,
            fn=lambda: generate_references(
                novel_id, store,
                engine=get_engine(engine_name),
                seed=params.get("seed", 0),
            ),
        )
    else:
        raise ValueError(f"unknown job kind {job.kind!r} -- expected one of {JOB_KINDS}")

    return pipeline_run.run_id


def _finish_run(store: Store, job_id: str, status: StageStatus) -> None:
    """Close the bookkeeping run a non-pipeline job opened. Left RUNNING it read as live work forever; only a
    still-RUNNING row is touched, so a build run the pipeline job already finalised is left as it is."""
    job = store.get_job(job_id)
    if job is not None and job.run_id:
        store.transition_pipeline_run(job.run_id, StageStatus.RUNNING, status)


def run_job(store: Store, job: Job, params: dict[str, Any]) -> None:
    """Run one job to completion against an already-open `Store`, updating
    the `job` row throughout. Never raises -- a failure is recorded on the
    row (`FAILED`/`PARTIAL` + `error_summary`), matching `stage()`'s own
    "accurate record, not a quieter one" rule while still letting the
    worker thread move on to the next queued job. An interrupt is recorded
    INTERRUPTED and re-raised.

    The PENDING -> RUNNING claim is the first write: a job cancelled while it waited loses the claim
    and is not run."""
    if not store.transition_job(job.job_id, [JobStatus.PENDING], JobStatus.RUNNING, started_at=time.time()):
        log.info("job %s not run: it is no longer PENDING", job.job_id)
        return
    try:
        run_id = _dispatch(store, job, params)
    except PartialStageFailure as exc:
        store.transition_job(
            job.job_id, [JobStatus.RUNNING], JobStatus.PARTIAL, finished_at=time.time(),
            error_summary=f"{exc} (progress: {exc.progress})",
        )
        _finish_run(store, job.job_id, StageStatus.PARTIAL)
        log.warning("job %s partial: %s", job.job_id, exc)
        return
    except Exception as exc:
        store.transition_job(
            job.job_id, [JobStatus.RUNNING], JobStatus.FAILED, finished_at=time.time(),
            error_summary=str(exc),
        )
        _finish_run(store, job.job_id, StageStatus.FAILED)
        log.exception("job %s failed", job.job_id)
        return
    except BaseException as exc:
        store.transition_job(
            job.job_id, [JobStatus.RUNNING], JobStatus.INTERRUPTED, finished_at=time.time(),
            error_summary=f"interrupted: {type(exc).__name__}",
        )
        _finish_run(store, job.job_id, StageStatus.FAILED)
        raise
    store.transition_job(
        job.job_id, [JobStatus.RUNNING], JobStatus.SUCCEEDED, finished_at=time.time(), run_id=run_id,
    )
    _finish_run(store, job.job_id, StageStatus.SUCCEEDED)


@dataclass(slots=True)
class _QueueItem:
    job_id: str
    novel_id: str
    db_path: str
    params: dict[str, Any]


class JobQueue:
    """One daemon worker thread; jobs run strictly sequentially,
    process-wide, across every project -- see module docstring for why.

    The caller enqueues by `job_id` + `db_path` rather than a live `Store`
    or job object, so the worker thread can open its own connection
    (`store_factory`) rather than sharing one across threads.
    """

    def __init__(self, store_factory: Callable[[str], Store] = Store) -> None:
        self._store_factory = store_factory
        #: Called with the novel id after every job, so the server can drop its cached payload: it was
        #: invalidated at enqueue only, and a client then read the pre-job state until some other write.
        self.on_finished: Callable[[str], None] | None = None
        self._q: queue.Queue[_QueueItem] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def submit(self, *, job_id: str, novel_id: str, db_path: str, params: dict[str, Any]) -> None:
        self._q.put(_QueueItem(job_id=job_id, novel_id=novel_id, db_path=db_path, params=params))

    def _worker(self) -> None:
        while True:
            item = self._q.get()
            try:
                self._run_item(item)
            except Exception:
                log.exception("job worker crashed handling %s", item.job_id)
            finally:
                self._q.task_done()
                if self.on_finished is not None:
                    try:
                        self.on_finished(item.novel_id)
                    except Exception:
                        log.exception("on_finished failed for %s", item.job_id)

    def _run_item(self, item: _QueueItem) -> None:
        # `Store(path)` creates a database when none exists. A project deleted while its job waited would
        # come back as an empty file that the next server start registers as a phantom project.
        if item.db_path != ":memory:" and not Path(item.db_path).exists():
            log.error("job %s dropped: its database %s no longer exists", item.job_id, item.db_path)
            return
        store = self._store_factory(item.db_path)
        try:
            job = store.get_job(item.job_id)
            if job is None:
                log.error("queued job %s vanished from its own store", item.job_id)
                return
            run_job(store, job, item.params)
        finally:
            store.close()
