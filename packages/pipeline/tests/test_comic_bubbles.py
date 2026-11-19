"""Bubble grouping, kind, tail and speaker clustering on synthetic panels (OCR is injected, not run)."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from echotales.pipeline.comic.bubbles import cluster_speakers, detect_bubbles
from echotales.pipeline.comic.ocr import TextLine
from echotales.pipeline.comic.panels import Panel


def _scene() -> tuple[Image.Image, list[Panel]]:
    # One 600x400 panel of noisy dark art with a white speech ellipse (tail down-left) and a pale caption box.
    rng = np.random.default_rng(5)
    arr = rng.integers(10, 90, size=(400, 600, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    d.ellipse([300, 40, 520, 140], fill=(250, 250, 250))
    d.polygon([(340, 120), (380, 130), (300, 200)], fill=(250, 250, 250))  # tail, tip at (300, 200)
    d.rectangle([20, 20, 200, 70], fill=(245, 235, 200))
    return img, [Panel(0, (0, 0, 600, 400))]


def _lines() -> list[TextLine]:
    return [
        TextLine((340, 65, 480, 85), "Hello there", 0.99),
        TextLine((350, 88, 470, 108), "friend.", 0.99),
        TextLine((30, 32, 190, 58), "Meanwhile", 0.99),
        TextLine((420, 300, 520, 340), "BOOM", 0.9),  # lettering straight over art: no bubble fill
    ]


def test_lines_group_into_bubbles_and_kinds_are_told_apart() -> None:
    img, panels = _scene()
    got = detect_bubbles(img, _lines(), panels)
    by_text = {b.text: b for b in got}
    assert set(by_text) == {"Hello there friend.", "Meanwhile", "BOOM"}
    assert by_text["Hello there friend."].kind == "speech"
    assert by_text["Meanwhile"].kind == "narration"
    assert by_text["BOOM"].kind == "sfx"


def test_tail_tip_is_found_for_speech_only() -> None:
    img, panels = _scene()
    by_text = {b.text: b for b in detect_bubbles(img, _lines(), panels)}
    tip = by_text["Hello there friend."].tail
    assert tip is not None and abs(tip[0] - 300) < 25 and abs(tip[1] - 200) < 25
    assert by_text["Meanwhile"].tail is None


def test_reading_order_top_to_bottom_then_by_direction() -> None:
    img = Image.new("RGB", (600, 400), (30, 30, 30))
    d = ImageDraw.Draw(img)
    for box in ([60, 20, 240, 90], [330, 22, 540, 92], [60, 200, 240, 270]):
        d.rectangle(box, fill=(250, 250, 250))
    lines = [TextLine((70, 40, 230, 70), "B", 0.9), TextLine((340, 42, 530, 72), "A", 0.9),
             TextLine((70, 220, 230, 250), "C", 0.9)]
    panels = [Panel(0, (0, 0, 600, 400))]
    assert [b.text for b in detect_bubbles(img, lines, panels)] == ["B", "A", "C"]
    assert [b.text for b in detect_bubbles(img, lines, panels, rtl=True)] == ["A", "B", "C"]


def test_speaker_clusters_split_by_what_the_tail_points_at() -> None:
    red = np.tile(np.array([200, 30, 30], dtype=float), 8)
    red2 = red + 3
    blue = np.tile(np.array([30, 30, 200], dtype=float), 8)
    labels = cluster_speakers([red, blue, red2, blue + 2], threshold=0.2)
    assert labels[0] == labels[2] and labels[1] == labels[3] and labels[0] != labels[1]
    assert cluster_speakers([None, red], threshold=0.2)[0] is None


def test_coloured_lettering_in_a_bubble_coloured_area_is_an_effect_not_speech() -> None:
    img = Image.new("RGB", (400, 200), (240, 240, 230))
    d = ImageDraw.Draw(img)
    d.text((150, 80), "SHSH", fill=(220, 90, 10))
    for dx in range(4):
        d.text((150 + dx, 81), "SHSH", fill=(220, 90, 10))
    got = detect_bubbles(img, [TextLine((148, 78, 200, 96), "SHSH", 0.9)], [Panel(0, (0, 0, 400, 200))])
    assert got[0].kind == "sfx"
