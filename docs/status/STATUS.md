# EchoTales — status

**Merged 2026-09-29** from three overlapping documents (`STATUS.md`,
`REMAINING_WORK.md`, `FINAL_ECHOTALES_READINESS.md`) that had converged on
saying the same things three ways. This file is what remains after removing
that duplication — nothing measured was dropped, only the repeated framing.
The originals are preserved in git history if the exact prior wording is
ever needed.

**Purpose:** the single place that answers "is X actually working, and how
do we know?", "what is explicitly missing?", and "is v1 ready?" — reconciled
against code, tests, and real artifacts. **Per-claim evidence with citations
lives in `docs/results/FINAL_EVIDENCE_TABLE.md`; that file wins over
anything below that disagrees with it.** `docs/EVOLUTION.md` stays the
historical, append-only reasoning log — never edited to "fix" a stale claim,
a new dated section is added instead. `docs/HANDOFF.md` stays "what to pick
up next." `docs/design/VISUAL_RENDERING.md` is the deeper status doc for the
render subsystem specifically.

**Last reconciled:** 2026-09-27 (Minimal Disclosure Compiler, EVOLUTION
4.99). Re-run this audit (or at least spot-check the Partial/Experimental/
Missing rows in the component matrix) after any of: a new full render, a new
gold-confirmation pass, or before writing anything for external/paper use
from a status claimed here.

**Branch:** `validation/evidence-pass-2026-09-24` — local, not pushed, not
merged to `master`. **Canonical database:** `data/db/reverend-insanity.db`
(`docs/results/CANONICAL_RUN.md`).

---

## Phase A in progress (2026-10-22)

See `docs/HANDOFF.md` "Pick up here" and EVOLUTION 4.123. **A1** version
stamp, **A2** silver reference set (14 chapters, `eval/reader_gold.py`),
**A3** reader stage (`echotales reader`, run stage 6b, job kind `reader`),
**A4** validators, **A6** role slots (unproven), **A8** empty canon tables are
built. A5 (identity merges), A7 (`look_at`), A9 (rebuild) are not done.
**Gate A not met:** speakers 84.6 / 64.3 / 58.3 % and appearance
71.4 / 45.5 / 66.7 % (LotM / RI / ORV) on silver references the prompts were
tuned on, so optimistic. Databases in `data/db/` are unrebuilt and unstamped
(real renders 409). Any "Working" row below that depends on appearance,
speaker accuracy or persona links should be read against this until Gate A
passes.

## Test status (2026-10-22 for backend; other rows as dated 2026-10-02)

| Suite | Result |
|---|---|
| Backend (`packages/core` + `packages/pipeline`) | 1,533 passed (2026-10-22; was 1,206 on 2026-10-02) |
| `packages/research` (research arena) | 16 passed |
| `packages/ecrdt` (standalone research package) | 55 passed |
| Webview (Jest) | 82 passed |
| Webview accessibility (axe-core) | 0 violations across 16 routes × 4 widths × 2 themes (128 runs) |
| Webview production build from a clean `npm ci` | compiles; no source maps; no offline novel exports shipped |

## Readiness by area

| # | Area | Status | Basis |
|---|---|---|---|
| 1 | Engineering | **DONE for v1 scope** | Pipeline runs end to end on a 199-chapter volume; webview redesigned and QA'd; audio orchestrator has an end-to-end test. |
| 2 | Reproducibility | **DONE** | `scripts/reproduce_results.sh`; canonical database hash pinned. Cannot rebuild the database from a clean checkout — source EPUBs are copyrighted and not committed. |
| 3 | Core resolution | **PARTIAL** | Silver CEAF-e F1 67.4; 58 of 88 hard cases never detected; the LOTM transmigration comes out as two characters. |
| 4 | Observer state | **PARTIAL** | Mechanism demonstrated and ablated (real image engine, EVOLUTION 4.85); witness-level rendering and mid-chapter reveals not supported. |
| 5 | Multimodal generation | **PARTIAL** | Images, audio, and vertical (1080×1920) video all render on real data. Panel quality is below the product bar by the owner's own standard. Audio does not consume narrative state. |
| 6 | Ablations | **DONE** | A1, A2, A7, and the resolution ablation, with negative results reported. |
| 7 | External validation | **DONE (one benchmark), weak result** | LitBank, 100 documents. Not comparable to supervised systems. |
| 8 | Human validation | **WAITING ON HUMAN** | Review sheets and protocol prepared; 0 labels; no kappa. |
| 9 | Patent / IP | **WAITING ON IPR CELL** | Packet prepared privately (`docs/private/IP/`, gitignored). |
| 10 | Publication | **PARTIAL** | Experiment table, claim boundaries, venue decision, and a draft skeleton exist. Gated on human labels and the IPR decision. Research-arena verdicts (2 killed, 1 weakly surviving, 2 open) are in `docs/research/DECISION_LOG.md`. |
| 11 | Security | **PARTIAL** | `.env` untracked, no keys in repo/history. Keys exposed in an earlier session transcript must be rotated by their owner (`docs/ops/SECURITY_KEY_ROTATION.md`). |
| 12 | Documentation | **DONE** | EVOLUTION/STATUS/HANDOFF and the webview docs are current. |

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
| Block/span classification | `ingest/classify.py`; ORV bracketed `SYSTEM_WINDOW` fixed; 188 stray `HEADING` blocks/novel remain (open defect) | Partial | minor: a few blocks misclassified per novel | small noise in span-type-conditioned metrics | root-cause the residual HEADING blocks (bounded, not urgent) | — |
| Mention detection | Qwen2.5 NER (full-chapter windowing) + gazetteer + corpus commonness filter. Measured: entities 82 → 261, CEAF-e recall 25.2 → 48.9%. Commonness-filter fix landed (multi-word names after "this/that" no longer dropped): canonical CEAF-e F1 67.4. Hard cases: 58/88 still undetected (address terms 16, relational 15, titles 11, pronouns 10 by design; `data/eval/hardcase_taxonomy.json`) | Partial | detection, not linking, is the bottleneck (24/24 detected hard cases linked correctly) | vocatives, relation graph, title-holder resolution are research | — | — |
| Hard-case detection (relational/deictic, title transfer) | mention layer never emits a mention for most of the SILVER hard-case set in the first place | **Measured:** 59 of 89 hard cases never detected as mentions at all — relational/deictic 25/29, title transfer 16/17. Retriever's title recall@10 (77.8%, 88.9% with production-exact context) was measured with the gold span handed to it directly; on real text, detection is the actual bottleneck, not retrieval or scoring | most relational/deictic and title-transfer characters never enter the graph | resolver/scorer work downstream of this is moot for these alias types until detection improves | improve mention detection for relational/deictic and title spans before any further retrieval or scorer work | mention detection |
| Speaker attribution | 46.1% attributed (2,392/5,192) on the post-NER-fix volume with pronoun recovery off, essentially flat against the pre-fix 45.5%. A previously-persisted 63.0% counted pronoun-recovery guesses mislabelled `CONTEXTUAL_LLM` that a spot check found right 2 times in 15; that pass is now opt-in (`run --recover-pronoun-speakers`). Real LLM tier (ch1-3, 32 lines) spot-checks 12 right / 16 wrong and is still on | Partial | ~half of dialogue lines have no confident speaker and get an anonymous voice | wrong speakers are audible in the audiobook (ch1 siege lines) | a labelled speaker set; decide tier 4; make voice casting respect span confidence | mention detection |
| Identity resolution / resolver | Hand-tuned pre-filters carry every real link; the learned scorer is confirmed structurally too weak (precision plateaus 0.66-0.77, six clan members merge under calibration). Real breakdown of 880 links on RI: `GAZETTEER_EXACT=870, DECLARATION=5, NAME_CONTAINMENT=2, RELATIONAL_COPRESENCE=3, SCORED=0` — the scorer settles no link at all. Re-scoring a 10,058-pair evidence cache under every ablation condition shows the scorer's real maximum output is 0.527 against the 0.80 link threshold. The arithmetic reason: 0.550 is the hard ceiling three always-inert features impose, independent of weights | Partial | none directly (pre-filters cover the real cases) | scorer is not a defensible ML contribution as-is | new candidate-evidence feature family, not reweighting | — |
| Candidate retrieval | `resolve/retrieve.py::CandidateRetriever`; recall@10 real: `RIGID_NAME` ~100%, `RELATIONAL_DEICTIC` 0%→59%, `TRANSFERABLE_TITLE` structurally unmeasurable on RI (every real mention correctly resolves to `None` by design, non-negotiable #9) | Partial | none | 1/3 alias types has no defensible recall@k number, ever, on this novel, under the current eval design | redesign the eval question for `TRANSFERABLE_TITLE` (score correct-DEFER, or use a novel with an eventual reveal) | mention detection, gold set |
| Scorer | `resolve/score.py`, 5 dense features + 3 hard pre-filters | **OPTIONAL / EXPERIMENTAL — contributes 0 links on the canonical run (16,538 pairs, max score 0.41); every link comes from the deterministic pre-filters. Do not claim it improves resolution.** Ranks the correct candidate first 97/103 times (94.2%) — it is not blind — but `speech_partner_compatibility` is 0, `temporal_validity` is 1, and `first_attested_soft_prior` is never positive on every one of 15,796 real pairs, so the best reachable probability is 0.550 against the 0.80 threshold. A chronologically-split refit does not move this. Every one of the 103 labelled gold candidates is decided by a pre-filter before the scorer sees it, so the scorer's own operating region has zero labels | none (pre-filters cover real traffic) | central open research problem; retire or activate the three inert features, or make the decision comparative (rank+margin) since ranking is already 94% correct | see `docs/paper/ABLATION_PLAN.md` | candidate retrieval |
| Temporal state (`state_of`) | `core/state.py::StateResolver.state_of` — three-axis time, timeline/observer-aware, returns `persona_ids: list[str]` (plural, supports concurrent bodies). Observer axis has schema+model+query+writer (`Store.add_observation`, `resolve/detect_observations.py`, `render --observer`); `docs/design/architecture.md`'s headline acceptance test passes on real data — RI's Bai Ning Bing at ch200 returns 2 aliases for `READER`, 1 (strict subset) for a witness, 0 for a non-witness | Verified | none | the real research contribution, working as designed, demonstrated on real data | — (do not touch without a measured defect) | — |
| Minimal Disclosure Compiler | `core/disclosure.py::compile_minimal_disclosure` — task-conditioned evidence minimization on top of `state_of()`. Opt-in render integration only (`use_mdc=False` default, unchanged behavior everywhere it isn't explicitly turned on). See `docs/results/ABLATIONS.md` | Experimental — measured, one leg (render) structurally hollow because the real DB has zero SELF attributes (open defect below); dialogue_brief synthetic leg demonstrates the mechanism | none in the default pipeline | priority 1 of 3 IPR-review candidates; not yet a patentability determination | populate SELF-kind attributes on the canonical DB to get a real render-leg number | Temporal state |
| Truth status (retract vs. close_interval) | `core/enums.py::EventType`, deliberately distinct members | Verified | none | non-negotiable #5, holding | — | — |
| Contradiction detection | `resolve/contradiction.py`, swept at window boundaries | Experimental (fires on constructed over-merges, zero hits on 60 real chapters) | none observed yet | can't yet claim it catches a real contradiction | needs validation against real data once resolution has anything to over-merge | resolver |
| Self/Persona split | `persona/split.py` — `BodyChange` detection, `BodyEpoch`, `write_epochs`; LOTM transmigration linking + split verified end-to-end | Verified for detected transmigration/reincarnation cases | none | supports the paper's central downstream-embodiment claim | audit disguise/possession/clone (concurrent, not sequential) cases separately — schema supports it, no dedicated test exists yet | resolver |
| Body-state appearance | `persona/build.py`, `attire.py`; extraction contamination fixed | Partial | none observed | RI's real body2 (Fang Yuan) has zero appearance attributes — blocks a real img2img/appearance-transition test today | populate/extract body2 appearance for at least one real case | Self/Persona split |
| Reference-image generation | `persona/reference_gen.py` — one sheet per `persona_id` (body-qualified) | Verified for txt2img; img2img body-transition experimental (full pipeline built, GPU-completion unconfirmed) | none for txt2img; img2img not in any product path | img2img A/B (independent-gen vs. transition) has never been run to completion | run img2img once on an idle machine, side-by-side vs. independent generation | body-state appearance |
| Reference-image search | `persona/refimg_search.py`, DuckDuckGo-backed, quality-filtered, deliberately not auto-wired into generation | Verified (as a manual review tool) | reviewer can browse candidates; nothing auto-selects | — | — | — |
| Panel direction | `render/direction.py` — LLM art director + 5 guardrails | Partial | latest complete real render is the best output that exists, still below product bar | prompt-wording changes alone repeatedly failed — architecture-level fixes are what moved real numbers | benchmark-first per Visual Rendering Track before more prompt changes | mention/resolution, SceneState |
| SceneState | `render/scene_state.py` | Verified, with a documented partial-backfill caveat for pre-existing databases (kind=NULL rows) | none on fresh databases | — | — | resolver |
| Beat segmentation | `render/scenes.py`/`beats.py`, `_MAX_BLOCKS_PER_PANEL=4` | Verified | none | — | — | — |
| Image generation | `render/panels.py` — GuoFeng3/Illustrious/NoobAI/Refined, all 8GB-VRAM CPU-offload | Partial (technically works, quality below product bar by the user's own standard) | visual output is the weakest part of the product | central open question: model/compute vs. architecture | see Visual Rendering Track plan | panel direction |
| Observer-conditioned generation | `render --observer`, reference conditioning gated on the observer's own knowledge state rather than the reader's | **Verified on a real image engine:** RI chapter 169, blocks 1-10, NoobAI XL on local hardware, everything held constant but `--observer`. Reader: 5/5 panels reference-conditioned, prompt names the character and depicts two people. Non-witness: 0/5 conditioned. Cache keys and pixels differ on all 10/10 blocks (`docs/results/ABLATIONS.md`). Caveat: the cache key hashes persona ids and attributes but not aliases, so a name-only reveal does not invalidate an already-rendered panel | first end-to-end demonstration that the graph's observer axis changes rendered pixels, not just query results | needs a second corpus/scene with a sustained disguise for a harder contrast | Temporal state, image generation, cache/invalidation |
| Image conditioning | IP-Adapter code still present in SDXL engines; call-site conditioning removed for measured contamination; `RenderBackendCapabilities` typed model exists, unwired | Verified-removed-at-callsite / capability model Experimental | none currently (prompt-text-only identity) | any reconditioning approach must beat the documented contamination baseline with evidence | Visual Rendering Track Phase 4b (conditioning benchmark) | image generation |
| img2img (body transition) | `persona/reference_gen.py` + `_img2img_worker.py` + `panels.py::IllustriousEngine._ensure_img2img_pipe` | Experimental — own code comments defer the "does it complete on real hardware" verdict; no completed run exists | not in any product path | no side-by-side identity/contamination comparison exists yet | run once on idle hardware | reference generation, body-state appearance |
| Multi-character composition | Capped at `max_references=2`; SD1.5 (GuoFeng3) cannot hold hero+crowd together (measured checkpoint ceiling); role-based typed model (`CharacterRole`) built, not wired to generation-time behavior | Partial | crowd/3+-person panels are the weakest single case | ceiling confirmed to be checkpoint, not prompt | Visual Rendering Track Phase 4a | image generation |
| Motion generation | `render/motion.py`, SVD, 8GB cpu_offload — real chapter video exists | Verified functional; shot-rule quality never manually reviewed | motion may be technically present but visually wrong and nobody has looked | — | eyeball a real chapter's motion before trusting the heuristics | image generation |
| Video composition | `render/compose.py`, `FfmpegComposeEngine`, real `.mp4` output exists | Verified functional | — | — | — | motion generation |
| 9:16 vertical video | `render/compose.py` composes chapter videos at 1080×1920, 30 fps with Ken Burns motion, burned captions, `--speed` control. `render/reels.py` is a separate unused pacing/style planner that duplicates `director.py`; no automatic short highlight cut exists | Verified for full-chapter vertical video; no short highlight-reel generator (nothing measured says one is needed) | vertical chapter videos play in the webview Output library | the planner in `reels.py` is dead code | delete it or wire it, if a short-cut format is ever wanted | panels, audio |
| Audio/TTS | `voice/engine.py::ChatterboxEngine`, real (not stub) — two full-chapter real renders exist; casting deterministic per-seed | Verified (core synthesis + real artifacts); `render_novel` covered end to end by `test_voice_render_novel.py` (stub engine, real WAV output) | orchestration exercised in CI against the stub engine | real-engine (Chatterbox) output still rests on manual artifacts; no listening test | a gated real-engine integration test, and a listening study | speaker attribution, casting |
| Voice bank / emotional delivery | `voice/bank.py` — VCTK (110 speakers), CREMA-D (6 emotions). EARS added: `load_ears`, `--bank-kind ears` — 107 studio speakers at 48 kHz, 22 emotions, 7 reading styles, CC BY-NC 4.0 (research only). `voice/delivery.py`'s HUSHED polarity requests a real "whisper" clip | Experimental — loader/routing/unit tests landed; full-bank Chatterbox render of RI ch1 completed (97 lines, 892s, `data/novels/RI/audio-runs/ears-native/`) | audible cast with real actors; also makes speaker-attribution errors audible | no listening test or MOS exists | fix attribution before judging voice quality | Audio/TTS, speaker attribution |
| Temporal voice/persona state | `persona/build.py::load_trait_profiles` is explicitly body-independent | **Missing** entirely — confirmed by reading the code | a transmigrated character (LOTM's Zhou Mingrui→Klein Moretti) sounds identical in both bodies | audio-side twin of the render track's central `state_of`-vs-flat ablation | unbuilt | Self/Persona split, voice casting |
| Delivery markers / inner monologue / prosody | `voice/delivery.py::settings_for` — wired into `SynthesisRequest.exaggeration`/`cfg_weight`/reference-clip emotion selection | Verified | audio delivery actually varies by narrative signal | a real, working, non-trivial mechanism worth keeping in the paper | — | — |
| Spatial reverb / audio effects | Only pitch-shift exists (`voice/pitch.py`, ffmpeg rubberband); no reverb/room effect anywhere | Missing | flat audio space | — | unbuilt | — |
| Chapter audio packaging | Voice stage writes `ch<N>/chapter.wav` (every line in order, 0.35s gaps) | Built | — | `test_voice_render_novel.py` | — | voice stage |
| Frontend | Full redesign: `react-router-dom` v7 routes in `webview/src/router.js`; dark, Inter Tight/Inter, violet-accent system; every page reads the live `webview-server` API via `ProjectContext`. 28/28 webview tests pass; production build rendered/verified via Playwright at 1440px and 390px | Verified | one coherent visual identity end to end; Generation/Outputs/Project screens now show real backend data | — | wire remaining secondary screens (`EntitySidebar`/`ChapterNav`/`AnalysisPanel`/`EntityPicker` still plain-CSS) if a future pass wants full consistency | backend routes (all now consumed) |
| Backend API | stdlib `http.server` (`webview_server.py`), review/correction routes plus project lifecycle, job triggers/status, EPUB/reference upload, render preview/generate, output library (see `docs/design/details.md`) | Verified — `test_jobs.py`/`test_webview_server_jobs.py` pass (11 tests), stub-mode dispatch only | reviewer can correct data, upload an EPUB, trigger every stage, browse output, all over HTTP; consumed by the frontend | — | — | job system |
| Jobs/progress | `jobs.py::JobQueue`, one in-process daemon worker thread, strictly sequential process-wide; `job` table + `Job` model; `GET /api/projects/<id>/jobs`(`/<job_id>`) exposes status including nested `StageRun` detail. Resumability live end-to-end | Verified for dispatch/sequencing/resumability; frontend polling verified | real render-job status visible in Generation screen; real ingest-job trigger visible in Project home | — | wire `ManuscriptProgress.js` to a live job once one is running | backend API |
| File upload | `POST /api/projects/<id>/source` (EPUB) and reference-image upload, both via stdlib-only multipart parser, validated before accepting | Verified | reviewer can create a project and attach its EPUB entirely from the browser | — | — | job system |
| Output library | `GET /api/novels/<id>/output` (filesystem walk of `paths.py`'s layout) and file-serving route, path-escape-checked | Verified via integration test + manual browser check against real data | reviewer can browse real rendered output from the browser | — | — | backend API |
| Evaluation harness | `echotales eval --report` — B³ scoring, self-retrieval smoke test, gold recall@k gate. `Store.escalation_summary()`, `held_out_coverage`, `eval/stats.py` bootstrap CIs, `eval/persist.py` writes `data/eval/results/<run_id>/metrics.json` | Verified as infrastructure; the confirmed-tier and draft-tier numbers it has ever printed are both self-agreement (gold drafted from the pipeline's own `mention` table); `TRANSFERABLE_TITLE` structurally unmeasurable | — | the reporting mechanism is real and enforces `CIRCULAR_DRAFTERS`/`ReviewDepth`, but has never yet had a non-circular gold set to score against | build gold that is independent of the system under test, then redesign the `TRANSFERABLE_TITLE` eval question | gold datasets |
| Gold datasets | Draft coverage only, mostly drafted from pipeline output. **Confirmed: 0 records across the entire corpus** — the file that previously read `confirmed: true` was circular (scored against its own source) and is quarantined at `data/gold/_unusable/`. A blind annotation tool exists (`echotales annotate`) — round-tripped against RI (3 tasks, 2 answered, 1 correctly skipped) — running it at scale is the owner's call | Missing — no confirmed gold exists at any scale | none directly | every downstream accuracy claim is unanchored until a person adjudicates records against source text | run `echotales annotate` at scale against the independent draft files first; public corpora (LitBank/PDNC) for standard metrics | — |
| Baselines | Both built and run on RI ch1-10 against the same silver set, same model, same scorer: Baseline A (long-context) 1 call, 10 mentions, B³ recall 0.2%; Baseline B (LLMLINK-style dual-LLM) 177 calls, 133 mentions, B³ recall 4.6%; EchoTales 0 resolution calls, 359 mentions, 79.1% | Verified (cost and extraction coverage); not a coreference-quality comparison | shows the cost shape of the graph approach | ch1-10 silver gold is surface-trivial, so B³ measures extraction coverage; neither baseline has run on the full volume | full-volume runs; non-trivial gold | gold datasets |
| Ablations | `eval/evidence_cache.py` (opt-in `resolve --capture-evidence`) + `eval/ablate.py`/`echotales ablate`, nine conditions re-scoring cached real evidence with no re-inference. Real result: `no-gazetteer-compounding` drops force-links from 9.2% to 1.2%; `no-temporal-scoping` changes nothing; scorer's own maximum output across every condition is 0.527 vs. 0.80 threshold. Three conditions (alias typing, Self/Persona split, truth status) are `REQUIRES_RERESOLVE`, printed as such rather than silently omitted | Verified as infrastructure and measured on real data; the visual/render ablation is still Missing | — | sharpest resolver finding in the project's life — the scorer cannot link *anything* | build the visual ablation next — it's the paper's likely central figure | resolver, render pipeline |
| Paper artifacts | `scripts/paper/make_paper_artifacts.py` generates `docs/paper/TABLES.md`/`FIGURES.md` and CSVs from real run artifacts, pinned to specific gold files/DB paths | Verified — tables/figures regenerate from `scripts/reproduce_results.sh` | — | reviewers can regenerate every table from source rather than trusting hand-typed numbers | keep pinning new tables to specific gold/DB paths as more are added | ablations, baselines |
| IP/patent documentation | `docs/private/IP/invention_disclosure.md` exists (gitignored — the repo is public and publishing a disclosure is itself a disclosure). Its self-declared blocking item (four unverified LINK-KG claims) is closed: `docs/paper/PRIOR_ART_LINKKG.md` verifies all four against the full paper | Partial — document is real and current; three of its own claims are stronger than the code (retraction writer zero callers, concurrent Self/Persona unit-tests-only, `GenerationState` scope) | — | positioning is now evidence-backed rather than asserted | apply the three downgrades; verify LLMLINK itself before it goes to VIT | prior-art verification |

---

## Stale or misleading claims found (still worth knowing)

1. **"Recurring Unnamed Characters — done"** (a past HANDOFF claim, citing
   `test_unnamed_recurring_character_persistence.py`). True, but answers a
   different question than it appears to: it verifies
   `resolve_anaphora_for_novel`/resolver assign the same `target_id` to a
   recurring epithet mention across chapters — it does not touch voice.
   `speakers/runner.py::_assign_anonymous_slots` mints ids chapter-scoped by
   construction, so a recurring unnamed character still gets a fresh
   anonymous **voice** every chapter. Open defect, unfixed in the audio path.
2. **The `TRANSFERABLE_TITLE` recall@k gate.** OVERTURNED — the gate was
   measured and it FAILS at recall@10 = 66.7% (n=9, threshold 80%); see
   `docs/results/EXPERIMENT_RESULTS.md`. What blocked it was mechanical, not
   structural: `eval` had no `--gold` flag, so the corpus's one
   alias-diverse hand-drafted file was unreachable from the CLI and
   gitignored. `generate_gold.py` only admits mentions with a resolved
   `target_id`, but every real `TRANSFERABLE_TITLE` mention on RI correctly
   resolves to `None` by design (non-negotiable #9) — the gate cannot
   produce a number on this novel no matter how much more gets annotated.
3. **IP-Adapter "removal"** is real but narrower than the phrase suggests:
   the SDXL engine classes still carry full working IP-Adapter code; only
   the `render_panels` call site was changed to pass empty references.
4. **The headline coreference result is retracted, not just superseded.**
   The confirmed-tier B³ figure this document previously reported
   (precision=100.0%, recall=94.6%, f1=97.2%, RI ch1-60) was scored against
   gold drafted by `SELECT`ing the pipeline's own `mention` table and marked
   `confirmed: true` without an independent human pass — it measured the
   system against itself. That file is now quarantined at
   `data/gold/_unusable/reverend-insanity-c1-c50.jsonl`; every other draft
   file in `data/gold/` is `confirmed: false` — zero gold records exist
   anywhere in the corpus. `eval/gold.py` now enforces this structurally
   (`CIRCULAR_DRAFTERS`, `GoldProvenanceError`, `ReviewDepth`).
5. **Gold sets in this corpus are surface-trivial**, and that independently
   re-condemns the retracted headline: `reverend-insanity.jsonl`'s
   non-circular silver subset is 1,816 mentions over 23 distinct surfaces,
   100% recoverable by grouping on the surface string. Scoring against it
   returns the same byte-identical B³ figure the retraction condemned, for a
   second, independent reason. `eval/validate_gold.py::_surface_triviality`
   now fails any file at ≥99%. `reverend-insanity-hardcases.jsonl` (63.6%)
   is the only evaluation set in the corpus that measures anything.

**Verified-vs-claimed quick reference:**
- **Genuinely solid, don't relitigate:** `state_of()`/temporal model, truth
  status, Self/Persona schema (multi-body support), delivery-marker→
  synthesis-parameter wiring, EPUB-only decision, lexicon induction,
  hand-curated aliases never as pipeline input.
- **Real but narrower than the name suggests:** IP-Adapter "removal"
  (call-site only), "Recurring Unnamed Characters — done" (resolution only,
  not voice), the reels engine (planning logic only, not wired).
- **Confirmed structurally broken, not just untuned:** the resolver's
  learned scorer; the `TRANSFERABLE_TITLE` recall@k gate on RI.
- **Retracted, not merely stale — do not re-cite even as a lower bound:**
  the confirmed-tier B³ coreference result and the draft-tier B³ figure
  that sat one line above it in every `eval` printout. Both were the system
  scored against gold drafted from its own output. There is currently no
  gold set and no measured coreference accuracy claim anywhere in this
  codebase — say so plainly rather than substituting either number.

---

## What is left (gaps, by audience)

### Metrics we will not have

**Entity resolution:**

| Metric | State | Why |
|---|---|---|
| Any human-anchored P/R/F1 | Blocked by decision | Every figure is scored against the SILVER set, which an LLM drafted. No human gold, no IAA. Two annotators on 3–5 chapters, then Cohen's κ (roughly 6–10 person-hours), would fix this. |
| Inter-annotator agreement | Blocked by decision | The two independent LLM drafts cover different chapters, so they can't even stand in for model–model agreement. |
| Coreference on non-trivial gold | Blocked by data | Two of three silver files are 100% surface-trivial. CEAF-e (63.1%) is the only discriminative number on it. Needs more hard-case annotation. |
| Hard-case accuracy by category, end to end | Measured, small n | 29 of 88 detected; of the decidable ones, 23/23 linked correctly, 0 wrong, 0 deferred; 6 undecidable. The resolver is precise on what it sees — the loss is at detection. n≈23 is too small for a per-category figure. |
| LINK/NEW/DEFER decision accuracy | Not measurable | No labelled decisions exist — all 103 labelled gold candidates are decided by pre-filters. Blind-annotate ~200 SCORE-verdict pairs (`eval/blind_review.py` exists) — about 3 hours of human work. |
| Review burden / escalation rate | Measured, degenerate | 0 of 703 LLM calls escalated. Bounded at zero — either excellent or a sign the ladder cannot fire; nothing distinguishes the two without a fault injection. |
| Held-out conformal coverage | Not evaluable | No held-out pairs — pre-filters decide every labelled pair. Same fix as LINK/NEW/DEFER. |
| Scorer contribution | Measured: zero | Under all 8 cache-answerable ablation conditions, "scorer would link" is 0. A design decision, not a measurement gap: retire the scorer, or make it comparative (rank+margin) since ranking is already 94.2% correct. |
| Speaker attribution accuracy | Coverage measured; precision spot-checked only | 46.1% attributed. Precision exists only as spot checks. A labelled speaker set is human-only. |

**Baselines/external:** Baselines only ran on ch1-10 (full volume: ~2.4h GPU
per volume for Baseline B). GraphRAG/CORE-KG baselines not built. BOOKCOREF/
LitBank numbers not run at scale. Generalisation measured on LOTM ch1-3 only
(B³ recall 62.3%, CEAF-e F1 41.4, well below RI; transmigration split into
two Selves).

**Ablations needing a re-resolve:** `no-alias-typing`, `no-self-persona-split`,
`no-truth-status` are not answerable from the cache — each needs a full
199-chapter re-resolve (~47 min/condition) plus a code flag that doesn't
exist yet. There is also no visual ablation (render with a flat vs.
`state_of`-driven state) — the render-side twin of the resolver ablations,
treated as central by `docs/design/plans.md`.

**Visual generation:** CLIPScore measured (`docs/results/EXPERIMENT_RESULTS.md`: 77/87
panels align with own prompt over shuffled). Character identity consistency
across panels not built (judged by eye in `VERSIONS.md`). Human preference
rating: none. Observer contrast only at 5 panels/1 chapter, not a benchmark
— a sustained-disguise novel is needed for "two depictions of one character
by observer," blocked by data (RI has none). Per-panel wall time on a
larger GPU not run.

**Audio:** MOS/listening test human-only, none taken. Speaker similarity
(embedding cosine) not built. One observed voice–character gender/age
mismatch, caused by attribution not casting. Temporal voice state not
built (see component matrix).

### Architecture: designed or partial, not delivered

| Mechanism | State | Evidence |
|---|---|---|
| Retraction as distinct from interval end | Query semantics implemented and tested; writer has no caller | `retract_alias_bindings` has zero callers; `retracted_chapter IS NOT NULL` returns 0 rows in every database |
| Story-time axis (dream, flashback) | Defined; no fact ever written off `MAIN_TIMELINE` | Segments detected, facts never attached to them |
| Concurrent Self/Persona (disguise, possession, body-swap, clone, dream persona) | Unit tests only | Real corpus contains only sequential reincarnation |
| Observer-scoped persona bindings | Column exists; no writer | A witness learns the alias but not the persona; witness-conditioned render drops the character (`docs/results/EXPERIMENT_RESULTS.md`, Self/Persona validation section, §3) |
| Shared multimodal `GenerationState` | Built for the image path only | Panel prompt and render cache key read one compiled state per beat; audio has no state-dependent input |
| Aliases in the render read set | Missing | Render digest hashes persona ids and attributes, not aliases — a name-only reveal doesn't invalidate a panel |
| Transmigration merge (one Self, new Persona) | Not built | LOTM ch1–3: Zhou Mingrui and Klein resolved as two Selves |
| Detection of relational/deictic and title spans | Weak | 25/29 relational and 16/17 title mentions never detected |
| Bounded LLM investigator for uncertain pairs | Not built, deliberately | No labelled SCORE-region pairs to show it would help |

### Open defects

1. **`data/db/reverend-insanity.db` has zero SELF-kind attribute rows and
   zero relation rows** (found 2026-09-27 building the MDC ablation
   harness). PERSONA-kind attributes are fine (617 rows/98 personas).
   SELF-kind extraction against `PERSON_KEYS` was apparently never run
   against this database. Blocks meaningful real-data evaluation of
   anything reading SELF attributes/relationships, including the MDC render
   experiment and presumably `world/context.py::story_context`'s brief.
2. **Speaker attribution**: the real LLM tier (ch1-3) credits lines to
   vocative addressees and absent characters. The worse, pronoun-based pass
   is opt-in. Voice casting now voices attributions below confidence 0.7 as
   distinct "unconfirmed" speakers instead of as the named character.
3. **Silver span drift**: 7 records past the end of ch1 on the rerun
   database — the new ingest correctly drops the author's note.
4. **Two hardcases records need adjudication** — human-only.
5. Render pipeline items from EVOLUTION 4.51/4.52 are still open — see
   `docs/HANDOFF.md`.
6. `render/reels.py` is an unused planner (no ffmpeg call). Chapter videos
   are already vertical 1080×1920; only an automatic short highlight cut
   does not exist.
7. Block/span classification: 188 stray `HEADING` blocks/novel remain
   (bounded, not urgent).

### Patent disclosure (VIT filing)

| Gap | Why it matters |
|---|---|
| The repo has been public since 2026-08-07 | Prior public disclosure is counsel's first question; grace-period rules are jurisdiction-specific |
| Temporal KG literature not searched | Bitemporal/knowledge-time modelling has a database/TKG literature not yet surveyed |
| Mechanisms M2–M4 (retraction, concurrency, observer-scoped bindings) are EXPERIMENTAL or DESIGNED | Not demonstrated on real data — a claim resting on them rests on tests, not measurements |
| Every "potentially differentiating" line says ASSERT — VERIFY WITH COUNSEL | Nothing in the disclosure is a legal opinion |

The disclosure itself lives in `docs/private/IP/` (gitignored, never
committed). Do not reference its contents from any public doc.

### University report

- Complete author lists for references 3–12 — only LLMLINK and LINK-KG read
  in full, others cited from abstracts.
- The ≥5-papers-per-member related-work requirement needs each member to
  confirm their papers and write their own limitations paragraph (human-only).
- Team confirmation of the work split.
- Figures 6a, 8, 9, 10 rendered as SVG from generated CSVs
  (`scripts/paper/plot_paper_figures.py`, `docs/paper/figures/`). Figure 11
  (escalation, all zeros) stays a sentence rather than a chart.

### Reproducibility and hygiene

| Item | State |
|---|---|
| Branch `validation/evidence-pass-2026-09-24` | 50+ commits, not pushed, not merged to `master`. A disk failure loses the whole pass. Pushing is the owner's call — the repo is public. |
| `.env` API keys | Never committed, but printed into an earlier session transcript. **Rotate them.** |
| Lint / types | Clean on touched files. Repo-wide, `mypy` reports `import-untyped` noise. |
| Venv drift | `chatterbox-tts` and `setuptools<81` installed directly in `.venv`; documented route is the `uv run --with` overlay. |
| `reproduce_results.sh` | Runs end to end against an existing database. Cannot regenerate one from a clean checkout — source EPUBs are copyrighted and never committed. |
| Eval outputs | Every table in `docs/paper/TABLES.md` names its source file, gold file, and database. |

### What only a person can do

1. Annotate 3–5 chapters as human gold, two annotators for IAA.
2. Blind-label ~200 SCORE-region pairs — unblocks the scorer, calibration,
   and the investigator question.
3. Adjudicate the two flagged hardcases records.
4. Listen to the EARS render and rate it; rate a sample of panels.
5. Read Narrative Graph Prompting, StoryWeaver, and CORE-KG before filing.
6. Decide on pushing the branch, promoting the database, and rotating keys.
7. Give the team's confirmations for the report.

### What does *not* need doing

- More resolver tuning on silver data. A negative result (scorer contributes
  0) is already established and documented.
- A rented GPU for anything except the items in `docs/ops/RUNPOD_MIGRATION.md`
  Section 5.
- Building `GenerationState`, the investigator, or concurrent-persona
  writers *to make a document true*. Each should wait for a measurement
  that justifies it.
