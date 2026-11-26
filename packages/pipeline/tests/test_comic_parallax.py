"""Depth parallax: near pixels move more than far ones, and zero shift changes nothing."""

from __future__ import annotations

import pytest

pytest.importorskip("cv2")

import numpy as np
from echotales.pipeline.comic.parallax import parallax_warp
from PIL import Image


def _scene():
    rng = np.random.default_rng(4)
    img = Image.fromarray(rng.integers(0, 255, size=(60, 120, 3), dtype=np.uint8))
    depth = np.zeros((60, 120), dtype=np.float32)
    depth[:, 60:] = 1.0  # left half far, right half near
    return img, depth


def test_zero_shift_is_identity() -> None:
    img, depth = _scene()
    assert np.array_equal(np.asarray(parallax_warp(img, depth, 0.0)), np.asarray(img))


def test_near_half_moves_further_than_far_half() -> None:
    img, depth = _scene()
    out = np.asarray(parallax_warp(img, depth, 6.0)).astype(int)
    src = np.asarray(img).astype(int)

    def best_shift(sl: slice) -> int:
        errs = {s: np.abs(out[:, sl] - np.roll(src, s, axis=1)[:, sl]).mean() for s in range(-9, 10)}
        return min(errs, key=errs.get)

    far, near = best_shift(slice(15, 45)), best_shift(slice(75, 105))
    assert abs(near) > abs(far) and near != far


def test_depth_input_is_a_multiple_of_14_with_the_aspect_kept_and_needs_no_torchvision() -> None:
    """transformers' AutoImageProcessor demands torchvision, which the venv does not have; the preprocessing is
    ten lines of numpy, so it is done here (DPT rule: keep aspect, the scale nearer 1, sides multiples of 14)."""
    from echotales.pipeline.comic.parallax import prepare_depth_input

    arr = prepare_depth_input(Image.new("RGB", (1200, 1660), (255, 255, 255)))
    assert arr.shape[0] == 3 and arr.shape[1] % 14 == 0 and arr.shape[2] % 14 == 0
    assert abs(arr.shape[1] / arr.shape[2] - 1660 / 1200) < 0.03
    assert min(arr.shape[1:]) >= 518 - 14
    assert abs(arr[0, 0, 0] - (1 - 0.485) / 0.229) < 1e-4  # ImageNet normalisation of white
