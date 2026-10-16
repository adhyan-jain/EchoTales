"""Score the audit against the two-annotator labels (docs/research/PREFIX_FAITHFULNESS/PREREG_LABELS.md, Addendum 2).

    /home/adhyan/Desktop/EchoTales/.venv/bin/python -I scripts/prefix_audit/score_labels2.py

Annotator 1 = Claude (frozen files, sha256 in labels/LABELS.sha256); annotator 2 = gpt-5.6-luna (labels/luna_labels.jsonl).
Reads files only; no model call. LABELS: MODEL-GENERATED, two model annotators, no human review.
"""

from __future__ import annotations

import glob
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUD = ROOT / "data" / "eval" / "prefix_audit"
LAB = AUD / "labels"
NOVELS = ("lord-of-the-mysteries", "omniscient-readers-viewpoint", "reverend-insanity")
KNOWN = ("male", "female")


def wilson(k: int, n: int, z: float = 1.96) -> list[float | None]:
    if n == 0:
        return [None, None]
    p, d = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k: int, n: int) -> dict:
    return dict(n=k, of=n, share=round(k / n, 4) if n else None, wilson95=wilson(k, n))


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / (n * n)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else None


def frozen_ok() -> bool:
    want = dict(line.split()[::-1] for line in (LAB / "LABELS.sha256").read_text().splitlines() if line.strip())
    return all(hashlib.sha256((LAB / n).read_bytes()).hexdigest() == h for n, h in want.items())


def rows(kind: str, repair: str) -> dict[tuple[str, str, float], dict]:
    out: dict = {}
    for nid in NOVELS:
        for f in glob.glob(str(AUD / f"audit_{kind}-{repair}_{nid}.json")):
            for r in json.load(open(f))["rows"]:
                if r["key"] == "gender":
                    out[(nid, r["entity"], float(r["k"]))] = dict(r, set="original" if kind == "repair" else "added")
    return out


def classify(served, truth) -> str:
    if served in (None, "unknown"):
        return "withheld"
    return "correct" if served == truth else "wrong"


def tally(items: list[str]) -> dict:
    n, c = len(items), Counter(items)
    return {x: rate(c[x], n) for x in ("correct", "withheld", "wrong")} | {"cuts": n}


def combine(mine: str | None, luna: str) -> tuple[str, str]:
    """T*: declared in Addendum 2."""
    m = mine if mine in KNOWN else None
    if m and luna in KNOWN:
        return (m, "agree") if m == luna else ("disputed", "disputed")
    if m:
        return m, "mine_only"
    if luna in KNOWN:
        return luna, "luna_resolved"
    return ("non-person" if "non-person" in (mine, luna) else "unknown"), "neither"


def main() -> None:
    assert frozen_ok(), "annotator-1 label files changed after they were frozen; refusing to score"
    mine_truth: dict = {}
    for nid in NOVELS:
        mine_truth |= {k: v["label"] for k, v in json.load(open(LAB / f"truth_{nid}.json")).items() if not k.startswith("_")}
    mine_prefix = {i["item"]: i["label"] for i in json.load(open(LAB / "prefix.json"))["items"]}
    key = {i["item"]: i for i in json.load(open(LAB / "prefix_key.json"))}
    lun = [json.loads(line) for line in (LAB / "luna_labels.jsonl").read_text().splitlines()]
    L_truth = {r["entity"]: r for r in lun if r["kind"] == "truth"}
    L_pre = {(r["novel"], r["entity"], float(r["k"])): r for r in lun if r["kind"] == "prefix"}
    out: dict = dict(labels="MODEL-GENERATED: annotator 1 Claude (frozen), annotator 2 gpt-5.6-luna; no human review",
                     luna_file_sha256=hashlib.sha256((LAB / "luna_labels.jsonl").read_bytes()).hexdigest(), luna_records=len(lun),
                     luna_invalid=sum(r["gender"] == "invalid" for r in lun),
                     luna_unverified_known=sum(r["gender"] in KNOWN and not r["verified"] for r in lun))

    # D'. agreement on the truth labels
    common = [e for e in mine_truth if e in L_truth]
    cat = lambda x: "unknown" if x == "undetermined" else x  # noqa: E731
    out["Dprime_truth"] = dict(
        characters_labelled_by_both=len(common),
        kappa_4class=kappa([(mine_truth[e], cat(L_truth[e]["label"])) for e in common]),
        raw_agreement_4class=round(sum(mine_truth[e] == cat(L_truth[e]["label"]) for e in common) / max(1, len(common)), 4),
        both_known=sum(mine_truth[e] in KNOWN and L_truth[e]["label"] in KNOWN for e in common),
        contradictions_male_vs_female=sum(mine_truth[e] in KNOWN and L_truth[e]["label"] in KNOWN and mine_truth[e] != L_truth[e]["label"] for e in common),
        mine_known_luna_not=sum(mine_truth[e] in KNOWN and L_truth[e]["label"] not in KNOWN for e in common),
        luna_known_mine_not=sum(mine_truth[e] not in KNOWN and L_truth[e]["label"] in KNOWN for e in common),
        strict_verification_luna_known=sum(L_truth[e]["gender"] in KNOWN and L_truth[e]["verified_strict"] for e in L_truth),
        luna_known_total=sum(L_truth[e]["label"] in KNOWN for e in L_truth),
    )
    agree_pairs = []
    for i, it in key.items():
        l = L_pre.get((it["novel"], it["entity"], float(it["k"])))
        if l:
            agree_pairs.append((mine_prefix[i], "undetermined" if l["label"] not in KNOWN else l["label"]))
    out["Dprime_prefix_vs_my_46"] = dict(items=len(agree_pairs), kappa=kappa(agree_pairs), raw=round(sum(a == b for a, b in agree_pairs) / max(1, len(agree_pairs)), 4),
                                         contradictions=sum(a in KNOWN and b in KNOWN and a != b for a, b in agree_pairs),
                                         mine_known_luna_undetermined=sum(a in KNOWN and b == "undetermined" for a, b in agree_pairs),
                                         luna_known_mine_undetermined=sum(a == "undetermined" and b in KNOWN for a, b in agree_pairs))

    # T*
    tstar, how = {}, Counter()
    for e in L_truth:
        tstar[e], h = combine(mine_truth.get(e), L_truth[e]["label"])
        how[h] += 1
    out["Tstar_resolution"] = dict(how)
    out["Tstar_distribution"] = dict(Counter(tstar.values()))
    out["Tstar_not_male_female_share"] = round(sum(v not in KNOWN for v in tstar.values()) / len(tstar), 4)

    # A'. premature disclosure etc. over all exposed pairs, original and added cuts, P* = Luna prefix label
    off = rows("repair", "off") | rows("dense", "off")
    on = rows("repair", "on") | rows("dense", "on")
    A: dict = {}
    for sset in ("original", "added", "all"):
        sel = [k for k, r in off.items() if (sset == "all" or r["set"] == sset)]
        allcuts = len(sel)
        exp = [k for k in sel if off[k]["exposed"] and k in L_pre]
        c, chars = Counter(), {}
        for k in exp:
            r = off[k]
            s, p = r["full_value"], (L_pre[k]["label"] if L_pre[k]["label"] in KNOWN else "undetermined")
            if r["diverge"]:
                cls = ("reverse" if s in (None, "unknown") else "premature_disclosure" if p == "undetermined"
                       else "justified_by_text" if p == s else "text_says_otherwise")
            else:
                cls = "no_divergence_unsupported_in_both" if s in KNOWN and p == "undetermined" else "no_divergence"
            c[cls] += 1
            chars.setdefault(cls, set()).add(k[1])
        A[sset] = dict(character_cuts=allcuts, exposed_labelled=len(exp), diverging=sum(off[k]["diverge"] for k in exp), classes=dict(c),
                       characters_per_class={k: len(v) for k, v in chars.items()},
                       premature_rate=rate(c["premature_disclosure"], allcuts), justified_rate=rate(c["justified_by_text"], allcuts))
    out["Aprime"] = A

    # B'. correctness against T* on exposed pairs
    def correctness(sset: str) -> dict:
        sel = [k for k, r in off.items() if r["exposed"] and (sset == "all" or r["set"] == sset) and tstar.get(k[1]) in KNOWN]
        t = lambda k: tstar[k[1]]  # noqa: E731
        return dict(characters=len({k[1] for k in sel}),
                    status_quo=tally([classify(off[k]["full_value"], t(k)) for k in sel]),
                    prefix_only_build=tally([classify(off[k]["prefix_value"], t(k)) for k in sel]),
                    repaired=tally([classify(on[k]["full_value"], t(k)) for k in sel if k in on]))
    out["Bprime"] = {s: correctness(s) for s in ("original", "added", "all")}
    wrong = Counter()
    for k, r in off.items():
        t = tstar.get(k[1])
        if r["exposed"] and t in KNOWN:
            for name, v in (("status_quo", r["full_value"]), ("prefix_only", r["prefix_value"])):
                if classify(v, t) == "wrong":
                    wrong[(k[1], name)] += 1
    out["wrong_values_by_character"] = {f"{e}|{n}": c for (e, n), c in wrong.items()}

    # sensitivity: strict verification for Luna prefix labels
    strict = Counter()
    for k in [k for k in off if off[k]["exposed"] and off[k]["diverge"] and k in L_pre]:
        l = L_pre[k]
        p = l["gender"] if (l["gender"] in KNOWN and l["verified_strict"]) else "undetermined"
        s = off[k]["full_value"]
        strict["reverse" if s in (None, "unknown") else "premature_disclosure" if p == "undetermined" else "justified_by_text" if p == s else "text_says_otherwise"] += 1
    out["Aprime_sensitivity_strict_verification_diverging"] = dict(strict)
    (AUD / "labels_summary_v2.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
