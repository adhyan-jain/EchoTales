"""Pooled, event-cluster view of ALL PD leakage data (v2, v3, v6), including the v6 result that did not replicate.

Read-only over stored runs (no model calls). For each dataset a model is "G2-valid" if B-vs-B2 agreement on that dataset's
real plain controls >= 90% and its synthetic A-vs-B agreement (PD v3 run, same 62 items) >= 80%. Arms: A original, B = mean
of the two cipher arms, B3 = cue-preserving pseudonyms (v2/v3 B3 from the PD v5 runs, v6 B3 from the v6 runs).
Resampling unit = event (5,000 resamples, seed 20261019). Output: data/eval/chimera/pd_final_pooled.json.
"""
import json
import math
import random
from pathlib import Path

ROOT = Path("data/eval/chimera")
SEED = 20261019


def runs(ver):
    out = {}
    for f in sorted((ROOT / ver).glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            out[r["model"]] = r
    return out


V2, V3, V6 = runs("pd_v2"), runs("pd_v3"), runs("pd_v6")
V5 = {m: r["B3"] for m, r in runs("pd_v5").items()}


def synth_ok(m):
    r = V3.get(m)
    if not r:
        return None
    S = r["synth_truth"]
    sp = [i for i, t in S.items() if t["type"] != "pre_alias"]
    return sum(r["synth"][i]["A"] == r["synth"][i]["B"] for i in sp) / len(sp)


def g2a(r):
    T = r["truth"]
    ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
    return sum(r["real"][i]["B"] == r["real"][i]["B2"] for i in ctrl) / len(ctrl)


def rows(r, b3_src):
    T = r["truth"]
    out = {}
    for i, t in T.items():
        if t["kind"] != "pre":
            continue

        def h(arm, i=i, t=t):
            return int(r["real"][i][arm] == t["identity_letter"])

        b3v = b3_src(i)
        out.setdefault(t["event"], []).append(dict(A=h("A"), B=(h("B") + h("B2")) / 2,
                                                   B3=None if b3v is None else int(b3v == t["identity_letter"])))
    return out


def quant(vals, f):
    v = sorted(x for x in vals if not math.isnan(x))
    return round(v[int(f * len(v))], 4) if v else None


def stat(per_event):
    evs = sorted(per_event)

    def calc(es):
        rs = [x for e in es for x in per_event[e]]
        a = sum(x["A"] for x in rs) / len(rs)
        b = sum(x["B"] for x in rs) / len(rs)
        rb3 = [x["B3"] for x in rs if x["B3"] is not None]
        return a - b, (a - sum(rb3) / len(rb3)) if rb3 else float("nan")

    pt = calc(evs)
    rng = random.Random(SEED)
    bs = [calc([rng.choice(evs) for _ in evs]) for _ in range(5000)]
    pos = sum(1 for e in evs if sum(x["A"] - x["B"] for x in per_event[e]) > 0)
    neg = sum(1 for e in evs if sum(x["A"] - x["B"] for x in per_event[e]) < 0)
    n, k = pos + neg, min(pos, neg)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n) if n else 1.0
    return dict(events=len(evs), gap_A_minus_B=round(pt[0], 4), ci=[quant([x[0] for x in bs], 0.025), quant([x[0] for x in bs], 0.975)],
                gap_A_minus_B3=None if math.isnan(pt[1]) else round(pt[1], 4),
                ci_B3=[quant([x[1] for x in bs], 0.025), quant([x[1] for x in bs], 0.975)],
                events_positive=pos, events_negative=neg, sign_p=round(p, 5))


def b3_source(ds, m, r):
    if ds == "v6":
        return lambda i: r["real"][i].get("B3")
    return lambda i: V5[m].get(i) if m in V5 else None


def pool(selector, datasets):
    pe = {}
    for ds in datasets:
        for m, r in {"v2": V2, "v3": V3, "v6": V6}[ds].items():
            if selector(ds, m, r):
                for e, v in rows(r, b3_source(ds, m, r)).items():
                    pe.setdefault(e, []).extend(v)
    return stat(pe) if pe else None


def valid(ds, m, r):
    s = synth_ok(m)
    return s is not None and g2a(r) >= 0.90 and s >= 0.80


def main():
    out = dict(note="Read-only pooled view of all PD leakage data; event-cluster; includes the PD v6 result that did not replicate.")
    out["per_dataset_valid_models"] = {ds: sorted(m for m, r in d.items() if valid(ds, m, r))
                                       for ds, d in (("v2", V2), ("v3", V3), ("v6", V6))}
    sets = (("v2", ["v2"]), ("v3", ["v3"]), ("v6", ["v6"]), ("fresh_v3_v6", ["v3", "v6"]), ("all_v2_v3_v6", ["v2", "v3", "v6"]))
    out["valid_pool"] = {name: pool(valid, ds) for name, ds in sets}
    out["luna_only"] = {name: pool(lambda ds, m, r: m == "gpt-5.6-luna", ds) for name, ds in sets}
    out["all_models_g2a80"] = {name: pool(lambda ds, m, r: g2a(r) >= 0.80 and (synth_ok(m) or 0) >= 0.80, ds)
                               for name, ds in sets if name in ("v6", "fresh_v3_v6", "all_v2_v3_v6")}
    out["v6_per_model"] = {m: dict(g2a_v6=round(g2a(r), 3), synth_v3=None if synth_ok(m) is None else round(synth_ok(m), 3),
                                   cluster=stat(rows(r, lambda i, r=r: r["real"][i].get("B3")))) for m, r in V6.items()}
    Path(ROOT / "pd_final_pooled.json").write_text(json.dumps(out, indent=1))
    print("valid models:", out["per_dataset_valid_models"])
    for k in ("valid_pool", "luna_only", "all_models_g2a80"):
        for name, v in out[k].items():
            print(k, name, v)


if __name__ == "__main__":
    main()
