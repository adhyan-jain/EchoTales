"""Serial-level sensitivity for the persona-stage audit (review round 3, "Nested-cut uncertainty").

The paper's 685 character-cuts are nested within three web serials, so a Wilson interval whose unit is the
character-cut understates the uncertainty about any wider population. With three serials a serial-level bootstrap or
random-effects model has too few units to mean anything, so this script reports only descriptive quantities in which
the serial is the unit: per-serial divergence, the spread across serials, and a leave-one-serial-out pooled rate.
It re-reads stored audit files, so it makes no model calls.

Run: python scripts/paper/serial_level_sensitivity.py   (writes data/eval/serial_level_sensitivity.json)
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PA = ROOT / "data" / "eval" / "prefix_audit"
OUT = ROOT / "data" / "eval" / "serial_level_sensitivity.json"
SERIALS = ["lord-of-the-mysteries", "omniscient-readers-viewpoint", "reverend-insanity"]


def _gender(block: dict) -> tuple[int, int]:
    g = block["pooled"]["gender"]
    return g["diverge"], g["compared"]


def main() -> None:
    summary = json.loads((PA / "summary.json").read_text())["by_novel"]
    per: dict[str, dict] = {}
    for s in SERIALS:
        d0, n0 = _gender(summary[s]["off"])  # original 13 cuts
        dense = json.loads((PA / f"audit_dense-off_{s}.json").read_text())
        d1, n1 = _gender(dense)  # 11 added cuts
        on0 = _gender(summary[s]["on"])[0]
        on1 = _gender(json.loads((PA / f"audit_dense-on_{s}.json").read_text()))[0]
        per[s] = dict(original=dict(diverge=d0, cuts=n0), added=dict(diverge=d1, cuts=n1),
                      all=dict(diverge=d0 + d1, cuts=n0 + n1, rate=(d0 + d1) / (n0 + n1)),
                      with_versioning_diverge=on0 + on1)

    tot_d = sum(p["all"]["diverge"] for p in per.values())
    tot_n = sum(p["all"]["cuts"] for p in per.values())
    rates = {s: p["all"]["rate"] for s, p in per.items()}
    loso = {}
    for held in SERIALS:
        d = sum(p["all"]["diverge"] for s, p in per.items() if s != held)
        n = sum(p["all"]["cuts"] for s, p in per.items() if s != held)
        loso[held] = dict(diverge=d, cuts=n, rate=d / n)

    out = dict(
        note="descriptive only; serial is the unit; three units cannot support population inference",
        trait="gender (the only trait that diverged on the original cuts; archetype is derived from it)",
        per_serial=per, pooled=dict(diverge=tot_d, cuts=tot_n, rate=tot_d / tot_n),
        serial_rate_min=min(rates.values()), serial_rate_max=max(rates.values()),
        serial_rate_mean=sum(rates.values()) / len(rates),
        leave_one_serial_out=loso,
        every_serial_positive=all(p["all"]["diverge"] > 0 for p in per.values()),
        versioning_diverge_all_serials=sum(p["with_versioning_diverge"] for p in per.values()),
    )
    OUT.write_text(json.dumps(out, indent=1))
    pct = lambda x: f"{100 * x:.1f}%"
    for s, p in per.items():
        print(f"{s:32s} {p['all']['diverge']:>3}/{p['all']['cuts']:<4} {pct(p['all']['rate'])}"
              f"   (original {p['original']['diverge']}/{p['original']['cuts']}, added {p['added']['diverge']}/{p['added']['cuts']})")
    print(f"pooled {tot_d}/{tot_n} {pct(tot_d / tot_n)}; serial range {pct(out['serial_rate_min'])}-{pct(out['serial_rate_max'])}")
    for h, v in loso.items():
        print(f"  without {h:30s} {v['diverge']}/{v['cuts']} {pct(v['rate'])}")
    print("versioning divergence across serials:", out["versioning_diverge_all_serials"])


if __name__ == "__main__":
    main()
