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


def test_predictions_round_trip_to_rescore_and_by_source(tmp_path):
    import json

    d1 = _doc("Fang Yuan bowed to Bai Ling.", [(0, 9, "person", "ordinary"), (22, 30, "person", "ordinary")])
    d2 = _doc("Vael'thar came.", [(0, 9, "person", "invented")], "d2", "invented")
    d2["source"] = "public_domain"
    docs = [d1, d2]
    preds = {"d1": [_sp(0, 9, score=0.9), _sp(22, 30, score=0.35), _sp(10, 15, "location", score=0.5)],
             "d2": [_sp(0, 9, score=0.7)]}
    res = ns.evaluate(None, docs, threshold=0.4, detected=(preds, {"wall_seconds": 0.1}))
    assert set(res["metrics_by_source"]) == {"synthetic", "public_domain"}
    assert res["metrics_by_source"]["synthetic"]["exact"]["span_only"]["overall"]["tp"] == 1
    assert res["metrics_by_source"]["public_domain"]["overlap"]["span_only"]["overall"]["tp"] == 1
    assert res["metrics"]["overlap"]["span_only"]["overall"]["tp"] == 2
    # Raw predictions are stored unthresholded, so the 0.35 span is still there.
    assert len(res["predictions"]["d1"]) == 3

    out = ns.write_result(tmp_path / "r.json", res, {"system": "x"})
    payload = json.loads(out.read_text(encoding="utf-8"))
    again = ns.rescore_payload(payload, docs, threshold=0.4)
    assert again["metrics"] == res["metrics"]
    assert again["metrics_by_source"] == res["metrics_by_source"]
    lower = ns.rescore_payload(payload, docs, threshold=0.3)
    assert lower["metrics"]["overlap"]["span_only"]["overall"]["tp"] == 3
    # A result that does not cover every gold doc is refused rather than scored as empty.
    payload["predictions"].pop("d2")
    with pytest.raises(ValueError, match="missing"):
        ns.rescore_payload(payload, docs)
    # Unreachable ollama degrades to nulls instead of raising.
    meta = ns.ollama_model_meta("nope:0b", base_url="http://127.0.0.1:9", timeout=0.5)
    assert meta == {"digest": None, "parameter_size": None, "quantization_level": None, "size_vram": None}


def test_evaluate_heuristic_runs_and_serialises(tmp_path):
    docs = ns.load_gold(GOLD_DIR, "dev")
    res = ns.evaluate(HeuristicDetector(), docs)
    assert res["runtime"]["wall_seconds"] >= 0
    out = ns.write_result(tmp_path / "r.json", res, {"system": "heuristic"})
    import json

    payload = json.loads(out.read_text())
    assert payload["system"] == {"system": "heuristic"} and "timestamp" in payload and "hardware" in payload


def test_boundary_mode_ignores_article_and_honorific():
    cases = [("the Emperor", "Emperor"), ("Dokja-ssi", "Dokja"), ("Mr. Darcy", "Darcy")]
    for gold_surface, pred_surface in cases:
        text = f"x {gold_surface} y"
        doc = _doc(text, [(2, 2 + len(gold_surface), "person", "ordinary")])
        a = text.index(pred_surface)
        m = ns.score_predictions([doc], {"d1": [_sp(a, a + len(pred_surface), text=pred_surface)]})["metrics"]
        assert m["boundary"]["span_only"]["overall"]["tp"] == 1, gold_surface
        assert m["exact"]["span_only"]["overall"]["tp"] == 0, gold_surface
    # Overlapping but a different name is not a boundary match.
    doc = _doc("Fang Yuan bowed", [(0, 9, "person", "ordinary")])
    m = ns.score_predictions([doc], {"d1": [_sp(0, 4, text="Fang")]})["metrics"]
    assert m["boundary"]["span_only"]["overall"]["tp"] == 0


def test_generic_role_excluded_by_default_and_reported():
    text = "The dean spoke to Fang Yuan"
    gold = [(0, 8, "title_epithet", "shared_title"), (18, 27, "person", "ordinary")]
    doc = _doc(text, gold)
    doc["spans"][0]["generic_role"] = True
    # Predicting only the name: the skipped generic role is not a miss.
    m = ns.score_predictions([doc], {"d1": [_sp(18, 27, text='Fang Yuan')]})["metrics"]["boundary"]["span_only"]
    assert (m["overall"]["fn"], m["overall"]["fp"]) == (0, 0)
    assert m["generic_role"] == {"gold": 1, "matched": 0, "recall": 0.0}
    # Predicting the generic role as well is not a false positive either, and counts toward its recall.
    m = ns.score_predictions([doc], {"d1": [_sp(0, 8, text='The dean'), _sp(18, 27, text='Fang Yuan')]})["metrics"]["boundary"]["span_only"]
    assert (m["overall"]["fn"], m["overall"]["fp"]) == (0, 0) and m["generic_role"]["recall"] == 1.0
    # include_generic scores it as ordinary gold.
    m = ns.score_predictions([doc], {"d1": [_sp(18, 27, text='Fang Yuan')]}, include_generic=True)["metrics"]["boundary"]["span_only"]
    assert m["overall"]["fn"] == 1


def test_nested_predictions_suppressed():
    doc = _doc("Bai Ningbing smiled", [(0, 12, "person", "ordinary")])
    preds = {"d1": [NerSpan(text="Bai Ningbing", start=0, end=12, label="character"),
                    NerSpan(text="Bai", start=0, end=3, label="character")]}
    m = ns.score_predictions([doc], preds)["metrics"]["exact"]["span_only"]["overall"]
    assert (m["tp"], m["fp"]) == (1, 0)
