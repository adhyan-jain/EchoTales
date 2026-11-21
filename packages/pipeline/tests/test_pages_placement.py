"""4.185: bubbles stay off the subject, move to the gutter instead of shrinking, and the webtoon strip gives them room."""

from __future__ import annotations

import numpy as np
from echotales.pipeline.pages.composer import ComposerPanel, PanelRole, compose_pages
from echotales.pipeline.pages.lettering import (
    MIN_FONT_PX,
    LetterItem,
    LetterKind,
    _font,
    _wrap,
    letter_panel,
    sentence_case,
)
from echotales.pipeline.pages.placement import estimate_subject, speaker_point, subject_share
from PIL import Image, ImageDraw

W, H = 800, 1000
RECT = (0, 0, W, H)
BLOB = (180, 300, 620, 760)  # a bright skin-coloured "character" in the middle


def _scene(blob: tuple[int, int, int, int] | None = BLOB) -> Image.Image:
    img = Image.new("RGB", (W, H), (40, 60, 90))
    if blob:
        ImageDraw.Draw(img).rectangle(blob, fill=(235, 190, 160))
    return img


def _speech(i: str, text: str, pos: str | None = None) -> LetterItem:
    return LetterItem(i, LetterKind.SPEECH, text, pos)


def _hit(box: tuple[int, int, int, int], blob: tuple[int, int, int, int]) -> bool:
    return not (box[2] <= blob[0] or blob[2] <= box[0] or box[3] <= blob[1] or blob[3] <= box[1])


def test_bubble_avoids_a_bright_subject_blob() -> None:
    img = _scene()
    items = [_speech("a", "Hello there, how are you today?", "left"), _speech("b", "Fine, thank you for asking me.", "right")]
    res = letter_panel(img, RECT, items, rtl=False)
    assert len(res.placed) == 2
    for p in res.placed:
        assert not _hit(p.box, BLOB), p.box


def test_old_behaviour_would_have_covered_it() -> None:
    # The estimate sees the blob: a box on it is reported as subject, a box in the corner is not.
    smap = estimate_subject(_scene())
    assert subject_share([(260, 400, 540, 560)], RECT, smap) > 0.8
    assert subject_share([(10, 10, 200, 100)], RECT, smap) < 0.05


def test_text_that_has_no_clear_spot_goes_to_the_gutter_not_a_smaller_font() -> None:
    # Everything but a thin strip is subject, so there is nowhere clear on the picture.
    img = Image.new("RGB", (W, H + 400), (255, 255, 255))
    img.paste(_scene((0, 0, W, H)), (0, 0))
    res = letter_panel(img, RECT, [_speech("a", "I will not be moved by words alone.", "left")], rtl=False, gutter_below=400)
    p = res.placed[0]
    assert p.in_gutter and p.box[1] >= H
    assert p.font_size >= MIN_FONT_PX
    assert res.gutter_used >= p.box[3] - H
    assert p.tail_tip is not None and p.tail_tip[1] < H


def test_without_a_gutter_the_bubble_stays_on_the_least_harmful_spot() -> None:
    res = letter_panel(_scene((0, 0, W, H)), RECT, [_speech("a", "Hello", "left")], rtl=False)
    assert not res.placed[0].in_gutter and res.gutter_used == 0


def test_font_never_drops_below_the_legibility_floor_on_a_real_size_panel() -> None:
    long = "This is a long line of dialogue that goes on for quite a while before it finally stops talking."
    res = letter_panel(_scene(), RECT, [_speech("a", long, "left")], rtl=False)
    assert res.placed and min(p.font_size for p in res.placed) >= MIN_FONT_PX


def test_tail_points_at_the_face_and_stops_short_of_it() -> None:
    img = _scene()
    p = letter_panel(img, RECT, [_speech("a", "Hello", None)], rtl=False).placed[0]
    cx, cy = (BLOB[0] + BLOB[2]) / 2, (BLOB[1] + BLOB[3]) / 2
    face = speaker_point(estimate_subject(img), RECT, None)
    assert face is not None and abs(face[0] - cx) < 80 and abs(face[1] - cy) < 80
    assert p.tail_tip is not None
    # Nearer the speaker than the bubble is, and not buried in the middle of the face.
    box_c = ((p.box[0] + p.box[2]) / 2, (p.box[1] + p.box[3]) / 2)
    assert np.hypot(p.tail_tip[0] - cx, p.tail_tip[1] - cy) < np.hypot(box_c[0] - cx, box_c[1] - cy)


def test_wrap_balances_lines_instead_of_leaving_an_orphan() -> None:
    font = _font(False, 30)
    text = "Fang Yuan quietly hand over the Spring Autumn Cicada now"
    lines = _wrap(text, font, 560)
    widths = [font.getlength(x) for x in lines]
    assert len(lines) >= 2 and min(widths) > 0.5 * max(widths)


def test_sentence_case_only_touches_all_caps() -> None:
    assert sentence_case("GET OUT OF HERE!") == "Get out of here!"
    assert sentence_case("Get out of here!") == "Get out of here!"
    assert sentence_case("OK") == "OK"


def test_webtoon_scene_change_gets_a_bigger_gap_and_a_band() -> None:
    p = lambda i, scene, role=PanelRole.SCENE, gap=0: ComposerPanel(f"p{i}", role, 832, 1216, scene_index=scene, letter_gap=gap)  # noqa: E731
    layout = compose_pages([p(0, 0), p(1, 0), p(2, 1)], "webtoon")[0]
    a, b, c = layout.panels
    same, change = b.y - (a.y + a.h), c.y - (b.y + b.h)
    assert change > 3 * same
    assert [(x.above, x.below) for x in layout.bands] == [("p1", "p2")]


def test_webtoon_gap_grows_to_hold_the_lettering_below_a_panel() -> None:
    p = lambda i, gap: ComposerPanel(f"p{i}", PanelRole.SCENE, 832, 1216, letter_gap=gap)  # noqa: E731
    tight = compose_pages([p(0, 0), p(1, 0)], "webtoon")[0]
    roomy = compose_pages([p(0, 300), p(1, 0)], "webtoon")[0]
    gap = lambda lay: lay.panels[1].y - (lay.panels[0].y + lay.panels[0].h)  # noqa: E731
    assert gap(roomy) >= 300 and gap(tight) < 100


def test_webtoon_splash_is_taller_than_a_normal_panel() -> None:
    layout = compose_pages(
        [ComposerPanel("a", PanelRole.SCENE, 832, 1216), ComposerPanel("b", PanelRole.SPLASH, 832, 1216)], "webtoon"
    )[0]
    assert layout.panels[1].h > layout.panels[0].h
