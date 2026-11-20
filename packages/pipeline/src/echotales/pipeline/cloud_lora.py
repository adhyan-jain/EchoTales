"""Character LoRA training job spec for a RunPod worker. Optional, off by default, mock-tested only.

The dataset is the approved reference images of one character (no other source), written as a manifest next to the
images so a run is reproducible and the training worker is told exactly what it may use. Submitting goes through the
cloud ledger; `--dry-run` prints the estimate and submits nothing. The returned .safetensors is loaded locally by the
Z-Image worker through `ECHOTALES_ZIMAGE_LORA` (`workers_zimage.lora_args`).

Worker contract:
    request   {"input": {"task": "train-lora", "base_model", "trigger", "steps", "rank", "images": [{"name", "b64",
               "caption"}]}}
    response  {"status": "COMPLETED", "output": {"lora": "<b64 safetensors>"}}
"""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from echotales.pipeline.cloud_ledger import estimate_job_usd  # type: ignore[import-untyped]
from echotales.pipeline.render.runpod import RunPodClient  # type: ignore[import-untyped]

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(slots=True)
class LoraTrainSpec:
    character: str
    images: list[Path]
    trigger: str
    base_model: str = "z-image-turbo"
    steps: int = 1000
    rank: int = 16

    def manifest(self) -> dict[str, Any]:
        d = asdict(self)
        d["images"] = [p.name for p in self.images]
        return d


def build_spec(character: str, reference_dir: Path | str, *, trigger: str = "", **kw: Any) -> LoraTrainSpec:
    """Spec from the approved reference images in `reference_dir`; refuses an empty dataset."""
    images = sorted(p for p in Path(reference_dir).glob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        raise ValueError(f"no approved reference images in {reference_dir}; a LoRA needs at least one")
    return LoraTrainSpec(character, images, trigger or f"echo_{character.lower().replace(' ', '_')}", **kw)


def write_manifest(spec: LoraTrainSpec, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(spec.manifest(), indent=1), encoding="utf-8")
    return out_path


def estimate_usd(spec: LoraTrainSpec) -> float:
    return float(estimate_job_usd("lora", 1))


def submit(spec: LoraTrainSpec, client: RunPodClient | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Estimate (dry run: stop there, send nothing) or reserve in the ledger, submit and return the job id."""
    est = estimate_usd(spec)
    if dry_run:
        return {"dry_run": True, "estimated_usd": est, "images": len(spec.images), "submitted": False}
    client = client or RunPodClient.from_settings("runpod_lora_endpoint", "ECHOTALES_RUNPOD_LORA_ENDPOINT")
    payload = {
        "task": "train-lora", "base_model": spec.base_model, "trigger": spec.trigger, "steps": spec.steps,
        "rank": spec.rank,
        "images": [{"name": p.name, "b64": base64.b64encode(p.read_bytes()).decode("ascii"),
                    "caption": f"{spec.trigger}, {spec.character}"} for p in spec.images],
    }
    job = client.submit(payload, kind="lora", estimated_usd=est, note=spec.character)
    return {"dry_run": False, "estimated_usd": est, "job_id": job.job_id, "submitted": True}
