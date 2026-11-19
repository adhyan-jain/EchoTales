"""understand_pages: pages -> panels -> ordered bubbles -> speaker clusters, JSON round trip, text masks."""

from __future__ import annotations

import pytest

pytest.importorskip("scipy")

import numpy as np
from PIL import Image, ImageDraw

from echotales.pipeline.comic.ingest import PageImage
from echotales.pipeline.comic.ocr import TextLine
from echotales.pipeline.comic.understand import ComicUnderstanding, understand_pages


class FakeOcr:
    name = "fake"

    def __init__(self, lines):
        self.lines = lines

    def read(self, image):
        return self.lines


def _page():
    rng = np.random.default_rng(7)
    arr = np.full((700, 600, 3), 255, dtype=np.uint8)
    arr[20:320, 20:580] = rng.integers(10, 90, size=(300, 560, 3), dtype=np.uint8)
    arr[360:680, 20:580] = rng.integers(10, 90, size=(320, 560, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    d.ellipse([300, 50, 520, 150], fill=(250, 250, 250))
    d.polygon([(340, 130), (380, 140), (300, 215)], fill=(250, 250, 250))
    d.rectangle([40, 380, 260, 430], fill=(245, 235, 200))
    return img


LINES = [TextLine((340, 75, 480, 95), "Hello", 0.99), TextLine((350, 98, 470, 118), "there.", 0.99),
         TextLine((50, 392, 250, 418), "Later that night", 0.99)]


def test_understanding_orders_bubbles_and_round_trips_json(tmp_path):
    und = understand_pages([PageImage(0, "p1.png", _page())], FakeOcr(LINES), out_dir=tmp_path)
    page = und.pages[0]
    assert [len(p.bubbles) for p in page.panels] == [1, 1]
    flat = und.bubbles()
    assert [b.text for b in flat] == ["Hello there.", "Later that night"]
    assert [b.kind for b in flat] == ["speech", "narration"]
    assert flat[0].speaker == "Character A" and flat[1].speaker is None  # narration has no speaker
    again = ComicUnderstanding.from_dict(und.to_dict())
    assert [b.text for b in again.bubbles()] == ["Hello there.", "Later that night"]
    assert again.pages[0].panels[0].box == page.panels[0].box


def test_text_mask_covers_bubbles_and_is_written(tmp_path):
    und = understand_pages([PageImage(0, "p1.png", _page())], FakeOcr(LINES), out_dir=tmp_path)
    mask = np.asarray(Image.open(tmp_path / und.pages[0].mask_file))
    assert mask[100, 400] > 0 and mask[400, 100] > 0  # inside both bubbles
    assert mask[250, 100] == 0  # open art is untouched


def test_sound_effects_stay_in_the_clean_plate_by_default(tmp_path):
    """An effect is painted into the art and is neither voiced nor subtitled; a rectangle over it only destroys art
    (Pepper&Carrot SPLASH lost its spray). `mask_sfx=True` removes them, all of them."""
    sfx = TextLine((60, 600, 200, 640), "SPLASH", 0.99)  # on open art: no bubble fill, so it is an effect
    und = understand_pages([PageImage(0, "p1.png", _page())], FakeOcr([*LINES, sfx]), out_dir=tmp_path)
    assert [b.kind for b in und.bubbles()] == ["speech", "narration", "sfx"]
    mask = np.asarray(Image.open(tmp_path / und.pages[0].mask_file))
    assert mask[620, 100] == 0 and mask[100, 400] > 0
    und = understand_pages([PageImage(0, "p1.png", _page())], FakeOcr([*LINES, sfx]), out_dir=tmp_path, mask_sfx=True)
    assert np.asarray(Image.open(tmp_path / und.pages[0].mask_file))[620, 100] > 0


def test_a_bubble_that_leaked_into_same_coloured_art_does_not_mask_the_art(tmp_path):
    img = _page()
    ImageDraw.Draw(img).rectangle([300, 156, 420, 300], fill=(250, 250, 250))  # a pale window under the bubble
    und = understand_pages([PageImage(0, "p1.png", img)], FakeOcr(LINES), out_dir=tmp_path)
    mask = np.asarray(Image.open(tmp_path / und.pages[0].mask_file))
    assert mask[100, 400] > 0 and mask[290, 350] == 0
