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


@pytest.fixture(autouse=True, scope="session")
def _image_worker_is_the_stub_in_tests():  # type: ignore[no-untyped-def]
    """The image worker defaults to NoobAI outside stub mode (never a flat image on a real run), so a developer whose
    `.env` says `ECHOTALES_LLM_MODE=local` would otherwise load the GPU model from any test that draws an image."""
    import os

    previous = os.environ.get("ECHOTALES_IMAGE_WORKER")
    if previous is None:
        os.environ["ECHOTALES_IMAGE_WORKER"] = "stub"
    yield
    if previous is None:
        os.environ.pop("ECHOTALES_IMAGE_WORKER", None)
