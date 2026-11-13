"""The no-private-data regression run: `scripts/demo/run_demo.py` against the real HTTP API in stub mode."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

DEMO_DIR = Path(__file__).resolve().parents[3] / "scripts" / "demo"


@pytest.fixture(scope="module")
def steps(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict]:
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(DEMO_DIR))
        mp.setenv("ECHOTALES_LLM_MODE", "stub")
        import run_demo

        # run_demo works from inside its directory and restores the cwd itself.
        result = run_demo.run_demo(tmp_path_factory.mktemp("demo"))
        sys.modules.pop("run_demo", None)
        sys.modules.pop("make_sample_epub", None)
        yield {s.name: s for s in result}


def test_demo_runs_every_step(steps: dict) -> None:
    expected = [
        "project", "upload", "build", "read", "titles", "correct", "lock", "voice", "m4b", "render",
    ]
    assert list(steps) == expected
    failed = {n: s.detail for n, s in steps.items() if not s.ok}
    assert not failed, failed
    # Stub audio is silent, so the server must refuse the M4B; that refusal is the correct outcome.
    assert steps["m4b"].expected_refusal

