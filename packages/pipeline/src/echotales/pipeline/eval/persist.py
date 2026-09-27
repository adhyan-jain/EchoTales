"""Persist an evaluation run so a reported number can be traced to one.

COMPLETION_PLAN Track 2 item 10. `core/pipeline_run.py` was fully built --
`ensure_pipeline_run`, `stage`, `record_artifact` -- with **zero callers**
outside `cmd_run` (EVOLUTION 4.72). Meanwhile every number this project ever
quoted existed only in a terminal, which is how 4.74 could take two months to
notice that a published B-cubed figure had been computed against a gold file
that was later edited: there was no record of which file, which database, or
which code produced it.

This writes a results directory per eval run and registers it as a
`StageArtifact`, so "where did 97.2% come from" has an answer that is not
somebody's memory.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from echotales.core.models import StageStatus
from echotales.core.pipeline_run import (
    digest_text,
    ensure_pipeline_run,
    finish_stage,
    record_artifact,
    start_stage,
)
from echotales.core.store import Store

#: Overridable by `ECHOTALES_EVAL_ROOT` for the same reason as
#: `compounding.curve_root` -- a fixed repo path cannot be exercised
#: by a test without leaving a directory behind.
DEFAULT_RESULTS_ROOT = Path("data/eval/results")


def results_root() -> Path:
    env = os.environ.get("ECHOTALES_EVAL_ROOT", "")
    return Path(env) / "results" if env else DEFAULT_RESULTS_ROOT


def _git_commit() -> str:
    """The commit the numbers came from, or a marker that it is unknown.

    Not fatal when absent: a checkout without git still produces valid
    results, and refusing to write them would be worse than recording
    "unknown".
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        commit = out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if not commit:
        return "unknown"
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    ).stdout.strip()
    # The dirty marker matters more than the hash here: this repository's
    # numbers have been produced from an uncommitted tree for most of its
    # life, and a bare hash would imply a reproducibility it does not have.
    return f"{commit}-dirty" if dirty else commit


def persist_eval(
    store: Store,
    novel_id: str,
    *,
    metrics: dict[str, Any],
    report_text: str = "",
    gold_path: str = "",
    seed: int = 0,
    root: Path | None = None,
) -> Path:
    """Write `<root>/<run_id>/` and register it against a `pipeline_run`.

    The `run_id` keys off the *database* rather than the source EPUB: an eval
    scores whatever a database contains, the source text may not even be
    present in a checkout (`data/raw/` is gitignored), and pretending the
    novel file identified the run would attach results to something that was
    never read.
    """
    db_path = Path(getattr(store, "path", "") or "unknown.db")
    digest = digest_text(f"{db_path.resolve()}|{db_path.stat().st_size if db_path.exists() else 0}")
    run = ensure_pipeline_run(store, novel_id=novel_id, source_digest=digest)

    if root is None and not os.environ.get("ECHOTALES_EVAL_ROOT") and not getattr(store, "is_canonical", False):
        # A scratch database's scores are experiments, not results: they went
        # to data/eval/results/ beside the canonical runs, and the paper
        # generator's "newest run" then cited a scratch database as Table 4's
        # source (2026-09-27). Same rule as the compounding curves.
        root = Path("data/scratch/eval/results")
    out_dir = (root or results_root()) / run.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "run_id": run.run_id,
        "novel_id": novel_id,
        "database": str(db_path),
        "gold_path": gold_path,
        "seed": seed,
        "git_commit": _git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "written_at": time.time(),
        "metrics": metrics,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    if report_text:
        (out_dir / "report.txt").write_text(report_text, encoding="utf-8")

    handle = start_stage(
        store,
        run_id=run.run_id,
        stage_name="eval",
        input_digest=digest_text(f"{digest}|eval|{gold_path}|{seed}"),
    )
    record_artifact(
        store,
        stage_run_id=handle.stage_run.stage_run_id,
        kind="eval_results",
        path_or_ref=str(out_dir),
        content_digest=digest_text(json.dumps(metrics, sort_keys=True, default=str)),
    )
    finish_stage(store, handle, status=StageStatus.SUCCEEDED)
    store.conn.commit()
    return out_dir
