"""Keep evaluation-artifact writes out of the repository during tests.

`resolve_novel` and `detect_mentions` write a gazetteer-compounding curve
unconditionally (EVOLUTION 4.77), and several long-standing tests resolve a
toy novel called "t". Without this, every test run left
`data/eval/compounding/t.json` in the working tree -- caught while auditing
this session's own work, after it had already happened.

Autouse and session-scoped: the point is that no test has to remember.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True, scope="session")
def _eval_artifacts_to_tmp(tmp_path_factory):  # type: ignore[no-untyped-def]
    root = tmp_path_factory.mktemp("eval-artifacts")
    import os

    previous = os.environ.get("ECHOTALES_EVAL_ROOT")
    os.environ["ECHOTALES_EVAL_ROOT"] = str(root)
    yield root
    if previous is None:
        os.environ.pop("ECHOTALES_EVAL_ROOT", None)
    else:
        os.environ["ECHOTALES_EVAL_ROOT"] = previous
