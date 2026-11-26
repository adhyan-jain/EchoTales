"""The bake-off runner's `hybrid:<llm tag>:<tau_high>:<tau_low>` spec: parsing, wiring and the two-phase run (fakes only)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from echotales.pipeline.eval import ner_spans as ns
from echotales.pipeline.mentions.ner import NerSpan
from echotales.pipeline.mentions.ner_classify import ClassifyItem, NerClassifyResponse

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts/eval/ner_bakeoff.py"
_spec = importlib.util.spec_from_file_location("ner_bakeoff", _SCRIPT)
bakeoff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bakeoff)


def test_parse_keeps_colons_in_the_tag():
    assert bakeoff.parse_hybrid_spec("hybrid:qwen3:8b:0.7:0.3") == ("qwen3:8b", 0.7, 0.3)
    assert bakeoff.parse_hybrid_spec("hybrid:gemma2:9b:0.6:0.4") == ("gemma2:9b", 0.6, 0.4)


@pytest.mark.parametrize("bad", ["hybrid", "hybrid:qwen3:8b", "hybrid:qwen3:8b:0.7", "hybrid:m:x:0.3",
                                 "hybrid:m:0.3:0.7", "hybrid::0.7:0.3", "hybrid:m:1.5:0.3"])
def test_parse_rejects_malformed(bad):
    with pytest.raises(SystemExit):
        bakeoff.parse_hybrid_spec(bad)


class FakeEncoder:
    def __init__(self, name, spans):
        self.name, self.spans, self.model_id, self.model_version = name, spans, name, "v"
        self.unloaded = False

    def detect(self, text):
        return [s for s in self.spans if text[s.start:s.end] == s.text]

    def unload(self):
        self.unloaded = True


class FakeClient:
    def __init__(self):
        self.calls = 0

    def complete(self, task, prompt, schema, **kw):
        self.calls += 1
        return SimpleNamespace(value=NerClassifyResponse(items=[ClassifyItem(id=0, is_name=True)]))


def test_build_and_run_hybrid_with_fakes(tmp_path):
    text = "Fang Yuan met Zorblax. Nothing."
    gl = FakeEncoder("gliner", [NerSpan("Fang Yuan", 0, 9, "character", 0.9), NerSpan("Zorblax", 14, 21, "character", 0.5)])
    sp = FakeEncoder("spacy", [])
    client = FakeClient()
    det, meta = bakeoff.build_hybrid("hybrid:fake:7b:0.7:0.3", client=client, gliner=gl, spacy=sp, cache_dir=tmp_path)
    assert meta["tau_high"] == 0.7 and meta["tau_low"] == 0.3 and meta["classifier_model"] == "fake:7b"
    assert meta["gliner_hf_revision"] == bakeoff.GLINER_REVISION and "none" in meta["gazetteer"]
    docs = [{"doc_id": "d", "text": text, "spans": []}]
    (preds, runtime), extra = bakeoff.run_hybrid(det, docs, ns)
    assert gl.unloaded and extra["classifier_calls"] == 1 and extra["route_counts"]["accept"] == 1
    assert {s.text for s in preds["d"]} == {"Fang Yuan", "Zorblax"}
    assert runtime["seconds_per_1k_tokens"] is not None
    # Second run with different taus reads the verdict from disk and makes no new LLM call.
    det2, _ = bakeoff.build_hybrid("hybrid:fake:7b:0.8:0.3", client=client, gliner=gl, spacy=sp, cache_dir=tmp_path)
    _, extra2 = bakeoff.run_hybrid(det2, docs, ns)
    assert extra2["classifier_calls"] == 0 and client.calls == 1
