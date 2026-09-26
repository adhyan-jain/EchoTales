"""Visual Rendering Track Phase 1b: a real cache key for rendered images.

**The bug this fixes.** `render/panels.py`'s image cache (the code path that
decides whether `render_panels` skips a block or spends GPU time on it) was
pure file-path existence: `if image_path.exists(): skip`. A separate prompt-
content digest existed, but only for cross-panel dedupe *within one run* --
it was never persisted or compared across runs. Swapping `--image-engine`,
checkpoint, seed, or steps and re-running into the same output directory
therefore served the stale image from the previous configuration, silently,
with no error. This module is the fix: a single digest over every
quality-affecting input, so a caller can tell "this exact configuration was
already rendered" from "something changed and this needs a new render."

**What's deliberately NOT covered.** This digests reference *paths*, not
file bytes (`contract.py::digest_reference_paths`) -- re-reading every
reference image on every cache check would defeat the point of caching. A
reference file replaced in place without a path change is a known,
documented limitation, not a silently accepted one.
"""

from __future__ import annotations

from echotales.pipeline.render.contract import GenerationRequest, VisualRenderPlan, _digest

#: Bumped whenever this key's own *shape* changes (a field added/removed/
#: reordered in a way that would otherwise produce a same-looking digest for
#: semantically different inputs). Not bumped for an ordinary content change
#: -- that's what the digest itself is for.
#: "2": `state_digest` is now `GenerationState.digest()` at the panel's own
#: in-chapter position (it was hashed at the chapter start from a different
#: attribute set), so every key from "1" is stale by construction.
RENDER_CACHE_VERSION = "2"


def compute_render_cache_key(plan: VisualRenderPlan, request: GenerationRequest) -> str:
    """The real cache key: every field that can change the pixels.

    Includes, per Visual Rendering Track spec item 11: state digest, plan
    digest, prompt, negative prompt, backend, checkpoint id+version, LoRAs,
    reference image paths + reference weight, seed, dimensions, steps,
    guidance scale, and this module's own version constant.
    """
    reference_digest = _digest(*[str(p) for p in request.base.reference_images])
    return _digest(
        RENDER_CACHE_VERSION,
        plan.state_digest,
        plan.plan_digest,
        request.prompt,
        request.negative_prompt,
        request.backend_name,
        request.checkpoint_id,
        request.checkpoint_version,
        tuple(request.loras),
        reference_digest,
        request.base.reference_weight,
        request.seed,
        request.width,
        request.height,
        request.steps,
        request.guidance_scale,
        request.renderer_version,
    )
