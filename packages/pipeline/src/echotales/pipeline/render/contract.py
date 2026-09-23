"""Visual Rendering Track Phase 1a: a typed render contract.

Before this module, the only typed shape in the render path was
`panels.py::PanelImageRequest` (prompt/seed/dimensions/references) and a bare
`PanelImageEngine` Protocol with no declared capabilities -- every caller that
needed to know "can this backend do X" either hardcoded an engine name (e.g.
`RefinedEngine.base_engine: str = "noobai"`) or duck-typed a single `hasattr`
check (`persona/reference_gen.py::_supports_img2img_subprocess`). This module
generalizes that into a first-class capability declaration and gives the
renderer a real plan/attempt/artifact vocabulary to hang benchmarking,
caching, and QA off of (see `render/cache_key.py`, `render/plan_builder.py`).

**Nothing here changes what gets rendered.** `VisualRenderPlan` is computed
and attached to manifests (Phase 1c); it does not yet replace how prompts are
built (`panels.py::render_panels`'s existing logic) -- that is a Phase 4
decision, gated on real benchmark evidence, per this codebase's own repeated
lesson that architecture changes need a measured before/after
(EVOLUTION.md SS4.45/4.46).

`GenerationRequest` wraps `PanelImageRequest` rather than duplicating its
fields -- see `GenerationRequest.base`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from echotales.pipeline.render.panels import PanelImageRequest


class CharacterRole(StrEnum):
    """A character's weight in a panel's composition.

    Doesn't exist anywhere in the pre-Phase-1 pipeline -- every reference
    image was either included or not, with no notion of "this one matters
    more than that one." Introduced so a future multi-pass renderer (Phase
    4a, gated on benchmark evidence) can insert principals first and
    background figures last, rather than stacking every reference into one
    IP-Adapter call the way the removed conditioning path used to
    (EVOLUTION.md SS4.47's documented contamination).
    """

    PRINCIPAL = "PRINCIPAL"
    SUPPORT = "SUPPORT"
    BACKGROUND = "BACKGROUND"


def _digest(*parts: object) -> str:
    """Stable short digest over an ordered sequence of parts.

    Shared by every `*_digest`/cache-key field in this module and by
    `render/cache_key.py`, so "what goes into a digest" is answered in one
    place rather than reimplemented per call site with a risk of silently
    omitting a field (the exact failure mode that made the pre-Phase-1 image
    cache unsafe -- see `render/cache_key.py`'s module docstring).
    """
    blob = "\x1f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True, frozen=True)
class CharacterRenderSpec:
    """One character's presence in a panel, tied to a specific body/state.

    `persona_id` (not `self_id`) is the identity key here: appearance,
    reference images, and body-state all live on `Persona`, not `Self`
    (`packages/core/src/echotales/core/models.py`'s own module docstring --
    "Self is not persona"). `self_id` is carried alongside for provenance and
    cross-referencing, never as an alternate identity key -- using it to pick
    a reference image would be exactly the bug this spec exists to prevent
    (Body A reference material leaking into a Body B render).
    """

    persona_id: str
    self_id: str
    role: CharacterRole
    #: Resolved reference sheet paths for this persona (from
    #: `Attribute` rows keyed `REFERENCE_PATH_KEY`, `persona/reference_gen.py`).
    #: Empty means prompt-only -- the pre-Phase-1 default for every panel.
    reference_paths: tuple[Path, ...] = ()
    #: Free-text hints already computed by `direction.py`'s art-director
    #: pass (pose/expression/action) -- reused verbatim, not recomputed.
    pose_hint: str = ""
    expression_hint: str = ""


@dataclass(slots=True, frozen=True)
class EnvironmentRenderSpec:
    """A panel's setting, reusing whatever `scenes.py`/`scene_state.py`
    already compute -- this module does not reinvent scene-state semantics,
    which is `packages/core` territory."""

    location: str = ""
    lighting: str = ""
    time_of_day: str = ""
    mood: str = ""


@dataclass(slots=True, frozen=True)
class CompositionSpec:
    """Layout/crop metadata currently implicit in `compose.py` and
    `direction.py`'s `PanelDirection.layout`/`shot` fields -- named here so a
    `VisualRenderPlan` can carry it as data instead of only as prompt text."""

    shot: str = ""
    layout: str = ""
    is_crowd_cut: bool = False


@dataclass(slots=True, frozen=True)
class VisualRenderPlan:
    """The top-level render plan for one panel.

    Every plan must be derived from a real `state_of(...)` call
    (`packages/core/src/echotales/core/state.py::StateResolver.state_of`,
    unmodified) plus scene/beat context -- `state_digest` records a hash of
    that actual result, not of what the plan *assumes* the state to be, so a
    stale plan is detectable rather than silently wrong. See
    `render/plan_builder.py::build_render_plan` for the only place that
    should construct one of these from real data; tests may construct one
    directly from a fixture.
    """

    novel_id: str
    chapter: float
    beat_id: str
    panel_seq: int
    characters: tuple[CharacterRenderSpec, ...]
    environment: EnvironmentRenderSpec
    composition: CompositionSpec
    #: Hash of the `state_of(...)` result(s) actually used to build this
    #: plan's `characters`. Empty string is a legitimate value for a fixture
    #: or a pre-Phase-1c call site that hasn't wired state_of() through yet --
    #: never treat an empty digest as an error, only as "unprovenanced."
    state_digest: str = ""
    #: Which resolver supplied persona_ids: "state_of" (timeline/observer-
    #: aware, `core/state.py`) or "persona_at" (pipeline-layer,
    #: `persona/split.py`, not novel/observer-filtered). Recorded because the
    #: two resolvers can disagree; `plan_builder.py` always uses `state_of`,
    #: but this field makes that an auditable fact, not an assumption.
    resolver: str = "state_of"

    @property
    def plan_digest(self) -> str:
        """Hash of this plan's own content -- part of the cache key
        (`render/cache_key.py`) so a plan-shape change (e.g. a character
        added/removed, a role reassigned) invalidates cached renders even
        when the final prompt string happens to end up textually identical.
        """
        char_parts = tuple(
            (c.persona_id, c.self_id, c.role.value, c.pose_hint, c.expression_hint)
            for c in self.characters
        )
        return _digest(
            self.novel_id,
            self.chapter,
            self.beat_id,
            self.panel_seq,
            char_parts,
            self.environment.location,
            self.environment.lighting,
            self.environment.time_of_day,
            self.environment.mood,
            self.composition.shot,
            self.composition.layout,
            self.composition.is_crowd_cut,
            self.state_digest,
        )


@dataclass(slots=True)
class RenderBackendCapabilities:
    """What an image backend can actually do.

    Generalizes the one existing capability-check precedent in the codebase,
    `persona/reference_gen.py::_supports_img2img_subprocess`'s
    `hasattr(engine, "_ensure_img2img_pipe")`, into a declared attribute set
    every `PanelImageEngine` implementation carries -- see
    `panels.py::PanelImageEngine.capabilities` (added alongside this module).
    Replaces hardcoded engine-name assumptions like
    `RefinedEngine.base_engine: str = "noobai"` with something a caller can
    actually query instead of guess.
    """

    supports_multi_reference: bool = False
    max_references: int = 0
    supports_img2img: bool = False
    supports_lora: bool = False
    supports_negative_prompt: bool = True
    #: True for a remote/API backend (Gemini, OpenRouter) -- these ignore
    #: `reference_images`/`init_image` entirely today (confirmed by reading
    #: `render/gemini.py`/`render/openrouter.py`'s `generate()`), which a
    #: capability-aware caller can now branch on instead of discovering by
    #: the request silently having no effect.
    is_hosted: bool = False
    model_family: str = ""


@dataclass(slots=True)
class GenerationRequest:
    """Wraps `PanelImageRequest` (panels.py) rather than duplicating its
    fields -- `base` is the request an engine's `generate()` actually
    receives; everything else here is provenance/config that the pre-Phase-1
    caches never captured (see `render/cache_key.py`)."""

    base: "PanelImageRequest"
    backend_name: str
    checkpoint_id: str = ""
    checkpoint_version: str = ""
    loras: tuple[str, ...] = ()
    steps: int = 0
    guidance_scale: float = 0.0
    renderer_version: str = "1"

    # Convenience passthroughs so call sites reading a `GenerationRequest`
    # don't need `.base.<field>` for the fields that already fully identify
    # the pixels requested -- see `PanelImageRequest` for the canonical docs.
    @property
    def prompt(self) -> str:
        return self.base.prompt

    @property
    def negative_prompt(self) -> str:
        return self.base.negative_prompt

    @property
    def seed(self) -> int:
        return self.base.seed

    @property
    def width(self) -> int:
        return self.base.width

    @property
    def height(self) -> int:
        return self.base.height


@dataclass(slots=True)
class GenerationAttempt:
    """One concrete try at turning a `GenerationRequest` into pixels."""

    request: GenerationRequest
    seed_used: int
    output_path: Path
    duration_s: float = 0.0
    #: Best-effort; `None` for hosted backends or when CUDA isn't available
    #: (mirrors `RenderBackendCapabilities.is_hosted`'s reasoning).
    vram_peak_mb: float | None = None
    retry_reason: str = ""


class QATier(StrEnum):
    """How much a `VisualQAResult` is allowed to do.

    Only `VALIDATED_GATE` may trigger automatic rejection (spec: "Only
    validated gates may trigger automatic rejection"). `DIAGNOSTIC` and
    `HEURISTIC` are informational until a real benchmark
    (`render/bench/`, Phase 2) shows a check actually correlates with human
    ratings -- promoting a check's tier without that evidence would repeat
    the mistake this whole track exists to avoid (shipping an untested
    "should work" fix)."""

    DIAGNOSTIC = "DIAGNOSTIC"
    VALIDATED_GATE = "VALIDATED_GATE"
    HEURISTIC = "HEURISTIC"


@dataclass(slots=True)
class VisualQAResult:
    """The outcome of one QA check against one `GenerationAttempt`."""

    check_name: str
    tier: QATier
    passed: bool
    score: float | None = None
    notes: str = ""


@dataclass(slots=True)
class RenderArtifact:
    """The persisted record for one rendered panel: plan + the attempt that
    was kept + its QA results + everything needed to reconstruct the cache
    key that produced it. This is what `render/bench/manifest.py` (Phase 2)
    serializes, and what a future human-review tool (Phase 5b) keys off of."""

    plan: VisualRenderPlan
    attempt: GenerationAttempt
    qa_results: tuple[VisualQAResult, ...] = ()
    cache_key: str = ""


def digest_reference_paths(paths: tuple[Path, ...] | list[Path]) -> str:
    """Content-independent reference-set digest for the cache key.

    Deliberately hashes *paths*, not file bytes -- re-reading every reference
    image on every cache check would defeat the point of caching. A reference
    file replaced in place without a path change is a known limitation, not
    silently accepted: `render/cache_key.py`'s module docstring says so.
    """
    return _digest(*[str(p) for p in paths])
