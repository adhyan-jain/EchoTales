"""Tests for Phase 4 speaker attribution."""

from __future__ import annotations

import pytest
from echotales.core.enums import AliasType, AttributionMethod, BlockType, ReferenceMode, SpanType
from echotales.core.models import Block, Chapter, Mention, Span
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.stub import StubProvider
from echotales.pipeline.spans.scene import ActiveScene
from echotales.pipeline.speakers import (
    attribute_chapter,
    attribute_explicit,
    attribute_novel,
    attribute_proximal,
    attribute_span,
    attribute_turn_taking,
)
from echotales.pipeline.speakers.runner import _scene_roster


def span(text: str, span_type: SpanType = SpanType.DIALOGUE, span_id: str = "s1") -> Span:
    return Span(
        id=span_id,
        novel_id="t",
        chapter=1.0,
        block_index=0,
        start=0,
        end=len(text),
        span_type=span_type,
        text=text,
    )


def chapter(*texts: str, number: float = 1.0) -> Chapter:
    return Chapter(
        novel_id="t",
        number=number,
        title="T",
        source_href="a.html",
        blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(texts)],
    )


# ---------------------------------------------------------------------------
# Tier 1: explicit
# ---------------------------------------------------------------------------


class TestExplicit:
    def test_name_before_verb(self) -> None:
        out = attribute_explicit(span("“Speak.”"), preceding="Li Wei said,", following="")
        assert out and out.speaker == "Li Wei"
        assert out.method is AttributionMethod.EXPLICIT

    def test_verb_after_quote(self) -> None:
        out = attribute_explicit(span("“Speak.”"), preceding="", following=", said Li Wei.")
        assert out and out.speaker == "Li Wei"

    def test_following_is_checked_before_preceding(self) -> None:
        """'…,' X said is far more common than X said, '…' in this prose.

        Checking the wrong side first picks up the previous line's speaker.
        """
        out = attribute_explicit(
            span("“Speak.”"), preceding="Wu An laughed. Wu Bei said,", following=" Li Wei replied."
        )
        assert out and out.speaker == "Li Wei"

    def test_delivery_adverb_between_name_and_verb(self) -> None:
        out = attribute_explicit(span("“Speak.”"), preceding="", following=" Li Wei coldly said.")
        assert out and out.speaker == "Li Wei"

    def test_joint_attribution_keeps_both_speakers(self) -> None:
        """Forcing one speaker would silently discard the other."""
        out = attribute_explicit(
            span("“Yes!”"), preceding="", following=" Wu Liao and Wu An immediately responded."
        )
        assert out and out.method is AttributionMethod.JOINT
        assert out.speaker == "Wu Liao"
        assert out.co_speakers == ["Wu An"]

    def test_unknown_names_are_rejected_when_a_roster_is_supplied(self) -> None:
        out = attribute_explicit(
            span("“Speak.”"),
            preceding="",
            following=" Nonexistent Person said.",
            known_names=frozenset({"Li Wei"}),
        )
        assert out is None

    def test_honorific_forms_match_the_roster(self) -> None:
        """Exact matching rejected 'Wang' against a stored 'Elder Wang'."""
        out = attribute_explicit(
            span("“Speak.”"),
            preceding="",
            following=" Elder Wang said.",
            known_names=frozenset({"wang"}),
        )
        assert out and "Wang" in out.speaker

    def test_no_attribution_returns_none(self) -> None:
        assert attribute_explicit(span("“Speak.”"), preceding="", following="") is None


# ---------------------------------------------------------------------------
# Tier 2: proximal
# ---------------------------------------------------------------------------


class TestProximal:
    def test_action_before_the_line(self) -> None:
        out = attribute_proximal(span("“Speak.”"), preceding="Li Wei nodded.", following="")
        assert out and out.speaker == "Li Wei"
        assert out.method is AttributionMethod.PROXIMAL

    def test_split_sentence_takes_the_nearest_name(self) -> None:
        """The case plans.md calls out.

        In "Wu Liao excused himself, but Wu An hesitated and said softly:" the
        speaker is Wu An -- the last name before the line, not the first.
        """
        out = attribute_proximal(
            span("“I will go.”"),
            preceding="Wu Liao turned away, but Wu An hesitated",
            following="",
        )
        assert out and out.speaker == "Wu An"

    def test_confidence_is_below_explicit(self) -> None:
        explicit = attribute_explicit(span("“x”"), preceding="", following=" Li Wei said.")
        proximal = attribute_proximal(span("“x”"), preceding="Li Wei nodded.", following="")
        assert explicit and proximal and proximal.confidence < explicit.confidence


# ---------------------------------------------------------------------------
# Tier 3: turn-taking
# ---------------------------------------------------------------------------


class TestTurnTaking:
    def test_two_party_exchange_alternates(self) -> None:
        out = attribute_turn_taking(span("“x”"), ["Wu An", "Wu Bei", "Wu An"])
        assert out and out.speaker == "Wu Bei"

    def test_three_speakers_defers(self) -> None:
        """With three parties the alternation assumption is unfounded.

        A confident wrong answer is worse than deferring.
        """
        assert attribute_turn_taking(span("“x”"), ["A", "B", "C", "A"]) is None

    def test_too_little_history_defers(self) -> None:
        assert attribute_turn_taking(span("“x”"), ["A"]) is None


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------


class TestLadder:
    def test_explicit_wins_over_proximal(self) -> None:
        out = attribute_span(
            span("“Speak.”"), preceding="Wu Bei nodded.", following=" Li Wei said."
        )
        assert out.method is AttributionMethod.EXPLICIT
        assert out.speaker == "Li Wei"

    def test_crowd_reactions_get_no_speaker(self) -> None:
        """Attributing a crowd to the last named character invents attributions
        that propagate into voice casting."""
        out = attribute_span(span("“Impossible!”", SpanType.CROWD_REACTION))
        assert out.speaker is None
        assert out.method is AttributionMethod.UNATTRIBUTED_CHORUS
        assert out.is_resolved, "a chorus is a resolved outcome, not a failure"

    def test_inner_monologue_goes_to_the_pov_holder(self) -> None:
        out = attribute_span(
            span("“What now?”", SpanType.INNER_MONOLOGUE), pov_holder="Fang Yuan"
        )
        assert out.speaker == "Fang Yuan"
        assert out.method is AttributionMethod.POV_INFERRED

    def test_narration_is_not_attributed(self) -> None:
        out = attribute_span(span("He walked away.", SpanType.NARRATION_ACTION))
        assert out.method is AttributionMethod.UNRESOLVED

    def test_unresolvable_line_defers(self) -> None:
        out = attribute_span(span("“Speak.”"))
        assert out.speaker is None
        assert out.method is AttributionMethod.UNRESOLVED


# ---------------------------------------------------------------------------
# Chapter level
# ---------------------------------------------------------------------------


class TestChapterLevel:
    def test_attribution_reaches_across_block_boundaries(self) -> None:
        """~15% of speech spans occupy a paragraph of their own.

        Confining the window to the current block makes those unattributable
        no matter how explicit the neighbouring text is.
        """
        ch = chapter("Li Wei stepped forward.", "“I have something to report.”")
        out = attribute_chapter(ch)
        speech = [a for a in out if a.speaker]
        assert speech and speech[0].speaker == "Li Wei"

    def test_scene_break_resets_alternation(self) -> None:
        """Carrying turn-taking across a scene break attributes the first line
        of a new scene to someone no longer present."""
        ch = chapter(
            "Wu An said, “One.”",
            "Wu Bei said, “Two.”",
            "* * *",
            "“Three.”",
        )
        out = attribute_chapter(ch)
        last = [a for a in out if a.span_id.endswith(":0")][-1]
        assert last.method is not AttributionMethod.TURN_TAKING

    def test_only_confident_lines_seed_alternation(self) -> None:
        """Seeding the state from a guess makes the next guess worse."""
        ch = chapter("“One.”", "“Two.”", "“Three.”")
        out = attribute_chapter(ch)
        assert all(a.method is not AttributionMethod.TURN_TAKING for a in out)


class TestRunner:
    @pytest.fixture
    def store(self) -> Store:
        s = Store(":memory:")
        s.add_novel("t", "T", "x.epub", "generic")
        return s

    def test_spans_are_persisted_with_speakers(self, store: Store) -> None:
        store.add_chapter(chapter("Li Wei said, “Speak.”"))
        store.conn.commit()
        report = attribute_novel("t", store)
        assert report.dialogue_spans > 0
        saved = store.get_spans("t", 1.0)
        assert any(s.speaker_self_id for s in saved)

    def test_roster_accumulates_across_chapters(self, store: Store) -> None:
        """A character introduced in chapter 1 still speaks in chapter 2."""
        store.add_chapter(chapter("Li Wei arrived.", number=1.0))
        store.add_chapter(chapter("Li Wei said, “Speak.”", number=2.0))
        store.conn.commit()
        report = attribute_novel("t", store)
        assert report.by_method.get(AttributionMethod.EXPLICIT.value, 0) >= 1

    def test_coverage_is_reported(self, store: Store) -> None:
        store.add_chapter(chapter("Li Wei said, “Speak.”", "“Who?”"))
        store.conn.commit()
        report = attribute_novel("t", store)
        assert 0.0 <= report.coverage <= 1.0


class TestContextualTier:
    """Tier 4: LLM-backed cold-start attribution, gated to early chapters."""

    @pytest.fixture
    def store(self) -> Store:
        s = Store(":memory:")
        s.add_novel("t", "T", "x.epub", "generic")
        # Chapter 1 establishes the roster; chapter 2's inner monologue has no
        # nearby name or verb, so tiers 1-3 and POV inference all miss it --
        # the exact cold-start gap tier 4 exists for.
        s.add_chapter(chapter("Zhou Mingrui walked home.", number=1.0))
        s.add_chapter(
            Chapter(
                novel_id="t",
                number=2.0,
                title="T2",
                source_href="b.html",
                blocks=[
                    Block(
                        index=0,
                        block_type=BlockType.PROSE,
                        text="Painful! Why does my head hurt so much?",
                        italic_ranges=[(0, 40)],
                    )
                ],
            )
        )
        s.add_mentions(
            [
                Mention(
                    id="m1",
                    novel_id="t",
                    segment_id="",
                    chapter=1.0,
                    offset=0,
                    text="Zhou Mingrui",
                    alias_type=AliasType.RIGID_NAME,
                    span_type=SpanType.NARRATION_ACTION,
                    reference_mode=ReferenceMode.PRESENT,
                    block_index=0,
                )
            ]
        )
        s.conn.commit()
        return s

    def test_no_client_leaves_it_unresolved(self, store: Store) -> None:
        report = attribute_novel("t", store, llm_chapter_cutoff=3.0)
        assert report.by_method.get(AttributionMethod.UNRESOLVED.value, 0) == 1

    def test_roster_match_resolves_it(self, store: Store) -> None:
        stub = StubProvider()
        stub.register_response(
            "speaker_attribution", {"speaker": "Zhou Mingrui", "confidence": 0.8}
        )
        report = attribute_novel(
            "t", store, client=ModelClient(provider_override=stub), llm_chapter_cutoff=3.0
        )
        assert report.by_method.get(AttributionMethod.CONTEXTUAL_LLM.value, 0) == 1
        spans = store.get_spans("t", 2.0)
        assert any(s.speaker_self_id == "Zhou Mingrui" for s in spans)
        assert len(stub.calls) == 1

    def test_off_roster_answer_is_discarded(self, store: Store) -> None:
        """A name the model invents that is not in the roster must not stick --
        mirrors how the regex tiers already discard an unknown capitalised
        token via `_known`."""
        stub = StubProvider()
        stub.register_response(
            "speaker_attribution", {"speaker": "Someone Else", "confidence": 0.9}
        )
        report = attribute_novel(
            "t", store, client=ModelClient(provider_override=stub), llm_chapter_cutoff=3.0
        )
        assert report.by_method.get(AttributionMethod.UNRESOLVED.value, 0) == 1

    def test_scene_roster_narrows_to_active_cast(self) -> None:
        """xyz.md Step 3's scene-constrained pass, reusing tier 4 per HANDOFF.md.

        Chapter-wide roster has three names, but only two are present in the
        scene covering this block -- the roster handed to the model should be
        just those two, in chapter-frequency order.
        """
        scenes = [
            ActiveScene(
                segment_id="seg1",
                chapter=1.0,
                block_from=0,
                block_to=5,
                active_selves={"Fang Yuan", "Zhao Sanshou"},
            )
        ]
        fallback = ["Fang Yuan", "Gu Yue Dong Tu", "Zhao Sanshou"]
        assert _scene_roster(2, scenes, fallback) == ["Fang Yuan", "Zhao Sanshou"]

    def test_scene_roster_falls_back_outside_any_scene(self) -> None:
        scenes = [
            ActiveScene(
                segment_id="seg1", chapter=1.0, block_from=0, block_to=2,
                active_selves={"Fang Yuan"},
            )
        ]
        fallback = ["Fang Yuan", "Gu Yue Dong Tu"]
        assert _scene_roster(9, scenes, fallback) == fallback

    def test_scene_roster_falls_back_when_scene_cast_empty(self) -> None:
        scenes = [
            ActiveScene(segment_id="seg1", chapter=1.0, block_from=0, block_to=5)
        ]
        fallback = ["Fang Yuan", "Gu Yue Dong Tu"]
        assert _scene_roster(1, scenes, fallback) == fallback

    def test_cutoff_excludes_later_chapters(self, store: Store) -> None:
        stub = StubProvider()
        stub.register_response(
            "speaker_attribution", {"speaker": "Zhou Mingrui", "confidence": 0.8}
        )
        attribute_novel(
            "t", store, client=ModelClient(provider_override=stub), llm_chapter_cutoff=1.0
        )
        assert len(stub.calls) == 0
