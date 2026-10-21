# Reveal-aware visual memory: phase 1 and 2 implementation

> Merged on 2026-10-22 from 2 separate documents to keep the docs tree small. Each section below is one original file, text unchanged; its old path is in the section heading. The originals are in git history.

---

<!-- merged-from: docs/research/reveal_aware_visual_memory/PHASE1_IMPLEMENTATION.md -->
## Source: `docs/research/reveal_aware_visual_memory/PHASE1_IMPLEMENTATION.md`

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

---

<!-- merged-from: docs/research/reveal_aware_visual_memory/PHASE2_IMPLEMENTATION.md -->
## Source: `docs/research/reveal_aware_visual_memory/PHASE2_IMPLEMENTATION.md`

# Reveal-Aware Visual Memory: Phase 2 Implementation Note

**Date**: 2026-10-13  
**Status**: Implementation Phase 2 complete; Cutoff-Scoped Visual Asset Emission implemented and verified; model-free test suite passing (10/10 tests); full visual memory regression suite passing (26/26 tests); default rendering behavior preserved.

---

## 1. Overview & Objective

Phase 2 builds upon the provenance-scoped selector layer established in Phase 1 (`VisualMemorySelector`, R1–R6 selection rules) by implementing the asset generation and compilation side: **Cutoff-Scoped Visual Asset Emission** (`emit_scoped_reference`).

The mission of Phase 2 is to compile reusable character reference assets under explicit narrative coordinates:
1. Story position $p$: The story-world time being depicted.
2. Discourse cutoff $k$: The narrative revelation boundary available to the viewer.
3. Observer $o$: The audience or character viewpoint (`READER`, character observer, or `SYSTEM`).
4. Disclosure policy $\Pi$: Information revelation rules (`IN_SEQUENCE`, `RETROSPECTIVE`, `OMNISCIENT`).

Crucially, **story position $p$ and discourse cutoff $k$ are strictly decoupled**. In sequential reading ($p=5, k=5$), later reveals (e.g., a scar disclosed at chapter 100) are strictly excluded from early prompts. In retrospective rendering (e.g., a flashback to $p=5$ rendered for a reader at $k=100$), the scar is admitted because it held in-world at $p=5$ and has been revealed to the viewer by cutoff $k=100$.

Prompts are assembled **strictly from facts admissible under $(p, k, o, \Pi)$**, accompanied by a verifiable provenance manifest (`<asset_id>_manifest.json`) recording the exact facts, physical row IDs, semantic assertions, temporal bounds, and engine parameters used.

---

## 2. Architectural Design & Enhancements

### 2.1 Fact Identity: Physical Row ID vs. Semantic Assertion Identity

A core design requirement was establishing reliable provenance linking every prompt token to its underlying database assertion:
- **Physical Row Identity (`source_row_id`)**: The SQLite autoincrement primary key `attribute.id`. This represents the physical database row. It is ephemeral across total database rebuilds but provides exact, verifiable auditability for an active database instance.
- **Semantic Assertion Identity (`fact_ref`)**: Generated via `observable_ref(attr)` in `echotales.core.readset` (e.g., `attr:s1:hair_color:black`). Survives database rebuilds and re-extractions.
- **Epistemic Attestation Tuple**: `(fact_ref, learned_at_pos, valid_interval, retracted_at, observer_id, truth_status)`. Uniquely identifies the bitemporal assertion in the graph.

**Core Changes**:
- In `packages/core/src/echotales/core/models.py`: Added `source_row_id: int | None = None` to `TemporalFact` so that all fact models (`Attribute`, `AliasBinding`, etc.) can hold the physical row ID.
- In `packages/core/src/echotales/core/store.py`: Updated `Store.get_attributes` to populate `source_row_id=r["id"] if "id" in r.keys() else None` from the SQLite row.
- In `packages/core/src/echotales/core/visual_memory.py`: Added `source_row_id: int | None = None` to `FactProvenance`.

### 2.2 Authoritative Epistemic Resolution: `StateResolver.resolve_admissible_attributes`

The legacy reference path (`appearance_of`) inspected only `interval.from_lb <= p` and ignored `learned_at_pos`, `retracted_at`, and observer scoping. Furthermore, `StateResolver.state_of` resolved facts through epistemic gates (`_visible_to_observer`, `_temporal_certainty`) but collapsed them into a flat `dict[str, str]`, discarding the underlying `Attribute` instances and their provenance metadata.

To resolve this without altering legacy behavior:
- Added `resolve_admissible_attributes` to `StateResolver` (`packages/core/src/echotales/core/state.py`):
  - Accepts `target_id`, `target_kind=TargetKind.PERSONA`, `timeline_id`, `position=p`, `observer_id=o`, `knowledge_pos=k`, and `include_plausible=False`.
  - Filters attributes through `_visible_to_observer` and `_temporal_certainty`.
  - Resolves key collisions deterministically (later-learned facts win on collision).
  - Returns the winning `list[Attribute]` with full temporal and physical metadata intact, sorted deterministically by attribute key.

### 2.3 Prompt Assembly Discipline

To prevent post-cutoff information leakage:
1. **No Unchecked Canon Injections**: `apply_canon` was a position-free, cutoff-free table overlay. In `emit_scoped_reference`, `include_canon` defaults to `False`. Attributes must come from grounded store rows.
2. **No Whole-Novel Demographic Scans**: Legacy `_demographics` performed un-scoped text scans (`gather_appearance_passages`) over the whole novel when traits were missing. In `emit_scoped_reference`, demographics are derived directly from admissible `Attribute` rows (or explicit arguments); if absent, they fall back closed to `"unknown"` gender and `"adult"` age without scanning future prose.
3. **Deterministic Tag Assembly**: Attributes are phrased via `build_reference_prompt` into Danbooru tags and descriptive clauses in fixed sentence order (`_PROMPT_ORDER`).
4. **Content-Addressed Hashing**: A SHA-256 digest of the final prompt (`prompt_digest`) is computed and incorporated into the content-addressed asset ID: `ref_{novel_id}_{self_id}_{persona_id}_p{int(p)}_k{k.chapter}_{prompt_digest[:8]}`.

### 2.4 Transitive Parent Asset Verification

When emitting derived reference sheets (e.g., an img2img transformation or refined body sheet conditioned on prior assets):
- All parent asset IDs (`parent_asset_ids`) are verified against `parent_assets` and/or the registry.
- Transitive lineage is checked: if any parent asset has an effective cutoff $k_{\text{parent}} > k$, or depends on a fact that was retracted as of $k$, or was witnessed only by an unauthorized observer, the emission fails closed with `EmissionStatus.REJECTED` and specific rejection reasons (`CUTOFF_EXCEEDED`, `FACT_RETRACTED`, `TRANSITIVE_LINEAGE_VIOLATION`).

---

## 3. Provenance Manifest Specification

Alongside every generated reference image, a verifiable JSON provenance manifest (`<asset_id>_manifest.json`) is serialized.

### 3.1 JSON Manifest Schema

```json
{
  "asset_id": "ref_test_novel_s1_p1_p5_k5_8863aa9b",
  "asset_kind": "character_portrait",
  "body_epoch_index": 1,
  "checkpoint_id": "",
  "discourse_cutoff": {
    "chapter": 5,
    "offset": 0
  },
  "effective_cutoff": {
    "chapter": 1,
    "offset": 0
  },
  "engine_id": "stub",
  "image_content_digest": "",
  "image_path": "/path/to/ref_test_novel_s1_p1_p5_k5_8863aa9b.png",
  "manifest_path": "/path/to/ref_test_novel_s1_p1_p5_k5_8863aa9b_manifest.json",
  "observer_id": "READER",
  "observer_scope": [
    "READER",
    "SYSTEM"
  ],
  "parent_asset_ids": [],
  "persona_id": "p1",
  "policy": "in_sequence",
  "prompt": "1boy, solo, male, black hair, inked manga illustration, clean lines",
  "prompt_digest": "8863aa9bf2da06ba",
  "provenance_version": "1.0",
  "rendering_params": [],
  "seed": 0,
  "self_id": "s1",
  "source_facts": [
    {
      "certainty": "CERTAIN",
      "fact_ref": "attr:p1:hair_color:black",
      "learned_at_pos": {
        "chapter": 1,
        "offset": 0
      },
      "observer_id": "READER",
      "retracted_at": null,
      "source_row_id": 1,
      "truth_status": "TRUE",
      "valid_interval": {
        "from_lb": 1.0,
        "from_ub": 1.0,
        "to_lb": 100.0,
        "to_ub": 100.0
      }
    }
  ],
  "story_interval": {
    "from_lb": 1.0,
    "from_ub": 1.0,
    "to_lb": 100.0,
    "to_ub": 100.0
  },
  "story_pos": 5.0
}
```

Serialization and deserialization methods are provided on `VisualAssetRecord`:
- `record.save_manifest(path: str | Path)`
- `VisualAssetRecord.load_manifest(path: str | Path) -> VisualAssetRecord`
- `record.to_dict()` and `VisualAssetRecord.from_dict(d)`

---

## 4. Verification & Model-Free Test Suite

The test suite in `packages/pipeline/tests/test_scoped_reference.py` executes 10 model-free test cases without invoking LLMs, downloading models, or generating GPU diffusion images:

| Test Case | Narrative Scenario | Epistemic Verification | Status |
|---|---|---|---|
| `test_sequential_reveal` | Scar disclosed at $k=100$, query at $p=5, k=5$ under `IN_SEQUENCE`. | Scar excluded from prompt and manifest; only ch 1 hair fact included. | PASS |
| `test_retrospective_reconstruction` | Flashback at $p=5$, reader at $k=100$ under `RETROSPECTIVE`. | Scar admitted into prompt and manifest alongside ch 1 hair fact. | PASS |
| `test_body_transition` | Mortal body active on $[1, 20]$, Zombie body on $[21, 50]$. Query at $p=25$. | Requesting Mortal body fails closed (`EMBODIMENT_MISMATCH`); default binds Zombie body. | PASS |
| `test_observer_restriction` | Reader secret mark vs. witnessed hair color for observer `wu_clan`. | Secret mark excluded for `wu_clan`; witnessed hair color admitted. | PASS |
| `test_retraction_preservation_and_invalidation` | Robes disguise learned at $k=1$, retracted at $k=50$. Queries at $k=20$ and $k=60$. | Believed at $k=20$ (robes in prompt); retracted at $k=60$ (robes excluded). | PASS |
| `test_transitive_lineage` | Derived asset depends on parent asset with cutoff $k=50$. Queries at $k=20$ and $k=60$. | Rejected at $k=20$ (`CUTOFF_EXCEEDED`); admitted at $k=60$. | PASS |
| `test_fail_closed_fallback` | Non-existent entity or missing parent asset. | Fails closed (`NO_ADMISSIBLE_EMBODIMENT`, `TRANSITIVE_LINEAGE_VIOLATION`). | PASS |
| `test_digest_sensitivity` | Cutoff $k=5$ vs $k=100$ on character with late-revealed scar. | Produces distinct prompts, prompt digests, and asset IDs. | PASS |
| `test_manifest_serialization` | Emission with disk output. | Manifest and image written; round-tripped JSON matches record and preserves SQLite row IDs. | PASS |
| `test_legacy_compatibility` | Legacy `generate_references` call on store. | Executes unmodified and returns standard `ReferenceReport`. | PASS |

### Test Suite Execution Output

```bash
uv run pytest packages/core/tests/test_visual_memory.py packages/pipeline/tests/test_scoped_reference.py packages/research/tests/test_import_direction.py packages/pipeline/tests/test_plan_builder.py
============================== 26 passed in 5.68s ==============================
```

---

## 5. Non-Negotiables & Integrity Audit

1. **Working Tree Safety**: No commits, stashes, resets, or overwrites were performed on pre-existing work.
2. **Rendering Behavior**: Default render plans and legacy `generate_references` remain completely unchanged. Scoped reference emission is an opt-in entry point (`emit_scoped_reference`).
3. **Zero Financial/GPU Cost**: All tests use in-memory SQLite fixtures and `StubImageEngine`. No LLM APIs, image diffusion weights, or network calls were initiated.
4. **Strict Architectural Layering**: Confirmed by `test_import_direction.py`. `echotales.core` does not depend on `echotales.pipeline`.
5. **Claims Discipline**: The implementation and tests demonstrate deterministic, provenance-checked input generation and manifest emission under narrative coordinates. They do not claim formal mathematical proofs of diffusion model behavior or entity resolution.
