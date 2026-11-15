"""The worker script and the local engine's parent side, without torch and without a GPU."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from echotales.pipeline import compute
from echotales.pipeline.video import local, ltx_worker
from echotales.pipeline.video.local import ClipRequest, LocalLTXEngine, VideoEnvError
from PIL import Image


def _job(tmp_path: Path, **over) -> dict:
    img = tmp_path / "s.png"
    Image.new("RGB", (64, 96), (9, 9, 9)).save(img)
    clip = {"id": "c1", "start_image": str(img), "end_image": None, "prompt": "p", "frames": 17, "fps": 24,
            "width": 64, "height": 96, "seed": 1, "output": str(tmp_path / "o.mp4")}
    clip.update(over)
    return {"version": 1, "mode": "batched", "embed_cache_dir": str(tmp_path / "e"), "clips": [clip]}


class TestJobValidation:
    def test_a_good_job_passes(self, tmp_path) -> None:
        assert ltx_worker.validate_job(_job(tmp_path))["clips"][0]["id"] == "c1"

    @pytest.mark.parametrize(("over", "match"), [
        ({"frames": 60}, "8k\\+1"), ({"frames": 5}, "8k\\+1"), ({"width": 100}, "multiple of 32"),
        ({"fps": 0}, "fps"), ({"prompt": 3}, "prompt"), ({"start_image": "/nope.png"}, "does not exist"),
        ({"seed": None, "output": None}, "two clips|missing"),
    ])
    def test_a_bad_clip_is_named(self, tmp_path, over, match) -> None:
        job = _job(tmp_path, **over)
        if "seed" in over:
            del job["clips"][0]["seed"]
        with pytest.raises(ltx_worker.JobError, match=match):
            ltx_worker.validate_job(job)

    def test_job_level_errors(self, tmp_path) -> None:
        for bad, match in [({"version": 9}, "version"), ({"mode": "x"}, "mode"), ({"clips": []}, "non-empty"),
                           ({"embed_cache_dir": ""}, "embed_cache_dir")]:
            with pytest.raises(ltx_worker.JobError, match=match):
                ltx_worker.validate_job({**_job(tmp_path), **bad})

    def test_duplicate_ids_and_outputs(self, tmp_path) -> None:
        job = _job(tmp_path)
        job["clips"].append(dict(job["clips"][0]))
        with pytest.raises(ltx_worker.JobError, match="duplicate id"):
            ltx_worker.validate_job(job)
        job["clips"][1]["id"] = "c2"
        with pytest.raises(ltx_worker.JobError, match="two clips write"):
            ltx_worker.validate_job(job)

    def test_embedding_key_is_per_prompt_and_stable(self) -> None:
        assert ltx_worker.embed_key("a") == ltx_worker.embed_key("a") != ltx_worker.embed_key("b")


class TestWorkerProcess:
    def _run(self, *args: str):
        return subprocess.run([sys.executable, str(local.WORKER_PATH), *args], capture_output=True, text=True)

    def test_importing_the_worker_does_not_import_torch(self) -> None:
        code = "import sys; import echotales.pipeline.video.ltx_worker as w; print('torch' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        assert out.stdout.strip() == "False"

    def test_validate_only_runs_standalone_without_the_package(self, tmp_path) -> None:
        job = tmp_path / "job.json"
        job.write_text(json.dumps(_job(tmp_path)))
        r = subprocess.run([sys.executable, "-I", str(local.WORKER_PATH), "--job", str(job), "--validate-only"],
                           capture_output=True, text=True)
        assert r.returncode == 0 and "job ok: 1 clips" in r.stdout

    def test_an_invalid_job_exits_2_and_writes_the_reason(self, tmp_path) -> None:
        job, res = tmp_path / "job.json", tmp_path / "res.json"
        job.write_text(json.dumps(_job(tmp_path, frames=60)))
        r = self._run("--job", str(job), "--result", str(res))
        assert r.returncode == 2
        data = json.loads(res.read_text())
        assert data["ok"] is False and "8k+1" in data["error"]

    def test_unreadable_job_and_missing_result_argument(self, tmp_path) -> None:
        job = tmp_path / "job.json"
        job.write_text("{nope")
        assert self._run("--job", str(job), "--result", str(tmp_path / "r.json")).returncode == 2
        assert self._run("--job", str(job)).returncode == 2  # argparse: --result required

    def test_the_ram_watcher_aborts_with_a_reason_instead_of_swapping(self, tmp_path) -> None:
        res = tmp_path / "res.json"
        code = textwrap.dedent(f"""
            import time, sys
            sys.path.insert(0, {str(local.WORKER_PATH.parent)!r})
            import ltx_worker as w
            result = {{"ok": True, "error": None, "clips": []}}
            w.RamWatch(1e6, result, {str(res)!r}).start()
            time.sleep(5)
        """)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
        assert r.returncode == ltx_worker.RAM_ABORT_EXIT
        data = json.loads(res.read_text())
        assert data["ok"] is False and "fell under" in data["error"]


FAKE_WORKER = textwrap.dedent("""
    import json, sys, time
    a = sys.argv
    job = json.load(open(a[a.index("--job") + 1]))
    mode = job["clips"][0]["prompt"]
    if mode == "hang":
        time.sleep(60)
    print("PROGRESS " + json.dumps({"event": "loaded"}), flush=True)
    clips = []
    for i, c in enumerate(job["clips"]):
        ok = mode != "partial" or i == 0
        if ok:
            open(c["output"], "wb").write(b"mp4")
        clips.append({"id": c["id"], "ok": ok, "error": None if ok else "denoise: OutOfMemoryError",
                      "frames_written": c["frames"] if ok else 0, "seconds": {"denoise": 1.5}, "peak_vram_gb": 6.9})
    if mode != "crash":
        json.dump({"ok": True, "error": None, "mode": job["mode"], "min_avail_ram_gb": 4.2, "stages": [],
                   "clips": clips}, open(a[a.index("--result") + 1], "w"))
""")


class TestLocalEngine:
    def _requests(self, tmp_path: Path, prompt: str, n: int = 2) -> list[ClipRequest]:
        img = tmp_path / "s.png"
        Image.new("RGB", (64, 96)).save(img)
        return [ClipRequest(f"c{i}", img, prompt, 17, 24, 64, 96, i, tmp_path / f"o{i}.mp4") for i in range(n)]

    def _engine(self, tmp_path, monkeypatch, **kw) -> LocalLTXEngine:
        script = tmp_path / "fake_worker.py"
        script.write_text(FAKE_WORKER)
        monkeypatch.setattr(local, "WORKER_PATH", script)
        return LocalLTXEngine(python=sys.executable, work_dir=tmp_path / "w", check_resources=False, **kw)

    def test_unset_interpreter_names_the_setup_script(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv(local.ENV_VIDEO_PYTHON, raising=False)
        monkeypatch.chdir(tmp_path)  # no .env here
        with pytest.raises(VideoEnvError, match=r"scripts/setup_video\.sh"):
            LocalLTXEngine(work_dir=tmp_path / "w").generate_clips(self._requests(tmp_path, "x"))

    def test_a_missing_interpreter_names_the_setup_script(self, tmp_path) -> None:
        eng = LocalLTXEngine(python=str(tmp_path / "nope"), work_dir=tmp_path / "w")
        with pytest.raises(VideoEnvError, match=r"setup_video\.sh"):
            eng.generate_clips(self._requests(tmp_path, "x"))

    def test_the_interpreter_can_come_from_dot_env(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv(local.ENV_VIDEO_PYTHON, raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(f'OTHER=1\n{local.ENV_VIDEO_PYTHON}="{sys.executable}"\n')
        assert LocalLTXEngine(work_dir=tmp_path / "w").python == sys.executable

    def test_results_are_mapped_back_per_clip(self, tmp_path, monkeypatch) -> None:
        res = self._engine(tmp_path, monkeypatch).generate_clips(self._requests(tmp_path, "ok"))
        assert [r.ok for r in res] == [True, True]
        assert res[0].peak_vram_gb == 6.9 and res[0].seconds == {"denoise": 1.5} and res[0].frames_written == 17

    def test_a_failed_clip_keeps_its_own_error(self, tmp_path, monkeypatch) -> None:
        res = self._engine(tmp_path, monkeypatch).generate_clips(self._requests(tmp_path, "partial"))
        assert [r.ok for r in res] == [True, False] and "OutOfMemory" in res[1].error

    def test_a_worker_that_dies_without_a_result_fails_every_clip(self, tmp_path, monkeypatch) -> None:
        res = self._engine(tmp_path, monkeypatch).generate_clips(self._requests(tmp_path, "crash"))
        assert not any(r.ok for r in res) and "no result file" in res[0].error

    def test_a_silent_worker_is_killed_at_the_clip_timeout(self, tmp_path, monkeypatch) -> None:
        eng = self._engine(tmp_path, monkeypatch, clip_timeout_s=1.5)
        res = eng.generate_clips(self._requests(tmp_path, "hang", n=1))
        assert not res[0].ok and "killed" in res[0].error

    def test_an_invalid_batch_is_refused_before_a_process_starts(self, tmp_path, monkeypatch) -> None:
        reqs = self._requests(tmp_path, "ok")
        reqs[0].frames = 60
        with pytest.raises(ltx_worker.JobError):
            self._engine(tmp_path, monkeypatch).generate_clips(reqs)

    @pytest.mark.parametrize(("asked", "got"), [(97, 97), (72, 65), (60, 57), (10, 9), (3, 9)])
    def test_frames_snap_down_to_8k_plus_1(self, asked, got) -> None:
        assert local.snap_frames_8k1(asked) == got


class TestResourceCheck:
    def test_a_busy_gpu_refuses_above_500_mib(self, monkeypatch) -> None:
        monkeypatch.setattr(compute.gpu, "gpu_status", lambda: compute.gpu.GpuStatus("g", 800, 8188))
        monkeypatch.setattr(compute, "available_ram_mb", lambda: 6000)
        msg = compute.resource_refusal("ltx-local")
        assert msg and "busy" in msg

    def test_low_ram_refuses(self, monkeypatch) -> None:
        monkeypatch.setattr(compute.gpu, "gpu_status", lambda: compute.gpu.GpuStatus("g", 15, 8188))
        monkeypatch.setattr(compute, "available_ram_mb", lambda: 1000)
        assert "RAM" in compute.resource_refusal("ltx-local")

    def test_a_free_card_and_enough_ram_pass(self, monkeypatch) -> None:
        monkeypatch.setattr(compute.gpu, "gpu_status", lambda: compute.gpu.GpuStatus("g", 15, 8188))
        monkeypatch.setattr(compute, "available_ram_mb", lambda: 6000)
        assert compute.resource_refusal("ltx-local") is None

    def test_no_gpu_refuses(self, monkeypatch) -> None:
        monkeypatch.setattr(compute.gpu, "gpu_status", lambda: None)
        assert "NVIDIA" in compute.resource_refusal("ltx-local")
