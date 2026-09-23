"""Visual Rendering Track Phase 1b: `compute_render_cache_key` must change
whenever anything that affects pixels changes, and stay stable otherwise --
this is the fix for the pre-Phase-1 image cache being pure file-path
existence with no engine/model/seed component."""

from __future__ import annotations

from pathlib import Path

from echotales.pipeline.render.cache_key import compute_render_cache_key
from echotales.pipeline.render.contract import (
    CompositionSpec,
    EnvironmentRenderSpec,
    GenerationRequest,
    VisualRenderPlan,
)
from echotales.pipeline.render.panels import PanelImageRequest


def _plan() -> VisualRenderPlan:
    return VisualRenderPlan(
        novel_id="n1",
        chapter=1.0,
        beat_id="b1",
        panel_seq=1,
        characters=(),
        environment=EnvironmentRenderSpec(),
        composition=CompositionSpec(),
        state_digest="state-abc",
    )


def _request(**overrides) -> GenerationRequest:
    base_kwargs = dict(prompt="a scene", out_path=Path("/tmp/x.png"), seed=0)
    base_kwargs.update({k: v for k, v in overrides.items() if k in {"prompt", "seed", "reference_images", "reference_weight", "width", "height"}})
    base = PanelImageRequest(**base_kwargs)
    req_kwargs = dict(base=base, backend_name="noobai", steps=30, guidance_scale=7.0)
    req_kwargs.update({k: v for k, v in overrides.items() if k in {"backend_name", "checkpoint_id", "checkpoint_version", "loras", "steps", "guidance_scale"}})
    return GenerationRequest(**req_kwargs)


def test_cache_key_stable_for_identical_inputs():
    plan = _plan()
    assert compute_render_cache_key(plan, _request()) == compute_render_cache_key(
        plan, _request()
    )


def test_cache_key_changes_on_seed():
    plan = _plan()
    assert compute_render_cache_key(plan, _request(seed=0)) != compute_render_cache_key(
        plan, _request(seed=1)
    )


def test_cache_key_changes_on_backend():
    plan = _plan()
    assert compute_render_cache_key(
        plan, _request(backend_name="noobai")
    ) != compute_render_cache_key(plan, _request(backend_name="manga"))


def test_cache_key_changes_on_checkpoint_version():
    plan = _plan()
    assert compute_render_cache_key(
        plan, _request(checkpoint_version="v1")
    ) != compute_render_cache_key(plan, _request(checkpoint_version="v2"))


def test_cache_key_changes_on_steps_and_guidance():
    plan = _plan()
    assert compute_render_cache_key(plan, _request(steps=30)) != compute_render_cache_key(
        plan, _request(steps=35)
    )
    assert compute_render_cache_key(
        plan, _request(guidance_scale=6.0)
    ) != compute_render_cache_key(plan, _request(guidance_scale=7.0))


def test_cache_key_changes_on_references():
    plan = _plan()
    assert compute_render_cache_key(
        plan, _request(reference_images=[Path("/a.png")])
    ) != compute_render_cache_key(plan, _request(reference_images=[Path("/b.png")]))


def test_cache_key_changes_on_loras():
    plan = _plan()
    assert compute_render_cache_key(plan, _request(loras=())) != compute_render_cache_key(
        plan, _request(loras=("some-lora",))
    )


def test_cache_key_changes_when_plan_state_digest_changes():
    request = _request()
    plan_a = _plan()
    plan_b = VisualRenderPlan(
        novel_id="n1",
        chapter=1.0,
        beat_id="b1",
        panel_seq=1,
        characters=(),
        environment=EnvironmentRenderSpec(),
        composition=CompositionSpec(),
        state_digest="state-xyz",
    )
    assert compute_render_cache_key(plan_a, request) != compute_render_cache_key(
        plan_b, request
    )
