"""The lint ratchet: counts parse, a rise fails, and ruff on packages/ has not risen above the checked-in baseline.

Why the ruff check lives in the test suite and mypy does not: ruff takes about a second, mypy about a minute and its
count shifts with the installed stubs, so mypy runs from `make verify` only.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "maintenance" / "lint_ratchet.py"

pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="lint_ratchet.py missing")


def _load():
    spec = importlib.util.spec_from_file_location("lint_ratchet", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lint_ratchet"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parsers() -> None:
    m = _load()
    assert m.parse_ruff_count("x\nFound 549 errors.\n[*] 325 fixable") == 549
    assert m.parse_ruff_count("Found 1 error.") == 1
    assert m.parse_ruff_count("All checks passed!") == 0
    assert m.parse_mypy_count("a.py:1: error: x\nFound 1628 errors in 213 files (checked 246 source files)") == 1628
    assert m.parse_mypy_count("Success: no issues found in 3 source files") == 0
    with pytest.raises(ValueError):
        m.parse_ruff_count("traceback")


def test_a_rise_is_a_regression_and_a_fall_is_not() -> None:
    m = _load()
    assert m.regression(11, 10) and not m.regression(10, 10) and not m.regression(9, 10)


def test_baseline_file_has_both_counts() -> None:
    base = json.loads(SCRIPT.with_name("lint_baseline.json").read_text(encoding="utf-8"))
    assert isinstance(base["ruff"], int) and isinstance(base["mypy"], int)


@pytest.mark.skipif(shutil.which("ruff") is None and not (ROOT / ".venv" / "bin" / "ruff").exists(), reason="ruff not installed")
def test_ruff_count_has_not_risen() -> None:
    m = _load()
    try:
        current = m.count_ruff()
    except (ValueError, OSError):  # ruff is not importable by this interpreter
        pytest.skip("ruff could not be run by this interpreter")
    base = json.loads(SCRIPT.with_name("lint_baseline.json").read_text(encoding="utf-8"))
    assert current <= base["ruff"], f"ruff errors rose to {current} (baseline {base['ruff']})"
