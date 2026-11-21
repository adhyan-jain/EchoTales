"""Multi-reference keyframes on a RunPod worker (Qwen-Image-Edit class). Optional, off by default, mock-tested only.

Takes the approved character sheet(s) plus a prompt and returns one image, so a panel is conditioned on the sheet
instead of repeated appearance text (the local worker ignores reference images, HANDOFF open defect). Registered as
`qwen-image-edit-runpod` (image, surface `cloud-keyframe`), not in the `--image-engine` choices.

Worker contract:
    request   {"input": {"prompt", "negative_prompt", "width", "height", "seed", "references": ["<b64 png>", ...]}}
    response  {"status": "COMPLETED", "output": <image>}  (any shape `runpod._first_b64` accepts)
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING

from echotales.pipeline import cloud_ledger
from echotales.pipeline.render import contract
from echotales.pipeline.render.runpod import (
    RunPodClient,
    _first_b64,
)

if TYPE_CHECKING:
    from echotales.pipeline.render.panels import PanelImageRequest

MAX_REFERENCES = 3


class RunPodEditEngine:
    name = "qwen-image-edit-runpod"

    def __init__(self, client: RunPodClient | None = None) -> None:
        self.client = client or RunPodClient.from_settings("runpod_edit_endpoint", "ECHOTALES_RUNPOD_EDIT_ENDPOINT")

    @property
    def capabilities(self) -> contract.RenderBackendCapabilities:
        return contract.RenderBackendCapabilities(
            supports_multi_reference=True, max_references=MAX_REFERENCES, supports_img2img=False, supports_lora=False,
            supports_negative_prompt=True, is_hosted=True, model_family="qwen-image-edit",
        )

    @staticmethod
    def estimate_usd(images: int = 1) -> float:
        return float(cloud_ledger.estimate_job_usd("edit", images))

    def generate(self, request: PanelImageRequest) -> Path:
        refs = [p for p in request.reference_images if Path(p).is_file()][:MAX_REFERENCES]
        if not refs:
            raise RuntimeError("the multi-reference engine needs at least one approved character sheet on disk")
        payload = {
            "prompt": request.prompt, "negative_prompt": request.negative_prompt, "width": request.width,
            "height": request.height, "seed": request.seed,
            "references": [base64.b64encode(Path(p).read_bytes()).decode("ascii") for p in refs],
        }
        job = self.client.submit(payload, kind="edit", estimated_usd=self.estimate_usd(), note=f"{len(refs)} refs")
        state = self.client.wait(job)
        encoded = _first_b64(state.get("output"))
        if not encoded:
            raise RuntimeError(f"runpod edit job {job.job_id} completed with no image in its output")
        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        request.out_path.write_bytes(base64.b64decode(encoded.split(",", 1)[-1]))
        return Path(request.out_path)
