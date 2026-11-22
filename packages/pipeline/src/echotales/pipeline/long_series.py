"""Long series: rebuild only what an edited chapter touches, and say what a run will cost before it starts.

The build stages key their cache on the whole EPUB digest (`jobs._run_pipeline`), so correcting one chapter
re-ran every stage over every chapter. Here each chapter's text gets its own hash; a changed hash names exactly the
chapter-scoped products (panels, audio, video) to rebuild, and the stages that read the whole volume as a group.

The estimate reads the durations the job queue already records in `stage_run`; a stage never run on this database
falls back to `DEFAULT_SECONDS_PER_CHAPTER`, and says so.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from echotales.core.models import Chapter
from echotales.core.store import Store

#: Chapter-scoped output folders under `data/novels/<CODE>/<kind>/ch<N>/` (`paths.asset_dir`).
PRODUCT_KINDS = ("panels", "audio", "video", "pages")

#: Stages that read every chapter (identity, reader facts, personas): a changed chapter makes them stale as a group,
#: because an alias revealed in chapter 40 changes who chapter 3 was about.
VOLUME_STAGES = ("6 resolve", "6b reader", "7 personas", "7a gender", "7b appearance")

_BASELINE = "chapterhash"
_STALE = "stale"

#: Seconds per chapter for a stage this database has never timed. Unmeasured planning figures for a single consumer
#: GPU (a 7B local model, one diffusion model, one TTS model), kept deliberately round; every figure that comes from
#: here is reported with basis "estimate" so nobody mistakes it for a measurement.
DEFAULT_SECONDS_PER_CHAPTER: dict[str, float] = {
    "0 ingest": 1.0,
    "2 segment": 1.0,
    "3 mentions": 20.0,
    "4 speakers": 20.0,
    "5 anaphora": 5.0,
    "6 resolve": 10.0,
    "6b reader": 120.0,
    "7 personas": 15.0,
    "7a gender": 5.0,
    "7b appearance": 60.0,
    "render": 600.0,
    "voice": 900.0,
    "video": 120.0,
}
DEFAULT_STAGES = tuple(DEFAULT_SECONDS_PER_CHAPTER)


def chapter_hash(chapter: Chapter) -> str:
    h = hashlib.sha256()
    for b in chapter.blocks:
        h.update(f"{b.block_type.value}\x1f{b.text}\x1e".encode())
    return h.hexdigest()


def chapter_ref(novel_id: str, chapter: float) -> str:
    """The read-set entry an artifact lists when it consulted this chapter (`core/readset.py::fact_ref`)."""
    return f"chapter:{novel_id}:{chapter:g}"


def chapter_dirname(chapter: float) -> str:
    return f"ch{chapter:g}"


def _current_hashes(store: Store, novel_id: str) -> dict[float, str]:
    return {c.number: chapter_hash(c) for c in store.iter_chapters(novel_id)}


def _baseline_hashes(store: Store, novel_id: str) -> dict[float, str]:
    prefix = f"{_BASELINE}:{novel_id}:"
    rows = store.conn.execute("SELECT id, payload_json FROM derived_artifact WHERE id LIKE ?", (prefix + "%",))
    return {float(r["id"][len(prefix):]): r["payload_json"] for r in rows}


def record_baseline(store: Store, novel_id: str) -> None:
    """Remember each chapter's hash as the text the current products were built from; clears stale marks.

    Stored as `derived_artifact` rows with an empty read set so `invalidate_by_facts` can never invalidate the
    baseline itself.
    """
    for number, digest in _current_hashes(store, novel_id).items():
        store.record_artifact(f"{_BASELINE}:{novel_id}:{number:g}", "TEXT", [], digest, digest)
    store.conn.execute("DELETE FROM derived_artifact WHERE id LIKE ?", (f"{_STALE}:{novel_id}:%",))
    store.conn.commit()


def changed_chapters(store: Store, novel_id: str) -> list[float]:
    """Chapters whose text differs from the baseline. Empty when no baseline was ever recorded: nothing to compare."""
    baseline = _baseline_hashes(store, novel_id)
    if not baseline:
        return []
    return sorted(n for n, h in _current_hashes(store, novel_id).items() if baseline.get(n) != h)


@dataclass(frozen=True, slots=True)
class Product:
    name: str  # "panels/ch2"
    path: Path


@dataclass(slots=True)
class StaleReport:
    chapters: list[float] = field(default_factory=list)
    products: dict[float, list[Product]] = field(default_factory=dict)
    volume_stages: tuple[str, ...] = ()
    artifacts_invalidated: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapters": self.chapters,
            "products": {f"{c:g}": [p.name for p in ps] for c, ps in self.products.items()},
            "volume_stages": list(self.volume_stages),
            "artifacts_invalidated": self.artifacts_invalidated,
        }


def _existing_products(novel_id: str, chapter: float, data_root: Path | str | None) -> list[Product]:
    from echotales.pipeline import paths

    out = []
    for kind in PRODUCT_KINDS:
        d = paths.asset_dir(novel_id, kind, data_root=data_root or paths.DATA_ROOT) / chapter_dirname(chapter)
        if d.is_dir():
            out.append(Product(f"{kind}/{chapter_dirname(chapter)}", d))
    return out


def invalidate_changed(store: Store, novel_id: str, *, data_root: Path | str | None = None) -> StaleReport:
    """Mark the products of every changed chapter stale, and only those. Nothing on disk is deleted.

    Versioned render folders are history a reviewer may still want to compare (`paths.next_version`), so staleness
    is a record the next run reads, not a removal.
    """
    changed = changed_chapters(store, novel_id)
    report = StaleReport(chapters=changed, volume_stages=VOLUME_STAGES if changed else ())
    for n in changed:
        report.products[n] = _existing_products(novel_id, n, data_root)
        store.record_artifact(
            f"{_STALE}:{novel_id}:{n:g}", "TEXT", [], "", json.dumps([p.name for p in report.products[n]])
        )
    report.artifacts_invalidated = store.invalidate_by_facts([chapter_ref(novel_id, n) for n in changed])
    store.conn.commit()
    return report


def stale_products(store: Store, novel_id: str) -> list[tuple[float, list[str]]]:
    prefix = f"{_STALE}:{novel_id}:"
    rows = store.conn.execute("SELECT id, payload_json FROM derived_artifact WHERE id LIKE ?", (prefix + "%",))
    return sorted((float(r["id"][len(prefix):]), json.loads(r["payload_json"])) for r in rows)


# --- time and cost estimate -------------------------------------------------


def select_chapters(available: list[float], spec: str | None) -> list[float]:
    if not spec:
        return list(available)
    from echotales.pipeline.ingest.adapters import ChapterRange

    rng = ChapterRange.parse(spec)
    return [n for n in available if n in rng]


def _measured_seconds_per_chapter(store: Store, novel_id: str, stage: str, total_chapters: int) -> float | None:
    """Median seconds per chapter over this database's finished runs of `stage`.

    A run's chapter count is the range its job was asked for; a run with no range (the whole-book `pipeline` job)
    covered every chapter the book has now, which understates the rate for a book that has grown since.
    """
    rows = store.conn.execute(
        "SELECT sr.started_at, sr.finished_at, j.params_json FROM stage_run sr"
        " JOIN pipeline_run pr ON pr.run_id = sr.run_id"
        " LEFT JOIN job j ON j.run_id = sr.run_id"
        " WHERE pr.novel_id=? AND sr.stage_name=? AND sr.status='SUCCEEDED' AND sr.finished_at IS NOT NULL",
        (novel_id, stage),
    ).fetchall()
    rates = []
    for r in rows:
        seconds = r["finished_at"] - r["started_at"]
        spec = json.loads(r["params_json"] or "{}").get("chapters") if r["params_json"] else None
        count = len(select_chapters([c for c in store.chapter_numbers(novel_id)], spec)) if spec else total_chapters
        if seconds > 0 and count > 0:
            rates.append(seconds / count)
    return statistics.median(rates) if rates else None


def source_chapter_numbers(sources_path: str | Path, novel_id: str) -> list[float]:
    """Chapter numbers the novel's source would ingest, parsed from the EPUB without touching the store. Empty when
    there is no source or it cannot be read: the estimate then says it is unknown rather than guessing."""
    from echotales.pipeline.ingest.sources import get_source

    try:
        config = get_source(novel_id, sources_path)
        epub, adapter = config.open_adapter()
        try:
            return [c.number for c in adapter.chapters(config.chapters)]
        finally:
            epub.close()
    except Exception:  # an unreadable source is "unknown", not an error on the estimate path
        return []


def estimate_run(
    store: Store,
    novel_id: str,
    chapters: str | None,
    *,
    stages: tuple[str, ...] = DEFAULT_STAGES,
    gpu_hourly_usd: float = 0.0,
    source_chapters: list[float] | None = None,
) -> dict[str, Any]:
    """Seconds (and dollars at `gpu_hourly_usd`; a local run costs nothing per run) for `stages` over `chapters`.

    Before the first ingest the store has no chapters, so a new book read `chapters: 0` and 0 s for every stage (P&P
    e2e): `source_chapters` (the uploaded EPUB's chapters) stands in for them, and with neither the result says
    `known: False` and carries no numbers rather than a confident zero."""
    available = store.chapter_numbers(novel_id) or list(source_chapters or [])
    if not available:
        return {
            "novel_id": novel_id, "known": False, "chapters": None, "seconds": None, "cost_usd": None,
            "measured": False,
            "stages": [
                {"stage": s, "chapters": None, "seconds_per_chapter": None, "seconds": None, "basis": "unknown"}
                for s in stages
            ],
            "note": "unknown until ingest: the book has no chapters in this project yet and no readable source",
        }
    count = len(select_chapters(available, chapters))
    rows = []
    for stage in stages:
        measured = _measured_seconds_per_chapter(store, novel_id, stage, len(available))
        per = measured if measured is not None else DEFAULT_SECONDS_PER_CHAPTER.get(stage, 60.0)
        rows.append({
            "stage": stage, "chapters": count, "seconds_per_chapter": per, "seconds": per * count,
            "basis": "measured" if measured is not None else "estimate",
        })
    total = sum(r["seconds"] for r in rows)
    return {
        "novel_id": novel_id,
        "known": True,
        "chapters": count,
        "stages": rows,
        "seconds": total,
        "cost_usd": total / 3600.0 * gpu_hourly_usd,
        "measured": all(r["basis"] == "measured" for r in rows),
        "note": "stages marked estimate use unmeasured default figures; measured ones are medians of earlier runs here",
    }


def format_estimate(est: dict[str, Any]) -> str:
    if not est.get("known", True):
        return f"estimate for {est['novel_id']}: unknown ({est['note']})"
    lines = [f"estimate for {est['novel_id']}, {est['chapters']} chapter(s)"]
    for r in est["stages"]:
        lines.append(
            f"  {r['stage']:<16} {r['seconds'] / 60:8.1f} min   ({r['seconds_per_chapter']:.1f} s/chapter, {r['basis']})"
        )
    lines.append(f"  {'TOTAL':<16} {est['seconds'] / 3600:8.2f} h     cost ${est['cost_usd']:.2f}"
                 + ("" if est["measured"] else "   (includes estimates)"))
    return "\n".join(lines)
