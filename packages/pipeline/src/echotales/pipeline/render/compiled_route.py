"""Send a compiled prompt through the worker that matches `render.image_model`, so nothing is cut at 77 tokens.

Why: stage A's compiler wrote whole prompts, but `render_panels` still handed them to the legacy diffusers engine, which
clips at CLIP's 77 tokens; only the workers encode the whole prompt (chunked compel for NoobAI, Qwen3 for Z-Image and Anima).
Workers are kept for the life of the process because loading them costs 24-74 s (Z-Image measured 2026-11-16), and are
replaceable by tests through `set_worker`.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from echotales.pipeline.render.compiler import model_profile

log = logging.getLogger(__name__)

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


def release_worker(model_key: str) -> None:
    """Free the card held by `model_key`'s worker (a no-op when it was never loaded or has nothing to free).

    The Z-Image worker keeps its transformer resident between batches. The vision check (ollama) loads next and got a 500
    from ollama on every panel of the first M1 render (EVOLUTION M1.6): all 13 panels came back unchecked. The worker
    reloads itself on its next batch."""
    worker = _WORKERS.get(model_profile(model_key).key)
    close = getattr(worker, "close", None)
    if close is not None:
        close()


def generate_compiled(request: Any, sections: list[tuple[str, str]], model_key: str, *, greyscale: bool) -> None:
    """Render one `PanelImageRequest` with the worker for `model_key`, writing `request.out_path`."""
    generate_compiled_batch([request], [sections], model_key, greyscale=greyscale)


def generate_compiled_batch(
    requests: list[Any],
    sections_list: list[list[tuple[str, str]]],
    model_key: str,
    *,
    greyscale: bool,
) -> list[Any]:
    """Render a batch of `PanelImageRequest`s with the worker for `model_key`, writing each `request.out_path`.

    Returns the requests that produced no file. One call for the whole batch is the fast path (one model load); if it
    raises, each request is retried alone, because a chapter-wide failure (an out-of-memory on the largest panel, one bad
    prompt) used to lose every panel the worker could have drawn. A request that fails alone is logged by its path and
    skipped, so the chapter finishes with the panels that worked rather than none."""
    if not requests:
        return []
    from echotales.pipeline.workers_contract import ImageWorkerRequest

    def _one(r: Any) -> ImageWorkerRequest:
        return ImageWorkerRequest(
            prompt=r.prompt, negative_prompt=r.negative_prompt, width=r.width, height=r.height, seed=r.seed,
        )

    def _write(r: Any, resp: Any) -> None:
        r.out_path.parent.mkdir(parents=True, exist_ok=True)
        r.out_path.write_bytes(base64.b64decode(resp.image_b64))

    worker = worker_for(model_key)
    try:
        responses = worker.generate_many([_one(r) for r in requests], sections_list, greyscale=greyscale)
        for r, resp in zip(requests, responses, strict=True):
            _write(r, resp)
        return []
    except Exception as exc:
        log.warning("batch of %d panels failed (%s: %s); generating them one by one", len(requests), type(exc).__name__, exc)

    failed: list[Any] = []
    for r, secs in zip(requests, sections_list, strict=True):
        if r.out_path.exists():
            continue  # written before the batch raised
        try:
            _write(r, worker.generate_many([_one(r)], [secs], greyscale=greyscale)[0])
        except Exception as exc:
            log.warning("panel %s failed alone (%s: %s); skipped", r.out_path, type(exc).__name__, exc)
            failed.append(r)
    return failed
