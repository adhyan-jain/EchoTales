"""POST-HOC sensitivity of the PD v2 pooled leakage statistic to the renaming-validity threshold (R0).

Why: the pre-registered 95% bar was an arbitrary conventional choice (owner challenge, 2026-10-16: 88-95% should be an
acceptable range). The frozen verdict (INCONCLUSIVE at 95%) is NOT changed; this script only shows how the pooled
statistic and the pre-registered decision rule would read at other thresholds, so a v3 pre-registration can pick a
threshold with the numbers in view instead of after a result. Reads data/eval/chimera/pd_v2/run_*.json; no model calls.
Output: data/eval/chimera/pd_v2/threshold_sensitivity_posthoc.json."""
import json
import random
from pathlib import Path

OUT = Path("data/eval/chimera/pd_v2")
THRESHOLDS = [0.95, 0.90, 0.88, 0.85, 0.80]


def load():
    runs = {}
    for f in sorted(OUT.glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            runs[r["model"]] = r
    return runs


def per_model(r):
    T, S = r["truth"], r["synth_truth"]
    pre = [i for i, t in T.items() if t["kind"] == "pre"]
    ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
    r0 = sum(r["real"][i]["A"] == r["real"][i]["B"] for i in ctrl) / len(ctrl)
    pa = {i: int(r["real"][i]["A"] == T[i]["identity_letter"]) for i in pre}
    pb = {i: (int(r["real"][i]["B"] == T[i]["identity_letter"]) + int(r["real"][i]["B2"] == T[i]["identity_letter"])) / 2
          for i in pre}
    spre = [i for i, t in S.items() if t["type"] == "pre_alias"]
    sd = {i: int(r["synth"][i]["A"] == S[i]["identity_letter"]) - int(r["synth"][i]["B"] == S[i]["identity_letter"])
          for i in spre}
    mem = sum(v["C_orig"] == r["closed_truth"][e] for e, v in r["closed"].items()) >= 6  # v2 threshold for 19 events
    return dict(r0=r0, d={i: pa[i] - pb[i] for i in pre}, sd=sd, mem=mem)


def mean(d, keys):
    return sum(x for k in keys for x in d[k]) / sum(len(d[k]) for k in keys)


def main():
    pm = {m: per_model(r) for m, r in load().items()}
    out = dict(note="POST HOC sensitivity; the frozen v2 verdict (95%) is INCONCLUSIVE and is unchanged.",
               r0={m: round(v["r0"], 4) for m, v in pm.items()}, thresholds={})
    for thr in THRESHOLDS:
        ok = {m: v for m, v in pm.items() if v["r0"] >= thr}
        if not ok:
            out["thresholds"][str(thr)] = dict(models=[], verdict="no model passes")
            continue
        by, sy = {}, {}
        for v in ok.values():
            for i, x in v["d"].items():
                by.setdefault(i, []).append(x)
            for i, x in v["sd"].items():
                sy.setdefault(i, []).append(x)
        ids, sids = sorted(by), sorted(sy)
        gp, gs = mean(by, ids), mean(sy, sids)
        rng = random.Random(20261016)
        gb, db = [], []
        for _ in range(5000):
            g1 = mean(by, [rng.choice(ids) for _ in ids])
            g2 = mean(sy, [rng.choice(sids) for _ in sids])
            gb.append(g1)
            db.append(g1 - g2)
        gb.sort()
        db.sort()
        n_mem = sum(v["mem"] for v in ok.values())
        cond = dict(i=gp >= 0.10 and gb[125] > 0, ii=(gp - gs) > 0 and db[125] > 0, iii=n_mem >= 3)
        rule = ("INCONCLUSIVE (fewer than 3 models)" if len(ok) < 3 else
                "SUPPORTED" if all(cond.values()) else "PARTIALLY SUPPORTED" if cond["i"] else "NOT SUPPORTED")
        out["thresholds"][str(thr)] = dict(
            models=sorted(ok), pooled_gap=gp, gap_ci95=[gb[125], gb[4875]], synthetic_gap=gs, did=gp - gs,
            did_ci95=[db[125], db[4875]], memory_models=n_mem, conditions=cond, rule_reading=rule)
    (OUT / "threshold_sensitivity_posthoc.json").write_text(json.dumps(out, indent=1))
    for thr, v in out["thresholds"].items():
        if v.get("models"):
            print(f"R0>={thr}: {len(v['models'])} models {v['models']} gap {v['pooled_gap']:+.3f} "
                  f"[{v['gap_ci95'][0]:+.3f},{v['gap_ci95'][1]:+.3f}] syn {v['synthetic_gap']:+.3f} DiD {v['did']:+.3f} "
                  f"[{v['did_ci95'][0]:+.3f},{v['did_ci95'][1]:+.3f}] memory {v['memory_models']} -> {v['rule_reading']}")
        else:
            print(f"R0>={thr}: none")


if __name__ == "__main__":
    main()
