"""config.json `persona.prefix_causal` reaches Settings, and the default without a config file is on."""

from __future__ import annotations

import json

from echotales.pipeline import config as cfg


def test_config_json_sets_the_persona_toggle(tmp_path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"persona": {"prefix_causal": False}}))
    monkeypatch.setattr(cfg, "_CONFIG_JSON", path)
    assert cfg._load_config_json() == {"persona_prefix_causal": False}
    monkeypatch.delenv("ECHOTALES_PERSONA_PREFIX_CAUSAL", raising=False)
    assert cfg.get_settings(reload=True).persona_prefix_causal is False


def test_default_is_on_without_a_config_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cfg, "_CONFIG_JSON", tmp_path / "missing.json")
    monkeypatch.delenv("ECHOTALES_PERSONA_PREFIX_CAUSAL", raising=False)
    assert cfg.get_settings(reload=True).persona_prefix_causal is True


def teardown_function() -> None:
    cfg.get_settings(reload=True)  # leave the process-wide settings as the real config.json defines them
