"""OLMo training-data check (PREREG_PD_CONFIRM_v2_addendum_3.md, exploratory): is each event's book in OLMo-2's public training corpus?

Callers: run by hand after the events file is frozen and the olmo32b E1 run exists. For each book of a confirmatory event: 3 verbatim spans of 12
consecutive words from the prefix at 20%, 50% and 80% of the prefix (starting at a sentence start), each counted with the infini-gram API
(index v4_olmo-2-1124-13b-instruct_llama, query_type count). Presence score = spans with count >= 1 (0 to 3); present if >= 2. Then the Spearman
correlation of the score with olmo32b's per-event gap (permutation over books, 20,000 shuffles, seed 20261101). If the API cannot be queried
within 20 minutes of the start, the check is recorded as "not available". Output: data/eval/chimera/confirm/main/olmo_corpus_check.json.
"""
from __future__ import annotations

import json
import math
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_reveal_benchmark as PD  # noqa: E402

P = Path("docs/research/preregistrations")
OUT = Path("data/eval/chimera/confirm/main")
URL, INDEX = "https://api.infini-gram.io/", "v4_olmo-2-1124-13b-instruct_llama"
BUDGET_S = 20 * 60


def spans(text: str, cut: int):
    pre = text[:cut]
    out = []
    for frac in (0.2, 0.5, 0.8):
        pos = int(len(pre) * frac)
        m = re.compile(r"[.!?][”\"’')]*\s+").search(pre, pos)
        start = m.end() if m else pos
        out.append(" ".join(pre[start:start + 400].split()[:12]))
    return out


def count(c: httpx.Client, q: str):
    for k in range(3):
        try:
            j = c.post(URL, json=dict(index=INDEX, query_type="count", query=q), timeout=90.0).json()
            if "count" in j:
                return int(j["count"])
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(3 * (k + 1))
    return None


def main():
    t0 = time.time()
    evs = json.loads((P / "PD_confirm_events_v1.json").read_text())["events"]
    texts = Path("data/raw/pd_confirm/texts")
    books = {}
    for ev in evs:
        if ev["gutenberg"] in books:
            continue
        text = PD.load_text(texts, ev["gutenberg"])
        books[ev["gutenberg"]] = spans(text, PD.locate(ev, text)["cut"])
    res = {}
    with httpx.Client() as c, ThreadPoolExecutor(6) as ex:
        futs = [(g, i, ex.submit(count, c, q)) for g, qs in books.items() for i, q in enumerate(qs)]
        for g, i, f in futs:
            try:
                v = f.result(timeout=max(1, BUDGET_S - (time.time() - t0)))
            except Exception:
                v = None
            res.setdefault(g, {})[i] = v
            if time.time() - t0 > BUDGET_S:
                break
    done = {g: v for g, v in res.items() if len(v) == 3 and all(x is not None for x in v.values())}
    if len(done) < 10:
        (OUT / "olmo_corpus_check.json").write_text(json.dumps(dict(status="not available", reason=f"only {len(done)} books answered in 20 minutes")))
        print("not available:", len(done), "books answered")
        return
    score = {g: sum(1 for x in v.values() if x >= 1) for g, v in done.items()}
    run = json.loads((OUT / "e1_olmo32b.json").read_text())
    by = {e["id"]: e for e in evs}
    per = {}
    for i, t in run["truth"].items():
        if t["kind"] == "pre" and by[t["event"]].get("split") == "test":
            h = int(run["real"][i]["A"] == t["identity_letter"]) - int(run["real"][i]["B"] == t["identity_letter"])
            per.setdefault(by[t["event"]]["gutenberg"], {}).setdefault(t["event"], []).append(h)
    gap = {g: float(np.mean([np.mean(v) for v in d.values()])) for g, d in per.items()}
    bk = sorted(set(done) & set(gap))
    x = np.array([score[b] for b in bk])
    y = np.array([gap[b] for b in bk])
    rho = float(stats.spearmanr(x, y)[0]) if len(set(x)) > 1 else float("nan")
    rng, cnt, B = random.Random(20261101), 0, 20000
    for _ in range(B):
        xp = list(x)
        rng.shuffle(xp)
        r_ = stats.spearmanr(xp, y)[0]
        cnt += (not math.isnan(r_)) and abs(r_) >= abs(rho)
    present = [b for b in bk if score[b] >= 2]
    absent = [b for b in bk if score[b] < 2]
    out = dict(status="done", exploratory=True, index=INDEX, books_queried=len(done), books_with_gap=len(bk),
               score_distribution={int(k): int((x == k).sum()) for k in set(x)}, spearman=rho, perm_p_two_sided=(cnt + 1) / (B + 1),
               present_books=len(present), absent_books=len(absent),
               mean_gap_present=float(np.mean([gap[b] for b in present])) if present else None,
               mean_gap_absent=float(np.mean([gap[b] for b in absent])) if absent else None, wall_seconds=round(time.time() - t0, 1))
    (OUT / "olmo_corpus_check.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out))


if __name__ == "__main__":
    main()
