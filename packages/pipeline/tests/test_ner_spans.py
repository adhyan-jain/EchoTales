"""Gold validity and metric correctness for the romanized-name span eval (no network, no GPU)."""

from __future__ import annotations

from pathlib import Path

import pytest
from echotales.pipeline.eval import ner_spans as ns
from echotales.pipeline.mentions.ner import HeuristicDetector, NerSpan

GOLD_DIR = Path(__file__).resolve().parents[3] / "data" / "gold" / "ner_romanized"


def _doc(text, spans, doc_id="d1", background="zh"):
    return {"doc_id": doc_id, "source": "synthetic", "background": background, "split": "dev", "text": text,
            "spans": [{"start": a, "end": b, "surface": text[a:b], "label": lab, "category": cat}
                      for a, b, lab, cat in spans]}


def _sp(start, end, label="character", score=1.0, text="x"):
    return NerSpan(text=text, start=start, end=end, label=label, score=score)


def test_real_gold_offsets_and_schema_valid():
    docs = ns.load_gold(GOLD_DIR, strict=False)
    assert len(docs) >= 90
    errors = [e for d in docs for e in ns.validate_record(d)]
    assert errors == []
    assert {d["split"] for d in docs} == {"dev", "test"}
    assert len({d["doc_id"] for d in docs}) == len(docs)
    for bg in ns.BACKGROUNDS:
        assert {"dev", "test"} <= {d["split"] for d in docs if d["background"] == bg}


def test_validator_catches_bad_offsets():
    d = _doc("Fang Yuan bowed", [(0, 9, "person", "ordinary")])
    d["spans"][0]["surface"] = "Fang Yuen"
    assert any("surface" in e for e in ns.validate_record(d))
    d2 = _doc("Fang Yuan bowed", [(0, 4, "person", "ordinary"), (3, 9, "person", "ordinary")])
    assert any("overlapping" in e for e in ns.validate_record(d2))


def test_exact_vs_overlap():
    doc = _doc("Fang Yuan bowed", [(0, 9, "person", "ordinary")])
    preds = {"d1": [_sp(0, 4)]}  # "Fang" only
    m = ns.score_predictions([doc], preds)["metrics"]
    assert m["exact"]["span_only"]["overall"]["tp"] == 0
    assert m["overlap"]["span_only"]["overall"]["tp"] == 1


def test_one_to_one_matching():
    # One long prediction covers two gold spans: only one may match.
    doc = _doc("Fang Yuan Lu Chen", [(0, 9, "person", "ordinary"), (10, 17, "person", "ordinary")])
    m = ns.score_predictions([doc], {"d1": [_sp(0, 17)]})["metrics"]["overlap"]["span_only"]["overall"]
    assert (m["tp"], m["fp"], m["fn"]) == (1, 0, 1)
    # Two predictions on one gold span: one match, one false positive.
    doc2 = _doc("Fang Yuan bowed", [(0, 9, "person", "ordinary")])
    m2 = ns.score_predictions([doc2], {"d1": [_sp(0, 4), _sp(5, 9)]})["metrics"]["overlap"]["span_only"]["overall"]
    assert (m2["tp"], m2["fp"], m2["fn"]) == (1, 1, 0)


def test_label_aware_and_personish_group():
    doc = _doc("the clan head spoke to Fang Yuan in Qing Mao Mountain",
               [(0, 13, "title_epithet", "shared_title"), (23, 32, "person", "ordinary"),
                (36, 53, "location", "ordinary")])
    preds = {"d1": [_sp(0, 13, "character"), _sp(23, 32, "location"), _sp(36, 53, "location")]}
    m = ns.score_predictions([doc], preds)["metrics"]["exact"]
    assert m["span_only"]["overall"]["tp"] == 3
    la = m["label_aware"]["overall"]
    assert la["tp"] == 2 and la["fp"] == 1 and la["fn"] == 1  # character on title_epithet OK; location on person not
    assert m["label_aware"]["by_gold_label"]["title_epithet"]["recall"] == 1.0
    assert m["label_aware"]["by_gold_label"]["person"]["recall"] == 0.0


def test_breakdowns_and_error_lists():
    d1 = _doc("Rain fell. Bai bowed.", [(0, 4, "person", "word_like"), (11, 14, "person", "word_like")],
              "d1", "zh")
    d2 = _doc("Vael'thar came.", [(0, 9, "person", "invented")], "d2", "invented")
    res = ns.score_predictions([d1, d2], {"d1": [_sp(11, 14, text="Bai"), _sp(5, 9, text="fell")], "d2": []})
    ov = res["metrics"]["exact"]["span_only"]
    assert ov["by_category"]["word_like"]["recall"] == 0.5
    assert ov["by_category"]["invented"]["recall"] == 0.0
    assert ov["by_background"]["zh"]["precision"] == 0.5
    assert ov["by_background"]["invented"]["recall"] == 0.0
    err = res["errors"]["exact"]["span_only"]
    assert [f["surface"] for f in err["false_positives"]] == ["fell"]
    assert {(m["doc_id"], m["surface"]) for m in err["missed"]} == {("d1", "Rain"), ("d2", "Vael'thar")}


def test_label_map_hook():
    doc = _doc("Fang Yuan bowed", [(0, 9, "person", "ordinary")])
    preds = {"d1": [_sp(0, 9, "PER")]}
    default = ns.score_predictions([doc], preds)["metrics"]["exact"]["label_aware"]["overall"]["tp"]
    mapped = ns.score_predictions([doc], preds, label_map={"per": "person"})["metrics"]["exact"]["label_aware"]
    assert default == 0 and mapped["overall"]["tp"] == 1


def test_sweep_picks_highest_recall_with_precision_floor():
    text = "Aaaa Bbbb Cccc Dddd"
    doc = _doc(text, [(0, 4, "person", "ordinary"), (5, 9, "person", "ordinary"), (10, 14, "person", "ordinary")])
    # scores: two true names at 0.9/0.6, one true at 0.3, one junk at 0.4 (Dddd)
    preds = {"d1": [_sp(0, 4, score=0.9), _sp(5, 9, score=0.6), _sp(10, 14, score=0.3), _sp(15, 19, score=0.4)]}
    sw = ns.sweep_thresholds([doc], preds, min_precision=0.95)
    assert sw["chosen"]["threshold"] == 0.55 or sw["chosen"]["threshold"] == 0.6
    assert sw["chosen"]["recall"] == pytest.approx(2 / 3)
    assert sw["chosen"]["precision"] == 1.0
    assert len(sw["rows"]) == 17 and sw["rows"][0]["threshold"] == 0.1 and sw["rows"][-1]["threshold"] == 0.9


def test_sweep_falls_back_to_max_f1():
    doc = _doc("Aaaa Bbbb", [(0, 4, "person", "ordinary"), (5, 9, "person", "ordinary")])
    preds = {"d1": [_sp(0, 4, score=0.8), _sp(10, 14, score=0.8), _sp(5, 9, score=0.2)]}
    sw = ns.sweep_thresholds([doc], preds, min_precision=0.99)
    assert "max F1" in sw["rule"]
    assert sw["chosen"]["f1"] == max(r["f1"] for r in sw["rows"])


def test_evaluate_heuristic_runs_and_serialises(tmp_path):
    docs = ns.load_gold(GOLD_DIR, "dev")
    res = ns.evaluate(HeuristicDetector(), docs)
    assert res["runtime"]["wall_seconds"] >= 0
    out = ns.write_result(tmp_path / "r.json", res, {"system": "heuristic"})
    import json

    payload = json.loads(out.read_text())
    assert payload["system"] == {"system": "heuristic"} and "timestamp" in payload and "hardware" in payload
