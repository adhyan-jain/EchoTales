"""Real-data bugs found by the hybrid check (NER_ROMANIZED.md "Real-data check") and the `fast` detector. Fakes only."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from echotales.core.enums import AliasType, BlockType
from echotales.core.models import Block, Chapter
from echotales.core.store import Store
from echotales.pipeline.config import LLMMode, ModelBackend, Settings
from echotales.pipeline.ingest.normalize import strip_name_tail
from echotales.pipeline.mentions import hybrid as hybrid_mod
from echotales.pipeline.mentions.commonness import build_profile
from echotales.pipeline.mentions.gazetteer import Gazetteer
from echotales.pipeline.mentions.hybrid import (
    FAST_GLINER_THRESHOLD,
    HybridDetector,
    build_hybrid_detector,
)
from echotales.pipeline.mentions.runner import detect_mentions, resolve_detector_mode
from test_hybrid_detector import FakeVoter, _client, _store


def _det(hits: dict[str, tuple[str, float]], **kw) -> HybridDetector:
    return HybridDetector(gliner=FakeVoter("gliner", hits, []), fast=True, **kw)


class TestNameTails:
    @pytest.mark.parametrize(
        ("raw", "clean"),
        [
            ("Fang Zhi’s", "Fang Zhi"),  # curly: the RI defect
            ("Fang Zhi's", "Fang Zhi"),
            ("Yoo Sangah-ssi²", "Yoo Sangah-ssi"),  # ORV superscript footnote
            ("Reader-nim³", "Reader-nim"),
            ("Dokja1", "Dokja"),  # plain digits glued to a capitalised word
            ("Kim Dokja’s¹", "Kim Dokja"),
            ("tls123", "tls123"),  # a username is not a footnote
            ("Rank 5", "Rank 5"),  # digits not glued to the word
            ("Fang Yuan", "Fang Yuan"),
        ],
    )
    def test_strip_name_tail(self, raw: str, clean: str) -> None:
        assert strip_name_tail(raw) == clean

    def test_detector_span_loses_the_possessive_and_keeps_its_offsets(self) -> None:
        text = "She loved Fang Zhi’s sword."
        det = _det({"Fang Zhi’s": ("character", 0.9)})
        (span,) = det.detect(text)
        assert (span.text, text[span.start:span.end]) == ("Fang Zhi", "Fang Zhi")

    def test_detector_span_loses_the_footnote_marker(self) -> None:
        text = "“I’m Dokja¹,” he said."
        (span,) = _det({"Dokja¹": ("character", 0.9)}).detect(text)
        assert span.text == "Dokja" and text[span.start:span.end] == "Dokja"

    def test_gazetteer_still_finds_a_name_followed_by_a_footnote_marker(self) -> None:
        # Otherwise the trimmed surface would lose the very mention it came from: "²" is isalnum().
        gaz = Gazetteer()
        gaz.add("Dokja", AliasType.RIGID_NAME)
        assert [h.surface for h in gaz.find("I'm Dokja¹. Dokja2 left. Dokjas stayed.")] == ["Dokja", "Dokja"]


class TestPluralClass:
    CORPUS = (
        "In particular was a group of wild beasts called Predicament. How could he fight the Predicaments? "
        + "He killed many Predicaments. " * 6
        + "Ren Zu said hello. " * 30
    )

    def test_plural_of_a_seen_singular_is_a_class_whatever_its_label(self) -> None:
        profile = build_profile(self.CORPUS, [])
        assert profile.is_plural_class("Predicaments") and profile.is_plural_class("Predicament")

    def test_a_name_that_rarely_pluralises_is_not(self) -> None:
        corpus = "Bennet spoke. " * 60 + "The Bennets left."
        assert not build_profile(corpus, []).is_plural_class("Bennets")
        assert not build_profile(corpus, []).is_plural_class("Bennet")

    def test_a_name_ending_in_s_with_no_singular_in_the_text_is_not(self) -> None:
        corpus = "James spoke. " * 40
        assert not build_profile(corpus, []).is_plural_class("James")

    def test_predicaments_never_reaches_the_graph(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        text = self.CORPUS + " Ren Zu met Fang Yuan."
        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(Chapter(
            novel_id="t", number=1, title="T", source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)],
        ))
        store.conn.commit()
        det = _det({"Predicaments": ("organization", 0.8), "Predicament": ("organization", 0.8),
                    "Fang Yuan": ("character", 0.9)})
        detect_mentions("t", store, detector=det, settings=Settings(lexicon_path=tmp_path), use_commonness_filter=True)
        assert {m.text for m in store.get_mentions("t")} == {"Fang Yuan"}


class TestFastRouting:
    TEXT = "Fang Yuan met Will near the gate. Lin watched them go."

    def routes(self, det: HybridDetector):
        return {r.candidate.surface: r for r in det.detect_candidates(self.TEXT)}

    def test_one_gliner_vote_at_the_threshold_accepts_with_no_second_source_or_classifier(self) -> None:
        r = self.routes(_det({"Fang Yuan": ("character", FAST_GLINER_THRESHOLD)}))["Fang Yuan"]
        assert (r.accepted, r.route) == (True, "accept")

    def test_below_the_threshold_rejects(self) -> None:
        assert not self.routes(_det({"Lin": ("character", 0.39)}))["Lin"].accepted

    def test_confirmed_alias_accepts_without_a_vote(self) -> None:
        det = HybridDetector(gliner=FakeVoter("gliner", {}, []), known_aliases=["Lin"], fast=True)
        assert self.routes(det)["Lin"].accepted

    def test_a_seed_alone_is_not_enough(self) -> None:
        det = HybridDetector(gliner=FakeVoter("gliner", {}, []), seed_names=["Lin"], fast=True)
        assert not self.routes(det)["Lin"].accepted

    def test_wordlike_surface_is_accepted_per_occurrence_and_never_promoted(self) -> None:
        det = _det({"Will": ("character", 0.9), "Fang Yuan": ("character", 0.9)})
        by = {s.text: s for s in det.detect(self.TEXT)}
        assert by["Will"].positional and not by["Fang Yuan"].positional
        assert by["Will"].provenance.detector == "fast"
        assert not det.may_promote("Will", by["Will"].provenance.evidence_json)
        assert det.may_promote("Fang Yuan", by["Fang Yuan"].provenance.evidence_json)

    def test_fast_has_no_spacy_and_no_classifier(self) -> None:
        det = _det({"Fang Yuan": ("character", 0.9)})
        assert det.spacy is None and det.classifier is None and det.name.startswith("fast(")


class TestBuildAndDefault:
    def test_fast_builds_gliner_at_the_measured_threshold_without_spacy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict = {}
        monkeypatch.setattr(hybrid_mod, "_importable", lambda _m: True)
        monkeypatch.setattr(hybrid_mod, "_spacy_ready", lambda _m: pytest.fail("fast must not look for spaCy"))
        monkeypatch.setattr(hybrid_mod, "GlinerDetector", lambda model_id, threshold=0.5, **_k: seen.update(m=model_id, t=threshold) or object())
        det = build_hybrid_detector(
            Settings(llm_mode=LLMMode.LOCAL, mentions_gliner_model="/p/gliner"), client=None, fast=True
        )
        assert det is not None and det.fast and det.spacy is None
        assert seen == {"m": "/p/gliner", "t": FAST_GLINER_THRESHOLD}

    def test_fast_in_stub_mode_never_loads_a_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(hybrid_mod, "GlinerDetector", lambda *a, **k: pytest.fail("constructed"))
        assert build_hybrid_detector(Settings(llm_mode=LLMMode.STUB), client=None, fast=True) is None

    def test_missing_gliner_falls_back_with_a_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(hybrid_mod, "_importable", lambda _m: False)
        with caplog.at_level(logging.WARNING):
            assert build_hybrid_detector(Settings(llm_mode=LLMMode.LOCAL), client=None, fast=True) is None
        assert "mentions.detector=fast" in caplog.text

    @pytest.mark.parametrize(
        ("compute", "expected"), [("local-low", "fast"), ("local-high", "hybrid"), ("cloud", "hybrid")]
    )
    def test_absent_config_follows_compute(self, compute: str, expected: str) -> None:
        cfg = Settings(llm_mode=LLMMode.LOCAL, compute=compute)
        client = SimpleNamespace(backend=ModelBackend.OLLAMA)
        assert resolve_detector_mode(cfg, client) == expected

    def test_stub_runs_stay_on_the_legacy_path(self) -> None:
        local = Settings(llm_mode=LLMMode.LOCAL)
        assert resolve_detector_mode(Settings(llm_mode=LLMMode.STUB), SimpleNamespace(backend=ModelBackend.OLLAMA)) == "llm"
        assert resolve_detector_mode(local, SimpleNamespace(backend=ModelBackend.STUB)) == "llm"
        assert resolve_detector_mode(local, None) == "llm"

    def test_explicit_config_always_wins(self) -> None:
        client = SimpleNamespace(backend=ModelBackend.OLLAMA)
        for explicit in ("llm", "hybrid", "fast", "heuristic"):
            cfg = Settings(llm_mode=LLMMode.LOCAL, compute="local-low", mentions_detector=explicit)
            assert resolve_detector_mode(cfg, client) == explicit
        assert resolve_detector_mode(Settings(mentions_detector="hybrid"), None) == "hybrid"

    def test_unknown_value_is_loud(self) -> None:
        with pytest.raises(ValueError, match=r"mentions\.detector"):
            resolve_detector_mode(Settings(mentions_detector="gliner"), None)

    def test_ner_flag_overrides_config_for_the_run_only(self) -> None:
        from echotales.pipeline.cli import build_parser

        args = build_parser().parse_args(["run", "--novel", "x", "--ner", "fast"])
        assert args.ner == "fast"
        assert build_parser().parse_args(["run", "--novel", "x"]).ner is None

    def test_absent_config_runs_fast_through_the_runner_with_no_llm_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[str] = []
        monkeypatch.setattr(hybrid_mod, "_importable", lambda _m: True)
        monkeypatch.setattr(
            hybrid_mod, "GlinerDetector",
            lambda *_a, **_k: FakeVoter("gliner", {"Fang Yuan": ("character", 0.5), "Lin": ("character", 0.45)}, events),
        )
        store = _store()
        report = detect_mentions(
            "t", store, client=_client(events),
            settings=Settings(lexicon_path=tmp_path, llm_mode=LLMMode.LOCAL, compute="local-low"),
            use_commonness_filter=False,
        )
        got = {m.text: m for m in store.get_mentions("t")}
        assert set(got) == {"Fang Yuan", "Lin"} and {m.detector for m in got.values()} == {"fast"}
        assert events == ["gliner.detect", "gliner.unload"], "fast must not touch the LLM"
        assert report.detector_name.startswith("fast(")
