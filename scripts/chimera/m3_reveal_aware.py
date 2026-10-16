"""M3: construct validity of the premature-resolution metric on synthetic worlds (implements PREREG_M3 v1).

Labels come from the world spec only (synthetic). No model, no LLM, no spend, no novel text. The shipped resolver is
imported and run unchanged; the reveal-aware systems are wrappers over its output, so no repository file is edited.

    python scripts/chimera/m3_reveal_aware.py --out data/eval/chimera/m3_results.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sio_synthetic_oracle as S  # noqa: E402

from echotales.core.enums import AliasType  # noqa: E402
from echotales.pipeline.resolve.detect_reveals import REVEAL_PATTERNS  # noqa: E402

TEMPLATES = ("T0", "T1", "T2", "T3")
DESIGN = ("T0", "T1")
NAME = r"[A-Z][\w’']*(?:\s+[A-Z][\w’']*){0,3}"
# D_plus extra patterns: written for T0 and T1 ONLY (PREREG_M3 section 3)
PLUS = [
    re.compile(rf"(?P<alias>[Tt]he [a-z]+(?: [a-z]+)?), in truth, was (?P<name>{NAME})"),
    re.compile(rf"(?P<alias>[Tt]he [a-z]+(?: [a-z]+)?) was none other than (?P<name>{NAME})"),
]


# ------------------------------------------------------------------ worlds
def make_world2(seed: int, template: str) -> S.World:
    """SIO v1 structure with the reveal sentence template as a parameter (title stream omitted: not used by M3)."""
    rng = random.Random(seed)
    givens = rng.sample(S.GIVEN, 6)
    fams = rng.sample(S.FAMILY, 5)
    names = [f"{givens[0]} {fams[0]}", f"{givens[1]} {fams[0]}", f"{givens[2]} {fams[1]}",
             f"{givens[3]} {fams[2]}", givens[4], givens[5]]
    w = S.World(seed=seed, names=names)
    d0, d1 = 2 + seed % 3, 2 + (seed // 3) % 2
    a = [3, 9]
    r = [a[0] + d0, a[1] + d1]
    pool = [0, 1, 2, 3]
    y0 = rng.choice(pool)
    z0 = rng.choice([c for c in pool if c != y0])
    y1 = rng.choice([c for c in pool if c != y0])
    z1 = rng.choice([c for c in pool if c != y1])
    reveals = [dict(alias=S.ALIASES[0], a=a[0], r=r[0], d=d0, y=y0, z=z0),
               dict(alias=S.ALIASES[1], a=a[1], r=r[1], d=d1, y=y1, z=z1)]
    w.reveals = reveals
    alias_pre: dict[int, int] = {}
    post_ch: dict[int, int] = {}
    for i, rv in enumerate(reveals):
        for c in range(rv["a"], rv["r"]):
            alias_pre[c] = i
        for c in (rv["r"], rv["r"] + 1):
            if c <= S.N_CHAPTERS and c not in alias_pre:
                post_ch[c] = i
    lone = set(alias_pre) | set(post_ch)
    P, NR = S.P, S.NR
    deictic = AliasType.RELATIONAL_DEICTIC
    rigid = AliasType.RIGID_NAME

    def place() -> str:
        return rng.choice(S.PLACES)

    for n in range(1, S.N_CHAPTERS + 1):
        ch = S._Ch(w, n)
        if n in lone:
            rv = reveals[alias_pre.get(n, post_ch.get(n))]
            z, y = rv["z"], rv["y"]
            if n in alias_pre:
                ch.men(names[z], rigid, P, "control", names[z], names[z])
                ch.text(" spoke quietly with ")
                ch.men(rv["alias"], deictic, P, "pre_alias", None, names[y])
                ch.text(f" near {place()}. ")
            else:
                if n == rv["r"]:
                    rv["sent_start"] = len(ch.buf)
                    al_cap, al = rv["alias"].capitalize(), rv["alias"]
                    if template in ("T0", "T1"):
                        ch.men(al_cap, deictic, P, "post_alias", names[y], names[y])
                        ch.text(", in truth, was " if template == "T0" else " was none other than ")
                        ch.men(names[y], rigid, NR, "control", names[y], names[y])
                        ch.text(". ")
                    elif template == "T2":
                        ch.text("Everyone now understood: ")
                        ch.men(al, deictic, P, "post_alias", names[y], names[y])
                        ch.text(" was ")
                        ch.men(names[y], rigid, NR, "control", names[y], names[y])
                        ch.text(" all along. ")
                    else:  # T3
                        ch.men(names[y], rigid, NR, "control", names[y], names[y])
                        ch.text(" had been ")
                        ch.men(al, deictic, P, "post_alias", names[y], names[y])
                        ch.text(" all along. ")
                ch.men(names[z], rigid, P, "control", names[z], names[z])
                ch.text(" met ")
                ch.men(rv["alias"], deictic, P, "post_alias", names[y], names[y])
                ch.text(f" near {place()}. ")
        elif n == 1:
            for idx in (0, 1, 2, 5):
                ch.men(names[idx], rigid, P, "control", names[idx], names[idx])
                ch.text(f" waited at {place()}. ")
        elif n == 2:
            for idx in (3, 4):
                ch.men(names[idx], rigid, P, "control", names[idx], names[idx])
                ch.text(f" waited at {place()}. ")
        else:
            for idx in rng.sample([0, 1, 2, 3, 4], 3):
                ch.men(names[idx], rigid, P, "control", names[idx], names[idx])
                ch.text(f" crossed {place()}. ")
        ch.done()
    return w


# ------------------------------------------------------------------ detectors
def _sentence_start(text: str, pos: int) -> int:
    starts = [m.end() for m in re.finditer(r"[.!?]\s+", text[:pos])]
    return starts[-1] if starts else 0


def detect(w: S.World, detector: str) -> list[dict]:
    """Detected reveals: dict(chapter, sent_start, alias, label). Reads the spec only for D_oracle."""
    names = set(w.names)
    out: list[dict] = []
    if detector == "oracle":
        for rv in w.reveals:
            out.append(dict(chapter=rv["r"], sent_start=rv["sent_start"], alias=rv["alias"], label=w.names[rv["y"]]))
        return out
    by_ch = defaultdict(list)
    for m in w.mentions:
        if m.alias_type is AliasType.RELATIONAL_DEICTIC:
            by_ch[m.chapter].append(m)
    for n, text in w.chapters.items():
        for pat in REVEAL_PATTERNS:
            for mt in pat.finditer(text):
                label = mt.group("name").strip()
                if label not in names:
                    continue
                ss = _sentence_start(text, mt.start())
                cand = [m for m in by_ch.get(n, []) if ss <= m.offset < mt.start()]
                if not cand:
                    continue  # repo patterns capture no alias: none can be attached
                out.append(dict(chapter=n, sent_start=ss, alias=cand[-1].text.lower(), label=label))
        if detector == "plus":
            for pat in PLUS:
                for mt in pat.finditer(text):
                    label = mt.group("name").strip()
                    if label in names:
                        out.append(dict(chapter=n, sent_start=mt.start("alias"), alias=mt.group("alias").lower(),
                                        label=label))
    seen, uniq = set(), []
    for d in out:
        k = (d["alias"], d["chapter"])
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq


# ------------------------------------------------------------------ systems
def system_labels(system: str, w: S.World, base: dict, reveals: list[dict]) -> dict:
    by_alias = {d["alias"]: d for d in reveals}
    out: dict = {}
    for m in w.mentions:
        lab = base[m.id]
        if m.kind in ("pre_alias", "post_alias"):
            if system == "S_abstain":
                lab = None
            elif system == "S_retro" and m.text.lower() in by_alias:
                lab = by_alias[m.text.lower()]["label"]
            elif system == "S_causal" and m.text.lower() in by_alias:
                d = by_alias[m.text.lower()]
                after = m.chapter > d["chapter"] or (m.chapter == d["chapter"] and m.offset >= d["sent_start"])
                lab = d["label"] if after else None
        out[m.id] = lab
    return out


def score(w: S.World, labels: dict, acc: dict) -> None:
    rv_by_alias = {rv["alias"]: rv for rv in w.reveals}
    for m in w.mentions:
        if m.kind not in ("pre_alias", "post_alias"):
            continue
        rv = rv_by_alias[m.text.lower()]
        y = w.names[rv["y"]]
        L = labels[m.id]
        pre = m.kind == "pre_alias"
        acc["n_" + m.kind] += 1
        acc["omni_correct"] += L == y
        acc["overcommit"] += (L is not None and L != y)
        acc["reader_correct"] += (L is None) if pre else (L == y)
        if pre:
            acc["premature"] += L == y
            acc[f"pre_d{rv['d']}"] += 1
            acc[f"premature_d{rv['d']}"] += L == y


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cells: dict[tuple, dict] = {}
    recall: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    false_det: dict[tuple, int] = defaultdict(int)

    def cell(*key):
        return cells.setdefault(key, defaultdict(int))

    for template in TEMPLATES:
        for seed in range(S.N_WORLDS):
            w = make_world2(seed, template)
            for m in w.mentions:  # generator self-check: exact offsets
                assert w.chapters[m.chapter][m.offset:m.offset + len(m.text)] == m.text
            base = S.run(w, S.N_CHAPTERS)
            dets = {d: detect(w, d) for d in ("oracle", "repo", "plus")}
            truth = {(rv["alias"], rv["r"], w.names[rv["y"]]) for rv in w.reveals}
            for d, found in dets.items():
                got = {(x["alias"], x["chapter"], x["label"]) for x in found}
                recall[(d, template)][0] += len(truth & got)
                recall[(d, template)][1] += len(truth)
                false_det[(d, template)] += len(got - truth)
            for system in ("S0", "S_abstain"):
                score(w, system_labels(system, w, base, []), cell(system, "-", template))
            for system in ("S_retro", "S_causal"):
                for d, found in dets.items():
                    score(w, system_labels(system, w, base, found), cell(system, d, template))

    def r(k, d):
        return dict(k=k, n=d, rate=(k / d if d else None), wilson95=S.wilson(k, d))

    def agg(acc: dict) -> dict:
        npre, npost = acc["n_pre_alias"], acc["n_post_alias"]
        n = npre + npost
        return dict(
            n_pre_alias=npre, n_post_alias=npost, premature=r(acc["premature"], npre),
            reader_accuracy=r(acc["reader_correct"], n), omniscient_accuracy=r(acc["omni_correct"], n),
            overcommit=r(acc["overcommit"], n),
            premature_by_distance={dd: r(acc[f"premature_d{dd}"], acc[f"pre_d{dd}"]) for dd in (2, 3, 4)},
        )

    pooled: dict[tuple, dict] = {}
    for (sys_, det, _tpl), acc in cells.items():
        tot = pooled.setdefault((sys_, det), defaultdict(int))
        for k, v in acc.items():
            tot[k] += v
    res = dict(
        preregistration="PREREG_M3_reveal_aware_synthetic.md v1",
        label_provenance="SYNTHETIC (by construction from the world spec); no model, no human, no novel text",
        worlds=len(TEMPLATES) * S.N_WORLDS, templates=list(TEMPLATES),
        detection_recall={f"{d}|{t}": dict(**r(k, n), false_detections=false_det[(d, t)])
                          for (d, t), (k, n) in recall.items()},
        pooled={f"{s}|{d}": agg(a) for (s, d), a in pooled.items()},
        by_template={f"{s}|{d}|{t}": agg(a) for (s, d, t), a in cells.items()},
    )
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
