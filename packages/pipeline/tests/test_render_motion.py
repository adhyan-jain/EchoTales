"""Motion-clip tag matching and library caching (xyz.md Step 4, video revision)."""

from __future__ import annotations

from pathlib import Path

import pytest

from echotales.pipeline.render.motion import (
    GENERIC_TAGS,
    build_motion_library,
    get_engine,
    load_motion_library,
    match_tag,
)


class TestMatchTag:
    def test_keyword_beats_polarity(self) -> None:
        assert match_tag("Their swords clashed in the courtyard.") == "clash"

    def test_wind_keyword(self) -> None:
        assert match_tag("A cold wind cut across the plain.") == "wind"

    def test_heightened_polarity_falls_back_to_impact(self) -> None:
        assert match_tag("He shouted furiously.") == "impact"

    def test_no_cue_is_none(self) -> None:
        assert match_tag("He walked to the market and bought bread.") is None


class TestBuildMotionLibrary:
    def test_builds_one_clip_per_tag(self, tmp_path) -> None:
        report = build_motion_library("t", out_dir=tmp_path)
        assert report.clips == len(GENERIC_TAGS)
        assert report.skipped_cached == 0

    def test_rerun_reuses_cache(self, tmp_path) -> None:
        build_motion_library("t", out_dir=tmp_path)
        report = build_motion_library("t", out_dir=tmp_path)
        assert report.clips == 0
        assert report.skipped_cached == len(GENERIC_TAGS)

    def test_stub_writes_real_frame_sequence(self, tmp_path) -> None:
        build_motion_library("t", out_dir=tmp_path, num_frames=5)
        library = load_motion_library("t", tmp_path)
        clip = library["clash"]
        frames = sorted(Path(clip.frames_dir).glob("frame*.png"))
        assert len(frames) == 5
        for frame in frames:
            assert frame.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_load_missing_library_is_empty(self, tmp_path) -> None:
        assert load_motion_library("nope", tmp_path) == {}

    def test_unknown_engine_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown motion engine"):
            get_engine("nope")
