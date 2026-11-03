"""Skip markers for tests that need something a clean CI checkout does not have.

Found by running the CI commands in a clean worktree (2026-10-31): 17 tests failed there, though they pass on a
developer machine, because they need gitignored research data, the real CLIP tokenizer (`transformers`) or `torch`.
They run wherever those exist; they are skipped, not deleted, where they do not.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

requires_clip = pytest.mark.skipif(
    importlib.util.find_spec("transformers") is None,
    reason="needs transformers: without the real CLIP tokenizer token counts are an over-estimate",
)
requires_torch = pytest.mark.skipif(importlib.util.find_spec("torch") is None, reason="needs torch")
_EVAL = Path(__file__).resolve().parents[3] / "data" / "eval"
requires_adjudication_data = pytest.mark.skipif(
    not all(p.is_file() for p in (
        _EVAL / "adjudication" / "standard_200_blind.csv",
        _EVAL / "adjudication" / "standard_200_v2_blind.csv",
        _EVAL / "human_review_200.csv",
    )),
    reason="the blind adjudication packages and human_review_200.csv are gitignored research data; "
           "this runs where they are supplied locally",
)
