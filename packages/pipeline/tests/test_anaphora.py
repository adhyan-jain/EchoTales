"""Tests for Phase 5 local anaphora resolution.

Weighted toward precision-over-recall (non-negotiable #9): most of these check
that the resolver *declines* rather than guesses, because a false merge
corrupts an entity permanently while a missed link costs one mention Phase 6
may still recover.
"""

from __future__ import annotations

import pytest
from echotales.core.enums import (
    AliasType,
    BlockType,
    Canonicity,
    ReferenceMode,
    SegmentType,
    SpanType,
)
from echotales.core.models import MAIN_TIMELINE, Block, Chapter, Mention, NarrativeSegment, Span
from echotales.core.store import Store
from echotales.pipeline.anaphora import (
    MentionGroup,
    ViolationKind,
    check_co_presence,
    check_layer_boundary,
    find_pronouns,
    group_mentions,
    infer_gender,
    most_informative_label,
    present_cast,
    resolve_novel,
    resolve_pronoun,
    validate_groups,
)


def mention(
    text: str,
    offset: int,
    *,
    mid: str | None = None,
    chapter: float = 1.0,
    block_index: int = 0,
    alias_type: AliasType = AliasType.RIGID_NAME,
    mode: ReferenceMode = ReferenceMode.PRESENT,
) -> Mention:
    return Mention(
        id=mid or f"m{offset}",
        novel_id="t",
        segment_id="seg0",
        chapter=chapter,
        offset=offset,
        block_index=block_index,
        text=text,
        alias_type=alias_type,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=mode,
    )


def span(text: str, start: int = 0, span_type: SpanType = SpanType.NARRATION_ACTION) -> Span:
    return Span(
        id=f"s{start}",
        novel_id="t",
        chapter=1.0,
        block_index=0,
        start=start,
        end=start + len(text),
        span_type=span_type,
        text=text,
    )


def segment(
    timeline: str, from_block: int, to_block: int, *, chapter: float = 1.0
) -> NarrativeSegment:
    return NarrativeSegment(
        id=f"seg-{timeline}-{from_block}",
        novel_id="t",
        chapter_from=chapter,
        offset_from=from_block,
        chapter_to=chapter,
        offset_to=to_block,
        timeline_id=timeline,
        story_seq_from=0.0,
        story_seq_to=1.0,
        segment_type=SegmentType.MAIN if timeline == MAIN_TIMELINE else SegmentType.DREAM_OTHER,
        canonicity=Canonicity.CANONICAL,
    )


# ---------------------------------------------------------------------------
# Pronouns
# ---------------------------------------------------------------------------


class TestFindPronouns:
    def test_finds_third_person(self) -> None:
        found = {p[0].casefold() for p in find_pronouns("He told her they had arrived.")}
        assert {"he", "her", "they"} <= found

    def test_first_and_second_person_are_excluded(self) -> None:
        """Those resolve to speaker and addressee, which attribution handles."""
        assert find_pronouns("I told you so.") == []

    def test_offsets_are_absolute(self) -> None:
        found = find_pronouns("he ran", base_offset=100)
        assert found[0][1] == 100

    def test_gender_and_number_are_reported(self) -> None:
        _, _, gender, number = find_pronouns("she")[0]
        assert (gender, number) == ("f", "sg")


class TestResolvePronoun:
    def test_nearest_prior_mention_wins(self) -> None:
        candidates = [mention("Wu An", 0), mention("Fang Yuan", 100)]
        out = resolve_pronoun(150, "m", "sg", candidates)
        assert out and out[0].text == "Fang Yuan"

    def test_later_mentions_are_ignored(self) -> None:
        """Cataphora is rare here and admitting it doubles the candidate set."""
        assert resolve_pronoun(50, "m", "sg", [mention("Fang Yuan", 100)]) is None

    def test_distant_antecedents_are_refused(self) -> None:
        assert resolve_pronoun(10_000, "m", "sg", [mention("Fang Yuan", 0)]) is None

    def test_gender_disagreement_rejects(self) -> None:
        candidates = [mention("Bai Ning Bing", 0)]
        assert resolve_pronoun(50, "f", "sg", candidates, genders={"Bai Ning Bing": "m"}) is None

    def test_unknown_gender_is_compatible_with_anything(self) -> None:
        """Unknown must not act as a mismatch, or recall collapses."""
        out = resolve_pronoun(50, "f", "sg", [mention("Someone", 0)], genders={"Someone": "n"})
        assert out is not None

    def test_a_unique_candidate_scores_higher_than_a_chosen_one(self) -> None:
        unique = resolve_pronoun(50, "m", "sg", [mention("Fang Yuan", 0)])
        several = resolve_pronoun(
            50, "m", "sg", [mention("Fang Yuan", 0), mention("Wu An", 20)]
        )
        assert unique and several and unique[1] > several[1]

    def test_no_candidates_returns_none(self) -> None:
        assert resolve_pronoun(50, "m", "sg", []) is None

    def test_non_rigid_mentions_are_not_antecedents(self) -> None:
        candidates = [mention("Elder", 0, alias_type=AliasType.TRANSFERABLE_TITLE)]
        assert resolve_pronoun(50, "m", "sg", candidates) is None


class TestInferGender:
    def test_male_cues(self) -> None:
        assert infer_gender("X", ["He raised his hand.", "his brother said"]) == "m"

    def test_female_cues(self) -> None:
        assert infer_gender("X", ["She raised her hand.", "her sister said"]) == "f"

    def test_mixed_evidence_stays_unknown(self) -> None:
        """A wrong guess should cost a missed link, not a fabricated fact."""
        assert infer_gender("X", ["He and she spoke.", "his and her things"]) == "n"

    def test_no_evidence_is_unknown(self) -> None:
        assert infer_gender("X", []) == "n"


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


class TestGrouping:
    def test_same_surface_form_groups_within_a_chapter(self) -> None:
        mentions = [mention("Fang Yuan", 0), mention("Fang Yuan", 200, mid="m2")]
        groups, _ = group_mentions(mentions, [span("Fang Yuan walked.")])
        assert len(groups) == 1
        assert groups[0].size == 2

    def test_different_names_stay_separate(self) -> None:
        mentions = [mention("Fang Yuan", 0), mention("Wu An", 50, mid="m2")]
        groups, _ = group_mentions(mentions, [span("x")])
        assert len(groups) == 2

    def test_groups_carry_a_rationale(self) -> None:
        """A bad merge has to be auditable after the fact."""
        groups, _ = group_mentions([mention("Fang Yuan", 0)], [span("x")])
        assert groups[0].rationale

    def test_most_informative_label_prefers_the_fullest_name(self) -> None:
        mentions = [mention("Wang", 0), mention("Sect Master Wang Lin", 10, mid="m2")]
        assert most_informative_label(mentions) == "Sect Master Wang Lin"


class TestPresentCast:
    def test_only_present_mentions_count(self) -> None:
        """A character merely named in dialogue is not in the scene."""
        mentions = [
            mention("Fang Yuan", 0),
            mention("Wu An", 10, mid="m2", mode=ReferenceMode.DIALOGUE_REFERENCE),
        ]
        assert present_cast(mentions) == {"Fang Yuan"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestLayerBoundary:
    def test_a_group_spanning_two_timelines_is_split(self) -> None:
        """Dream entities must not merge with main-timeline ones."""
        mentions = [
            mention("Fang Yuan", 0, mid="a", block_index=1),
            mention("Fang Yuan", 0, mid="b", block_index=6),
        ]
        segments = [segment(MAIN_TIMELINE, 0, 4), segment("DREAM_CH1_1", 5, 9)]
        group = MentionGroup(id="g0", mention_ids=["a", "b"], label="Fang Yuan")
        out = check_layer_boundary(group, {m.id: m for m in mentions}, segments)
        assert out is not None and len(out) == 2

    def test_a_group_within_one_timeline_is_untouched(self) -> None:
        mentions = [
            mention("Fang Yuan", 0, mid="a", block_index=1),
            mention("Fang Yuan", 0, mid="b", block_index=2),
        ]
        segments = [segment(MAIN_TIMELINE, 0, 9)]
        group = MentionGroup(id="g0", mention_ids=["a", "b"], label="Fang Yuan")
        assert check_layer_boundary(group, {m.id: m for m in mentions}, segments) is None

    def test_mentions_outside_every_segment_do_not_trigger_a_split(self) -> None:
        """Block index, not character offset, is the unit segments use.

        Comparing the two made most mentions match no segment, and the empty
        timeline then split against MAIN_TIMELINE -- thousands of phantom
        violations.
        """
        mentions = [
            mention("Fang Yuan", 0, mid="a", block_index=1),
            mention("Fang Yuan", 900, mid="b", block_index=2),
        ]
        segments = [segment(MAIN_TIMELINE, 0, 9)]
        group = MentionGroup(id="g0", mention_ids=["a", "b"], label="Fang Yuan")
        assert check_layer_boundary(group, {m.id: m for m in mentions}, segments) is None


class TestCoPresence:
    def test_simultaneous_distinct_mentions_violate(self) -> None:
        mentions = [
            mention("Wu An", 0, mid="a"),
            mention("Wu Bei", 50, mid="b"),
        ]
        group = MentionGroup(id="g0", mention_ids=["a", "b"], label="Wu An")
        violation = check_co_presence(group, {m.id: m for m in mentions})
        assert violation and violation.kind == ViolationKind.CO_PRESENCE

    def test_identical_surface_forms_do_not_violate(self) -> None:
        mentions = [mention("Wu An", 0, mid="a"), mention("Wu An", 50, mid="b")]
        group = MentionGroup(id="g0", mention_ids=["a", "b"], label="Wu An")
        assert check_co_presence(group, {m.id: m for m in mentions}) is None

    def test_concurrent_personas_suppress_the_penalty(self) -> None:
        """Clones and sustained disguises are *expected* to co-occur.

        This is why the penalty is defined between personas and never between
        selves.
        """
        mentions = [mention("Wu An", 0, mid="a"), mention("Wu Bei", 50, mid="b")]
        group = MentionGroup(id="g0", mention_ids=["a", "b"], label="Cloned One")
        assert (
            check_co_presence(
                group,
                {m.id: m for m in mentions},
                concurrent_personas=frozenset({"Cloned One"}),
            )
            is None
        )

    def test_non_present_mentions_are_ignored(self) -> None:
        mentions = [
            mention("Wu An", 0, mid="a"),
            mention("Wu Bei", 50, mid="b", mode=ReferenceMode.DIALOGUE_REFERENCE),
        ]
        group = MentionGroup(id="g0", mention_ids=["a", "b"], label="Wu An")
        assert check_co_presence(group, {m.id: m for m in mentions}) is None


class TestValidateGroups:
    def test_violating_groups_are_split_not_repaired(self) -> None:
        mentions = [mention("Wu An", 0, mid="a"), mention("Wu Bei", 50, mid="b")]
        group = MentionGroup(id="g0", mention_ids=["a", "b"], label="Wu An")
        result = validate_groups([group], mentions, [segment(MAIN_TIMELINE, 0, 9)])
        assert len(result.groups) == 2
        assert result.split_count >= 1

    def test_clean_groups_survive(self) -> None:
        mentions = [mention("Wu An", 0, mid="a"), mention("Wu An", 50, mid="b")]
        group = MentionGroup(id="g0", mention_ids=["a", "b"], label="Wu An")
        result = validate_groups([group], mentions, [segment(MAIN_TIMELINE, 0, 9)])
        assert len(result.groups) == 1
        assert not result.violations

    def test_excessive_fragmentation_escalates(self) -> None:
        """Far more groups than names means something upstream is broken."""
        mentions = [mention("Wu An", i * 10, mid=f"m{i}") for i in range(8)]
        groups = [MentionGroup(id=f"g{i}", mention_ids=[f"m{i}"], label="Wu An") for i in range(8)]
        result = validate_groups(groups, mentions, [segment(MAIN_TIMELINE, 0, 9)])
        assert result.needs_escalation


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class TestRunner:
    @pytest.fixture
    def store(self) -> Store:
        s = Store(":memory:")
        s.add_novel("t", "T", "x.epub", "generic")
        s.add_chapter(
            Chapter(
                novel_id="t",
                number=1.0,
                title="T",
                source_href="a.html",
                blocks=[
                    Block(index=0, block_type=BlockType.PROSE, text="Fang Yuan stepped forward."),
                    Block(index=1, block_type=BlockType.PROSE, text="He drew his blade."),
                ],
            )
        )
        s.add_segments([segment(MAIN_TIMELINE, 0, 5)])
        s.add_mentions([mention("Fang Yuan", 0, block_index=0)])
        s.conn.commit()
        return s

    def test_group_ids_are_written_back(self, store: Store) -> None:
        resolve_novel("t", store)
        assert any(m.local_group_id for m in store.get_mentions("t"))

    def test_report_counts(self, store: Store) -> None:
        report = resolve_novel("t", store)
        assert report.chapters == 1
        assert report.groups >= 1
