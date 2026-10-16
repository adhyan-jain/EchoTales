"""Pool the per-serial audit JSONs into the tables used by docs/research/PREFIX_FAITHFULNESS/REPORT.md.

    python scripts/prefix_audit/summarize.py            # prints tables, writes data/eval/prefix_audit/summary.json

Reads only data/eval/prefix_audit/audit_repair-{off,on}_<novel>.json (ids, chapter numbers and counts; no novel text).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

NOVELS = ["lord-of-the-mysteries", "omniscient-readers-viewpoint", "reverend-insanity"]
TRAITS = ("gender", "archetype", "age_band", "register", "big_five")


def load(mode: str, nid: str) -> dict:
    return json.loads((C.RESULTS / f"audit_repair-{mode}_{nid}.json").read_text())


def pooled_character_cuts(rows: list[dict]) -> tuple[int, int, int]:
    """(character-cuts compared, with any trait divergence, exposed to later evidence) over the five trait keys."""
    seen: dict[tuple, list[bool]] = {}
    for r in rows:
        if r["key"] in TRAITS:
            cell = seen.setdefault((r["entity"], r["k"]), [False, False])
            cell[0] = cell[0] or r["diverge"]
            cell[1] = cell[1] or bool(r["exposed"])
    return len(seen), sum(c[0] for c in seen.values()), sum(c[1] for c in seen.values())


def main() -> None:
    out: dict = {"by_novel": {}, "pooled": {}}
    pool = {m: {"rows": [], "n_gender": 0, "unk_served": 0, "unk_prefix": 0, "attr_rows": 0, "secs": 0.0} for m in ("off", "on")}
    for nid in NOVELS:
        for mode in ("off", "on"):
            d = load(mode, nid)
            p = pool[mode]
            p["rows"] += d["rows"]
            p["attr_rows"] += d["attribute_rows_full"]
            p["secs"] += d["persona_stage_seconds_full"]
            for k, v in d["by_k"].items():
                a = v["gender_availability"]
                p["n_gender"] += a.get("n", 0)
                p["unk_served"] += a.get("unknown_full", 0)
                p["unk_prefix"] += a.get("unknown_prefix", 0)
            out["by_novel"].setdefault(nid, {})[mode] = dict(
                attribute_rows_full=d["attribute_rows_full"], persona_stage_seconds_full=d["persona_stage_seconds_full"],
                pooled=d["pooled"])
    print("| mode | character-cuts | with a trait divergence | Wilson 95% | exposed to later evidence | gender diverges | persona-set diverges |")
    print("|---|---|---|---|---|---|---|")
    for mode in ("off", "on"):
        p = pool[mode]
        n, div, exp = pooled_character_cuts(p["rows"])
        g = sum(r["diverge"] for r in p["rows"] if r["key"] == "gender")
        ps = sum(r["diverge"] for r in p["rows"] if r["key"] == "persona_set")
        w = C.wilson(div, n)
        print(f"| repair {mode} | {n} | {div} | [{w[0]:.3f}, {w[1]:.3f}] | {exp if mode == 'off' else 'n/a'} | {g} | {ps} |")
        out["pooled"][mode] = dict(character_cuts=n, with_divergence=div, wilson=w, exposed=exp if mode == "off" else None,
                                   gender_diverge=g, persona_set_diverge=ps)
    off_rows = pool["off"]["rows"]
    print("\nStatic screen (repair off), per key: exposed fact-cuts, of which diverged, H1 violations (diverged outside the window)")
    for key in (*TRAITS, "persona_set"):
        sel = [r for r in off_rows if r["key"] == key and r["exposed"] is not None]
        exp = sum(bool(r["exposed"]) for r in sel)
        both = sum(bool(r["exposed"]) and r["diverge"] for r in sel)
        viol = sum((not r["exposed"]) and r["diverge"] for r in sel)
        print(f"  {key:12s} scored={len(sel):4d} exposed={exp:4d} diverged-in-window={both:3d} "
              f"precision={(both / exp if exp else 0):.3f} H1-violations={viol}")
        out["pooled"].setdefault("screen", {})[key] = dict(scored=len(sel), exposed=exp, diverged_in_window=both, h1_violations=viol)
    # Fair yardsticks for the screen: against the base rate of "flag everything", and as a certifier of safe cuts.
    gen = [r for r in off_rows if r["key"] == "gender" and r["exposed"] is not None]
    n_g, div_g = len(gen), sum(r["diverge"] for r in gen)
    exp_g = [r for r in gen if r["exposed"]]
    safe_g = [r for r in gen if not r["exposed"]]
    both_g = sum(r["diverge"] for r in exp_g)
    print(f"\nScreen yardsticks (gender): base rate of a flag-everything screen = {div_g}/{n_g} = {div_g / n_g:.3f}; "
          f"screen precision = {both_g}/{len(exp_g)} = {both_g / len(exp_g):.3f} (lift {both_g / len(exp_g) / (div_g / n_g):.2f}x); "
          f"recall = {both_g}/{div_g}; cuts certified safe without a rebuild = {len(safe_g)}/{n_g} "
          f"({len(safe_g) / n_g:.3f}), divergent among them = {sum(r['diverge'] for r in safe_g)}")
    # Ablation: HIDE-ONLY repair. An exposed gender is hidden (the stage's own fallback is 'unknown'); scored against the prefix build.
    hide_div = sum(("unknown" if r["exposed"] else r["full_value"]) != r["prefix_value"] for r in gen)
    lost = sum(r["exposed"] and r["diverge"] is False and r["prefix_value"] != "unknown" for r in gen)
    reversed_ = sum(r["exposed"] and r["diverge"] and r["prefix_value"] != "unknown" for r in gen)
    print(f"Hide-only ablation (gender): diverges from the prefix build on {hide_div}/{n_g} cuts "
          f"(of which {lost} hide a value the prefix build already held and the full build agreed with, "
          f"{reversed_} hide a value the full build would have changed); versioned repair: 0/{n_g}; unrepaired: {div_g}/{n_g}")
    out["pooled"]["screen_yardsticks"] = dict(n=n_g, base_rate=div_g / n_g, precision=both_g / len(exp_g), recall=1.0 if div_g == both_g else both_g / div_g,
                                              certified_safe=len(safe_g), divergent_among_safe=sum(r["diverge"] for r in safe_g))
    out["pooled"]["hide_only"] = dict(n=n_g, diverge=hide_div, hides_correct_known=lost, hides_changed_value=reversed_, unrepaired=div_g, versioned=0)
    print("\nCost (pooled over 13 cuts): gender 'unknown' share among compared character-cuts")
    for mode in ("off", "on"):
        p = pool[mode]
        n = p["n_gender"]
        print(f"  repair {mode:3s}: n={n}  served unknown={p['unk_served']} ({p['unk_served'] / n:.3f})  "
              f"prefix-only build knows unknown={p['unk_prefix']} ({p['unk_prefix'] / n:.3f})  "
              f"attribute rows (3 full builds)={p['attr_rows']}  persona-stage seconds={p['secs']:.1f}")
        out["pooled"].setdefault("cost", {})[mode] = dict(
            n=n, unknown_served=p["unk_served"], unknown_prefix=p["unk_prefix"], attribute_rows=p["attr_rows"],
            persona_stage_seconds=round(p["secs"], 2))
    (C.RESULTS / "summary.json").write_text(json.dumps(out, indent=1))
    print("\nwrote", C.RESULTS / "summary.json")


if __name__ == "__main__":
    main()
