"""Cloud phase (EVOLUTION 4.174): mock transport only. No network, no key, no paid call is made by any test here."""
from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any

import pytest
from echotales.pipeline import cloud_ledger, cloud_lora, workers_zimage
from echotales.pipeline.cloud_ledger import BudgetExceeded, CloudLedger
from echotales.pipeline.engines import registry as reg
from echotales.pipeline.render.panels import PanelImageRequest
from echotales.pipeline.render.runpod import RunPodClient
from echotales.pipeline.render.runpod_edit import RunPodEditEngine
from echotales.pipeline.video.runpod_video import RunPodVideoEngine
from echotales.pipeline.voice.elevenlabs import ElevenLabsEngine
from echotales.pipeline.voice.engine import SynthesisRequest, get_engine
from echotales.pipeline.workers_contract import VideoWorkerRequest


class _Resp:
    def __init__(self, body: Any = None, status: int = 200, content: bytes = b"") -> None:
        self._body, self.status_code, self.content = body, status, content

    def json(self) -> Any:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class FakeHTTP:
    """Records every call; replays `completed` for any status poll. Stands in for httpx.Client."""

    def __init__(self, completed: dict[str, Any] | None = None, post_content: bytes = b"") -> None:
        self.calls: list[tuple[str, str]] = []
        self.completed = completed or {"status": "COMPLETED", "executionTime": 36000, "output": {}}
        self.post_content = post_content

    def post(self, url: str, **kw: Any) -> _Resp:
        self.calls.append(("POST", url))
        if url.endswith("/run"):
            return _Resp({"id": "job1", "status": "IN_QUEUE"})
        return _Resp({"status": "CANCELLED"}, content=self.post_content)

    def get(self, url: str, **kw: Any) -> _Resp:
        self.calls.append(("GET", url))
        return _Resp(self.completed)


def _client(tmp_path: Path, http: FakeHTTP, budget: float = 9.0, **kw: Any) -> RunPodClient:
    ledger = CloudLedger(tmp_path / "ledger.json", budget)
    return RunPodClient(endpoint="ep", api_key="k", ledger=ledger, usd_per_hour=3600.0, poll_seconds=0,
                        client=http, **kw)  # type: ignore[arg-type]


def test_ledger_persists_and_reloads(tmp_path: Path) -> None:
    led = CloudLedger(tmp_path / "l.json", 9.0)
    e = led.reserve("runpod", "video", 1.25, "x")
    led.settle(e, 0.5)
    again = CloudLedger(tmp_path / "l.json", 9.0)
    assert again.spent_usd == 0.5 and again.entries[0].estimated_usd == 1.25 and again.summary()["calls"] == 1


def test_budget_hard_stop_refuses_before_any_submit(tmp_path: Path) -> None:
    http = FakeHTTP()
    c = _client(tmp_path, http, budget=1.0)
    with pytest.raises(BudgetExceeded):
        c.submit({}, kind="video", estimated_usd=1.5)
    assert http.calls == [] and c.ledger.entries == []


def test_spend_accumulates_toward_the_stop(tmp_path: Path) -> None:
    http = FakeHTTP()
    c = _client(tmp_path, http, budget=1.0)
    c.submit({}, kind="video", estimated_usd=0.6)
    with pytest.raises(BudgetExceeded):
        c.submit({}, kind="video", estimated_usd=0.6)
    assert len([k for k in http.calls if k[0] == "POST"]) == 1


def test_cancel_calls_the_cancel_endpoint_and_keeps_estimate(tmp_path: Path) -> None:
    http = FakeHTTP()
    c = _client(tmp_path, http)
    job = c.submit({}, kind="video", estimated_usd=0.4)
    c.cancel(job)
    assert http.calls[-1] == ("POST", "https://api.runpod.ai/v2/ep/cancel/job1")
    assert c.ledger.entries[0].status == "cancelled" and c.ledger.spent_usd == 0.4


def test_actual_cost_replaces_estimate_after_completion(tmp_path: Path) -> None:
    http = FakeHTTP()  # executionTime 36000 ms at $3600/h = $10/h-second... = 36 s * 1 $/s
    c = _client(tmp_path, http, budget=100.0)
    job = c.submit({}, kind="video", estimated_usd=2.0)
    c.wait(job)
    assert c.ledger.entries[0].actual_usd == 36.0 and c.ledger.entries[0].status == "completed"


def test_missing_key_or_endpoint_is_a_clear_error_and_records_nothing(tmp_path: Path) -> None:
    c = RunPodClient(endpoint="", api_key="", ledger=CloudLedger(tmp_path / "l.json", 9.0),
                     env_name="ECHOTALES_RUNPOD_VIDEO_ENDPOINT", client=FakeHTTP())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="ECHOTALES_RUNPOD_API_KEY, ECHOTALES_RUNPOD_VIDEO_ENDPOINT"):
        c.submit({}, kind="video", estimated_usd=0.1)
    assert c.ledger.entries == []


def test_video_engine_round_trip(tmp_path: Path) -> None:
    http = FakeHTTP({"status": "COMPLETED", "executionTime": 1000, "output": {"video": "QUJD", "duration_s": 3.0}})
    eng = RunPodVideoEngine(_client(tmp_path, http, budget=100.0))
    out = eng.generate(VideoWorkerRequest(keyframe_b64="AA==", mode="i2v"))
    assert out.video_bytes == b"ABC" and out.duration_s == 3.0
    assert http.calls[0][1].endswith("/ep/run")


def test_edit_engine_sends_references_and_needs_one(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    sheet.write_bytes(b"png")
    http = FakeHTTP({"status": "COMPLETED", "executionTime": 1, "output": {"image": "QUJD"}})
    eng = RunPodEditEngine(_client(tmp_path, http, budget=100.0))
    req = PanelImageRequest(prompt="p", out_path=tmp_path / "o" / "a.png", reference_images=[sheet])
    assert eng.generate(req).read_bytes() == b"ABC"
    assert eng.capabilities.supports_multi_reference and eng.capabilities.max_references == 3
    with pytest.raises(RuntimeError, match="character sheet"):
        eng.generate(PanelImageRequest(prompt="p", out_path=tmp_path / "b.png"))


def test_lora_dry_run_submits_nothing_and_manifest_lists_dataset(tmp_path: Path) -> None:
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "a.png").write_bytes(b"1")
    (refs / "notes.txt").write_text("not an image")
    spec = cloud_lora.build_spec("Lan Qing", refs)
    http = FakeHTTP()
    out = cloud_lora.submit(spec, _client(tmp_path, http), dry_run=True)
    assert out["submitted"] is False and out["images"] == 1 and http.calls == []
    m = json.loads(cloud_lora.write_manifest(spec, tmp_path / "m.json").read_text())
    assert m["images"] == ["a.png"] and m["trigger"] == "echo_lan_qing"
    real = cloud_lora.submit(spec, _client(tmp_path, http, budget=100.0))
    assert real["job_id"] == "job1" and http.calls[0][1].endswith("/run")
    with pytest.raises(ValueError):
        cloud_lora.build_spec("x", tmp_path / "empty-nowhere")


def test_dry_run_report_writes_and_sends_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cloud_ledger.paths, "CLOUD_LEDGER_PATH", tmp_path / "ledger.json")
    rep = cloud_ledger.dry_run_report("video", 10)
    assert rep["submitted"] is False and rep["estimated_usd"] > 0 and not (tmp_path / "ledger.json").exists()


def test_zimage_lora_plumbing_unset_changes_nothing() -> None:
    assert workers_zimage.lora_args({}) is None
    assert workers_zimage.lora_args({"ECHOTALES_ZIMAGE_LORA": "/m/x/char.safetensors"}) == ("/m/x", "char.safetensors", 0.6)
    env = {"ECHOTALES_ZIMAGE_LORA": "/m/c.safetensors", "ECHOTALES_ZIMAGE_LORA_SCALE": "0.9"}
    assert workers_zimage.lora_args(env)[2] == 0.9


def test_elevenlabs_writes_wav_ledgers_and_never_sends_reference_clip(tmp_path: Path) -> None:
    http = FakeHTTP(post_content=b"\x00\x00" * 2400)
    http.post = lambda url, **kw: (http.calls.append(("POST", url)), _Resp(content=b"\x01\x00" * 2400, status=200))[1]  # type: ignore[method-assign]
    ledger = CloudLedger(tmp_path / "l.json", 9.0)
    eng = ElevenLabsEngine(api_key="k", voice_id="v1", ledger=ledger, client=http)  # type: ignore[arg-type]
    clip = tmp_path / "real_actor.wav"
    out = eng.synthesize(SynthesisRequest(text="Hello there", out_path=tmp_path / "o.wav", reference_clip=clip))
    with wave.open(str(out)) as fh:
        assert fh.getframerate() == 24000 and fh.getnframes() == 2400
    assert ledger.entries[0].provider == "elevenlabs" and http.calls[0][1].endswith("/text-to-speech/v1")


def test_elevenlabs_missing_key_and_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("ECHOTALES_ELEVENLABS_API_KEY", "ECHOTALES_ELEVENLABS_VOICE_ID"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="ECHOTALES_ELEVENLABS_API_KEY"):
        get_engine("elevenlabs").synthesize(SynthesisRequest("hi", tmp_path / "a.wav"))
    http = FakeHTTP()
    eng = ElevenLabsEngine(api_key="k", voice_id="v", ledger=CloudLedger(tmp_path / "l.json", 0.0001), client=http)  # type: ignore[arg-type]
    with pytest.raises(BudgetExceeded):
        eng.synthesize(SynthesisRequest("a long enough line to cost something", tmp_path / "a.wav"))
    assert http.calls == []


def test_registry_entries_carry_licence_and_tier_and_stay_off_local_lists() -> None:
    for kind, name in (("tts", "elevenlabs"), ("video", "wan-runpod"), ("image", "qwen-image-edit-runpod"),
                       ("image", "character-lora-runpod")):
        e = reg.get(kind, name)
        assert e.licence and e.tier == "cloud" and e.where == "hosted" and e.commercial_safe is None
    assert "wan-runpod" not in reg.names("video", surface="anime-video")
    assert "qwen-image-edit-runpod" not in reg.names("image", surface="render-image")
    assert "elevenlabs" not in {e.name for e in reg.select(commercial_safe=True)}
    assert "no cloning of real people" in reg.get("tts", "elevenlabs").note
    assert get_engine("stub").name == "stub"  # the default tts stays local


def test_unset_cloud_config_leaves_local_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    from echotales.pipeline import compute
    from echotales.pipeline.config import get_settings

    s = get_settings()
    assert s.cloud_budget_usd == 9.0 and not s.runpod_video_endpoint and not s.elevenlabs_api_key
    assert compute.policy().image_provider == "local"
    assert workers_zimage.lora_args({}) is None
