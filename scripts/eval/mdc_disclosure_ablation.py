"""Does the Minimal Disclosure Compiler (`core/disclosure.py`) reduce evidence
beyond what observer filtering already does, without leaking anything new?

Pre-registered rules (fixed here, in code, before any number was computed):

  Targets (render)   the 15 most-mentioned Selves in `reverend-insanity.db`
                      that have a `self_persona_binding` row (all of the top
                      20 do, checked directly against the real database
                      before writing this harness).
  Positions (render)  chapters 20, 100, 190 -- early/mid/late in a 199-chapter
                      volume, story position = knowledge position (READER).
  Conditions          FULL     -- every distinct fact in the store for the
                                  target, ignoring observer/temporal/task
                                  filtering entirely (the true upper bound).
                      TOPK     -- `world/context.py::_ranked` applied to the
                                  observer-valid candidate's attributes (the
                                  one capped-truncation mechanism already
                                  shipped in this codebase); aliases and
                                  relationships are untouched by that
                                  mechanism, so it caps attributes only.
                      OBSERVER -- `compile_generation_state` unmodified,
                                  today's production behavior for render.
                      MDC      -- `compile_minimal_disclosure` with
                                  `plan_builder.RENDER_TASK_SPEC`.
  Metric              evidence_count = |aliases| + |attributes| + |relations|
                      selected under each condition; evidence_reduction_pct
                      = 1 - MDC/OBSERVER (the correct baseline per the
                      approved plan: FULL vs OBSERVER is the already-measured
                      observer-filter effect from `observer_ablation.py`, not
                      this module's contribution).

  A confound found while building this harness, reported rather than
  papered over: `reverend-insanity.db` has **zero** SELF-kind attribute rows
  and **zero** relation rows (checked directly: `SELECT count(*) FROM
  attribute WHERE target_kind='SELF'` -> 0; `SELECT count(*) FROM relation`
  -> 0). `world/schema.py`'s own docstring already documents this gap for
  LOCATION/ORGANIZATION/ITEM; it turns out SELF-kind extraction against
  `PERSON_KEYS` (role/faction/status/...) was never run against this
  database either. The render experiment below is real and honestly
  measured, but on this corpus its entire "evidence" surface for a SELF
  target is aliases -- attributes/relationships are 0 in every condition
  because there is nothing in the graph to select from, not because MDC
  did anything. That is itself a reportable finding (see the write-up), not
  a limitation of this script.

  Because the real corpus cannot exercise the attribute/relationship
  coverage-plus-dependency-closure machinery at all, a second experiment
  (`dialogue_brief`) runs against a small, explicitly synthetic in-memory
  fixture built in this file -- populated with the role/faction/status/
  relationship facts the real database lacks -- to test the mechanism this
  script exists to evaluate. Per the user's own instruction ("use synthetic
  adversarial cases where real corpus coverage is missing"), this is stated
  plainly rather than silently substituted.

  A third experiment (`cast_naming`) runs multiple simultaneous top-mentioned
  Selves through one MDC batch call on the real corpus, to exercise the one
  mechanism real data *can* test: cross-cast alias disambiguation
  (`disclosure.py::_disambiguating_aliases`).

Usage:
    python3 scripts/eval/mdc_disclosure_ablation.py [--db data/db/reverend-insanity.db]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from echotales.core.disclosure import TaskSpec, compile_minimal_disclosure
from echotales.core.enums import OBSERVER_READER, AliasType, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    AliasBinding,
    Attribute,
    DiscoursePosition,
    Persona,
    Relation,
    Self,
    SelfPersonaBinding,
)
from echotales.core.readset import EpistemicLeakageValidator
from echotales.core.state import StateResolver, compile_generation_state
from echotales.core.store import Store
from echotales.pipeline.render.plan_builder import RENDER_TASK_SPEC
from echotales.pipeline.world.context import _ranked

NOVEL = "reverend-insanity"
N_TARGETS = 15
POSITIONS = (20.0, 100.0, 190.0)


def _full_context(store: Store, target_id: str) -> dict[str, int]:
    """Every distinct fact in the store for this target, no filtering at all."""
    aliases = {a.alias.casefold() for a in store.get_aliases_for(TargetKind.SELF, target_id)}
    attrs = {(a.key, a.value) for a in store.get_attributes(TargetKind.SELF, target_id)}
    rels = {(r.type, r.dst_self) for r in store.get_relations(target_id) if r.src_self == target_id}
    return {"aliases": len(aliases), "attributes": len(attrs), "relationships": len(rels)}


def _topk_baseline(resolver: StateResolver, target_id: str, position: float) -> dict[str, int]:
    """`world/context.py::_ranked` applied to the observer-valid candidate's
    attributes -- the one capped-truncation mechanism already shipped here.
    It does not touch aliases or relationships at all (that module never
    emits either into its brief), so this condition reports the candidate's
    full alias/relationship counts alongside the capped attribute count --
    an honest reflection of what that mechanism actually limits, not a
    claim that it limits everything.
    """
    obs_res = resolver.state_of(target_id, position=position)
    capped = _ranked(dict(obs_res.attributes), TargetKind.SELF)
    return {
        "aliases": len(obs_res.aliases),
        "attributes": len(capped),
        "relationships": len(obs_res.relationships),
    }


def _observer_filtered(store: Store, target_id: str, position: float) -> dict[str, Any]:
    gen = compile_generation_state(store, NOVEL, [target_id], position=position)
    t = gen.target(target_id)
    counts = {
        "aliases": len([f for f in gen.allowed_facts if f.startswith("alias:")]),
        "attributes": len(t.self_attributes) if t else 0,
        "relationships": len([f for f in gen.allowed_facts if f.startswith("rel:")]),
    }
    return {"counts": counts, "state": gen}


def _mdc(store: Store, target_id: str, position: float) -> dict[str, Any]:
    result = compile_minimal_disclosure(
        store, NOVEL, [target_id], RENDER_TASK_SPEC, position=position,
    )
    t = result.state.target(target_id)
    counts = {
        "aliases": len([f for f in result.state.allowed_facts if f.startswith("alias:")]),
        "attributes": len(t.self_attributes) if t else 0,
        "relationships": len([f for f in result.state.allowed_facts if f.startswith("rel:")]),
    }
    return {"counts": counts, "result": result}


def run_render_experiment(store: Store) -> dict[str, Any]:
    conn = store.conn
    top = [
        r[0] for r in conn.execute(
            "SELECT target_id FROM mention WHERE target_id LIKE ? "
            "GROUP BY target_id ORDER BY count(*) DESC LIMIT ?",
            (f"{NOVEL}:self:%", N_TARGETS),
        )
    ]
    bound = {r[0] for r in conn.execute("SELECT self_id FROM self_persona_binding")}
    targets = [t for t in top if t in bound]

    rows: list[dict[str, Any]] = []
    resolver = StateResolver(store, NOVEL)
    leak_checks = 0
    leaks_found = 0
    t0 = time.perf_counter()
    for target_id in targets:
        for position in POSITIONS:
            full = _full_context(store, target_id)
            topk = _topk_baseline(resolver, target_id, position)
            observer = _observer_filtered(store, target_id, position)
            mdc = _mdc(store, target_id, position)

            # Leakage sanity gate: MDC's own selected content must never
            # trip its own forbidden-fact check (the invariant this module
            # exists to preserve, not widen).
            validator = EpistemicLeakageValidator()
            probe_text = " ".join(mdc["result"].state.allowed_facts)
            leak = validator.validate(mdc["result"].state, probe_text)
            leak_checks += 1
            if not leak.is_valid:
                leaks_found += 1

            def total(c: dict[str, int]) -> int:
                return c["aliases"] + c["attributes"] + c["relationships"]

            rows.append({
                "target": target_id, "position": position,
                "full": total(full), "topk": total(topk),
                "observer": total(observer["counts"]), "mdc": total(mdc["counts"]),
                "unsatisfied_keys": mdc["result"].unsatisfied_keys,
            })
    elapsed = time.perf_counter() - t0

    def avg(key: str) -> float:
        return sum(r[key] for r in rows) / len(rows) if rows else 0.0

    observer_total = sum(r["observer"] for r in rows)
    mdc_total = sum(r["mdc"] for r in rows)
    reduction_pct = (1 - mdc_total / observer_total) if observer_total else None

    return {
        "targets": targets, "positions": list(POSITIONS), "queries": len(rows),
        "avg_evidence": {"full": avg("full"), "topk": avg("topk"),
                          "observer": avg("observer"), "mdc": avg("mdc")},
        "evidence_reduction_pct_vs_observer": reduction_pct,
        "leakage_checks": leak_checks, "leakage_failures": leaks_found,
        "compile_wall_clock_s": elapsed,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Synthetic fixture: the real corpus has zero SELF attributes/relationships,
# so the coverage-plus-dependency-closure mechanism cannot be exercised on
# real data. Explicitly labeled synthetic per the user's own instruction.
# ---------------------------------------------------------------------------

SYN_NOVEL = "syn-disclosure-fixture"
DIALOGUE_TASK_SPEC = TaskSpec(
    task_id="dialogue_brief",
    required_keys={TargetKind.SELF: frozenset({"role", "faction", "status"})},
    require_persona=False,
    require_relationships=True,
    require_name=True,
)


def _build_synthetic_fixture() -> Store:
    store = Store(":memory:")
    store.add_novel(SYN_NOVEL, "Synthetic Disclosure Fixture", "", "synthetic")

    people = [
        ("s_hunter", "Fang Yuan", {"role": "hunter", "faction": "Gu Yue clan",
                                    "status": "alive", "personality": "cautious",
                                    "origin": "border village"}),
        ("s_elder", "Elder Chen", {"role": "clan elder", "faction": "Gu Yue clan",
                                    "status": "alive", "reputation": "respected"}),
        ("s_rival", "Wu Yi Hai", {"role": "rival hunter", "faction": "Wu clan",
                                   "status": "missing"}),
    ]
    for sid, label, attrs in people:
        store.add_self(Self(id=sid, novel_id=SYN_NOVEL, canonical_label=label,
                             first_attested_pos=DiscoursePosition(chapter=1)))
        store.add_persona(Persona(id=f"p_{sid}", novel_id=SYN_NOVEL, body_label=f"{label}'s body",
                                   first_attested_pos=DiscoursePosition(chapter=1)))
        store.add_self_persona_binding(SelfPersonaBinding(
            self_id=sid, persona_id=f"p_{sid}",
            interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER,
        ))
        store.add_alias_binding(SYN_NOVEL, AliasBinding(
            alias=label, alias_type=AliasType.RIGID_NAME, target_kind=TargetKind.SELF, target_id=sid,
            interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER,
        ))
        for key, value in attrs.items():
            store.add_attribute(SYN_NOVEL, Attribute(
                target_kind=TargetKind.SELF, target_id=sid, key=key, value=value,
                interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
                learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER,
            ))
    store.add_relation(SYN_NOVEL, Relation(
        src_self="s_hunter", dst_self="s_elder", type="DISCIPLE_OF",
        interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
        learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER,
    ))
    store.add_relation(SYN_NOVEL, Relation(
        src_self="s_hunter", dst_self="s_rival", type="RIVAL_OF",
        interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
        learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER,
    ))
    store.conn.commit()
    return store


def run_dialogue_experiment() -> dict[str, Any]:
    """The synthetic fixture has `s_hunter` related to both `s_elder`
    (DISCIPLE_OF) and `s_rival` (RIVAL_OF). Querying only `[s_hunter,
    s_elder]` -- the rival offstage -- is what actually exercises
    `require_relationships`'s cross-referenced-cast filter
    (`disclosure.py`'s `relation_dsts` restriction): DISCIPLE_OF's
    destination is in the batch and should be kept; RIVAL_OF's destination
    is not and should be dropped, exactly the coverage decision
    `compile_generation_state` does not make (it keeps every SELF
    relationship unconditionally, offstage or not).
    """
    store = _build_synthetic_fixture()
    target_ids = ["s_hunter", "s_elder"]

    observer = compile_generation_state(store, SYN_NOVEL, target_ids, position=50)
    result = compile_minimal_disclosure(
        store, SYN_NOVEL, target_ids, DIALOGUE_TASK_SPEC, position=50,
    )

    def count(gen: Any) -> int:
        return len(gen.allowed_facts)

    validator = EpistemicLeakageValidator()
    leak = validator.validate(result.state, " ".join(result.state.allowed_facts))

    return {
        "note": "synthetic fixture -- see module docstring for why",
        "targets": target_ids,
        "observer_evidence": count(observer),
        "mdc_evidence": count(result.state),
        "evidence_reduction_pct_vs_observer": 1 - count(result.state) / count(observer),
        "unsatisfied_keys": result.unsatisfied_keys,
        "mdc_read_set_subset_of_observer": set(result.state.read_set) <= set(observer.read_set),
        "leakage_valid": leak.is_valid,
        "observer_kept_offstage_rivalry": "rel:RIVAL_OF:s_rival" in observer.allowed_facts,
        "mdc_kept_onstage_relationship_only": (
            "rel:DISCIPLE_OF:s_elder" in result.state.allowed_facts
            and "rel:RIVAL_OF:s_rival" not in result.state.allowed_facts
        ),
    }


def run_cast_naming_experiment(store: Store) -> dict[str, Any]:
    """Real-data test of `_disambiguating_aliases`: several simultaneous
    top-mentioned Selves in one MDC batch call, naming-only task."""
    conn = store.conn
    top5 = [
        r[0] for r in conn.execute(
            "SELECT target_id FROM mention WHERE target_id LIKE ? "
            "GROUP BY target_id ORDER BY count(*) DESC LIMIT 5", (f"{NOVEL}:self:%",),
        )
    ]
    task = TaskSpec(task_id="cast_naming", require_persona=False, require_name=True)
    result = compile_minimal_disclosure(store, NOVEL, top5, task, position=190.0)
    observer = compile_generation_state(store, NOVEL, top5, position=190.0)
    obs_aliases = len([f for f in observer.allowed_facts if f.startswith("alias:")])
    mdc_aliases = len([f for f in result.state.allowed_facts if f.startswith("alias:")])
    return {
        "targets": top5,
        "observer_alias_count": obs_aliases,
        "mdc_alias_count": mdc_aliases,
        "read_set_subset": set(result.state.read_set) <= set(observer.read_set),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/db/reverend-insanity.db")
    ap.add_argument("--out", default="data/eval/mdc_disclosure_ablation.json")
    args = ap.parse_args()

    store = Store(args.db)
    render = run_render_experiment(store)
    cast_naming = run_cast_naming_experiment(store)
    store.close()

    dialogue = run_dialogue_experiment()

    report = {
        "db": args.db,
        "rules": (__doc__ or "").split("Pre-registered rules")[1].split("Usage:")[0].strip(),
        "render": render,
        "dialogue_brief": dialogue,
        "cast_naming": cast_naming,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, default=list) + "\n")

    print(f"render: {render['queries']} queries over {len(render['targets'])} targets")
    print(f"  avg evidence  full={render['avg_evidence']['full']:.2f} "
          f"topk={render['avg_evidence']['topk']:.2f} "
          f"observer={render['avg_evidence']['observer']:.2f} "
          f"mdc={render['avg_evidence']['mdc']:.2f}")
    pct = render["evidence_reduction_pct_vs_observer"]
    print(f"  evidence reduction vs observer: {pct * 100:.1f}%" if pct is not None else "  n/a")
    print(f"  leakage: {render['leakage_failures']}/{render['leakage_checks']} failures")
    print(f"dialogue_brief (synthetic): observer={dialogue['observer_evidence']} "
          f"mdc={dialogue['mdc_evidence']} "
          f"reduction={dialogue['evidence_reduction_pct_vs_observer'] * 100:.1f}%")
    print(f"  observer kept the offstage rivalry: {dialogue['observer_kept_offstage_rivalry']}")
    print(f"  mdc kept only the onstage relationship: {dialogue['mdc_kept_onstage_relationship_only']}")
    print(f"cast_naming (real data): observer_aliases={cast_naming['observer_alias_count']} "
          f"mdc_aliases={cast_naming['mdc_alias_count']}")
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
