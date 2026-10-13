"""H-XDIS-ALIAS (convergence pass C1): re-score the saved H-XDIS trials with
PDNC gold speakers canonicalised through PDNC's own alias lists.

H-GATE-XDIS found 58/1000 gold labels that are name variants ("Kemp",
"Lucy", "Dorian Gray") rather than character-list main names. The probe
scores `q.speaker in owners` against the raw string, so the ladder was scored
wrong on all 58 and the LLM -- whose shortlist kept main names only -- could
not pick the gold either. 58 of the 160 "errors" may be that artifact.

The rule (docs/research/CONVERGENCE.md, C1) was frozen before any
corrected number: main name; else a unique exact-lowercase alias match; else a
unique `comparison_key` match; else UNSCORABLE (excluded, counted). Exact
before normalised because `comparison_key` strips honorifics and turns "Miss
Tendril" into "Mr Tendril" -- 4 ambiguous rows under a one-step rule, 0 under
the tiered one (an input count, disclosed).

CPU only; no LLM call. The H-GATE-XDIS analysis is reused verbatim
(`gate_xdis.analyse`) so the only difference from the original is the labels.
"""

from __future__ import annotations

import json

from echotales.research.config import ExperimentConfig
from echotales.research.experiments import gate_xdis as gx
from echotales.research.schema import RunResult

HYPOTHESIS_ID = "H-XDIS-ALIAS"
DEFAULT_PARAMS = {
    "source_run": "data/eval/research/H-XDIS/real-6f97e4d14f536dfe",
    "candidates_window": 20,
    "rates": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
    "primary_rates": [0.10, 0.20],
    "resamples": 2000,
}


def canon(gold: str, characters: dict) -> str | None:
    """PDNC raw gold string -> unique main name, or None (UNSCORABLE)."""
    from echotales.pipeline.ingest.normalize import comparison_key

    if gold in characters:
        return gold
    forms = [(c.name, f) for c in characters.values() for f in (c.name, *c.aliases)]
    exact = {name for name, f in forms if f.lower() == gold.lower()}
    if exact:
        return next(iter(exact)) if len(exact) == 1 else None
    key = comparison_key(gold)
    norm = {name for name, f in forms if key and comparison_key(f) == key}
    return next(iter(norm)) if len(norm) == 1 else None


def relabel(rows: list[dict], novels: dict) -> tuple[list[dict], list[dict], int]:
    """Apply `canon` to re-derived rows: (scorable rows, change log, #dropped)."""
    out, changes, dropped = [], [], 0
    for r in rows:
        nv = novels[r["novel"]]
        c = canon(r["gold"], nv.characters)
        if c is None:
            dropped += 1
            changes.append({"unit": r["unit"], "gold_raw": r["gold"], "canon": None,
                            "reason": "UNSCORABLE: no unique alias match; excluded"})
            continue
        err = c not in r["owners"]
        llm_ok = r["llm"] == c
        if err != r["err"] or llm_ok != r["llm_correct"]:
            changes.append({
                "unit": r["unit"], "gold_raw": r["gold"], "canon": c, "owners": r["owners"],
                "llm": r["llm"], "ladder_err": [r["err"], err], "llm_correct": [r["llm_correct"], llm_ok],
                "disagree": r["disagree"], "canon_in_llm_shortlist": bool(r.get("_canon_in_cands")),
                "reason": f"gold {r['gold']!r} is a PDNC alias of {c!r}",
            })
        out.append({**r, "gold_raw": r["gold"], "gold": c, "err": err, "llm_correct": llm_ok,
                    "gold_in_shortlist": bool(r.get("_canon_in_cands")),
                    "gender_gold": nv.gender_of(c),
                    # H-CAL's definition, recomputed under the canonical gold.
                    "addressee_capture": bool(err and set(r["owners"]) & set(r.get("_addressees", ())))})
    return out, changes, dropped


def _rederive_with_cands(rows: list[dict], window: int) -> tuple[dict, dict]:
    """gate_xdis._rederive (exact-match gate) plus what C1 needs and it does
    not keep: whether canon(gold) was in the LLM's shortlist, and the quote's
    canonicalised gold addressees."""
    from echotales.research.datasets import pdnc

    gate = gx._rederive(rows, window)
    novels = {name: pdnc.load_novel(name) for name in sorted({r["novel"] for r in rows})}
    for r in rows:
        nv = novels[r["novel"]]
        q = next(x for x in nv.quotes if x.id == r["qid"])
        near = [x for x in nv.quotes if abs(x.index - q.index) <= window]
        cands = sorted({x.speaker for x in near} | {a for x in near for a in x.addressees}
                       | set(r["owners"]))
        cands = [c for c in cands if c in nv.characters]
        c = canon(r["gold"], nv.characters)
        r["_canon_in_cands"] = bool(c and c in cands)
        r["_addressees"] = tuple(canon(a, nv.characters) or a for a in q.addressees)
    return gate, novels


def _stub_rows(seed: int) -> tuple[list[dict], dict]:
    from echotales.research.datasets.pdnc import Character

    rows = gx._synthetic(seed)
    chars = {"A": Character("A", "A", ("Al",), "M", "major"), "B": Character("B", "B", ("Bea",), "F", "major")}

    class _Nv:
        characters = chars

        @staticmethod
        def gender_of(n):
            return chars[n].gender if n in chars else "U"

    for i, r in enumerate(rows):
        if r["gold"] == "B" and i % 3 == 0:  # an alias-named gold, so relabel runs
            r["gold"], r["err"], r["owners"] = "Bea", True, ["B"]
        r["_canon_in_cands"] = True
    return rows, {r["novel"]: _Nv for r in rows}


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    if stub:
        rows, novels = _stub_rows(cfg.base_seed)
        gate = {"checked": len(rows), "mismatches": []}
        inputs = {}
    else:
        source = gx.ROOT / p["source_run"]
        rows = gx._load_saved(source)
        gate, novels = _rederive_with_cands(rows, int(p["candidates_window"]))
        if gate["mismatches"]:
            raise RuntimeError(f"exact-match gate failed on {len(gate['mismatches'])} rows")
        inputs = {"source_trials": source / "trials.jsonl"}
    n_orig, err_orig = len(rows), sum(r["err"] for r in rows)
    relabelled, changes, dropped = relabel(rows, novels)
    summary, _curves, hint, trials = gx.analyse(relabelled, p, cfg.base_seed, stub, gate=gate)
    summary.update({
        "original_n": n_orig, "original_errors": int(err_orig), "unscorable_dropped": dropped,
        "rows_changed": len(changes),
        "flips": {"ladder_err_to_correct": sum(c.get("ladder_err") == [True, False] for c in changes),
                  "ladder_correct_to_err": sum(c.get("ladder_err") == [False, True] for c in changes),
                  "llm_wrong_to_right": sum(c.get("llm_correct") == [False, True] for c in changes),
                  "llm_right_to_wrong": sum(c.get("llm_correct") == [True, False] for c in changes)},
        "canon_gold_in_llm_shortlist": round(sum(r["gold_in_shortlist"] for r in relabelled)
                                             / max(1, len(relabelled)), 4),
        "changed_rows": changes,
    })
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="xdis_alias_rescore",
                      mode="stub" if stub else "real", config_hash=cfg.hash, n_units=len(relabelled),
                      n_trials=len(trials), summary=json.loads(json.dumps(summary)),
                      verdict_hint="alias-corrected " + hint,
                      notes=["tiered alias rule frozen in CONVERGENCE.md C1",
                             "LLM outputs fixed from H-XDIS; only labels change",
                             "addressee_capture recomputed under canonical gold",
                             "changed_rows lists every row whose ladder or LLM correctness changed"]),
            trials, inputs)
