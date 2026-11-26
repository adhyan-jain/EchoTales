"""M1 step 2: lettering is done by code. Bubbles, tails, shout style, and text that never vanishes silently."""

from __future__ import annotations

from echotales.pipeline.pages.lettering import LetterItem, LetterKind, letter_panel
from PIL import Image

RECT = (0, 0, 600, 500)


def _canvas() -> Image.Image:
    return Image.new("RGB", (600, 500), (90, 120, 160))


def _speech(span_id: str, text: str, pos: str | None = None, *, shouted: bool = False) -> LetterItem:
    return LetterItem(span_id, LetterKind.SPEECH, text, pos, shouted)


def test_tail_points_toward_the_speaker_position() -> None:
    left = letter_panel(_canvas(), RECT, [_speech("a", "Hello there", "left")], rtl=False).placed[0]
    right = letter_panel(_canvas(), RECT, [_speech("a", "Hello there", "right")], rtl=False).placed[0]
    assert left.tail_tip is not None and right.tail_tip is not None
    assert left.tail_tip[0] < 300 < right.tail_tip[0]
    for p in (left, right):
        assert 0 <= p.tail_tip[0] <= 600 and 0 <= p.tail_tip[1] <= 500


def test_unknown_speaker_position_points_to_the_centre() -> None:
    tip = letter_panel(_canvas(), RECT, [_speech("a", "Hello", None)], rtl=False).placed[0].tail_tip
    assert tip is not None and abs(tip[0] - 300) < 40


def test_narration_has_no_tail_and_thought_has_a_tail() -> None:
    items = [
        LetterItem("n", LetterKind.NARRATION, "The night was long."),
        LetterItem("t", LetterKind.THOUGHT, "What now?", "left"),
    ]
    res = letter_panel(_canvas(), RECT, items, rtl=False)
    by_id = {p.span_id: p for p in res.placed}
    assert by_id["n"].tail_tip is None
    assert by_id["t"].tail_tip is not None


def test_shouted_style_is_chosen_from_the_flag() -> None:
    calm = letter_panel(_canvas(), RECT, [_speech("a", "Stop", "left")], rtl=False).placed[0]
    loud = letter_panel(_canvas(), RECT, [_speech("a", "Stop", "left", shouted=True)], rtl=False).placed[0]
    assert (calm.style, loud.style) == ("speech", "shout")


def test_bubbles_do_not_overlap() -> None:
    items = [_speech(f"s{i}", "A fairly long line of speech here", "left" if i % 2 else "right") for i in range(4)]
    res = letter_panel(_canvas(), RECT, items, rtl=False)
    boxes = [p.box for p in res.placed]
    assert len(boxes) == 4
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_text_is_drawn_into_the_panel() -> None:
    img = _canvas()
    before = img.copy()
    letter_panel(img, RECT, [_speech("a", "Hello", "left")], rtl=False)
    assert img.tobytes() != before.tobytes()


def test_long_text_shrinks_then_splits_and_keeps_every_word() -> None:
    text = " ".join(f"word{i}" for i in range(50))
    res = letter_panel(Image.new("RGB", (300, 240)), (0, 0, 300, 240), [_speech("a", text, "left")], rtl=False)
    drawn = " ".join(p.text for p in res.placed).split()
    lost = " ".join(o.lost_text for o in res.overflow).split()
    assert [o.kind for o in res.overflow] == ["split"] and len(res.placed) == 2
    assert set(text.split()) <= set(drawn) | set(lost)


def test_text_that_cannot_fit_is_truncated_and_recorded() -> None:
    text = " ".join(f"word{i}" for i in range(400))
    res = letter_panel(Image.new("RGB", (200, 150)), (0, 0, 200, 150), [_speech("a", text, "left")], rtl=False)
    kinds = {o.kind for o in res.overflow}
    assert "truncated" in kinds
    trunc = next(o for o in res.overflow if o.kind == "truncated")
    assert trunc.span_id == "a" and trunc.lost_text
    assert any(p.text.endswith("…") for p in res.placed)


def test_an_item_with_no_room_is_reported_unplaced() -> None:
    items = [_speech(f"s{i}", "Some words that take space in the bubble", "left") for i in range(40)]
    res = letter_panel(Image.new("RGB", (200, 150)), (0, 0, 200, 150), items, rtl=False)
    unplaced = {o.span_id for o in res.overflow if o.kind == "unplaced"}
    placed = {p.span_id for p in res.placed}
    assert unplaced and {i.span_id for i in items} <= placed | unplaced


def test_sfx_layer_reuses_the_manga_overlay() -> None:
    img = _canvas()
    before = img.copy()
    res = letter_panel(img, RECT, [LetterItem("x", LetterKind.SFX, "BOOM")], rtl=False)
    assert img.tobytes() != before.tobytes()
    assert res.placed and res.placed[0].style == "sfx"


def test_expanded_letter_kinds_render_distinct_styles() -> None:
    styles = [
        (LetterKind.MEMORY, "memory"),
        (LetterKind.FLASHBACK, "flashback"),
        (LetterKind.TIME_SKIP, "time_skip"),
        (LetterKind.POETRY, "poetry"),
        (LetterKind.SYSTEM_INTERFACE, "system_interface"),
        (LetterKind.CROWD_COLLECTIVE, "crowd_collective"),
    ]
    for kind, expected_style in styles:
        img = _canvas()
        before = img.copy()
        item = LetterItem("k1", kind, "Test text content for style verification", "left")
        res = letter_panel(img, RECT, [item], rtl=False)
        assert len(res.placed) == 1
        assert res.placed[0].style == expected_style
        assert img.tobytes() != before.tobytes()

