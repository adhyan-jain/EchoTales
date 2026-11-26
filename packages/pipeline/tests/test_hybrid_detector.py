"""Hybrid mention detector (D69): routing, pass order, provenance to Mention, and the default-off wiring. Fakes only."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter
from echotales.core.store import Store
from echotales.pipeline import config as config_mod
from echotales.pipeline.config import LLMMode, ModelBackend, Settings
from echotales.pipeline.llm.tasks import Task, profile_for
from echotales.pipeline.mentions import hybrid as hybrid_mod
from echotales.pipeline.mentions.chapter_ner import (
    NameCache,
    VocabularyDetector,
    extract_chapter_names,
)
from echotales.pipeline.mentions.hybrid import HybridDetector, build_hybrid_detector
from echotales.pipeline.mentions.ner import NerEntity, NerResponse, NerSpan
from echotales.pipeline.mentions.ner_classify import (
    BATCH,
    ClassifyCache,
    ClassifyItem,
    LlmNameClassifier,
    NerClassifyResponse,
    Verdict,
    sentence_around,
)
from echotales.pipeline.mentions.runner import detect_mentions

TEXT = "Fang Yuan met Will near the gate. Lin watched them go."


class FakeVoter:
    """GLiNER- or spaCy-like: reports `{surface: (label, score)}` wherever it occurs, and logs its calls."""

    def __init__(self, name: str, hits: dict[str, tuple[str, float]], log: list[str]) -> None:
        self.name = name
        self.model_id = f"{name}-model"
        self.model_name = f"{name}-model"
        self.model_version = f"{name}-v1"
        self.hits = hits
        self.log = log

    def detect(self, text: str) -> list[NerSpan]:
        self.log.append(f"{self.name}.detect")
        out = []
        for surface, (label, score) in self.hits.items():
            i = text.find(surface)
            while i >= 0:
                out.append(NerSpan(surface, i, i + len(surface), label, score))
                i = text.find(surface, i + 1)
        return sorted(out, key=lambda s: s.start)

    def unload(self) -> None:
        self.log.append(f"{self.name}.unload")


def detector(gliner=None, spacy=None, log=None, **kw) -> HybridDetector:
    log = log if log is not None else []
    return HybridDetector(
        gliner=FakeVoter("gliner", gliner, log) if gliner is not None else None,
        spacy=FakeVoter("spacy", spacy, log) if spacy is not None else None,
        **kw,
    )


def route_of(det: HybridDetector, surface: str, text: str = TEXT):
    return {r.candidate.surface: r for r in det.detect_candidates(text)}[surface]


class TestRouting:
    def test_confirmed_gazetteer_alias_accepts_with_no_model_vote(self) -> None:
        r = route_of(detector(known_aliases=["Fang Yuan"]), "Fang Yuan")
        assert (r.accepted, r.route) == (True, "accept")

    def test_roster_names_count_as_confirmed_aliases(self) -> None:
        det = detector()
        spans = det.detect_with_context(TEXT, ["Lin"])
        assert [s.text for s in spans] == ["Lin"]

    def test_high_gliner_score_accepts(self) -> None:
        r = route_of(detector(gliner={"Fang Yuan": ("character", 0.9)}), "Fang Yuan")
        assert r.accepted and r.route == "accept" and r.label == "character"

    def test_two_independent_sources_agreeing_accept_below_tau_high(self) -> None:
        det = detector(gliner={"Lin": ("character", 0.5)}, spacy={"Lin": ("character", 0.7)})
        r = route_of(det, "Lin")
        assert r.accepted and r.route == "accept" and "agree" in r.evidence

    def test_single_low_score_rejects(self) -> None:
        r = route_of(detector(gliner={"Lin": ("character", 0.2)}), "Lin")
        assert (r.accepted, r.route) == (False, "reject")

    def test_single_mid_score_goes_to_the_classifier(self) -> None:
        assert route_of(detector(gliner={"Lin": ("character", 0.5)}), "Lin").route == "classifier"

    def test_label_disagreement_goes_to_the_classifier(self) -> None:
        det = detector(gliner={"Lin": ("character", 0.5)}, spacy={"Lin": ("location", 0.7)})
        r = route_of(det, "Lin")
        assert r.route == "classifier" and "disagree" in r.evidence

    def test_a_common_word_goes_to_the_classifier_even_at_a_high_score(self) -> None:
        # "Will" is on the gazetteer's ambiguity blocklist: it scores high as a name exactly when it is a word.
        assert route_of(detector(gliner={"Will": ("character", 0.95)}), "Will").route == "classifier"

    def test_injected_wordlike_predicate_is_honoured(self) -> None:
        det = detector(gliner={"Lin": ("character", 0.95)}, is_wordlike=lambda s: s == "Lin")
        assert route_of(det, "Lin").route == "classifier"

    def test_gazetteer_alias_beats_the_wordlike_demotion(self) -> None:
        # (The gazetteer itself refuses a blocklisted word as an alias, so the predicate stands in for one.)
        det = detector(gliner={"Lin": ("character", 0.95)}, known_aliases=["Lin"], is_wordlike=lambda _s: True)
        assert route_of(det, "Lin").route == "accept"

    def test_classifier_decides_the_mid_candidates(self) -> None:
        def classifier(text, cands, *, chapter=None):
            return [Verdict(c.surface == "Lin", "location", "because") for c in cands]

        det = detector(gliner={"Lin": ("character", 0.5), "Will": ("character", 0.9)}, classifier=classifier)
        got = {r.candidate.surface: r for r in det.detect_candidates(TEXT)}
        assert got["Lin"].accepted and got["Lin"].label == "location" and "because" in got["Lin"].evidence
        assert not got["Will"].accepted and got["Will"].route == "classifier"

    def test_no_classifier_rejects_the_classifier_route(self) -> None:
        r = route_of(detector(gliner={"Lin": ("character", 0.5)}), "Lin")
        assert not r.accepted and r.route == "classifier" and "no classifier" in r.evidence
        assert detector(gliner={"Lin": ("character", 0.5)}).detect(TEXT) == []

    def test_a_failed_classifier_call_rejects(self) -> None:
        det = detector(gliner={"Lin": ("character", 0.5)}, classifier=lambda t, c, *, chapter=None: [None] * len(c))
        assert not route_of(det, "Lin").accepted

    def test_overlapping_spans_merge_keeping_every_vote(self) -> None:
        det = detector(
            gliner={"Fang Yuan": ("character", 0.9)},
            spacy={"Fang Yuan": ("character", 0.7), "Yuan met": ("character", 0.7)},
        )
        cands = det.candidates(TEXT)
        fang = next(c for c in cands if "Fang" in c.surface)
        assert fang.surface == "Fang Yuan"  # two votes beat one
        assert {v.source for v in fang.votes} == {"gliner", "spacy"} and len(fang.votes) == 3
        assert fang.search_key == "fangyuan"


class TestPassOrder:
    def test_gliner_is_unloaded_before_spacy_runs(self) -> None:
        log: list[str] = []
        det = detector(gliner={"Lin": ("character", 0.9)}, spacy={"Lin": ("character", 0.7)}, log=log)
        det.precompute([TEXT, "Lin again."])
        assert log == ["gliner.detect", "gliner.detect", "gliner.unload", "spacy.detect", "spacy.detect"]

    def test_precomputed_text_is_not_rerun(self) -> None:
        log: list[str] = []
        det = detector(gliner={"Lin": ("character", 0.9)}, log=log)
        det.precompute([TEXT])
        det.detect(TEXT)
        assert log == ["gliner.detect", "gliner.unload"]


class TestClassifier:
    def test_sentence_around_picks_the_candidates_sentence(self) -> None:
        i = TEXT.index("Lin")
        assert sentence_around(TEXT, i, i + 3) == "Lin watched them go."

    def test_long_runon_is_windowed_around_the_candidate(self) -> None:
        text = "word " * 200 + "Lin " + "word " * 200
        i = text.index("Lin")
        assert "Lin" in sentence_around(text, i, i + 3, max_chars=100)

    def _client(self, calls: list[int]):
        def complete(task, prompt, schema, **kw):
            assert task is Task.NER_CLASSIFY
            n = prompt.count("candidate:")
            calls.append(n)
            items = [ClassifyItem(id=i, is_name=True, label="Location", reason="r") for i in range(n)]
            return SimpleNamespace(value=NerClassifyResponse(items=items))

        return SimpleNamespace(complete=complete)

    def test_batches_of_forty_and_caching(self, tmp_path: Path) -> None:
        text = " ".join(f"Name{i} walked." for i in range(BATCH + 5))
        det = HybridDetector()
        cands = [
            det.candidates(text)  # none: no voters
        ]
        assert cands == [[]]
        from echotales.pipeline.mentions.candidate import NameCandidate, Vote

        cs = []
        for i in range(BATCH + 5):
            s = text.index(f"Name{i} ")
            cs.append(NameCandidate.build(f"Name{i}", s, s + len(f"Name{i}"), (Vote("gliner", "character", 0.5),)))
        calls: list[int] = []
        cache = ClassifyCache(tmp_path / "c.json", model="m")
        clf = LlmNameClassifier(self._client(calls), cache=cache)
        verdicts = clf(text, cs)
        assert calls == [BATCH, 5] and all(v and v.is_name and v.label == "location" for v in verdicts)
        clf(text, cs)  # all cached now
        assert calls == [BATCH, 5]
        cache.flush()
        assert json.loads((tmp_path / "c.json").read_text())

    def test_failed_call_gives_none_verdicts(self) -> None:
        def boom(*a, **k):
            raise RuntimeError("down")

        from echotales.pipeline.mentions.candidate import NameCandidate, Vote

        c = NameCandidate.build("Lin", 0, 3, (Vote("gliner", "character", 0.5),))
        assert LlmNameClassifier(SimpleNamespace(complete=boom))("Lin x", [c]) == [None]

    def test_ner_classify_is_routed_like_ner(self) -> None:
        a, b = profile_for(Task.NER), profile_for(Task.NER_CLASSIFY)
        assert (a.ollama_model, a.anthropic_model, a.temperature) == (b.ollama_model, b.anthropic_model, b.temperature)


# --------------------------------------------------------------------------------------------------------------------
# Through the runner: provenance on Mention rows, and the default-off wiring.
# --------------------------------------------------------------------------------------------------------------------

CHAPTER_TEXT = "Fang Yuan stepped forward. Wu An followed him. Lin watched from the gate."


def _store() -> Store:
    s = Store(":memory:")
    s.add_novel("t", "T", "x.epub", "generic")
    s.add_chapter(Chapter(
        novel_id="t", number=1, title="T", source_href="a.html",
        blocks=[Block(index=0, block_type=BlockType.PROSE, text=CHAPTER_TEXT)],
    ))
    s.conn.commit()
    return s


def _settings(tmp_path: Path, **kw) -> Settings:
    return Settings(lexicon_path=tmp_path, **kw)


def _client(events: list[str], *, ner_entities: list[NerEntity] | None = None):
    def complete(task, prompt, schema, **kw):
        events.append(f"complete:{task.value}")
        if task is Task.NER_CLASSIFY:
            return SimpleNamespace(value=NerClassifyResponse(items=[ClassifyItem(id=0, is_name=True, reason="subject")]))
        return SimpleNamespace(value=NerResponse(entities=ner_entities or [], confidence=0.8))

    return SimpleNamespace(backend=ModelBackend.OLLAMA, model_for=lambda _t: "fake-model", complete=complete)


@pytest.fixture
def patched_models(monkeypatch: pytest.MonkeyPatch):
    events: list[str] = []
    monkeypatch.setattr(hybrid_mod, "_importable", lambda _m: True)
    monkeypatch.setattr(hybrid_mod, "_spacy_ready", lambda _m: True)
    monkeypatch.setattr(
        hybrid_mod, "GlinerDetector",
        lambda model_id, threshold=0.5, **_k: FakeVoter(
            "gliner", {"Fang Yuan": ("character", 0.9), "Wu An": ("character", 0.5), "Lin": ("character", 0.5)}, events
        ),
    )
    monkeypatch.setattr(
        hybrid_mod, "SpacyDetector", lambda _name="": FakeVoter("spacy", {"Wu An": ("character", 0.7)}, events)
    )
    return events


class TestRunnerWiring:
    def test_hybrid_provenance_reaches_the_mention_rows(self, tmp_path: Path, patched_models: list[str]) -> None:
        events = patched_models
        store = _store()
        report = detect_mentions(
            "t", store, client=_client(events),
            settings=_settings(tmp_path, llm_mode=LLMMode.LOCAL, mentions_detector="hybrid"),
            use_commonness_filter=False,
        )
        by_text = {m.text: m for m in store.get_mentions("t")}
        assert set(by_text) == {"Fang Yuan", "Wu An", "Lin"}
        fang, wu, lin = by_text["Fang Yuan"], by_text["Wu An"], by_text["Lin"]
        assert (fang.detector, fang.model_id, fang.model_version) == ("hybrid", "gliner-model", "gliner-v1")
        assert fang.ner_score == 0.9 and fang.end_offset == fang.offset + 9 and fang.search_key == "fangyuan"
        assert json.loads(fang.evidence_json)["votes"][0]["source"] == "gliner"
        assert "agree" in json.loads(wu.evidence_json)["evidence"]  # two sources, below tau_high
        assert json.loads(lin.evidence_json)["route"] == "classifier"  # mid score, the model said yes
        assert report.hybrid_routes == {"accept": 2, "classifier_accept": 1}
        # GLiNER and ollama never co-resident: its unload precedes the first model call.
        assert events.index("gliner.unload") < events.index("complete:ner_classify")

    def test_explicit_llm_is_the_legacy_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            hybrid_mod, "build_hybrid_detector", lambda *a, **k: pytest.fail("hybrid must not be built when llm is explicit")
        )
        monkeypatch.setattr("echotales.pipeline.mentions.runner.build_hybrid_detector", hybrid_mod.build_hybrid_detector)
        events: list[str] = []
        store = _store()
        detect_mentions(
            "t", store, client=_client(events, ner_entities=[NerEntity(text="Fang Yuan", label="character")]),
            settings=_settings(tmp_path, llm_mode=LLMMode.LOCAL, mentions_detector="llm"), use_commonness_filter=False,
        )
        (m,) = store.get_mentions("t")
        assert (m.detector, m.model_id, m.ner_score) == ("llm:fake-model", "fake-model", 0.85)
        assert m.end_offset == 9 and m.search_key == "fangyuan" and m.evidence_json is None
        assert events == ["complete:ner"]

    def test_legacy_without_a_client_records_the_heuristic(self, tmp_path: Path) -> None:
        store = _store()
        detect_mentions("t", store, settings=_settings(tmp_path), use_commonness_filter=False)
        assert {m.detector for m in store.get_mentions("t")} == {"heuristic"}

    def test_heuristic_mode_ignores_the_client(self, tmp_path: Path) -> None:
        events: list[str] = []
        store = _store()
        detect_mentions(
            "t", store, client=_client(events),
            settings=_settings(tmp_path, llm_mode=LLMMode.LOCAL, mentions_detector="heuristic"),
            use_commonness_filter=False,
        )
        assert events == [] and {m.detector for m in store.get_mentions("t")} == {"heuristic"}

    def test_stub_mode_never_constructs_gliner(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def explode(*a, **k):
            raise AssertionError("GLiNER constructed in stub mode")

        monkeypatch.setattr(hybrid_mod, "GlinerDetector", explode)
        monkeypatch.setattr(hybrid_mod, "_importable", lambda _m: True)
        store = _store()
        detect_mentions(
            "t", store, settings=_settings(tmp_path, llm_mode=LLMMode.STUB, mentions_detector="hybrid"),
            use_commonness_filter=False,
        )
        assert {m.detector for m in store.get_mentions("t")} == {"heuristic"}

    def test_stub_backend_client_never_constructs_gliner(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(hybrid_mod, "GlinerDetector", lambda *a, **k: pytest.fail("constructed"))
        stub_client = SimpleNamespace(backend=ModelBackend.STUB)
        assert build_hybrid_detector(
            _settings(tmp_path, llm_mode=LLMMode.LOCAL, mentions_detector="hybrid"), client=stub_client
        ) is None

    def test_missing_gliner_falls_back_with_a_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(hybrid_mod, "_importable", lambda _m: False)
        monkeypatch.setattr(hybrid_mod, "GlinerDetector", lambda *a, **k: pytest.fail("constructed"))
        with caplog.at_level("WARNING"):
            assert build_hybrid_detector(_settings(tmp_path, llm_mode=LLMMode.LOCAL), client=None) is None
        assert "gliner is not importable" in caplog.text

    def test_unknown_detector_value_is_loud(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match=r"mentions\.detector"):
            detect_mentions("t", _store(), settings=_settings(tmp_path, mentions_detector="gliner"))

    def test_defaults_and_config_json_keys(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        defaults = Settings()
        assert (defaults.mentions_detector, defaults.mentions_tau_high, defaults.mentions_tau_low) == ("", 0.7, 0.3)
        assert defaults.mentions_gliner_model == "urchade/gliner_medium-v2.1"
        assert defaults.mentions_classifier_model == "qwen3:8b"
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"mentions": {"detector": "hybrid", "gliner_model": "/p/gliner", "classifier_model": "c:1b", "tau_high": 0.8}}))
        monkeypatch.setattr(config_mod, "_CONFIG_JSON", cfg)
        loaded = config_mod._load_config_json()
        assert loaded == {"mentions_detector": "hybrid", "mentions_gliner_model": "/p/gliner", "mentions_classifier_model": "c:1b",
                          "mentions_tau_high": 0.8}
        cfg.write_text("{}")
        assert config_mod._load_config_json() == {}


class TestClassifierModelRouting:
    """`mentions.classifier_model` moves only Task.NER_CLASSIFY on the ollama backend (D69: qwen3:8b beat qwen2.5:7b)."""

    def test_classify_follows_the_setting_and_ner_keeps_its_profile(self) -> None:
        from echotales.pipeline.config import ModelBackend
        from echotales.pipeline.llm.client import ModelClient

        client = ModelClient(settings=Settings(model_backend=ModelBackend.OLLAMA, mentions_classifier_model="qwen3:8b"))
        assert client.model_for(Task.NER_CLASSIFY) == "qwen3:8b"
        assert client.model_for(Task.NER) == profile_for(Task.NER).ollama_model
        blank = ModelClient(settings=Settings(model_backend=ModelBackend.OLLAMA, mentions_classifier_model=""))
        assert blank.model_for(Task.NER_CLASSIFY) == profile_for(Task.NER_CLASSIFY).ollama_model

    def test_qwen3_8b_passes_the_size_policy_by_its_tag(self) -> None:
        from echotales.pipeline.engines.registry import check_llm_model

        check_llm_model("qwen3:8b", provider="ollama")


class TestPerOccurrenceAcceptance:
    """A common-word surface is accepted where the classifier saw it, never propagated by vocabulary matching."""

    WILL = "Lark Han said hello. Lark it hold?"

    @pytest.fixture(autouse=True)
    def _lark_is_a_common_word(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # "Will" itself is on the gazetteer's ambiguity blocklist and can never be a vocabulary or gazetteer entry
        # (so it is already per-occurrence); "Lark" is a common word the blocklist does not cover.
        monkeypatch.setattr(hybrid_mod, "_is_common_word", lambda surface: surface.casefold() == "lark")

    @staticmethod
    def _accept_only_first(text, cands, *, chapter=None):
        return [Verdict(c.start == 0, "character", "first only") for c in cands]

    def _vocab(self, det: HybridDetector, text: str, known: list[str] | None = None) -> VocabularyDetector:
        names = extract_chapter_names(det, text, known_names=known or [], chapter=1)
        return VocabularyDetector(
            names.surfaces, provenance=names.provenance, scores=names.scores, occurrences=names.occurrences
        )

    def test_wordlike_acceptance_is_not_propagated_to_other_positions(self) -> None:
        det = detector(gliner={"Lark": ("character", 0.9)}, classifier=self._accept_only_first)
        spans = self._vocab(det, self.WILL).detect(self.WILL)
        assert [(s.text, s.start) for s in spans] == [("Lark", 0)]

    def test_non_wordlike_name_still_matches_at_its_other_occurrences(self) -> None:
        text = "Fang Yuan said hello. Then Fang Yuan left."
        det = detector(gliner={"Fang Yuan": ("character", 0.9)}, classifier=self._accept_only_first)
        spans = self._vocab(det, text).detect(text)
        assert [s.start for s in spans] == [0, text.rindex("Fang Yuan")]

    def test_occurrence_still_matches_when_the_span_clips_its_context(self) -> None:
        det = detector(gliner={"Lark": ("character", 0.9)}, classifier=self._accept_only_first)
        vocab = self._vocab(det, self.WILL)
        assert [s.start for s in vocab.detect("Lark Han said")] == [0]

    def test_classifier_only_wordlike_is_not_promotable_but_gazetteer_and_names_are(self) -> None:
        det = detector(gliner={"Lark": ("character", 0.9), "Fang Yuan": ("character", 0.9)},
                       classifier=self._accept_only_first)
        text = "Lark Han met Fang Yuan."
        by = {s.text: s for s in det.detect_with_context(text, [])}
        assert not det.may_promote("Lark", by["Lark"].provenance.evidence_json)
        assert det.may_promote("Fang Yuan", by["Fang Yuan"].provenance.evidence_json)
        confirmed = {s.text: s for s in det.detect_with_context(text, ["Lark"])}
        assert det.may_promote("Lark", confirmed["Lark"].provenance.evidence_json)

    def test_classifier_only_wordlike_is_not_fed_back_as_a_confirmed_alias(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def complete(task, prompt, schema, **kw):
            if task is Task.NER_CLASSIFY:
                n = prompt.count("candidate:")
                # Only "Lark Han ..." is a name.
                items = [ClassifyItem(id=i, is_name="Lark Han" in prompt.split("\n\n", 1)[1].splitlines()[i], reason="r")
                         for i in range(n)]
                return SimpleNamespace(value=NerClassifyResponse(items=items))
            return SimpleNamespace(value=NerResponse(entities=[], confidence=0.8))

        client = SimpleNamespace(backend=ModelBackend.OLLAMA, model_for=lambda _t: "fake-model", complete=complete)
        monkeypatch.setattr(hybrid_mod, "_importable", lambda _m: True)
        monkeypatch.setattr(hybrid_mod, "_spacy_ready", lambda _m: False)
        monkeypatch.setattr(
            hybrid_mod, "GlinerDetector",
            lambda *_a, **_k: FakeVoter("gliner", {"Lark": ("character", 0.9)}, []),
        )
        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        for n, text in ((1, "Lark Han said hello."), (2, "Lark it hold?")):
            store.add_chapter(Chapter(
                novel_id="t", number=n, title="T", source_href=f"{n}.html",
                blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)],
            ))
        store.conn.commit()
        detect_mentions(
            "t", store, client=client,
            settings=_settings(tmp_path, llm_mode=LLMMode.LOCAL, mentions_detector="hybrid"),
            use_commonness_filter=False,
        )
        got = [(int(m.chapter), m.text) for m in store.get_mentions("t")]
        assert (1, "Lark") in got
        assert (2, "Lark") not in got, "chapter 1's classifier-only 'Lark' must not become a gazetteer voter"


def test_name_cache_is_not_used_for_classifier_keys(tmp_path: Path) -> None:
    """The classify cache must not collide with the NER one even for identical key text."""
    a = NameCache(tmp_path / "a.json", model="m")
    b = ClassifyCache(tmp_path / "b.json", model="m")
    assert a._key("x") != b._key("x")
