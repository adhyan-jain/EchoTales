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

import logging
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from echotales.core.models import Job, StageStatus
from echotales.core.pipeline_run import (
    PartialStageFailure,
    digest_text,
    ensure_pipeline_run,
    finish_stage,
    start_stage,
)
from echotales.core.store import Store

log = logging.getLogger(__name__)

#: HTTP-triggered generation jobs never reach a paid API -- gemini/openrouter
#: stay CLI-only, operated by a human who opts in each time via the
#: existing `--image-engine` flag (approved plan, Product Orchestration
#: track: "Do not spend money"). Any other engine name a caller passes is a
#: 400, not a silent downgrade to stub -- a wrong request should look wrong,
#: not quietly succeed as something else.
ALLOWED_HTTP_ENGINES = frozenset(
    {"stub", "sdxl", "illustrious", "noobai", "refined", "manga"}
)

#: The set of job kinds this module knows how to run. Mirrors the CLI's own
#: subcommand granularity (`cli.py`'s `ingest`/`resolve`/`persona`/
#: `appearance`/`render`/`voice`/`refimg-search`) rather than inventing a
#: different breakdown -- an HTTP-triggered `resolve` job behaves exactly
#: like `echotales resolve`, including that command's existing prerequisite
#: assumptions (segment/mentions/speakers/anaphora already having run,
#: normally via `echotales run` or their own prior jobs).
JOB_KINDS = (
    "ingest",
    "resolve",
    "appearance",
    "persona",
    "render",
    "voice",
    "refimg_search",
    "reference_gen",
)


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
    finish_stage(store, handle, status=StageStatus.SUCCEEDED)
    return result


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
    pipeline_run = ensure_pipeline_run(store, novel_id=novel_id, source_digest=source_digest)
    input_digest = digest_text(f"{source_digest}|{job.kind}|v1|{job.params_json}")

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

    if job.kind == "ingest":
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
        from echotales.pipeline.persona import build_personas

        client = None
        if params.get("use_llm"):
            from echotales.pipeline.llm.client import ModelClient

            client = ModelClient(store=store)
            client.require_ready()
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="persona",
            input_digest=input_digest,
            fn=lambda: build_personas(novel_id, store, client=client),
        )
    elif job.kind == "render":
        from echotales.pipeline.render.panels import get_engine, render_panels
        from echotales.pipeline import paths

        engine_name = params.get("engine", "stub")
        if engine_name not in ALLOWED_HTTP_ENGINES:
            raise ValueError(
                f"engine {engine_name!r} is not allowed over HTTP -- paid engines "
                "(gemini/openrouter) are CLI-only. Allowed: "
                f"{sorted(ALLOWED_HTTP_ENGINES)}"
            )
        chapters = params.get("chapters")
        out_dir = params.get("panel_dir") or str(paths.asset_dir(novel_id, "panels"))
        run_stage(
            store, run_id=pipeline_run.run_id, stage_name="render",
            input_digest=input_digest,
            fn=lambda: render_panels(
                novel_id, store,
                out_dir=out_dir,
                engine=get_engine(engine_name),
                chapters=chapters,
                seed=params.get("seed", 20260812),
            ),
        )
    elif job.kind == "voice":
        from echotales.pipeline.voice import get_engine as get_voice_engine, load_vctk, render_novel
        from echotales.pipeline import paths

        engine_name = params.get("engine", "stub")
        # Same bank selection as `cmd_voice`; the HTTP job path hardcoded VCTK
        # and so could never use an emotion-capable bank.
        from echotales.pipeline.voice.bank import load_cremad, load_ears

        bank_root = params.get("bank", "data/voice")
        bank_kind = params.get("bank_kind", "vctk")
        if bank_kind == "ears":
            bank = load_ears(bank_root)
        elif bank_kind == "cremad":
            bank = load_cremad(bank_root)
        else:
            bank = load_vctk(bank_root)
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
            ),
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
        from echotales.pipeline.render.panels import get_engine

        engine_name = params.get("engine", "stub")
        if engine_name not in ALLOWED_HTTP_ENGINES:
            raise ValueError(
                f"engine {engine_name!r} is not allowed over HTTP -- paid engines "
                "(gemini/openrouter) are CLI-only. Allowed: "
                f"{sorted(ALLOWED_HTTP_ENGINES)}"
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


def run_job(store: Store, job: Job, params: dict[str, Any]) -> None:
    """Run one job to completion against an already-open `Store`, updating
    the `job` row throughout. Never raises -- a failure is recorded on the
    row (`FAILED`/`PARTIAL` + `error_summary`), matching `stage()`'s own
    "accurate record, not a quieter one" rule while still letting the
    worker thread move on to the next queued job."""
    store.update_job(job.job_id, status=StageStatus.RUNNING, started_at=time.time())
    try:
        run_id = _dispatch(store, job, params)
    except PartialStageFailure as exc:
        store.update_job(
            job.job_id, status=StageStatus.PARTIAL, finished_at=time.time(),
            error_summary=f"{exc} (progress: {exc.progress})",
        )
        log.warning("job %s partial: %s", job.job_id, exc)
        return
    except Exception as exc:
        store.update_job(
            job.job_id, status=StageStatus.FAILED, finished_at=time.time(),
            error_summary=str(exc),
        )
        log.exception("job %s failed", job.job_id)
        return
    store.update_job(
        job.job_id, status=StageStatus.SUCCEEDED, finished_at=time.time(), run_id=run_id,
    )


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
                store = self._store_factory(item.db_path)
                try:
                    job = store.get_job(item.job_id)
                    if job is None:
                        log.error("queued job %s vanished from its own store", item.job_id)
                        continue
                    run_job(store, job, item.params)
                finally:
                    store.close()
            except Exception:
                log.exception("job worker crashed handling %s", item.job_id)
            finally:
                self._q.task_done()
