"""Tests for Phase 1 span classification and delivery markers."""

from __future__ import annotations

import pytest
from echotales.core.enums import BlockType, SpanType
from echotales.core.models import Block, Chapter
from echotales.pipeline.spans import (
    DeliveryPolarity,
    classify_block_spans,
    classify_chapter,
    dominant_polarity,
    extract_delivery_markers,
)
from echotales.pipeline.spans.classify import split_block, split_quoted


def block(text: str, *, italics: list[tuple[int, int]] | None = None, index: int = 0) -> Block:
    return Block(
        index=index,
        block_type=BlockType.PROSE,
        text=text,
        italic_ranges=italics or [],
    )


def types(text: str, *, italics: list[tuple[int, int]] | None = None) -> list[SpanType]:
    spans = classify_block_spans(block(text, italics=italics), novel_id="t", chapter=1.0)
    return [s.span_type for s in spans]


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------


class TestSplitQuoted:
    def test_plain_narration_is_one_span(self) -> None:
        assert len(split_quoted("He walked into the hall.")) == 1

    def test_curly_quotes_are_isolated(self) -> None:
        spans = split_quoted("He said, “Speak.” Then he left.")
        assert [s.is_quoted for s in spans] == [False, True, False]

    def test_straight_quotes_are_isolated(self) -> None:
        spans = split_quoted('He said, "Speak." Then he left.')
        assert any(s.is_quoted for s in spans)

    def test_apostrophe_does_not_open_a_quote(self) -> None:
        """A mid-word apostrophe must not swallow the rest of the paragraph."""
        spans = split_quoted("He didn't know what Fang Yuan's plan was.")
        assert not any(s.is_quoted for s in spans)

    def test_unterminated_quote_runs_to_the_end(self) -> None:
        """Multi-paragraph speeches open a quote and never close it."""
        spans = split_quoted("He said, “This will continue")
        assert spans[-1].is_quoted

    def test_cjk_brackets_are_quotes(self) -> None:
        spans = split_quoted("彼は「そうだ」と言った")
        assert any(s.is_quoted for s in spans)

    def test_offsets_index_the_original_text(self) -> None:
        text = "He said, “Speak.” Then he left."
        for span in split_quoted(text):
            assert text[span.start : span.end] == span.text


class TestSplitOnEmphasis:
    def test_emphasis_creates_a_boundary(self) -> None:
        """The bug this fixes: a thought plus trailing narration in one block.

        Splitting on quotes alone yields one span, the emphasis covers too
        small a fraction of it, and the structural signal that motivated
        choosing EPUB over PDF is discarded at the last step.
        """
        text = "Where am I? Calming himself down, he repeated the question."
        spans = split_block(text, [(0, 11)])
        assert len(spans) == 2
        assert spans[0].is_emphasised
        assert not spans[1].is_emphasised

    def test_emphasised_span_is_inner_monologue(self) -> None:
        text = "Where am I? Calming himself down, he repeated the question."
        assert types(text, italics=[(0, 11)])[0] is SpanType.INNER_MONOLOGUE

    def test_trailing_narration_is_not_inner_monologue(self) -> None:
        text = "Where am I? Calming himself down, he repeated the question."
        assert types(text, italics=[(0, 11)])[1] is not SpanType.INNER_MONOLOGUE

    def test_no_emphasis_leaves_splitting_unchanged(self) -> None:
        text = "He said, “Speak.” Then he left."
        assert len(split_block(text, [])) == len(split_quoted(text))

    def test_emphasis_and_quotes_both_split(self) -> None:
        text = "He thought, “yes.” Truly? He wondered."
        spans = split_block(text, [(19, 26)])
        assert any(s.is_quoted for s in spans)
        assert any(s.is_emphasised for s in spans)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class TestDialogue:
    def test_quoted_speech_is_dialogue(self) -> None:
        assert SpanType.DIALOGUE in types("He said, “Elder, I have something to report.”")

    def test_narration_around_dialogue_is_not_dialogue(self) -> None:
        out = types("He said, “Speak.” The elder frowned.")
        assert out.count(SpanType.DIALOGUE) == 1


class TestInnerMonologue:
    @pytest.mark.parametrize(
        "text",
        [
            "He thought, “This one is shortsighted.”",
            "“So that is how it works,” he mused.",
            "“Impossible,” he sneered inwardly.",
            "“I see,” he said in his heart.",
            "“Truly?” he thought to himself.",
        ],
    )
    def test_thought_verbs_mark_reported_thought(self, text: str) -> None:
        """Quoted thought is speech-shaped but must not be voiced as speech."""
        assert SpanType.INNER_MONOLOGUE in types(text)

    def test_speech_without_a_thought_verb_stays_dialogue(self) -> None:
        assert SpanType.INNER_MONOLOGUE not in types("“Speak,” the elder said coldly.")

    def test_emphasis_beats_inference(self) -> None:
        """The translator marked it explicitly; every other cue is inference."""
        assert types("Where am I?", italics=[(0, 11)]) == [SpanType.INNER_MONOLOGUE]


class TestNarrationSubtypes:
    def test_action(self) -> None:
        assert types("He stretched out his arm and grabbed the blade.") == [
            SpanType.NARRATION_ACTION
        ]

    def test_description(self) -> None:
        assert types("A huge crimson ball appeared on the river surface.") == [
            SpanType.NARRATION_DESCRIPTION
        ]

    def test_exposition(self) -> None:
        """Kept in audio, skipped in panels -- so it must be separable."""
        assert types("It is said in legend that a river of time exists.") == [
            SpanType.NARRATION_EXPOSITION
        ]


class TestCrowdReactions:
    def test_a_run_of_short_exclamations_becomes_a_crowd(self) -> None:
        """Forcing a speaker onto each would invent attributions from nothing."""
        out = types("“Hmm?” “What Gu worm?” “Impossible!” “Incredible!”")
        assert out.count(SpanType.CROWD_REACTION) >= 3

    def test_a_single_exclamation_beside_narration_is_not_a_crowd(self) -> None:
        out = types("The elder frowned deeply and considered the matter at length.")
        assert SpanType.CROWD_REACTION not in out


class TestNonStoryBlocks:
    def test_system_window_becomes_one_span(self) -> None:
        b = Block(
            index=0,
            block_type=BlockType.SYSTEM_WINDOW,
            text="[ Level: 7 ]",
            system_fields={"Level": "7"},
        )
        spans = classify_block_spans(b, novel_id="t", chapter=1.0)
        assert [s.span_type for s in spans] == [SpanType.SYSTEM_WINDOW]

    def test_translator_note_is_non_diegetic(self) -> None:
        b = Block(index=0, block_type=BlockType.TRANSLATOR_NOTE, text="TL Note: gu = insect")
        spans = classify_block_spans(b, novel_id="t", chapter=1.0)
        assert [s.span_type for s in spans] == [SpanType.NON_DIEGETIC]


class TestSpanTypeProperties:
    def test_exposition_is_audio_only(self) -> None:
        assert not SpanType.NARRATION_EXPOSITION.is_renderable_visually
        assert SpanType.NARRATION_DESCRIPTION.is_renderable_visually

    def test_only_dialogue_is_spoken_aloud(self) -> None:
        assert SpanType.DIALOGUE.is_spoken_aloud
        assert not SpanType.INNER_MONOLOGUE.is_spoken_aloud


class TestChapterLevel:
    def test_ids_are_unique_and_ordered(self) -> None:
        chapter = Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[block("He walked.", index=0), block("She ran.", index=1)],
        )
        spans = classify_chapter(chapter)
        assert len({s.id for s in spans}) == len(spans)
        assert [s.block_index for s in spans] == [0, 1]


# ---------------------------------------------------------------------------
# Delivery markers -- non-negotiable #10
# ---------------------------------------------------------------------------


class TestDeliveryMarkers:
    def test_flat_markers_are_detected(self) -> None:
        markers = extract_delivery_markers("he said expressionlessly")
        assert markers[0].polarity is DeliveryPolarity.FLAT

    @pytest.mark.parametrize(
        ("text", "polarity"),
        [
            ("he shouted", DeliveryPolarity.HEIGHTENED),
            ("she whispered", DeliveryPolarity.HUSHED),
            ("he sneered", DeliveryPolarity.COLD),
            ("she smiled", DeliveryPolarity.WARM),
            ("he stammered", DeliveryPolarity.HESITANT),
        ],
    )
    def test_polarities(self, text: str, polarity: DeliveryPolarity) -> None:
        assert extract_delivery_markers(text)[0].polarity is polarity

    def test_multi_word_markers_are_not_truncated(self) -> None:
        markers = extract_delivery_markers("he replied in a low voice")
        assert markers[0].text == "in a low voice"

    def test_flat_wins_over_other_markers(self) -> None:
        """The canonical case: flat delivery inside a violent scene.

        A majority vote or an average would let the surrounding drama back in;
        the contrast between the flatness and the carnage is the effect.
        """
        markers = extract_delivery_markers("he said calmly, then roared at the corpse")
        assert dominant_polarity(markers) is DeliveryPolarity.FLAT

    def test_no_markers_yields_none(self) -> None:
        assert dominant_polarity(extract_delivery_markers("he said")) is None

    def test_markers_are_attached_to_narration_spans(self) -> None:
        spans = classify_block_spans(
            block("“Speak.” The elder answered coldly."), novel_id="t", chapter=1.0
        )
        narration = [s for s in spans if s.span_type is not SpanType.DIALOGUE]
        assert any("coldly" in m for s in narration for m in s.delivery_markers)
