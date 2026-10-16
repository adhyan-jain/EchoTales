"""A synthetic volume with exactly known truth (docs/research/PREFIX_FAITHFULNESS/PREREG_SYNTHETIC.md).

    PYTHONPATH=<worktree>/packages/core/src:<worktree>/packages/pipeline/src \
      python scripts/prefix_audit/synthetic_oracle.py --all            # nine configurations x 5 seeds, 3 processes
      python scripts/prefix_audit/synthetic_oracle.py --p-anchor 0.35 --p-adv 0.05 --seeds 5

Invented text only. Truth and the reader-visible evidence are set by construction, so nothing here uses an annotator or a model.
LABEL PROVENANCE: SYNTHETIC.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
WT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import audit as A  # noqa: E402
import common as C  # noqa: E402
from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind  # noqa: E402
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span  # noqa: E402
from echotales.core.store import Store  # noqa: E402

NOVEL = "syn"
CHAPTERS, CHARACTERS, LAST_INTRO = 40, 80, 28
CUTS = (4, 8, 12, 16, 20, 28)
MODES = {"status_quo": (False, None), "plain": (True, None), "anch_1_80": (True, (1, 0.8)), "anch_2_80": (True, (2, 0.8)), "anch_1_100": (True, (1, 1.0))}
GRID = [(pa, pd) for pa in (0.10, 0.35, 0.70) for pd in (0.0, 0.05, 0.15)]
SYL = ["ka", "ro", "mi", "te", "lu", "so", "ven", "dar", "ni", "bo", "fe", "za", "hu", "pel", "wa", "gri"]
VP = ["walked to the gate", "waited by the door", "studied the map", "crossed the yard", "lit the lamp", "counted the coins",
      "mended the net", "climbed the stair"]
NOUN = ["cloak", "boots", "satchel", "lantern", "sleeve"]
PART = ["trailing", "wet", "shaking", "gleaming"]
VERB2 = ["paused", "smiled", "left", "sighed", "turned"]
PRON = {"male": ("he", "his"), "female": ("she", "her")}


def poisson(rng: random.Random, lam: float) -> int:
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def names(rng: random.Random, n: int) -> list[str]:
    out: set[str] = set()
    while len(out) < n:
        out.add("".join(rng.choice(SYL) for _ in range(rng.choice((2, 3)))).capitalize())
    return sorted(out)


def sentence(rng: random.Random, name: str, gender: str, p_anchor: float, p_adv: float) -> tuple[str, bool]:
    """(text, own_cue). The name is the only capitalised word, so the anchored window runs to the full stop."""
    vp, u = rng.choice(VP), rng.random()
    if u < p_anchor:
        subj, poss = PRON[gender]
        cue = f", {poss} {rng.choice(NOUN)} {rng.choice(PART)}" if rng.random() < 0.5 else f" and {subj} {rng.choice(VERB2)}"
        return f"{name} {vp}{cue}.", True
    if u < p_anchor + p_adv:
        subj, poss = PRON[rng.choice(("male", "female"))]
        cue = f" beside the stranger, {poss} {rng.choice(NOUN)} {rng.choice(PART)}" if rng.random() < 0.5 else f" beside the stranger and {subj} {rng.choice(VERB2)}"
        return f"{name} {vp}{cue}.", False
    return f"{name} {vp}.", False


def generate(path: Path, seed: int, p_anchor: float, p_adv: float) -> tuple[dict, dict]:
    """Write one synthetic volume to `path`; return (truth gender by entity, chapters with an own cue by entity)."""
    rng = random.Random(seed)
    if path.exists():
        path.unlink()
    store = Store(str(path))
    store.add_novel(NOVEL, "Syn", "x.epub", "generic")
    nm = names(rng, CHARACTERS)
    ent = [f"{NOVEL}:self{i}" for i in range(CHARACTERS)]
    gender = {e: rng.choice(("male", "female")) for e in ent}
    intro = {e: rng.randint(1, LAST_INTRO) for e in ent}
    label = dict(zip(ent, nm, strict=True))
    own: dict[str, set[int]] = {e: set() for e in ent}
    for e in ent:
        store.add_self(Self(id=e, novel_id=NOVEL, canonical_label=label[e],
                            first_attested_pos=DiscoursePosition(chapter=float(intro[e]), offset=0), kind=TargetKind.SELF))
    n_sp = n_m = 0
    for c in range(1, CHAPTERS + 1):
        active = [e for e in ent if intro[e] <= c]
        paras: list[tuple[str, list[tuple[int, str]]]] = []
        for e in active:
            if intro[e] != c and rng.random() > 0.6:
                continue
            for _ in range(1 + poisson(rng, 0.7)):
                subjects = [e] + [rng.choice(active) for _ in range(3) if rng.random() < 0.5]
                text, offs, pos = "", [], 0
                for s in subjects:
                    sent, has_own = sentence(rng, label[s], gender[s], p_anchor, p_adv)
                    if has_own:
                        own[s].add(c)
                    offs.append((pos, s))
                    text += sent + " "
                    pos += len(sent) + 1
                paras.append((text.strip(), offs))
        store.add_chapter(Chapter(novel_id=NOVEL, number=float(c), title="T", source_href=f"{c}.html",
                                  blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, (t, _o) in enumerate(paras)]))
        spans, mentions = [], []
        for i, (t, offs) in enumerate(paras):
            n_sp += 1
            spans.append(Span(id=f"sp{n_sp}", novel_id=NOVEL, chapter=float(c), block_index=i, start=0, end=len(t),
                              span_type=SpanType.NARRATION_ACTION, text=t))
            for off, s in offs:
                n_m += 1
                mentions.append(Mention(id=f"m{n_m}", novel_id=NOVEL, segment_id="s", chapter=float(c), offset=off, block_index=i,
                                        text=label[s], alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                                        reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id=s))
        store.add_spans(spans)
        store.add_mentions(mentions)
    store.conn.commit()
    store.close()
    return gender, {e: sorted(v) for e, v in own.items()}


def evaluate(p_anchor: float, p_adv: float, seeds: int) -> dict:
    tally = {m: Counter() for m in MODES}
    per_seed = []
    for seed in range(seeds):
        src = C.SCRATCH / f"syn_pa{round(p_anchor * 100)}_pd{round(p_adv * 100)}_s{seed}.src.db"
        truth, own = generate(src, seed, p_anchor, p_adv)
        seed_t = {m: Counter() for m in MODES}
        for mode, (repair, anchored) in MODES.items():
            tag = f"{mode}_pa{round(p_anchor * 100)}_pd{round(p_adv * 100)}_s{seed}"
            full, _ = A.build(NOVEL, src, f"{tag}_full", None, repair, anchored)
            for k in CUTS:
                pre, _ = A.build(NOVEL, src, f"{tag}_k{k}", k, repair, anchored)
                fs, ts = A.read_state(full, NOVEL, k), A.read_state(pre, NOVEL, k)
                for e in sorted(e for e in set(fs) & set(ts) if pre.chapters_for_target(NOVEL, e)):
                    for pid in sorted(set(fs[e]["attrs"]) & set(ts[e]["attrs"])):
                        gf, gp = fs[e]["attrs"][pid].get("gender"), ts[e]["attrs"][pid].get("gender")
                        known = gf not in (None, "unknown")
                        determinable = any(ch <= k for ch in own[e])
                        t = seed_t[mode]
                        t["pairs"] += 1
                        t["diverge"] += gf != gp
                        t["correct"] += known and gf == truth[e]
                        t["wrong"] += known and gf != truth[e]
                        t["withheld"] += not known
                        t["served_known_not_determinable"] += known and not determinable
                        t["diverge_premature"] += (gf != gp) and known and not determinable
                        t["diverge_justified"] += (gf != gp) and known and determinable
                pre.close()
            full.close()
        for m in MODES:
            tally[m].update(seed_t[m])
        per_seed.append({m: dict(seed_t[m]) for m in MODES})
    return dict(p_anchor=p_anchor, p_adv=p_adv, seeds=seeds, totals={m: dict(tally[m]) for m in MODES}, per_seed=per_seed)


def summarise(res: dict) -> dict:
    t = res["totals"]
    sq, pl = t["status_quo"]["correct"], t["plain"]["correct"]
    out = {}
    for m, v in t.items():
        n = v["pairs"]
        out[m] = dict(pairs=n, diverge=v["diverge"], correct_share=round(v["correct"] / n, 4), withheld_share=round(v["withheld"] / n, 4),
                      wrong_share=round(v["wrong"] / n, 4), served_known_not_determinable=v["served_known_not_determinable"],
                      diverge_premature=v["diverge_premature"], diverge_justified=v["diverge_justified"],
                      recovered_fraction=(round((v["correct"] - pl) / (sq - pl), 4) if m.startswith("anch") and sq != pl else None))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--p-anchor", type=float)
    ap.add_argument("--p-adv", type=float)
    ap.add_argument("--seeds", type=int, default=5)
    a = ap.parse_args()
    out_dir = C.RESULTS / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)
    if a.all:
        def run(cfg):  # noqa: ANN001, ANN202
            pa, pd = cfg
            r = subprocess.run([sys.executable, str(Path(__file__)), "--p-anchor", str(pa), "--p-adv", str(pd), "--seeds", str(a.seeds)],
                               env={"PYTHONPATH": f"{WT}/packages/core/src:{WT}/packages/pipeline/src", "PATH": "/usr/bin:/bin"},
                               capture_output=True, text=True, cwd=WT)
            print(cfg, "exit", r.returncode, flush=True)
            if r.returncode:
                print(r.stderr[-500:], flush=True)
            return r.returncode
        with ThreadPoolExecutor(max_workers=3) as ex:
            sys.exit(1 if any(ex.map(run, GRID)) else 0)
    res = evaluate(a.p_anchor, a.p_adv, a.seeds)
    res["summary"] = summarise(res)
    (out_dir / f"syn_pa{round(a.p_anchor * 100)}_pd{round(a.p_adv * 100)}.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["summary"], indent=1))


if __name__ == "__main__":
    main()
