"""H-XDIS-PS (convergence pass C2): does ladder-vs-LLM disagreement still
flag the ladder's errors when the LLM's candidate list is built by the
*product*, not from PDNC gold?

H-XDIS gave qwen the speakers/addressees of the surrounding 20 quotes, read
from PDNC's human annotation -- a list that always contains the true speaker
and nobody else the product could not know about. H-GATE-XDIS's random-pick
control showed the list alone does not produce the gain; it did not show qwen
is as accurate when the list is noisy, incomplete, and full of place names.

Everything about the list is frozen in docs/research/CONVERGENCE.md
C2 and enforced structurally: `product_shortlist` receives text, offsets, the
ladder's own surface and a corpus profile -- no PDNC object. Disagreement is
computed product-side (surface comparison under `comparison_key`), because
the product has no alias index; gold enters only in `_score`.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.experiments import gate_xdis as gx
from echotales.research.experiments.disagreement_posterior import _llm
from echotales.research.experiments.xdis_alias_rescore import canon
from echotales.research.schema import RunResult

HYPOTHESIS_ID = "H-XDIS-PS"
DEFAULT_PARAMS = {
    "n_quotes": 1000, "model": "qwen2.5:7b", "context_chars": 600,  # = H-XDIS
    "window_chars": 2000, "max_cands": 12, "cap_consistency": 0.5,
    "source_run": "data/eval/research/H-XDIS/real-6f97e4d14f536dfe",
    "source_seed": 20261002,  # H-XDIS's base seed, so the sample is identical
    "rates": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
    "primary_rates": [0.10, 0.20],
    "resamples": 2000,
    "llm": True,  # False = build and audit shortlists only (CPU)
}


# --------------------------------------------------------------------------
# product side: no gold anywhere until `_score`


@dataclass
class NovelProfile:
    """Whole-volume statistics the product legitimately has (volume-first
    processing, non-negotiable 6)."""

    text: str
    commonness: object = None
    _cs: dict = field(default_factory=dict)
    _ci: dict = field(default_factory=dict)

    def __post_init__(self):
        from echotales.pipeline.mentions.commonness import CommonnessProfile

        self.commonness = CommonnessProfile(corpus=self.text.casefold())

    def counts(self, s: str) -> tuple[int, int]:
        """(case-sensitive, case-insensitive) whole-word occurrences."""
        if s not in self._cs:
            pat = rf"(?<![\w’']){re.escape(s)}(?![\w’'])"
            self._cs[s] = len(re.findall(pat, self.text))
            self._ci[s] = len(re.findall(pat, self.text, re.I))
        return self._cs[s], self._ci[s]


def comparison_agree(a: str | None, b: str | None) -> bool:
    """Product-side "same person": equal `comparison_key`, or one name's
    tokens a subset of the other's ("Kemp" / "Dr. Kemp")."""
    from echotales.pipeline.ingest.normalize import comparison_key

    if not a or not b:
        return False
    ka, kb = comparison_key(a), comparison_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    ta, tb = set(ka.split()), set(kb.split())
    return ta <= tb or tb <= ta


def product_shortlist(text: str, start: int, end: int, ladder_raw: str | None,
                      profile: NovelProfile, *, window: int = 2000, k: int = 12,
                      cap_consistency: float = 0.5) -> list[str]:
    """CONVERGENCE.md C2, steps 1-6. No gold parameter by design."""
    from echotales.pipeline.ingest.normalize import comparison_key
    from echotales.pipeline.mentions.chapter_ner import plausible_name
    from echotales.pipeline.mentions.ner import HeuristicDetector

    win = text[max(0, start - window):start] + "\n" + text[end:end + window]
    in_win: Counter = Counter()
    for sp in HeuristicDetector().detect(win):
        s = sp.text.strip()
        if not plausible_name(s) or not comparison_key(s):
            continue
        if profile.commonness.is_common_noun(s):
            continue
        cs, ci = profile.counts(s)
        if ci and cs / ci < cap_consistency:
            continue
        in_win[s] += 1
    groups: dict[str, list[str]] = {}
    for s in in_win:
        groups.setdefault(comparison_key(s), []).append(s)
    reps = []
    for forms in groups.values():
        best = max(forms, key=lambda s: (profile.counts(s)[0], s))
        reps.append((sum(in_win[f] for f in forms), profile.counts(best)[0], best))
    reps.sort(key=lambda t: (-t[0], -t[1], t[2]))
    out = [s for _, _, s in reps[:k]]
    if ladder_raw and not any(comparison_key(s) == comparison_key(ladder_raw) for s in out):
        out = out[:k - 1] + [ladder_raw] if len(out) >= k else out + [ladder_raw]
    return sorted(out)


def product_inventory(text: str, profile: NovelProfile, *, min_count: int = 3,
                      cap_consistency: float = 0.5) -> frozenset[str]:
    """S1 (CONVERGENCE.md): the ladder's `known_names` from the
    product's own detector over the whole volume, instead of PDNC's list."""
    from echotales.pipeline.ingest.normalize import comparison_key
    from echotales.pipeline.mentions.chapter_ner import plausible_name
    from echotales.pipeline.mentions.ner import HeuristicDetector
    from echotales.research.transforms.attribution_probe import _NOT_NAME_TOKENS

    out: set[str] = set()
    for s in {sp.text.strip() for sp in HeuristicDetector().detect(text)}:
        if not plausible_name(s) or not comparison_key(s) or profile.commonness.is_common_noun(s):
            continue
        cs, ci = profile.counts(s)
        if cs < min_count or (ci and cs / ci < cap_consistency):
            continue
        out |= {s, s.lower(), comparison_key(s)}
        toks = s.replace(".", " ").split()
        if len(toks) > 1:
            out |= {t for t in toks if t[:1].isupper() and len(t) > 2 and t.lower() not in _NOT_NAME_TOKENS}
    return frozenset(out)


def _parse(raw: str, cands: list[str]) -> str | None:
    return next((c for c in sorted(cands, key=len, reverse=True)
                 if re.search(re.escape(c), raw, re.I)), None)


# --------------------------------------------------------------------------
# sample and scoring


def _sample(base_seed: int, n: int, stub: bool):
    """The H-XDIS sample, re-derived with its own code path and seed."""
    from echotales.research.datasets import pdnc
    from echotales.research.transforms.attribution_probe import probe

    novels = ([pdnc.synthetic_novel(seed=base_seed)] if stub
              else [pdnc.load_novel(x) for x in pdnc.available()])
    pool = []
    for nv in novels:
        qidx = {q.id: q for q in nv.quotes}
        for r in probe(nv):
            if r.resolved and r.owners and r.quote_id in qidx:
                pool.append((nv, qidx[r.quote_id], r))
    rng = random.Random(derive_seed(base_seed, "sample"))
    rng.shuffle(pool)
    return pool[:n if not stub else 40]


def _score(nv, q, r, cands, llm, idx) -> dict:
    """Gold enters here and only here."""
    from echotales.pipeline.ingest.normalize import comparison_key

    def owners(s):
        return (idx.get(s.lower()) or idx.get(comparison_key(s)) or frozenset()) if s else frozenset()

    g = canon(q.speaker, nv.characters) or q.speaker
    adr = {canon(a, nv.characters) or a for a in q.addressees}
    err = g not in r.owners
    return {
        "unit": f"{nv.name}:{q.id}", "novel": nv.name, "qid": q.id, "conf": r.confidence,
        "disagree": llm is None or not comparison_agree(llm, r.predicted_raw),
        "err": err, "owners": list(r.owners), "llm": llm,
        "gold": g, "pred": r.predicted or r.owners[0], "method": r.method,
        "quote_type": r.quote_type.lower(),
        "addressee_capture": bool(err and set(r.owners) & adr), "vocative": bool(r.predicted_in_quote),
        "gender_gold": nv.gender_of(g), "gender_pred": r.gender_pred,
        "n_cands": max(1, len(cands)),
        # C_product_random: how much of the list a uniform pick would agree with
        "owners_in_cands": sum(comparison_agree(c, r.predicted_raw) for c in cands),
        "gold_in_shortlist": any(g in owners(c) for c in cands),
        "llm_correct": g in owners(llm),
        "alias_disagree": llm is None or not (owners(llm) & set(r.owners)),
    }


def run(cfg: ExperimentConfig, *, stub: bool):
    from echotales.pipeline.paths import RESEARCH_SCRATCH_DIR
    from echotales.research.transforms.attribution_probe import alias_index

    p = cfg.params
    sample = _sample(int(p["source_seed"]), int(p["n_quotes"]), stub)
    inputs = {}
    if not stub:
        src = gx.ROOT / p["source_run"]
        saved = [json.loads(x)["unit_id"] for x in (src / "trials.jsonl").read_text().splitlines() if x.strip()]
        if saved != [f"{nv.name}:{q.id}" for nv, q, _ in sample]:
            raise RuntimeError("sample does not reproduce the H-XDIS unit ids")
        inputs = {"source_trials": src / "trials.jsonl"}
    # Answers are cached per unit so an interrupted run resumes instead of
    # re-paying for GPU calls; a changed list invalidates its entry.
    cache_path = RESEARCH_SCRATCH_DIR / "xdis_ps_cache" / f"{p['model'].replace(':', '_')}.jsonl"
    cache = {}
    if not stub and cache_path.exists():
        cache = {d["unit"]: d for d in map(json.loads, cache_path.read_text().splitlines())}
    profiles, idxs, rows, extra = {}, {}, [], []
    s1 = {"changed_prediction": 0, "now_unresolved": 0, "inventory_size": {}}
    if p.get("ladder_inventory", "pdnc") == "product":
        # S1: same units, ladder re-run with a product-built name inventory.
        from echotales.research.transforms.attribution_probe import probe

        by_nv: dict[str, list] = {}
        for nv, q, r in sample:
            by_nv.setdefault(nv.name, []).append((nv, q, r))
        redo = {}
        for name, items in by_nv.items():
            nv = items[0][0]
            profiles[name], idxs[name] = NovelProfile(nv.text), alias_index(nv)
            inv = product_inventory(nv.text, profiles[name])
            s1["inventory_size"][name] = len(inv)
            for pr in probe(nv, [q for _, q, _ in items], known_names=inv):
                redo[(name, pr.quote_id)] = pr
        kept = []
        for nv, q, r in sample:
            r2 = redo.get((nv.name, q.id))
            if r2 is None or not r2.resolved or not r2.owners:
                s1["now_unresolved"] += 1
                continue
            s1["changed_prediction"] += r2.predicted_raw != r.predicted_raw
            kept.append((nv, q, r2))
        sample = kept
    for nv, q, r in sample:
        if nv.name not in profiles:
            profiles[nv.name], idxs[nv.name] = NovelProfile(nv.text), alias_index(nv)
        unit = f"{nv.name}:{q.id}"
        cands = product_shortlist(nv.text, q.start, q.end, r.predicted_raw, profiles[nv.name],
                                  window=int(p["window_chars"]), k=int(p["max_cands"]),
                                  cap_consistency=float(p["cap_consistency"]))
        raw = None
        if stub:
            llm = cands[derive_seed(cfg.base_seed, unit) % len(cands)] if cands else None
        elif not p["llm"]:
            llm = None
        elif unit in cache and cache[unit]["cands"] == cands:
            raw, llm = cache[unit]["raw"], cache[unit]["llm"]
        else:
            lo = max(0, q.start - int(p["context_chars"]))
            hi = min(len(nv.text), q.end + int(p["context_chars"]))
            prompt = (f"Passage:\n{nv.text[lo:hi]}\n\nIn this passage, who speaks the quotation "
                      f"“{q.text[:300]}”?\nChoose exactly one name from this list: "
                      f"{', '.join(cands)}.\nAnswer with the name only.")
            raw = _llm(prompt, p["model"])
            llm = _parse(raw, cands)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with cache_path.open("a") as fh:
                fh.write(json.dumps({"unit": unit, "cands": cands, "raw": raw, "llm": llm}) + "\n")
        rows.append(_score(nv, q, r, cands, llm, idxs[nv.name]))
        extra.append({"cands": cands, "raw": raw})
    n = len(rows)
    audit = {"shortlist_gold_recall": round(sum(x["gold_in_shortlist"] for x in rows) / n, 4),
             "mean_cands": round(sum(x["n_cands"] for x in rows) / n, 2),
             "ladder_errors": int(sum(x["err"] for x in rows)),
             "ladder_inventory": p.get("ladder_inventory", "pdnc")}
    if p.get("ladder_inventory", "pdnc") == "product":
        audit["s1"] = s1
    if not stub and not p["llm"]:
        return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="xdis_product_shortlist", mode="real",
                          config_hash=cfg.hash, n_units=n, n_trials=0, summary=audit,
                          verdict_hint="SHORTLIST AUDIT ONLY (no LLM)"), [], inputs)
    summary, _curves, hint, gtrials = gx.analyse(rows, p, cfg.base_seed, stub)
    err = np.array([x["err"] for x in rows], dtype=float)
    reach = [x for x in rows if x["gold_in_shortlist"]]
    nd = sum(x["disagree"] for x in rows)
    summary.update(audit)
    summary.update({
        "llm_accuracy_all": round(sum(x["llm_correct"] for x in rows) / n, 4),
        "llm_accuracy_gold_reachable": round(sum(x["llm_correct"] for x in reach) / max(1, len(reach)), 4),
        "disagreement_rate": round(nd / n, 4),
        "p_err_given_disagree": round(sum(x["err"] for x in rows if x["disagree"]) / max(1, nd), 4),
        "p_err_given_agree": round(sum(x["err"] for x in rows if not x["disagree"]) / max(1, n - nd), 4),
        "auroc_alias_space_disagreement": gx._r(gx.auroc(np.array([float(x["alias_disagree"]) for x in rows]), err)),
    })
    a2 = summary["operating_points"]["P2a_disagree"]["auroc"]
    a1 = summary["operating_points"]["P1_conf"]["auroc"]
    summary["collapse"] = bool(not summary["primary_rates_passed"] or a2 is None or a1 is None or a2 - a1 < 0.05)
    if summary["collapse"]:
        summary["status"] = "KILL (collapse)"
    for t, x, e in zip(gtrials, rows, extra):
        t.outputs.update({"cands": e["cands"], "llm": x["llm"], "raw": e["raw"],
                          "gold_in_shortlist": x["gold_in_shortlist"], "gold": x["gold"],
                          "pred": x["pred"], "gender_gold": x["gender_gold"],
                          "gender_pred": x["gender_pred"], "llm_correct": x["llm_correct"]})
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="xdis_product_shortlist",
                      mode="stub" if stub else "real", config_hash=cfg.hash, n_units=n,
                      n_trials=len(gtrials), summary=summary,
                      verdict_hint=f"{summary['status']} (product shortlist, gold recall "
                                   f"{audit['shortlist_gold_recall']}): " + hint.split(": ", 1)[-1],
                      notes=["shortlist built without PDNC gold (CONVERGENCE.md C2)",
                             "disagreement computed product-side by surface comparison",
                             "ladder errors scored on alias-corrected gold (C1 rule)",
                             "ladder known_names still from PDNC's character list (disclosed)"]),
            gtrials, inputs)
