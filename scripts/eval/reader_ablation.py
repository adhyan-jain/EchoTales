"""Run the reader stage on every reference chapter from fresh baseline copies and score each chapter separately.

    python scripts/eval/reader_ablation.py run <label> [--novel N] [--chapters 7,14]
    python scripts/eval/reader_ablation.py compare <label_a> <label_b>

Why this exists: a prompt change that helps LotM ch7 can hurt ORV ch2, and every gain before this script was read off
the chapters the change was tuned on. A change counts only if it is measured on **all** reference chapters of **all**
novels from the same starting database, and a chapter that gets worse is printed, not averaged away. Results are
written to `data/eval/reader/<label>.json` with the commit they were produced by.

Scores are against model-drafted silver references (`data/gold/reader/`); held-out chapters (`"held_out": true`) are
reported on their own line because no change was tuned on them.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.eval import reader_gold as g
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.reader.runner import read_novel

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "eval" / "reader"
SCRATCH = ROOT / "data" / "scratch" / "ablation"
NOVELS = ("lord-of-the-mysteries", "reverend-insanity", "omniscient-readers-viewpoint")


def _gold_files(novel: str) -> list[Path]:
    return sorted((ROOT / "data" / "gold" / "reader").glob(f"{novel}-ch*.json"))


def _copy_baseline(novel: str) -> Path:
    """A fresh copy of the run-of-record database, so no run starts from another run's output."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    dst = SCRATCH / f"{novel}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(dst) + suffix).unlink(missing_ok=True)
    src = sqlite3.connect(f"file:{ROOT / 'data' / 'db' / (novel + '.db')}?mode=ro", uri=True)
    out = sqlite3.connect(dst)
    src.backup(out)
    out.close()
    src.close()
    return dst


def run(label: str, novels: tuple[str, ...], only: set[int] | None) -> None:
    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    result: dict = {"label": label, "commit": commit, "chapters": {}}
    t0 = time.time()
    for novel in novels:
        files = _gold_files(novel)
        golds = [g.load_reader_gold(f) for f in files]
        chapters = [x.chapter for x in golds if only is None or int(x.chapter) in only]
        db = _copy_baseline(novel)
        store = Store(str(db))
        read_novel(novel, store, ModelClient(store=store), chapters=chapters)
        for gold, f in zip(golds, files):
            if gold.chapter not in chapters:
                continue
            sp = g.score_speakers(gold, store)
            ap = g.score_appearance(gold, store)
            pl = g.score_persona_links(gold, store)
            ag = g.score_ages(gold, store)
            kd = g.score_kinds(gold, store)
            raw = json.loads(f.read_text(encoding="utf-8"))
            result["chapters"][f"{novel}:{int(gold.chapter)}"] = {
                "held_out": bool(raw.get("held_out", False)),
                "speakers": [sp.correct, sp.total],
                "false_dialogue": sp.false_dialogue if gold.lines_complete else None,
                "appearance": [ap.correct, ap.total], "persona_links": [pl.correct, pl.total],
                "ages": [ag.correct, ag.total], "kinds": [kd.correct, kd.total],
                "speaker_misses": sp.misses,
            }
        store.close()
    result["seconds"] = round(time.time() - t0)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{label}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    report(result)


def _pct(pair: list[int]) -> str:
    return f"{pair[0]}/{pair[1]}" + (f" {pair[0] / pair[1]:.0%}" if pair[1] else "")


def _sum(rows: list[dict], key: str) -> list[int]:  # type: ignore[type-arg]
    return [sum(r[key][0] for r in rows), sum(r[key][1] for r in rows)]


def report(result: dict) -> None:  # type: ignore[type-arg]
    print(f"== {result['label']} (commit {result['commit']}, {result.get('seconds', '?')}s) ==")
    for novel in NOVELS:
        rows = {k: v for k, v in result["chapters"].items() if k.startswith(novel)}
        if not rows:
            continue
        tuned = [v for v in rows.values() if not v["held_out"]]
        held = [v for v in rows.values() if v["held_out"]]
        sp = _pct(_sum(tuned, "speakers")) if tuned else "-"
        ap = _pct(_sum(tuned, "appearance")) if tuned else "-"
        line = f"{novel[:14]:14s} tuned speakers {sp:>11s}  appearance {ap:>9s}"
        if held:
            line += f" | held-out speakers {_pct(_sum(held, 'speakers'))}  appearance {_pct(_sum(held, 'appearance'))}"
        print(line)
    allrows = list(result["chapters"].values())
    print("ALL            speakers", _pct(_sum(allrows, "speakers")), " appearance", _pct(_sum(allrows, "appearance")),
          " persona", _pct(_sum(allrows, "persona_links")), " kinds", _pct(_sum(allrows, "kinds")))
    macro = [r["speakers"][0] / r["speakers"][1] for r in allrows if r["speakers"][1]]
    print(f"macro-average speakers over {len(macro)} chapters: {sum(macro) / len(macro):.1%}  (every chapter counts equally)")


def compare(a: str, b: str) -> None:
    ra = json.loads((OUT / f"{a}.json").read_text(encoding="utf-8"))
    rb = json.loads((OUT / f"{b}.json").read_text(encoding="utf-8"))
    print(f"{a} -> {b}: per chapter speakers (correct/total), appearance")
    worse = 0
    for key in sorted(set(ra["chapters"]) & set(rb["chapters"])):
        x, y = ra["chapters"][key], rb["chapters"][key]
        dx = y["speakers"][0] - x["speakers"][0]
        da = y["appearance"][0] - x["appearance"][0]
        flag = "  WORSE" if dx < 0 or da < 0 else ""
        worse += bool(flag)
        held = " [held-out]" if y["held_out"] else ""
        print(f"  {key:34s} speakers {x['speakers'][0]:3d} -> {y['speakers'][0]:3d} /{y['speakers'][1]:<3d} ({dx:+d})"
              f"   appearance {x['appearance'][0]} -> {y['appearance'][0]} ({da:+d}){held}{flag}")
    print(f"chapters that got worse on speakers or appearance: {worse}")
    report(rb)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "run":
        sel = tuple(sys.argv[sys.argv.index("--novel") + 1].split(",")) if "--novel" in sys.argv else NOVELS
        chosen = {int(x) for x in sys.argv[sys.argv.index("--chapters") + 1].split(",")} if "--chapters" in sys.argv else None
        run(sys.argv[2], sel, chosen)
    elif cmd == "compare":
        compare(sys.argv[2], sys.argv[3])
