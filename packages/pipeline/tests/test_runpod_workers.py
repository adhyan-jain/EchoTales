"""RunPod worker handlers (workers/runpod/*) against the real client code path (EVOLUTION 4.180).

The handlers sit outside `packages/`, so they are loaded by file path. Their heavy `_run` is replaced; torch, diffusers
and the `runpod` package are never imported. A fake HTTP object plays RunPod: POST /run executes the handler and GET
/status returns COMPLETED (or FAILED with the handler's `error`, as RunPod does). No network, no key, no GPU.
"""
from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from echotales.pipeline.cloud_ledger import CloudLedger
from echotales.pipeline.cloud_lora import build_spec
from echotales.pipeline.cloud_lora import submit as submit_lora
from echotales.pipeline.render.panels import PanelImageRequest
from echotales.pipeline.render.runpod import RunPodClient
from echotales.pipeline.render.runpod_edit import RunPodEditEngine
from echotales.pipeline.video.runpod_video import RunPodVideoEngine
from echotales.pipeline.workers_contract import VideoWorkerRequest

ROOT = Path(__file__).resolve().parents[3]
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 16


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _load(name: str) -> ModuleType:
    path = ROOT / "workers" / "runpod" / name / "handler.py"
    spec = importlib.util.spec_from_file_location(f"_runpod_worker_{name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    status_code = 200

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        return None


class FakeRunPod:
    """Stands in for httpx.Client: runs the handler on POST /run, replays its result on GET /status."""

    def __init__(self, handler: Any) -> None:
        self.handler, self.sent = handler, []
        self.result: dict[str, Any] = {}

    def post(self, url: str, json: dict[str, Any] | None = None, headers: Any = None) -> _Resp:
        assert url.endswith("/run") and set(json or {}) == {"input"}
        self.sent.append(json["input"])
        out = self.handler({"id": "j1", "input": json["input"]})
        if "error" in out:
            self.result = {"status": "FAILED", "error": out["error"]}
        else:
            self.result = {"status": "COMPLETED", "executionTime": 1000, "output": out}
        return _Resp({"id": "j1", "status": "IN_QUEUE"})

    def get(self, url: str, headers: Any = None) -> _Resp:
        return _Resp(self.result)


def _client(tmp_path: Path, handler: Any) -> tuple[RunPodClient, FakeRunPod]:
    fake = FakeRunPod(handler)
    return RunPodClient(endpoint="ep", api_key="k", ledger=CloudLedger(tmp_path / "ledger.json", 9.0),
                        usd_per_hour=0.8, poll_seconds=0.0, client=fake), fake  # type: ignore[arg-type]


def test_runpod_package_is_not_needed() -> None:
    for name in ("wan_video", "qwen_image_edit", "lora_trainer"):
        mod = _load(name)
        assert callable(mod.handler)
        assert mod.runpod is None or hasattr(mod.runpod, "serverless")  # absent here, present in the image


# ---- wan_video ----------------------------------------------------------------------------------------------------

def test_wan_round_trip_through_the_real_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("wan_video")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(mod, "_run", lambda p: seen.update(p) or b"mp4bytes")
    client, fake = _client(tmp_path, mod.handler)
    req = VideoWorkerRequest(keyframe_b64=_b64(PNG), prompt="she turns", num_frames=81, fps=24)
    resp = RunPodVideoEngine(client).generate(req)  # mode defaults to "s2v", the contract default
    assert fake.sent[0]["model"] == "wan2.2-i2v"
    assert resp.video_bytes == b"mp4bytes" and resp.duration_s == pytest.approx(81 / 24, abs=1e-3)
    assert seen["keyframe"] == PNG and seen["num_frames"] == 81 and seen["prompt"] == "she turns"


def test_wan_audio_is_reported_ignored_and_last_frame_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("wan_video")
    monkeypatch.setattr(mod, "_run", lambda p: b"v")
    base = {**VideoWorkerRequest(keyframe_b64=_b64(PNG)).to_input_dict(), "model": "wan2.2-i2v"}
    assert mod.handler({"input": {**base, "audio": _b64(b"wav")}})["audio_ignored"] is True
    assert "last_frame" in mod.handler({"input": {**base, "last_frame": _b64(PNG)}})["error"]


@pytest.mark.parametrize("patch, fragment", [
    ({"keyframe": None}, "keyframe"),
    ({"keyframe": "!!not base64!!"}, "base64"),
    ({"num_frames": 80}, "4n+1"),
    ({"num_frames": 4000}, "num_frames"),
    ({"fps": 0}, "fps"),
    ({"model": "other"}, "unsupported model"),
])
def test_wan_bad_input_is_a_clear_error(patch: dict[str, Any], fragment: str, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("wan_video")
    monkeypatch.setattr(mod, "_run", lambda p: pytest.fail("must not reach the model"))
    inp = {**VideoWorkerRequest(keyframe_b64=_b64(PNG)).to_input_dict(), "model": "wan2.2-i2v", **patch}
    assert fragment in mod.handler({"input": inp})["error"]


def test_wan_model_failure_surfaces_as_the_client_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("wan_video")

    def boom(p: dict[str, Any]) -> bytes:
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(mod, "_run", boom)
    client, _ = _client(tmp_path, mod.handler)
    with pytest.raises(RuntimeError, match="CUDA out of memory"):
        RunPodVideoEngine(client).generate(VideoWorkerRequest(keyframe_b64=_b64(PNG)))


# ---- qwen_image_edit ----------------------------------------------------------------------------------------------

def test_qwen_round_trip_through_the_real_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("qwen_image_edit")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(mod, "_run", lambda p: seen.update(p) or PNG)
    ref = tmp_path / "sheet.png"
    ref.write_bytes(b"sheet-bytes")
    out = tmp_path / "panel.png"
    client, fake = _client(tmp_path, mod.handler)
    req = PanelImageRequest(prompt="a hall", out_path=out, negative_prompt="blurry", width=768, height=1152, seed=7,
                            reference_images=[ref])
    assert RunPodEditEngine(client).generate(req) == out
    assert out.read_bytes() == PNG
    assert seen["references"] == [b"sheet-bytes"] and (seen["width"], seen["height"], seen["seed"]) == (768, 1152, 7)
    assert set(fake.sent[0]) == {"prompt", "negative_prompt", "width", "height", "seed", "references"}


@pytest.mark.parametrize("patch, fragment", [
    ({"prompt": ""}, "prompt"),
    ({"references": []}, "references"),
    ({"references": [_b64(b"a")] * 4}, "references"),
    ({"references": ["@@@"]}, "references[0]"),
    ({"width": 10}, "width"),
    ({"seed": "x"}, "seed"),
])
def test_qwen_bad_input_is_a_clear_error(patch: dict[str, Any], fragment: str, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("qwen_image_edit")
    monkeypatch.setattr(mod, "_run", lambda p: pytest.fail("must not reach the model"))
    inp = {"prompt": "p", "negative_prompt": "", "width": 1024, "height": 1024, "seed": 1,
           "references": [_b64(PNG)], **patch}
    assert fragment in mod.handler({"input": inp})["error"]


# ---- lora_trainer -------------------------------------------------------------------------------------------------

def test_lora_round_trip_through_the_real_submit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("lora_trainer")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(mod, "_run", lambda p: seen.update(p) or b"safetensors")
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "a b.png").write_bytes(PNG)
    client, fake = _client(tmp_path, mod.handler)
    res = submit_lora(build_spec("Lizzy Bennet", refs, steps=500, rank=8), client)
    assert res["submitted"] and res["job_id"] == "j1"
    assert base64.b64decode(client.poll(type("J", (), {"job_id": "j1"})())["output"]["lora"]) == b"safetensors"
    assert seen["steps"] == 500 and seen["rank"] == 8 and seen["trigger"] == "echo_lizzy_bennet"
    assert seen["images"][0]["name"] == "a_b.png" and seen["images"][0]["data"] == PNG
    assert fake.sent[0]["task"] == "train-lora"


def test_lora_unsupported_base_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("lora_trainer")
    monkeypatch.setattr(mod, "_run", lambda p: pytest.fail("must not train an unsupported base"))
    good = {"task": "train-lora", "base_model": "z-image-turbo", "trigger": "t", "steps": 10, "rank": 4,
            "images": [{"name": "a.png", "b64": _b64(PNG), "caption": "c"}]}
    err = mod.handler({"input": {**good, "base_model": "flux-dev"}})["error"]
    assert "unsupported base_model" in err and "z-image-turbo" in err


@pytest.mark.parametrize("patch, fragment", [
    ({"task": "other"}, "task"),
    ({"trigger": ""}, "trigger"),
    ({"steps": 0}, "steps"),
    ({"rank": 999}, "rank"),
    ({"images": []}, "images"),
    ({"images": [{"name": "a.png", "b64": "###"}]}, "base64"),
])
def test_lora_bad_input_is_a_clear_error(patch: dict[str, Any], fragment: str, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("lora_trainer")
    monkeypatch.setattr(mod, "_run", lambda p: pytest.fail("must not train"))
    good = {"task": "train-lora", "base_model": "z-image-turbo", "trigger": "t", "steps": 10, "rank": 4,
            "images": [{"name": "a.png", "b64": _b64(PNG), "caption": "c"}]}
    assert fragment in mod.handler({"input": {**good, **patch}})["error"]


def test_lora_missing_trainer_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _load("lora_trainer")
    monkeypatch.setenv("AI_TOOLKIT_DIR", str(tmp_path / "nope"))
    inp = {"task": "train-lora", "base_model": "z-image-turbo", "trigger": "t", "steps": 10, "rank": 4,
           "images": [{"name": "a.png", "b64": _b64(PNG), "caption": "c"}]}
    assert "ai-toolkit not found" in mod.handler({"input": inp})["error"]


def test_handlers_do_not_import_heavy_libraries_at_module_level() -> None:
    for name in ("wan_video", "qwen_image_edit", "lora_trainer"):
        src = (ROOT / "workers" / "runpod" / name / "handler.py").read_text(encoding="utf-8")
        top = [ln for ln in src.splitlines() if ln.startswith(("import ", "from "))]
        assert not [ln for ln in top if any(h in ln for h in ("torch", "diffusers", "transformers", "PIL"))]
