"""A7: does the state-derived part of the render cache key do anything?

The observer-contrast result ("keys differ 10/10") could not isolate the
state digest: between observers the prompt and `plan_digest` change too, and
`plan_digest` itself hashes each character's `persona_id` and the
`state_digest` (`render/contract.py::VisualRenderPlan.plan_digest`). This
harness separates the layers by computing three keys from the *same* plan and
request objects for every panel:

  A  full key, as shipped (`render/cache_key.py::compute_render_cache_key`)
  B  state digest removed from the key AND from plan_digest; everything else,
     including the prompt, identical
  C  B plus persona ids removed from plan_digest's character tuple -- no
     state-derived input left except what reaches the prompt

It runs the real renderer (`render/panels.py::render_panels`) with the stub
image engine and no LLM client (mechanical, deterministic prompts), so plans
and prompts are exactly what production would build. `build_render_plan` and
`compute_render_cache_key` are wrapped to capture their inputs; nothing else
changes.

Ground truth is computed independently of every key: a panel is STALE when its
render-relevant state changed, i.e. for any cast member, the (persona ids,
Self attributes, attributes of the drawn persona) returned by `state_of` for
that panel's observer and position. Alias changes are tracked separately as
NAME changes -- whether a name change should re-render an image is a policy
question, and the key is documented not to cover it.

A second, pixel-level truth was added after the first run showed the state
truth over-counts (EVOLUTION 4.91): DRAWN-STALE counts only what can reach the
generator -- the persona actually drawn (`plan.characters`) and that persona's
attributes. A concurrent body that is not drawn, or a Self attribute such as
`status`, is state-stale but not drawn-stale. Both truths are reported; the
pre-registered one is not replaced.

Each event is applied to a fresh copy of the canonical database and compared
with a baseline run. A second pass freezes each panel's prompt and negative
prompt at their baseline values, to show the upper bound of the digest's role
when state changes do not reach the prompt.

GPU cost is not measured (stub engine). The estimate uses the one recorded
NoobAI XL timing on this card, 22 s/panel (EVOLUTION, 39 panels), and is
labelled as an estimate everywhere it is reported.

Usage:
    python3 scripts/eval/a7_cache_ablation.py [--db data/db/reverend-insanity.db]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any

from echotales.core.enums import OBSERVER_READER, AliasType, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    AliasBinding,
    Attribute,
    DiscoursePosition,
    Persona,
    SelfPersonaBinding,
)
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.pipeline.render import panels as panels_mod
from echotales.pipeline.render.cache_key import RENDER_CACHE_VERSION
from echotales.pipeline.render.contract import _digest

NOVEL = "reverend-insanity"
CHAPTERS = [1.0, 2.0, 166.0, 178.0, 197.0]
GPU_S_PER_PANEL = 22.0
SCRATCH = Path("data/scratch/reruns/a7-scratch")
FULL = FuzzyInterval(from_lb=0, from_ub=0, to_lb=10**6, to_ub=10**6)


# --------------------------------------------------------------------------
# key variants
# --------------------------------------------------------------------------

def _key(plan: Any, request: Any, *, plan_digest: str, state_digest: str,
         prompt: str | None = None, negative: str | None = None) -> str:
    """Mirror of `compute_render_cache_key` with each layer injectable.

    Kept field-for-field identical to the shipped function; `main` asserts
    condition A reproduces the renderer's own key on every panel, and
    `test_a7_harness` does the same on a fixture, so a drift is caught.
    """
    reference_digest = _digest(*[str(p) for p in request.base.reference_images])
    return _digest(
        RENDER_CACHE_VERSION,
        state_digest,
        plan_digest,
        request.prompt if prompt is None else prompt,
        request.negative_prompt if negative is None else negative,
        request.backend_name,
        request.checkpoint_id,
        request.checkpoint_version,
        tuple(request.loras),
        reference_digest,
        request.base.reference_weight,
        request.seed,
        request.width,
        request.height,
        request.steps,
        request.guidance_scale,
        request.renderer_version,
    )


def keys_for(plan: Any, request: Any, *, prompt: str | None = None,
             negative: str | None = None) -> dict[str, str]:
    no_state = dataclasses.replace(plan, state_digest="")
    no_state_no_persona = dataclasses.replace(
        no_state,
        characters=tuple(dataclasses.replace(c, persona_id="") for c in plan.characters),
    )
    return {
        "A": _key(plan, request, plan_digest=plan.plan_digest, state_digest=plan.state_digest,
                  prompt=prompt, negative=negative),
        "B": _key(plan, request, plan_digest=no_state.plan_digest, state_digest="",
                  prompt=prompt, negative=negative),
        "C": _key(plan, request, plan_digest=no_state_no_persona.plan_digest, state_digest="",
                  prompt=prompt, negative=negative),
    }


# --------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------

def _truth(store: Store, observer: str, chapter: float, cast: list[str]) -> tuple[Any, Any]:
    """Render-relevant state and name state for a panel, independent of keys."""
    resolver = StateResolver(store, NOVEL, default_observer=observer)
    render_state, names = [], []
    for sid in cast:
        r = resolver.state_of(sid, position=chapter)
        persona_attrs: tuple[Any, ...] = ()
        if r.persona_ids:
            persona_attrs = tuple(sorted(
                (a.key, a.value) for a in store.get_attributes(TargetKind.PERSONA, r.persona_ids[0])
                if a.is_standing
            ))
        render_state.append((sid, tuple(r.persona_ids), tuple(sorted(r.attributes.items())), persona_attrs))
        names.append((sid, tuple(sorted(r.aliases))))
    return tuple(render_state), tuple(names)


def capture(db: Path, observer: str, out: Path) -> tuple[dict[str, dict[str, Any]], float]:
    """Run the stub renderer once; return per-panel captured inputs and wall time."""
    store = Store(str(db))
    rows: dict[str, dict[str, Any]] = {}
    pending: dict[int, dict[str, Any]] = {}
    orig_plan, orig_key = panels_mod.build_render_plan, panels_mod.compute_render_cache_key

    def plan_wrapper(store_, novel_id, **kw):  # type: ignore[no-untyped-def]
        plan = orig_plan(store_, novel_id, **kw)
        pending[id(plan)] = {"cast": list(kw["cast_self_ids"]), "chapter": kw["chapter"]}
        return plan

    def key_wrapper(plan, request):  # type: ignore[no-untyped-def]
        key = orig_key(plan, request)
        meta = pending.pop(id(plan), {"cast": [], "chapter": plan.chapter})
        panel = f"{plan.chapter:g}:{Path(request.base.out_path).stem.split('_', 1)[-1]}"
        truth, names = _truth(store, observer, meta["chapter"], meta["cast"])
        drawn = tuple(sorted(
            (c.persona_id, tuple(sorted((a.key, a.value) for a in store.get_attributes(
                TargetKind.PERSONA, c.persona_id) if a.is_standing)))
            for c in plan.characters
        ))
        rows[panel] = {"plan": plan, "request": request, "shipped_key": key,
                       "truth": truth, "drawn": drawn, "names": names}
        return key

    panels_mod.build_render_plan = plan_wrapper
    panels_mod.compute_render_cache_key = key_wrapper
    t0 = time.perf_counter()
    try:
        panels_mod.render_panels(
            NOVEL, store, out_dir=out, engine=panels_mod.StubImageEngine(),
            chapters=CHAPTERS, client=None, max_panels=40, observer_id=observer,
        )
    finally:
        panels_mod.build_render_plan, panels_mod.compute_render_cache_key = orig_plan, orig_key
        store.close()
    return rows, time.perf_counter() - t0


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------

def fresh_copy(src: Path, name: str) -> Path:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    dst = SCRATCH / f"{name}.db"
    shutil.copyfile(src, dst)
    return dst


def cast_counts(rows: dict[str, dict[str, Any]]) -> Counter[str]:
    c: Counter[str] = Counter()
    for r in rows.values():
        for sid, pids, *_ in r["truth"]:
            if pids:
                c[sid] += 1
    return c


def apply_event(db: Path, event: str, target_self: str, target_persona: str,
                offcast_persona: str) -> None:
    store = Store(str(db))
    pos = DiscoursePosition(chapter=0)
    if event == "E1_cast_appearance":
        store.add_attribute(NOVEL, Attribute(
            target_kind=TargetKind.PERSONA, target_id=target_persona, key="hair_color",
            value="silver", interval=FULL, learned_at_pos=pos, observer_id=OBSERVER_READER))
    elif event == "E1b_cast_attire":
        store.add_attribute(NOVEL, Attribute(
            target_kind=TargetKind.PERSONA, target_id=target_persona, key="attire",
            value="silver armour", interval=FULL, learned_at_pos=pos, observer_id=OBSERVER_READER))
    elif event == "E2_offcast_appearance":
        store.add_attribute(NOVEL, Attribute(
            target_kind=TargetKind.PERSONA, target_id=offcast_persona, key="hair_color",
            value="silver", interval=FULL, learned_at_pos=pos, observer_id=OBSERVER_READER))
    elif event == "E3_cast_new_body":
        pid = f"{target_self}:bodyA7"
        store.add_persona(Persona(id=pid, novel_id=NOVEL, body_label="a7 test body",
                                  first_attested_pos=pos))
        store.add_self_persona_binding(SelfPersonaBinding(
            self_id=target_self, persona_id=pid, interval=FULL, learned_at_pos=pos,
            observer_id=OBSERVER_READER))
    elif event == "E5_cast_alias_only":
        store.add_alias_binding(NOVEL, AliasBinding(
            alias="A7 Test Name", alias_type=AliasType.RIGID_NAME, target_kind=TargetKind.SELF,
            target_id=target_self, interval=FULL, learned_at_pos=pos, observer_id=OBSERVER_READER))
    elif event == "E6_cast_self_attribute":
        store.add_attribute(NOVEL, Attribute(
            target_kind=TargetKind.SELF, target_id=target_self, key="status",
            value="a7 test status", interval=FULL, learned_at_pos=pos, observer_id=OBSERVER_READER))
    store.conn.commit()
    store.close()


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

def compare(base: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]], *,
            freeze_prompt: bool) -> dict[str, Any]:
    panels = sorted(set(base) & set(new))
    out: dict[str, Any] = {"panels": len(panels),
                           "only_in_one_run": len(set(base) ^ set(new)),
                           "stale": 0, "drawn_stale": 0, "name_changed": 0, "prompt_changed": 0,
                           "conditions": {}, "conditions_drawn_truth": {}}
    cond = {c: Counter() for c in "ABC"}
    cond_drawn = {c: Counter() for c in "ABC"}
    uniq: dict[str, set[str]] = {c: set() for c in "ABC"}
    for p in panels:
        b, n = base[p], new[p]
        kb = keys_for(b["plan"], b["request"])
        prompt = negative = None
        if freeze_prompt:
            prompt, negative = b["request"].prompt, b["request"].negative_prompt
        kn = keys_for(n["plan"], n["request"], prompt=prompt, negative=negative)
        stale = b["truth"] != n["truth"]
        drawn_stale = b["drawn"] != n["drawn"]
        out["stale"] += stale
        out["drawn_stale"] += drawn_stale
        out["name_changed"] += b["names"] != n["names"]
        out["prompt_changed"] += b["request"].prompt != n["request"].prompt
        for c in "ABC":
            changed = kb[c] != kn[c]
            uniq[c].update((kb[c], kn[c]))
            cond[c]["necessary_regen" if stale and changed else
                    "incorrect_reuse" if stale else
                    "unnecessary_regen" if changed else "correct_reuse"] += 1
            cond_drawn[c]["necessary_regen" if drawn_stale and changed else
                          "incorrect_reuse" if drawn_stale else
                          "unnecessary_regen" if changed else "correct_reuse"] += 1
    for c in "ABC":
        regen = cond[c]["necessary_regen"] + cond[c]["unnecessary_regen"]
        out["conditions"][c] = {**{k: cond[c][k] for k in (
            "correct_reuse", "incorrect_reuse", "necessary_regen", "unnecessary_regen")},
            "hits": cond[c]["correct_reuse"] + cond[c]["incorrect_reuse"],
            "misses": regen, "unique_keys": len(uniq[c]),
            "est_gpu_s": regen * GPU_S_PER_PANEL}
        out["conditions_drawn_truth"][c] = {k: cond_drawn[c][k] for k in (
            "correct_reuse", "incorrect_reuse", "necessary_regen", "unnecessary_regen")}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/db/reverend-insanity.db")
    ap.add_argument("--out", default="data/eval/a7_cache_ablation.json")
    args = ap.parse_args()
    src = Path(args.db)

    base_db = fresh_copy(src, "baseline")
    base, base_s = capture(base_db, OBSERVER_READER, SCRATCH / "render-baseline")
    # A shipped-key reproduction check: condition A must equal what the
    # renderer itself computed, or the harness is not measuring production.
    mismatched = sum(keys_for(r["plan"], r["request"])["A"] != r["shipped_key"] for r in base.values())
    assert mismatched == 0, f"condition A diverges from the shipped key on {mismatched} panels"

    casts = cast_counts(base)
    target_self = casts.most_common(1)[0][0]
    target_persona = next(pids[0] for r in base.values()
                          for sid, pids, *_ in r["truth"] if sid == target_self and pids)
    store = Store(str(src))
    offcast_persona = next(
        pid for (pid,) in store.conn.execute(
            f"SELECT persona_id FROM self_persona_binding WHERE self_id NOT IN ({','.join('?' * len(casts))})",
            tuple(casts))
    )
    witness = store.conn.execute(
        "SELECT observer_id FROM observation ORDER BY observer_id LIMIT 1").fetchone()[0]
    store.close()

    report: dict[str, Any] = {
        "db": str(src), "chapters": CHAPTERS, "gpu_s_per_panel_estimate": GPU_S_PER_PANEL,
        "baseline_panels": len(base), "baseline_wall_s": round(base_s, 2),
        "shipped_key_reproduced": True,
        "targets": {"cast_self": target_self, "cast_persona": target_persona,
                    "offcast_persona": offcast_persona, "witness_observer": witness},
        "events": {},
    }

    replay_db = fresh_copy(src, "E0")
    replay, s = capture(replay_db, OBSERVER_READER, SCRATCH / "render-E0")
    report["events"]["E0_replay"] = {"realistic": compare(base, replay, freeze_prompt=False),
                                     "wall_s": round(s, 2)}

    for ev in ("E1_cast_appearance", "E1b_cast_attire", "E2_offcast_appearance", "E3_cast_new_body",
               "E5_cast_alias_only", "E6_cast_self_attribute"):
        db = fresh_copy(src, ev)
        apply_event(db, ev, target_self, target_persona, offcast_persona)
        new, s = capture(db, OBSERVER_READER, SCRATCH / f"render-{ev}")
        report["events"][ev] = {"realistic": compare(base, new, freeze_prompt=False),
                                "frozen_prompt": compare(base, new, freeze_prompt=True),
                                "wall_s": round(s, 2)}

    obs_db = fresh_copy(src, "E4")
    for label, observer in (("E4_observer_witness", witness),):
        new, s = capture(obs_db, observer, SCRATCH / f"render-{label}")
        report["events"][label] = {"realistic": compare(base, new, freeze_prompt=False),
                                   "frozen_prompt": compare(base, new, freeze_prompt=True),
                                   "wall_s": round(s, 2)}

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    for name, ev in report["events"].items():
        for mode in ("realistic", "frozen_prompt"):
            if mode not in ev:
                continue
            r = ev[mode]
            print(f"{name:24} {mode:13} panels={r['panels']:3} stale={r['stale']:3} drawn={r['drawn_stale']:3} "
                  f"prompt_changed={r['prompt_changed']:3} names={r['name_changed']:3}  " + "  ".join(
                      f"{c}: reuse ok/bad={v['correct_reuse']}/{v['incorrect_reuse']} "
                      f"regen need/extra={v['necessary_regen']}/{v['unnecessary_regen']}"
                      for c, v in r["conditions"].items()))
            print(" " * 38 + "drawn-truth  " + "  ".join(
                f"{c}: bad_reuse={v['incorrect_reuse']} extra_regen={v['unnecessary_regen']}"
                for c, v in r["conditions_drawn_truth"].items()))
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
