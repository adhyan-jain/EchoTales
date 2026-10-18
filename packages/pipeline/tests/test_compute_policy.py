"""ECHOTALES_COMPUTE and the provider switches (pipeline/compute.py), the RunPod engine, and the hosted LLM providers.

Everything here is offline: HTTP goes through `httpx.MockTransport`, settings are built with `_env_file=None` so the
developer's real `.env` (and any key in it) cannot leak into a result, and no test reaches RunPod, OpenAI or Gemini.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from echotales.pipeline import compute
from echotales.pipeline.compute import ComputePolicy, parse_mode, policy, resource_refusal
from echotales.pipeline.config import ModelBackend, Settings
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.tasks import Task
from echotales.pipeline.render.panels import PanelImageRequest, get_engine
from echotales.pipeline.render.runpod import RunPodImageEngine

PNG = base64.b64encode(b"\x89PNG-bytes").decode()


def _s(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def _p(**kw) -> ComputePolicy:
    return policy(_s(**kw))


def test_the_default_is_the_laptop_safe_local_profile() -> None:
    p = _p()
    assert (p.mode, p.llm_provider, p.image_provider, p.default_tier) == ("local-low", "stub", "local", "preview")
    assert p.scenes_for(None) == 3 and p.scenes_for("full") == 70 and p.force_sequential


def test_the_three_modes_and_the_provider_overrides() -> None:
    assert (_p(compute="local-high").default_tier, _p(compute="local-high").scenes_for(None)) == ("full", 70)
    cloud = _p(compute="cloud")
    assert (cloud.llm_provider, cloud.image_provider, cloud.default_engine) == ("runpod", "runpod", "runpod")
    # Each provider overrides the preset independently: a hosted director with local images, and the reverse.
    mixed = _p(compute="local-low", llm_provider="openai", image_provider="gemini")
    assert (mixed.llm_provider, mixed.image_provider, mixed.default_engine) == ("openai", "gemini", "gemini")
    assert _p(compute="cloud", image_provider="local").default_engine == "noobai"
    assert _p(llm_provider="Gemini").llm_provider == "gemini"  # case and spacing are forgiven


def test_aliases_and_a_typo_is_an_error_not_a_quiet_default() -> None:
    assert [parse_mode(v) for v in ("", "local", "Low", "laptop", "HIGH", "local_high", "RunPod")] == [
        "local-low", "local-low", "local-low", "local-low", "local-high", "local-high", "cloud",
    ]
    with pytest.raises(ValueError, match="not one of"):
        parse_mode("turbo")
    with pytest.raises(ValueError, match="ECHOTALES_LLM_PROVIDER"):
        _p(llm_provider="skynet")
    with pytest.raises(ValueError, match="ECHOTALES_IMAGE_PROVIDER"):
        _p(image_provider="dalle")


def test_low_compute_rules_apply_only_in_local_low() -> None:
    low, high = _p(), _p(compute="local-high")
    assert (low.director_num_ctx(8192), high.director_num_ctx(8192)) == (4096, 8192)
    assert low.director_num_ctx(2048) == 2048  # a cap, never a raise
    assert (low.director_model("gemma2:9b"), high.director_model("gemma2:9b")) == ("gemma2:9b", "gemma2:9b")
    assert _p(low_compute_director_model="qwen2.5:7b").director_model("gemma2:9b") == "qwen2.5:7b"
    assert not high.force_sequential


def test_missing_variables_are_named_and_values_never_appear() -> None:
    assert _p(compute="cloud").llm_missing() == [
        "ECHOTALES_RUNPOD_API_KEY", "ECHOTALES_RUNPOD_LLM_BASE_URL", "ECHOTALES_RUNPOD_LLM_MODEL",
    ]
    assert _p(llm_provider="openai").llm_missing() == ["ECHOTALES_OPENAI_API_KEY", "ECHOTALES_OPENAI_MODEL"]
    assert _p(llm_provider="gemini", gemini_api_key="k").llm_missing() == ["ECHOTALES_GEMINI_MODEL"]
    assert _p().llm_missing() == []
    assert _p(compute="cloud").image_missing("runpod") == ["ECHOTALES_RUNPOD_API_KEY", "ECHOTALES_RUNPOD_IMAGE_ENDPOINT"]
    assert _p(runpod_api_key="s3cret", runpod_image_endpoint="ep").image_missing("runpod") == []
    assert "s3cret" not in repr(_p(runpod_api_key="s3cret").llm_missing())


def test_engine_gating_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compute.gpu, "gpu_status", lambda: compute.gpu.GpuStatus("RTX", 15, 8188))
    monkeypatch.setattr(compute, "available_ram_mb", lambda: 6000)
    low = _p()
    assert resource_refusal("stub", low) is None and resource_refusal("noobai", low) is None

    # A request cannot name a hosted engine the operator never selected; the CLI always could.
    assert "not enabled on this server" in resource_refusal("gemini", low, http=True)
    assert resource_refusal("gemini", low) is None  # the person at the keyboard is the opt-in
    assert low.http_engines() == ["stub", "noobai", "illustrious", "sdxl"]

    cloud = _p(compute="cloud")
    assert cloud.http_engines() == ["stub", "runpod"]
    assert "ECHOTALES_IMAGE_PROVIDER is runpod" in resource_refusal("noobai", cloud)
    assert "ECHOTALES_RUNPOD_API_KEY" in resource_refusal("runpod", cloud, http=True)
    ready = _p(compute="cloud", runpod_api_key="k", runpod_image_endpoint="ep")
    assert resource_refusal("runpod", ready, http=True) is None  # cloud never checks the local GPU or RAM
    monkeypatch.setattr(compute, "available_ram_mb", lambda: 10)
    assert resource_refusal("runpod", ready, http=True) is None


def test_local_low_refuses_on_a_busy_gpu_or_short_memory_and_local_high_skips_the_memory_check(monkeypatch) -> None:
    monkeypatch.setattr(compute.gpu, "gpu_status", lambda: compute.gpu.GpuStatus("RTX", 5200, 8188))
    assert "GPU is busy" in resource_refusal("noobai", _p()) and "5200 of 8188" in resource_refusal("noobai", _p())

    monkeypatch.setattr(compute.gpu, "gpu_status", lambda: compute.gpu.GpuStatus("RTX", 15, 8188))
    monkeypatch.setattr(compute, "available_ram_mb", lambda: 1500)
    why = resource_refusal("noobai", _p())
    assert "1500 MiB of RAM" in why and "local-high" in why
    assert resource_refusal("noobai", _p(compute="local-high")) is None
    assert resource_refusal("noobai", _p(low_compute_min_free_ram_mb=1000)) is None

    monkeypatch.setattr(compute.gpu, "gpu_status", lambda: None)
    assert "NVIDIA GPU" in resource_refusal("noobai", _p())


# --- the language-model providers -------------------------------------------------------------------------------


def test_the_backend_follows_the_provider_then_the_preset_then_the_old_setting() -> None:
    assert ModelClient(settings=_s(model_backend=ModelBackend.OLLAMA)).backend is ModelBackend.OLLAMA
    assert ModelClient(settings=_s(model_backend=ModelBackend.STUB)).backend is ModelBackend.STUB
    assert ModelClient(settings=_s(compute="cloud", model_backend=ModelBackend.OLLAMA)).backend is ModelBackend.RUNPOD
    both = _s(compute="cloud", llm_provider="gemini", model_backend=ModelBackend.OLLAMA)
    assert ModelClient(settings=both).backend is ModelBackend.GEMINI


def test_hosted_providers_share_one_openai_compatible_client_with_their_own_url_key_and_model() -> None:
    from echotales.pipeline.llm.gateway import GatewayProvider
    from echotales.pipeline.llm.tasks import profile_for

    cases = [
        (dict(llm_provider="runpod", runpod_llm_base_url="https://api.runpod.ai/v2/abc/openai/v1/",
              runpod_api_key="rk", runpod_llm_model="llama-70b"),
         "https://api.runpod.ai/v2/abc/openai/v1", "rk", "llama-70b"),
        (dict(llm_provider="openai", openai_api_key="ok", openai_model="gpt-x"), "https://api.openai.com/v1", "ok", "gpt-x"),
        (dict(llm_provider="gemini", gemini_api_key="gk", gemini_model="gem-x"),
         "https://generativelanguage.googleapis.com/v1beta/openai", "gk", "gem-x"),
    ]
    for kw, base, key, model in cases:
        client = ModelClient(settings=_s(**kw))
        provider = client._provider_for(profile_for(Task.PANEL_DIRECTION), Task.PANEL_DIRECTION)
        assert isinstance(provider, GatewayProvider)
        assert (provider.host, provider._api_key, provider.model) == (base, key, model)
        assert client.model_for(Task.PANEL_DIRECTION) == model


def test_hosted_preflight_names_the_missing_variables_and_checks_nothing_over_the_network_without_them() -> None:
    result = ModelClient(settings=_s(llm_provider="openai")).preflight()
    assert not result.available and result.missing == ["ECHOTALES_OPENAI_API_KEY", "ECHOTALES_OPENAI_MODEL"]
    assert "ECHOTALES_OPENAI_API_KEY" in result.detail


def test_gemini_model_listing_uses_models_slash_names() -> None:
    from echotales.pipeline.llm.gateway import GatewayProvider

    provider = GatewayProvider(model="gemini-x", host="https://example.test/v1", api_key="k")
    provider._client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"id": "models/gemini-x"}]})
    ))
    assert provider.available()


def test_local_low_caps_the_directors_context_and_leaves_every_other_task_alone() -> None:
    from echotales.pipeline.llm.tasks import profile_for

    low = ModelClient(settings=_s(model_backend=ModelBackend.OLLAMA, llm_local_num_ctx=8192))
    director = low._provider_for(profile_for(Task.PANEL_DIRECTION), Task.PANEL_DIRECTION)
    other = low._provider_for(profile_for(Task.ADJUDICATION), Task.ADJUDICATION)
    assert director.num_ctx == 4096 and other.num_ctx == 8192
    high = ModelClient(settings=_s(compute="local-high", model_backend=ModelBackend.OLLAMA, llm_local_num_ctx=8192))
    assert high._provider_for(profile_for(Task.PANEL_DIRECTION), Task.PANEL_DIRECTION).num_ctx == 8192


# --- the RunPod image engine --------------------------------------------------------------------------------------


def _engine(handler, **kw) -> RunPodImageEngine:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return RunPodImageEngine(api_key="SECRET-KEY", endpoint="ep123", poll_seconds=0, client=client, **kw)


def _request(tmp_path) -> PanelImageRequest:
    return PanelImageRequest(
        prompt="1boy, solo", out_path=tmp_path / "out" / "p.png", negative_prompt="bad", width=832, height=1216, seed=7
    )


def test_runpod_submits_polls_and_writes_the_image(tmp_path) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers["authorization"], request.content))
        if request.method == "POST":
            return httpx.Response(200, json={"id": "job1", "status": "IN_QUEUE"})
        polls = sum(1 for m, *_ in seen if m == "GET")
        status = "IN_PROGRESS" if polls < 2 else "COMPLETED"
        output = {"images": [{"image": "data:image/png;base64," + PNG}]}
        return httpx.Response(200, json={"id": "job1", "status": status, "output": output})

    out = _engine(handler).generate(_request(tmp_path))
    assert out.read_bytes() == b"\x89PNG-bytes"
    assert [(m, p) for m, p, *_ in seen] == [
        ("POST", "/v2/ep123/run"), ("GET", "/v2/ep123/status/job1"), ("GET", "/v2/ep123/status/job1"),
    ]
    assert all(auth == "Bearer SECRET-KEY" for _m, _p, auth, _c in seen)
    assert json.loads(seen[0][3]) == {
        "input": {"prompt": "1boy, solo", "negative_prompt": "bad", "width": 832, "height": 1216, "seed": 7}
    }


@pytest.mark.parametrize("output", [PNG, {"image": PNG}, {"image_base64": PNG}, {"images": [PNG]}, {"output": {"image": PNG}}])
def test_runpod_accepts_the_common_response_shapes(tmp_path, output) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "j", "status": "COMPLETED", "output": output})

    assert _engine(handler).generate(_request(tmp_path)).read_bytes() == b"\x89PNG-bytes"


def test_runpod_failures_are_clear_and_never_print_the_key(tmp_path) -> None:
    def failed(request):
        return httpx.Response(200, json={"id": "j", "status": "FAILED", "error": "CUDA out of memory"})

    with pytest.raises(RuntimeError, match="failed: CUDA out of memory"):
        _engine(failed).generate(_request(tmp_path))
    with pytest.raises(RuntimeError, match="rejected the API key") as exc:
        _engine(lambda r: httpx.Response(401, json={})).generate(_request(tmp_path))
    assert "SECRET-KEY" not in str(exc.value)
    with pytest.raises(RuntimeError, match="endpoint not found"):
        _engine(lambda r: httpx.Response(404, json={})).generate(_request(tmp_path))
    empty = {"id": "j", "status": "COMPLETED", "output": {"note": "x"}}
    with pytest.raises(RuntimeError, match="no image in its output"):
        _engine(lambda r: httpx.Response(200, json=empty)).generate(_request(tmp_path))
    queued = {"id": "j", "status": "IN_QUEUE"}
    with pytest.raises(RuntimeError, match="did not finish"):
        _engine(lambda r: httpx.Response(200, json=queued), timeout=0.0).generate(_request(tmp_path))


def test_runpod_without_configuration_says_which_variables(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(compute, "policy", lambda settings=None: _p())
    with pytest.raises(RuntimeError, match="ECHOTALES_RUNPOD_API_KEY, ECHOTALES_RUNPOD_IMAGE_ENDPOINT"):
        RunPodImageEngine().generate(_request(tmp_path))
    assert get_engine("runpod").name == "runpod"


# --- the CLI ------------------------------------------------------------------------------------------------------


def test_the_render_cli_refuses_a_local_engine_when_memory_is_short_and_says_why(tmp_path, monkeypatch, capsys) -> None:
    from echotales.pipeline.cli import main
    from test_render_runner import _seeded_store

    _seeded_store(tmp_path).close()
    monkeypatch.setattr(compute.gpu, "gpu_status", lambda: compute.gpu.GpuStatus("RTX", 15, 8188))
    monkeypatch.setattr(compute, "available_ram_mb", lambda: 400)
    code = main(["--db", str(tmp_path / "t.db"), "render", "--novel", "t", "--image-engine", "noobai",
                 "--skip-motion", "--skip-compose", "--panel-dir", str(tmp_path / "p")])
    err = capsys.readouterr().err
    assert code == 2 and "400 MiB of RAM" in err and "--ignore-resource-guard" in err
    assert not (tmp_path / "p").exists()  # nothing was loaded or written


def test_a_bare_render_stays_on_the_stub_and_renders_the_tiers_scene_count(tmp_path, monkeypatch, capsys) -> None:
    from echotales.pipeline.cli import main
    from test_render_runner import _seeded_store

    _seeded_store(tmp_path).close()
    monkeypatch.setattr(compute, "policy", lambda settings=None: _p())
    out = tmp_path / "out"
    code = main(["--db", str(tmp_path / "t.db"), "render", "--novel", "t", "--no-director", "--skip-motion",
                 "--skip-compose", "--panel-dir", str(out / "p"), "--motion-dir", str(out / "m"),
                 "--voice-dir", str(out / "a"), "--out", str(out / "v"), "--version-suffix", "tier test"])
    text = capsys.readouterr().out
    assert code == 0
    assert "compute: local-low; images: stub; language: stub; scenes per chapter: 3" in text
    assert "output version: v1_tier-test" in text
