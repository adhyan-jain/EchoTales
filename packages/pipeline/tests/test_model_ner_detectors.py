"""Model-backed NER detectors with fakes: no downloads, no GPU."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest
from echotales.pipeline.mentions import gliner_ner
from echotales.pipeline.mentions.gliner_ner import GlinerDetector, _sentence_chunks
from echotales.pipeline.mentions.nametag_ner import NameTagDetector
from echotales.pipeline.mentions.ner import NerEntity, _locate
from echotales.pipeline.mentions.spacy_ner import SpacyDetector


class FakeGliner:
    """Finds every 'Fang Yuan' / 'Kyoto' in the chunk it is handed."""

    def __init__(self, score: float = 0.9):
        self.calls: list[tuple[str, list[str], float]] = []
        self.score = score

    def predict_entities(self, text, labels, threshold=0.5):
        self.calls.append((text, labels, threshold))
        out = []
        for needle, label in (("Fang Yuan", "person"), ("Kyoto", "location")):
            i = text.find(needle)
            while i >= 0:
                out.append({"start": i, "end": i + len(needle), "text": needle, "label": label, "score": self.score})
                i = text.find(needle, i + 1)
        return out


def _prose(n: int) -> str:
    return " ".join(f"Sentence {i} mentions Fang Yuan in Kyoto." for i in range(n))


def test_chunk_offsets_map_back_across_boundaries():
    text = _prose(80)
    det = GlinerDetector(model=FakeGliner(), max_chars=300)
    spans = det.detect(text)
    assert len(det._model.calls) > 1
    assert all(text[s.start : s.end] == s.text for s in spans)
    assert sum(s.text == "Fang Yuan" for s in spans) == 80


def test_overlap_deduped_keeping_higher_score():
    text = _prose(30)
    chunks = _sentence_chunks(text, 200)
    assert any(chunks[i + 1][0] < chunks[i][1] for i in range(len(chunks) - 1))
    spans = GlinerDetector(model=FakeGliner(), max_chars=200).detect(text)
    assert len({(s.start, s.end) for s in spans}) == len(spans)


def test_chunks_cover_text_and_respect_limit():
    text = "x" * 2500  # one sentence longer than the limit is hard-split
    chunks = _sentence_chunks(text, 1000)
    assert all(e - s <= 1000 for s, e in chunks)
    assert chunks[0][0] == 0 and chunks[-1][1] == len(text)


def test_label_mapping_threshold_and_name():
    fake = FakeGliner()
    det = GlinerDetector(model=fake, threshold=0.42)
    spans = det.detect("Fang Yuan went to Kyoto.")
    assert {(s.text, s.label) for s in spans} == {("Fang Yuan", "character"), ("Kyoto", "location")}
    assert fake.calls[0][2] == 0.42
    assert "person" in fake.calls[0][1]
    assert det.name == "gliner:urchade/gliner_medium-v2.1"
    assert all(s.score == 0.9 for s in spans)


def test_unknown_label_dropped_and_context_ignored():
    class Odd(FakeGliner):
        def predict_entities(self, text, labels, threshold=0.5):
            return [{"start": 0, "end": 3, "text": text[:3], "label": "mystery", "score": 0.9}]

    assert GlinerDetector(model=Odd()).detect_with_context("Fang Yuan", ["X"]) == []


def test_model_version_from_config():
    m = FakeGliner()
    m.config = SimpleNamespace(_commit_hash="abc123")
    assert GlinerDetector(model=m).model_version == "abc123"
    assert GlinerDetector(model=FakeGliner()).model_version is None


def _fake_torch(available: bool, free: int, monkeypatch):
    cuda = SimpleNamespace(
        is_available=lambda: available,
        mem_get_info=lambda: (free, 8 * 1024**3),
        empty_cache=lambda: emptied.append(1),
    )
    emptied: list[int] = []
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=cuda))
    return emptied


def test_device_auto_selection(monkeypatch):
    _fake_torch(True, 4 * 1024**3, monkeypatch)
    assert gliner_ner.resolve_device("auto") == "cuda"
    _fake_torch(True, 1 * 1024**3, monkeypatch)
    assert gliner_ner.resolve_device("auto") == "cpu"
    _fake_torch(False, 0, monkeypatch)
    assert gliner_ner.resolve_device("auto") == "cpu"
    assert gliner_ner.resolve_device("cpu") == "cpu"


def test_unload_drops_model_and_empties_cache(monkeypatch):
    emptied = _fake_torch(True, 4 * 1024**3, monkeypatch)
    det = GlinerDetector(model=FakeGliner())
    det.unload()
    assert det._model is None and emptied == [1]


class _Ent:
    def __init__(self, text, label_, s):
        self.text, self.label_, self.start_char, self.end_char = text, label_, s, s + len(text)


def test_spacy_mapping_drops_norp():
    text = "Fang Yuan met a Chinese monk in Kyoto."
    ents = [_Ent("Fang Yuan", "PERSON", 0), _Ent("Chinese", "NORP", 16), _Ent("Kyoto", "GPE", 32)]
    det = SpacyDetector(nlp=lambda t: SimpleNamespace(ents=ents))
    spans = det.detect(text)
    assert [(s.text, s.label, s.score) for s in spans] == [("Fang Yuan", "character", 0.7), ("Kyoto", "location", 0.7)]
    assert det.name == "spacy:en_core_web_sm"


def test_nametag_requires_tagger_and_maps_conll():
    with pytest.raises(ImportError):
        NameTagDetector()
    det = NameTagDetector(lambda t: [(0, 4, "PER"), (5, 9, "MISC")])
    assert [(s.text, s.label) for s in det.detect("Kimu Dokj")] == [("Kimu", "character")]


def test_locate_requires_word_boundary():
    text = "Ling Lingering. Will will go. Fang Yuan's blade; Ling-er; xLing."
    spans = _locate([NerEntity(text="Ling", label="character")], text, 0.8)
    assert [s.start for s in spans] == [0, text.index("Ling-er")]
    assert all(text[s.start : s.end] == "Ling" for s in spans)
    names = _locate([NerEntity(text="Fang Yuan", label="character")], text, 0.8)
    assert len(names) == 1
