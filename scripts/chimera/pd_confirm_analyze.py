"""Pre-registered analysis of the confirmatory study (PREREG_PD_CONFIRM.md section 6 and 7 as amended by v2, addenda 1 to 3).
One run, no re-analysis versions. Reads data/eval/chimera/confirm/<tag>/ (e1_*.json, e4_*.json, e5_*.json, e5judge_*.json) and the frozen
events file; writes analysis.json there and prints a summary. Everything is event-cluster (10,000 resamples, seed 20261101); items inside an
event are never treated as independent. Label provenance: TEXT-DERIVED oracle, model-selected events, no human labels.

Callers: run by hand after the model runs. Primary set = events the audit labelled EXPLICIT, test split only; the dev split and the
secondary set (all verified events) are reported as exploratory.

  python scripts/chimera/pd_confirm_analyze.py [--tag main] [--events FILE]
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import numpy as np
from scipy import stats

P = Path("docs/research/preregistrations")
OUT = Path("data/eval/chimera/confirm")
SEED, NB = 20261101, 10000


def boot_events(per_event: dict, stat, n=NB, seed=SEED):
    """per_event: event -> payload; stat(list_of_payloads) -> float. Returns (point, lo, hi, var, samples)."""
    evs = sorted(per_event)
    rng = random.Random(seed)
    pt = stat([per_event[e] for e in evs])
    bs = []
    for _ in range(n):
        v = stat([per_event[rng.choice(evs)] for _ in evs])
        if not (isinstance(v, float) and math.isnan(v)):
            bs.append(v)
    bs.sort()
    return pt, bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs))], float(np.var(bs, ddof=1)), bs


def sign_p_one_sided(pos: int, neg: int) -> float:
    n = pos + neg
    return float(sum(math.comb(n, i) for i in range(pos, n + 1)) / 2 ** n) if n else 1.0


def holm(ps: dict) -> dict:
    items = sorted(ps.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def dl_hk(ys, vs):
    """DerSimonian-Laird random effects with Hartung-Knapp interval (t, k-1 df); returns pooled, lo, hi, tau2, one-sided p (H0: <= 0)."""
    k = len(ys)
    w = [1 / v for v in vs]
    fe = sum(wi * y for wi, y in zip(w, ys)) / sum(w)
    q = sum(wi * (y - fe) ** 2 for wi, y in zip(w, ys))
    c = sum(w) - sum(wi ** 2 for wi in w) / sum(w)
    tau2 = max(0.0, (q - (k - 1)) / c) if k > 1 else 0.0
    ws = [1 / (v + tau2) for v in vs]
    th = sum(wi * y for wi, y in zip(ws, ys)) / sum(ws)
    if k < 2:
        return th, None, None, tau2, None
    var_hk = sum(wi * (y - th) ** 2 for wi, y in zip(ws, ys)) / ((k - 1) * sum(ws))
    t = stats.t.ppf(0.975, k - 1)
    se = math.sqrt(var_hk)
    return th, th - t * se, th + t * se, tau2, (float(stats.t.sf(th / se, k - 1)) if se > 0 else None)


def load_e1(out: Path):
    runs = {}
    for f in sorted(out.glob("e1_*.json")):
        r = json.loads(f.read_text())
        runs[r["model"]] = r
    return runs


def event_rows(r, evs_by_id, split, primary_only):
    """event -> list of per-pre-item dicts (A, B, B2, B3 as 0/1 identity hits) for this model."""
    T = r["truth"]
    rows = {}
    for i, t in T.items():
        if t["kind"] != "pre":
            continue
        ev = evs_by_id[t["event"]]
        if split and ev.get("split") != split:
            continue
        if primary_only and ev.get("audit") not in ("EXPLICIT", "NA"):
            continue
        h = {arm: int(r["real"][i].get(arm) == t["identity_letter"]) for arm in ("A", "B", "B2", "B3") if arm in r["real"][i]}
        rows.setdefault(t["event"], []).append(h)
    return rows


def gap_stat(key):
    def f(payloads):
        vals = [np.mean([h["A"] - h[key] for h in rows]) for rows in payloads]
        return float(np.mean(vals)) if vals else float("nan")
    return f


def recovered(payloads):
    a = np.mean([np.mean([h["A"] for h in rows]) for rows in payloads])
    b = np.mean([np.mean([h["B"] for h in rows]) for rows in payloads])
    b3 = np.mean([np.mean([h["B3"] for h in rows]) for rows in payloads])
    return float((b3 - b) / (a - b)) if abs(a - b) > 1e-9 else float("nan")


def ci_str(lo, hi):
    return f"[{100 * lo:+.1f}, {100 * hi:+.1f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="main")
    ap.add_argument("--events", default=str(P / "PD_confirm_events_v1.json"))
    a = ap.parse_args()
    out = OUT / a.tag
    evs = json.loads(Path(a.events).read_text())["events"]
    by = {e["id"]: e for e in evs}
    runs = load_e1(out)
    res = dict(tag=a.tag, label_provenance="TEXT-DERIVED oracle; model-selected events; no human labels", models=sorted(runs), n_events=len(evs),
               n_test=sum(e.get("split") == "test" for e in evs), n_primary_test=sum(e.get("split") == "test" and e.get("audit") == "EXPLICIT" for e in evs),
               per_model={})
    # ------------------------------------------------ per model
    gaps_by_model = {}
    for m, r in runs.items():
        for label, split, prim in (("primary_test", "test", True), ("all_verified_test", "test", False), ("dev_exploratory", "dev", False)):
            rows = event_rows(r, by, split, prim)
            if len(rows) < 3:
                res["per_model"].setdefault(m, {})[label] = dict(events=len(rows), note="fewer than 3 events")
                continue
            pt, lo, hi, var, _ = boot_events(rows, gap_stat("B"))
            pt3, lo3, hi3, var3, _ = boot_events(rows, gap_stat("B3"))
            rf, rlo, rhi, _, _ = boot_events(rows, recovered)
            pos = sum(1 for e in rows if np.mean([h["A"] - h["B"] for h in rows[e]]) > 0)
            neg = sum(1 for e in rows if np.mean([h["A"] - h["B"] for h in rows[e]]) < 0)
            d = dict(events=len(rows), gap_A_minus_B=pt, ci=[lo, hi], var=var, gap_A_minus_B3=pt3, ci_B3=[lo3, hi3], var_B3=var3,
                     recovered_fraction=rf, recovered_ci=[rlo, rhi], events_pos=pos, events_neg=neg, sign_p_one_sided=sign_p_one_sided(pos, neg))
            res["per_model"].setdefault(m, {})[label] = d
            if label == "primary_test":
                gaps_by_model[m] = (rows, d)
        T = r["truth"]
        ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
        g2a = sum(r["real"][i]["B"] == r["real"][i]["B2"] for i in ctrl) / max(1, len(ctrl))
        inv = sum(v == "INVALID" for d_ in r["real"].values() for v in d_.values())
        tot = sum(len(d_) for d_ in r["real"].values())
        acc = {arm: round(sum(r["real"][i][arm] == T[i]["truth_letter"] for i in ctrl) / max(1, len(ctrl)), 4) for arm in ("A", "B", "B2", "B3")}
        res["per_model"].setdefault(m, {}).update(
            G2a_B_eq_B2=round(g2a, 4), invalid_share=round(inv / max(1, tot), 4), ctrl_acc=acc,
            m2_orig_correct=sum(r["m2"][e]["M2_orig"] == r["m2_truth"][e] for e in r["m2_truth"]),
            m2_ren_correct=sum(r["m2"][e]["M2_ren"] == r["m2_truth"][e] for e in r["m2_truth"]),
            closed_orig_correct=sum(r["closed"][e]["C_orig"] == r["closed_truth"][e] for e in r["closed_truth"]), events_with_m2=len(r["m2_truth"]))
    # ------------------------------------------------ H1 and H2
    ps = {}
    usable = [m for m in gaps_by_model if res["per_model"][m].get("invalid_share", 0) <= 0.10]
    res["h1_h2_models"] = usable
    if len(usable) >= 2:
        ys = [gaps_by_model[m][1]["gap_A_minus_B"] for m in usable]
        vs = [max(gaps_by_model[m][1]["var"], 1e-6) for m in usable]
        th, lo, hi, tau2, p = dl_hk(ys, vs)
        hm = holm({m: gaps_by_model[m][1]["sign_p_one_sided"] for m in usable})
        npos = sum(1 for m in usable if gaps_by_model[m][1]["gap_A_minus_B"] > 0 and hm[m] < 0.05)
        res["H1"] = dict(pooled=th, ci=[lo, hi], tau2=tau2, p_one_sided=p, models_positive_holm_sig=npos, holm_adjusted_sign_p=hm,
                         models_used=len(usable), criterion_needs_4_models=len(usable) >= 4,
                         passes=bool(th >= 0.10 and lo is not None and lo > 0 and npos >= 3 and len(usable) >= 4))
        if p is not None:
            ps["H1"] = p
        ys3 = [gaps_by_model[m][1]["gap_A_minus_B3"] for m in usable]
        vs3 = [max(gaps_by_model[m][1]["var_B3"], 1e-6) for m in usable]
        th3, lo3, hi3, _t, p3 = dl_hk(ys3, vs3)
        allrows = {}
        for m in usable:
            for e, v in gaps_by_model[m][0].items():
                allrows.setdefault(e, []).extend(v)
        rf, rlo, rhi, _, _ = boot_events(allrows, recovered)
        res["H2"] = dict(pooled_A_minus_B3=th3, ci=[lo3, hi3], p_one_sided=p3, recovered_fraction=rf, recovered_ci=[rlo, rhi],
                         passes=bool(th3 >= 0.10 and lo3 is not None and lo3 > 0 and rhi < 2 / 3 and rf < 1 / 3))
        if p3 is not None:
            ps["H2"] = p3
    # ------------------------------------------------ H3
    if gaps_by_model:
        evs_all = sorted({e for m in gaps_by_model for e in gaps_by_model[m][0]})
        g = {e: float(np.mean([np.mean([h["A"] - h["B"] for h in gaps_by_model[m][0][e]]) for m in gaps_by_model if e in gaps_by_model[m][0]])) for e in evs_all}
        W = {e: math.log2(1 + by[e]["W"]) for e in evs_all}
        gid = {e: by[e]["gutenberg"] for e in evs_all}
        x, y = np.array([W[e] for e in evs_all]), np.array([g[e] for e in evs_all])
        rho = float(stats.spearmanr(x, y)[0]) if len(set(x)) > 1 and len(set(y)) > 1 else float("nan")
        books = sorted({gid[e] for e in evs_all})
        wb = {b: W[next(e for e in evs_all if gid[e] == b)] for b in books}
        rng, cnt, B = random.Random(SEED), 0, 20000
        for _ in range(B):
            vals = [wb[b] for b in books]
            rng.shuffle(vals)
            perm = dict(zip(books, vals))
            r_ = stats.spearmanr(np.array([perm[gid[e]] for e in evs_all]), y)[0]
            cnt += (not math.isnan(r_)) and r_ >= rho
        p = (cnt + 1) / (B + 1) if not math.isnan(rho) else None
        res["H3"] = dict(spearman=rho, perm_p_one_sided=p, events=len(evs_all), books=len(books), passes=bool(p is not None and rho >= 0.20 and p < 0.05),
                         note=None if p is not None else "fame is constant or the gap is constant: correlation undefined")
        if p is not None:
            ps["H3"] = p
        by_band = {}
        for e in evs_all:
            by_band.setdefault(by[e]["band"], []).append(g[e])
        res["gap_by_fame_band"] = {b: dict(events=len(v), mean_gap=float(np.mean(v))) for b, v in by_band.items()}
    # ------------------------------------------------ P1 (primary, addendum 5): fame contrast
    if gaps_by_model:
        grp = {"hm": [], "low": []}
        for e in sorted({e for m in gaps_by_model for e in gaps_by_model[m][0]}):
            v = [np.mean([h["A"] - h["B"] for h in gaps_by_model[m][0][e]]) for m in gaps_by_model if e in gaps_by_model[m][0]]
            grp["low" if by[e].get("W", 0) < 3 else "hm"].append(float(np.mean(v)))
        if len(grp["hm"]) >= 3 and len(grp["low"]) >= 3:
            rng = random.Random(SEED)
            diffs = []
            for _ in range(NB):
                x1 = [rng.choice(grp["hm"]) for _ in grp["hm"]]
                x0 = [rng.choice(grp["low"]) for _ in grp["low"]]
                diffs.append(float(np.mean(x1) - np.mean(x0)))
            diffs.sort()
            d_ = float(np.mean(grp["hm"]) - np.mean(grp["low"]))
            sd = float(np.sqrt((np.var(grp["hm"], ddof=1) * (len(grp["hm"]) - 1) + np.var(grp["low"], ddof=1) * (len(grp["low"]) - 1)) / (len(grp["hm"]) + len(grp["low"]) - 2)))
            mde = (stats.norm.ppf(0.95) + stats.norm.ppf(0.80)) * sd * math.sqrt(1 / len(grp["hm"]) + 1 / len(grp["low"]))
            p1 = float(sum(1 for x in diffs if x <= 0) / len(diffs))
            res["P1"] = dict(events_high_mid=len(grp["hm"]), events_low=len(grp["low"]), mean_gap_high_mid=float(np.mean(grp["hm"])), mean_gap_low=float(np.mean(grp["low"])),
                             difference=d_, ci=[diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs))]], p_one_sided=p1, passes=bool(p1 < 0.05),
                             pooled_event_sd=sd, minimum_detectable_difference_80pct_power=mde)
        else:
            res["P1"] = dict(events_high_mid=len(grp["hm"]), events_low=len(grp["low"]), note="fewer than 3 events in a group: not testable")
    # ------------------------------------------------ H5
    e4 = {}
    for f in sorted(out.glob("e4_*.json")):
        r = json.loads(f.read_text())
        e4[r["model"]] = r["rows"]
    if e4:
        def rate(rows, arm, kind):
            per = {}
            for x_ in rows:
                if x_["arm"] != arm or x_["kind"] != kind or by[x_["event"]].get("audit") not in ("EXPLICIT", "NA"):
                    continue
                per.setdefault(x_["event"], []).append(int(x_["answer"] == (x_["identity"] if kind in ("pre", "post") else x_["truth"])))
            return per

        res["H5"] = {}
        for m, rows in list(e4.items()) + [("pooled", [x_ for rr in e4.values() for x_ in rr])]:
            d = {}
            for kind in ("pre", "post", "ctrl"):
                for arm in ("O", "P1", "P2", "P3"):
                    per = rate(rows, arm, kind)
                    d[f"{kind}_{arm}"] = float(np.mean([np.mean(v) for v in per.values()])) if per else None
            pre = {arm: rate(rows, arm, "pre") for arm in ("O", "P1", "P2")}
            common = sorted(set(pre["O"]) & set(pre["P1"]) & set(pre["P2"]))
            if len(common) >= 3:
                pack = {e: (np.mean(pre["O"][e]), np.mean(pre["P1"][e]), np.mean(pre["P2"][e])) for e in common}
                red, rlo, rhi, _, bs = boot_events(pack, lambda q: float(1 - np.mean([t[2] for t in q]) / max(np.mean([t[0] for t in q]), 1e-9)))
                v1, vlo, vhi, _, _ = boot_events(pack, lambda q: float(np.mean([t[1] - t[2] for t in q])))
                d["premature_reduction_P2_vs_O"] = dict(point=red, ci=[rlo, rhi], O_rate=d["pre_O"])
                d["P2_beats_P1_points"] = dict(point=v1, ci=[vlo, vhi])
                d["p_one_sided_reduction"] = float(sum(1 for b in bs if b <= 0) / len(bs))
            for kind in ("post", "ctrl"):
                a_, b_ = rate(rows, "O", kind), rate(rows, "P2", kind)
                cm = sorted(set(a_) & set(b_))
                if len(cm) >= 3:
                    pk = {e: (np.mean(a_[e]), np.mean(b_[e])) for e in cm}
                    pt, lo, hi, _, _ = boot_events(pk, lambda q: float(np.mean([t[1] - t[0] for t in q])))
                    d[f"utility_{kind}_P2_minus_O"] = dict(point=pt, ci=[lo, hi], noninferior_margin_5pts=bool(lo > -0.05))
            res["H5"][m] = d
        pp = res["H5"].get("pooled", {})
        if "premature_reduction_P2_vs_O" in pp:
            c = pp["premature_reduction_P2_vs_O"]
            pp["H5_counts"] = bool(c["point"] >= 0.5 and c["ci"][0] > 0 and pp.get("utility_post_P2_minus_O", {}).get("noninferior_margin_5pts")
                                   and pp.get("utility_ctrl_P2_minus_O", {}).get("noninferior_margin_5pts")
                                   and pp["P2_beats_P1_points"]["point"] >= 0.05 and pp["P2_beats_P1_points"]["ci"][0] > 0)
            ps["H5"] = pp["p_one_sided_reduction"]
    if ps:
        res["raw_p"] = ps
        res["holm_adjusted_p"] = holm(ps)
    # ------------------------------------------------ E5
    e5 = {}
    for f in sorted(out.glob("e5_*.json")):
        r = json.loads(f.read_text())
        e5[r["model"]] = r
    if e5:
        res["E5"] = dict(events=max(r["events"] for r in e5.values()), per_model={})
        for cond in ("O", "P1", "P2"):
            per = {}
            for r in e5.values():
                for x_ in r["rows"]:
                    if x_["cond"] == cond:
                        per.setdefault(x_["event"], []).append(int(x_["spoiler"]))
            if per:
                pt, lo, hi, _, _ = boot_events(per, lambda q: float(np.mean([np.mean(t) for t in q])))
                res["E5"][f"spoiler_rate_{cond}"] = dict(point=pt, ci=[lo, hi], events=len(per))
        for m, r in e5.items():
            for cond in ("O", "P1", "P2"):
                v = [int(x_["spoiler"]) for x_ in r["rows"] if x_["cond"] == cond]
                res["E5"]["per_model"].setdefault(m, {})[cond] = dict(spoiler_rate=float(np.mean(v)) if v else None, outputs=len(v))
        faith = {}
        for f in sorted(out.glob("e5judge_*.json")):
            for x_ in json.loads(f.read_text())["rows"]:
                if x_["supported"] is None or x_["unsupported"] is None:
                    continue
                d = faith.setdefault(x_["cond"], [0, 0])
                d[0] += x_["supported"]
                d[1] += x_["unsupported"]
        res["E5"]["faithfulness_supported_share"] = {c: (v[0] / (v[0] + v[1]) if v[0] + v[1] else None) for c, v in faith.items()}
    (out / "analysis.json").write_text(json.dumps(res, indent=1, default=float))
    # ------------------------------------------------ print
    print(f"events {res['n_events']} (test {res['n_test']}, primary test {res['n_primary_test']}); models {res['models']}")
    for m, d in res["per_model"].items():
        p = d.get("primary_test", {})
        if "gap_A_minus_B" in p:
            print(f"{m:20s} gap A-B {100 * p['gap_A_minus_B']:+.1f} {ci_str(*p['ci'])} | A-B3 {100 * p['gap_A_minus_B3']:+.1f} | R {p['recovered_fraction']:+.2f} | "
                  f"+{p['events_pos']}/-{p['events_neg']} (n={p['events']}) | G2a {d['G2a_B_eq_B2']} invalid {d['invalid_share']}")
    for k in ("P1", "H1", "H2", "H3"):
        if k in res:
            print(k, json.dumps(res[k], default=float)[:420])
    if "H5" in res and "pooled" in res["H5"]:
        print("H5 pooled", json.dumps(res["H5"]["pooled"], default=float)[:700])
    if "E5" in res:
        print("E5", json.dumps(res["E5"], default=float)[:700])
    if "holm_adjusted_p" in res:
        print("Holm", res["holm_adjusted_p"])


if __name__ == "__main__":
    main()
