"""Scene-cut v3 evaluation: candidates, pairwise judge calls (cached), rule learning on LEARN, report on held-out.

    PYTHONPATH=packages/core/src:packages/pipeline/src ECHOTALES_MODEL_BACKEND=ollama ECHOTALES_LLM_MODE=local \
        python scripts/eval/segment_v3_eval.py cands                  # candidate recall (learn and held, no model but nomic)
    ... judge --split learn                                           # judge calls, GPU lock per chapter, resumable
    ... rules --split learn --out data/scratch/segment/v3_rule.json   # choose the rule on learn
    ... judge --split held; ... report --rule data/scratch/segment/v3_rule.json   # held-out is read once, report only

The prompt is frozen on learn chapters; held-out chapters are judged only after that.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from echotales.core.store import Store
from echotales.pipeline.llm.ollama import OllamaProvider
from echotales.pipeline.segment.cuts import TimeRelation
from echotales.pipeline.segment.discontinuity import canonical_position, load_nlp, score_chapter
from echotales.pipeline.segment.embed import get_embedder
from echotales.pipeline.segment.judge import (
    JudgeCache,
    candidate_boundaries,
    decide_cuts,
    judge_boundary,
    rule_grid,
)
from echotales.pipeline.segment.place_tags import TaggedBlock
from segment_tag_tune import prf

GOLD = "data/gold/segment/scene_boundaries.json"
TAGS = "data/scratch/segment/tagcache/qwen3_8b_p4"
CANDS = Path("data/scratch/segment/v3_candidates.json")
JCACHE = "data/scratch/segment/judgecache"
LOCK = "/tmp/echotales-gpu.lock"


def load():
    meta = json.loads(Path(GOLD).read_text())
    stores = {n: Store(meta["dbs"][n]) for n in meta["novels"]}
    return meta, stores


def in_split(meta, novel, ch, split):
    lm = float(meta.get("learn_max", {}).get(novel, 10))
    return {"learn": float(ch) <= lm, "held": float(ch) > lm, "all": True}[split]


def tags_for(novel, ch):
    p = Path(TAGS) / f"{novel}_{ch}.json"
    if not p.exists():
        return None
    return [TaggedBlock(d["block"], d["place"], TimeRelation(d["time_shift"]), d["time_anchor"]) for d in json.loads(p.read_text())]


def cmd_cands(a, meta, stores):
    nlp = load_nlp()
    out = json.loads(CANDS.read_text()) if CANDS.exists() else {}
    for novel, gold in meta["novels"].items():
        for ch in gold:
            key = f"{novel}|{ch}"
            if key in out:
                continue
            chap = stores[novel].get_chapter(novel, float(ch))
            with open(LOCK, "w") as lk:
                fcntl.flock(lk, fcntl.LOCK_EX)
                emb = get_embedder()
                bs = score_chapter(chap, stores[novel].get_mentions(novel, float(ch)), nlp=nlp, embedder=emb)
            cs = candidate_boundaries(chap, bs, tags_for(novel, ch), disc_rate=a.disc_rate)
            out[key] = [{"pos": c.position, "sources": sorted(c.sources), "sep": c.separator} for c in cs]
    CANDS.write_text(json.dumps(out))
    report_recall(meta, stores, out, a.split)


def gold_sets(meta, stores, novel, ch):
    spec = meta["novels"][novel][ch]
    chap = stores[novel].get_chapter(novel, float(ch))
    g = {canonical_position(chap, x["block"]) for x in spec["cuts"]}
    amb = {canonical_position(chap, x) for x in spec.get("ambiguous", [])}
    neg = {canonical_position(chap, x["block"]) for x in spec.get("negatives", [])}
    return chap, g, amb, neg


def report_recall(meta, stores, cands, split):
    tot = hit = n_c = 0
    per: dict[str, list[int]] = {}
    for key, cs in cands.items():
        novel, ch = key.split("|")
        if not in_split(meta, novel, ch, split):
            continue
        _, g, _, _ = gold_sets(meta, stores, novel, ch)
        pos = {c["pos"] for c in cs}
        tot += len(g)
        hit += len(g & pos)
        n_c += len(pos)
        p = per.setdefault(novel, [0, 0, 0])
        p[0] += len(g)
        p[1] += len(g & pos)
        p[2] += len(pos)
    print(f"candidate recall {split}: {hit}/{tot}  candidates {n_c}")
    for n, (t, h, c) in per.items():
        print(f"  {n[:20]:20s} {h}/{t}  cands {c}")


def cmd_judge(a, meta, stores):
    cands = json.loads(CANDS.read_text())
    llm = OllamaProvider(model=a.model, timeout=600.0, num_ctx=4096)
    cache = JudgeCache(JCACHE, a.model)
    for key, cs in cands.items():
        novel, ch = key.split("|")
        if not in_split(meta, novel, ch, a.split):
            continue
        todo = [c for c in cs if cache.get(novel, float(ch), c["pos"]) is None]
        if not todo:
            continue
        chap = stores[novel].get_chapter(novel, float(ch))
        mentions = stores[novel].get_mentions(novel, float(ch))
        with open(LOCK, "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            for c in todo:
                judge_boundary(chap, c["pos"], llm, novel_id=novel, mentions=mentions, cache=cache)
        print(key, len(todo), flush=True)


def judged(meta, stores, a, split):
    cands = json.loads(CANDS.read_text())
    cache = JudgeCache(JCACHE, a.model)
    out = {}
    for key, cs in cands.items():
        novel, ch = key.split("|")
        if not in_split(meta, novel, ch, split):
            continue
        js = []
        for c in cs:
            j = cache.get(novel, float(ch), c["pos"])
            if j is None:
                continue
            j.sources, j.separator = c["sources"], c["sep"]
            js.append(j)
        out[(novel, ch)] = js
    return out


def score_split(meta, stores, js_by, rule):
    per: dict[str, list[int]] = {}
    hn = [0, 0]
    detail = []
    for (novel, ch), js in js_by.items():
        chap, g, amb, neg = gold_sets(meta, stores, novel, ch)
        pred = {canonical_position(chap, b) for b in decide_cuts(js, rule, chap)}
        pred = {x for x in pred if x not in (amb - g)}
        p = per.setdefault(novel, [0, 0, 0])
        p[0] += len(g & pred)
        p[1] += len(pred - g)
        p[2] += len(g - pred)
        hn[0] += len(neg)
        hn[1] += len(neg & pred)
        detail.append((novel, ch, chap, g, pred, {j.block: j for j in js}))
    tp, fp, fn = (sum(v[i] for v in per.values()) for i in range(3))
    return prf(tp, fp, fn), {n: prf(*v) for n, v in per.items()}, hn, detail


def cmd_rules(a, meta, stores):
    js = judged(meta, stores, a, a.split)
    rows = []
    for r in rule_grid():
        pooled, per, hn, _ = score_split(meta, stores, js, r)
        rows.append((pooled["f1"], r, pooled, per, hn))
    rows.sort(key=lambda x: (-x[0], x[1].min_gap))
    for f1, r, pooled, _per, _hn in rows[:8]:
        print(f"{f1:.3f} {r.name} gap{r.min_gap} {pooled}")
    best = rows[0]
    print("best per novel:", json.dumps(best[3]))
    if a.out:
        Path(a.out).write_text(json.dumps({"rule": asdict(best[1]), "learn": best[2], "learn_per_novel": best[3], "top": [(x[1].name, x[1].min_gap, x[0]) for x in rows[:8]]}))


def cmd_report(a, meta, stores):
    from echotales.pipeline.segment.judge import CutRule

    rule = CutRule(**json.loads(Path(a.rule).read_text())["rule"])
    res = {"rule": asdict(rule), "model": a.model}
    for split in ("learn", "held"):
        js = judged(meta, stores, a, split)
        pooled, per, hn, detail = score_split(meta, stores, js, rule)
        res[split] = {"pooled": pooled, "per_novel": per, "hard_negatives": hn[0], "hard_negative_false_cuts": hn[1]}
        print(split, pooled, "hard neg", hn)
        for n, s in per.items():
            print("  ", n[:20], s)
        if split == "held":
            ex: dict[str, dict[str, list]] = {}
            for novel, ch, chap, g, pred, by in detail:
                text = {b.index: b.text for b in chap.blocks}
                anchor = lambda b, text=text: " ".join(text.get(b, "").split()[:5])  # noqa: E731
                e = ex.setdefault(novel, {"false_positives": [], "false_negatives": []})
                for b in sorted(pred - g):
                    j = by.get(b)
                    if len(e["false_positives"]) < 3:
                        e["false_positives"].append({"chapter": ch, "block": b, "anchor": anchor(b), "reason": j.reason if j else "", "judge": [j.time_continuous, j.same_location, j.same_people_in_focus] if j else None})
                for b in sorted(g - pred):
                    j = by.get(b)
                    if len(e["false_negatives"]) < 3:
                        e["false_negatives"].append({"chapter": ch, "block": b, "anchor": anchor(b), "reason": j.reason if j else "not a candidate", "judge": [j.time_continuous, j.same_location, j.same_people_in_focus] if j else None})
            res["examples"] = ex
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["cands", "judge", "rules", "report"])
    ap.add_argument("--split", default="learn", choices=["learn", "held", "all"])
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--disc-rate", type=float, default=0.10)
    ap.add_argument("--rule")
    ap.add_argument("--out")
    a = ap.parse_args()
    meta, stores = load()
    {"cands": cmd_cands, "judge": cmd_judge, "rules": cmd_rules, "report": cmd_report}[a.cmd](a, meta, stores)


if __name__ == "__main__":
    main()
