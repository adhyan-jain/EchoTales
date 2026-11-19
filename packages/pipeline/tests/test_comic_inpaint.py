"""Clean plates: masked text is removed, everything else is left bit-identical; SRT from OCR text and voice timing."""

from __future__ import annotations

import numpy as np
import pytest
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
    pytest.importorskip("cv2")
    clean, lettered, mask = _gradient_with_text()
    out = CvInpainter().inpaint(lettered, mask)
    m = np.asarray(mask) > 0
    err = np.abs(np.asarray(out, dtype=int) - np.asarray(clean, dtype=int))[m].mean()
    assert err < 6, err
    assert np.array_equal(np.asarray(out)[~m], np.asarray(lettered)[~m])


def test_empty_mask_is_a_no_op_and_registry_knows_cv() -> None:
    pytest.importorskip("cv2")
    img = Image.new("RGB", (30, 30), (10, 20, 30))
    assert np.array_equal(np.asarray(CvInpainter().inpaint(img, Image.new("L", (30, 30), 0))), np.asarray(img))
    assert get_inpainter("cv").name == "cv"


def test_srt_uses_voice_timing_and_escapes_nothing_surprising() -> None:
    srt = srt_text([(0.0, 1.5, "Hello there."), (2.25, 4.0, "NO! Don't.")])
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,500\nHello there.\n")
    assert "2\n00:00:02,250 --> 00:00:04,000\nNO! Don't.\n" in srt


def _fake_lama(tmp_path):
    """A TorchScript stand-in with big-lama's call signature (image, mask) -> image: it paints masked pixels mid-grey."""
    torch = pytest.importorskip("torch")

    class Fill(torch.nn.Module):
        def forward(self, img, mask):
            assert img.shape[-1] % 8 == 0 and img.shape[-2] % 8 == 0  # the real net needs multiples of 8
            return img * (1 - mask) + 0.5 * mask

    path = tmp_path / "fake-lama.pt"
    torch.jit.script(Fill()).save(str(path))
    return path


def test_lama_fills_only_masked_pixels_on_a_size_that_is_not_a_multiple_of_eight(tmp_path) -> None:
    from echotales.pipeline.comic.inpaint import LamaInpainter

    clean, lettered, mask = _gradient_with_text()
    lettered = lettered.crop((0, 0, 197, 117))
    mask = mask.crop((0, 0, 197, 117))
    out = LamaInpainter(_fake_lama(tmp_path), device="cpu").inpaint(lettered, mask)
    m = np.asarray(mask) > 0
    assert out.size == (197, 117)
    assert np.array_equal(np.asarray(out)[~m], np.asarray(lettered)[~m])
    assert abs(int(np.asarray(out)[60, 100, 0]) - 128) <= 1


def test_lama_runs_one_window_per_distant_region_not_the_whole_page(tmp_path) -> None:
    """A tall webtoon strip with two small bubbles must not be one huge tensor."""
    from echotales.pipeline.comic.inpaint import LamaInpainter

    inp = LamaInpainter(_fake_lama(tmp_path), device="cpu")
    seen = []
    real = inp.model
    inp.model = lambda img, msk: (seen.append(tuple(img.shape[-2:])), real(img, msk))[1]
    img = Image.new("RGB", (300, 3000), (90, 90, 90))
    mask = Image.new("L", (300, 3000), 0)
    d = ImageDraw.Draw(mask)
    d.rectangle([100, 100, 160, 140], fill=255)
    d.rectangle([100, 2700, 160, 2740], fill=255)
    out = inp.inpaint(img, mask)
    assert len(seen) == 2 and all(h < 600 for h, _ in seen), seen
    assert np.asarray(out)[120, 130, 0] == 128 and np.asarray(out)[1500, 130, 0] == 90


def test_auto_prefers_lama_when_weights_exist_and_falls_back_to_cv(tmp_path) -> None:
    from echotales.pipeline.comic import inpaint

    assert inpaint.get_inpainter("auto", weights=tmp_path / "missing.pt").name == "cv"  # no cv2 needed to pick it
    pytest.importorskip("torch")
    assert inpaint.get_inpainter("auto", weights=_fake_lama(tmp_path), device="cpu").name == "lama"
