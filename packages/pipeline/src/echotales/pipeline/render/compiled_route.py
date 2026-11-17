"""Send a compiled prompt through the worker that matches `render.image_model`, so nothing is cut at 77 tokens.

Why: stage A's compiler wrote whole prompts, but `render_panels` still handed them to the legacy diffusers engine, which
clips at CLIP's 77 tokens; only the workers encode the whole prompt (chunked compel for NoobAI, Qwen3 for Z-Image and Anima).
Workers are kept for the life of the process because loading them costs 24-74 s (Z-Image measured 2026-11-16), and are
replaceable by tests through `set_worker`.
"""

from __future__ import annotations

import base64
from typing import Any

from echotales.pipeline.render.compiler import model_profile

_WORKERS: dict[str, Any] = {}


def set_worker(model_key: str, worker: Any | None) -> None:
    """Install (or with `None` remove) the worker for `model_key`; the test seam."""
    if worker is None:
        _WORKERS.pop(model_key, None)
    else:
        _WORKERS[model_key] = worker


def worker_for(model_key: str) -> Any:
    profile = model_profile(model_key)
    if profile.key not in _WORKERS:
        if profile.key == "z-image-turbo":
            from echotales.pipeline.workers_zimage import LocalZImageWorker as W
        elif profile.key == "anima":
            from echotales.pipeline.workers_anima import LocalAnimaWorker as W
        else:
            from echotales.pipeline.workers_local import LocalNoobAIWorker as W
        _WORKERS[profile.key] = W()
    return _WORKERS[profile.key]


def generate_compiled(request: Any, sections: list[tuple[str, str]], model_key: str, *, greyscale: bool) -> None:
    """Render one `PanelImageRequest` with the worker for `model_key`, writing `request.out_path`."""
    generate_compiled_batch([request], [sections], model_key, greyscale=greyscale)


def generate_compiled_batch(
    requests: list[Any],
    sections_list: list[list[tuple[str, str]]],
    model_key: str,
    *,
    greyscale: bool,
) -> None:
    """Render a batch of `PanelImageRequest`s with the worker for `model_key`, writing each `request.out_path`."""
    if not requests:
        return
    from echotales.pipeline.workers_contract import ImageWorkerRequest

    reqs = [
        ImageWorkerRequest(
            prompt=r.prompt,
            negative_prompt=r.negative_prompt,
            width=r.width,
            height=r.height,
            seed=r.seed,
        )
        for r in requests
    ]
    responses = worker_for(model_key).generate_many(
        reqs, sections_list, greyscale=greyscale,
    )
    for r, resp in zip(requests, responses, strict=True):
        r.out_path.parent.mkdir(parents=True, exist_ok=True)
        r.out_path.write_bytes(base64.b64decode(resp.image_b64))

