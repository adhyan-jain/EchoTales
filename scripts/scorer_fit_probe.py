"""Would fitting the existing scorer help? A bounded, chronological probe.

Run only after `scorer_diagnosis.py`, and only to answer one question: given the
SILVER labels that exist, does fitting `ScoringModel` (the existing logistic
model -- no new architecture) produce a scorer that links correctly on later
chapters, and *what does it learn*?

Chronological split by chapter, never random: a random split lets late-volume
evidence about a character calibrate an early decision about the same one.
Train on the earliest 60% of labelled chapters, calibrate on the next 20%,
evaluate once on the final 20%.

The default scorer is not touched; the fitted one is written to
`data/eval/scorer/fitted.json` as an ablation artifact only.

SILVER -- LLM-derived reference set (Claude), not human gold; no IAA.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from echotales.core.models import SCORED_FEATURES, EvidenceVector
from echotales.pipeline.resolve.score import ScoringModel

DIAG = Path("data/eval/scorer_diagnosis")
OUT = Path("data/eval/scorer")
LINK, NEW = 0.80, 0.35


def main() -> int:
    chapter = {r["case_id"]: float(r["chapter"]) for r in csv.DictReader((DIAG / "cases.csv").open())}
    rows = [r for r in csv.DictReader((DIAG / "candidates.csv").open())]
    feat_names = [k for k in rows[0] if k not in ("case_id", "candidate", "is_gold", "prefilter", "raw_score")]
    data = []
    for r in rows:
        feats = {k: float(r[k]) for k in feat_names if r[k] != ""}
        data.append((chapter[r["case_id"]], r["case_id"], EvidenceVector(**feats), r["is_gold"] == "1", r["prefilter"]))
    data.sort(key=lambda t: t[0])
    chapters = sorted({t[0] for t in data})
    c_train = chapters[int(len(chapters) * 0.6)]
    c_dev = chapters[int(len(chapters) * 0.8)]
    train = [(e, y) for c, _, e, y, _ in data if c <= c_train]
    dev = [(e, y) for c, _, e, y, _ in data if c_train < c <= c_dev]
    test = [(cid, e, y, pf) for c, cid, e, y, pf in data if c > c_dev]

    raw = ScoringModel()
    fitted = ScoringModel().fit(train)
    calibrated = ScoringModel().fit(train).calibrate(dev) if dev else fitted

    def evaluate(model: ScoringModel) -> dict[str, float | int]:
        by_case: dict[str, list[tuple[float, bool]]] = {}
        for cid, e, y, _pf in test:
            by_case.setdefault(cid, []).append((model.probability(e), y))
        link = new = defer = correct_link = false_link = 0
        for cands in by_case.values():
            top_p, top_gold = max(cands, key=lambda t: t[0])
            if top_p >= LINK:
                link += 1
                correct_link += top_gold
                false_link += not top_gold
            elif top_p < NEW:
                new += 1
            else:
                defer += 1
        n = len(by_case) or 1
        return {"cases": len(by_case), "link_coverage": round(link / n, 4), "defer_rate": round(defer / n, 4),
                "new_rate": round(new / n, 4), "false_link_rate": round(false_link / max(link, 1), 4),
                "link_accuracy": round(correct_link / max(link, 1), 4)}

    report = {
        "banner": "SILVER -- LLM-derived reference set (Claude), not human gold; no IAA",
        "split_chapters": {"train_le": c_train, "dev_le": c_dev},
        "sizes": {"train_pairs": len(train), "dev_pairs": len(dev), "test_pairs": len(test),
                  "train_positive": sum(y for _, y in train)},
        "test_prefilter_verdicts": {v: sum(1 for *_, pf in test if pf == v) for v in {pf for *_, pf in test}},
        "raw": evaluate(raw), "fitted": evaluate(fitted), "calibrated": evaluate(calibrated),
        "fitted_weights": {k: round(v, 3) for k, v in fitted.weights.items()},
        "fitted_bias": round(fitted.bias, 3),
        "scored_features": list(SCORED_FEATURES),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    fitted.save(OUT / "fitted.json")
    (OUT / "fit_probe.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
