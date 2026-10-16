"""Checks prompted by an external adversarial review of the PD leakage claims (2026-10-16). No model calls; reads the stored
PD v2 and v3 runs. POST HOC, descriptive.

(1) Cluster-correct inference. Earlier scripts bootstrapped ITEMS, but items within an event share one reveal, one book and
    one cast, so they are not independent. Here the resampling unit is the EVENT, and an event-level sign test is reported.
(2) Gate-threshold sweep. The memory-free gate G2 (B-vs-B2 on real controls, A-vs-B on unseen synthetic items) was chosen
    after the gaps were seen; the pooled gap is recomputed for G2a from 70% to 95% (G2b fixed at 80%) to show how much the
    conclusion depends on the bar.
(3) Competence floor. Per (model, event) pair, keep only events where the model answers that event's plain controls
    correctly in BOTH arms at least 75% of the time, so that renaming did not wreck comprehension of that book; the gap on
    the surviving pairs is a partial answer to the cue-loss objection (it cannot remove cue loss that leaves accuracy intact).
Output: data/eval/chimera/pd_adversarial_checks.json.
"""
import json
import math
import random
from pathlib import Path

ROOT = Path("data/eval/chimera")
BOOT, SEED = 5000, 20261016


def load(ver):
    runs = {}
    for f in sorted((ROOT / ver).glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            runs[r["model"]] = r
    return runs


def g2(r):
    T, S = r["truth"], r["synth_truth"]
    ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
    sp = [i for i, t in S.items() if t["type"] != "pre_alias"]
    return (sum(r["real"][i]["B"] == r["real"][i]["B2"] for i in ctrl) / len(ctrl),
            sum(r["synth"][i]["A"] == r["synth"][i]["B"] for i in sp) / len(sp))


def diffs(r, keep=None):
    """item diffs (A minus mean of B, B2) grouped by event; keep(event) -> bool filters events."""
    out = {}
    T = r["truth"]
    for i, t in T.items():
        if t["kind"] != "pre" or (keep and not keep(t["event"])):
            continue
        a = int(r["real"][i]["A"] == t["identity_letter"])
        b = (int(r["real"][i]["B"] == t["identity_letter"]) + int(r["real"][i]["B2"] == t["identity_letter"])) / 2
        out.setdefault(t["event"], []).append(a - b)
    return out


def cluster_stat(by_event):
    """pooled gap (mean over all item diffs) with an EVENT-level bootstrap CI, and the event-level sign test."""
    evs = sorted(by_event)
    if not evs:
        return None

    def pooled(es):
        n = sum(len(by_event[e]) for e in es)
        return sum(x for e in es for x in by_event[e]) / n

    rng = random.Random(SEED)
    bs = sorted(pooled([rng.choice(evs) for _ in evs]) for _ in range(BOOT))
    ev_mean = {e: sum(v) / len(v) for e, v in by_event.items()}
    pos = sum(m > 0 for m in ev_mean.values())
    neg = sum(m < 0 for m in ev_mean.values())
    n = pos + neg
    k = min(pos, neg)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n) if n else 1.0
    return dict(events=len(evs), items=sum(len(v) for v in by_event.values()), pooled_gap=round(pooled(evs), 4),
                event_cluster_ci95=[round(bs[int(0.025 * BOOT)], 4), round(bs[int(0.975 * BOOT)], 4)],
                events_positive=pos, events_negative=neg, events_zero=len(evs) - n, event_sign_test_p=round(p, 5))


def merge(list_of_by_event):
    """pool (model, item) diffs per event across models."""
    out = {}
    for d in list_of_by_event:
        for e, v in d.items():
            out.setdefault(e, []).extend(v)
    return out


def main():
    out = dict(note="POST HOC, descriptive; event-cluster bootstrap (5,000 resamples of events, seed 20261016).")
    for ver in ("pd_v2", "pd_v3"):
        runs = load(ver)
        res = dict(per_model_cluster={m: cluster_stat(diffs(r)) for m, r in runs.items()}, g2a_sweep={}, competence_floor={})
        for bar in (0.70, 0.75, 0.80, 0.85, 0.90, 0.95):
            ok = [m for m, r in runs.items() if g2(r)[0] >= bar and g2(r)[1] >= 0.80]
            res["g2a_sweep"][str(bar)] = dict(models=sorted(ok), **(cluster_stat(merge([diffs(runs[m]) for m in ok])) or {}))
        for tag, pool in (("all_models", list(runs)),
                          ("G2_valid_models", [m for m, r in runs.items() if g2(r)[0] >= 0.90 and g2(r)[1] >= 0.80])):
            parts, kept_pairs, total_pairs = [], 0, 0
            for m in pool:
                r = runs[m]
                T = r["truth"]
                good = set()
                for e in sorted({t["event"] for t in T.values()}):
                    ctrl = [i for i, t in T.items() if t["kind"] == "ctrl" and t["event"] == e]
                    total_pairs += 1
                    accs = [sum(r["real"][i][arm] == T[i]["truth_letter"] for i in ctrl) / len(ctrl) for arm in ("A", "B", "B2")]
                    if min(accs) >= 0.75:
                        good.add(e)
                        kept_pairs += 1
                parts.append(diffs(r, keep=lambda e, g=good: e in g))
            st = cluster_stat(merge(parts))
            res["competence_floor"][tag] = dict(model_event_pairs_kept=kept_pairs, model_event_pairs_total=total_pairs, **(st or {}))
        out[ver] = res
    # combined over both datasets (31 distinct events): G2-valid local pool, G2-valid pool incl. Luna if valid, and Luna alone
    comb = {}
    for tag, sel in (("G2_valid_models", lambda m, r: g2(r)[0] >= 0.90 and g2(r)[1] >= 0.80),
                     ("luna_only", lambda m, r: m == "gpt-5.6-luna"),
                     ("all_models_G2a_80", lambda m, r: g2(r)[0] >= 0.80 and g2(r)[1] >= 0.80)):
        parts = [diffs(r) for ver in ("pd_v2", "pd_v3") for m, r in load(ver).items() if sel(m, r)]
        comb[tag] = cluster_stat(merge(parts))
    out["combined_v2_v3_31_events"] = comb
    # sensitivity: keep only events an independent model (label audit) judged EXPLICIT from the reveal passage
    audit_path = ROOT / "pd_label_audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        sens = {}
        for who, a in audit.items():
            explicit = {e for e, v in a["verdicts"].items() if v == "EXPLICIT"}
            for tag, sel in (("G2_valid_models", lambda m, r: g2(r)[0] >= 0.90 and g2(r)[1] >= 0.80),
                             ("luna_only", lambda m, r: m == "gpt-5.6-luna")):
                parts = [diffs(r, keep=lambda e, ex=explicit: e in ex) for ver in ("pd_v2", "pd_v3")
                         for m, r in load(ver).items() if sel(m, r)]
                st = cluster_stat(merge(parts))
                sens[f"{who}|explicit_only|{tag}"] = dict(explicit_events=len(explicit), **(st or {}))
        out["label_audit_sensitivity"] = sens
        for k, s in sens.items():
            print("label-audit", k, s)
    (ROOT / "pd_adversarial_checks.json").write_text(json.dumps(out, indent=1))
    for tag, s in comb.items():
        print("combined", tag, s)
    for ver in ("pd_v2", "pd_v3"):
        print("==", ver)
        for m, s in out[ver]["per_model_cluster"].items():
            print(f"  {m:22s} gap {s['pooled_gap']:+.3f} eventCI {s['event_cluster_ci95']} events +{s['events_positive']}/-{s['events_negative']}/0:{s['events_zero']} p={s['event_sign_test_p']}")
        for bar, s in out[ver]["g2a_sweep"].items():
            print(f"  G2a>={bar}: models {len(s.get('models', []))} gap {s.get('pooled_gap')} CI {s.get('event_cluster_ci95')} +{s.get('events_positive')}/-{s.get('events_negative')} p={s.get('event_sign_test_p')}")
        for tag, s in out[ver]["competence_floor"].items():
            print(f"  floor {tag}: pairs {s['model_event_pairs_kept']}/{s['model_event_pairs_total']} gap {s.get('pooled_gap')} CI {s.get('event_cluster_ci95')} events {s.get('events')} +{s.get('events_positive')}/-{s.get('events_negative')} p={s.get('event_sign_test_p')}")


if __name__ == "__main__":
    main()
