"""Clean plates: masked text is removed, everything else is left bit-identical; SRT from OCR text and voice timing."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from echotales.pipeline.comic.inpaint import CvInpainter, get_inpainter, srt_text


def _gradient_with_text() -> tuple[Image.Image, Image.Image, Image.Image]:
    x = np.linspace(40, 200, 200, dtype=np.uint8)
    base = np.tile(x, (120, 1))
    clean = Image.fromarray(np.stack([base, base, base], axis=2))
    lettered = clean.copy()
    ImageDraw.Draw(lettered).rectangle([80, 50, 120, 70], fill=(0, 0, 0))
    mask = Image.new("L", (200, 120), 0)
    ImageDraw.Draw(mask).rectangle([76, 46, 124, 74], fill=255)
    return clean, lettered, mask


def test_cv_inpaint_restores_a_smooth_background_and_leaves_the_rest_alone() -> None:
    clean, lettered, mask = _gradient_with_text()
    out = CvInpainter().inpaint(lettered, mask)
    m = np.asarray(mask) > 0
    err = np.abs(np.asarray(out, dtype=int) - np.asarray(clean, dtype=int))[m].mean()
    assert err < 6, err
    assert np.array_equal(np.asarray(out)[~m], np.asarray(lettered)[~m])


def test_empty_mask_is_a_no_op_and_registry_knows_cv() -> None:
    img = Image.new("RGB", (30, 30), (10, 20, 30))
    assert np.array_equal(np.asarray(CvInpainter().inpaint(img, Image.new("L", (30, 30), 0))), np.asarray(img))
    assert get_inpainter("cv").name == "cv"


def test_srt_uses_voice_timing_and_escapes_nothing_surprising() -> None:
    srt = srt_text([(0.0, 1.5, "Hello there."), (2.25, 4.0, "NO! Don't.")])
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,500\nHello there.\n")
    assert "2\n00:00:02,250 --> 00:00:04,000\nNO! Don't.\n" in srt
