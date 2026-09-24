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

**Update, 2026-09-25:** the "Scorer", "Identity resolution / resolver",
"Audio/TTS", "Mention detection" and "Image generation" rows below were
re-reconciled against `EVOLUTION.md` 4.85 (scorer diagnosis, the EARS voice
bank, observer-conditioned generation on a real image engine, and hard-case
detection loss) — two new rows ("Hard-case detection" and
"Observer-conditioned generation") were added rather than folded silently
into existing ones.

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
**Truth constraint — DISCHARGED 2026-09-24.** This file carried the
constraint that "the real ollama re-run that would show 4.76's effect on
recall/attribution has **not been run** — nothing below may say or imply
mention recall, CEAF-e, or speaker attribution improved." **That re-run has
now happened** (`docs/NER_WINDOWING_RESULT.md`, full volume, 47 min, 660
calls): CEAF-e recall 25.2% → 48.9%, entities 82 → 261, speaker
identifiability 48.8% → 63.0%, and the "mentions roughly double" half of
the recorded prediction is **refuted** (+14.6% — the fix finds *entities*,
not mentions, because `_locate` already searched the whole chapter). Those
are measured and may be cited. **The constraint's successor:** the B³/MUC
figures from that run are **tautological** on a surface-trivial gold set
(`docs/EVAL_RETRIEVER.md` Section 1) and must never be quoted as accuracy.
Everything attributed to 4.77-4.81 below **is** measured on real data, and
there is still zero confirmed gold.

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
2. **The `TRANSFERABLE_TITLE` recall@k gate.** **OVERTURNED 2026-09-24 --
   the gate was measured and it FAILS at recall@10 = 66.7% (n=9, threshold
   80%); see `docs/EVAL_RETRIEVER.md`.** What blocked it was mechanical, not
   structural: `eval` had no `--gold` flag, so the corpus's one
   alias-diverse file (`reverend-insanity-hardcases.jsonl`, hand-drafted, 17
   TRANSFERABLE_TITLE records) was unreachable from the CLI *and* gitignored.
   The reasoning below holds only for `generate_gold.py`-derived gold, not
   for hand-drafted gold, and the "no matter how much more gets annotated"
   conclusion does not follow. Original text: `generate_gold.py` only
   admits mentions with a resolved `target_id`, but every real
   `TRANSFERABLE_TITLE` mention on RI correctly resolves to `None` by
   design (non-negotiable #9). The gate cannot produce a number on this
   novel no matter how much more gets annotated.
3. **IP-Adapter "removal"** (EVOLUTION Section 4.47) is real but narrower than the
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

## New findings, 2026-09-24 (evidence pass)

Added by the validation/evidence pass. Each is measured, with a reproducible
command behind it; see `docs/VALIDATION_BASELINE.md` for the checkpoint.

1. **The ollama blocker was a misdiagnosis.** Every doc recorded the re-run as
   blocked because "ollama is unreachable from a sandboxed Claude Code shell".
   The daemon was simply not running; `ollama serve` brought it up in **one
   second**. The re-run that gated the most in this project was never
   environmentally blocked.
2. **Gold sets in this corpus are surface-trivial, and that independently
   re-condemns the retracted headline.** `reverend-insanity.jsonl`'s
   *non-circular* silver subset is 1,816 mentions over **23 distinct
   surfaces**, 100% recoverable by grouping on the surface string. Scoring
   against it returns B3 P=100.0% R=94.6% F1=97.2% -- byte-identical to the
   figure 4.74 retracted for circularity. Two independent reasons, same
   number. `eval/validate_gold.py::_surface_triviality` now fails any file at
   >=99%. **`reverend-insanity-hardcases.jsonl` (63.6%) is the only
   evaluation set in the corpus that measures anything.**
3. **The gold key was destroying records.** `GoldMention.key` was
   `(novel, chapter, offset)`, so a word-boundary prefix surface overwrote the
   longer surface it prefixes -- **55 of c1-c5's 343 annotations (16%) died at
   load time**, silently, passing CI for six weeks. Fixed by carrying the
   normalised surface in the key.
4. **770 spans in the circular tier are shifted by exactly +1** (all
   `gold-auto-builder`, all ch61-199). The silver tier is clean: 3,457/3,457
   spans verified against chapter text.
5. **The retraction writer has zero callers.** `retract_alias_bindings` is
   never invoked; `retracted_chapter IS NOT NULL` is **0 rows across all 27
   databases**. The query semantics are implemented and tested; nothing ever
   retracts on real data. The invention disclosure calls this "Verified
   today. Implemented" and needs downgrading.
6. **"Concurrent" Self/Persona bindings are unit-tests-only.** Real data has
   one self with >1 persona (sequential reincarnation). **0** personas bound
   to >1 self, **0** non-MAIN-timeline bindings, **0** `FABRICATED` aliases in
   any database.
7. **No fact is ever attached to a non-MAIN timeline.** Dream and flashback
   segments are detected, but every `alias_binding` / `attribute` /
   `self_persona_binding` row is `MAIN_TIMELINE`. The story-time axis is
   defined and unused at fact level.
8. **`GenerationState` does not exist** (zero hits repo-wide). The visual half
   exists (`plan_builder.py::build_render_plan`); the **voice path never calls
   `state_of`, never touches `Persona`, and has no observer parameter**.
   `state.py:6`'s claim that voice selection consumes the query is false.
9. **Baseline B now exists** (`eval/baseline_b.py`), dual-LLM memorisation
   targeting LLMLINK. Neither baseline has been executed yet.

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
| Block/span classification | `ingest/classify.py`; ORV bracketed `SYSTEM_WINDOW` fixed (Section 4.64); 188 stray `HEADING` blocks/novel remain (open defect #9) | Partial | minor: a few blocks misclassified per novel | small noise in span-type-conditioned metrics | root-cause the residual HEADING blocks (bounded, not urgent) | — |
| Mention detection | Qwen2.5 NER + gazetteer; `TRANSFERABLE_TITLE` fixed end-to-end (Section 4.62). Root cause of the recall ceiling found and fixed in code (EVOLUTION 4.76, 2026-09-23; **measured 2026-09-24, see `docs/NER_WINDOWING_RESULT.md`**): `ner.py` was sending only `text[:6000]` per chapter and stopping, invisible to roughly half of every novel (RI median chapter 11,667 chars, 199/199 chapters over 6,000, only 51.9% of text ever reaching the model; `item` also missing from the label set). Now windows the full chapter (~3 calls/chapter) and offers `item`. **Landed and unit-tested, not yet run against real ollama output — effect on real recall is unmeasured**, see HANDOFF's "Pick up here" | Partial | some dialogue still goes unattributed as of the last real run; whether the fix changes that is unknown | recall ceiling mechanism identified and patched, real-data effect unadjudicated | run the real re-resolve (`docs/COMPLETION_PLAN.md` Track 1 item 3) and report the delta, favourable or not | — |
| Hard-case detection (relational/deictic, title transfer) | mention layer never emits a mention for most of the SILVER hard-case set in the first place | **Measured Section 4.85 (2026-09-25):** 59 of 89 hard cases are never detected as mentions at all — relational/deictic 25/29, title transfer 16/17. The retriever's title recall@10 (77.8%, 88.9% with production-exact context) (Candidate retrieval row below) was measured with the gold span handed to it directly; on real text, detection is the actual bottleneck, not retrieval or scoring | most relational/deictic and title-transfer characters never enter the graph | resolver/scorer work downstream of this is moot for these alias types until detection improves | improve mention detection for relational/deictic and title spans before any further retrieval or scorer work | mention detection |
| Speaker attribution | 45.5% identifiable (Section 4.60), honestly measured after removing a turn-taking tier proven wrong 82.9% of the time — **this number predates the NER windowing fix above and has not been re-measured against it** | Partial | ~half of dialogue lines have no confident speaker | limits audiobook casting quality | re-run against the windowed NER path before doing any more attribution-layer tuning | mention detection |
| Identity resolution / resolver | Hand-tuned pre-filters carry every real link; the learned scorer is confirmed structurally too weak (defect #1, precision plateaus 0.66-0.77, six clan members merge under calibration). **Measured on real RI data (Section 4.77/4.78, 2026-09-23):** `by_method` no longer hardcodes `SCORED` — real breakdown of 880 links is `GAZETTEER_EXACT=870, DECLARATION=5, NAME_CONTAINMENT=2, RELATIONAL_COPRESENCE=3, SCORED=0` — i.e. **the scorer settles no link at all**. (`resolve`'s printout shows `SCORED=82`; that is exactly the count of *created* entities, not links, so the two agree.) Re-scoring a 10,058-pair evidence cache under every ablation condition shows the scorer's real maximum output is 0.527 against the 0.80 link threshold; `temporal_validity` blocks zero of 2,051 real pre-filter blocks (all from `co_presence_violation`). **Section 4.85 (2026-09-25) found the arithmetic reason**: see the Scorer row below — 0.550 is the hard ceiling three always-inert features impose, independent of the weights that produced the observed 0.527 | Partial | none directly (pre-filters cover the real cases) | scorer is not a defensible ML contribution as-is — now confirmed on real pairs, not only the theoretical 0.711 bound | new candidate-evidence feature family (Part K), not reweighting | — |
| Candidate retrieval | `resolve/retrieve.py::CandidateRetriever`; recall@10 real: `RIGID_NAME` ~100%, `RELATIONAL_DEICTIC` 0%→59% (Section 4.60 fix), `TRANSFERABLE_TITLE` structurally unmeasurable (Section 4.69, stale-claim #2 above) | Partial | none | 1/3 alias types has no defensible recall@k number, ever, on this novel, under the current eval design | redesign the eval question for `TRANSFERABLE_TITLE` (score correct-DEFER, or use a novel with an eventual reveal) | mention detection, gold set |
| Scorer | `resolve/score.py`, 5 dense features + 3 hard pre-filters | Experimental (confirmed unfixable by reweighting; Section 4.78 measured its real max at 0.527 vs. a 0.80 threshold over every one of 10,058 real pairs — arithmetically incapable of linking, not merely untuned. **Diagnosed to a specific arithmetic cause, Section 4.85 (2026-09-25):** `scripts/scorer_diagnosis.py` shows the scorer ranks the correct candidate first 97/103 times (94.2%) — it is not blind — but `speech_partner_compatibility` is 0, `temporal_validity` is 1, and `first_attested_soft_prior` is never positive on every one of 15,796 real pairs, so the best reachable probability is 0.550 against the 0.80 threshold, a hard ceiling from three inert features rather than mistuned weights. A chronologically-split refit (`scripts/scorer_fit_probe.py`) does not move this and links nothing. Worse: every one of the 103 labelled gold candidates is decided by a pre-filter before the scorer sees it, so the scorer's own operating region has zero labels — neither a fitted scorer nor a bounded investigator is evaluable there, so neither was built. `docs/SCORER_DIAGNOSIS.md`, `docs/STORYTRACE_TRANSFER.md`.) | none (pre-filters cover real traffic) | central open research problem; retire or activate the three inert features, or make the decision comparative (rank+margin) since ranking is already 94% correct | see Part K plan | candidate retrieval |
| Temporal state (`state_of`) | `core/state.py::StateResolver.state_of` — three-axis time, timeline/observer-aware, returns `persona_ids: list[str]` (plural, supports concurrent bodies). **The observer axis was schema+model+query with no writer until Section 4.80 (2026-09-23):** `Store.add_observation`, `resolve/detect_observations.py`, `render --observer` now exist, and `architecture.md`'s headline acceptance test passes on real data for the first time — RI's Bai Ning Bing at ch200 returns 2 aliases for `READER`, 1 (strict subset) for a witness, 0 for a non-witness | Verified | none | the real research contribution, working as designed, and now demonstrated on real data rather than only unit tests | — (do not touch without a measured defect) | — |
| Truth status (retract vs. close_interval) | `core/enums.py::EventType`, deliberately distinct members | Verified | none | non-negotiable #5, holding | — | — |
| Contradiction detection | `resolve/contradiction.py`, swept at window boundaries | Experimental (fires on constructed over-merges, zero hits on 60 real chapters — diagnostic of Phase 6 over-splitting, not proof the detector works) | none observed yet | can't yet claim it catches a real contradiction | needs validation against real data once resolution has anything to over-merge | resolver |
| Self/Persona split | `persona/split.py` — `BodyChange` detection, `BodyEpoch`, `write_epochs`; LOTM transmigration linking + split verified end-to-end | Verified for detected transmigration/reincarnation cases | none | supports the paper's central downstream-embodiment claim | audit disguise/possession/clone (concurrent, not sequential) cases separately — schema supports it, no dedicated test exists yet | resolver |
| Body-state appearance | `persona/build.py`, `attire.py`; extraction contamination fixed (Section 4.49, 16/16→0/16) | Partial | none observed | RI's real body2 (Fang Yuan) has zero appearance attributes — blocks a real img2img/appearance-transition test today | populate/extract body2 appearance for at least one real case | Self/Persona split |
| Reference-image generation | `persona/reference_gen.py` — one sheet per `persona_id` (body-qualified) | Verified for txt2img; img2img body-transition **experimental** (full pipeline built, GPU-completion unconfirmed, own code comments defer the verdict) | none for txt2img; img2img not in any product path | img2img A/B (independent-gen vs. transition) has never been run to completion | run img2img once on an idle machine, side-by-side vs. independent generation | body-state appearance |
| Reference-image search | `persona/refimg_search.py`, DuckDuckGo-backed, quality-filtered, deliberately not auto-wired into generation | Verified (as a manual review tool) | reviewer can browse candidates; nothing auto-selects | — | — | — |
| Panel direction | `render/direction.py` — LLM art director + 5 guardrails (hallucination stripping, cast validation, crowd/layout rewrite, invented-second-subject logging) | Partial | v54 (latest complete real render) is the best output that exists, still below product bar | prompt-wording changes alone repeatedly failed (Section 4.45/4.46) — architecture-level fixes are what moved real numbers | benchmark-first per Visual Rendering Track before more prompt changes | mention/resolution, SceneState |
| SceneState | `render/scene_state.py`; v54 fixed the byte-identical-crowd-panel bug | Verified post-v54, with a documented partial-backfill caveat for pre-existing databases (kind=NULL rows) | none on fresh databases | — | — | resolver |
| Beat segmentation | `render/scenes.py`/`beats.py`, `_MAX_BLOCKS_PER_PANEL=4` | Verified | none | — | — | — |
| Image generation | `render/panels.py` — GuoFeng3/Illustrious/NoobAI/Refined, all 8GB-VRAM CPU-offload | Partial (technically works, quality below product bar by the user's own standard even at v54) | visual output is the weakest part of the product | central open question: model/compute vs. architecture — untested until Visual Rendering Track Phase 3 | see Visual Rendering Track plan | panel direction |
| Observer-conditioned generation | `render --observer`, reference conditioning gated on the observer's own knowledge state rather than the reader's | **Verified on a real image engine, Section 4.85 (2026-09-25):** RI chapter 169, blocks 1-10, NoobAI XL on local hardware, everything held constant but `--observer`. Reader: 5/5 panels reference-conditioned, prompt names the character and depicts two people. Non-witness: 0/5 conditioned, prompt says "a figure," one person, solo. Cache keys and pixels differ on all 10/10 blocks. `docs/OBSERVER_CONTRAST_VALIDATION.md`. **Caveat pinned by `test_readset_invalidation.py` the same session:** the cache key (`plan_builder.state_digest`) hashes persona ids and attributes but not aliases, so a name-only reveal does not invalidate an already-rendered panel | this is the first end-to-end demonstration that the graph's observer axis actually changes rendered pixels, not just query results | needs a second corpus/scene with a sustained disguise for a harder contrast (blocked — see readiness doc) | Temporal state (`state_of`), image generation, cache/invalidation |
| Image conditioning | IP-Adapter code still present in SDXL engines; call-site conditioning removed (Section 4.47) for measured contamination; `RenderBackendCapabilities` typed model now exists (2026-09-21, unwired) | Verified-removed-at-callsite / capability model Experimental (just built, not yet used to reintroduce conditioning) | none currently (prompt-text-only identity) | any reconditioning approach must beat the documented contamination baseline with evidence | Visual Rendering Track Phase 4b (conditioning benchmark) | image generation |
| img2img (body transition) | `persona/reference_gen.py` + `_img2img_worker.py` + `panels.py::IllustriousEngine._ensure_img2img_pipe` — full subprocess-isolated pipeline | Experimental — own code comments defer the "does it complete on real hardware" verdict; no completed run exists | not in any product path | no side-by-side identity/contamination comparison exists yet | run once on idle hardware (Visual Rendering Track Phase 4c) | reference generation, body-state appearance |
| Multi-character composition | Capped at `max_references=2`; SD1.5 (GuoFeng3) cannot hold hero+crowd together (measured checkpoint ceiling, Section 4.45/4.46); role-based typed model (`CharacterRole`) built 2026-09-21, not wired to any generation-time behavior | Partial | crowd/3+-person panels are the weakest single case | ceiling confirmed to be checkpoint, not prompt — a real, citable finding | Visual Rendering Track Phase 4a, gated on Phase 3 evidence | image generation |
| Motion generation | `render/motion.py`, SVD, 8GB cpu_offload — real chapter video exists (Section 4.24) | Verified functional; shot-rule quality **never manually reviewed** (EVOLUTION's own follow-up item, "Watch the output") | motion may be technically present but visually wrong and nobody has looked | — | eyeball a real chapter's motion before trusting the heuristics | image generation |
| Video composition | `render/compose.py`, `FfmpegComposeEngine`, real `.mp4` output exists | Verified functional | — | — | — | motion generation |
| 9:16 reels engine | `render/reels.py` — pure dataclass/enum planning logic, **no ffmpeg call, not imported by any generation path** | Missing (as a working feature; present only as unwired planning logic) | reels don't exist as a deliverable today | — | wire into `compose.py`, or drop the claim that it's built | video composition |
| Audio/TTS | `voice/engine.py::ChatterboxEngine`, real (not stub) — two full-chapter real renders exist (RI ch1 545s, LOTM ch1); casting deterministic per-seed | Verified (core synthesis + real artifacts); `render_novel` orchestrator has **zero direct test coverage** | audio works when manually invoked; nobody has re-verified it in CI | confidence rests on 2 manual artifacts, not automated tests | add an integration test that actually calls `render_novel`, even gated | speaker attribution, casting |
| Voice bank / emotional delivery | `voice/bank.py` — VCTK (110 speakers, read speech, no emotion) and CREMA-D (6 emotions, 16 kHz, no whisper) existed already. **EARS added Section 4.85 (2026-09-25):** `load_ears`, `--bank-kind ears` — 107 studio speakers at 48 kHz, 22 emotions, 7 reading styles, CC BY-NC 4.0 (research only, not for a commercial release). `voice/delivery.py`'s HUSHED polarity now requests a real `"whisper"` clip instead of the `fear` stand-in every earlier bank was limited to; `BankVoice.clip_for`'s fallback chain (`whisper`→`fear`, `loud`→`angry`, `sad`→`neutral`) keeps VCTK/CREMA-D producing exactly what they did before whisper existed | Experimental — loader, routing and unit tests landed; a balanced 22-speaker subset downloaded; **full-bank Chatterbox render of RI ch1 completed (EVOLUTION 4.87)**: 97 lines, 892 s, 7 native-English voices, `data/audio-ears-native/` | audible cast with real actors; it also makes speaker-attribution errors audible (opening siege lines voiced as Fang Yuan / Bai Ning Bing) | no listening test or MOS exists; Chatterbox runs through the `uv run --with chatterbox-tts --with "setuptools<81"` overlay by design | fix attribution before judging voice quality | Audio/TTS, speaker attribution |
| Temporal voice/persona state | `persona/build.py::load_trait_profiles` is explicitly body-independent (`persona_at(store, entity.id)` picks one profile per Self, any epoch) | **Missing** entirely — confirmed by reading the code, not merely undocumented | a transmigrated character (LOTM's Zhou Mingrui→Klein Moretti) sounds identical in both bodies | this is the audio-side twin of the render track's central `state_of`-vs-flat ablation, and it doesn't exist yet | plans.md Phase 9 items 1/3/5, unbuilt | Self/Persona split, voice casting |
| Delivery markers / inner monologue / prosody | `voice/delivery.py::settings_for` — genuinely wired into `SynthesisRequest.exaggeration`/`cfg_weight`/reference-clip emotion selection (Section 4.39), not just detected upstream | Verified | audio delivery actually varies by narrative signal | a real, working, non-trivial mechanism worth keeping in the paper | — | — |
| Spatial reverb / audio effects | Only pitch-shift exists (`voice/pitch.py`, ffmpeg rubberband); no reverb/room effect anywhere | Missing | flat audio space | — | plans.md Phase 9 item 5, unbuilt | — |
| Chapter audio packaging | No per-chapter audio-only file from the voice stage itself; concatenation only happens as a side effect of video composition (`compose.py::concatenate_audio`) | Partial | no standalone "listen to chapter N" audio artifact exists | — | promote chapter audio to a first-class artifact if audiobook delivery matters as a demo surface | video composition |
| Frontend | (2026-09-22, editorial/archive product-polish pass) Full shell rebuild: `App.js` is now a rail(nav)+workspace+inspector layout, not header tabs — six screens (Script/Characters/State/Generation/Outputs/Project), all real or honestly marked unavailable, none fake. Dead blue-gradient CSS (`.btn-primary`/`.btn-gradient`/`.view-tabs`) deleted (zero `.js` references, confirmed by grep before deletion). New primitives: `DepthCard`/`ManuscriptSurface`/`TimelineRail`+`StateNode`/`ArchiveRow`/`DossierHeader`/`MediaArtifact`/`InspectorSection`/`JobStatusBadge`. `ScriptView` wrapped in `ManuscriptSurface` (all six existing interactions — mention/speaker click, flag, create-mention, merge, retype — reverified working post-restyle, manually, against a real live backend). `CharacterDashboard` gets a `DossierHeader`, a real "Search for more references" action, and an honest `TimelineRail` (no epoch data exists in the payload — confirmed by reading `build_character_dashboard`, so it never fabricates one). `NewProject`'s upload `<input>` is enabled and wired to the real `POST .../source` route; `ProjectHome` adds a real "Start ingestion" trigger. Theme toggle (`theme.js`, previously dead infrastructure — `initTheme()` was called at load but nothing exposed a switch) now has a real control. 18/18 tests pass (`Section7Smoke.test.js` + new `ProductScreens.test.js`); manually verified against the real `reverend-insanity` canonical DB via Playwright (Script/Characters/dossier/Project/Outputs/Generation screens, ink+paper themes, a real mention-click→EntityPicker round trip) — no console errors | Verified | the whole app has one coherent visual identity end to end; three previously-nonexistent screens (Generation/Outputs/Project) now show real backend data | — | wire remaining secondary screens (`EntitySidebar`/`ChapterNav`/`AnalysisPanel`/`EntityPicker` still plain-CSS, not yet migrated to the token system) if a future pass wants full consistency | backend routes (all now consumed) |
| Backend API | stdlib `http.server` (`webview_server.py`), review/correction routes plus (2026-09-22, Product Orchestration track) project lifecycle, job triggers/status, EPUB/reference upload, render preview/generate, output library — see `details.md`'s `webview_server.py` entry for the full route list | Verified — `test_jobs.py`/`test_webview_server_jobs.py` pass (11 tests), stub-mode dispatch only, no real GPU/network run performed | reviewer can correct data, upload an EPUB, trigger every stage, and browse output, all over HTTP; **now consumed by the frontend** (2026-09-22 product-polish pass) — `api.js` has a wrapper for every route | — | — | job system |
| Jobs/progress | `jobs.py::JobQueue`, one in-process daemon worker thread, strictly sequential process-wide (matches the existing ollama/diffusion GPU-sharing constraint); `job` table (`store.py`) + `Job` model (`models.py`); `GET /api/projects/<id>/jobs`(`/<job_id>`) exposes status including nested `StageRun` detail. Resumability (skip-on-matching-`SUCCEEDED`-digest via `pipeline_run.py::stage()`) is live end-to-end. **`ManuscriptProgress.js` is still fed a hardcoded placeholder in `NewProject.js`'s "preview" section** (deliberately — it illustrates what ingestion *will* look like before a file is even picked); real job polling is wired into `GenerationWorkspace` (render jobs) and `ProjectHome` (ingest jobs) instead | Verified for dispatch/sequencing/resumability via `test_jobs.py`; frontend polling verified via `ProductScreens.test.js` + manual check | real render-job status visible in the Generation screen; real ingest-job trigger visible in Project home | — | wire `ManuscriptProgress.js` itself to a live job once one is running, instead of only showing the pre-upload preview | backend API |
| File upload | `POST /api/projects/<id>/source` (EPUB, via stdlib-only `_multipart.py` parser, validated by actually opening the file with `Epub()` before accepting) and `POST /api/novels/<id>/characters/<self_id>/reference/upload` (reference image, same parser). **The upload `<input>` in `NewProject.js` is now enabled** and calls the real route (2026-09-22) | Verified for the backend route (integration test) and the frontend call (`ProductScreens.test.js`-adjacent `Section7Smoke.test.js` case, plus manual check) | a reviewer can create a project and attach its EPUB entirely from the browser | — | — | job system |
| Output library | `GET /api/novels/<id>/output` (pure filesystem walk of `data/<CODE>/{panels,video,audio,references}/` per `pipeline/paths.py`'s layout, no new metadata table) and `GET /api/novels/<id>/output/file` (serves one file, path-escape-checked against `paths.novel_root`). **`OutputLibrary.js` now consumes this** (2026-09-22) — verified manually against the real `reverend-insanity` output directory (a real 262.6 MB `ch1.mp4` rendered correctly; the Reels tab correctly always reads "not produced yet," since `render/reels.py` has no ffmpeg call and there is no reels kind in the listing at all) | Verified via integration test + manual browser check against real data | a reviewer can browse real rendered output from the browser | — | — | backend API |
| Evaluation harness | `echotales eval --report` — B³ scoring (draft + confirmed tiers), self-retrieval smoke test, gold recall@k gate. **Extended Section 4.79-4.81 (2026-09-23):** `Store.escalation_summary()` now prints escalation rate at the top of every run (RI: 370 calls, 0 escalations, 0.0%); `held_out_coverage` (chapter-range split, never random) validates conformal coverage on unseen data rather than the calibration set itself; `eval/stats.py` bootstrap CIs on every reported number (caught a real coordinate bug on first use — a linked-share CI computed 0.4% instead of the correct 98.6% because it keyed gold offsets against block-local `mention.offset`); `eval/persist.py` writes `data/eval/results/<run_id>/metrics.json` with commit/seed/platform, `-dirty` marker included honestly | Verified as infrastructure, and now measurably richer — the confirmed-tier and draft-tier numbers it has ever printed are both self-agreement (EVOLUTION 4.74) because the gold they scored against was drafted from the pipeline's own `mention` table; also **one alias type structurally unmeasurable** by current design (stale claim #2) | — | the reporting mechanism is real, enforces `CIRCULAR_DRAFTERS`/`ReviewDepth` (`eval/gold.py`), and now reports escalation/coverage/intervals, but has never yet had a non-circular gold set to score against | build gold that is independent of the system under test (see Gold datasets row), then redesign the `TRANSFERABLE_TITLE` eval question | gold datasets |
| Gold datasets | Draft coverage only, all drafted from pipeline output except two small independent files: RI 198/199 ch (7,879 records, 4,422 of them `mention`-table-derived), LOTM 213/213 ch (6,756, 100% derived), ORV 186/188 ch (4,836, 100% derived), plus `reverend-insanity-c1-c5.jsonl` (343 records, LLM read chapter text directly — independent) and `reverend-insanity-hardcases.jsonl` (89 records, independent). **Confirmed: 0 records across the entire corpus** as of 2026-09-23 (EVOLUTION 4.74) — the 6,952-record file that previously read `confirmed: true` was circular (scored against its own source) and is quarantined at `data/gold/_unusable/`; the 3,457 records elsewhere that read `confirmed: true` were a 2026-08-12 bulk approval with no per-record review and are now `review_depth: bulk, confirmed: false`. **A blind annotation tool now exists (Section 4.81, `echotales annotate`)** — emits surface + a ±240-char window with no system field or pre-filled answer, refuses a leaking task, round-tripped against RI (3 tasks, 2 answered, 1 correctly skipped rather than defaulted) — but running it at scale is still the owner's call, not yet done | Missing — no confirmed gold exists at any scale | none directly | every downstream accuracy claim (resolver, Baseline A, recall@k gate) is unanchored until a person adjudicates records against source text, independent of pipeline output | run `echotales annotate` at scale against the two independent draft files first (they're not circular, just unconfirmed); public corpora (LitBank/PDNC) for standard metrics per EVOLUTION 4.74's stated route | — |
| Baselines | Both built and run on RI ch1-10 against the same silver set, same model (`qwen2.5:7b`), same scorer (EVOLUTION 4.84, `docs/BASELINES.md`): Baseline A (`eval/baseline_a.py`, long-context) 1 call, 10 mentions, B³ recall 0.2%; Baseline B (`eval/baseline_b.py`, LLMLINK-style dual-LLM) 177 calls, 133 mentions, B³ recall 4.6%; EchoTales 0 resolution calls, 359 mentions, 96.3% | Verified (cost and extraction coverage); **not** a coreference-quality comparison | shows the cost shape of the graph approach | ch1-10 silver gold is surface-trivial, so B³ measures extraction coverage; neither baseline has run on the full volume | full-volume runs; non-trivial gold | gold datasets |
| Ablations | **Built Section 4.78 (2026-09-23)**, superseding the "None found" verdict this row carried before — `eval/evidence_cache.py` (opt-in `resolve --capture-evidence`, a `scoring_evidence` table) + `eval/ablate.py`/`echotales ablate`, nine conditions re-scoring cached real evidence with no re-inference. Real result on RI's cache (10,058 pairs pre-NER-fix, 15,796 post-fix as of EVOLUTION 4.84, both committed at `data/eval/ablation/reverend-insanity.json` via `ablate --out`): `no-gazetteer-compounding` drops force-links from 9.2% to 1.2%; `no-temporal-scoping` changes nothing (temporal blocking is inert on this corpus); the scorer's own maximum output across every condition is 0.527 vs. the 0.80 link threshold. Three of the plan's named conditions (no alias typing, no Self/Persona split, no truth status) are not answerable by re-scoring this cache and are printed as such (`REQUIRES_RERESOLVE`) rather than silently omitted. The central `state_of`-vs-flat downstream visual ablation (Part M) still does not exist | Verified as infrastructure and measured on real data; the visual/render ablation is still Missing | — | this is the sharpest resolver finding in the project's life — the scorer cannot link *anything*, not merely under-tuned | build the visual ablation next — it's the paper's likely central figure | resolver, render pipeline |
| Paper artifacts | **Built** (EVOLUTION 4.84, extended 2026-09-25) — `scripts/make_paper_artifacts.py` generates `docs/paper/TABLES.md`/`FIGURES.md` and the CSVs under `docs/paper/tables/` from real run artifacts: Table 4 (coreference) and Table 5 (recall@K) are now pinned to their specific gold files (the full silver file and the hardcases file respectively) rather than "newest run with silver metrics," after that ambiguity briefly swapped Table 4 for the 45-case hardcases run; Table 6 (ablations) is built from `data/eval/ablation/reverend-insanity.json`, written by `echotales ablate --out <path>` (new flag — `ablate` used to print to stdout only) | Verified — tables/figures regenerate from `scripts/reproduce_results.sh` against committed artifacts | — | reviewers can regenerate every table from source rather than trusting hand-typed numbers | keep pinning new tables to specific gold/DB paths as more are added | ablations, baselines |
| IP/patent documentation | `docs/IP/invention_disclosure.md` exists (written 2026-09-24, EVOLUTION 4.82, gitignored -- the repo is public and publishing a disclosure is itself a disclosure). Its self-declared blocking item (Section 3.1, the four unverified LINK-KG claims) is **closed**: `docs/PRIOR_ART_LINKKG.md` verifies all four TRUE against the full paper, and corrects two framing errors -- LINK-KG is SOTA for *legal-document* KG construction scored on node-duplication rates, not narrative coreference, and **LLMLINK is the real positioning target**. Three claims inside the disclosure still need downgrading against this pass's findings: the retraction writer has zero callers (0 retracted rows in all 27 DBs), concurrent Self/Persona bindings are unit-tests-only, and `GenerationState` does not exist | Partial -- the document is real and current; three of its own claims are stronger than the code | — | positioning is now evidence-backed rather than asserted | apply the three downgrades; verify LLMLINK itself before it goes to VIT | prior-art verification |

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
- **New this pass (2026-09-25), measured on real data:** observer-conditioned
  image generation on a real engine (NoobAI XL, ch169 — see the Observer-
  conditioned generation row above); the scorer's ceiling is arithmetic, not
  a tuning problem (three always-inert features cap probability at 0.550
  against the 0.80 threshold, over 15,796 real pairs — Scorer row above);
  hard-case mention detection, not retrieval or scoring, is the real
  bottleneck (59/89 hard cases never become mentions); the EARS voice bank
  (whisper/loud styles) lands but its full-bank render is queued, not run.
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
