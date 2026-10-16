"""Confirmatory study, step 1: choose the books (PD_CONFIRM_event_mining_rules_v1.md sections 1, 2, 8, 9; PREREG_PD_CONFIRM_v2_L40S.md section 1).

Callers: run by hand, once. Reads data/raw/pd_confirm/pg_catalog.csv (Gutenberg catalogue, fetched 2026-10-16) and
data/raw/pd_confirm/wikidata_pg_sitelinks.csv (one SPARQL query, same date), writes docs/research/preregistrations/PD_confirm_books_v1.json
(ids, titles, authors, W, band, order, dev/test) and downloads the texts of the drawn books to the git-ignored data/raw/pd_confirm/texts/.
Eligibility is decided from catalogue metadata only (no book text is read before the draw): language en, type Text, fiction (subjects
contain Fiction or LoCC starts PR, PS, PZ; subjects containing Drama, Poetry, Essays, Letters or Biography excluded), and "published before
1928" approximated from the catalogue's author years (every author died before 1928, or has no death year and was born before 1850; the
catalogue has no first-publication year; stated limit). Seed 20261101; 40 books per band; the shuffled draw is the mining order.
Split: SHA-256 rule of the mining file section 9 (books, not events).
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx

RAW = Path("data/raw/pd_confirm")
P = Path("docs/research/preregistrations")
SEED = 20261101
EXCL_SUBJ = re.compile(r"Drama|Poetry|Essays|Letters|Biography", re.I)
UA = "EchoTales-research/1.0 (academic; contact via repo owner)"


def author_ok(authors: str) -> bool:
    """Catalogue Authors look like 'Doyle, Arthur Conan, 1859-1930'."""
    if not authors.strip():
        return False
    for a in authors.split(";"):
        m = re.search(r"(\d{4})\??\s*-\s*(\d{4})?", a)
        if not m:
            return False
        b, d = int(m.group(1)), (int(m.group(2)) if m.group(2) else None)
        if not ((d is not None and d < 1928) or (d is None and b < 1850)):
            return False
    return True


def main():
    rnd = int(sys.argv[sys.argv.index("--round") + 1]) if "--round" in sys.argv else 1  # PREREG_PD_CONFIRM_v2_addendum_1.md
    ex = json.loads((P / "PD_CONFIRM_excluded_books.json").read_text())
    excluded = {int(x) for x in ex["used"]} | {int(k) for k in ex["examined_and_dropped"]}
    W = {int(r["pg"]): int(r["n"]) for r in csv.DictReader(open(RAW / "wikidata_pg_sitelinks.csv"))}
    elig = []
    for r in csv.DictReader(open(RAW / "pg_catalog.csv", encoding="utf-8")):
        if r["Type"] != "Text" or r["Language"] != "en":
            continue
        subj, locc = r["Subjects"], r["LoCC"]
        if not (re.search(r"Fiction", subj) or re.match(r"(PR|PS|PZ)", locc)) or EXCL_SUBJ.search(subj):
            continue
        gid = int(r["Text#"])
        if gid in excluded or not author_ok(r["Authors"]):
            continue
        elig.append(dict(id=gid, title=r["Title"].replace("\n", " "), authors=r["Authors"], W=W.get(gid, 0)))
    for e in elig:
        e["band"] = "high" if e["W"] >= 20 else "mid" if e["W"] >= 3 else "low"
    prev = json.loads((P / "PD_confirm_books_v1.json").read_text()) if rnd > 1 else None
    already = {b["id"] for b in prev["books"]} if prev else set()
    rng = random.Random(SEED + rnd - 1)
    drawn, counts = [], {}
    for band in ("high", "mid", "low"):
        pool = sorted((e for e in elig if e["band"] == band and e["id"] not in already), key=lambda e: e["id"])
        counts[band] = len(pool)
        drawn += rng.sample(pool, min(40, len(pool)))
    rng.shuffle(drawn)  # bands interleaved, so a time-limited mining pass keeps the fame spread
    base = max((b["order"] for b in prev["books"]), default=-1) + 1 if prev else 0
    for i, e in enumerate(drawn):
        e["order"] = base + i
        e["round"] = rnd
        e["split"] = "dev" if int(hashlib.sha256((str(e["id"]) + "20261101").encode()).hexdigest()[:8], 16) % 100 < 20 else "test"
    for e in drawn:
        e.setdefault("round", rnd)
    if prev:
        prev["books"] += drawn
        prev.setdefault("rounds", {})[str(rnd)] = dict(seed=SEED + rnd - 1, eligible_remaining_by_band=counts, drawn=len(drawn))
        out = prev
    else:
        out = dict(eligible_by_band=counts, eligible_total=len(elig), excluded_used_books=len(excluded), seed=SEED, books=drawn,
                   rounds={"1": dict(seed=SEED, drawn=len(drawn))}, note="eligibility from catalogue metadata only; texts fetched after this file was written")
    (P / "PD_confirm_books_v1.json").write_text(json.dumps(out, indent=1))
    print("eligible", len(elig), counts, "drawn", len(drawn), "dev", sum(e["split"] == "dev" for e in drawn))
    if "--no-download" in sys.argv:
        return
    tdir = RAW / "texts"
    tdir.mkdir(exist_ok=True)
    ok = bad = 0
    with httpx.Client(follow_redirects=True, timeout=60.0, headers={"User-Agent": UA}) as c:
        for e in drawn:
            f = tdir / f"pg{e['id']}.txt"
            if f.exists() and f.stat().st_size > 1000:
                ok += 1
                continue
            for url in (f"https://www.gutenberg.org/cache/epub/{e['id']}/pg{e['id']}.txt", f"https://www.gutenberg.org/files/{e['id']}/{e['id']}-0.txt"):
                try:
                    r = c.get(url)
                except httpx.HTTPError:
                    continue
                if r.status_code == 200 and "*** START" in r.text and "*** END" in r.text:
                    f.write_text(r.text, encoding="utf-8")
                    ok += 1
                    break
            else:
                bad += 1
            time.sleep(1.5)
    print("downloaded ok", ok, "failed", bad)


if __name__ == "__main__":
    main()
