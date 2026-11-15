"""The local LTX-Video engine: a batch of clips through one worker subprocess.

`workers_contract.VideoWorkerRequest` carries one base64 keyframe and returns one base64 MP4, which cannot
express "generate these eight clips in one process so the text encoder and the transformer load once", and
base64 over a pipe for 4 s clips is waste when both sides share a disk. So the composer talks to a
`ClipEngine` (below) that takes a list of file-based requests; the contract and its stub are untouched and
keep serving the cloud-shaped engines.

The model runs in a different interpreter (`ECHOTALES_VIDEO_PYTHON`, built by `scripts/setup_video.sh`)
because its libraries conflict with the main environment's and because 8 GB cannot hold the model between
clips; see `ltx_worker.py`. Everything here is the parent's side: resource check, job file, subprocess
supervision, result parsing.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from echotales.pipeline.compute import resource_refusal
from echotales.pipeline.video import ltx_worker

log = logging.getLogger(__name__)

ENV_VIDEO_PYTHON = "ECHOTALES_VIDEO_PYTHON"
ENGINE_NAME = "ltx-local"
#: Seconds with no PROGRESS line before a worker is killed. One clip's slowest stage measured 70 s (cold
#: reload plus denoise); the first line only arrives after the text encoder and model load, which was
#: 50 s cold for the encoder alone, so 400 leaves a margin without hiding a hang for long.
DEFAULT_CLIP_TIMEOUT_S = 400.0
WORKER_PATH = Path(ltx_worker.__file__).resolve()


class VideoEnvError(RuntimeError):
    """The local video engine cannot start; the message names the fix."""


@dataclass(slots=True)
class ClipRequest:
    clip_id: str
    start_image: Path
    prompt: str
    frames: int
    fps: int
    width: int
    height: int
    seed: int
    output: Path
    end_image: Path | None = None


@dataclass(slots=True)
class ClipResult:
    clip_id: str
    ok: bool
    error: str | None = None
    output: Path | None = None
    frames_written: int = 0
    seconds: dict[str, float] = field(default_factory=dict)
    peak_vram_gb: float | None = None


class ClipEngine(Protocol):
    """What the composer needs from a video engine."""

    engine_id: str

    def model_identity(self) -> str:
        """Names the weights, so a changed model file changes every clip's cache key."""
        ...

    def snap_frames(self, frames: int) -> int:
        """The nearest frame count the engine can make that is not above `frames`."""
        ...

    def generate_clips(self, requests: list[ClipRequest]) -> list[ClipResult]: ...


def snap_frames_8k1(frames: int) -> int:
    """LTX makes 8k+1 frames; 97 -> 97, 60 -> 57. Rounds down so a clip never outruns its shot."""
    return max(9, (max(frames, 1) - 1) // 8 * 8 + 1)


def _env_value(name: str) -> str:
    """The variable from the environment, else from `.env` in the working directory.

    `config.Settings` reads `.env` for its own fields without exporting it, and this value is the
    interpreter path the README tells people to put in `.env`, so it must work from there too.
    """
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in Path(".env").read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("\"'")
    except OSError:
        pass
    return ""


def _hf_blob(repo: str, filename: str) -> str:
    """The content hash of a cached model file: the blob's file name, without importing huggingface_hub."""
    root = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub"
    folder = root / ("models--" + repo.replace("/", "--")) / "snapshots"
    for snap in sorted(folder.glob("*"), reverse=True) if folder.is_dir() else []:
        f = snap / filename
        if f.exists():
            return f"{filename}@{f.resolve().name}"
    return f"{filename}@not-in-cache"


class LocalLTXEngine:
    """LTX-Video 2B 0.9.8 distilled, via `ltx_worker.py` in the video environment."""

    engine_id = ENGINE_NAME

    def __init__(
        self,
        *,
        python: str | None = None,
        mode: str = "batched",
        work_dir: str | Path,
        clip_timeout_s: float = DEFAULT_CLIP_TIMEOUT_S,
        min_free_ram_gb: float = 2.0,
        check_resources: bool = True,
    ) -> None:
        self.python = python or _env_value(ENV_VIDEO_PYTHON)
        self.mode = mode
        self.work_dir = Path(work_dir)
        self.clip_timeout_s = clip_timeout_s
        self.min_free_ram_gb = min_free_ram_gb
        self.check_resources = check_resources
        #: Filled by the last `generate_clips`: the worker's stage table, for the run record.
        self.last_run: dict = {}

    def model_identity(self) -> str:
        return f"{_hf_blob(ltx_worker.TRANSFORMER_REPO, ltx_worker.TRANSFORMER_FILE)}|{ltx_worker.MODEL_TAG}"

    def snap_frames(self, frames: int) -> int:
        return snap_frames_8k1(frames)

    def _interpreter(self) -> str:
        if not self.python:
            raise VideoEnvError(
                f"{ENV_VIDEO_PYTHON} is not set. Run scripts/setup_video.sh to create .venv-video and set "
                f"{ENV_VIDEO_PYTHON}=<repo>/.venv-video/bin/python in .env"
            )
        if not Path(self.python).exists():
            raise VideoEnvError(
                f"{ENV_VIDEO_PYTHON}={self.python!r} does not exist; run scripts/setup_video.sh to create it"
            )
        return self.python

    def generate_clips(self, requests: list[ClipRequest]) -> list[ClipResult]:
        if not requests:
            return []
        python = self._interpreter()
        if self.check_resources:
            refusal = resource_refusal(ENGINE_NAME)
            if refusal:
                raise VideoEnvError(str(refusal))
        self.work_dir.mkdir(parents=True, exist_ok=True)
        job_path, result_path = self.work_dir / "job.json", self.work_dir / "result.json"
        result_path.unlink(missing_ok=True)
        job = {
            "version": ltx_worker.JOB_VERSION, "mode": self.mode,
            "embed_cache_dir": str(self.work_dir.parent / "embeds"), "min_free_ram_gb": self.min_free_ram_gb,
            "clips": [
                {"id": r.clip_id, "start_image": str(r.start_image),
                 "end_image": str(r.end_image) if r.end_image else None, "prompt": r.prompt,
                 "frames": r.frames, "fps": r.fps, "width": r.width, "height": r.height, "seed": r.seed,
                 "output": str(r.output)}
                for r in requests
            ],
        }
        ltx_worker.validate_job(job)  # fail here, in the main environment, not after a model load
        job_path.write_text(json.dumps(job, indent=1), encoding="utf-8")

        stalled = self._supervise([python, str(WORKER_PATH), "--job", str(job_path), "--result", str(result_path)])
        return self._results(requests, result_path, stalled)

    def _supervise(self, cmd: list[str]) -> str | None:
        """Run the worker, stream its output to the log, kill it if it goes silent. Returns a reason or None."""
        env = {**os.environ, "HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"}
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, bufsize=1
        )
        lines: queue.Queue[str | None] = queue.Queue()

        def pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.put(line.rstrip("\n"))
            lines.put(None)

        threading.Thread(target=pump, daemon=True).start()
        last = time.monotonic()
        while True:
            try:
                line = lines.get(timeout=1.0)
            except queue.Empty:
                if time.monotonic() - last > self.clip_timeout_s:
                    proc.kill()
                    proc.wait()
                    return f"worker silent for {self.clip_timeout_s:.0f}s, killed"
                continue
            if line is None:
                break
            last = time.monotonic()
            log.info("ltx-worker: %s", line)
            if line.startswith("PROGRESS") or line.startswith("!!"):
                print(f"[ltx] {line}", file=sys.stderr, flush=True)  # stdout carries --json
        proc.wait()
        return None

    def _results(self, requests: list[ClipRequest], result_path: Path, stalled: str | None) -> list[ClipResult]:
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        self.last_run = {k: data.get(k) for k in ("mode", "stages", "min_avail_ram_gb", "error")}
        by_id = {c["id"]: c for c in data.get("clips", [])}
        why = stalled or data.get("error") or "worker produced no result file"
        out: list[ClipResult] = []
        for r in requests:
            c = by_id.get(r.clip_id)
            ok = bool(c and c.get("ok")) and r.output.exists()
            out.append(ClipResult(
                clip_id=r.clip_id, ok=ok,
                error=None if ok else (c.get("error") if c and c.get("error") else why),
                output=r.output if ok else None, frames_written=int(c["frames_written"]) if c else 0,
                seconds=dict(c.get("seconds", {})) if c else {},
                peak_vram_gb=c.get("peak_vram_gb") if c else None,
            ))
        return out
