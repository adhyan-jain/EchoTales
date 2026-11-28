"""Markdown tables from data/eval/segment/scene_induction_v5_*.json (written by segment_v5_eval.py report)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    for path in sys.argv[1:]:
        r = json.loads(Path(path).read_text())
        print(f"\n### {Path(path).name} (model {r['model']}, tag '{r['tag']}', selected on {r.get('selected_on')})\n")
        print("| gold | split | arm | metric | TP | FP | FN | P | R | F1 |\n|---|---|---|---|---|---|---|---|---|---|")
        for gold in ("audited", "original"):
            for split, arms in r.get(gold, {}).items():
                for arm in ("outline", "fused"):
                    for m in ("exact", "pm1"):
                        p = arms[arm][m]["pooled"]
                        print(f"| {gold} | {split} | {arm} | {m} | {p['tp']} | {p['fp']} | {p['fn']} | {p['precision']} | {p['recall']} | {p['f1']} |")
        for gold in ("audited", "original"):
            for split, arms in r.get(gold, {}).items():
                per = arms["fused"]["pm1"]["per_novel"]
                print(f"\n{gold} {split} fused +-1 per novel F1: " + ", ".join(f"{n} {v['f1']} ({v['tp']}/{v['fp']}/{v['fn']})" for n, v in per.items()))


if __name__ == "__main__":
    main()
