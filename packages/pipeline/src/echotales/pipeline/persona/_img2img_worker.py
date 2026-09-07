"""Standalone worker: run exactly one img2img reference-transition generation.

**Why a subprocess at all.** EVOLUTION 4.55: body1 (txt2img) and body2
(img2img) sharing one process means body2's `vae.decode` OOMs on this 7.65
GiB card even after the host-memory leak fix and an `empty_cache()` +
`gc.collect()` mitigation immediately before the call -- the mitigation
freed enough of PyTorch's *own* caching allocator to get the denoise loop
running, but not enough to survive decode's transient float32 upcast on
top of whatever fragmentation body1's run left behind in the same CUDA
context. A fresh process gets a fresh CUDA context with no such
fragmentation, which no in-process cache-clear can produce. This is
intentionally the smallest process boundary possible: it loads one engine,
runs one `generate()` call, writes one file, and exits -- body1's pipeline
is never constructed here, and the parent process's own pipeline is never
touched by this call, so there is nothing to reconcile between the two.

Invoked only from `persona/reference_gen.py::_generate_one`, only when
`reference_transition_mode="img2img"` and the body being generated is not
the first body of its character -- every other call path is unaffected.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Cap worker thread allocation to avoid system thread over-subscription and swap thrashing
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "4")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: _img2img_worker.py <request.json>", file=sys.stderr)
        return 2

    payload = json.loads(Path(argv[1]).read_text())

    from echotales.pipeline.render.panels import PanelImageRequest, get_engine

    engine = get_engine(payload["engine_name"])
    request = PanelImageRequest(
        prompt=payload["prompt"],
        out_path=Path(payload["out_path"]),
        negative_prompt=payload.get("negative_prompt", ""),
        width=payload.get("width", 1024),
        height=payload.get("height", 1024),
        seed=payload.get("seed", 0),
        init_image=payload.get("init_image"),
        transition_strength=payload.get("transition_strength", 0.5),
    )
    engine.generate(request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
