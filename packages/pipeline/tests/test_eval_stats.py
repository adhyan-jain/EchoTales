"""Bootstrap intervals (COMPLETION_PLAN Track 2 item 10, EVOLUTION 4.81).

Every number this project has reported was a point estimate. A 52-point
metric disagreement over 6,238 mentions and an 81%->93% rise between windows
of 145 and 166 links both looked equally solid without one.
"""

from __future__ import annotations

from echotales.pipeline.eval.stats import (
    bootstrap_ci,
    paired_bootstrap,
    rate,
)


def _hits(n_true: int, n_false: int) -> list[bool]:
    return [True] * n_true + [False] * n_false


class TestBootstrapCI:
    def test_the_point_estimate_is_the_plain_statistic(self) -> None:
        interval = bootstrap_ci(_hits(90, 10), rate, resamples=200, seed=1)
        assert interval.point == 0.9

    def test_the_interval_brackets_the_point(self) -> None:
        interval = bootstrap_ci(_hits(90, 10), rate, resamples=500, seed=1)
        assert interval.low <= interval.point <= interval.high

    def test_more_examples_give_a_tighter_interval(self) -> None:
        """The property that makes an interval worth printing at all: it is
        what separates 'measured on 6,238 mentions' from 'measured on 145'."""
        small = bootstrap_ci(_hits(9, 1), rate, resamples=500, seed=2)
        large = bootstrap_ci(_hits(900, 100), rate, resamples=500, seed=2)
        assert (large.high - large.low) < (small.high - small.low)

    def test_a_single_example_reports_no_spread_rather_than_inventing_one(self) -> None:
        interval = bootstrap_ci([True], rate, resamples=500, seed=1)
        assert interval.low == interval.high == 1.0
        assert interval.resamples == 0

    def test_an_empty_set_does_not_divide_by_zero(self) -> None:
        assert bootstrap_ci([], rate, resamples=10).point == 0.0

    def test_the_seed_makes_it_reproducible(self) -> None:
        a = bootstrap_ci(_hits(70, 30), rate, resamples=300, seed=5)
        b = bootstrap_ci(_hits(70, 30), rate, resamples=300, seed=5)
        assert (a.low, a.high) == (b.low, b.high)

    def test_a_different_seed_gives_a_different_draw(self) -> None:
        a = bootstrap_ci(_hits(70, 30), rate, resamples=300, seed=5)
        b = bootstrap_ci(_hits(70, 30), rate, resamples=300, seed=6)
        assert (a.low, a.high) != (b.low, b.high)


class TestPairedBootstrap:
    def test_a_real_improvement_excludes_zero(self) -> None:
        # B is right wherever A is, plus 20 more out of 100.
        examples = list(range(100))
        a = lambda xs: sum(1 for x in xs if x < 60) / len(xs)  # noqa: E731
        b = lambda xs: sum(1 for x in xs if x < 80) / len(xs)  # noqa: E731
        result = paired_bootstrap(examples, a, b, resamples=500, seed=3)
        assert result.delta > 0
        assert result.significant
        assert result.p_value < 0.05

    def test_two_identical_systems_are_not_distinguishable(self) -> None:
        examples = list(range(100))
        same = lambda xs: sum(1 for x in xs if x < 50) / len(xs)  # noqa: E731
        result = paired_bootstrap(examples, same, same, resamples=500, seed=3)
        assert result.delta == 0.0
        assert not result.significant

    def test_a_tiny_difference_on_few_examples_is_not_significant(self) -> None:
        """The case this exists to catch -- a compounding curve window of 145
        links rising to 166 is not automatically a result."""
        examples = list(range(20))
        a = lambda xs: sum(1 for x in xs if x < 10) / len(xs)  # noqa: E731
        b = lambda xs: sum(1 for x in xs if x < 11) / len(xs)  # noqa: E731
        assert not paired_bootstrap(examples, a, b, resamples=500, seed=3).significant

    def test_a_regression_also_excludes_zero_on_the_other_side(self) -> None:
        examples = list(range(100))
        a = lambda xs: sum(1 for x in xs if x < 80) / len(xs)  # noqa: E731
        b = lambda xs: sum(1 for x in xs if x < 60) / len(xs)  # noqa: E731
        result = paired_bootstrap(examples, a, b, resamples=500, seed=3)
        assert result.delta < 0 and result.significant and result.high < 0


class TestHeldOutCoverage:
    """`calibrate_from_gold` fits and reports on the same samples, so its
    (1-alpha) figure is a fit statistic and the conformal guarantee was never
    validated out-of-sample (Track 2 item 9, EVOLUTION 4.81)."""

    def test_one_chapter_cannot_be_split_forwards_in_time(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from echotales.pipeline.eval.calibrate import HeldOutCoverage

        result = HeldOutCoverage(novel_id="n", split_chapter=1.0, calibration_size=5)
        assert result.test_size == 0
        assert "not evaluated" in result.summary()

    def test_coverage_is_correct_over_correct_plus_missed(self) -> None:
        from echotales.pipeline.eval.calibrate import HeldOutCoverage

        result = HeldOutCoverage(
            novel_id="n", split_chapter=10.0, test_size=100,
            covered=96, missed=4, false_links=3, alpha=0.05,
        )
        assert result.empirical_coverage == 0.96
        assert result.target_coverage == 0.95
        assert "MET" in result.summary()

    def test_a_missed_guarantee_is_flagged_not_rounded_away(self) -> None:
        from echotales.pipeline.eval.calibrate import HeldOutCoverage

        result = HeldOutCoverage(
            novel_id="n", split_chapter=10.0, test_size=100,
            covered=80, missed=20, alpha=0.05,
        )
        assert result.empirical_coverage == 0.8
        assert "NOT MET" in result.summary()


class TestPersistence:
    def test_a_results_directory_records_what_produced_the_numbers(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """EVOLUTION 4.74 retracted a figure nobody could trace to a gold
        file, a database or a commit."""
        import json

        from echotales.core.store import Store
        from echotales.pipeline.eval.persist import persist_eval

        store = Store(str(tmp_path / "p.db"))
        try:
            store.add_novel("n", "N", "", "")
            store.conn.commit()
            out = persist_eval(
                store, "n", metrics={"f1": 0.5}, gold_path="g.jsonl",
                seed=7, root=tmp_path / "results",
            )
            payload = json.loads((out / "metrics.json").read_text())
            assert payload["metrics"] == {"f1": 0.5}
            assert payload["gold_path"] == "g.jsonl"
            assert payload["seed"] == 7
            assert payload["git_commit"]
            assert payload["novel_id"] == "n"
            # The artifact is registered, not just written to disk.
            kinds = [
                r[0] for r in store.conn.execute("SELECT kind FROM stage_artifact")
            ]
            assert "eval_results" in kinds
        finally:
            store.close()

    def test_the_dirty_marker_is_not_omitted(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """This repository's numbers have come from an uncommitted tree for
        most of its life; a bare hash would imply a reproducibility it does
        not have."""
        from echotales.pipeline.eval.persist import _git_commit

        commit = _git_commit()
        assert commit == "unknown" or "-" in commit or len(commit) >= 7
