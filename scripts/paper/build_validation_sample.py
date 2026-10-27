"""Stratified sample of character-cuts for the targeted human validation of the pipeline-disclosure labels.

    python3 scripts/paper/build_validation_sample.py --counts      # stratum populations only
    python3 scripts/paper/build_validation_sample.py               # draw the sample, write manifest + key

Reads stored audit and label files only; no model call. The draw is purposive (it over-represents rare classes on
purpose), so it supports per-stratum agreement between humans and the model annotators, not a population rate; only
the random-control stratum S6 can be weighted back to a rate. The manifest carries no served value and no model label;
those go to a separate key file so a blind sheet can be built from the manifest alone. The manifest hash is printed
so it can be recorded before any annotator sees a case.
LABEL PROVENANCE of the strata definitions: MODEL-GENERATED (annotator 1 Claude, annotator 2 gpt-5.6-luna).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUD = ROOT / "data" / "eval" / "prefix_audit"
LAB = AUD / "labels"
OUT = ROOT / "data" / "eval" / "validation"
KNOWN = ("male", "female")
SEED = 20261101
# Smallest population draws first, so a rare case is not claimed by a larger stratum before its own turn.
ORDER = ("S1", "S2", "S3", "S4", "S5", "S6")
TARGET = {"S1": 10, "S2": 8, "S3": 8, "S4": 2, "S5": 8, "S6": 12}
N_REPEAT = 4


def audit_rows(repair: str) -> dict:
    out: dict = {}
    for kind, tag in (("repair", "original"), ("dense", "added")):
        for f in sorted(glob.glob(str(AUD / f"audit_{kind}-{repair}_*.json"))):
            d = json.load(open(f))
            for r in d["rows"]:
                if r["key"] == "gender":
                    out[(d["novel"], r["entity"], float(r["k"]))] = dict(r, set=tag)
    return out


def prefix_labels(name: str) -> dict:
    out: dict = {}
    for line in (LAB / name).read_text().splitlines():
        r = json.loads(line)
        if r["kind"] == "prefix":
            out[(r["novel"], r["entity"], float(r["k"]))] = r["label"] if r["label"] in KNOWN else "undetermined"
    return out


def claude_prefix() -> dict:
    lab = {i["item"]: i["label"] for i in json.load(open(LAB / "prefix.json"))["items"]}
    return {(k["novel"], k["entity"], float(k["k"])): (lab[k["item"]] if lab[k["item"]] in KNOWN else "undetermined")
            for k in json.load(open(LAB / "prefix_key.json"))}


def strata() -> tuple[dict[str, list], dict]:
    off, on = audit_rows("off"), audit_rows("on")
    strict, perm, claude = prefix_labels("luna_labels.jsonl"), prefix_labels("luna_labels_permissive.jsonl"), claude_prefix()
    cand: dict[str, list] = defaultdict(list)
    key: dict = {}
    for k, r in off.items():
        s, p = r["full_value"], strict.get(k)
        if p is None:
            continue  # no model prefix label to compare a human against
        tags = []
        if r["exposed"] and r["diverge"]:
            if s in (None, "unknown"):
                tags.append("S4")
            elif p == "undetermined":
                tags.append("S1")
            else:
                tags.append("S2")
        if k in claude and (claude[k] != p or perm.get(k, p) != p):
            tags.append("S3")
        o = on.get(k)
        if r["exposed"] and o and o["full_value"] in (None, "unknown") and p in KNOWN:
            tags.append("S5")
        if not r["diverge"]:
            tags.append("S6")
        for t in tags:
            cand[t].append(k)
        key[k] = dict(set=r["set"], served_unrepaired=s, prefix_build=r["prefix_value"],
                      served_repaired=o["full_value"] if o else None, annotator2_strict=p,
                      annotator2_permissive=perm.get(k), annotator1=claude.get(k))
    return cand, key


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", action="store_true")
    a = ap.parse_args()
    cand, key = strata()
    pops = {t: len(cand[t]) for t in ORDER}
    if a.counts:
        for t in ORDER:
            by = Counter((k[0], key[k]["set"]) for k in cand[t])
            print(t, pops[t], "target", TARGET[t], dict(sorted(by.items())))
        return

    rng = random.Random(SEED)
    taken: set = set()
    picked: list[dict] = []
    shortfall: dict = {}
    for t in sorted(ORDER, key=lambda x: pops[x]):
        pool = [k for k in cand[t] if k not in taken]
        rng.shuffle(pool)
        by_novel = defaultdict(list)
        for k in pool:
            by_novel[k[0]].append(k)
        chosen: list = []
        while len(chosen) < TARGET[t] and any(by_novel.values()):  # round-robin so no serial dominates a stratum
            for n in sorted(by_novel):
                if by_novel[n] and len(chosen) < TARGET[t]:
                    chosen.append(by_novel[n].pop())
        if len(chosen) < TARGET[t]:
            shortfall[t] = TARGET[t] - len(chosen)
        taken.update(chosen)
        picked += [dict(stratum=t, novel=k[0], entity=k[1], k=k[2], cut_set=key[k]["set"]) for k in chosen]

    rng.shuffle(picked)
    for i, c in enumerate(picked):
        c["case"] = f"C{i + 1:03d}"
    repeats = [dict(c, case=f"R{i + 1:03d}", repeat_of=c["case"]) for i, c in enumerate(rng.sample(picked, N_REPEAT))]
    manifest = dict(seed=SEED, populations=pops, targets=TARGET, shortfall=shortfall, cases=picked + repeats)
    text = json.dumps(manifest, indent=1, sort_keys=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pipeline_disclosure_sample.json").write_text(text)
    (OUT / "pipeline_disclosure_sample_key.json").write_text(json.dumps(
        {c["case"]: key[(c["novel"], c["entity"], c["k"])] for c in picked}, indent=1, sort_keys=True))
    print("cases", len(picked), "repeats", len(repeats), "shortfall", shortfall)
    print("manifest sha256", hashlib.sha256(text.encode()).hexdigest())


if __name__ == "__main__":
    main()
