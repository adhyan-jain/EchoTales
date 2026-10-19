"""Shared helpers for the engineering-invariant probes (E1-E6). New file; imports existing code unchanged.

LABEL PROVENANCE: every probe built on these helpers is SYSTEM-INTERNAL (no reference labels) or SYNTHETIC (labels by
construction). CPU only; no LLM, no network, no GPU. Scratch copies only; no novel text is ever written, only ids,
chapter numbers and counts.
"""

from __future__ import annotations

import os
import shutil
import time
import zlib
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"

SCRATCH = Path("/tmp/claude-1000/-home-adhyan-Desktop-EchoTales/cc27fc62-24e6-4508-8f1c-359e03379db1/scratchpad")
REPO = Path(__file__).resolve().parents[2]
DBS = {
    "reverend-insanity": SCRATCH / "ri_copy.db",
    "lord-of-the-mysteries": SCRATCH / "lord-of-the-mysteries.copy.db",
    "omniscient-readers-viewpoint": SCRATCH / "omniscient-readers-viewpoint.copy.db",
}

from echotales.core.store import Store  # noqa: E402
from echotales.pipeline.config import Settings  # noqa: E402
from echotales.pipeline.ingest.adapters.base import ChapterRange  # noqa: E402
from echotales.pipeline.ingest.sources import get_source  # noqa: E402
from echotales.pipeline.mentions.induce import load_or_seed  # noqa: E402
from echotales.pipeline.resolve import resolve_novel  # noqa: E402


def fresh_copy(src: Path, workdir: Path, name: str) -> str:
    """A throwaway copy; the source scratch DB is never opened for writing."""
    workdir.mkdir(parents=True, exist_ok=True)
    dst = workdir / f"{name}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(dst) + suffix).unlink(missing_ok=True)
    shutil.copy(src, dst)
    return str(dst)


def _no_curve_write() -> None:
    # A scratch re-resolve must not touch data/scratch/eval/compounding (an existing file).
    import echotales.pipeline.eval.compounding as C

    C.record_resolution_half = lambda *a, **k: None  # type: ignore[assignment]


def run_resolve(
    db_path: str,
    nid: str,
    *,
    chapters: ChapterRange | None = None,
    window_size: int | None = None,
    volume_passes: bool = False,
    causal_titles: bool = False,
    chapter_order: list[float] | None = None,
) -> dict:
    """Resolve the stored mentions of one novel in a scratch DB and return a plain-data snapshot.

    `volume_passes=True` with `chapters` given keeps the title-holder / transmigration passes (prefix_volume_passes).
    `chapter_order` permutes the order in which chapters are fed to the loop (instance-level patch of
    Store.iter_chapters; no source file changed).
    """
    _no_curve_write()
    store = Store(db_path)
    cfg = Settings(_env_file=None)  # defaults only: .env is deliberately not read by this script
    if window_size is not None:
        cfg = cfg.model_copy(update={"window_size": window_size})
    if chapter_order is not None:
        by_num = {c.number: c for c in store.iter_chapters(nid)}
        ordered = [by_num[n] for n in chapter_order if n in by_num]
        store.iter_chapters = lambda _nid, _o=ordered: iter(_o)  # type: ignore[method-assign]
    lex = load_or_seed(get_source(nid).lexicon)
    t0 = time.time()
    report = resolve_novel(
        nid, store, lexicon=lex, settings=cfg, force_rewipe=True, chapters=chapters,
        prefix_volume_passes=volume_passes, causal_titles=causal_titles,
    )
    snap = snapshot(store, nid)
    snap["seconds"] = round(time.time() - t0, 1)
    snap["report"] = dict(
        groups=report.groups, linked=report.linked, created=report.created, deferred=report.deferred,
        recovered=report.recovered_from_deferral, unresolved=report.unresolved, entities=report.entities,
        by_window={int(k): dict(v) for k, v in report.link_method_by_window.items()},
    )
    store.close()
    return snap


def snapshot(store: Store, nid: str) -> dict:
    ments = store.get_mentions(nid)
    return dict(
        mentions={
            m.id: (float(m.chapter), m.target_id, m.method.value if m.method else None, m.block_index, m.offset)
            for m in ments
        },
        aliases=[
            (b.target_id, b.alias_type.value, b.learned_at_pos.chapter, b.learned_at_pos.offset,
             zlib.crc32(b.alias.lower().encode()), b.observer_id)
            for b in store.all_aliases(nid)
        ],
    )


def partition_diff(var: dict, ref: dict) -> dict:
    """Id-free comparison of two resolutions of the same mentions.

    Each variant cluster is mapped to the reference cluster holding most of its members; a mention is *moved* when its
    reference cluster differs from that majority image. Computed in both directions and reported as the larger count so
    a split and a merge are both visible. Unlinked mentions are not counted as moved (they have no cluster); the
    number of mentions linked in only one of the two runs is reported separately.
    """
    from collections import Counter

    vm, rm = var["mentions"], ref["mentions"]
    ids = [i for i in vm if i in rm]
    link_only_var = sum(1 for i in ids if vm[i][1] and not rm[i][1])
    link_only_ref = sum(1 for i in ids if rm[i][1] and not vm[i][1])
    both = [i for i in ids if vm[i][1] and rm[i][1]]

    def one_way(a: dict, b: dict) -> tuple[int, set]:
        cont: dict = {}
        for i in both:
            cont.setdefault(a[i][1], Counter())[b[i][1]] += 1
        major = {c: cnt.most_common(1)[0][0] for c, cnt in cont.items()}
        moved = {i for i in both if b[i][1] != major[a[i][1]]}
        return len(moved), moved

    n1, s1 = one_way(vm, rm)
    n2, s2 = one_way(rm, vm)
    return dict(
        both_linked=len(both), moved_var_to_ref=n1, moved_ref_to_var=n2, moved_max=max(n1, n2),
        moved_rate_max=round(max(n1, n2) / len(both), 5) if both else None,
        linked_only_in_variant=link_only_var, linked_only_in_reference=link_only_ref,
        moved_mention_ids_sample=sorted(s1 | s2)[:25],
        moved_by_chapter=dict(sorted(Counter(int(vm[i][0]) for i in (s1 | s2)).items())),
    )
