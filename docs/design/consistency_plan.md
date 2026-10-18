# Plan: approved-reference identity and location consistency (no LoRA)

## Context

The first real LotM chapter 1 render (NoobAI XL, 8 GB laptop) came out inconsistent: hair shade and face changed
between panels, and the backgrounds wandered. The setting fixes (commits b22fc1a..97ab2a5, v6) now give one
consistent bedroom. Identity is still not fixed, because every panel is prompt-only: since EVOLUTION 4.47 the call
site hard-codes `reference_images=[]`, `reference_weight=0.0`.

Research (production platforms: Xiaoyunque/Seedance, Kling Elements, Catimind, LTX Studio; papers: AniMaker,
Character-Adapter, Unbounded, CANVAS) points to: approved asset baselines (character sheet, location image) ->
reference-conditioned generation -> reviewer loop that re-renders only flagged shots. Per-character LoRA is
excluded by the owner. Local models only. One model resident on the GPU at a time; no CPU-offload spill into RAM.

Intended outcome: with a flag on, panels are conditioned on HUMAN-APPROVED references only, characters keep their
hair/face, scenes in one room share a background, and failures are flagged and re-rendered selectively.

This plan is implementation guidance only. Nothing in it is built yet. Every threshold is a proposed starting
value, not a measurement; the owner confirms them before Phase 0 runs.

## Deliverables once this plan is approved (docs only, no code)

1. Write this plan to `docs/design/consistency_plan.md` (convention: `docs/design/video_plan.md`).
2. Add EVOLUTION section 4.107: the LotM render review, the setting fixes b22fc1a/d681013/b85f3b6/97ab2a5, the
   correction of the earlier "consistency decent" verdict, and the research findings above.
3. Update `docs/HANDOFF.md` "Pick up here" and "Open defects": identity plan; director drops the character name on
   pronoun-only beats; WORLD_CONTEXT eats ~22 tokens; 3-scene preview too sparse; 77-token CLIP limit with no
   verified long-prompt encoder; location facts never extracted (`extract_world` unwired); `scene_state`
   segment_id/index key mismatch; stale `IllustriousEngine` docstring (`panels.py:~534`).
4. Commit locally. Never push. No Co-Authored-By trailer, no emoji, no section symbols (`.claude/RULES.md`; the
   owner's rule overrides the harness's default attribution line).
5. Deliver the execution prompt to the owner for "agy" (Antigravity).

## Facts verified in code

- `render/panels.py:2776-2785` hard-codes empty references; `references`/`curated`/`weight` are computed
  (~:2843-2893) and discarded; `_honest_conditioned` (:2793) already reports `conditioned_on` only when references
  are really sent; `render/cache_key.py` already hashes reference paths and weight (`RENDER_CACHE_VERSION "2"`).
- `IllustriousEngine._load_ip_adapter` (:670) and `generate` (:693-760) still hold a working whole-image SDXL
  IP-Adapter path (CLIP ViT-H encoder, nested `[[images]]` input, blank image at scale 0 when a panel has none).
  `NoobAIEngine` (:932) inherits it and reports `max_references=2`. No mask/regional code exists.
- `ref_image_candidate` already has nullable `persona_id` and `quality_score` (`core/store.py:585-597`);
  `select_ref_image_candidate` (:1232) clears `selected` for the whole `(novel_id, self_id)`, which breaks
  multi-body characters. Generated sheets are not candidates; `reference_path_for` (`persona/reference_gen.py:813`)
  is their only reader (`render/plan_builder.py:223`, `render/panels.py:1485`).
- `world/extract.py::extract_world` is wired to no CLI/job: 0 location facts anywhere. LOCATION Self rows exist
  (LOTM 36, ORV 23, RI 12). `render/scene_state.py` builds the row id with `scene.index` (:75) but looks up by
  `segment_id` (:106); the table is empty everywhere.
- No image-embedding scorer exists. `VisualQAResult`/`QATier` and `RenderArtifact.qa_results` exist in
  `render/contract.py` but are never populated. `jobs.py` render job (:247-287) does not forward `block_range`.
- Environment: diffusers 0.39.0, transformers 5.15.0, torch 2.6.0+cu124. `open_clip`, `insightface`, `onnxruntime`
  are NOT installed. `h94/IP-Adapter` (incl. ViT-H encoder) and `Laxhar/noobai-XL-1.1` are in the local HF cache.

## Order and dependencies

```
Phase 5a (docs 4.107) -> start now, independent
Phase 0 (gate) -------> Phase 2 -> Phase 3 -> Phase 4
Phase 1a (data model/CLI) can run parallel to Phase 0 (it supplies approved sheets to Phase 0)
Phase 1b (UI) waits for the Phase 0 verdict
Phase 5b-d are parallel to everything
```

Blocked on the owner: hand-approving sheets for the Phase 0 characters; blind-labelling Phase 0 panels; confirming
thresholds; choosing Phase 4 location references; approving any new dependency or download.

Do NOT: auto-select any reference (4.47 bled colour from one auto-picked reference); add a per-character LoRA;
enable any cloud path or source `RUNPOD_*`/`OPENAI_*`; change Reverend Insanity prompts or cache keys with flags
off; run two models on the GPU at once; touch `.claude/worktrees/prefix-faithfulness`; edit the frozen project
document; restyle the webview; push; add a Co-Authored-By trailer.

## Phase 0: measurement gate (build nothing permanent first)

Goal: decide whether whole-image IP-Adapter at 0.5-0.8 on NoobAI XL fixes hair shade and face without colour
bleed, and whether regional masks are needed.

Create `scripts/eval/ref_conditioning_probe.py` (throwaway harness; instantiates `NoobAIEngine` directly). Output
to `data/eval/ref_conditioning/<date>/`: `grid.csv`, images, and a `labels.csv` the owner fills in blind (arm order
shuffled).

Setup: 2 LotM characters with clearly different hair/colour; the owner hand-approves one front portrait each from
`data/novels/LOTM/references/*.png` (regenerate with `persona/reference_gen.py` if a sheet is a poor anchor).
12 single-character prompts and 8 two-character prompts from the v6 ch1 render
(`data/novels/LOTM/panels/ch1/VERSIONS.md`); same seeds across arms.

Arms, single character: A0 none; A1 scale 0.5; A2 0.65; A3 0.8; A4 per-block scale via `set_ip_adapter_scale`
dict (mid + up blocks only; check the exact SDXL dict keys in the diffusers 0.39 docs, do not guess).
Arms, two characters: B0 none; B1 both images whole-image at 0.65; B2 both with left/right feathered masks via
`cross_attention_kwargs={"ip_adapter_masks": ...}` using `diffusers.image_processor.IPAdapterMaskProcessor` and
the nested `ip_adapter_image=[[img1, img2]]` contract already at `panels.py:746`. Verify the mask tensor shape and
that mask amplitude (0-1) scales per-image influence (Phase 4 depends on it).
84 images, about 65 minutes at ~45 s/image.

Measure (owner labels): hair shade correct Y/N per character; same face 1-5; colour bleed Y/N; prompt adherence
(pose, crowd, setting) Y/N. Record peak VRAM, resident system RAM (confirm `enable_model_cpu_offload` in
`IllustriousEngine` does not breach the no-RAM-spill rule), s/image. Log, but do not yet trust: CLIP ViT-H
image-embedding cosine between face crop and sheet (encoder already cached), Lab distance between hair medians.

Proposed pass criteria: a conditioned arm gets hair shade right on >= 80% of single-character panels and >= 25
points above A0; mean face >= 3.5 or wins >= 70% of paired comparisons vs A0; adherence no worse than A0 - 10
points; B2 bleed <= 10% and <= half of B1; peak VRAM < 7.5 GB with no swap growth. With ~12 panels the interval is
wide: near-threshold means inconclusive, expand to 24 prompts rather than deciding.

If it fails, work down: (1) lower scale / up-blocks only; (2) `ip-adapter-plus-face_sdxl_vit-h` for close-ups only
(check cache; download needs owner approval); (3) existing `init_image` img2img path for close-up faces; (4) skip
conditioning, do Phase 3 best-of-k with a fixed attribute template; (5) otherwise stop and write the negative
result in EVOLUTION. Do not build Phases 2-4. Effort: 1-1.5 days + ~30 min of owner labelling.

## Phase 1: approved character sheets

Data model: reuse `ref_image_candidate` (already has `persona_id`, an audit log, and the human-only
`selected=1` invariant). A generated sheet becomes a candidate: `backend='generated-sheet'`,
`source_url=file://<path>`, `persona_id` set, `id=f"{persona_id}:sheet:{sha1(file)[:10]}"`, `selected=0`.
Add nullable `role` column ('sheet' | 'location') via the existing `ALTER TABLE` reconcile block (~`store.py:585`).
v1 is ONE front-facing portrait per body (IP-Adapter copies composition; a multi-view sheet would pollute panels).

Fixes: scope `select_ref_image_candidate` unselect to `(novel_id, self_id, persona_id)` when the candidate has a
`persona_id`, and add a `persona_id` filter to `list_ref_image_candidates` (a reincarnated character's second body
must not evict the first). A regenerated sheet gets a new hash id, so the old approval no longer matches (stale).

The gate: `approved_reference_path(store, novel_id, persona_id) -> Path | None` in `persona/refimg.py`: returns a
path only if a `selected=1` candidate exists, the file exists and the sha matches. Swap it for
`reference_path_for` at `render/plan_builder.py:223` and `render/panels.py:1485` only when the Phase 2 flag is on.
First read how plan_builder uses the path; an unapproved sheet must not change the cache key.

Files: `core/store.py`, `core/models.py` (`RefImageCandidate.role`), `persona/refimg.py`,
`persona/reference_gen.py` (register sheets at the end of `generate_references`), `webview_server.py` (next to the
reference routes ~:1085/:1277/:1446-1506: `GET /api/novels/<id>/characters/<self_id>/sheets`,
`POST .../sheets/<persona_id>/approve` and `/reject`), `cli.py`/`commands.py` (`persona refimg sheets|approve|
import-sheets`), `webview/src/components/CharacterDashboard.js`, `webview/src/api.js`.
UI: per-body "Generated sheet" card with image, state badge (unapproved / approved "conditions panels" / stale),
Approve / Regenerate / Upload, grouped by body; served through the existing `_OUTPUT_KINDS` "references" route
(confirm it serves by path).

Tests: pytest `test_refimg_sheets.py` (`test_generated_sheet_registers_unselected`,
`test_select_scopes_by_persona_id`, `test_approved_reference_path_requires_selection`,
`test_regenerated_sheet_revokes_approval`); `test_webview_server.py::test_sheet_approve_route`; jest
`CharacterDashboard.test.js` "renders generated sheet card and approves" (mock `api.approveSheet` per method as in
`ProductScreens.test.js`).
Acceptance: an unapproved sheet never reaches a request; two bodies of one character stay selected; web-search
candidate behaviour unchanged. Effort 1.5 days backend/CLI + 1 day UI.

## Phase 2: conditioning re-wire with regional masks (flag off by default)

Flags (consistent with `pipeline/compute.py`, no third config mechanism): `ECHOTALES_REF_CONDITIONING=off|approved`
(default off), `ECHOTALES_REF_REGIONAL=on|off` (default on when conditioning is on); CLI mirror
`render --conditioning approved`. Resolve in a small `ConditioningPolicy` next to `policy()`. Flag off means
`reference_images=[]` exactly as today; Reverend Insanity stays byte-identical.

Modify: `render/panels.py` (call site :2776-2785 builds `reference_images` from approved characters by prominence,
weight from Phase 0's winning value; keep the crowd rule: a mob on a wide frame gets no sheet; the hand-curated
`curated` RI scene-reference path stays disabled until Phase 4); `PanelImageRequest` (~:138) gains
`reference_regions` (normalised boxes) and `reference_masks_feather`; `IllustriousEngine._load_ip_adapter/generate`
builds masks with `IPAdapterMaskProcessor` and passes `cross_attention_kwargs={"ip_adapter_masks": [...]}` (keep the
blank-image scale-0 branch at :750); `render/contract.py` capability `supports_regional_masks` (True for Illustrious
and NoobAI; False for stub/hosted, which keep `max_references=0`); `render/cache_key.py` hashes regions + flag
state, and with no references the hash must equal today's (golden test; bump `RENDER_CACHE_VERSION` only if that
changes).

Masks in v1 (no segmentation model): one character -> no mask, whole-image at the Phase 0 scale; two -> left/right
halves with 10-15% feathered overlap, ordered by the director's "left"/"right" layout words else first mention;
three -> thirds; more than three -> condition only the top-prominence ones and flag it. v2 option: director emits a
`positions` field (small prompt change that needs its own check on Reverend Insanity). No cross-attention-map or
SAM masks.

VRAM: ViT-H encoder (~1.2 GB fp16) + adapter is unmeasured (Phase 0 records it). If tight, precompute embeds once
per approved sheet with `pipe.prepare_ip_adapter_image_embeds`, cache to disk, pass `ip_adapter_image_embeds`;
verify this works with masks and CFG first. `compute.py::resource_refusal` should account for the adapter.
Fallbacks: adapter load failure -> existing warning, prompt-only; more refs than `max_references` -> truncate by
prominence; mask error -> whole-image at lower scale, logged in `PanelReport`.

Tests (`test_render_panels.py`, stub engine records the request; never compare colours across processes):
`test_conditioning_off_sends_no_references`, `test_only_approved_sheets_condition`,
`test_two_character_panel_gets_two_regions`, `test_conditioned_on_reports_only_sent_refs`,
`test_cache_key_unchanged_without_refs`; `test_cache_key.py`: key changes with region or flag.
Acceptance: owner's full ch1 run with the flag on reaches at least the Phase 0 hair-shade rate; with the flag off
all 1,444 existing tests pass and the manifest is unchanged. Risks: masks + `ip_adapter_image_embeds` interaction
in diffusers 0.39; a half-frame mask cutting across a close-up. Effort 3-4 days.

## Phase 3: reviewer loop (best-of-k, flagged-only re-render)

Scorer runs on CPU after each generation inside `render_panels` (the diffusion model stays resident; no second GPU
model). v1: CLIP ViT-H image-embedding cosine between the character's upper-body crop (Phase 2 region box, top part)
and the approved sheet, plus a Lab hair-colour distance. Alternative to evaluate if CLIP is weak: deepghs CCIP
(`dghs-imgutils`, onnxruntime, not installed; needs owner approval for new dependencies and a licence check).
Validate against the Phase 0 labels: stay `QATier.HEURISTIC` (flag only, never silently reject) until AUC >= 0.8 on
>= 60 labelled crops.

Best-of-k: k=1 first; a panel below threshold gets up to 2 more candidates (seed + 9973, the `MangaDiffusersEngine`
convention). Candidates under `<chapter_dir>/candidates/<stem>/seed<N>.png`; per-version `review.json` sidecar
(candidates, scores, chosen). Populate `RenderArtifact.qa_results` with `VisualQAResult`, set
`GenerationAttempt.retry_reason`, add `candidates`/`score` to `PanelReport`. Chosen path is stored under the
original render cache key. Check the actual flag rate in Phase 0 before committing to k (~45 s per extra
candidate).

Flagged-only re-render: `render_panels` gains `only_blocks`/`stems` and `from_version` (copy unflagged panels);
`jobs.py` render job (:247-287) forwards `block_range`, `stems`, `from_version` (today it forwards none and always
creates a fresh `_studio_version`); CLI reuses `--block-range` and adds `--rerender-flagged <version>`. First
confirm whether `cache_index.json` is shared across version directories.
UI: replace the "QA & regeneration" EmptyState in `GenerationWorkspace.js` (its test asserts "not yet available"
and must change) with a per-panel flag list and a "Re-render flagged" button; `OutputLibrary.js` needs panel
identity (block index, stem).
Tests: `test_review_loop.py` (`test_below_threshold_rerolls_up_to_k`, `test_qa_result_is_heuristic_tier`,
`test_only_flagged_rerendered`); `test_jobs.py::test_render_job_forwards_block_range`; jest
`GenerationWorkspace.test.js` "lists flagged panels and triggers rerender".
Acceptance: scorer ranking correlates with human labels (AUC above); a flagged-only rerun touches only flagged
panels. Risks: CLIP is crude for anime faces; drifting thresholds could mask real failures. Effort 3 days.

## Phase 4: location references

- Wire `world/extract.py::extract_world`: a `world` CLI subcommand and a `world` job kind in `jobs.py`; measure LLM
  cost on one chapter first; behind a flag.
- Scene -> location: `scene_location(store, novel_id, scene) -> self_id | None` (in `render/scene_refs.py` or new
  `render/locations.py`): most-mentioned LOCATION Self among the scene's mentions, else the chapter's most-cued
  place, else the existing `scene_locale` string. No new table; `ref_image_candidate` with `role='location'`, the
  character reference routes/UI reused under a Locations tab.
- Verify first, and fix if real: `render/scene_state.py` row id (:75) vs lookup (:106) key mismatch.
- Generation: one wide establishing image (~1216x832, no people) from the location's facts + `setting_first`
  (true panoramas out of scope), registered unapproved; owner approves one per location; only approved condition.
- Combined with characters: per-panel masks, each character its Phase 2 box, the location the complement
  (background) at lower amplitude (Phase 0 must have verified amplitude scaling); raise `max_references` to 3-4
  only if Phase 0 shows no quality/VRAM loss; no location reference on close-ups. Extend the Phase 0 harness with a
  location-scale arm (~0.3-0.5, to be measured).
Tests: `test_world_cli.py::test_extract_world_job_registers`; `test_locations.py`
(`test_scene_maps_to_most_mentioned_location`, `test_falls_back_to_locale`); jest Locations tab approval.
Acceptance: two LotM scenes in the same room share a background more closely than the v6 baseline (owner's
judgement) and characters keep hair colour with the location on. Effort 4-5 days. Blocked on: owner approving
locations. Risk: the location arm may fail; extraction quality is unmeasured.

## Phase 5: carry-over fixes

- 5a docs (do first): EVOLUTION 4.107 and HANDOFF, per the deliverables above; run `docs-sync` after each phase.
- 5b director omits the name on pronoun-only beats: carry the scene cast forward from the previous beat in the same
  scene (start in `render/beat_canon.py`, `render/director.py`, the cast-building part of `panels.py`; first read the
  RI `v44_carry-forward-cast-fix` and whether it is book-gated). Test `test_pronoun_only_beat_inherits_scene_cast`.
- 5c WORLD_CONTEXT: split the atomic ~22-token string into clauses so `persona/prompt.py::fit_to_budget` drops
  partial pieces; only add when the budget has room. Test `test_world_context_drops_by_clause`.
- 5d preview tier and long prompts: make the 3-scene preview (`compute.py` `policy().scenes_for`) pick for coverage
  (distinct places/casts), optionally a 5-scene tier; spike `sd_embed`/`compel` long-prompt chunking on NoobAI in
  `scripts/eval/` and measure; do not wire it in blind (the 77-token budget stays hard until proven).
- Golden test: Reverend Insanity prompt output byte-identical with flags off.

## Verification, end to end

1. `python3 -m pytest packages/core/tests packages/pipeline/tests` green (1,444 baseline; stub-first, no GPU) after
   every phase; research tests explicitly with `-o addopts=""`; webview jest (112 baseline).
2. Phase 0 verdict recorded in EVOLUTION before any Phase 2 work starts.
3. Real renders only after checking the GPU is free (`nvidia-smi`), one model at a time, local ollama only.
4. Each real render gets a suffixed version dir and a one-line `VERSIONS.md` entry with an honest viewer verdict.
5. Phase 3 scorer validated against the owner's labels before being trusted.
6. Measured numbers go in EVOLUTION/HANDOFF with "verified" vs "should work" kept distinct.
