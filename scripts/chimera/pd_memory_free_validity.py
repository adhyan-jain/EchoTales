"""Memory-free validity of the renaming control, applied post hoc to PD v2 and PD v3 runs (no model calls).

Why: the original-versus-renamed (A vs B) agreement on plain controls is partly memory, because the original names let a
model recognise a famous book's characters (v2 section 5.15: disagreements are asymmetric toward A). Two agreement
measures contain no original-name arm, so memory cannot inflate or deflate them:
  G2a  B vs B2 agreement on real plain controls (two independent ciphers: pure renaming noise on real prose),
  G2b  A vs B agreement on UNSEEN synthetic non-reveal items (memory impossible).
Cipher robustness: the leakage gap computed separately against each cipher (A-B and A-B2) and the B-versus-B2 difference
in premature naming (should be ~0 if the ciphers only remove memory). All numbers are POST HOC on already-seen data;
they define the memory-free gate that PREREG_PD_v4.md fixes before new data. Output: data/eval/chimera/pd_memory_free_validity.json.
"""
import json
import math
import random
from pathlib import Path

ROOT = Path("data/eval/chimera")


def sign_p(a, b):
    n = a + b
    if n == 0:
        return 1.0
    k = min(a, b)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)


def one(r):
    T, S = r["truth"], r["synth_truth"]
    pre = [i for i, t in T.items() if t["kind"] == "pre"]
    ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]

    def hit(i, arm):
        return int(r["real"][i][arm] == T[i]["identity_letter"])

    g2a = sum(r["real"][i]["B"] == r["real"][i]["B2"] for i in ctrl) / len(ctrl)
    sp = [i for i, t in S.items() if t["type"] != "pre_alias"]
    g2b = sum(r["synth"][i]["A"] == r["synth"][i]["B"] for i in sp) / len(sp)
    rng = random.Random(20261016)

    def ci(f):
        bs = sorted(sum(f(j) for j in (rng.choice(pre) for _ in pre)) / len(pre) for _ in range(5000))
        return [round(bs[125], 4), round(bs[4875], 4)]

    a, b, b2 = (sum(hit(i, x) for i in pre) / len(pre) for x in ("A", "B", "B2"))
    n_ab = (sum(hit(i, "A") and not hit(i, "B") for i in pre), sum(hit(i, "B") and not hit(i, "A") for i in pre))
    n_ab2 = (sum(hit(i, "A") and not hit(i, "B2") for i in pre), sum(hit(i, "B2") and not hit(i, "A") for i in pre))
    return dict(
        G2a_B_eq_B2_real_controls=round(g2a, 4), G2b_A_eq_B_synthetic_unseen=round(g2b, 4), pre_items=len(pre),
        premature_A=round(a, 4), premature_B=round(b, 4), premature_B2=round(b2, 4),
        gap_A_minus_B=round(a - b, 4), gap_A_minus_B_ci=ci(lambda i: hit(i, "A") - hit(i, "B")), sign_p_A_vs_B=sign_p(*n_ab),
        gap_A_minus_B2=round(a - b2, 4), gap_A_minus_B2_ci=ci(lambda i: hit(i, "A") - hit(i, "B2")), sign_p_A_vs_B2=sign_p(*n_ab2),
        premature_B_minus_B2=round(b - b2, 4),
        both_ciphers_positive=bool(a - b > 0 and a - b2 > 0))


def pooled(runs, g2a_bar, g2b_bar):
    by, ok = {}, []
    for m, r in runs.items():
        v = one(r)
        if v["G2a_B_eq_B2_real_controls"] >= g2a_bar and v["G2b_A_eq_B_synthetic_unseen"] >= g2b_bar:
            ok.append(m)
            T = r["truth"]
            for i, t in T.items():
                if t["kind"] == "pre":
                    a = int(r["real"][i]["A"] == t["identity_letter"])
                    b = (int(r["real"][i]["B"] == t["identity_letter"]) + int(r["real"][i]["B2"] == t["identity_letter"])) / 2
                    by.setdefault(i, []).append(a - b)
    if not ok:
        return dict(models=[], note="no model passes")
    ids = sorted(by)

    def mean(ks):
        return sum(x for k in ks for x in by[k]) / sum(len(by[k]) for k in ks)

    rng = random.Random(20261016)
    bs = sorted(mean([rng.choice(ids) for _ in ids]) for _ in range(5000))
    return dict(models=sorted(ok), pooled_gap=round(mean(ids), 4), ci95=[round(bs[125], 4), round(bs[4875], 4)])


def main():
    out = dict(note="POST HOC on seen data; defines the memory-free gate fixed in PREREG_PD_v4.md. No original-name arm in G2a; unseen text in G2b.")
    for ver in ("pd_v2", "pd_v3"):
        runs = {}
        for f in sorted((ROOT / ver).glob("run_*.json")):
            r = json.loads(f.read_text())
            if r.get("status") == "COMPLETE":
                runs[r["model"]] = r
        out[ver] = dict(per_model={m: one(r) for m, r in runs.items()},
                        pooled_G2_80=pooled(runs, 0.80, 0.80), pooled_G2a_90_G2b_80=pooled(runs, 0.90, 0.80),
                        pooled_G2a_95_G2b_80=pooled(runs, 0.95, 0.80))
    (ROOT / "pd_memory_free_validity.json").write_text(json.dumps(out, indent=1))
    for ver in ("pd_v2", "pd_v3"):
        print("==", ver)
        for m, v in out[ver]["per_model"].items():
            print(f"{m:22s} G2a {v['G2a_B_eq_B2_real_controls']:.3f} G2b {v['G2b_A_eq_B_synthetic_unseen']:.3f} | premA {v['premature_A']:.3f} B {v['premature_B']:.3f} B2 {v['premature_B2']:.3f} | A-B {v['gap_A_minus_B']:+.3f} {v['gap_A_minus_B_ci']} p={v['sign_p_A_vs_B']:.1e} | A-B2 {v['gap_A_minus_B2']:+.3f} {v['gap_A_minus_B2_ci']} p={v['sign_p_A_vs_B2']:.1e} | B-B2 {v['premature_B_minus_B2']:+.3f}")
        for k in ("pooled_G2_80", "pooled_G2a_90_G2b_80", "pooled_G2a_95_G2b_80"):
            print(k, out[ver][k])


if __name__ == "__main__":
    main()
