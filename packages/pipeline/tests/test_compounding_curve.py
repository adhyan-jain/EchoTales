"""The gazetteer compounding curve is the project's own headline claim.

Non-negotiable #8 says the gazetteer compounds. Until 2026-09-23 the
detection half was printed and discarded and the resolution half did not
exist, so the claim had never been checked against a number (EVOLUTION 4.77).
"""

from __future__ import annotations

from echotales.core.enums import ResolutionMethod
from echotales.pipeline.eval.compounding import (
    CompoundingCurve,
    record_detection_half,
    record_resolution_half,
)
from echotales.pipeline.resolve.runner import ResolveReport


class TestCurvePersistence:
    def test_the_two_halves_do_not_clobber_each_other(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """They are written by different stages, minutes apart, so a plain
        overwrite would mean whichever ran last was the only half on disk."""
        record_detection_half("ri", window_size=40, points=[(1, 0.5)], root=tmp_path)
        record_resolution_half(
            "ri",
            window_size=40,
            by_window={1: {ResolutionMethod.GAZETTEER_EXACT.value: 9, "SCORED": 1}},
            root=tmp_path,
        )
        curve = CompoundingCurve.load("ri", tmp_path)
        assert curve.detection == [(1, 0.5)]
        assert curve.resolution == [(1, 0.9, 10)]

    def test_a_rerun_replaces_its_own_half(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        record_detection_half("ri", window_size=40, points=[(1, 0.5)], root=tmp_path)
        record_detection_half("ri", window_size=40, points=[(1, 0.8), (2, 0.9)], root=tmp_path)
        assert CompoundingCurve.load("ri", tmp_path).detection == [(1, 0.8), (2, 0.9)]

    def test_missing_file_is_an_empty_curve_not_an_error(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        curve = CompoundingCurve.load("never-run", tmp_path)
        assert curve.detection == [] and curve.resolution == []

    def test_a_corrupt_curve_does_not_kill_the_run_that_overwrites_it(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """35 minutes of resolution is worth more than a file that any rerun
        regenerates."""
        path = CompoundingCurve.path_for("ri", tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")
        record_resolution_half(
            "ri", window_size=40, by_window={0: {"SCORED": 1}}, root=tmp_path
        )
        assert CompoundingCurve.load("ri", tmp_path).resolution == [(0, 0.0, 1)]

    def test_an_empty_window_is_zero_not_a_division_error(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        record_resolution_half("ri", window_size=40, by_window={0: {}}, root=tmp_path)
        assert CompoundingCurve.load("ri", tmp_path).resolution == [(0, 0.0, 0)]


class TestResolveReportCurve:
    def test_rate_is_reported_with_its_denominator(self) -> None:
        """A window with four links at 100% is not evidence of compounding,
        and a bare rate invites reading it as though it were."""
        report = ResolveReport(novel_id="ri")
        report.link_method_by_window = {
            0: {ResolutionMethod.GAZETTEER_EXACT.value: 4},
            1: {ResolutionMethod.GAZETTEER_EXACT.value: 90, ResolutionMethod.SCORED.value: 10},
        }
        assert report.gazetteer_hit_rate_by_window() == [(0, 1.0, 4), (1, 0.9, 100)]

    def test_windows_come_out_in_reading_order(self) -> None:
        report = ResolveReport(novel_id="ri")
        report.link_method_by_window = {2: {"SCORED": 1}, 0: {"SCORED": 1}, 1: {"SCORED": 1}}
        assert [w for w, _, _ in report.gazetteer_hit_rate_by_window()] == [0, 1, 2]

    def test_no_links_means_no_curve_rather_than_a_flat_zero(self) -> None:
        assert ResolveReport(novel_id="ri").gazetteer_hit_rate_by_window() == []
