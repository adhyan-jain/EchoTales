"""Device and encoder selection: heavy work goes to CUDA / NVENC when they are there, and falls back cleanly when not.

Torch, the ffmpeg probe and the model libraries are all faked: these assert the choice, not that a GPU exists on the
machine running them. The real GPU is exercised by the smoke tests recorded in EVOLUTION 4.189."""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest
from echotales.pipeline import hwaccel
from echotales.pipeline.comic import ocr as comic_ocr
from echotales.pipeline.render import compose
from echotales.pipeline.video import clip_gate
from echotales.pipeline.voice import engine as voice_engine
from echotales.pipeline.voice import qa


def _fake_torch(*, cuda: bool, free_gib: float = 6.0) -> types.ModuleType:
    torch = types.ModuleType("torch")
    torch.float16 = "float16"  # type: ignore[attr-defined]
    torch.float32 = "float32"  # type: ignore[attr-defined]
    torch.cuda = types.SimpleNamespace(  # type: ignore[attr-defined]
        is_available=lambda: cuda, empty_cache=lambda: None, mem_get_info=lambda: (int(free_gib * 2**30), 8 * 2**30)
    )
    return torch


@pytest.fixture
def cuda(monkeypatch: pytest.MonkeyPatch):
    def set_cuda(available: bool, free_gib: float = 6.0) -> None:
        monkeypatch.setitem(sys.modules, "torch", _fake_torch(cuda=available, free_gib=free_gib))

    return set_cuda


class TestPickDevice:
    def test_cuda_when_available(self, cuda) -> None:
        cuda(True)
        assert hwaccel.pick_device() == "cuda"
        assert hwaccel.pick_device("auto") == "cuda"

    def test_cpu_only_when_there_is_no_cuda(self, cuda) -> None:
        cuda(False)
        assert hwaccel.pick_device() == "cpu"

    def test_an_explicit_cuda_without_cuda_falls_back_instead_of_dying_in_the_loader(self, cuda) -> None:
        cuda(False)
        assert hwaccel.pick_device("cuda") == "cpu"
        assert hwaccel.pick_device("cuda:0") == "cpu"

    def test_an_explicit_cpu_is_honoured_even_with_cuda(self, cuda) -> None:
        cuda(True)
        assert hwaccel.pick_device("cpu") == "cpu"

    def test_no_torch_at_all_is_no_cuda(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "torch", None)  # an import of None raises ImportError
        assert hwaccel.cuda_available() is False


class TestVideoEncoder:
    @pytest.fixture(autouse=True)
    def _probe(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("ECHOTALES_VIDEO_ENCODER", raising=False)
        hwaccel.video_encoder.cache_clear()
        monkeypatch.setattr(hwaccel.shutil, "which", lambda name: "/usr/bin/ffmpeg")
        yield
        hwaccel.video_encoder.cache_clear()

    def _probe_returns(self, monkeypatch: pytest.MonkeyPatch, code: int) -> list[list[str]]:
        calls: list[list[str]] = []

        def run(cmd, **_kw):  # type: ignore[no-untyped-def]
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, code, b"", b"")

        monkeypatch.setattr(hwaccel.subprocess, "run", run)
        return calls

    def test_nvenc_when_a_real_encode_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._probe_returns(monkeypatch, 0)
        assert hwaccel.video_encoder() == "h264_nvenc"
        assert "h264_nvenc" in calls[0]

    def test_libx264_when_the_probe_encode_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An ffmpeg that lists the encoder but has no driver or no free session must not be trusted."""
        self._probe_returns(monkeypatch, 1)
        assert hwaccel.video_encoder() == "libx264"

    def test_libx264_when_the_probe_cannot_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a, **_k):  # type: ignore[no-untyped-def]
            raise subprocess.TimeoutExpired("ffmpeg", 20)

        monkeypatch.setattr(hwaccel.subprocess, "run", boom)
        assert hwaccel.video_encoder() == "libx264"

    def test_libx264_without_ffmpeg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(hwaccel.shutil, "which", lambda name: None)
        assert hwaccel.video_encoder() == "libx264"

    def test_the_override_forces_cpu_without_probing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._probe_returns(monkeypatch, 0)
        monkeypatch.setenv("ECHOTALES_VIDEO_ENCODER", "libx264")
        assert hwaccel.video_encoder() == "libx264"
        assert calls == []

    def test_the_probe_runs_once_per_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._probe_returns(monkeypatch, 0)
        hwaccel.video_encoder()
        hwaccel.video_encoder()
        hwaccel.h264_args()
        assert len(calls) == 1

    def test_nvenc_arguments_are_constant_quality_yuv420p(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._probe_returns(monkeypatch, 0)
        args = hwaccel.h264_args(preset="ultrafast")
        assert args[:2] == ["-c:v", "h264_nvenc"]
        i = args.index("-rc")
        assert args[i:i + 6] == ["-rc", "vbr", "-cq", "19", "-b:v", "0"]
        assert args[-2:] == ["-pix_fmt", "yuv420p"]
        assert "ultrafast" not in args  # an x264 preset name means nothing to NVENC

    def test_x264_arguments_keep_the_old_quality(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._probe_returns(monkeypatch, 1)
        assert hwaccel.h264_args() == ["-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p"]
        assert "ultrafast" in hwaccel.h264_args(preset="ultrafast")


def test_compose_segments_and_mux_take_their_codec_from_hwaccel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every ffmpeg call that writes an H.264 file goes through `h264_args`, including the per-shot stills."""
    seen: list[list[str]] = []
    monkeypatch.setattr(compose, "h264_args", lambda **_k: ["-c:v", "h264_nvenc", "-pix_fmt", "yuv420p"])
    monkeypatch.setattr(compose, "_run_ffmpeg", lambda args: seen.append(list(args)))
    monkeypatch.setattr(compose, "_zoompan_filter", lambda *a, **k: "null")
    still = types.SimpleNamespace(kind="still", asset_path="a.png", duration=1.0)
    clip = types.SimpleNamespace(kind="clip", asset_path=str(tmp_path), duration=1.0)
    compose._render_segment(still, tmp_path / "s.mp4")  # type: ignore[arg-type]
    compose._render_segment(clip, tmp_path / "c.mp4")  # type: ignore[arg-type]
    assert len(seen) == 2 and all("h264_nvenc" in call for call in seen)

    seen.clear()
    monkeypatch.setattr(compose, "concatenate_audio", lambda *_a, **_k: None)
    (tmp_path / "x.ass").write_text("", encoding="utf-8")
    eng = compose.FfmpegComposeEngine(captions_path=tmp_path / "x.ass")
    eng.assemble([tmp_path / "s.mp4"], [], tmp_path / "out.mp4", tmp_path)
    assert "h264_nvenc" in seen[-1] and "libx264" not in seen[-1]


class TestWhisper:
    def _run(self, monkeypatch: pytest.MonkeyPatch, **kw) -> dict:  # type: ignore[no-untyped-def]
        captured: dict = {}

        def fake_pipeline(task, **opts):  # type: ignore[no-untyped-def]
            captured.update(opts)
            return lambda audio, **_k: {"text": " hello "}

        monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(pipeline=fake_pipeline))
        monkeypatch.setattr(qa, "read_mono", lambda p: ([0.0] * 16, 16000))
        assert qa.whisper_transcriber(**kw)([Path("a.wav")]) == ["hello"]
        return captured

    def test_whisper_runs_on_cuda_in_fp16(self, cuda, monkeypatch: pytest.MonkeyPatch) -> None:
        cuda(True)
        opts = self._run(monkeypatch)
        assert opts["device"] == "cuda" and opts["dtype"] == "float16"

    def test_whisper_falls_back_to_cpu_fp32_without_cuda(self, cuda, monkeypatch: pytest.MonkeyPatch) -> None:
        cuda(False)
        opts = self._run(monkeypatch)
        assert opts["device"] == "cpu" and opts["dtype"] == "float32"


class TestChatterbox:
    def _device(self, monkeypatch: pytest.MonkeyPatch, **kw) -> str:  # type: ignore[no-untyped-def]
        seen: dict = {}

        class FakeTTS:
            sr = 24000

            @classmethod
            def from_pretrained(cls, device):  # type: ignore[no-untyped-def]
                seen["device"] = device
                return cls()

        monkeypatch.setitem(sys.modules, "chatterbox", types.ModuleType("chatterbox"))
        monkeypatch.setitem(sys.modules, "chatterbox.tts", types.SimpleNamespace(ChatterboxTTS=FakeTTS))
        voice_engine.get_engine("chatterbox", **kw)._ensure_model()  # type: ignore[attr-defined]
        return seen["device"]

    def test_defaults_to_cuda(self, cuda, monkeypatch: pytest.MonkeyPatch) -> None:
        cuda(True)
        assert self._device(monkeypatch) == "cuda"

    def test_cpu_only_without_cuda(self, cuda, monkeypatch: pytest.MonkeyPatch) -> None:
        cuda(False)
        assert self._device(monkeypatch) == "cpu"


class TestClipGate:
    def _device(self, monkeypatch: pytest.MonkeyPatch) -> str:
        class FakeModel:
            dtype = "x"

            def to(self, device):  # type: ignore[no-untyped-def]
                return self

            def eval(self):  # type: ignore[no-untyped-def]
                return self

        fake = types.SimpleNamespace(
            CLIPModel=types.SimpleNamespace(from_pretrained=lambda *a, **k: FakeModel()),
            CLIPProcessor=types.SimpleNamespace(from_pretrained=lambda *a, **k: object()),
        )
        monkeypatch.setitem(sys.modules, "transformers", fake)
        emb = clip_gate.ClipImageEmbedder()
        emb._load()
        return emb.device

    def test_cuda_with_room(self, cuda, monkeypatch: pytest.MonkeyPatch) -> None:
        cuda(True, free_gib=6.0)
        assert self._device(monkeypatch) == "cuda"

    def test_cuda_even_while_ollama_holds_part_of_the_card(self, cuda, monkeypatch: pytest.MonkeyPatch) -> None:
        """The old rule needed under 500 MiB used, so the gate went to the CPU whenever a model was still loaded."""
        cuda(True, free_gib=3.0)
        assert self._device(monkeypatch) == "cuda"

    def test_cpu_when_the_card_cannot_hold_it_or_is_absent(self, cuda, monkeypatch: pytest.MonkeyPatch) -> None:
        cuda(True, free_gib=0.5)
        assert self._device(monkeypatch) == "cpu"
        cuda(False)
        assert self._device(monkeypatch) == "cpu"


class TestRapidOcr:
    def _kwargs(self, monkeypatch: pytest.MonkeyPatch, providers: list[str]) -> tuple[dict, str]:
        seen: dict = {}

        class FakeRapid:
            def __init__(self, **kw):  # type: ignore[no-untyped-def]
                seen.update(kw)

        monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", types.SimpleNamespace(RapidOCR=FakeRapid))
        monkeypatch.setitem(sys.modules, "onnxruntime", types.SimpleNamespace(get_available_providers=lambda: providers))
        return seen, comic_ocr.RapidOcr().device

    def test_cuda_when_onnxruntime_has_the_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen, device = self._kwargs(monkeypatch, ["CUDAExecutionProvider", "CPUExecutionProvider"])
        assert device == "cuda" and seen == {"det_use_cuda": True, "cls_use_cuda": True, "rec_use_cuda": True}

    def test_cpu_on_the_stock_wheel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen, device = self._kwargs(monkeypatch, ["CPUExecutionProvider"])
        assert device == "cpu" and not any(seen.values())
