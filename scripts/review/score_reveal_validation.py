"""Score the human reveal-validation labels (journal Revision 1, major issue 5).

Why this exists: the paper may only say that the text oracle is "human-validated" to the extent these numbers allow,
so the script reports what the two annotators per event agreed on, how often each check failed, and whether the
headline gaps survive dropping the events people flagged. Agreement is Fleiss' kappa with two raters per event (three
annotators in rotation, so "rater 1" and "rater 2" are not the same people across events and Cohen's kappa would
mislabel the design). Proportions carry Wilson 95% intervals; the gap sensitivities reuse the stored-run code of
pd_final_pooled.py (item-pooled, event-cluster bootstrap) and pd_confirm_analyze.py (event-weighted per model,
DerSimonian-Laird with Hartung-Knapp across models) so they are the same estimands as the paper's main numbers.

Inputs : scripts/review/reveal_validation_app/events.json, data/eval/validation/reveal_labels/labels_*.json
Output : data/eval/validation/reveal_human_v1.json
Run    : python scripts/review/score_reveal_validation.py [--labels DIR] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chimera"))

EVENTS = Path("scripts/review/reveal_validation_app/events.json")
LABELS = Path("data/eval/validation/reveal_labels")
OUT = Path("data/eval/validation/reveal_human_v1.json")
CONFIRM_EVENTS = Path("docs/research/preregistrations/PD_confirm_events_v1.json")
LABEL_AUDIT = Path("data/eval/chimera/pd_label_audit.json")
Q = {"q0": ["yes", "no"], "q1": ["explicit", "implied", "no"], "q2": ["revelation", "reminder", "cant_tell"],
     "q3": ["no", "suspect", "confident"], "q4": ["yes", "no"]}


def wilson(k: int, n: int, z: float = 1.959964):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return dict(k=k, n=n, rate=round(p, 4), ci=[round(c - h, 4), round(c + h, 4)])


def fleiss(pairs: list[tuple[str, str]], cats: list[str]):
    """Fleiss' kappa for items rated by exactly two raters each."""
    if not pairs:
        return None
    n, N = 2, len(pairs)
    tot = Counter(c for p in pairs for c in p)
    pj = {c: tot[c] / (N * n) for c in cats}
    Pi = [(sum(v * v for v in Counter(p).values()) - n) / (n * (n - 1)) for p in pairs]
    Pbar, Pe = sum(Pi) / N, sum(v * v for v in pj.values())
    kappa = None if Pe >= 1 else round((Pbar - Pe) / (1 - Pe), 3)
    return dict(kappa=kappa, raw_agreement=round(sum(a == b for a, b in pairs) / N, 3), events=N)


def load_labels(d: Path, events: dict):
    per_event = {k: {} for k in events}
    files = sorted(d.glob("labels_*.json"))
    if not files:
        sys.exit(f"REFUSING: no labels_*.json in {d}")
    for f in files:
        x = json.loads(f.read_text())
        if x.get("app") != "reveal-check":
            sys.exit(f"REFUSING: {f.name} is not a Reveal Check export")
        for key, row in x["labels"].items():
            if key not in events or x["annotator"] not in events[key]["annotators"]:
                sys.exit(f"REFUSING: {f.name} labels {key}, which was not assigned to {x['annotator']}")
            if all(row.get(q) for q in Q):
                per_event[key][x["annotator"]] = row
    return per_event, [f.name for f in files]


def model_audit():
    """Model verdicts the annotators never saw: confirmatory events carry the open-model audit; exploratory events the
    reference-model label audit (pd_label_audit.json)."""
    out = {e["id"]: e["audit"] for e in json.loads(CONFIRM_EVENTS.read_text())["events"]}
    if LABEL_AUDIT.exists():
        for m in json.loads(LABEL_AUDIT.read_text()).values():
            for ev, v in m.get("verdicts", {}).items():
                out.setdefault(ev, v.get("verdict") if isinstance(v, dict) else v)
    return out


def gap_sensitivity(keep_exploratory: set[str], keep_confirm: set[str]):
    """Headline gaps restricted to an event subset, with the paper's own estimators."""
    import pd_confirm_analyze as CA
    import pd_final_pooled as FP

    pe = {}
    for ds, runs in (("v2", FP.V2), ("v3", FP.V3), ("v6", FP.V6)):
        r = runs.get("gpt-5.6-luna")
        if r:
            for e, v in FP.rows(r, FP.b3_source(ds, "gpt-5.6-luna", r)).items():
                if e in keep_exploratory:
                    pe.setdefault(e, []).extend(v)
    ref = FP.stat(pe) if len(pe) >= 3 else None
    by = {e["id"]: e for e in json.loads(CONFIRM_EVENTS.read_text())["events"]}
    ys, vs, per_model = [], [], {}
    for m, r in CA.load_e1(CA.OUT / "main").items():
        rows = {e: v for e, v in CA.event_rows(r, by, "test", True).items() if e in keep_confirm}
        if len(rows) < 3:
            continue
        pt, lo, hi, var, _ = CA.boot_events(rows, CA.gap_stat("B"))
        per_model[m] = dict(events=len(rows), gap_A_minus_B=round(pt, 4), ci=[round(lo, 4), round(hi, 4)])
        ys.append(pt)
        vs.append(max(var, 1e-6))
    pooled = None
    if len(ys) >= 2:
        th, lo, hi, tau2, p = CA.dl_hk(ys, vs)
        pooled = dict(pooled=round(th, 4), ci=[round(lo, 4), round(hi, 4)], models=len(ys))
    return dict(reference_model_exploratory=ref, confirmatory_per_model=per_model, confirmatory_H1_pooled=pooled)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=str(LABELS))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-gaps", action="store_true", help="skip the stored-run sensitivity (for synthetic tests)")
    a = ap.parse_args()
    data = json.loads(EVENTS.read_text())
    events = {e["key"]: e for e in data["events"]}
    per_event, files = load_labels(Path(a.labels), events)
    full = {k: v for k, v in per_event.items() if len(v) == 2}

    res = dict(label_provenance="HUMAN: three author-annotators, two per event, blind to model labels; public-domain events only",
               item_set=data["version"], files=files, events_total=len(events),
               events_double_labelled=len(full), events_single_labelled=sum(len(v) == 1 for v in per_event.values()))
    res["label_distribution"] = {q: dict(Counter(r[q] for v in per_event.values() for r in v.values())) for q in Q}
    res["agreement_fleiss"] = {q: fleiss([tuple(r[q] for r in v.values()) for v in full.values()], cats) for q, cats in Q.items()}

    def both(v, q, val):
        return all(r[q] == val for r in v.values())

    def any_(v, q, val):
        return any(r[q] == val for r in v.values())

    n = len(full)
    vals = list(full.values())
    res["event_level"] = dict(
        reveal_explicit_both=wilson(sum(both(v, "q1", "explicit") for v in vals), n),
        reveal_not_identifying_any=wilson(sum(any_(v, "q1", "no") for v in vals), n),
        revelation_both=wilson(sum(both(v, "q2", "revelation") for v in vals), n),
        reminder_any=wilson(sum(any_(v, "q2", "reminder") for v in vals), n),
        inferable_confident_any=wilson(sum(any_(v, "q3", "confident") for v in vals), n),
        inferable_confident_both=wilson(sum(both(v, "q3", "confident") for v in vals), n),
        valid_both=wilson(sum(both(v, "q4", "yes") for v in vals), n),
        invalid_any=wilson(sum(any_(v, "q4", "no") for v in vals), n),
    )
    by_stratum = {}
    for k, v in full.items():
        s = events[k]["stratum"].split("-")[0]
        by_stratum.setdefault(s, []).append(v)
    res["by_track"] = {s: dict(events=len(vs_), reveal_explicit_both=wilson(sum(both(v, "q1", "explicit") for v in vs_), len(vs_)),
                               inferable_confident_any=wilson(sum(any_(v, "q3", "confident") for v in vs_), len(vs_)),
                               invalid_any=wilson(sum(any_(v, "q4", "no") for v in vs_), len(vs_)))
                       for s, vs_ in sorted(by_stratum.items())}
    labels = [r for v in per_event.values() for r in v.values()]
    knows = [r for r in labels if r["q0"] == "yes"]
    fresh = [r for r in labels if r["q0"] == "no"]
    res["prior_knowledge"] = dict(
        labels_knowing_plot=wilson(len(knows), len(labels)),
        confident_inference_if_known=wilson(sum(r["q3"] == "confident" for r in knows), len(knows)),
        confident_inference_if_not_known=wilson(sum(r["q3"] == "confident" for r in fresh), len(fresh)))
    audit = model_audit()
    exp = [(k, v) for k, v in full.items() if audit.get(events[k]["event_id"]) == "EXPLICIT"]
    res["model_audit_agreement"] = dict(
        note="share of events the model audit called EXPLICIT that both annotators also called explicit",
        explicit_confirmed=wilson(sum(both(v, "q1", "explicit") for _, v in exp), len(exp)))

    flagged = {k for k, v in full.items()
               if any_(v, "q4", "no") or any_(v, "q1", "no") or any_(v, "q3", "confident")}
    res["flagged_events"] = sorted(events[k]["event_id"] for k in flagged)
    if not a.no_gaps:
        sampled_e = {events[k]["event_id"] for k in full if events[k]["stratum"].startswith("exploratory")}
        sampled_c = {events[k]["event_id"] for k in full if events[k]["stratum"].startswith("confirmatory")}
        kept = {events[k]["event_id"] for k in full if k not in flagged}
        res["gap_sensitivity"] = dict(
            rule="drop an event if either annotator said: invalid item, reveal does not identify, or identity confidently inferable before the reveal",
            validated_subset=gap_sensitivity(sampled_e, sampled_c),
            validated_subset_minus_flagged=gap_sensitivity(sampled_e & kept, sampled_c & kept))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("events_double_labelled", "agreement_fleiss", "event_level")}, indent=1))
    print("flagged:", res["flagged_events"])
    print("wrote", a.out)


if __name__ == "__main__":
    main()
