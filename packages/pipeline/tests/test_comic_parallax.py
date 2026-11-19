"""Depth parallax: near pixels move more than far ones, and zero shift changes nothing."""

from __future__ import annotations

import pytest

pytest.importorskip("cv2")

import numpy as np
from PIL import Image

from echotales.pipeline.comic.parallax import parallax_warp


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
