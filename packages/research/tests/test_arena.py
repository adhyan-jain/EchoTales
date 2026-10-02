"""Infrastructure guarantees: deterministic stub runs, seed derivation,
statistics, and each experiment's stub path."""

import json

import pytest

from echotales.research import stats
from echotales.research.config import derive_seed, stable_hash
from echotales.research.runner import available, run_experiment


def test_derive_seed_is_stable_and_independent_of_other_keys():
    assert derive_seed(1, "a", "b") == derive_seed(1, "a", "b")
    assert derive_seed(1, "a", "b") != derive_seed(1, "a", "c")
    assert stable_hash({"x": 1, "y": 2}) == stable_hash({"y": 2, "x": 1})


def test_wilson_is_honest_at_extremes():
    p, lo, hi = stats.wilson(0, 10)
    assert p == 0 and lo == 0 and 0 < hi < 0.35
    p, lo, hi = stats.wilson(10, 10)
    assert p == 1 and hi == 1 and 0.65 < lo < 1


def test_ece_perfect_calibration_is_zero():
    ece, table = stats.expected_calibration_error([1.0, 1.0, 0.0, 0.0], [True, True, False, False])
    assert ece == pytest.approx(0.0)
    assert table


def test_bradley_terry_orders_a_clear_winner_first():
    s = stats.bradley_terry(["a", "b", "c"], [("a", "b")] * 5 + [("b", "c")] * 5 + [("a", "c")] * 5)
    assert s["a"] > s["b"] > s["c"]


@pytest.mark.parametrize("name", available())
def test_every_experiment_runs_in_stub_mode_deterministically(name, tmp_path):
    out1 = run_experiment(name, stub=True, out_root=tmp_path / "a", run_id="r")
    out2 = run_experiment(name, stub=True, out_root=tmp_path / "b", run_id="r",
                          params={"out_dir": str(tmp_path / "stim")} if name == "error_cost_stimuli" else None)
    if name == "error_cost_stimuli":
        # out_dir is a reported path, so normalise it before comparing.
        a = json.loads((out1 / "results.json").read_text())
        b = json.loads((out2 / "results.json").read_text())
        for d in (a, b):
            d["summary"].pop("out_dir")
            d.pop("config_hash")
        assert a == b
    else:
        assert (out1 / "results.json").read_bytes() == (out2 / "results.json").read_bytes()
    prov = json.loads((out1 / "provenance.json").read_text())
    assert {"git_sha", "git_dirty", "config_hash"} <= set(prov)
