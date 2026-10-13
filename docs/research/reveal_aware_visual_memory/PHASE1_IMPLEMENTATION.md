# Reveal-Aware Visual Memory: Phase 1 Implementation Note

**Date**: 2026-10-13  
**Status**: Implementation Phase 1 complete; model-free correctness verified; integration boundary prepared (opt-in only, default render path unchanged).

---

## 1. Audit of the Active Visual-Reference Path

Prior to implementation, the visual reference generation and consumption call paths were audited against the active working tree. The audit traced actual callers, database access, and backend execution requests.

### 1.1 Audit Findings by Component

- **`packages/core/src/echotales/core/state.py`**:
  `StateResolver.state_of` applies the observer and discourse cutoff (`knowledge_pos`) filter to `SelfPersonaBinding` rows and `Attribute` rows via `_visible_to_observer`. A fact first learned after `knowledge_pos` is excluded; a fact retracted at `retracted_at <= knowledge_pos` is excluded. However, persona attributes assembled inside `_fold_target` (lines 653–657) read `store.get_attributes(TargetKind.PERSONA, drawn)` and filtered solely on `interval.from_lb <= position`, bypassing `knowledge_pos`, retraction, and observer scoping (defect D1/D2 in `REPOSITORY_AUDIT.md`).
- **`packages/core/src/echotales/core/interval.py`**:
  `FuzzyInterval` models story time as independent bounds. `contains(p)` yields three values: `CERTAIN`, `PLAUSIBLE`, or `EXCLUDED`. Crucially, an open-ended interval `open_ended(from_lb)` with no `last_evidence` sets `to_lb = from_lb`, which makes any subsequent story position $p > \text{from\_lb}$ strictly `PLAUSIBLE`, not `CERTAIN`. Unchecked promotion of `PLAUSIBLE` to `CERTAIN` is an epistemic leak risk.
- **`packages/core/src/echotales/core/models.py`**:
  `DiscoursePosition(chapter, offset)` provides a strictly total order over text locations. `TemporalFact` models valid time (`interval`), transaction/knowledge time (`learned_at_pos`, `retracted_at`), and observer scope (`observer_id`). `SelfPersonaBinding` links a continuing consciousness (`Self`) to an embodiment epoch (`Persona`).
- **`packages/pipeline/src/echotales/pipeline/persona/split.py`**:
  Defines `bodies_of` and `persona_at`. `persona_at` is total (falling back to `:body1` when no binding exists), whereas `StateResolver.state_of` is honest (empty before first appearance).
- **`packages/pipeline/src/echotales/pipeline/persona/reference_gen.py`**:
  `generate_references` generates reference sheets per character body. It calls `appearance_of(store, persona_id, standing_only=True, position=None)`. The docstring explicitly notes: *"Reference sheets (`generate_references`) call this with no position -- a sheet is meant to be the character's canonical, whole-novel appearance, not a snapshot."* Appearance facts from any chapter in the novel are included. The output path and appearance digest are written as `Attribute` rows with `key="reference_image_path"` and stamped with `entity.first_attested_pos` as `learned_at_pos`, retroactively dating the reference sheet to chapter 1 regardless of when its constituent facts were narrated.
- **`packages/pipeline/src/echotales/pipeline/render/plan_builder.py`**:
  `build_render_plan` queries `reference_path_for(store, persona_id)` and populates `CharacterRenderSpec.reference_paths`. `reference_path_for` reads `store.get_attributes` directly without position, observer, or cutoff checks.
- **`packages/pipeline/src/echotales/pipeline/render/panels.py`**:
  In `render_panels`, `PanelImageRequest` was unconditionally instantiated with `reference_images=[], reference_weight=0.0` (lines 2740, 2811, 2851). IP-Adapter reference conditioning was deliberately disconnected in production (HANDOFF Section 4.47) due to color and composition contamination.
- **`packages/pipeline/src/echotales/pipeline/render/cache_key.py`**:
  Hashes `plan.state_digest` and `request.base.reference_images`. When `reference_images` is empty, reference asset changes do not invalidate the panel cache key.
- **`packages/pipeline/src/echotales/pipeline/world/context.py`**:
  `story_context` builds director prompts using `_facts_as_of` (filters `learned_at.chapter <= chapter` and `is_standing` only). It ignores observer scoping, retraction position, intervals, and truth status, completely bypassing `GenerationState`.

### 1.2 Summary Answers to Required Audit Questions

| Audit Question | Verified State in Codebase |
|---|---|
| **Which backend supports reference conditioning?** | `MangaDiffusersEngine` (SD1.5 + IP-Adapter) and `IllustriousEngine`/`NoobAIEngine` (SDXL + IP-Adapter ViT-H). Hosted (`gemini`, `openrouter`), `sdxl` base, and `stub` do not condition on reference images. |
| **Which call path generates character-reference images?** | `echotales.pipeline.persona.reference_gen.generate_references`, triggered via CLI command `echotales persona --references`. |
| **Which current panel-rendering calls supply reference images?** | **Zero.** `render_panels` unconditionally sets `reference_images=[]` and `reference_weight=0.0` on the `PanelImageRequest` sent to `engine.generate`. |
| **Does the selected backend actually consume them?** | In default panel rendering, **no backend consumes them** because an empty list is passed. In reference generation or standalone tests, `MangaDiffusersEngine` and `IllustriousEngine` consume them if IP-Adapter weights are installed. |
| **Are generated references derived from all-novel or cutoff-scoped facts?** | **All-novel appearance facts.** `appearance_of` is called with `position=None`, pooling all standing appearance attributes across the entire book. |
| **Does the current director/context path bypass the compiled state?** | **Yes.** `story_context` uses flat chapter filtering and whole-volume lexicon, bypassing `StateResolver`, `GenerationState`, observer scoping, and retraction position. |
| **Which parts of the reference pipeline are inactive, experimental, or disconnected?** | 1. Reference image conditioning in `render_panels` is disconnected (`reference_images=[]`).<br>2. `reference_transition_mode="img2img"` in `reference_gen.py` is experimental and opt-in only.<br>3. `curated_character_reference` in `render_panels` is gathered but not forwarded to generation.<br>4. `reference_paths` in `CharacterRenderSpec` is populated but disconnected from `_panel_request`.<br>5. `reference_path_for` performs un-scoped database queries without provenance tracking. |

---

## 2. Minimal Typed Model

The schema is defined in `packages/core/src/echotales/core/visual_memory.py`. Every field is strictly justified by the selection algorithm.

### 2.1 Schema Definitions

```python
@dataclass(frozen=True, slots=True)
class FactProvenance:
    fact_ref: str
    learned_at_pos: DiscoursePosition
    valid_interval: FuzzyInterval
    retracted_at: DiscoursePosition | None = None
    observer_id: str = OBSERVER_READER
    truth_status: TruthStatus = TruthStatus.TRUE
    certainty: Certainty = Certainty.CERTAIN

@dataclass(frozen=True, slots=True)
class VisualAssetRecord:
    asset_id: str
    asset_kind: VisualAssetKind
    self_id: str
    persona_id: str
    story_interval: FuzzyInterval
    source_facts: tuple[FactProvenance, ...]
    parent_asset_ids: tuple[str, ...] = ()
    body_epoch_index: int | None = 1
    effective_cutoff: DiscoursePosition = DiscoursePosition(chapter=0, offset=0)
    observer_scope: frozenset[str] = frozenset({OBSERVER_READER, OBSERVER_SYSTEM})
    image_path: str = ""
    prompt_digest: str = ""
    image_content_digest: str = ""
    engine_id: str = "stub"
    checkpoint_id: str = ""
    seed: int = 0
    rendering_params: tuple[tuple[str, str], ...] = ()
    provenance_version: str = "1.0"
```

### 2.2 Field Justification

1. `asset_id`, `asset_kind`: Unique stable address and functional role (`CHARACTER_PORTRAIT`, `BODY_STATE`, `COMPOSITION_GUIDE`).
2. `self_id`, `persona_id`, `body_epoch_index`: Grounding in the two-level identity model. Prevents selecting assets across physical embodiment transitions (Property R2).
3. `story_interval`: Bounds the story-world time during which the depicted embodiment and traits are valid.
4. `source_facts`: Explicit references to the exact facts that formed the generation prompt. Enables transitive disclosure verification (Property R1).
5. `parent_asset_ids`: Explicit links to prior visual assets conditioned during generation (e.g. img2img parent sheet). Enables transitive lineage tracking (Property R5).
6. `effective_cutoff`: The maximum disclosure cutoff across all direct source facts and all parent assets.
7. `observer_scope`: Audience access control list. Prevents character-facing renders from using reader secrets (Case D).
8. `prompt_digest`, `image_content_digest`, `engine_id`, `checkpoint_id`, `seed`: Content-addressed invalidation and reproducible identification of inputs.
9. `provenance_version`: Ensures schema forward-compatibility.

### 2.3 Distinction: Generation Inputs vs. Pixel Claims

This model and selector make guarantees solely about **generation-time input specifications and asset reference conditioning chains**.
They **do not** claim:
- That the downstream diffusion model faithfully reproduces every specified trait.
- That the diffusion model is incapable of independently hallucinating visual features that were not present in the prompt.
- Zero pixel-level leakage across arbitrary generative checkpoints.

The formal guarantee is restricted to: **no inadmissible fact, un-disclosed detail, retracted belief, or incompatible parent asset is permitted to enter the conditioning inputs or reference chain of the rendered panel.**

---

## 3. Request and Selection Policy

A visual request separates narrative coordinates:

```python
@dataclass(frozen=True, slots=True)
class VisualRequest:
    self_id: str
    story_pos: float                        # Story-world position p
    discourse_cutoff: DiscoursePosition     # Knowledge/discourse cutoff k
    observer_id: str = OBSERVER_READER     # Observer viewpoint o
    policy: DisclosurePolicy = DisclosurePolicy.IN_SEQUENCE
    allow_plausible: bool = False           # Conservative uncertainty gate
    target_persona_id: str | None = None
    modality: str = "character_reference"
    requested_asset_kind: VisualAssetKind = VisualAssetKind.CHARACTER_PORTRAIT
    timeline_id: str = MAIN_TIMELINE
```

### 3.1 Selection Algorithm Pseudocode

```text
Algorithm VisualMemorySelector.select(request, registry):
  Input: request (self_id, p, k, o, policy, allow_plausible)
         registry (VisualAssetRegistry)
  Output: SelectionResult (status, selected_asset, reason, candidate_evaluations, permitted_facts)

  1. Embodiment Query:
     effective_k = (infinity if policy == OMNISCIENT else k)
     state = resolver.state_of(request.self_id, target_kind=SELF, position=p,
                               knowledge_pos=effective_k, observer_id=o,
                               include_plausible=allow_plausible)
     admissible_personas = set(state.persona_ids)
     if request.target_persona_id:
         admissible_personas = admissible_personas ∩ {request.target_persona_id}

     permitted_facts = resolve_permitted_facts(state, admissible_personas, p, effective_k, o)

     if admissible_personas is empty:
         return FALLBACK_PROMPT_ONLY(reason=NO_ADMISSIBLE_EMBODIMENT, permitted_facts)

  2. Candidate Filtering:
     candidates = registry.find_for_self(request.self_id, request.requested_asset_kind)
     if candidates is empty:
         return FALLBACK_PROMPT_ONLY(reason=NO_ASSET_REGISTERED, permitted_facts)

  3. Evaluation Gates (for each candidate C in candidates):
     # Gate 1: Embodiment compatibility
     if C.persona_id not in admissible_personas:
         reject C (EMBODIMENT_MISMATCH)
     if not C.story_interval.contains(p):
         reject C (STORY_TIME_INCOMPATIBLE)
     if C.story_interval.contains(p) == PLAUSIBLE and not allow_plausible:
         reject C (EMBODIMENT_UNCERTAIN)

     # Gate 2: Observer scope
     if o != SYSTEM and o not in C.observer_scope:
         reject C (OBSERVER_UNAUTHORIZED)

     # Gate 3: Lineage integrity
     for parent_id in C.parent_asset_ids:
         if parent_id not in registry:
             reject C (TRANSITIVE_LINEAGE_VIOLATION)

     # Gate 4: Transitive facts (Cutoff, Retraction, Certainty)
     transitive_facts = C.transitive_facts(registry)
     for fact in transitive_facts:
         if o != READER and o != SYSTEM:
             if not observer_witnessed_fact(o, fact, effective_k):
                 reject C (OBSERVER_UNAUTHORIZED)
         if policy != OMNISCIENT:
             if fact.learned_at_pos > k:
                 reject C (CUTOFF_EXCEEDED)
             if fact.retracted_at is not None and fact.retracted_at <= k:
                 reject C (FACT_RETRACTED)
         if fact.certainty == PLAUSIBLE and not allow_plausible:
             reject C (FACT_UNCERTAINTY_EXCLUDED)

     if C passed all gates:
         mark C admissible

  4. Decision:
     if admissible_candidates is empty:
         return FALLBACK_PROMPT_ONLY(reason=first_rejection_reason, candidate_evaluations, permitted_facts)

     chosen = sort_deterministically(admissible_candidates, lead_persona, p)[0]
     return SELECTED(selected_asset=chosen, candidate_evaluations, permitted_facts)
```

---

## 4. Exact Conditions Under Which a Reference is Safe to Reuse

Let asset $A$ have persona ID $\pi(A)$, story validity interval $I(A)$, observer scope $\Omega(A)$, parent assets $\text{Parents}(A)$, and transitive source facts $\Phi^*(A)$.

Given a request with target Self $E$, story position $p$, discourse cutoff $k$, observer $o$, view policy $\Pi$, and uncertainty tolerance $\mu \in \{\text{strict}, \text{plausible}\}$:

$A$ is **safe to reuse** if and only if all of the following hold:

1. **Embodiment Admissibility**:
   $$\pi(A) \in \text{StateOf}(E, p, k, o).\text{persona\_ids}$$
   $$\text{contains}(I(A), p) \in \begin{cases} \{\text{CERTAIN}\} & \text{if } \mu = \text{strict} \\ \{\text{CERTAIN}, \text{PLAUSIBLE}\} & \text{if } \mu = \text{plausible} \end{cases}$$
2. **Observer Scope**:
   $$o = \text{SYSTEM} \quad \lor \quad o \in \Omega(A)$$
   $$\forall \varphi \in \Phi^*(A), \quad (o \in \{\text{READER}, \text{SYSTEM}\} \lor \text{Witnessed}(o, \varphi) \le k)$$
3. **Discourse Cutoff Admissibility**:
   $$\Pi = \text{OMNISCIENT} \quad \lor \quad \left( \forall \varphi \in \Phi^*(A), \, \text{learned\_at}(\varphi) \le k \right)$$
4. **Historical Belief Preservation**:
   $$\Pi = \text{OMNISCIENT} \quad \lor \quad \left( \forall \varphi \in \Phi^*(A), \, \text{retracted\_at}(\varphi) = \bot \lor k < \text{retracted\_at}(\varphi) \right)$$
5. **Transitive Lineage Closure**:
   $$\forall P \in \text{Parents}(A), \quad P \in \text{Registry} \land \text{SafeToReuse}(P, \text{req})$$
6. **Epistemic Certainty**:
   $$\mu = \text{plausible} \quad \lor \quad \left( \forall \varphi \in \Phi^*(A), \, \text{certainty}(\varphi) = \text{CERTAIN} \right)$$

If any clause is violated, the selector deterministically falls back to prompt-only generation with an inspectable reason and audit trail.

---

## 5. Correctness Properties and Verification Locations

| Property | Description | Verification Suite & Test |
|---|---|---|
| **R1 — Provenance Admissibility** | Selected reference's transitive source-fact lineage must be admissible under cutoff $k$. Late-revealed facts trigger rejection. | `packages/core/tests/test_visual_memory.py::test_r1_provenance_admissibility` |
| **R2 — Embodiment Compatibility** | A reference tied to an incompatible body epoch must not be selected solely because `self_id` matches. | `packages/core/tests/test_visual_memory.py::test_r2_embodiment_compatibility` |
| **R3 — Cutoff Independence** | Adding facts or references disclosed after cutoff $k$ does not alter selection for requests with cutoff $\le k$. | `packages/core/tests/test_visual_memory.py::test_r3_cutoff_independence_deterministic`<br>`test_r3_cutoff_independence_hypothesis` (Hypothesis property test) |
| **R4 — Retrospective Distinction** | Request at story position $p$ with cutoff $k > p$ obeys its view policy; $p$ and $k$ are not equated. Flashbacks permit post-$p$ reveals. | `packages/core/tests/test_visual_memory.py::test_r4_retrospective_distinction` |
| **R5 — Transitive Lineage** | Child asset conditioned on parent asset inherits parent dependencies; cannot bypass cutoff restriction. | `packages/core/tests/test_visual_memory.py::test_r5_transitive_lineage` |
| **R6 — Conservative Fallback** | When no compatible reference is safe, reports explicit fallback reason, audit log, and safe permitted facts. | `packages/core/tests/test_visual_memory.py::test_r6_conservative_fallback` |

### 5.1 Conceptual Cases Verified

- **Case A (In-sequence rendering)**: Detail true at $p=3$, disclosed at $k=50$. Request at $p=3, k=10$ rejects the asset (`CUTOFF_EXCEEDED`).
- **Case B (Retrospective rendering)**: Flashback at $p=3$ with discourse cutoff $k=60$ (`RETROSPECTIVE`) admits the asset.
- **Case C (Embodiment change)**: Fang Yuan scholar body ($[1, 10]$) vs immortal body ($[10, 50]$). Request at $p=25$ rejects scholar sheet (`EMBODIMENT_MISMATCH`).
- **Case D (Observer-specific knowledge)**: Wu Clan observer lacks observation of secret rank-3 cultivation. Request at $k=10$ rejects asset (`OBSERVER_UNAUTHORIZED`). Witnessing at $k=15$ admits it at $k=20$, but rejects at $k=12$.
- **Case E (Uncertain/plausible state)**: Plausible disguise fact is rejected when `allow_plausible=False` (`FACT_UNCERTAINTY_EXCLUDED`), and admitted only when `allow_plausible=True`.
- **Historical Retraction Preservation**: Belief learned at $k=2$ and retracted at $k=40$. Request at $k=20$ admits the asset; request at $k=50$ rejects it (`FACT_RETRACTED`).

---

## 6. What Is Implemented vs. What Remains

### Implemented in Phase 1:
- Minimal typed models (`FactProvenance`, `VisualAssetRecord`, `VisualRequest`, `CandidateEvaluation`, `SelectionResult`).
- In-memory registry with transitive lineage indexing (`VisualAssetRegistry`).
- Deterministic selector with 5 correctness gates (`VisualMemorySelector`).
- Safe prompt-only fallback fact resolution via `StateResolver`.
- Integration hook in `build_render_plan` via optional `visual_registry` parameter (opt-in; default remains 100% legacy-compatible).
- Comprehensive test suite covering R1–R6, Cases A–E, and integration boundary.

### Remains for Subsequent Phases:
- **Reference sheet provenance generator**: Updating `generate_references` to emit `VisualAssetRecord`s with per-attribute source facts rather than flat un-scoped strings.
- **Production render loop routing**: Wiring `visual_registry` into `render_panels` once reference conditioning (IP-Adapter) is re-evaluated or re-enabled.
- **Persistent asset catalog**: Serializing asset manifests to disk (`manifest.json` under `data/novels/<CODE>/references/`).
- **Cross-modal coordination**: Unifying speech timbre reference selection with visual reference selection under identical $(p, k, o)$ constraints.

---

## 7. Explicit Limits & Non-Guarantees

1. **Model-Generated Pixels Are Unconstrained**:
   The compiler gates input prompts and image conditioning references. Once an image model generates an image, pixel-level features are subject to stochastic model weights. A prompt that omits a scar does not prevent an anime checkpoint with a strong bias from drawing a facial mark.
2. **Extractor Garbage-In, Garbage-Out**:
   Provenance guarantees are relative to the narrative store. If the upstream extractor erroneously stamps an appearance attribute with chapter 1 instead of chapter 100, the compiler will treat it as disclosed at chapter 1.
3. **No Direct Production Render Changes in Phase 1**:
   Default production render output is unchanged; existing render caches and pipeline invocations are not affected.

---

## 8. Risks and Open Issues

1. **Sparse Real-World Observer Rows**:
   As noted in `REPOSITORY_AUDIT.md`, shipped novel databases currently contain zero retracted attributes and 12 observation rows (Reverend Insanity only; Lord of the Mysteries and ORV have 0). Observer-specific gating relies heavily on synthetic fixtures until extractor updates generate rich observation logs.
2. **IP-Adapter Drift and Contamination**:
   HANDOFF Section 4.47 disabled IP-Adapter reference conditioning because reference sheets introduced color and composition contamination. Selecting the *epistemically correct* reference sheet does not by itself solve diffusion conditioning contamination.
3. **Prompt Budget Pressure**:
   Fallback to prompt-only generation places appearance clauses directly into the prompt text, competing against the 77-token CLIP budget in `fit_to_budget`.
