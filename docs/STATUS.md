# EchoTales — authoritative current status

**Purpose:** the single place that answers "is X actually working, and how do
we know?" — reconciled directly against code, tests, and real artifacts, not
against what `HANDOFF.md`/`EVOLUTION.md` claim. Those two files are not
wrong on purpose, but they drift (see "Stale claims found" below), and this
document exists specifically to be mechanically re-checkable rather than
trusted.

**Last reconciled:** 2026-09-23, via three parallel codebase audits (render
pipeline, persona/reference identity + core models, webview/backend/job
system, audio/TTS pipeline) that read the actual implementation, tests, and
on-disk artifacts rather than summarizing docs. File:line citations below
were verified at that time; re-verify before trusting a citation against a
much later commit.

**Update, same day (2026-09-23):** the "Gold datasets", "Evaluation
harness", and "Baselines" rows below were re-reconciled after the gold
retraction (`EVOLUTION.md` 4.74) — see "Stale claims found this pass" #5.
The confirmed-tier B³ numbers those rows used to cite no longer exist as a
claim anywhere in this document.

**Update, same day:** the "Jobs/progress", "File upload", "Output library",
and "Backend API" rows below were re-reconciled after the Product
Orchestration track landed (see `HANDOFF.md`'s new section and
`EVOLUTION.md` 4.73) — the "Missing" verdicts they previously carried are
now stale and have been corrected in place, not left to silently
contradict a later HANDOFF entry.

**Update, 2026-09-24:** the "Identity resolution / resolver", "Scorer",
"Evaluation harness", "Baselines", "Gold datasets", "Ablations" and
"Temporal state (`state_of`)" rows below were re-reconciled against
`EVOLUTION.md` 4.76-4.82 (mention-layer truncation fix, resolution
provenance, the ablation harness, the observer axis, the evidence layer).
**Truth constraint that must survive any future edit to this file:** the
real ollama re-run that would show 4.76's effect on recall/attribution has
**not been run** — nothing below may say or imply mention recall, CEAF-e,
or speaker attribution improved. Everything attributed to 4.77-4.81 below
**is** measured on real data (resolution needs no LLM and runs off
already-stored mentions), and there is still zero confirmed gold.

**How this relates to other docs:**
- `EVOLUTION.md` stays the historical, append-only reasoning log — never
  edit it to "fix" a stale claim, add a new dated section instead.
- `HANDOFF.md` stays "what to pick up next" — update it, don't duplicate it
  here.
- `docs/VISUAL_RENDERING.md` is the deeper status doc for the render
  subsystem specifically (Visual Rendering Track).
- This file is the 30-second-scan summary across the whole system.

---

## Stale or misleading claims found this pass

1. **"Recurring Unnamed Characters — done"** (`HANDOFF.md` webview section,
   citing `test_unnamed_recurring_character_persistence.py`). True, but
   answers a different question than it appears to: it verifies
   `resolve_novel` assigns the same `target_id` to a recurring epithet
   mention across chapters — it does not touch voice. `speakers/runner.py::
   _assign_anonymous_slots` mints ids as `f"{novel_id}:anon:{chapter_number:g}
   :{scene_key}:{slot}"` (chapter-scoped by construction), so a recurring
   unnamed character still gets a fresh anonymous **voice** every chapter.
   Open defect #8 is real and unfixed in the audio path; the HANDOFF bullet
   describes an adjacent, already-fixed problem in a different layer.
2. **The `TRANSFERABLE_TITLE` recall@k gate** (HANDOFF's former top "Pick up
   here" item) was resolved this session (EVOLUTION §4.69) as an
   eval-design defect, not a data-coverage gap: `generate_gold.py` only
   admits mentions with a resolved `target_id`, but every real
   `TRANSFERABLE_TITLE` mention on RI correctly resolves to `None` by
   design (non-negotiable #9). The gate cannot produce a number on this
   novel no matter how much more gets annotated.
3. **IP-Adapter "removal"** (EVOLUTION §4.47) is real but narrower than the
   phrase suggests: the SDXL engine classes (`IllustriousEngine`/
   `NoobAIEngine`) still carry full working IP-Adapter code; only the
   `render_panels` call site was changed to pass empty references. Dead
   code above it still computes curated references that are then discarded.
4. **The image cache** was pure file-path existence before this session's
   Phase 1 work (`render/panels.py`, pre-2026-09-21) — swapping engine/
   checkpoint/seed and re-rendering into the same directory silently served
   a stale image. A tested fix module (`render/cache_key.py`) exists as of
   2026-09-21 but is **not yet wired into the real cache-check sites** —
   don't read its existence as the bug being closed.
5. **The headline coreference result is retracted, not just superseded**
   (`EVOLUTION.md` 4.74, 2026-09-23). The confirmed-tier B³ figure this
   document previously reported (precision=100.0%, recall=94.6%,
   f1=97.2%, RI ch1-60, 1,816 mentions) was scored against
   `reverend-insanity-c1-c50.jsonl`, gold built by
   `eval/generate_gold.py::_extract_gold_from_db` by `SELECT`ing the
   pipeline's own `mention` table and then marked
   `provenance: human, confirmed: true` on 2026-08-12 without an
   independent human pass — it measured the system against itself.
   Precision of exactly 100.0% was the arithmetic signature of that, not
   a result. That file is now quarantined at
   `data/gold/_unusable/reverend-insanity-c1-c50.jsonl` (see its
   `README.md`) and every other draft file in `data/gold/` is
   `confirmed: false` — **zero gold records exist anywhere in the corpus
   as of this pass.** `eval/gold.py` now enforces this structurally
   (`CIRCULAR_DRAFTERS`, `GoldProvenanceError`, `ReviewDepth`), so a
   repeat of this specific failure should raise instead of silently
   producing a number.

---

## Component status matrix

Status legend: **Verified** (real artifact + passing test, or measured
against real data) · **Partial** (works for a real, bounded subset;
documented gap remains) · **Experimental** (implemented but its own code/
docs defer the success verdict) · **Missing** (confirmed absent by grep/read,
not merely undocumented).

| Component | Current implementation | Status | User-visible consequence | Research consequence | Recommended action | Depends on |
|---|---|---|---|---|---|---|
| Ingestion | EPUB→chapters/blocks, 3 novels fully ingested (198-213 ch each) | Verified | none — works | none | — | — |
| Block/span classification | `ingest/classify.py`; ORV bracketed `SYSTEM_WINDOW` fixed (§4.64); 188 stray `HEADING` blocks/novel remain (open defect #9) | Partial | minor: a few blocks misclassified per novel | small noise in span-type-conditioned metrics | root-cause the residual HEADING blocks (bounded, not urgent) | — |
| Mention detection | Qwen2.5 NER + gazetteer; `TRANSFERABLE_TITLE` fixed end-to-end (§4.62). Root cause of the recall ceiling found and fixed in code (EVOLUTION 4.76, 2026-09-23): `ner.py` was sending only `text[:6000]` per chapter and stopping, invisible to roughly half of every novel (RI median chapter 11,667 chars, 199/199 chapters over 6,000, only 51.9% of text ever reaching the model; `item` also missing from the label set). Now windows the full chapter (~3 calls/chapter) and offers `item`. **Landed and unit-tested, not yet run against real ollama output — effect on real recall is unmeasured**, see HANDOFF's "Pick up here" | Partial | some dialogue still goes unattributed as of the last real run; whether the fix changes that is unknown | recall ceiling mechanism identified and patched, real-data effect unadjudicated | run the real re-resolve (`docs/COMPLETION_PLAN.md` Track 1 item 3) and report the delta, favourable or not | — |
| Speaker attribution | 45.5% identifiable (§4.60), honestly measured after removing a turn-taking tier proven wrong 82.9% of the time — **this number predates the NER windowing fix above and has not been re-measured against it** | Partial | ~half of dialogue lines have no confident speaker | limits audiobook casting quality | re-run against the windowed NER path before doing any more attribution-layer tuning | mention detection |
| Identity resolution / resolver | Hand-tuned pre-filters carry every real link; the learned scorer is confirmed structurally too weak (defect #1, precision plateaus 0.66-0.77, six clan members merge under calibration). **Measured on real RI data (§4.77/4.78, 2026-09-23):** `by_method` no longer hardcodes `SCORED` — real breakdown of 880 links is `GAZETTEER_EXACT=870, DECLARATION=5, NAME_CONTAINMENT=2, RELATIONAL_COPRESENCE=3, SCORED=0` — i.e. **the scorer settles no link at all**. (`resolve`'s printout shows `SCORED=82`; that is exactly the count of *created* entities, not links, so the two agree.) Re-scoring a 10,058-pair evidence cache under every ablation condition shows the scorer's real maximum output is 0.527 against the 0.80 link threshold; `temporal_validity` blocks zero of 2,051 real pre-filter blocks (all from `co_presence_violation`) | Partial | none directly (pre-filters cover the real cases) | scorer is not a defensible ML contribution as-is — now confirmed on real pairs, not only the theoretical 0.711 bound | new candidate-evidence feature family (Part K), not reweighting | — |
| Candidate retrieval | `resolve/retrieve.py::CandidateRetriever`; recall@10 real: `RIGID_NAME` ~100%, `RELATIONAL_DEICTIC` 0%→59% (§4.60 fix), `TRANSFERABLE_TITLE` structurally unmeasurable (§4.69, stale-claim #2 above) | Partial | none | 1/3 alias types has no defensible recall@k number, ever, on this novel, under the current eval design | redesign the eval question for `TRANSFERABLE_TITLE` (score correct-DEFER, or use a novel with an eventual reveal) | mention detection, gold set |
| Scorer | `resolve/score.py`, 5 dense features + 3 hard pre-filters | Experimental (confirmed unfixable by reweighting; §4.78 measured its real max at 0.527 vs. a 0.80 threshold over every one of 10,058 real pairs — arithmetically incapable of linking, not merely untuned) | none (pre-filters cover real traffic) | central open research problem | see Part K plan | candidate retrieval |
| Temporal state (`state_of`) | `core/state.py::StateResolver.state_of` — three-axis time, timeline/observer-aware, returns `persona_ids: list[str]` (plural, supports concurrent bodies). **The observer axis was schema+model+query with no writer until §4.80 (2026-09-23):** `Store.add_observation`, `resolve/detect_observations.py`, `render --observer` now exist, and `architecture.md`'s headline acceptance test passes on real data for the first time — RI's Bai Ning Bing at ch200 returns 2 aliases for `READER`, 1 (strict subset) for a witness, 0 for a non-witness | Verified | none | the real research contribution, working as designed, and now demonstrated on real data rather than only unit tests | — (do not touch without a measured defect) | — |
| Truth status (retract vs. close_interval) | `core/enums.py::EventType`, deliberately distinct members | Verified | none | non-negotiable #5, holding | — | — |
| Contradiction detection | `resolve/contradiction.py`, swept at window boundaries | Experimental (fires on constructed over-merges, zero hits on 60 real chapters — diagnostic of Phase 6 over-splitting, not proof the detector works) | none observed yet | can't yet claim it catches a real contradiction | needs validation against real data once resolution has anything to over-merge | resolver |
| Self/Persona split | `persona/split.py` — `BodyChange` detection, `BodyEpoch`, `write_epochs`; LOTM transmigration linking + split verified end-to-end | Verified for detected transmigration/reincarnation cases | none | supports the paper's central downstream-embodiment claim | audit disguise/possession/clone (concurrent, not sequential) cases separately — schema supports it, no dedicated test exists yet | resolver |
| Body-state appearance | `persona/build.py`, `attire.py`; extraction contamination fixed (§4.49, 16/16→0/16) | Partial | none observed | RI's real body2 (Fang Yuan) has zero appearance attributes — blocks a real img2img/appearance-transition test today | populate/extract body2 appearance for at least one real case | Self/Persona split |
| Reference-image generation | `persona/reference_gen.py` — one sheet per `persona_id` (body-qualified) | Verified for txt2img; img2img body-transition **experimental** (full pipeline built, GPU-completion unconfirmed, own code comments defer the verdict) | none for txt2img; img2img not in any product path | img2img A/B (independent-gen vs. transition) has never been run to completion | run img2img once on an idle machine, side-by-side vs. independent generation | body-state appearance |
| Reference-image search | `persona/refimg_search.py`, DuckDuckGo-backed, quality-filtered, deliberately not auto-wired into generation | Verified (as a manual review tool) | reviewer can browse candidates; nothing auto-selects | — | — | — |
| Panel direction | `render/direction.py` — LLM art director + 5 guardrails (hallucination stripping, cast validation, crowd/layout rewrite, invented-second-subject logging) | Partial | v54 (latest complete real render) is the best output that exists, still below product bar | prompt-wording changes alone repeatedly failed (§4.45/4.46) — architecture-level fixes are what moved real numbers | benchmark-first per Visual Rendering Track before more prompt changes | mention/resolution, SceneState |
| SceneState | `render/scene_state.py`; v54 fixed the byte-identical-crowd-panel bug | Verified post-v54, with a documented partial-backfill caveat for pre-existing databases (kind=NULL rows) | none on fresh databases | — | — | resolver |
| Beat segmentation | `render/scenes.py`/`beats.py`, `_MAX_BLOCKS_PER_PANEL=4` | Verified | none | — | — | — |
| Image generation | `render/panels.py` — GuoFeng3/Illustrious/NoobAI/Refined, all 8GB-VRAM CPU-offload | Partial (technically works, quality below product bar by the user's own standard even at v54) | visual output is the weakest part of the product | central open question: model/compute vs. architecture — untested until Visual Rendering Track Phase 3 | see Visual Rendering Track plan | panel direction |
| Image conditioning | IP-Adapter code still present in SDXL engines; call-site conditioning removed (§4.47) for measured contamination; `RenderBackendCapabilities` typed model now exists (2026-09-21, unwired) | Verified-removed-at-callsite / capability model Experimental (just built, not yet used to reintroduce conditioning) | none currently (prompt-text-only identity) | any reconditioning approach must beat the documented contamination baseline with evidence | Visual Rendering Track Phase 4b (conditioning benchmark) | image generation |
| img2img (body transition) | `persona/reference_gen.py` + `_img2img_worker.py` + `panels.py::IllustriousEngine._ensure_img2img_pipe` — full subprocess-isolated pipeline | Experimental — own code comments defer the "does it complete on real hardware" verdict; no completed run exists | not in any product path | no side-by-side identity/contamination comparison exists yet | run once on idle hardware (Visual Rendering Track Phase 4c) | reference generation, body-state appearance |
| Multi-character composition | Capped at `max_references=2`; SD1.5 (GuoFeng3) cannot hold hero+crowd together (measured checkpoint ceiling, §4.45/4.46); role-based typed model (`CharacterRole`) built 2026-09-21, not wired to any generation-time behavior | Partial | crowd/3+-person panels are the weakest single case | ceiling confirmed to be checkpoint, not prompt — a real, citable finding | Visual Rendering Track Phase 4a, gated on Phase 3 evidence | image generation |
| Motion generation | `render/motion.py`, SVD, 8GB cpu_offload — real chapter video exists (§4.24) | Verified functional; shot-rule quality **never manually reviewed** (EVOLUTION's own follow-up item, "Watch the output") | motion may be technically present but visually wrong and nobody has looked | — | eyeball a real chapter's motion before trusting the heuristics | image generation |
| Video composition | `render/compose.py`, `FfmpegComposeEngine`, real `.mp4` output exists | Verified functional | — | — | — | motion generation |
| 9:16 reels engine | `render/reels.py` — pure dataclass/enum planning logic, **no ffmpeg call, not imported by any generation path** | Missing (as a working feature; present only as unwired planning logic) | reels don't exist as a deliverable today | — | wire into `compose.py`, or drop the claim that it's built | video composition |
| Audio/TTS | `voice/engine.py::ChatterboxEngine`, real (not stub) — two full-chapter real renders exist (RI ch1 545s, LOTM ch1); casting deterministic per-seed | Verified (core synthesis + real artifacts); `render_novel` orchestrator has **zero direct test coverage** | audio works when manually invoked; nobody has re-verified it in CI | confidence rests on 2 manual artifacts, not automated tests | add an integration test that actually calls `render_novel`, even gated | speaker attribution, casting |
| Temporal voice/persona state | `persona/build.py::load_trait_profiles` is explicitly body-independent (`persona_at(store, entity.id)` picks one profile per Self, any epoch) | **Missing** entirely — confirmed by reading the code, not merely undocumented | a transmigrated character (LOTM's Zhou Mingrui→Klein Moretti) sounds identical in both bodies | this is the audio-side twin of the render track's central `state_of`-vs-flat ablation, and it doesn't exist yet | plans.md Phase 9 items 1/3/5, unbuilt | Self/Persona split, voice casting |
| Delivery markers / inner monologue / prosody | `voice/delivery.py::settings_for` — genuinely wired into `SynthesisRequest.exaggeration`/`cfg_weight`/reference-clip emotion selection (§4.39), not just detected upstream | Verified | audio delivery actually varies by narrative signal | a real, working, non-trivial mechanism worth keeping in the paper | — | — |
| Spatial reverb / audio effects | Only pitch-shift exists (`voice/pitch.py`, ffmpeg rubberband); no reverb/room effect anywhere | Missing | flat audio space | — | plans.md Phase 9 item 5, unbuilt | — |
| Chapter audio packaging | No per-chapter audio-only file from the voice stage itself; concatenation only happens as a side effect of video composition (`compose.py::concatenate_audio`) | Partial | no standalone "listen to chapter N" audio artifact exists | — | promote chapter audio to a first-class artifact if audiobook delivery matters as a demo surface | video composition |
| Frontend | (2026-09-22, editorial/archive product-polish pass) Full shell rebuild: `App.js` is now a rail(nav)+workspace+inspector layout, not header tabs — six screens (Script/Characters/State/Generation/Outputs/Project), all real or honestly marked unavailable, none fake. Dead blue-gradient CSS (`.btn-primary`/`.btn-gradient`/`.view-tabs`) deleted (zero `.js` references, confirmed by grep before deletion). New primitives: `DepthCard`/`ManuscriptSurface`/`TimelineRail`+`StateNode`/`ArchiveRow`/`DossierHeader`/`MediaArtifact`/`InspectorSection`/`JobStatusBadge`. `ScriptView` wrapped in `ManuscriptSurface` (all six existing interactions — mention/speaker click, flag, create-mention, merge, retype — reverified working post-restyle, manually, against a real live backend). `CharacterDashboard` gets a `DossierHeader`, a real "Search for more references" action, and an honest `TimelineRail` (no epoch data exists in the payload — confirmed by reading `build_character_dashboard`, so it never fabricates one). `NewProject`'s upload `<input>` is enabled and wired to the real `POST .../source` route; `ProjectHome` adds a real "Start ingestion" trigger. Theme toggle (`theme.js`, previously dead infrastructure — `initTheme()` was called at load but nothing exposed a switch) now has a real control. 18/18 tests pass (`Section7Smoke.test.js` + new `ProductScreens.test.js`); manually verified against the real `reverend-insanity` canonical DB via Playwright (Script/Characters/dossier/Project/Outputs/Generation screens, ink+paper themes, a real mention-click→EntityPicker round trip) — no console errors | Verified | the whole app has one coherent visual identity end to end; three previously-nonexistent screens (Generation/Outputs/Project) now show real backend data | — | wire remaining secondary screens (`EntitySidebar`/`ChapterNav`/`AnalysisPanel`/`EntityPicker` still plain-CSS, not yet migrated to the token system) if a future pass wants full consistency | backend routes (all now consumed) |
| Backend API | stdlib `http.server` (`webview_server.py`), review/correction routes plus (2026-09-22, Product Orchestration track) project lifecycle, job triggers/status, EPUB/reference upload, render preview/generate, output library — see `details.md`'s `webview_server.py` entry for the full route list | Verified — `test_jobs.py`/`test_webview_server_jobs.py` pass (11 tests), stub-mode dispatch only, no real GPU/network run performed | reviewer can correct data, upload an EPUB, trigger every stage, and browse output, all over HTTP; **now consumed by the frontend** (2026-09-22 product-polish pass) — `api.js` has a wrapper for every route | — | — | job system |
| Jobs/progress | `jobs.py::JobQueue`, one in-process daemon worker thread, strictly sequential process-wide (matches the existing ollama/diffusion GPU-sharing constraint); `job` table (`store.py`) + `Job` model (`models.py`); `GET /api/projects/<id>/jobs`(`/<job_id>`) exposes status including nested `StageRun` detail. Resumability (skip-on-matching-`SUCCEEDED`-digest via `pipeline_run.py::stage()`) is live end-to-end. **`ManuscriptProgress.js` is still fed a hardcoded placeholder in `NewProject.js`'s "preview" section** (deliberately — it illustrates what ingestion *will* look like before a file is even picked); real job polling is wired into `GenerationWorkspace` (render jobs) and `ProjectHome` (ingest jobs) instead | Verified for dispatch/sequencing/resumability via `test_jobs.py`; frontend polling verified via `ProductScreens.test.js` + manual check | real render-job status visible in the Generation screen; real ingest-job trigger visible in Project home | — | wire `ManuscriptProgress.js` itself to a live job once one is running, instead of only showing the pre-upload preview | backend API |
| File upload | `POST /api/projects/<id>/source` (EPUB, via stdlib-only `_multipart.py` parser, validated by actually opening the file with `Epub()` before accepting) and `POST /api/novels/<id>/characters/<self_id>/reference/upload` (reference image, same parser). **The upload `<input>` in `NewProject.js` is now enabled** and calls the real route (2026-09-22) | Verified for the backend route (integration test) and the frontend call (`ProductScreens.test.js`-adjacent `Section7Smoke.test.js` case, plus manual check) | a reviewer can create a project and attach its EPUB entirely from the browser | — | — | job system |
| Output library | `GET /api/novels/<id>/output` (pure filesystem walk of `data/<CODE>/{panels,video,audio,references}/` per `pipeline/paths.py`'s layout, no new metadata table) and `GET /api/novels/<id>/output/file` (serves one file, path-escape-checked against `paths.novel_root`). **`OutputLibrary.js` now consumes this** (2026-09-22) — verified manually against the real `reverend-insanity` output directory (a real 262.6 MB `ch1.mp4` rendered correctly; the Reels tab correctly always reads "not produced yet," since `render/reels.py` has no ffmpeg call and there is no reels kind in the listing at all) | Verified via integration test + manual browser check against real data | a reviewer can browse real rendered output from the browser | — | — | backend API |
| Evaluation harness | `echotales eval --report` — B³ scoring (draft + confirmed tiers), self-retrieval smoke test, gold recall@k gate. **Extended §4.79-4.81 (2026-09-23):** `Store.escalation_summary()` now prints escalation rate at the top of every run (RI: 370 calls, 0 escalations, 0.0%); `held_out_coverage` (chapter-range split, never random) validates conformal coverage on unseen data rather than the calibration set itself; `eval/stats.py` bootstrap CIs on every reported number (caught a real coordinate bug on first use — a linked-share CI computed 0.4% instead of the correct 98.6% because it keyed gold offsets against block-local `mention.offset`); `eval/persist.py` writes `data/eval/results/<run_id>/metrics.json` with commit/seed/platform, `-dirty` marker included honestly | Verified as infrastructure, and now measurably richer — the confirmed-tier and draft-tier numbers it has ever printed are both self-agreement (EVOLUTION 4.74) because the gold they scored against was drafted from the pipeline's own `mention` table; also **one alias type structurally unmeasurable** by current design (stale claim #2) | — | the reporting mechanism is real, enforces `CIRCULAR_DRAFTERS`/`ReviewDepth` (`eval/gold.py`), and now reports escalation/coverage/intervals, but has never yet had a non-circular gold set to score against | build gold that is independent of the system under test (see Gold datasets row), then redesign the `TRANSFERABLE_TITLE` eval question | gold datasets |
| Gold datasets | Draft coverage only, all drafted from pipeline output except two small independent files: RI 198/199 ch (7,879 records, 4,422 of them `mention`-table-derived), LOTM 213/213 ch (6,756, 100% derived), ORV 186/188 ch (4,836, 100% derived), plus `reverend-insanity-c1-c5.jsonl` (343 records, LLM read chapter text directly — independent) and `reverend-insanity-hardcases.jsonl` (89 records, independent). **Confirmed: 0 records across the entire corpus** as of 2026-09-23 (EVOLUTION 4.74) — the 6,952-record file that previously read `confirmed: true` was circular (scored against its own source) and is quarantined at `data/gold/_unusable/`; the 3,457 records elsewhere that read `confirmed: true` were a 2026-08-12 bulk approval with no per-record review and are now `review_depth: bulk, confirmed: false`. **A blind annotation tool now exists (§4.81, `echotales annotate`)** — emits surface + a ±240-char window with no system field or pre-filled answer, refuses a leaking task, round-tripped against RI (3 tasks, 2 answered, 1 correctly skipped rather than defaulted) — but running it at scale is still the owner's call, not yet done | Missing — no confirmed gold exists at any scale | none directly | every downstream accuracy claim (resolver, Baseline A, recall@k gate) is unanchored until a person adjudicates records against source text, independent of pipeline output | run `echotales annotate` at scale against the two independent draft files first (they're not circular, just unconfirmed); public corpora (LitBank/PDNC) for standard metrics per EVOLUTION 4.74's stated route | — |
| Baselines | Baseline A (long-context LLM, `eval/baseline_a.py`) built and tested (2/2) — its module docstring previously claimed RI gold was "100% human-confirmed" and cited the now-retracted B³ numbers as a comparison point; both were false and have been corrected in the code. A baseline comparison is meaningless until both sides are scored against gold neither produced, which doesn't exist yet. Baseline B (LLMLink-style dual-LLM) **not started** | Partial | — | paper needs both to be defensible, and neither has a real number to be defensible with | build Baseline B; build actual gold before either baseline's number means anything | gold datasets |
| Ablations | **Built §4.78 (2026-09-23)**, superseding the "None found" verdict this row carried before — `eval/evidence_cache.py` (opt-in `resolve --capture-evidence`, a `scoring_evidence` table) + `eval/ablate.py`/`echotales ablate`, nine conditions re-scoring cached real evidence with no re-inference. Real result on RI's 10,058-pair cache: `no-gazetteer-compounding` drops force-links from 9.2% to 1.2%; `no-temporal-scoping` changes nothing (temporal blocking is inert on this corpus); the scorer's own maximum output across every condition is 0.527 vs. the 0.80 link threshold. Three of the plan's named conditions (no alias typing, no Self/Persona split, no truth status) are not answerable by re-scoring this cache and are printed as such (`REQUIRES_RERESOLVE`) rather than silently omitted. The central `state_of`-vs-flat downstream visual ablation (Part M) still does not exist | Verified as infrastructure and measured on real data; the visual/render ablation is still Missing | — | this is the sharpest resolver finding in the project's life — the scorer cannot link *anything*, not merely under-tuned | build the visual ablation next — it's the paper's likely central figure | resolver, render pipeline |
| Paper artifacts | **None found** — no figure/diagram/table generation scripts exist | Missing | — | — | build once ablations/baselines exist; premature before that | ablations, baselines |
| IP/patent documentation | No invention-disclosure draft exists. `docs/VISUAL_RENDERING.md`'s Phase 5c section is a **planned** flag-list (state-triggered cache invalidation, canonical-state-to-render-plan compilation), not yet written as an actual disclosure | Missing (as a real document); a candidate-mechanism list exists in planning form only | — | — | write the internal disclosure draft (never committed publicly) once the flagged mechanisms are actually built, not before | Visual Rendering Track Phase 1+ |

---

## Verified-vs-claimed quick reference

Use this when a doc or an earlier session's summary claims something is
"done" — check here before trusting it at face value:

- **Genuinely solid, don't relitigate:** `state_of()`/temporal model, truth
  status, Self/Persona schema (multi-body support), delivery-marker→
  synthesis-parameter wiring, EPUB-only decision, lexicon induction,
  hand-curated aliases never as pipeline input.
- **Real but narrower than the name suggests:** IP-Adapter "removal"
  (call-site only), "Recurring Unnamed Characters — done" (resolution only,
  not voice), the reels engine (planning logic only, not wired).
- **Confirmed structurally broken, not just untuned:** the resolver's
  learned scorer; the `TRANSFERABLE_TITLE` recall@k gate on RI.
- **Confirmed absent, not merely undocumented:** paper-artifact generation,
  temporal voice/persona state, spatial audio effects. (Job/queue system,
  file upload, and output library existed as of 2026-09-22's Product
  Orchestration track — backend only, no frontend wiring yet; the
  resolution-scoring ablation harness existed as of 2026-09-23's
  `EVOLUTION.md` 4.78 — the *render/visual* ablation Part M is still
  absent; see the component matrix above, not this bullet, for the
  current state of either.)
- **New this pass (2026-09-23/24), measured on real data, not merely
  unit-tested:** resolution-method provenance (`by_method` no longer lies
  about 100% `SCORED`), the gazetteer compounding curve, the evidence-cache
  ablation harness, the escalation-rate summary, and the observer axis
  (`architecture.md`'s headline acceptance test now passes on real RI
  data). **Not measured, and must not be implied as measured:** any change
  in mention recall, CEAF-e, or speaker attribution from the NER-windowing
  fix (`EVOLUTION.md` 4.76) — the real ollama re-run that would show that
  has not been run.
- **Retracted, not merely stale — do not re-cite even as a lower bound:**
  the confirmed-tier B³ coreference result (precision=100.0%,
  recall=94.6%, f1=97.2%, RI ch1-60) and the draft-tier B³ figure
  (98.1% F1) that sat one line above it in every `eval` printout. Both
  were the system scored against gold drafted from its own output
  (`EVOLUTION.md` 4.74). There is currently no gold set and no measured
  coreference accuracy claim anywhere in this codebase — say so plainly
  rather than substituting either number.

---

## Next reconciliation

Re-run this audit (or at least spot-check the "Partial"/"Experimental"/
"Missing" rows above) after any of: a new full render, a new gold-
confirmation pass, or before writing anything for external/paper use from
a status claimed here.
