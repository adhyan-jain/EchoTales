"""Blind evidence sheets for model-generated gender labels (docs/research/PREFIX_FAITHFULNESS/PREREG_LABELS.md).

    /home/adhyan/Desktop/EchoTales/.venv/bin/python -I scripts/prefix_audit/label_sheets.py truth
    /home/adhyan/Desktop/EchoTales/.venv/bin/python -I scripts/prefix_audit/label_sheets.py prefix

Sheets hold the character's name, aliases and passages only. No value the system served (full or prefix build) is
printed, so the labeller is blind to what is being scored. LABEL PROVENANCE: MODEL-GENERATED (one annotator, Claude).
"""

from __future__ import annotations

import glob
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAP = ROOT / "data" / "scratch" / "prefix_audit"
AUD = ROOT / "data" / "eval" / "prefix_audit"
OUT = AUD / "labels"
BEFORE, AFTER, N_TRUTH, N_PREFIX = 120, 330, 9, 7


def conn(nid: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{SNAP / (nid + '.src.db')}?mode=ro", uri=True)


def gender_rows() -> list[dict]:
    rows: list[dict] = []
    for f in sorted(glob.glob(str(AUD / "audit_repair-off_*.json"))):
        d = json.load(open(f))
        rows += [dict(novel=d["novel"], **r) for r in d["rows"] if r["key"] == "gender"]
    return rows


def block_text(c: sqlite3.Connection, nid: str, chapter: float, block: int) -> str:
    spans = c.execute(
        "select start, text from span where novel_id=? and chapter=? and block_index=? order by start", (nid, chapter, block)
    ).fetchall()
    out, pos = "", 0
    for start, text in spans:
        out += " " * max(0, start - pos) + text
        pos = start + len(text)
    return out


def excerpts(c: sqlite3.Connection, nid: str, eid: str, upto: float | None, n: int, rng: random.Random) -> list[str]:
    q = "select chapter, block_index, offset, text from mention where novel_id=? and target_id=?"
    ms = c.execute(q + (" and chapter<=?" if upto is not None else "") + " order by chapter, offset",
                   (nid, eid) + ((upto,) if upto is not None else ())).fetchall()
    if not ms:
        return []
    by_ch: dict[float, list] = {}
    for m in ms:
        by_ch.setdefault(m[0], []).append(m)
    chapters = sorted(by_ch)
    picks = [chapters[round(i * (len(chapters) - 1) / max(1, n - 1))] for i in range(min(n, len(chapters)))] if len(chapters) > 1 else chapters
    out = []
    for ch in dict.fromkeys(picks):
        ch_, block, off, txt = rng.choice(by_ch[ch])
        body = block_text(c, nid, ch_, block)
        passage = re.sub(r"\s+", " ", body[max(0, off - BEFORE): off + AFTER]).strip()
        out.append(f"  [ch {ch_:g}] ...{passage}...")
    return out


def sheet(nid: str, eid: str, upto: float | None, n: int, rng: random.Random, c: sqlite3.Connection) -> str:
    name = c.execute("select canonical_label from self_entity where id=?", (eid,)).fetchone()
    aliases = [a for (a,) in c.execute(
        "select distinct alias from alias_binding where novel_id=? and target_id=? limit 6", (nid, eid))]
    total = c.execute("select count(*) from mention where novel_id=? and target_id=?" + (" and chapter<=?" if upto is not None else ""),
                      (nid, eid) + ((upto,) if upto is not None else ())).fetchone()[0]
    head = f"### {eid}\nname: {name[0] if name else '?'} | aliases: {', '.join(aliases) or '-'} | mentions{'' if upto is None else f' up to ch {upto:g}'}: {total}\n"
    return head + "\n".join(excerpts(c, nid, eid, upto, n, rng) or ["  (no passages)"]) + "\n"


def main() -> None:
    mode = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    rows = gender_rows()
    rng = random.Random(20261016)
    if mode == "truth":
        for nid in sorted({r["novel"] for r in rows}):
            ents = sorted({r["entity"] for r in rows if r["novel"] == nid})
            c = conn(nid)
            text = f"# TRUTH sheet {nid}: {len(ents)} characters. Label each: male | female | unknown (not determinable) | non-person\n\n"
            text += "\n".join(sheet(nid, e, None, N_TRUTH, rng, c) for e in ents)
            (OUT / f"sheet_truth_{nid}.txt").write_text(text)
            print(nid, len(ents))
    else:
        # exposed cuts: every diverging one plus an equal number of non-diverging exposed cuts, shuffled so the
        # labeller cannot tell which is which (the key is in prefix_key.json, not on the sheet).
        exposed = [r for r in rows if r["exposed"]]
        div = [r for r in exposed if r["diverge"]]
        non = rng.sample([r for r in exposed if not r["diverge"]], len(div))
        items = div + non
        rng.shuffle(items)
        key = []
        text = f"# PREFIX sheet: {len(items)} (character, cut) items. Label each from passages up to the cut ONLY: male | female | undetermined\n\n"
        for i, r in enumerate(items):
            c = conn(r["novel"])
            text += f"## item {i}  (cut: chapter {r['k']})\n" + sheet(r["novel"], r["entity"], float(r["k"]), N_PREFIX, rng, c) + "\n"
            key.append(dict(item=i, novel=r["novel"], entity=r["entity"], k=r["k"], diverge=r["diverge"]))
        (OUT / "sheet_prefix.txt").write_text(text)
        (OUT / "prefix_key.json").write_text(json.dumps(key, indent=1))
        print("items", len(items), "diverging", len(div))


if __name__ == "__main__":
    main()
