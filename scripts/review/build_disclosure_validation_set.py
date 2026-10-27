"""Build the item set for the pipeline-disclosure human validation app (docs/paper/journal/VALIDATION_PROTOCOL.md).

    python3 scripts/review/build_disclosure_validation_set.py

Input: the seeded manifest and key from scripts/paper/build_validation_sample.py. Output:
scripts/review/disclosure_validation_app/cases.json, which holds, per case, only what an annotator may see: the
character's name and aliases, passages up to the cut, and the one value the system served. No stratum, build identity,
repeat marker or model label is written. cases.json contains excerpts of copyrighted web serials, so it is gitignored and
deployed from this machine; it is regenerated from the manifest and the local source databases (data/scratch), never
committed. English cases need data/scratch/pd_db (python scripts/prefix_audit/pd_volume.py).

Humans see <= N_PASSAGES passages; model annotator 2 saw up to 24. That gap is stated in the protocol.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL = ROOT / "data" / "eval" / "validation"
SCRATCH = ROOT / "data" / "scratch"
OUT = ROOT / "scripts" / "review" / "disclosure_validation_app" / "cases.json"
ANNOTATORS = ["Adhyan", "Atharva", "Aryan"]
PAIRS = [(0, 1), (1, 2), (2, 0)]  # each case goes to two of three annotators in rotation
BEFORE, AFTER, N_PASSAGES = 150, 350, 8
TITLES = {"lord-of-the-mysteries": "Lord of the Mysteries", "omniscient-readers-viewpoint": "Omniscient Reader's Viewpoint",
          "reverend-insanity": "Reverend Insanity", "oliver-twist": "Oliver Twist", "three-musketeers": "The Three Musketeers"}


def conn(nid: str) -> sqlite3.Connection:
    p = SCRATCH / "pd_db" / f"{nid}.db" if nid in ("oliver-twist", "three-musketeers") else SCRATCH / "prefix_audit" / f"{nid}.src.db"
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def block_text(c: sqlite3.Connection, nid: str, chapter: float, block: int) -> str:
    out, pos = "", 0
    for start, text in c.execute("select start, text from span where novel_id=? and chapter=? and block_index=? order by start",
                                 (nid, chapter, block)).fetchall():
        out += " " * max(0, start - pos) + text
        pos = start + len(text)
    return out


def passages(c: sqlite3.Connection, nid: str, eid: str, upto: float, seed: str) -> list[dict]:
    rng = random.Random(seed)
    ms = c.execute("select chapter, block_index, offset, text from mention where novel_id=? and target_id=? and chapter<=? "
                   "order by chapter, offset", (nid, eid, upto)).fetchall()
    by_ch: dict[float, list] = {}
    for m in ms:
        by_ch.setdefault(m[0], []).append(m)
    chs = sorted(by_ch)
    if len(chs) > N_PASSAGES:  # spread evenly over the chapters up to the cut, as the model annotators' sheets do
        chs = [chs[round(i * (len(chs) - 1) / (N_PASSAGES - 1))] for i in range(N_PASSAGES)]
    out = []
    for ch in dict.fromkeys(chs):
        _, block, off, mtext = rng.choice(by_ch[ch])
        body = block_text(c, nid, ch, block)
        seg = re.sub(r"\s+", " ", body[max(0, off - BEFORE): off + AFTER]).strip()
        out.append(dict(chapter=ch, text=seg, mention=mtext))
    return out


def main() -> None:
    man = json.load(open(VAL / "pipeline_disclosure_sample.json"))
    key = json.load(open(VAL / "pipeline_disclosure_sample_key.json"))
    base = {c["case"]: c for c in man["cases"] if "repeat_of" not in c}
    cases = []
    for c in man["cases"]:
        src = base[c.get("repeat_of", c["case"])]
        nid, eid, k = src["novel"], src["entity"], float(src["k"])
        con = conn(nid)
        name = con.execute("select canonical_label from self_entity where id=?", (eid,)).fetchone()
        aliases = [a for (a,) in con.execute("select distinct alias from alias_binding where novel_id=? and target_id=? limit 6", (nid, eid))]
        ps = passages(con, nid, eid, k, src["case"])
        total = con.execute("select count(*) from mention where novel_id=? and target_id=? and chapter<=?", (nid, eid, k)).fetchone()[0]
        kv = key[src["case"]]
        # S5 cases exist to ask about a value the repair withheld; every other stratum shows what the unrepaired stage served.
        served = kv["served_repaired"] if src["stratum"] == "S5" else kv["served_unrepaired"]
        served = served if served in ("male", "female") else None
        cases.append(dict(case=c["case"], book=TITLES[nid], name=name[0] if name else "?", aliases=aliases, cut=k, mentions=total,
                          passages=ps, served=served))
    random.Random(man["seed"]).shuffle(cases)
    pair_of: dict[str, tuple[int, int]] = {}
    for i, c in enumerate([x for x in cases if not x["case"].startswith("R")]):
        pair_of[c["case"]] = PAIRS[i % 3]
    rep_of = {c["case"]: c["repeat_of"] for c in man["cases"] if "repeat_of" in c}
    for c in cases:  # a repeat goes to the same two people as its original, so self-consistency is measurable
        a, b = pair_of[rep_of.get(c["case"], c["case"])]
        c["annotators"] = [ANNOTATORS[a], ANNOTATORS[b]]
    blob = json.dumps(dict(version="disclosure-validation-v1", manifest_seed=man["seed"], annotators=ANNOTATORS, cases=cases),
                      ensure_ascii=False, indent=1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(blob)
    per = {n: sum(n in c["annotators"] for c in cases) for n in ANNOTATORS}
    print(f"wrote {OUT}: {len(cases)} cases, per annotator {per}, sha256 {hashlib.sha256(blob.encode()).hexdigest()[:12]}")
    print("no passages:", [c["case"] for c in cases if not c["passages"]])


if __name__ == "__main__":
    main()
