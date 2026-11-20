"""The compiler takes its engine choice from the engine registry, not from constants of its own (round 3, defect 9).

Before: `compiler.DEFAULT_MODEL` was the literal "noobai-xl-1.1", so a bare `model_profile()` was NoobAI while the product default
is Z-Image Turbo (D58), and each profile repeated its licence string, which the registry also holds."""

from __future__ import annotations

import pytest
from echotales.pipeline.config import get_settings
from echotales.pipeline.engines import registry
from echotales.pipeline.render import compiler


def test_every_compiler_profile_is_a_registry_entry_with_the_same_licence() -> None:
    assert set(compiler.PROFILES) == set(registry.compiler_profiles())
    for key, profile in compiler.PROFILES.items():
        spec = registry.get("image", key, surface="compiler")
        assert spec.licence.split(" (")[0] == profile.licence.split(" (")[0], key


def test_the_default_profile_is_the_configured_image_model_not_a_constant(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "render_image_model", "anima")
    assert compiler.model_profile().key == "anima"
    monkeypatch.setattr(get_settings(), "render_image_model", "z-image-turbo")
    assert compiler.model_profile().key == "z-image-turbo"
    assert compiler.model_profile("noobai-xl-1.1").key == "noobai-xl-1.1"


def test_a_model_the_registry_does_not_list_is_refused_and_the_message_lists_the_registry(monkeypatch) -> None:
    with pytest.raises(ValueError, match="z-image-turbo"):
        compiler.model_profile("no-such-model")
    monkeypatch.setattr(registry, "compiler_profiles", lambda: ("anima",))
    with pytest.raises(ValueError):
        compiler.model_profile("z-image-turbo")


def test_commercial_flags_come_from_the_registry_for_the_default() -> None:
    assert registry.get("image", "z-image-turbo", surface="compiler").commercial_safe is True
    assert registry.get("image", "noobai-xl-1.1", surface="compiler").commercial_safe is False
