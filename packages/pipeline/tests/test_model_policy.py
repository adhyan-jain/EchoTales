"""The owner's open-weight size policy (D70): up to 8B parameters, gemma2:9b the only named exception.

Why: the ceiling lived in prose while `.env.example` listed 32B to 72B RunPod models and nothing refused them.
"""
from __future__ import annotations

import dataclasses

import pytest
from echotales.pipeline.engines import registry as reg
from echotales.pipeline.llm.client import ModelClient

OPEN_WEIGHT = [e for e in reg.ENGINES if e.kind in ("llm", "ner") and e.role == "model"]


def _spec(name: str, params_b: float | None, approval: str | None = None, kind: str = "llm") -> reg.EngineSpec:
    return reg.EngineSpec(name, kind, "local-low", "x", None, "llm-model", role="model", params_b=params_b,
                          approval=approval)  # type: ignore[arg-type]


@pytest.mark.parametrize("spec", OPEN_WEIGHT, ids=lambda e: f"{e.kind}:{e.name}")
def test_open_weight_entries_have_size_and_approval(spec: reg.EngineSpec) -> None:
    assert spec.params_b is not None and spec.approval is not None
    if spec.approval == "not_authorized":
        with pytest.raises(reg.ModelPolicyError):
            reg.check_model_policy(spec)
    else:
        reg.check_model_policy(spec)


def test_gemma_is_an_owner_exception_and_qwen_is_policy() -> None:
    g, q = reg.get("llm", "gemma2:9b"), reg.get("llm", "qwen2.5:7b")
    assert (g.approval, g.params_b, g.quantization) == ("owner_exception", 9.2, "Q4_0")
    assert (q.approval, q.params_b) == ("policy", 7.6)
    reg.check_model_policy(g)
    reg.check_model_policy(q)


def test_unlisted_9b_and_14b_fail() -> None:
    with pytest.raises(reg.ModelPolicyError):
        reg.check_model_policy(_spec("other:9b", 9.0, "policy"))
    with pytest.raises(reg.ModelPolicyError):
        reg.check_model_policy(_spec("qwen2.5:14b", 14.8, "policy"))
    # the approval flag alone does not whitelist a name
    with pytest.raises(reg.ModelPolicyError):
        reg.check_model_policy(_spec("other:9b", 9.0, "owner_exception"))


def test_not_authorized_fails_even_when_small() -> None:
    with pytest.raises(reg.ModelPolicyError):
        reg.check_model_policy(_spec("tiny", 1.0, "not_authorized"))


def test_hosted_api_providers_are_exempt() -> None:
    anthropic = reg.get("llm", "anthropic")
    reg.check_model_policy(anthropic)
    reg.check_model_policy(dataclasses.replace(anthropic, params_b=500.0))
    reg.check_llm_model("claude-sonnet-5", provider="anthropic")
    reg.check_llm_model("gpt-whatever-70b", provider="openai")


def test_runpod_served_models_are_refused() -> None:
    for name in ("llama70b", "qwen72b", "olmo32b"):
        with pytest.raises(reg.ModelPolicyError):
            reg.check_llm_model(name, provider="runpod")


def test_check_llm_model_local_cases() -> None:
    reg.check_llm_model("gemma2:9b", provider="ollama")
    reg.check_llm_model("qwen2.5:7b-instruct", provider="ollama")
    reg.check_llm_model("z-engineer:latest", provider="ollama")
    with pytest.raises(reg.ModelPolicyError):
        reg.check_llm_model("llama3.1:70b", provider="ollama")


def test_client_refuses_a_big_ollama_model_and_stub_is_untouched() -> None:
    from echotales.pipeline.config import ModelBackend, Settings
    from echotales.pipeline.llm import tasks

    profile = dataclasses.replace(tasks.profile_for(tasks.Task.NER), ollama_model="llama3.1:70b")
    ollama = ModelClient(settings=Settings(model_backend=ModelBackend.OLLAMA))
    with pytest.raises(reg.ModelPolicyError):
        ollama._provider_for(profile, tasks.Task.NER)
    stub = ModelClient(settings=Settings(model_backend=ModelBackend.STUB))
    assert stub._provider_for(profile, tasks.Task.NER) is not None


# ---- owner addendum 2026-11-27: the ceiling is the advertised size class ----

def _classed(name: str, params_b: float, size_class_b: float, approval: str = "policy") -> reg.EngineSpec:
    return dataclasses.replace(_spec(name, params_b, approval), size_class_b=size_class_b)


def test_qwen3_8b_exact_8_2_class_8_passes() -> None:
    q = reg.get("llm", "qwen3:8b")
    assert (q.params_b, q.size_class_b, q.approval) == (8.2, 8.0, "policy")
    reg.check_model_policy(q)
    reg.check_llm_model("qwen3:8b", provider="ollama")


def test_class_9_not_excepted_fails_but_gemma_passes() -> None:
    with pytest.raises(reg.ModelPolicyError):
        reg.check_model_policy(_classed("other-model", 9.0, 9.0))
    reg.check_model_policy(reg.get("llm", "gemma2:9b"))


def test_class_14_fails() -> None:
    with pytest.raises(reg.ModelPolicyError):
        reg.check_model_policy(_classed("other-model", 14.8, 14.0))


def test_unregistered_tags_use_the_size_in_the_tag() -> None:
    reg.check_llm_model("foo:8b", provider="ollama")
    for tag in ("foo:9b", "foo:70b"):
        with pytest.raises(reg.ModelPolicyError):
            reg.check_llm_model(tag, provider="ollama")
