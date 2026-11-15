"""The clip quality gate: SSIM against known values, then real decoded clips that must pass or be rejected."""

from __future__ import annotations

import shutil

import numpy as np
import pytest
from _anime_helpers import drifting_embedder, same_content_embedder, write_mp4
from echotales.pipeline.video import clip_gate as g
from PIL import Image

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def _texture(seed: int, w: int = 64, h: int = 96) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.asarray(
        Image.fromarray(rng.integers(0, 256, (h // 8, w // 8, 3), dtype=np.uint8)).resize((w, h), Image.NEAREST)
    )


def _motion(start: np.ndarray, end: np.ndarray, n: int) -> list[np.ndarray]:
    s, e = start.astype(np.float32), end.astype(np.float32)  # uint8 * int would wrap
    return [(s * (1 - i / (n - 1)) + e * (i / (n - 1))).astype(np.uint8) for i in range(n)]


class TestSsim:
    def test_identical_images_score_one(self) -> None:
        a = np.random.default_rng(0).uniform(0, 255, (40, 40)).astype(np.float32)
        assert g.ssim(a, a) == pytest.approx(1.0)

    def test_constant_images_follow_the_luminance_term(self) -> None:
        # With no variance the structure terms cancel and SSIM = (2*a*b + C1) / (a^2 + b^2 + C1).
        a, b = np.full((20, 20), 100.0), np.full((20, 20), 200.0)
        c1 = (0.01 * 255) ** 2
        assert g.ssim(a, b) == pytest.approx((2 * 100 * 200 + c1) / (100**2 + 200**2 + c1))

    def test_matches_scikit_image_when_it_is_installed(self) -> None:
        skimage = pytest.importorskip("skimage.metrics")
        rng = np.random.default_rng(1)
        a = rng.uniform(0, 255, (50, 60)).astype(np.float32)
        b = np.clip(a + rng.normal(0, 25, a.shape), 0, 255).astype(np.float32)
        assert g.ssim(a, b) == pytest.approx(skimage.structural_similarity(a, b, data_range=255), abs=1e-4)

    def test_noise_scores_far_below_a_copy(self) -> None:
        rng = np.random.default_rng(2)
        a = rng.uniform(0, 255, (50, 50)).astype(np.float32)
        assert g.ssim(a, rng.uniform(0, 255, (50, 50)).astype(np.float32)) < 0.1

    def test_rejects_mismatched_or_tiny_inputs(self) -> None:
        with pytest.raises(ValueError, match="shape"):
            g.ssim(np.zeros((10, 10)), np.zeros((10, 11)))
        with pytest.raises(ValueError, match="smaller"):
            g.ssim(np.zeros((5, 5)), np.zeros((5, 5)))


@needs_ffmpeg
class TestGateClip:
    def _gate(self, frames, tmp_path, start, end=None, expected=None, embedder=None):
        clip = write_mp4(frames, tmp_path / "c.mp4")
        return g.gate_clip(
            clip, Image.fromarray(start), Image.fromarray(end) if end is not None else None,
            expected_frames=expected or len(frames), width=64, height=96, embedder=embedder or same_content_embedder,
        )

    def test_clean_motion_passes_with_its_scores_recorded(self, tmp_path) -> None:
        a, b = _texture(1), _texture(2)
        r = self._gate(_motion(a, b, 33), tmp_path, a, b)
        assert r.passed, r.reasons
        assert r.start_ssim > 0.9 and r.end_ssim > 0.9
        assert r.mean_diff > g.MIN_MOTION and r.spike_ratio < g.MAX_SPIKE_RATIO and r.frames == 33

    def test_a_still_image_is_rejected(self, tmp_path) -> None:
        a = _texture(1)
        r = self._gate([a] * 25, tmp_path, a)
        assert not r.passed and any(x.startswith("still") for x in r.reasons)

    def test_a_garbled_jump_is_rejected(self, tmp_path) -> None:
        a, b = _texture(1), _texture(2)
        frames = _motion(a, b, 49)
        frames[24] = np.random.default_rng(3).integers(0, 256, a.shape, dtype=np.uint8)
        r = self._gate(frames, tmp_path, a)
        assert not r.passed and any(x.startswith("jump") for x in r.reasons)

    def test_landing_on_the_wrong_end_frame_is_rejected(self, tmp_path) -> None:
        a, b, other = _texture(1), _texture(2), _texture(9)
        r = self._gate(_motion(a, b, 33), tmp_path, a, other)
        assert not r.passed and any(x.startswith("end frame") for x in r.reasons)

    def test_starting_on_a_different_picture_is_rejected(self, tmp_path) -> None:
        a, b = _texture(1), _texture(2)
        r = self._gate(_motion(b, a, 33), tmp_path, a)
        assert not r.passed and any(x.startswith("start frame") for x in r.reasons)

    def test_wrong_length_is_rejected(self, tmp_path) -> None:
        a, b = _texture(1), _texture(2)
        r = self._gate(_motion(a, b, 33), tmp_path, a, expected=41)
        assert not r.passed and any(x.startswith("length") for x in r.reasons)

    def test_an_undecodable_file_fails_closed(self, tmp_path) -> None:
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(b"not a video")
        r = g.gate_clip(bad, Image.fromarray(_texture(1)), None, expected_frames=9, width=64, height=96)
        assert not r.passed and r.reasons[0].startswith("gate could not run")

    def test_a_missing_file_fails_closed(self, tmp_path) -> None:
        r = g.gate_clip(tmp_path / "none.mp4", Image.fromarray(_texture(1)), None, expected_frames=9, width=64, height=96)
        assert not r.passed

    def test_content_drift_is_rejected_with_its_scores(self, tmp_path) -> None:
        a, b = _texture(1), _texture(2)
        r = self._gate(_motion(a, b, 33), tmp_path, a, b, embedder=drifting_embedder)
        assert not r.passed and any(x.startswith("content drift") for x in r.reasons)
        assert r.drift_min == 0.0 and r.drift_last == 0.0

    def test_no_drift_records_similarity_one(self, tmp_path) -> None:
        a, b = _texture(1), _texture(2)
        r = self._gate(_motion(a, b, 33), tmp_path, a, b)
        assert r.passed and r.drift_min == pytest.approx(1.0, abs=1e-3)

    def test_an_embedder_that_cannot_run_rejects_the_clip(self, tmp_path) -> None:
        def broken(images):
            raise RuntimeError("no CLIP weights")

        a, b = _texture(1), _texture(2)
        r = self._gate(_motion(a, b, 33), tmp_path, a, b, embedder=broken)
        assert not r.passed and any(x.startswith("drift check cannot run") for x in r.reasons)
        assert r.start_ssim > 0.9  # the other checks still ran and are recorded

    def test_drift_frames_are_about_eight_and_include_first_and_last(self, tmp_path) -> None:
        seen = []

        def spy(images):
            seen.append(len(images))
            return same_content_embedder(images)

        a, b = _texture(1), _texture(2)
        self._gate(_motion(a, b, 33), tmp_path, a, b, embedder=spy)
        assert seen == [1 + g.DRIFT_FRAMES]
