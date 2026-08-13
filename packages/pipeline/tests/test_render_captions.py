"""On-screen text, timed to the line being spoken.

The reference edits this format is modelled on put one line of the novel's
prose on screen and hold it -- the picture is the backdrop, the sentence is
what the viewer came for. These pin the two properties that make that work:
the timing is measured rather than estimated, and arbitrary novel prose
survives the trip into a subtitle file intact.
"""

from __future__ import annotations

from dataclasses import dataclass

from echotales.pipeline.render.captions import (
    MAX_CHARS_PER_CARD,
    build_captions,
    write_ass,
)


@dataclass
class _Line:
    span_id: str
    span_type: str
    text: str
    speaker_label: str = ""


class TestTiming:
    def test_cards_follow_the_voice_track(self) -> None:
        """Each line starts where the previous one's audio ended: the cards
        are in sync with the speech, not with an estimate of reading time."""
        lines = [
            _Line("s1", "NARRATION_ACTION", "He walked."),
            _Line("s2", "DIALOGUE", "Hand it over.", "Bai Ning Bing"),
            _Line("s3", "NARRATION_ACTION", "Rain fell."),
        ]
        caps = build_captions(lines, {"s1": 2.0, "s2": 3.0, "s3": 1.5})
        assert [(c.start, c.end) for c in caps] == [(0.0, 2.0), (2.0, 5.0), (5.0, 6.5)]

    def test_a_line_with_no_measured_audio_is_skipped(self) -> None:
        """An unsynced caption is worse than an absent one -- it lands over
        the wrong picture and desyncs everything after it."""
        lines = [
            _Line("s1", "NARRATION_ACTION", "He walked."),
            _Line("s2", "NARRATION_ACTION", "Unrendered."),
            _Line("s3", "NARRATION_ACTION", "Rain fell."),
        ]
        caps = build_captions(lines, {"s1": 2.0, "s3": 1.5})
        assert [c.text for c in caps] == ["He walked.", "Rain fell."]
        # ...and the survivors keep the clock they would have had.
        assert caps[1].start == 2.0

    def test_a_card_never_outlives_its_own_line(self) -> None:
        """A short clip with long text must not bleed over the next line."""
        caps = build_captions(
            [_Line("s1", "NARRATION_ACTION", "A short line."), _Line("s2", "DIALOGUE", "Next.")],
            {"s1": 0.4, "s2": 2.0},
        )
        assert caps[0].end <= 0.4 + 1e-9
        assert caps[1].start == 0.4


class TestCards:
    def test_long_narration_becomes_several_cards(self) -> None:
        """A wall of text over a portrait is what makes an edit look
        automated; the reels never show more than a couple of lines."""
        text = (
            "Fang Yuan was in deep green robes that had been torn to shreds. "
            "His hair was disheveled and blood flowed from numerous wounds. "
            "He stood silent as a sculpture, and the rain did not stop."
        )
        caps = build_captions([_Line("s1", "NARRATION_ACTION", text)], {"s1": 9.0})
        assert len(caps) > 1
        assert all(len(c.text) <= MAX_CHARS_PER_CARD for c in caps)
        # The line's own airtime is divided, never extended.
        assert caps[0].start == 0.0
        assert caps[-1].end <= 9.0 + 1e-9

    def test_cards_split_between_sentences(self) -> None:
        """Splitting mid-sentence reads as a failure; splitting between them
        reads as pacing."""
        text = "He raised his hand. " * 12
        caps = build_captions([_Line("s1", "NARRATION_ACTION", text)], {"s1": 12.0})
        for cap in caps:
            assert cap.text.endswith(".")

    def test_dialogue_is_marked_and_attributed(self) -> None:
        caps = build_captions(
            [_Line("s1", "DIALOGUE", "Hand it over.", "Bai Ning Bing")], {"s1": 2.0}
        )
        assert caps[0].is_dialogue
        assert caps[0].speaker == "Bai Ning Bing"

    def test_narration_can_be_suppressed(self) -> None:
        lines = [
            _Line("s1", "NARRATION_ACTION", "He walked."),
            _Line("s2", "DIALOGUE", "Hand it over.", "Bai"),
        ]
        caps = build_captions(lines, {"s1": 2.0, "s2": 2.0}, include_narration=False)
        assert [c.text for c in caps] == ["Hand it over."]
        # Dropping narration must not shift dialogue off the voice track.
        assert caps[0].start == 2.0


class TestAssOutput:
    def test_prose_with_filter_syntax_survives(self, tmp_path) -> None:
        """Novel prose is full of apostrophes, colons, commas and braces --
        all of which are syntax somewhere in ffmpeg. The ASS file is what
        keeps them out of a filter-graph string."""
        text = "It's here: {the demon}, he said -- 50% of it, at least."
        caps = build_captions([_Line("s1", "DIALOGUE", text, "Elder")], {"s1": 4.0})
        path = write_ass(caps, tmp_path / "c.ass", width=1080, height=1920)
        body = path.read_text(encoding="utf-8")

        assert "PlayResX: 1080" in body and "PlayResY: 1920" in body
        # Braces are ASS override syntax and must be escaped, not dropped.
        assert "\\{" in body and "\\}" in body
        assert "It's here" in body

    def test_style_scales_with_the_frame(self, tmp_path) -> None:
        tall = write_ass(
            build_captions([_Line("s1", "DIALOGUE", "Hi", "A")], {"s1": 1.0}),
            tmp_path / "tall.ass", width=1080, height=1920,
        ).read_text()
        short = write_ass(
            build_captions([_Line("s1", "DIALOGUE", "Hi", "A")], {"s1": 1.0}),
            tmp_path / "short.ass", width=1280, height=720,
        ).read_text()
        assert tall != short

    def test_timestamps_are_ass_formatted(self, tmp_path) -> None:
        caps = build_captions([_Line("s1", "DIALOGUE", "Hi", "A")], {"s1": 3661.5})
        body = write_ass(caps, tmp_path / "c.ass", width=1080, height=1920).read_text()
        assert "0:00:00.00,1:01:01.50" in body
