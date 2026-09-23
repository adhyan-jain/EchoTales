"""Visual Rendering Track Phase 1a: the typed render contract.

`render/contract.py` is additive -- it must not change what any existing
engine renders. These tests only check that the new dataclasses hold the
data they're given, that `GenerationRequest` round-trips `PanelImageRequest`
fields unchanged (no silent renaming), and that every `get_engine(...)`
dispatch target now exposes a `capabilities` matching what the render-
pipeline audit established per-engine.
"""

from __future__ import annotations

from pathlib import Path

from echotales.pipeline.render.contract import (
    CharacterRenderSpec,
    CharacterRole,
    CompositionSpec,
    EnvironmentRenderSpec,
    GenerationAttempt,
    GenerationRequest,
    QATier,
    RenderArtifact,
    VisualQAResult,
    VisualRenderPlan,
    digest_reference_paths,
)
from echotales.pipeline.render.panels import PanelImageRequest, get_engine


def test_generation_request_round_trips_panel_image_request_fields():
    base = PanelImageRequest(
        prompt="a scene",
        out_path=Path("/tmp/x.png"),
        negative_prompt="bad",
        width=768,
        height=512,
        seed=42,
    )
    request = GenerationRequest(base=base, backend_name="noobai")

    assert request.prompt == base.prompt
    assert request.negative_prompt == base.negative_prompt
    assert request.seed == base.seed
    assert request.width == base.width
    assert request.height == base.height
    assert request.base is base


def test_every_engine_declares_capabilities():
    expectations = {
        "stub": {"is_hosted": False, "supports_img2img": True},
        "sdxl": {"is_hosted": False, "supports_multi_reference": False},
        "illustrious": {"is_hosted": False, "supports_img2img": True, "max_references": 2},
        "noobai": {"is_hosted": False, "model_family": "noobai"},
        "refined": {"is_hosted": False},
        "manga": {"is_hosted": False, "supports_img2img": False, "max_references": 2},
        "gemini": {"is_hosted": True, "supports_multi_reference": False},
        "openrouter": {"is_hosted": True, "supports_multi_reference": False},
    }
    for name, expected in expectations.items():
        caps = get_engine(name).capabilities
        for field_name, value in expected.items():
            assert getattr(caps, field_name) == value, f"{name}.{field_name}"


def test_visual_render_plan_digest_is_stable_and_sensitive():
    char = CharacterRenderSpec(
        persona_id="self1:body1", self_id="self1", role=CharacterRole.PRINCIPAL
    )
    plan = VisualRenderPlan(
        novel_id="n1",
        chapter=1.0,
        beat_id="b1",
        panel_seq=1,
        characters=(char,),
        environment=EnvironmentRenderSpec(location="village"),
        composition=CompositionSpec(shot="close-up"),
        state_digest="abc123",
    )
    same = VisualRenderPlan(
        novel_id="n1",
        chapter=1.0,
        beat_id="b1",
        panel_seq=1,
        characters=(char,),
        environment=EnvironmentRenderSpec(location="village"),
        composition=CompositionSpec(shot="close-up"),
        state_digest="abc123",
    )
    assert plan.plan_digest == same.plan_digest

    changed = VisualRenderPlan(
        novel_id="n1",
        chapter=1.0,
        beat_id="b1",
        panel_seq=1,
        characters=(char,),
        environment=EnvironmentRenderSpec(location="different village"),
        composition=CompositionSpec(shot="close-up"),
        state_digest="abc123",
    )
    assert plan.plan_digest != changed.plan_digest


def test_digest_reference_paths_is_order_and_content_sensitive():
    a = digest_reference_paths([Path("/a.png"), Path("/b.png")])
    b = digest_reference_paths([Path("/b.png"), Path("/a.png")])
    c = digest_reference_paths([Path("/a.png"), Path("/b.png")])
    assert a == c
    assert a != b


def test_render_artifact_holds_plan_attempt_and_qa():
    base = PanelImageRequest(prompt="x", out_path=Path("/tmp/x.png"))
    request = GenerationRequest(base=base, backend_name="stub")
    attempt = GenerationAttempt(
        request=request, seed_used=0, output_path=Path("/tmp/x.png")
    )
    qa = VisualQAResult(check_name="flatness", tier=QATier.DIAGNOSTIC, passed=True)
    plan = VisualRenderPlan(
        novel_id="n1",
        chapter=1.0,
        beat_id="b1",
        panel_seq=1,
        characters=(),
        environment=EnvironmentRenderSpec(),
        composition=CompositionSpec(),
    )
    artifact = RenderArtifact(plan=plan, attempt=attempt, qa_results=(qa,))
    assert artifact.plan is plan
    assert artifact.attempt is attempt
    assert artifact.qa_results[0].passed is True
