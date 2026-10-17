"""Reader-faithfulness check: does what the product shows at chapter k depend only on chapters <= k?

    echotales --db data/db/<novel>.db faithfulness --novel <novel> --cuts 5,10,20

The definition applied directly (docs/research/READER_FAITHFULNESS.md, the truncate-and-rebuild oracle of the
prefix-faithfulness audit, scripts/prefix_audit/audit.py): rebuild the persona stage on the whole volume and on a copy
truncated after chapter k, then compare what a reader at the end of chapter k is served by each --
`state_of` on every person's personas (traits, persona set) and the Read page's cast (`webview.build_reader_cast`).
Any difference is a fact that chapters after k changed, i.e. a spoiler or a look-ahead.

Scope, stated because the check cannot see past it: resolution is held fixed (stored mention targets are kept, as in
the audit's Amendment 1), so a look-ahead inside identity resolution is not measured here; and persona attributes are
rebuilt from scratch on both sides, so a stored whole-volume extraction is not compared either. Divergence is the
oracle: it misses a leak that happens to produce the same value from either prefix (the counterfactual-suffix test
measures that; EVOLUTION 4.103). Works on throwaway copies taken with the SQLite backup API; the source database is
opened read-only and never written.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import TargetKind
from echotales.core.models import DiscoursePosition
from echotales.core.state import StateResolver
from echotales.core.store import Store

#: Persona facts compared per person. `persona_set` is the set of persona ids bound to the self at the position.
COMPARED_KEYS = ("gender", "age_band", "register", "archetype", "big_five")


@dataclass(slots=True)
class CutResult:
    chapter: int
    people_compared: int
    persona_divergent: list[tuple[str, str]] = field(default_factory=list)  # (self id, key)
    cast_divergent: list[tuple[str, str]] = field(default_factory=list)  # (entity id, field)
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.persona_divergent and not self.cast_divergent

    def summary(self) -> str:
        verdict = "ok" if self.ok else "DIVERGES"
        return (
            f"ch{self.chapter}: {self.people_compared} people, {len(self.persona_divergent)} persona facts and "
            f"{len(self.cast_divergent)} cast fields differ from a book that ends here  [{verdict}]"
        )


@dataclass(slots=True)
class FaithfulnessReport:
    novel_id: str
    prefix_causal: bool
    cuts: list[CutResult]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.cuts)


def _snapshot(src: str, dst: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(str(dst) + suffix).unlink(missing_ok=True)
    # The canonical databases carry live -wal files: a plain file copy can miss committed pages.
    source = sqlite3.connect(f"file:{Path(src).resolve()}?mode=ro", uri=True)
    out = sqlite3.connect(dst)
    with out:
        source.backup(out)
    out.close()
    source.close()


def _rebuild(src: Path, dst: Path, novel_id: str, upto: int | None, prefix_causal: bool) -> Store:
    from echotales.pipeline.persona import build_personas

    shutil.copy(src, dst)
    con = sqlite3.connect(dst)
    if upto is not None:
        for table, col in (("chapter", "number"), ("span", "chapter"), ("mention", "chapter"),
                           ("narrative_segment", "chapter_from")):
            con.execute(f"DELETE FROM {table} WHERE novel_id=? AND {col} > ?", (novel_id, upto))
    con.execute("DELETE FROM attribute WHERE novel_id=?", (novel_id,))
    con.execute("DELETE FROM persona WHERE novel_id=?", (novel_id,))
    con.commit()
    con.close()
    store = Store(str(dst))
    build_personas(novel_id, store, prefix_causal=prefix_causal)
    store.conn.commit()
    return store


def _reader_state(store: Store, novel_id: str, k: int) -> dict[str, dict]:
    resolver = StateResolver(store, novel_id)
    known = DiscoursePosition(chapter=k, offset=10**6)
    out = {}
    for s in store.all_selves(novel_id):
        if not s.kind.is_person:
            continue
        state = resolver.state_of(s.id, position=k + 0.5, knowledge_pos=known)
        facts: dict[str, object] = {"persona_set": tuple(sorted(state.persona_ids))}
        for pid in sorted(state.persona_ids):
            attrs = resolver.state_of(
                pid, target_kind=TargetKind.PERSONA, position=k + 0.5, knowledge_pos=known
            ).attributes
            for key in COMPARED_KEYS:
                if key in attrs:
                    facts[f"{key}@{pid}"] = attrs[key]
        out[s.id] = facts
    return out


def _cast(store: Store, novel_id: str, k: int) -> dict[str, dict]:
    from echotales.pipeline.webview import build_reader_cast

    # Colour is a whole-volume ranking by design (stable highlights), not reader content.
    return {e["id"]: {f: v for f, v in e.items() if f != "colour"} for e in build_reader_cast(store, novel_id, k)["entities"]}


def check_reader_faithfulness(
    db_path: str,
    novel_id: str,
    cuts: list[int],
    *,
    work_dir: Path,
    prefix_causal: bool = True,
) -> FaithfulnessReport:
    work_dir.mkdir(parents=True, exist_ok=True)
    src = work_dir / "source.db"
    _snapshot(db_path, src)
    full = _rebuild(src, work_dir / "full.db", novel_id, None, prefix_causal)
    results = []
    try:
        for k in cuts:
            t0 = time.time()
            cut = _rebuild(src, work_dir / f"cut{k}.db", novel_id, k, prefix_causal)
            try:
                a, b = _reader_state(full, novel_id, k), _reader_state(cut, novel_id, k)
                both = sorted(set(a) & set(b))
                persona: list[tuple[str, str]] = []
                for sid in both:
                    if a[sid]["persona_set"] != b[sid]["persona_set"]:
                        # Traits are keyed by persona id, so a different body set would also list every trait.
                        persona.append((sid, "persona_set"))
                        continue
                    persona += [(sid, key) for key in sorted(set(a[sid]) | set(b[sid])) if a[sid].get(key) != b[sid].get(key)]
                ca, cb = _cast(full, novel_id, k), _cast(cut, novel_id, k)
                cast: list[tuple[str, str]] = []
                for eid in sorted(set(ca) | set(cb)):
                    if eid not in ca or eid not in cb:
                        cast.append((eid, "present"))
                        continue
                    cast += [(eid, f) for f in sorted(set(ca[eid]) | set(cb[eid])) if ca[eid].get(f) != cb[eid].get(f)]
            finally:
                cut.close()
            results.append(CutResult(k, len(both), persona, cast, round(time.time() - t0, 2)))
    finally:
        full.close()
    return FaithfulnessReport(novel_id, prefix_causal, results)
