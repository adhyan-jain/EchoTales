"""Print the Channel 1 markdown tables for the merged paper from stored result JSON (no model calls, no network).

Callers: run by hand after pd_confirm_analyze.py has written confirm/{main,e2}/analysis.json; output is pasted into
docs/research/PAPER/READER_FAITHFULNESS.md. Reads: confirm/main/analysis.json, confirm/e2/analysis.json, confirm/main/olmo_corpus_check.json.
Every number is printed with its split and label provenance; a missing key prints "n/a" rather than failing, so a partial run still renders.
Gaps are stored as fractions and printed in percentage points.
"""
from __future__ import annotations

import json
from pathlib import Path

D = Path(__file__).resolve().parents[2] / "data" / "eval" / "chimera" / "confirm"


def pts(x):
    return "n/a" if x is None or x != x else f"{100 * x:+.1f}"


def ci(c):
    return "n/a" if not c else f"[{100 * c[0]:+.1f}, {100 * c[1]:+.1f}]"


def load(p):
    p = D / p
    return json.loads(p.read_text()) if p.exists() else {}


def main():
    m, e2, oc = load("main/analysis.json"), load("e2/analysis.json"), load("main/olmo_corpus_check.json")
    print(f"Label provenance: {m.get('label_provenance')}. Events {m.get('n_events')} (test {m.get('n_test')}, primary EXPLICIT test {m.get('n_primary_test')}).\n")
    print("Table C1. Per-model prefix gap on the primary test set (percentage points, 95% event-bootstrap interval)\n")
    print("| Model | Events | Gap A-B | CI | Gap A-B3 | Events +/- | Sign p (1-sided) | Control acc A / B / B3 | G2a |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, r in m.get("per_model", {}).items():
        p, c = r.get("primary_test", {}), r.get("ctrl_acc", {})
        print(f"| {name} | {p.get('events')} | {pts(p.get('gap_A_minus_B'))} | {ci(p.get('ci'))} | {pts(p.get('gap_A_minus_B3'))} | "
              f"{p.get('events_pos')}/{p.get('events_neg')} | {p.get('sign_p_one_sided')} | {c.get('A')} / {c.get('B')} / {c.get('B3')} | {r.get('G2a_B_eq_B2')} |")
    print("\nTable C2. Pre-registered tests\n")
    print("| Test | Estimate | CI | One-sided p | Passed | Note |")
    print("|---|---|---|---|---|---|")
    for k in ("H1", "H2"):
        h = m.get(k)
        if h:
            est = h.get("pooled", h.get("pooled_A_minus_B3"))
            print(f"| {k} | {pts(est)} | {ci(h.get('ci'))} | {h.get('p_one_sided')} | {h.get('passes', 'n/a')} | models {m.get('h1_h2_models')} |")
        else:
            print(f"| {k} | n/a | n/a | n/a | not evaluable | fewer than the required models in the pooled set |")
    h3 = m.get("H3", {})
    print(f"| H3 (fame dose-response, Spearman) | {h3.get('spearman')} | n/a | {h3.get('perm_p_one_sided')} | {h3.get('passes')} | {h3.get('events')} events, {h3.get('books')} books |")
    p1 = m.get("P1", {})
    print(f"| P1 (gap high+mid minus low) | {pts(p1.get('difference'))} | {ci(p1.get('ci'))} | {p1.get('p_one_sided')} | {p1.get('passes')} | "
          f"{p1.get('events_high_mid')} vs {p1.get('events_low')} events; minimum detectable {pts(p1.get('minimum_detectable_difference_80pct_power'))} pts |")
    print("\nTable C3. Gap by fame band (primary test set, mean per event)\n")
    print("| Band | Events | Mean gap (pts) |\n|---|---|---|")
    for b in ("high", "mid", "low"):
        g = m.get("gap_by_fame_band", {}).get(b, {})
        print(f"| {b} | {g.get('events')} | {pts(g.get('mean_gap'))} |")
    h5, e5 = m.get("H5", {}), m.get("E5", {})
    if h5:
        print("\nTable C4. E4 pseudonymisation mitigation (H5)\n")
        print("| Scope | Detail |\n|---|---|")
        for k, v in h5.items():
            print(f"| {k} | {json.dumps(v, default=float)[:400]} |")
    if e5:
        print("\nTable C5. E5 recap spoiler (exploratory, small n)\n")
        print("| Item | Value |\n|---|---|")
        for k, v in e5.items():
            print(f"| {k} | {json.dumps(v, default=float)[:400]} |")
    if e2:
        print("\nTable C6. E2 unseen LLM-authored stories (exploratory, underpowered)\n")
        print("| Model | Events | Gap A-B | CI |\n|---|---|---|---|")
        for name, r in e2.get("per_model", {}).items():
            p = r.get("primary_test", r.get("all_verified_test", {}))
            print(f"| {name} | {p.get('events')} | {pts(p.get('gap_A_minus_B'))} | {ci(p.get('ci'))} |")
    if oc:
        print("\nTable C7. OLMo-2 training-data presence vs gap (exploratory; infini-gram index " + str(oc.get("index")) + ")\n")
        print(f"Books queried {oc.get('books_queried')}, with a gap {oc.get('books_with_gap')}; presence-score distribution {oc.get('score_distribution')}; "
              f"Spearman {oc.get('spearman')}, permutation p (two-sided) {oc.get('perm_p_two_sided')}; mean gap present {pts(oc.get('mean_gap_present'))} vs absent {pts(oc.get('mean_gap_absent'))} pts.")


if __name__ == "__main__":
    main()
