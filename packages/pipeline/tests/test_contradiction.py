"""Tests for contradiction detection and the recall@k harness.

The contradiction detector cannot currently be exercised by real corpus data:
it exists to catch over-*merging*, and Phase 6 is presently over-*splitting*, so
no entity accumulates enough aliases to trigger it. These tests therefore
construct the failure directly — which is the right way to test a safety net
regardless.
"""

from __future__ import annotations

import pytest
from echotales.core.enums import (
    OBSERVER_READER,
    AliasType,
    AssertedBy,
    EventType,
    ReferenceMode,
    SpanType,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, DiscoursePosition, Mention
from echotales.core.store import Store
from echotales.pipeline.eval import (
    EvalMode,
    RetrievalCase,
    build_self_retrieval_cases,
    evaluate_recall,
)
from echotales.pipeline.mentions.gazetteer import AMBIGUITY_BLOCKLIST, Gazetteer
from echotales.pipeline.resolve.contradiction import (
    ContradictionKind,
    detect_attribute_conflict,
    detect_co_presence,
    detect_conflicting_names,
    sweep,
)
from echotales.pipeline.resolve.retrieve import CandidateRetriever, EntityProfile

NOVEL = "t"


def mention(
    text: str,
    offset: int,
    *,
    mid: str | None = None,
    chapter: float = 1.0,
    target: str = "e1",
    mode: ReferenceMode = ReferenceMode.PRESENT,
) -> Mention:
    return Mention(
        id=mid or f"m{offset}",
        novel_id=NOVEL,
        segment_id="seg0",
        chapter=chapter,
        offset=offset,
        text=text,
        alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=mode,
        target_kind=TargetKind.SELF,
        target_id=target,
    )


@pytest.fixture
def store() -> Store:
    s = Store(":memory:")
    s.add_novel(NOVEL, "T", "x.epub", "generic")
    return s


# ---------------------------------------------------------------------------
# Co-presence discovered later
# ---------------------------------------------------------------------------


class TestCoPresence:
    def test_two_forms_present_together_contradict(self) -> None:
        """Proves they were never one persona, however they were linked."""
        found = detect_co_presence(
            "e1", [mention("Wu An", 0, mid="a"), mention("Wu Bei", 60, mid="b")]
        )
        assert found is not None
        assert found.kind is ContradictionKind.CO_PRESENCE

    def test_same_name_twice_is_not_a_contradiction(self) -> None:
        found = detect_co_presence(
            "e1", [mention("Wu An", 0, mid="a"), mention("Wu An", 60, mid="b")]
        )
        assert found is None

    def test_honorific_variants_are_not_a_contradiction(self) -> None:
        """'Elder Wang' beside 'Wang' is one person addressed two ways."""
        found = detect_co_presence(
            "e1", [mention("Elder Wang", 0, mid="a"), mention("Wang", 60, mid="b")]
        )
        assert found is None

    def test_distant_mentions_do_not_contradict(self) -> None:
        found = detect_co_presence(
            "e1", [mention("Wu An", 0, mid="a"), mention("Wu Bei", 5000, mid="b")]
        )
        assert found is None

    def test_different_chapters_do_not_contradict(self) -> None:
        found = detect_co_presence(
            "e1",
            [
                mention("Wu An", 0, mid="a", chapter=1.0),
                mention("Wu Bei", 60, mid="b", chapter=2.0),
            ],
        )
        assert found is None

    def test_only_present_mentions_count(self) -> None:
        """A name spoken aloud says nothing about who is in the room."""
        found = detect_co_presence(
            "e1",
            [
                mention("Wu An", 0, mid="a"),
                mention("Wu Bei", 60, mid="b", mode=ReferenceMode.DIALOGUE_REFERENCE),
            ],
        )
        assert found is None


# ---------------------------------------------------------------------------
# Too many distinct names
# ---------------------------------------------------------------------------


class TestConflictingNames:
    def test_many_distinct_names_flag_a_bad_merge(self) -> None:
        profile = EntityProfile(
            target_id="e1",
            target_kind=TargetKind.SELF,
            label="X",
            aliases={"Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"},
        )
        found = detect_conflicting_names("e1", profile)
        assert found is not None
        assert found.kind is ContradictionKind.CONFLICTING_NAMES

    def test_a_name_plus_an_epithet_is_normal(self) -> None:
        profile = EntityProfile(
            target_id="e1",
            target_kind=TargetKind.SELF,
            label="X",
            aliases={"Fang Yuan", "the demon"},
        )
        assert detect_conflicting_names("e1", profile) is None

    def test_variants_of_one_name_do_not_count_separately(self) -> None:
        """Exactly the forms that *should* collapse must not trigger a split."""
        profile = EntityProfile(
            target_id="e1",
            target_kind=TargetKind.SELF,
            label="Justice",
            aliases={"Justice", "Miss Justice", "Lady Justice", "The Justice", "Mr. Justice"},
        )
        assert detect_conflicting_names("e1", profile) is None


# ---------------------------------------------------------------------------
# Attribute conflicts
# ---------------------------------------------------------------------------


class TestAttributeConflict:
    def add_attr(self, store: Store, key: str, value: str, chapter: int) -> None:
        store.add_attribute(
            NOVEL,
            Attribute(
                target_kind=TargetKind.SELF,
                target_id="e1",
                key=key,
                value=value,
                interval=FuzzyInterval.open_ended(chapter, last_evidence=1e6),
                learned_at_pos=DiscoursePosition(chapter=chapter),
                observer_id=OBSERVER_READER,
                asserted_by=AssertedBy.NARRATOR,
                truth_status=TruthStatus.TRUE,
            ),
        )

    def test_mutually_exclusive_values_contradict(self, store: Store) -> None:
        self.add_attr(store, "species", "human", 5)
        self.add_attr(store, "species", "demon", 90)
        store.conn.commit()
        found = detect_attribute_conflict("e1", store)
        assert found is not None
        assert found.kind is ContradictionKind.ATTRIBUTE_CONFLICT

    def test_ordinary_attributes_may_change(self, store: Store) -> None:
        """A rank or location changing over time is an update, not a conflict."""
        self.add_attr(store, "rank", "three", 5)
        self.add_attr(store, "rank", "five", 90)
        store.conn.commit()
        assert detect_attribute_conflict("e1", store) is None

    def test_repeated_identical_values_do_not_conflict(self, store: Store) -> None:
        self.add_attr(store, "species", "human", 5)
        self.add_attr(store, "species", "Human", 90)
        store.conn.commit()
        assert detect_attribute_conflict("e1", store) is None


# ---------------------------------------------------------------------------
# The sweep, and split emission
# ---------------------------------------------------------------------------


class TestSweep:
    def test_sweep_emits_split_events(self, store: Store) -> None:
        """Before this existed nothing in the pipeline emitted split/retract,
        which made the retroactive-correction metric unreportable."""
        store.add_mentions([mention("Wu An", 0, mid="a"), mention("Wu Bei", 60, mid="b")])
        store.conn.commit()
        profiles = {
            "e1": EntityProfile(
                target_id="e1", target_kind=TargetKind.SELF, label="Wu An",
                aliases={"Wu An", "Wu Bei"}, mention_count=2,
            )
        }
        found, report = sweep(NOVEL, store, profiles, window=1)

        assert found
        assert report.splits_emitted >= 1
        assert store.event_counts().get(EventType.SPLIT.value, 0) >= 1

    def test_clean_graph_emits_nothing(self, store: Store) -> None:
        store.add_mentions([mention("Wu An", 0, mid="a"), mention("Wu An", 60, mid="b")])
        store.conn.commit()
        profiles = {
            "e1": EntityProfile(
                target_id="e1", target_kind=TargetKind.SELF, label="Wu An",
                aliases={"Wu An"}, mention_count=2,
            )
        }
        found, report = sweep(NOVEL, store, profiles, window=1)
        assert not found
        assert report.splits_emitted == 0

    def test_split_event_carries_its_evidence(self, store: Store) -> None:
        """A reviewer at ch 190 must see why a ch-30 link was withdrawn."""
        store.add_mentions([mention("Wu An", 0, mid="a"), mention("Wu Bei", 60, mid="b")])
        store.conn.commit()
        profiles = {
            "e1": EntityProfile(
                target_id="e1", target_kind=TargetKind.SELF, label="Wu An",
                aliases={"Wu An", "Wu Bei"}, mention_count=2,
            )
        }
        sweep(NOVEL, store, profiles, window=1)
        events = [e for e in store.iter_events() if e.type is EventType.SPLIT]
        assert events and events[0].payload.get("detail")


# ---------------------------------------------------------------------------
# Gazetteer ambiguity blocklist
# ---------------------------------------------------------------------------


class TestAmbiguityBlocklist:
    @pytest.mark.parametrize("word", ["Fate", "Justice", "Hope", "Master", "Dawn"])
    def test_ambiguous_whole_words_are_refused(self, word: str) -> None:
        """An exact gazetteer match force-links through the pre-filter, so one
        common word admitted here mislinks every occurrence in the volume."""
        g = Gazetteer()
        g.add(word, AliasType.RIGID_NAME)
        assert len(g) == 0

    def test_compounds_containing_a_blocked_word_are_admitted(self) -> None:
        """Surrounding tokens disambiguate it."""
        g = Gazetteer()
        g.add("Fate Weaver Lin", AliasType.RIGID_NAME)
        assert len(g) == 1

    def test_blocklist_is_case_insensitive(self) -> None:
        g = Gazetteer()
        g.add("FATE", AliasType.RIGID_NAME)
        assert len(g) == 0

    def test_ordinary_names_still_admitted(self) -> None:
        g = Gazetteer()
        g.add("Fang Yuan", AliasType.RIGID_NAME)
        assert len(g) == 1

    def test_blocklist_is_non_empty(self) -> None:
        assert len(AMBIGUITY_BLOCKLIST) > 20


# ---------------------------------------------------------------------------
# recall@k harness
# ---------------------------------------------------------------------------


class TestRecallHarness:
    def retriever(self) -> CandidateRetriever:
        r = CandidateRetriever()
        r.observe("e1", "Fang Yuan", "gu master mountain clan", 1.0, label="Fang Yuan")
        r.observe("e1", "Fang Yuan", "gu master mountain clan", 2.0, label="Fang Yuan")
        r.observe("e2", "Wu An", "clan hall elder meeting", 1.0, label="Wu An")
        r.observe("e2", "Wu An", "clan hall elder meeting", 3.0, label="Wu An")
        return r

    def test_recall_at_k_finds_the_expected_entity(self) -> None:
        cases = [
            RetrievalCase(
                surface="Fang Yuan",
                context="gu master mountain",
                expected_target_id="e1",
            )
        ]
        result = evaluate_recall(self.retriever(), cases)
        assert result.recall_at(10) == 1.0

    def test_a_miss_is_recorded(self) -> None:
        cases = [
            RetrievalCase(surface="Nobody", context="", expected_target_id="e99")
        ]
        result = evaluate_recall(self.retriever(), cases)
        assert result.recall_at(20) == 0.0
        assert result.misses

    def test_recall_is_broken_down_by_alias_type(self) -> None:
        cases = [
            RetrievalCase("Fang Yuan", "gu master", "e1", AliasType.RIGID_NAME),
            RetrievalCase("Sect Master", "clan hall", "e2", AliasType.TRANSFERABLE_TITLE),
        ]
        result = evaluate_recall(self.retriever(), cases)
        assert set(result.by_alias_type_total) == {"RIGID_NAME", "TRANSFERABLE_TITLE"}

    def test_gate_is_untested_without_transferable_titles(self) -> None:
        """Reporting a pass on an untested gate would be worse than reporting nothing."""
        cases = [RetrievalCase("Fang Yuan", "gu master", "e1", AliasType.RIGID_NAME)]
        assert evaluate_recall(self.retriever(), cases).gate_passes is None

    def test_gate_fails_below_threshold(self) -> None:
        cases = [
            RetrievalCase("Nobody", "", "e99", AliasType.TRANSFERABLE_TITLE)
            for _ in range(5)
        ]
        result = evaluate_recall(self.retriever(), cases)
        assert result.gate_passes is False
        assert "FAIL" in result.summary()

    def test_self_retrieval_cases_skip_single_mention_entities(self) -> None:
        r = CandidateRetriever()
        r.observe("solo", "Once", "context", 1.0, label="Once")
        assert build_self_retrieval_cases(r) == []

    def test_self_retrieval_mode_is_labelled_as_a_smoke_test(self) -> None:
        """It must never be mistaken for a recall@k result."""
        r = self.retriever()
        result = evaluate_recall(
            r, build_self_retrieval_cases(r), mode=EvalMode.SELF_RETRIEVAL
        )
        assert "smoke test" in result.summary()
