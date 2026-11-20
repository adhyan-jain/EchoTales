"""RunPod serverless image generation: the `cloud` compute preset's image engine.

Submits one panel to a RunPod serverless endpoint (`POST /v2/<endpoint>/run`) and polls `/status/<id>` until it
completes, so a slow cold start does not hit the synchronous endpoint's time limit. Configured only by
`ECHOTALES_RUNPOD_API_KEY` and `ECHOTALES_RUNPOD_IMAGE_ENDPOINT` (`pipeline/compute.py`); nothing is read from anywhere
else, and the key is never written into an error message.

**The worker contract.** RunPod endpoints run whatever handler the owner deployed, so this engine fixes the shape it
speaks and accepts the common shapes back:

    request   {"input": {"prompt", "negative_prompt", "width", "height", "seed"}}
    response  {"status": "COMPLETED", "output": <image>}  where <image> is any of
                  "<base64 png>" | {"image": "<b64>"} | {"image_base64": "<b64>"} | {"images": ["<b64>", ...]}
                  | {"images": [{"image": "<b64>"} | {"data": "<b64>"}, ...]}

A `data:image/png;base64,` prefix is accepted. The handler chooses the checkpoint and the sampler: the director writes
NoobAI-style tag prompts (`persona/prompt.py`), so a worker should serve that checkpoint, and the quality tags are the
worker's to add (this engine sets no `quality_prefix`, so the director reserves no budget for one). Reference images are
accepted and ignored, as with the other hosted engines: character consistency rests on the canonical appearance text
repeated in every prompt, which is weaker than image conditioning.

This was written against RunPod's documented serverless API and tested against a mock transport only. No request to
RunPod has been made from this repository (2026-10-18); the first real endpoint is the first real test.
"""

from __future__ import annotations

import base64
import binascii
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from echotales.pipeline.render.contract import RenderBackendCapabilities

if TYPE_CHECKING:
    from echotales.pipeline.render.panels import PanelImageRequest

log = logging.getLogger(__name__)

API_BASE = "https://api.runpod.ai/v2"
_DONE = {"COMPLETED"}
_FAILED = {"FAILED", "CANCELLED", "TIMED_OUT"}


def _first_b64(output: Any) -> str | None:
    """The base64 image string in any shape the docstring lists, or None."""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for key in ("image", "image_base64", "data"):
            if isinstance(output.get(key), str):
                return output[key]
        images = output.get("images")
        if isinstance(images, list) and images:
            return _first_b64(images[0])
        if "output" in output:
            return _first_b64(output["output"])
    return None


@dataclass(slots=True)
class RunPodImageEngine:
    name: str = "runpod"
    api_key: str = ""
    endpoint: str = ""
    #: Total seconds to wait for one panel, cold start included.
    timeout: float = 600.0
    poll_seconds: float = 2.0
    client: httpx.Client | None = None

    @property
    def capabilities(self) -> RenderBackendCapabilities:
        return RenderBackendCapabilities(
            supports_multi_reference=False, max_references=0, supports_img2img=False, supports_lora=False,
            supports_negative_prompt=True, is_hosted=True, model_family="runpod",
        )

    def _config(self) -> tuple[str, str]:
        key, endpoint = self.api_key, self.endpoint
        if not (key and endpoint):
            from echotales.pipeline.compute import policy

            pol = policy()
            key, endpoint = key or pol.runpod_api_key, endpoint or pol.runpod_image_endpoint
        missing = [
            name for name, value in (("ECHOTALES_RUNPOD_API_KEY", key), ("ECHOTALES_RUNPOD_IMAGE_ENDPOINT", endpoint))
            if not value
        ]
        if missing:
            raise RuntimeError(f"the runpod engine needs {', '.join(missing)}; set them in .env (gitignored)")
        return key, endpoint

    def generate(self, request: PanelImageRequest) -> Path:
        key, endpoint = self._config()
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        client = self.client or httpx.Client(timeout=60.0)
        body = {"input": {
            "prompt": request.prompt, "negative_prompt": request.negative_prompt,
            "width": request.width, "height": request.height, "seed": request.seed,
        }}
        try:
            submitted = self._json(client.post(f"{API_BASE}/{endpoint}/run", json=body, headers=headers))
            job_id = submitted.get("id")
            if not job_id:
                raise RuntimeError(f"runpod did not return a job id: {sorted(submitted)}")
            deadline = time.monotonic() + self.timeout
            state = submitted
            while str(state.get("status", "")).upper() not in _DONE | _FAILED:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"runpod job {job_id} did not finish within {self.timeout:.0f}s")
                time.sleep(self.poll_seconds)
                state = self._json(client.get(f"{API_BASE}/{endpoint}/status/{job_id}", headers=headers))
        finally:
            if self.client is None:
                client.close()

        status = str(state.get("status", "")).upper()
        if status in _FAILED:
            raise RuntimeError(f"runpod job {job_id} {status.lower()}: {str(state.get('error', ''))[:300]}")
        encoded = _first_b64(state.get("output"))
        if not encoded:
            raise RuntimeError(f"runpod job {job_id} completed with no image in its output")
        try:
            data = base64.b64decode(encoded.split(",", 1)[-1], validate=False)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError(f"runpod job {job_id} returned an image that is not base64: {exc}") from exc
        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        request.out_path.write_bytes(data)
        return request.out_path

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        if response.status_code in (401, 403):
            raise RuntimeError("runpod rejected the API key (check ECHOTALES_RUNPOD_API_KEY)")
        if response.status_code == 404:
            raise RuntimeError("runpod endpoint not found (check ECHOTALES_RUNPOD_IMAGE_ENDPOINT)")
        response.raise_for_status()
        return response.json()


@dataclass(slots=True)
class RunPodJob:
    job_id: str
    entry: Any  # the cloud_ledger.LedgerEntry reserved for this job


@dataclass(slots=True)
class RunPodClient:
    """Submit / poll / cancel against one RunPod serverless endpoint, with every submit gated by the cloud ledger.

    The video, multi-reference keyframe and LoRA-training engines share this: the image engine above keeps its own
    loop so its (mock-tested, EVOLUTION 4.106) behaviour is untouched. `ledger.reserve` runs BEFORE the POST, so a
    budget refusal never reaches the network (`cloud_ledger.py`). Mock-tested only; no request has ever been sent.
    """

    endpoint: str
    api_key: str
    env_name: str = "ECHOTALES_RUNPOD_ENDPOINT"
    ledger: Any = None  # CloudLedger; None builds the default one on first submit
    usd_per_hour: float = 0.0
    timeout: float = 1800.0
    poll_seconds: float = 5.0
    client: httpx.Client | None = None

    @classmethod
    def from_settings(cls, endpoint_field: str, env_name: str, **kw: Any) -> RunPodClient:
        from echotales.pipeline.config import get_settings  # type: ignore[import-untyped]

        s = get_settings()
        return cls(endpoint=str(getattr(s, endpoint_field) or ""), api_key=str(s.runpod_api_key or ""),
                   env_name=env_name, usd_per_hour=float(s.cloud_gpu_usd_per_hour), **kw)

    def _check(self) -> dict[str, str]:
        missing = [n for n, v in (("ECHOTALES_RUNPOD_API_KEY", self.api_key), (self.env_name, self.endpoint)) if not v]
        if missing:
            raise RuntimeError(f"this cloud engine needs {', '.join(missing)}; set them in .env (gitignored)")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _http(self) -> httpx.Client:
        return self.client or httpx.Client(timeout=60.0)

    def submit(self, payload: dict[str, Any], *, kind: str, estimated_usd: float, note: str = "") -> RunPodJob:
        headers = self._check()
        if self.ledger is None:
            from echotales.pipeline.cloud_ledger import CloudLedger  # type: ignore[import-untyped]

            self.ledger = CloudLedger()
        entry = self.ledger.reserve("runpod", kind, estimated_usd, note)  # raises BudgetExceeded before any request
        http = self._http()
        try:
            body = RunPodImageEngine._json(
                http.post(f"{API_BASE}/{self.endpoint}/run", json={"input": payload}, headers=headers))
        except Exception:
            self.ledger.settle(entry, 0.0, "submit-failed")
            raise
        finally:
            if self.client is None:
                http.close()
        job_id = str(body.get("id") or "")
        if not job_id:
            self.ledger.settle(entry, 0.0, "submit-failed")
            raise RuntimeError(f"runpod did not return a job id: {sorted(body)}")
        self.ledger.attach_job(entry, job_id)
        return RunPodJob(job_id, entry)

    def poll(self, job: RunPodJob) -> dict[str, Any]:
        http = self._http()
        try:
            return RunPodImageEngine._json(
                http.get(f"{API_BASE}/{self.endpoint}/status/{job.job_id}", headers=self._check()))
        finally:
            if self.client is None:
                http.close()

    def wait(self, job: RunPodJob) -> dict[str, Any]:
        """Poll to a terminal state, settle the ledger with the billed execution time, return the status body."""
        deadline = time.monotonic() + self.timeout
        state = self.poll(job)
        while str(state.get("status", "")).upper() not in _DONE | _FAILED:
            if time.monotonic() > deadline:
                self.cancel(job)
                raise RuntimeError(f"runpod job {job.job_id} did not finish within {self.timeout:.0f}s; cancelled")
            time.sleep(self.poll_seconds)
            state = self.poll(job)
        status = str(state.get("status", "")).upper()
        ms = state.get("executionTime")
        actual = round(float(ms) / 1000.0 * self.usd_per_hour / 3600.0, 4) if isinstance(ms, (int, float)) else None
        self.ledger.settle(job.entry, actual, status.lower())
        if status in _FAILED:
            raise RuntimeError(f"runpod job {job.job_id} {status.lower()}: {str(state.get('error', ''))[:300]}")
        return state

    def cancel(self, job: RunPodJob) -> None:
        """POST /cancel/<id>; the entry keeps its estimate as the charge (a cancelled job may still have billed)."""
        http = self._http()
        try:
            RunPodImageEngine._json(http.post(f"{API_BASE}/{self.endpoint}/cancel/{job.job_id}", headers=self._check()))
        finally:
            if self.client is None:
                http.close()
        self.ledger.settle(job.entry, None, "cancelled")
