# Visual rendering — architecture status

**Purpose:** the authoritative current-state doc for the image-generation
path, the way `HANDOFF.md` is for open tasks and `EVOLUTION.md` is for
historical reasoning. This file describes what the renderer actually does
today and what changed in the Visual Rendering Track; it does not replace
`data/<novel>/panels/ch<N>/VERSIONS.md`, which stays the per-render-run log.

Read `EVOLUTION.md` before any model/checkpoint decision — the render history
below (v1-v54) records real reversals for measured reasons; don't repeat one.

## As of 2026-09-21 — audit baseline, before this track's changes

### Engine inventory

All engines live in `packages/pipeline/src/echotales/pipeline/render/panels.py`
unless noted. `get_engine(name, **kwargs)` (panels.py:876-907) dispatches by
name: `stub|sdxl|illustrious|refined|noobai|manga|gemini|openrouter`.

| Engine | Base | Steps/CFG | Reference support | Notes |
|---|---|---|---|---|
| `StubImageEngine` (162-194) | — | — | none | solid PNG, no GPU, used by every existing test |
| `SDXLEngine` (197-253) | SDXL base 1.0 | 30/7.0 | none | generic base class |
| `MangaDiffusersEngine` (256-454) | GuoFeng3 (SD1.5) | 40/7.5 | IP-Adapter, max 2 refs | has the only pixel-aware retry (`_is_flat`, 929-944) |
| `IllustriousEngine` (457-739) | Illustrious-XL | 30/6.0 | IP-Adapter + img2img (`_ensure_img2img_pipe`, 531-567) | base class for NoobAI |
| `RefinedEngine` (742-835) | NoobAI compose + GuoFeng3 restyle | 30/7.0, strength 0.35 | inherits base engine's | the only existing 2-pass mechanism, full-frame restyle, not layered by role |
| `NoobAIEngine(IllustriousEngine)` (839-873) | `Laxhar/noobai-XL-1.1` | 35/7.0 | inherits Illustrious | current default/primary checkpoint |
| `GeminiImageEngine` (`render/gemini.py:69-131`) | hosted | — | ignores refs/init_image entirely | retries once on refusal |
| `OpenRouterImageEngine` (`render/openrouter.py:94-167`) | hosted | — | ignores refs/init_image entirely | retries once on refusal |

### The two-cache problem (fixed in Phase 1, see below)

Two disjoint caches exist inside `render_panels`:
- **Prompt cache** (panels.py:2115-2121): keyed on `{chapter}:{lead}:
  {beat_digest}:{db_fingerprint}` — no engine/model/seed component, by design
  (decouples the LLM direction pass from the image pass).
- **Image cache** (panels.py:1836-1838, 2430-2437): pure **file-path
  existence** — `if image_path.exists(): skip`. A within-run prompt-content
  digest is used only for cross-panel dedupe inside one run, never persisted.

**Consequence (pre-Phase-1):** swapping `--image-engine`, checkpoint, seed, or
steps and re-running against the same output directory silently served the
stale image from the previous configuration, with no error or warning.

### The IP-Adapter call-site-vs-engine-code inconsistency

IP-Adapter is **not removed from the SDXL engine classes** —
`IllustriousEngine`/`NoobAIEngine` still carry full, working IP-Adapter code.
What was removed (EVOLUTION Section 4.47, measured colour/composition contamination
that didn't generalize across novels) is the **call site**:
`render_panels`'s per-panel loop unconditionally passes `reference_images=[],
reference_weight=0.0` (panels.py:2597-2607). Dead code just above it
(`match_scene_references`, panels.py:2478-2482) still computes curated
references that are then discarded — the manifest's `conditioned_on` field
could (pre-Phase-1) claim conditioning that never reached generation.

### The `self_id` vs `persona_id` granularity mismatch

`RefImageCandidate`/`RefImageSelectionEvent` (`packages/core/src/echotales/
core/models.py:539-584`) are keyed by `self_id` — candidate search has no
body/state-epoch dimension. Generated reference sheets (`persona/
reference_gen.py`) are already keyed per `persona_id` (one sheet per body).
These two paths don't share a key today.

### Baseline artifact

`data/RI/panels/ch1/VERSIONS.md`'s `v54_crowd-solo-scenestate-fix`
(2026-08-30/31, 51/51 panels, pixel-reviewed) is the most recent complete real
render and the baseline this track benchmarks against. `v10-v27` and `v45-v51`
are undocumented gaps in that log — never repeat this.

---

## Visual Rendering Track — phase log

See `/home/adhyan/.claude/plans/happy-weaving-crescent.md` for the full
phased plan. Status below is updated as each phase lands.

### Phase 0 — this document + EVOLUTION kickoff entry — DONE (2026-09-21)

### Phase 1 — typed contract + cache/provenance fix

**Status: partially done (2026-09-21).** Verified green:
`pytest packages/pipeline/tests/ packages/core/tests/ -q` (full suite,
including the new files below) and no behavior change to any existing engine.

**Done:**
- **1a — typed contract**: `render/contract.py` (`CharacterRole`,
  `CharacterRenderSpec`, `EnvironmentRenderSpec`, `CompositionSpec`,
  `VisualRenderPlan` + `plan_digest`, `GenerationRequest` wrapping
  `PanelImageRequest`, `GenerationAttempt`, `QATier`, `VisualQAResult`,
  `RenderArtifact`, `RenderBackendCapabilities`). Every engine in
  `panels.py` (`StubImageEngine`, `SDXLEngine`, `MangaDiffusersEngine`,
  `IllustriousEngine`, `RefinedEngine`, `NoobAIEngine`) plus the hosted
  engines (`GeminiImageEngine`, `OpenRouterImageEngine`) now expose a real
  `capabilities` property instead of the one hardcoded `hasattr` check that
  existed before. `PanelImageEngine` Protocol updated to declare it. Hosted
  engines' `generate()` now types its parameter as `PanelImageRequest`
  instead of bare `object`. `NoobAIEngine.quality_prefix` dropped
  `"masterpiece"` (kept `"score_9, score_8_up"` only) per the confirmed
  Phase 1 decision — not yet A/B-benchmarked against the old value, that's
  Phase 2/3's job.
- **1b — cache key module, not yet wired in**: `render/cache_key.py::
  compute_render_cache_key(plan, request)` — a single digest over
  state_digest, plan_digest, prompt, negative_prompt, backend, checkpoint
  id+version, LoRAs, reference paths+weight, seed, dimensions, steps,
  guidance, and a `RENDER_CACHE_VERSION` constant. **Tested in isolation
  (`test_render_cache_key.py`, 8/8 passing) but NOT yet wired into
  `panels.py`'s actual cache-check sites** (still file-path-existence only,
  panels.py:1836-1838/2430-2437 as of this writing) — the stale-image bug
  this module exists to fix is not yet closed in the real render path. That
  wiring, plus the `conditioned_on`-manifest truthfulness fix, is the next
  concrete step.
- **1d — reference schema reconciliation**: `RefImageCandidate`/
  `RefImageSelectionEvent` (`core/models.py`) gained optional `persona_id`
  (both) and `quality_score` (candidate only), persisted via an additive
  `Store._migrate()` ALTER TABLE, following the project's existing migration
  pattern exactly. Verified: `test_refimg_persona_reconciliation.py`, 4/4
  passing, including a pre-existing-database migration test.

**Not done yet (explicitly, not silently skipped):**
- 1b's cache-key module is not wired into `render_panels`'s actual
  generation loop — the stale-image-on-engine-swap bug is diagnosed and has
  a tested fix module, but the real render path doesn't call it yet.
- 1c (persona-level `VisualRenderPlan` derivation from real `state_of()`,
  `render/plan_builder.py`) — not started.
- No real (non-stub) local render has been run yet with any of this wired
  in — Phase 1's own exit criteria requires one demonstrating the cache-key
  fix actually invalidates on a seed change; that hasn't happened since the
  wiring itself isn't done.
- `NoobAIEngine.quality_prefix`'s masterpiece removal has not been
  A/B-compared against a real render yet.
