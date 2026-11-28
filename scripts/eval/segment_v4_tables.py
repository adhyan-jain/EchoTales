"""Markdown tables from data/eval/segment/scene_induction_v4_<model>.json (written by segment_v4_eval.py report)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    for path in sys.argv[1:]:
        r = json.loads(Path(path).read_text())
        print(f"\n### {r['model']}\n")
        for gold in ("original", "audited"):
            if gold not in r:
                continue
            print(f"\n{gold} gold (arms: outline only, cast only, fused = {r['fusion']['fused']['mode']}); pooled P / R / F1\n")
            print("| split | arm | TP | FP | FN | P | R | F1 | params |\n|---|---|---|---|---|---|---|---|---|")
            for split in ("learn", "held"):
                for arm, v in r[gold][split].items():
                    p = v["pooled"]
                    pr = {k: x for k, x in v["params"].items() if k not in ("mode",)}
                    print(f"| {split} | {arm} | {p['tp']} | {p['fp']} | {p['fn']} | {p['precision']} | {p['recall']} | {p['f1']} | k={pr['cast_k']} theta={pr['theta']} w={pr['window']} sep={pr['use_sep']} gap={pr['min_gap']} conf>={pr['conf_min']} |")
            print("\nPer novel F1 of the fused arm (learn / held):\n")
            for n, s in r[gold]["learn"]["fused"]["per_novel"].items():
                h = r[gold]["held"]["fused"]["per_novel"].get(n, {})
                print(f"- {n}: learn {s['f1']} (TP {s['tp']} FP {s['fp']} FN {s['fn']}), held {h.get('f1', 'n/a')} (TP {h.get('tp')} FP {h.get('fp')} FN {h.get('fn')})")


if __name__ == "__main__":
    main()
