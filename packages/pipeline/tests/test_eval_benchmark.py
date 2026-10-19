"""Unit test for the Golden Benchmark harness."""

from __future__ import annotations

from pathlib import Path

from eval.run_benchmark import run_benchmark


def test_golden_benchmark_path1(tmp_path: Path) -> None:
    rep = run_benchmark(novel_id="showcase", chapter=1.0, tier="path1", work_dir=tmp_path)
    assert rep.passed_all_gates is True
    assert rep.speaker_attribution_accuracy >= 0.90
    assert rep.identity_match_score >= 0.90
    assert rep.vlm_script_compliance_rate >= 0.85
    assert rep.same_voice_collisions == 0
    assert rep.cost_per_finished_minute_usd <= 0.50


def test_golden_benchmark_path2(tmp_path: Path) -> None:
    rep = run_benchmark(novel_id="showcase", chapter=1.0, tier="path2", work_dir=tmp_path)
    assert rep.passed_all_gates is True
    assert rep.cost_per_finished_minute_usd <= 1.80
