"""Layer-1 LLM name discovery: filtering, chunking, caching, matching."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from echotales.pipeline.ingest.normalize import display_label, name_containment
from echotales.pipeline.mentions import ner
from echotales.pipeline.mentions.chapter_ner import (
    NameCache,
    VocabularyDetector,
    chunk_text,
    extract_chapter_names,
    plausible_name,
)
from echotales.pipeline.mentions.ner import (
    DEFAULT_LABELS,
    NER_WINDOW_CHARS,
    NER_WINDOW_OVERLAP,
    MentionDetector,
    NerEntity,
    NerSpan,
    QwenNerDetector,
    _outranks,
    _windows,
)


class FakeDetector(MentionDetector):
    """Returns a scripted set of surfaces, and counts how often it is asked."""

    def __init__(self, returns: list[tuple[str, str]]) -> None:
        self.returns = returns
        self.calls = 0

    def detect(self, text: str) -> list[NerSpan]:
        return self.detect_with_context(text, [])

    def detect_with_context(
        self, text: str, known_names: list[str], *, chapter: float | None = None
    ) -> list[NerSpan]:
        self.calls += 1
        return [NerSpan(t, 0, len(t), label) for t, label in self.returns]


class TestPlausibleName:
    @pytest.mark.parametrize(
        "surface",
        [
            "Fang Yuan",
            "Spring Autumn Cicada",
            "Gu Yue Mo Bei",
        ],
    )
    def test_accepts_real_names(self, surface: str) -> None:
        assert plausible_name(surface)

    def test_rejects_a_copied_sentence(self) -> None:
        """The actual chapter-1 failure: the model returned a whole clause."""
        assert not plausible_name(
            "300 years ago you insulted me, took away my body's purity"
        )

    @pytest.mark.parametrize(
        "surface",
        [
            "major factions of justice",  # lowercase: a paraphrased description
            "a",  # too short
            "Fang Yuan, the demon",  # punctuation-bearing fragment
            "1234",  # no letters
        ],
    )
    def test_rejects_model_noise(self, surface: str) -> None:
        assert not plausible_name(surface)


class TestChunking:
    def test_short_text_is_one_chunk(self) -> None:
        assert chunk_text("a paragraph", size=100) == ["a paragraph"]

    def test_splits_on_paragraph_boundaries(self) -> None:
        text = "\n".join(f"paragraph {i} " + "x" * 40 for i in range(10))
        chunks = chunk_text(text, size=120)
        assert len(chunks) > 1
        # Nothing is lost and nothing is cut mid-line.
        assert "\n".join(chunks).replace("\n", "") == text.replace("\n", "")


class TestExtraction:
    def test_keeps_names_and_drops_noise(self) -> None:
        detector = FakeDetector(
            [
                ("Fang Yuan", "character"),
                ("Qing Mao Mountain", "location"),
                ("major factions of justice", "character"),
                ("Fang Yuan", "weapon"),  # invented label
            ]
        )
        names = extract_chapter_names(detector, "text", known_names=[])
        assert names.surfaces == {
            "Fang Yuan": "character",
            "Qing Mao Mountain": "location",
        }
        assert names.rejected == 2

    def test_character_label_wins_over_location(self) -> None:
        """Clan names double as place names; losing the person is the worse error."""
        detector = FakeDetector([("Gu Yue", "location"), ("Gu Yue", "character")])
        names = extract_chapter_names(detector, "text", known_names=[])
        assert names.surfaces["Gu Yue"] == "character"

    def test_a_failing_call_does_not_kill_the_run(self) -> None:
        class Exploding(MentionDetector):
            def detect(self, text: str) -> list[NerSpan]:
                raise RuntimeError("ollama fell over")

            def detect_with_context(self, text, known_names, *, chapter=None):  # type: ignore[no-untyped-def]
                raise RuntimeError("ollama fell over")

        names = extract_chapter_names(Exploding(), "text", known_names=[])
        assert names.surfaces == {}


class TestNameCache:
    def test_round_trips_and_suppresses_the_call(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "cache.json"
        detector = FakeDetector([("Fang Yuan", "character")])

        cache = NameCache(path, model="qwen2.5:7b")
        first = extract_chapter_names(detector, "chapter text", known_names=[], cache=cache)
        cache.flush()
        assert detector.calls == 1
        assert not first.cached

        reloaded = NameCache(path, model="qwen2.5:7b")
        second = extract_chapter_names(detector, "chapter text", known_names=[], cache=reloaded)
        assert detector.calls == 1, "cache hit must not reach the model"
        assert second.cached
        assert second.surfaces == first.surfaces

    def test_a_different_model_invalidates(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "cache.json"
        detector = FakeDetector([("Fang Yuan", "character")])
        cache = NameCache(path, model="qwen2.5:7b")
        extract_chapter_names(detector, "text", known_names=[], cache=cache)
        cache.flush()

        other = NameCache(path, model="llama3:latest")
        extract_chapter_names(detector, "text", known_names=[], cache=other)
        assert detector.calls == 2

    def test_changed_chapter_text_invalidates(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "cache.json"
        detector = FakeDetector([("Fang Yuan", "character")])
        cache = NameCache(path, model="m")
        extract_chapter_names(detector, "original", known_names=[], cache=cache)
        extract_chapter_names(detector, "re-ingested", known_names=[], cache=cache)
        assert detector.calls == 2

    def test_a_changed_ner_pass_invalidates(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Without this the 2026-09-23 windowing fix is inert on any novel
        with a cache file: same text, same model, so the truncated vocabulary
        is replayed and the measurement run reports no change."""
        path = tmp_path / "cache.json"
        detector = FakeDetector([("Fang Yuan", "character")])
        cache = NameCache(path, model="qwen2.5:7b")
        extract_chapter_names(detector, "chapter text", known_names=[], cache=cache)
        cache.flush()

        monkeypatch.setattr(ner, "NER_WINDOW_CHARS", 3_000)
        reloaded = NameCache(path, model="qwen2.5:7b")
        result = extract_chapter_names(
            detector, "chapter text", known_names=[], cache=reloaded
        )
        assert detector.calls == 2
        assert not result.cached

    def test_the_fingerprint_is_stable_across_calls(self) -> None:
        assert ner.ner_pass_fingerprint() == ner.ner_pass_fingerprint()

    def test_corrupt_cache_file_is_survivable(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "cache.json"
        path.write_text("{not json")
        cache = NameCache(path, model="m")
        assert cache.get("anything") is None

    def test_flush_is_a_noop_when_unchanged(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "cache.json"
        NameCache(path, model="m").flush()
        assert not path.exists()

    def test_written_file_is_readable_json(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "nested" / "cache.json"
        cache = NameCache(path, model="m")
        cache.put("text", {"Fang Yuan": "character"})
        cache.flush()
        assert json.loads(path.read_text())


class TestVocabularyDetector:
    def test_finds_only_the_approved_vocabulary(self) -> None:
        detector = VocabularyDetector({"Fang Yuan": "character"})
        spans = detector.detect("Fang Yuan looked at the Mountain and at Fang Zheng.")
        assert [s.text for s in spans] == ["Fang Yuan"]

    def test_reports_exact_offsets(self) -> None:
        detector = VocabularyDetector({"Fang Yuan": "character"})
        text = "Then Fang Yuan spoke."
        span = detector.detect(text)[0]
        assert text[span.start : span.end] == "Fang Yuan"

    def test_every_occurrence_is_emitted(self) -> None:
        """Collapsing repeats would understate prominence and lose co-presence."""
        detector = VocabularyDetector({"Fang Yuan": "character"})
        assert len(detector.detect("Fang Yuan and Fang Yuan again")) == 2

    def test_does_not_match_inside_a_longer_word(self) -> None:
        detector = VocabularyDetector({"Mo": "character"})
        assert detector.detect("Moonlight shone.") == []


class TestNameContainment:
    def test_dropped_house_prefix_is_strong_evidence(self) -> None:
        assert name_containment("Mo Bei", "Gu Yue Mo Bei") > 0.86

    def test_the_house_name_itself_does_not_match_its_members(self) -> None:
        """A prefix, not a suffix — otherwise "Gu Yue" merges the whole clan."""
        assert name_containment("Gu Yue", "Gu Yue Mo Bei") == 0.0

    def test_a_shared_surname_is_not_evidence(self) -> None:
        """HANDOFF Section 4.5: a bare surname identifies a family, not a person."""
        assert name_containment("Elder Wang", "Xiao Wang") == 0.0
        assert name_containment("Wang", "Elder Wang") == 0.0

    def test_siblings_of_one_house_stay_distinct(self) -> None:
        assert name_containment("Gu Yue Mo Bei", "Gu Yue Mo Chen") == 0.0

    def test_unrelated_names_score_zero(self) -> None:
        assert name_containment("Fang Yuan", "Fang Zheng") == 0.0

    def test_single_token_needs_ambiguity_data_by_default(self) -> None:
        """Section 4.15's ORV gap: without a caller-supplied ambiguity table, a
        1-token shared suffix ("Dokja" in "Kim Dokja") stays the old,
        strictly-2-token-or-nothing behaviour."""
        assert name_containment("Dokja", "Kim Dokja") == 0.0

    def test_single_token_matches_when_not_a_known_ambiguous_component(self) -> None:
        """"Dokja" appears in only one entity's aliases in this corpus, so
        it's treated as a dropped given name, not a bare surname."""
        out = name_containment("Dokja", "Kim Dokja", ambiguous_tokens=frozenset())
        assert out >= 0.86

    def test_single_token_still_blocked_when_it_is_a_known_surname(self) -> None:
        """"Wang" recurs across other entities in this corpus -- Section 4.5 still
        applies even with an ambiguity table supplied."""
        out = name_containment("Wang", "Elder Wang", ambiguous_tokens=frozenset({"wang"}))
        assert out == 0.0


class TestDisplayLabel:
    def test_possessive_never_becomes_the_label(self) -> None:
        """HANDOFF Section 4.9 item 1 — the longest raw surface is the possessive."""
        assert display_label(["Fang Yuan", "Fang Yuan's"]) == "Fang Yuan"

    def test_leading_article_is_dropped(self) -> None:
        assert (
            display_label(["the Spring Autumn Cicada", "Spring Autumn Cicada"])
            == "Spring Autumn Cicada"
        )

    def test_honorifics_are_kept(self) -> None:
        """Unlike inflection, a title carries information a reviewer wants."""
        assert display_label(["Wang", "Elder Wang"]) == "Elder Wang"

    def test_empty_input(self) -> None:
        assert display_label([]) == ""


class RecordingClient:
    """Stands in for `ModelClient`, recording every passage it was sent.

    Returns whichever entities the scripted map says are visible in the
    passage it actually received — so a window the detector never sent is a
    window whose entities never come back, which is exactly the failure this
    class exists to detect.
    """

    def __init__(self, visible: dict[str, str], *, confidence: float = 0.8) -> None:
        self.visible = visible
        self.confidence = confidence
        self.passages: list[str] = []

    def complete(self, task, prompt, schema, **kwargs):  # type: ignore[no-untyped-def]
        passage = prompt.split("Passage:\n", 1)[1].rsplit("\n\n", 2)[0]
        self.passages.append(passage)
        value = schema(
            entities=[
                {"text": surface, "label": label}
                for surface, label in self.visible.items()
                if surface in passage
            ],
            confidence=self.confidence,
        )
        return SimpleNamespace(value=value)


class TestNerWindows:
    def test_short_text_is_one_window(self) -> None:
        assert _windows("a chapter", size=100, overlap=10) == ["a chapter"]

    def test_empty_text_produces_no_call(self) -> None:
        assert _windows("") == []

    def test_windows_cover_every_character(self) -> None:
        """The property the old `text[:6000]` violated: no offset is invisible."""
        text = "".join(chr(ord("a") + i % 26) for i in range(20_000))
        windows = _windows(text)
        stride = NER_WINDOW_CHARS - NER_WINDOW_OVERLAP
        assert all(len(w) <= NER_WINDOW_CHARS for w in windows)
        for offset in range(len(text)):
            assert any(
                i * stride <= offset < i * stride + len(w)
                for i, w in enumerate(windows)
            ), offset

    def test_consecutive_windows_overlap(self) -> None:
        text = "x" * 15_000
        windows = _windows(text, size=1_000, overlap=200)
        assert len(windows) > 1
        # A name on a seam is whole in the next window because of this.
        assert all(len(w) <= 1_000 for w in windows)
        assert len(windows) == 19

    def test_a_pathological_overlap_is_refused_loudly(self) -> None:
        """A zero/negative stride, clamped to 1, would turn one chapter into
        thousands of calls. This file exists because a cost decision was made
        invisibly once already."""
        with pytest.raises(ValueError, match="overlap"):
            _windows("y" * 5_000, size=100, overlap=500)


class TestQwenDetectorCoversTheWholeChapter:
    def test_an_entity_past_6000_chars_is_found(self) -> None:
        """The 2026-09-23 defect: RI ch1 names Bai Ning Bing first at offset
        6746 of 13,100 chars, and she had zero mentions until chapter 108."""
        filler = "The village was quiet. " * 400  # ~9,200 chars
        text = filler + "Bai Ning Bing stepped out of the snow. " + filler
        offset = text.index("Bai Ning Bing")
        assert offset > 6_000, "the fixture must actually exercise the old cut"

        client = RecordingClient({"Bai Ning Bing": "character"})
        spans = QwenNerDetector(client, novel_id="ri").detect_with_context(text, [])

        assert [s.start for s in spans] == [offset]
        assert len(client.passages) > 1

    def test_the_same_span_seen_twice_is_emitted_once(self) -> None:
        """A name in the overlap region is returned by two windows; the union
        must not double-count it into a false prominence signal."""
        text = "a" * 5_800 + " Fang Yuan walked. " + "b" * 5_800
        client = RecordingClient({"Fang Yuan": "character"})
        spans = QwenNerDetector(client).detect_with_context(text, [])
        assert len(client.passages) >= 2
        assert len(spans) == 1

    def test_character_wins_a_tied_label_disagreement(self) -> None:
        """Window order must not decide whether an entity is a person."""
        location_first = NerSpan("Gu Yue", 0, 6, "location", 0.8)
        character = NerSpan("Gu Yue", 0, 6, "character", 0.8)
        assert _outranks(character, location_first)
        assert not _outranks(location_first, character)

    def test_higher_confidence_wins_regardless_of_label(self) -> None:
        assert _outranks(
            NerSpan("Gu Yue", 0, 6, "location", 0.9),
            NerSpan("Gu Yue", 0, 6, "character", 0.8),
        )

    def test_spans_come_back_sorted_by_offset(self) -> None:
        text = "Fang Yuan spoke. " + "c" * 8_000 + " Gu Yue Bo answered."
        client = RecordingClient({"Fang Yuan": "character", "Gu Yue Bo": "character"})
        spans = QwenNerDetector(client).detect_with_context(text, [])
        assert [s.start for s in spans] == sorted(s.start for s in spans)
        assert [s.text for s in spans] == ["Fang Yuan", "Gu Yue Bo"]


class TestItemLabel:
    def test_item_survives_the_keep_list(self) -> None:
        """`resolve/runner.py::_KIND_BY_LABEL` has mapped "item" to
        TargetKind.ITEM all along, but this filter dropped it before it could
        ever arrive — so a named Gu was typed as a person."""
        detector = FakeDetector([("Spring Autumn Cicada", "item")])
        names = extract_chapter_names(detector, "text", known_names=[])
        assert names.surfaces == {"Spring Autumn Cicada": "item"}
        assert names.rejected == 0

    def test_item_is_offered_in_the_schema(self) -> None:
        assert "item" in NerEntity.model_fields["label"].description
        assert "item" in DEFAULT_LABELS
