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


@pytest.fixture(autouse=True, scope="session")
def _clean_settings_environment():  # type: ignore[no-untyped-def]
    """Every test sees the same settings, whatever the developer's machine says.

    A developer `.env` with `ECHOTALES_LLM_MODE=local` / `ECHOTALES_MODEL_BACKEND=ollama` failed four tests under a
    hostile run (compute policy x2, demo end to end, panel batching) and had already broken one vision-pass test
    (a5a05a1). So: the repo `.env` is not read (`env_file` is cwd-relative, so it depends on where pytest starts),
    every inherited ECHOTALES_* value is dropped, and the developer's `config.json` is not read. Session-scoped so
    that module-scoped fixtures (the demo run) also start clean; a test's own `monkeypatch.setenv` still wins.
    `ECHOTALES_EVAL_ROOT` is kept: the fixture above owns it.
    """
    import os

    from echotales.pipeline import config

    with pytest.MonkeyPatch.context() as mp:
        for name in list(os.environ):
            if name.startswith("ECHOTALES_") and name != "ECHOTALES_EVAL_ROOT":
                mp.delenv(name)
        for name in ("ANTHROPIC_API_KEY", "OLLAMA_HOST"):
            mp.delenv(name, raising=False)
        mp.setenv("ECHOTALES_IMAGE_WORKER", "stub")
        mp.setitem(config.Settings.model_config, "env_file", None)
        mp.setattr(config, "_CONFIG_JSON", config._CONFIG_JSON.with_name("config.json.absent-in-tests"))
        config.get_settings(reload=True)
        yield
    config.get_settings(reload=True)


@pytest.fixture(autouse=True)
def _settings_cache_is_per_test(_clean_settings_environment):  # type: ignore[no-untyped-def]
    """The cached `Settings` never carries one test's env or `config.json` edits into the next."""
    from echotales.pipeline import config

    config.get_settings(reload=True)
    yield
    config.get_settings(reload=True)
