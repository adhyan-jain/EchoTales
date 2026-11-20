"""Draw more than one candidate per panel, let a local vision model answer the checklist, keep the best passing one.

Why (Opus review of the 2026-11-20 sheets): the checks that mattered to a viewer (one person where the text has one, the
lead's hair and outfit colour as locked, the lead in frame) were never looked at by anything but a human. The identity lock
(`persona/identity_lock.py`) makes them answerable, and `keyframes/qa.py` holds the checklist.

Order on an 8 GB card: all candidates are drawn first, in one batch per candidate index so the image worker loads once per
batch, and only then does the vision model load (ollama); it is unloaded before the next chapter's images. The two never
share the card.
"""

from __future__ import annotations

import dataclasses
import logging
import shutil
from pathlib import Path
from typing import Any

from echotales.pipeline.keyframes import qa
from echotales.pipeline.render.compiled_route import generate_compiled_batch, release_worker

log = logging.getLogger(__name__)

#: Locally, two candidates: a retry costs one more image (about 30 s on the 4060), and two draws rescued most first-try
#: failures in the measurement in docs/EVOLUTION.md (M1.6). `render.candidates` raises it.
DEFAULT_CANDIDATES = 2


def choose_vlm(*, vision_model: str, candidates: int) -> qa.OllamaVLM | None:
    """The vision model to use, or None. None when the config asks for a single candidate (nothing to choose between)
    or when no vision model is installed, in which case the reason is logged once and renders go on unchecked."""
    if candidates == 1:
        return None
    model = qa.pick_vision_model(qa.OllamaVLM.installed(), vision_model)
    if model is None:
        log.warning(qa.NO_VLM_MESSAGE)
        return None
    return qa.OllamaVLM(model)


def candidates_for(configured: int, vlm: Any) -> int:
    """`render.candidates` when set, else two with a vision model and one without."""
    if vlm is None:
        return 1
    return configured if configured > 0 else DEFAULT_CANDIDATES


def run(
    requests: list[Any], sections: list[list[tuple[str, str]]], expectations: dict[Path, qa.PanelExpectation], *,
    vlm: Any, candidates: int, model_key: str, greyscale: bool,
) -> list[dict[str, Any]]:
    """Check `requests` (already drawn once, at `out_path`), drawing `candidates - 1` more of each panel that has an
    expectation, and leave the chosen image at `out_path`. Returns one row per checked panel for `vision_check.jsonl`."""
    todo = [(r, s) for r, s in zip(requests, sections, strict=True) if r.out_path in expectations and r.out_path.exists()]
    if not todo:
        return []
    extras: dict[Path, list[Path]] = {r.out_path: [r.out_path] for r, _ in todo}
    for k in range(1, max(candidates, 1)):
        batch, secs = [], []
        for r, s in todo:
            # A different seed per candidate; prime strides keep them clear of the engine's own flat-panel retry (+9973).
            extra = dataclasses.replace(r, out_path=r.out_path.with_name(f"{r.out_path.stem}.cand{k}{r.out_path.suffix}"),
                                        seed=r.seed + 7919 * k)
            batch.append(extra)
            secs.append(s)
        failed = generate_compiled_batch(batch, secs, model_key, greyscale=greyscale)
        failed_paths = {f.out_path for f in failed}
        for (r, _s), extra in zip(todo, batch, strict=True):
            if extra.out_path not in failed_paths and extra.out_path.exists():
                extras[r.out_path].append(extra.out_path)
    rows: list[dict[str, Any]] = []
    release_worker(model_key)  # the image model still holds the card; ollama cannot load the vision model beside it
    try:
        for r, _s in todo:
            paths = extras[r.out_path]
            sel = qa.select_candidate(paths, expectations[r.out_path], vlm)
            if sel.chosen != 0:
                shutil.copyfile(paths[sel.chosen], r.out_path)
            rows.append({
                "panel": r.out_path.name, "candidates": len(paths), "chosen": sel.chosen, "passed": sel.passed,
                "first_passed": sel.first_passed, "unchecked": sel.unchecked, "failed": sel.failed,
                "model": getattr(vlm, "model", ""),
            })
    finally:
        for paths in extras.values():
            for extra in paths[1:]:
                extra.unlink(missing_ok=True)
        unload = getattr(vlm, "unload", None)
        if unload is not None:
            unload()
    return rows
