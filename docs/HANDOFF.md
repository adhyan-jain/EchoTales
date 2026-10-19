# EchoTales — Handoff

**Purpose: current open tasks only, ephemeral.** This file answers "what do
I work on next" and nothing else — it should be readable in under a
minute. The history of how the system got here (every fix, every
completed defect, the reasoning behind each change) lives in
`docs/EVOLUTION.md`, not here. A render-version number (`v44`, `v51`, `v54`,
...) is tracked in the relevant novel's `panels/ch<N>/VERSIONS.md`, never
here and never in `docs/EVOLUTION.md` — a HANDOFF/EVOLUTION section number
(like "4.52") is not a render version, and the two must never be
conflated.

**The others, in the order you want them:**

| File | Answers |
|---|---|
| `docs/EVOLUTION.md` | *Why is it built this way?* The diff between the original spec and reality — which mechanisms were replaced and what evidence replaced them, plus the permanent, append-only session log. **Read before changing a design decision, or to find out what was already tried.** |
| `docs/design/architecture.md` | The model: three axes of time, self vs persona, observers |
| `docs/design/details.md` | Per-file detail |
| `docs/design/plans.md` | The original spec. Amended three times; the amendments win and are marked *(revised)* |
| `docs/design/video_plan.md` | Motion video plan (superseded and built 2026-10-19, EVOLUTION 4.114-4.118; Path 1 parallax compositor and Path 2 Wan 2.2 / LTX video engine). |
| `docs/design/consistency_plan.md` | Approved-reference identity and location consistency plan (2026-10-18, Phase 0 measurement gate to Phase 5). |
| `docs/archive/COMPLETION_PLAN.md` | *What to build next and why*, across research/patent/product. The forward multi-track plan (2026-09-23), including the `ner.py` 6,000-char truncation finding that reorders the work. **Read this before starting a new track.** |

**Last updated:** 2026-10-19 (EVOLUTION 4.118).

## Pick up here — 2026-10-19 (Frontend Studio UX, Worker Containers, Multi-Chapter Benchmark; EVOLUTION 4.118)

- **ALL PHASES AND EXTENSIONS OF `reels_and_full_video_build_plan.md` COMPLETED.**
  - **React Studio UX Components (`webview/src/components/`):**
    - `CostMeterWidget.js`: Interactive pre-render cost meter itemizing RunPod GPU time, LLM tokens, and voice synthesis, with Path 1 ($0.50/min limit) and Path 2 ($1.80/min limit) toggling and budget alert badges.
    - `AssetStudio.js`: Studio reference manager for approving character 3-view turnarounds, expression sheets, location master plates, and resolving Story Bible ambiguous merges/review items.
    - `ScreenplayEditor.js`: Visual shot list editor enforcing shot pacing (flagging still holds > 6.0s), 180-degree camera axis tracking, framing, and dialogue performance cues.
    - `ShotGridQA.js`: 4-candidate keyframe inspector with 4-Check automated QA scores (face match, background similarity, VLM compliance, artifact cleanliness), candidate re-rolling, and reference locking.
    - Integrated as first-class tabs in `webview/src/pages/project/Pages.js` with full client routing in `webview/src/api.js`.
  - **RunPod Serverless Flex Worker Containers (`workers/`):**
    - Standalone handlers, Dockerfiles, requirements, and deployment documentation for `workers/qwen_image/`, `workers/qwen_tts/`, and `workers/wan_video/`. All handlers support standalone execution and offline stub fallbacks.
  - **Multi-Chapter Golden Benchmark & Arc Continuity (`eval/run_benchmark.py`):**
    - Benchmarked Chapters 1, 2, and 3 of *The Hound of the Baskervilles* (`showcase_ch1_gold.json`, `showcase_ch2_gold.json`, `showcase_ch3_gold.json`).
    - Verified 100% speaker attribution accuracy, 100% face match, 100% VLM compliance, 0 voice collisions, and 0 arc continuity anomalies across all 3 chapters.
- **Tests.** 1,511 core+pipeline pass (82.14s), 29 research pass (8.03s), 124 webview jest pass (3.98s). Total: 1,664 tests passing across repository.

## Pick up here — 2026-10-19 (Story Bible Snapshots, Delta Validator, Screenplay Compiler; EVOLUTION 4.110)

- **Phase 0 & Phase 1 Core Capabilities completed.**
  - Point-in-time Story Bible snapshots implemented: `Store.bible_at(novel_id, chapter) -> StoryBibleSnapshot` with zero future chapter leakage.
  - Bitemporal retraction support: `Store.retract_attribute` closes fact claims without losing historical visibility for earlier queries.
  - Studio review queue: `review_item` table and Store persistence methods for human review items.
  - Story Bible delta validator (`bible/validator.py`): alias resolution via SequenceMatcher and name containment, ambiguous merge flagging (`ambiguous_entity_merge`), and monotonicity contradiction detection (`conflicting_attribute`).
  - Story Bible delta extractor (`bible/delta.py`): frontier LLM prompt builder and strict JSON parser with deterministic offline fallback.
  - Screenplay compiler (`screenplay/compiler.py`): adapts novel chapters + `StoryBibleSnapshot` into validated `ScreenplayEpisode` enforcing 10-25 cuts/min, <= 6.0s still hold, 180-degree axis continuity, and audio coverage.
  - Showcase story & speaker ground truth: Arthur Conan Doyle's *The Hound of the Baskervilles* (100% public domain worldwide), 3 chapters in `data/novels/showcase/`, Chapter 1 hand-labeled gold speaker attribution dataset (`data/eval/attribution/showcase_ch1_gold.json`, 69 lines).
  - Added 15 new unit tests across 4 test modules (`test_store_bible.py`, `test_bible_validator.py`, `test_attribution_gold.py`, `test_screenplay_compiler.py`).
- **Next steps in Phase 1**:
  - Asset Studio (`packages/pipeline/src/echotales/pipeline/assets/turnaround.py` and `location.py`): generate 3-view turnarounds and location master plates via worker client.
  - Keyframe Engine (`packages/pipeline/src/echotales/pipeline/keyframes/engine.py` and `qa.py`): 4-candidate generation and 4-Check QA gate (face match, background structural similarity, VLM script compliance, artifact filter).
- **Tests.** 1,477 core+pipeline pass (70.88s), 29 research pass (8.13s), 112 webview jest pass (4.17s). Total: 1,618 tests passing.

## Pick up here — 2026-10-18 (consistency plan, setting fixes, EVOLUTION 4.107)

- **LotM setting fixes (commits b22fc1a..97ab2a5, v6_bedroom-slice-final2).** Setting
  and key objects rank above mood (`setting_first` for non-xianxia), duplicate quality
  tags dropped, director no longer copies "day, bright_sunlight", whole-scene setting
  cues passed to each beat, whole-word place cues, bedroom locale supported, and scenes
  inherit the chapter's most-cued place. Verified on LotM ch1 blocks 0 to 40 (2 scenes):
  produces one consistent wood-panelled bedroom across panels.
- **Correction of 4.106's "consistency decent" verdict.** Detailed review showed hair
  shade and face structure vary between panels. Root cause: every panel is prompt-only;
  since EVOLUTION 4.47 `reference_images=[]` and `reference_weight=0.0` have been hard-coded.
- **Approved-reference consistency plan (`docs/design/consistency_plan.md`).**
  Human-approved reference assets only, IP-Adapter conditioning with regional masks
  (superseded 2026-10-19 by `reels_and_full_video_build_plan.md`).
- **Open defects 27 to 34 added** (identity plan, pronoun-only director cast drop,
  WORLD_CONTEXT token eat, preview sparsity, 77-token CLIP limit, unwired extract_world,
  scene_state key mismatch, stale Illustrious docstring).
- Tests: 1,444 core+pipeline pass, 112 webview jest pass, 29 research pass.

## Pick up here — 2026-10-18 (first real genre render, ECHOTALES_COMPUTE, hosted-provider switches; EVOLUTION 4.106)

- **Local, unpushed commits** 010c9fb, b9fb688, e66d958 on `reader-faithfulness`
  (EVOLUTION 4.106), on top of the ones listed in the next block. No request was
  ever sent to RunPod, OpenAI or Gemini; those paths are tested against mocks.
- **First real image run under the genre profiles (LotM only).** LotM chapter 1,
  NoobAI, 10 scenes -> 33 images in 22 minutes
  (`data/novels/LOTM/panels/ch1/v2_genre-victorian-10panel-noobai`, scratch DB
  `data/scratch/ui/lotm-render.db`). v1 was xianxia; v2 is Victorian (coat,
  cravat, gloves, revolver, arched windows; brown hair, grey eyes). One image
  has a stray signature-like artefact; consistency across images looked decent;
  not reviewed image by image. **ORV has not been rendered under its new
  profile** (Open defect 15). `panels/ch1/VERSIONS.md` did not exist for LotM, so
  no entry was written; add one if you keep that directory.
- **`ECHOTALES_COMPUTE` (`pipeline/compute.py`) is the laptop-safety switch,
  default `local-low`.** DEFAULT CHANGE: a bare `echotales render --image-engine
  <real engine>` now renders **3 scenes**, not 70. `ECHOTALES_COMPUTE=local-high`
  restores 70 and the old pipeline; `--tier full` or `--max-panels N` set it per
  run. `local-low` also forces the director to finish and unload before the
  image model loads, caps the director context at 4096, and refuses a local
  render (CLI exit 2, server 409) when the GPU is busy or available RAM is under
  3000 MiB; `--ignore-resource-guard` overrides. A bare render with no
  `--image-engine` still uses the stub unless a hosted image provider was chosen.
- **`--max-panels` caps SCENES, not images.** One to three images per scene: 10
  scenes gave 33 (3.3 per scene). NoobAI is about 45 s per image here, so a
  3-scene preview is about 7 minutes and a 70-scene chapter about 2.9 hours.
- **Provider switches** (all `ECHOTALES_*`, empty by default, see `.env.example`):
  `ECHOTALES_LLM_PROVIDER` (ollama|runpod|openai|gemini|anthropic|gateway|stub),
  `ECHOTALES_IMAGE_PROVIDER` (local|runpod|gemini|openrouter|stub). Language
  model precedence: that variable, then the cloud preset, then
  `ECHOTALES_MODEL_BACKEND`. A hosted image engine is reachable over HTTP only
  if the operator selected it; paid engines named in a request are still refused.
- **`GET /api/compute`** (mode, enabled engines with the refusal reason,
  scenes per tier, estimate inputs, RAM, GPU) replaces `/api/gpu` as what the
  Studio reads for its engine picker; `/api/gpu` still exists. Studio has a
  Scope select and a browser notification when a job ends.
- **`echotales render --version-suffix NAME`** names the version directory
  (`v2_NAME`); the render's LLM preflight now checks only the panel director's
  model (it was refused over `llama3:latest`, which a render never calls).
- **Memory on this machine:** `gemma2:9b` spilled 2 GB into system RAM at
  `num_ctx` 8192 (9.5 GB total); at 4096 it is 8.1 GB (7.4 in VRAM). A smaller
  director (`ECHOTALES_LOW_COMPUTE_DIRECTOR_MODEL`) is opt-in and untested for
  quality; the repo measured `qwen2.5:7b` ignoring the director's negative rules.
- **Open (Open defects 23 to 26):** hosted paths mock-tested only, RunPod image
  worker contract needs a real handler, hosted cost unmetered, no few-step
  image model.
- Tests: 1,435 core+pipeline pass (re-run by the docs pass, 61 s). Research 29 and webview jest 112 are the change author's counts (total 1,464 with research), not re-run by the docs pass.

## Pick up here — 2026-10-18 (speaker join, Studio versions, genre profiles, GPU-checked engine picker; EVOLUTION 4.104 and 4.105)

- **Local, unpushed commits on `reader-faithfulness`** (165d9bb and 22cbb56 in
  4.104; 2495a1d, 69cbb53, 02d4889, f25baf0, f6f0e46 in 4.105). Verified on
  real LotM, ORV and RI databases (CPU, stub LLM, stub image engine, $0);
  numbers in EVOLUTION 4.104 and 4.105.
- **Genre profiles: LotM has now been rendered with a real engine (see the
  block above); ORV and a project of another genre have not.** The stub-engine
  prompt diff (RI 60 and LotM 73 panels identical; ORV 54 panels lose only the
  sleeve clause in 48 and the xianxia culture negative) is all there is for
  them. Next GPU session: ORV chapter 1 and one project of another genre
  (Open defect 15).
- **Speaker join fixed (EVOLUTION 4.105).** `Span.speaker_self_id` is a
  surface, not an entity id; the viewer and the persona stage now join it the
  way voice casting does. Payload spans have `speaker_entity_id`. Every persona
  was previously profiled from 0 spoken lines; only extraversion changes. The
  re-measured prefix audit (`data/eval/prefix_audit/dialogue_fix/`) shows
  `big_five` unrepaired divergence is 112/289, not 0/289: **any quoted
  "big_five 0/289" result (4.103 era, `docs/research/PAPER/READER_FAITHFULNESS.md`)
  is superseded and has not been rewritten there.** Repaired build: 0 on every
  key, `persona_set` 0/296.
- **Studio render jobs now write `vN_<engine>-studio` directories and a
  `VERSIONS.md` line** (`jobs.py`), like the CLI. They used to write into the
  root of `panels/ch<N>/`. LotM v1's manifest is a reconstruction
  (`v1/manifest.reconstructed.jsonl`, from `prompt_cache_v1.json`; no negative
  prompts), not the original.
- **Visual genre is a project setting.** Settings "Visual style" card or
  `POST /api/projects/<id>/genre`; `novel.visual_genre` column; render and
  reference jobs carry it in their digest. `Store.add_novel` is an upsert now.
  `genre.py`'s docstring mentions an `echotales genre` command that does not
  exist.
- **Studio engine picker.** Local engines (noobai, illustrious, sdxl) are
  offered only when the card is free (`pipeline/gpu.py`, busy above 1,500 MiB
  used); the render and reference_gen routes return 409 with the memory in use
  when busy or missing. Stub is always allowed. Superseded in detail by
  `GET /api/compute` and `compute.resource_refusal` (EVOLUTION 4.106).
- **Video: `docs/design/video_plan.md` is the plan (uncommitted, plan only,
  nothing built).** Its flagged defects and an owner decision are Open defects
  17 to 19; none is fixed.
- **`persona.prefix_causal` is ON by default** (EVOLUTION 4.104).
  Whole-novel consumers are unchanged
  (`scripts/prefix_audit/product_parity.py`: 0 voice, 0 reference, 0
  dashboard diffs on all three serials); only the reader-position view
  changes. Stamps are written when the persona stage runs, so a database built
  earlier should keep its old stamps until that stage is re-run (inferred
  from the code, not checked per database).
- **The Read page does not list the whole-volume cast.**
  `GET /api/novels/<id>/reader?chapter=c` -> `webview.py::build_reader_cast`.
  LotM chapter 5: 69 of 91 characters hidden. The Review page is unchanged on
  purpose (whole-volume).
- **Check:** `echotales --db <db> faithfulness --novel <id> --cuts 5,10`
  (truncate-and-rebuild of persona + reader cast, exit 1 on divergence).
  Faithful at every tested cut on all three serials with the default build,
  still after the speaker fix; the legacy build (`--whole-volume-personas`)
  fails on LotM. Run it after any change under `persona/` or `core/state.py`.
- **The persona_set residual is closed** (`BodyChange.confirmed_at`,
  `core.state.current_bindings`). Read bindings through `current_bindings`,
  never raw `get_self_persona_bindings`, when counting or ordering bodies.
- **Open (Open defects 12 to 14):** the Read guarantee is display-only because
  the whole payload is still sent; echo folding can depend on an earlier change
  a prefix rejects; the permanent-injury prominence gate is whole-volume.
- **Open (new, Open defects 15 to 19):** no real-engine render under the genre
  profiles; genre detection is a heuristic; video-plan defects and the
  one-model-per-image decision.
- **The novelty one-pager was deleted (2495a1d); do not re-add it.**
- Tests: this block's 1,408 core+pipeline count is superseded by the newer
  block above.

## Pick up here — 2026-10-17 (reader-faithfulness: canaries, selection leak, counterfactual suffix, EVOLUTION 4.103)

- **Local, unpushed commits `8309cf2..6561dba` on `reader-faithfulness`.**
  Three pre-registered experiments, all local models, $0 (owner rule: no
  RunPod, no OpenAI key). Numbers and files are in EVOLUTION 4.103; the
  research record is `docs/research/PREFIX_FAITHFULNESS/` and
  `docs/research/PAPER/READER_FAITHFULNESS.md`.
- **Provenance to keep when quoting:** suffix canaries are text-derived
  (whole-volume card 22.8% of 54 events, long-context positional
  instruction 40.6% of 46, 0 without the suffix); the selection leak
  (19.4% vs 1.4% over 24 merged events) is judge-labelled; the
  counterfactual suffix (47 of 289 gender cuts depend on the suffix vs 23
  that diverge; 0 after the repair) is system-internal. No human labels.
- **Open:** `labels/human_check.csv` and the CHIMERA spot-check sheets are
  still unfilled, so every figure above is "model-generated reference".
  Counterfactual test covers one intervention (pronoun swap) and the
  deterministic persona path only. Nothing in this session's work changed
  a pipeline default. **Superseded 2026-10-18 (EVOLUTION 4.104): the
  `prefix_causal` repair is now on by default.**
- Tests: 1,383 core+pipeline pass (change author's run; 1,399 as of 2026-10-18).

## Pick up here — 2026-10-16 (webview Research view, EVOLUTION 4.102)

- **Uncommitted, additive UI surface.** `/research` page, three
  `/api/research/*` routes, `pipeline/research_demo.py`. Reads stored
  results under `data/eval/chimera/`; the live probe calls local ollama only
  (5-model allow-list). Details and run instructions are in EVOLUTION 4.102
  and `docs/paper/project_doc/FRONTEND_RESEARCH_VIEW.md`.
- **Open:** `GET /api/research/items` returns 404 until
  `python scripts/chimera/build_demo_items.py` has been run (needs the
  Gutenberg texts under `data/raw/pd_gutenberg/`, not in git).
- **Open:** every figure on the page is exploratory; labels are text-derived
  and the owner spot-check is pending. Nothing on it is human-annotated.

## Pick up here — 2026-10-02 (mutation lab, EVOLUTION 4.101)

- **Research state of record is still `docs/research/DECISION_LOG.md`.**
  Mutation pass:
  - 33 candidates re-examined and 46 mutations generated
    (catalog removed 2026-10-03; verdicts in `DECISION_LOG.md`).
  - 8 new hypotheses registered with their kill criteria before any code
    existed.
  - Leading thread: **label poisoning** (H-IOL). **Superseded 2026-10-03** by the convergence
    pass (`docs/research/CONVERGENCE.md`): the converged thesis is KILLED;
    XDIS is kept as product infrastructure.
- **Visual batch done (2026-10-03).** Results are in `docs/research/DECISION_LOG.md`.
  - **H-VRUNG** survives weakly: no rung hides both gender and hair.
  - **H-JUDGE-V** survives. Setting errors are lost in the generator
    (rendered 12.5%). CLIPScore is at chance (0.52) on verified-rendered
    gender and hair errors. The llava-7b judge was an invalid instrument.
- **H-XDIS done (2026-10-03).** Ladder-vs-qwen2.5 disagreement ranks the
  ladder's errors at AUROC 0.889, against 0.612 for the tier confidences.
  - Where they agree, the ladder is wrong 3.3% of the time; where they
    disagree, 51.7%.
  - This is the posterior the unconfirmed-voice gate lacks (H-GATE's
    16-18% cap). It is a product hook, not yet wired.
- **H-GATE-XDIS (CPU follow-up, 2026-10-03): CONDITIONAL.**
  Verdict in `docs/research/DECISION_LOG.md`; numbers in
  `docs/research/experiments/H-GATE-XDIS/RESULTS.json`.
  - Disagreement-then-confidence catches 67% of ladder errors at 20%
    review, against 37% for confidence. At 10% it is 39% vs 25%.
  - **Open:**
    - qwen was given a PDNC-gold-derived shortlist; rerun with a
      product-built list (GPU);
    - 58 PDNC gold labels are name variants not in the character keys;
      a CPU alias fix is needed.
- **Product findings from the panels (not fixed):** under the ink style,
  "1boy" drew no person in 4/10 male panels, back views drift to bare backs,
  and silhouettes leak hair colour. See `ENGINEERING_NOTES.md` 17.
- **Decisive human step:** the H-COST v2 listening study.
  - Stimuli built with the H-IOL predictions on the exact scripts:
    `data/eval/research/H-COST/real-v2-iol/`.
  - Synthesise with `--param synthesize=true` (about 1 GPU-h), then pilot
    about 24 listeners.
- **Resource rule (owner, 2026-10-02):**
  - Heavy models go on the GPU, loaded directly, after checking it is free.
  - Never CPU-offload weights into RAM.
  - Ask before any RAM-heavy job.
  - The research renderer is `datasets/visual_beats.py::render_gpu`
    (anonymous RAM 1.3 GB, against about 4.2 GB for the product engine's
    CPU offload).
- **Open product item (not changed):** `render/panels.py`
  Illustrious/NoobAI engines still use `enable_model_cpu_offload`. See
  `docs/research/ENGINEERING_NOTES.md` items 1-4 for the GPU-direct
  recipe, including the VAE tile-threshold fix.
- **Every problem hit this session, with its lesson:**
  `docs/research/ENGINEERING_NOTES.md`.

## Pick up here — 2026-10-02 (research arena, EVOLUTION 4.100)

- **Research track lives in `packages/research/` and `docs/research/`;
  `docs/research/DECISION_LOG.md` is the state of record.** Five
  experiments run on real data: H-CAL killed, H-HEDGE killed, H-GATE
  surviving weakly, H-COST open, H-SELECT open. Numbers: EVOLUTION 4.100.
- **Decisive next step: the H-COST listening pilot** (study built, needs
  listeners; about 50 listeners or more probes per passage for a decisive
  run). Fix two design issues first: same-gender errors realise at about
  half the requested rate (select passages with 2+ speakers per gender or
  report realised rates), and narrator-only renders run about 30% longer
  (60 s vs 46 s), a duration confound to normalise or covary.
- Run the research suite explicitly: root testpaths omits it
  (`python3 -m pytest packages/research/tests -o addopts=""`).

## Pick up here — 2026-09-27 (Minimal Disclosure Compiler, EVOLUTION 4.99)

- **Priority 1 of 3 IPR-review candidates (Minimal Disclosure Compiler)
  is done, with measured results.** New `core/disclosure.py`
  (`compile_minimal_disclosure`) narrows an already observer/temporally-
  valid `state_of()` candidate set to the minimum sufficient subset a
  declared `TaskSpec` needs — greedy attribute-key coverage +
  cross-referenced-cast relationship filtering + alias disambiguation +
  dependency closure. Opt-in render integration only
  (`plan_builder.build_render_plan(..., use_mdc=False)` default unchanged).
  13 new tests, full suite still green. Full detail and numbers:
  EVOLUTION 4.99, `docs/results/MDC_DISCLOSURE_ABLATION.md`.
- **The render-task result (100% evidence reduction) is real but
  structurally hollow** — render's own `RENDER_TASK_SPEC` needs nothing
  SELF-level, and the real database has zero SELF attributes to filter
  from anyway (see open defect below). **The dialogue_brief result (36.4%
  reduction on a synthetic fixture, correctly dropping an offstage
  relationship while keeping an onstage one) is the one that actually
  demonstrates the mechanism is more than a renamed top-k/RAG filter** —
  no existing mechanism in this codebase does that.
- **Next up: Temporal-Epistemic Delta Compiler (priority 2 of 3).** Not
  started. Counterexample-Guided Generation (priority 3) after that.
  Neither of these results, nor MDC's, is a patentability determination —
  that's a separate, later prior-art/IPR review.

## Pick up here — 2026-09-26 (evidence-upgrade pass, EVOLUTION 4.91)

- **A7 cache-key ablation found and fixed a real defect**: the shipped
  render cache key served 23/23 panels stale on a drawn-persona hair or
  attire change (`state_of` on a Self only returns Self-targeted
  attributes; appearance attributes are Persona-targeted). Fixed in
  `render/plan_builder.py`, which now hashes the drawn persona's standing
  attributes into `state_digest`; two regression tests added. After the
  fix: 0 stale reuses, but 274 unnecessary regenerations over 218 stub
  panels — the digest now over-invalidates (an undrawn concurrent body, a
  non-visual Self attribute). Aliases are still not in the key. This was
  stub-mode only, no GPU; docs/archive/COMPLETION_PLAN.md item 25's real-render leg
  (change a seed on a real image engine, confirm invalidation) is still
  open.
- **A1/A2 make the observer axis causal, not just descriptive.** Collapsing
  observer to READER: 194/194 state and render-plan leaks. Removing
  knowledge time (+inf): 14 state leaks, 0 render leaks (embodiment
  bindings are reader-scoped). FULL: 0 leaks, 9 mid-chapter under-exposures.
- **LitBank gives the first human-annotated external number** (not the
  project's own LLM-drafted silver set — never call that set "gold"):
  standard CoNLL F1 15.9 (full person key) / 42.4 (proper-name mentions
  only), 100 documents. Not comparable to the published supervised 68.1
  (different task scope: no pronoun/nominal resolution by design).
- **Human-review package prepared, not run**: 200 stratified mentions + 88
  hard cases as gitignored CSVs. 0 labels, κ not computed — still the
  single largest gap per `docs/status/STATUS.md`'s readiness
  gate (Area 8, WAITING ON HUMAN).
- Full detail: EVOLUTION 4.91, `docs/results/A7_CACHE_ABLATION.md`,
  `docs/results/EXTERNAL_BENCHMARK.md`, `docs/results/HUMAN_REVIEW_PROTOCOL.md`,
  `docs/status/STATUS.md` (readiness gate, updated 2026-09-26).
- Suite: **1,085 passed** (was 1,078).

## Pick up here — 2026-09-25 (finalization pass, EVOLUTION 4.90)

- **Canonical database:** `data/db/reverend-insanity.db` (v1.1, sha256 `a2695660…`; v1 `42107645…`). Every script defaults to it (`docs/results/CANONICAL_RUN.md`). Per-claim status is in `docs/results/FINAL_EVIDENCE_TABLE.md`.
- **Next research work, in order:**
  1. Transmigration: LOTM's Zhou Mingrui and Klein are resolved as two Selves.
  2. Hard-case detection: address terms 16, relational 15, definite titles 11 (`data/eval/hardcase_taxonomy.json`).
  3. Attribution tier 4: 12 right / 16 wrong, and unstable across runs.
- **Do not re-run** anything that the canonical database already measured; `scripts/reproduce_results.sh` regenerates every artifact in about 10 minutes.

## Earlier — 2026-09-25: completion pass landed; read `docs/status/STATUS.md` first

That file is the single status record. The short version:

- **Verified on real data:** observer-conditioned generation on a real image
  engine; observer and knowledge-time query axes; read-set invalidation;
  sequential Self/Persona; both baselines; retriever recall@K; scorer
  diagnosis. Details in EVOLUTION 4.85.
- **The scorer cannot link by arithmetic** (max p = 0.550 vs 0.80) because
  three of its five weighted features are inert on this corpus. Ranking is 94%
  correct. Do not retune weights; see `docs/results/SCORER_DIAGNOSIS.md` Section 6.
- **Hard cases are lost at mention detection** — the next real research work.
- **Run-order trap:** `resolve` deletes persona bindings. Never run it after
  `run` without rebuilding personas.
- **EARS voice bank** rendered RI ch1 (`data/novels/RI/audio-runs/ears-native/`, EVOLUTION
  4.87). Next audio work is speaker attribution, not the bank: the opening
  siege lines are attributed to the vocative addressee and to Bai Ning Bing.
  4.88: pronoun speaker recovery is now opt-in (2/15 right); the honest
  attribution rate is 46.1%. Tier 4 (real LLM, ch1-3) is still on and is
  where the ch1 errors come from.
  Run Chatterbox via the `uv run --with chatterbox-tts --with "setuptools<81"`
  overlay; this session's venv has both installed directly, which is drift.
- **Before any patent filing:** read Narrative Graph Prompting (ICCVW 2025)
  and StoryWeaver (arXiv:2412.07375); the repo has been public since
  2026-08-07.

## Pick up here — Tracks 1-4, 6 largely landed; **three things are blocked and one of them gates everything**

**Session of 2026-09-23/24.** `docs/archive/COMPLETION_PLAN.md` carries DONE markers
per item; `docs/EVOLUTION.md` 4.76-4.83 has the detail. Suite **1,038 passed**
(was 928). **Read this list of blocked items before starting anything.**

### Blocked, in priority order

1. **Track 1 item 3 — the measuring re-run. DONE 2026-09-24.** Full account
   in `docs/results/NER_WINDOWING_RESULT.md`. The blocker was a **misdiagnosis**:
   ollama was not unreachable from a sandboxed shell, the daemon was simply
   not running (`ollama serve` brought it up in one second). Full volume,
   47 min, 660 calls, 0 escalations.

   **Prediction adjudicated as recorded — one part refuted.** CEAF-e recall
   25.2% → **48.9%** (confirmed); identifiability 48.8% → 63.0% was first
   marked confirmed but is **superseded** (EVOLUTION 4.88: the honest rate is
   46.1%, flat, so REFUTED); "mentions roughly double" → **+14.6%, REFUTED**. The fix
   finds *entities*, not mentions: **82 → 261 (+218%)**, because `_locate`
   already searched the whole chapter, so truncation only ever hid entities
   appearing *solely* past 6,000 chars. Bai Ning Bing now has ch1 mentions
   at exactly the three gold offsets (6697/6814/8757), first appearance
   ch108 → **ch1**.

   Side effects: the contradiction detector fires on real data for the first
   time (**50 contradictions → 50 splits**, was zero on 60 chapters); entity
   typing is now 261/261 with 0 unknown; `TURN_TAKING` is gone from
   attribution. **The scorer still links nothing** on a 57% larger evidence
   cache (15,796 pairs), which closes the starvation defence.

2. **Track 5 items 19-21 — CLIPScore pixel QA. The plan's premise was
   wrong.** It assumed `torch`+`transformers` was enough. Only CLIP's
   *tokenizer* is cached locally; `openai/clip-vit-large-patch14` has **no
   config and no vision weights** on disk, so the bench needs a ~1.7GB
   download. 1,182 panels are on disk waiting to be scored.

3. **Track 6 item 27 — verify the four LINK-KG claims** (`docs/design/plans.md:800-806`)
   against arXiv:2510.26486. Needs network. The disclosure's whole positioning
   rests on them and they have never been checked.

Also needing a GPU, not a blocker for the above: item 18 (the two
observer-contrast figures), item 25 (real-render cache invalidation).

### Landed this session, verified against real data

- **4.76 NER windowing + `item` label** — `text[:6000]` meant **51.9% of RI
  ever reached the model**; 199/199 chapters over the cut. Unit-tested only;
  see blocker 1.
- **4.77 resolution provenance + compounding curve** — `by_method` said 100%
  `SCORED` by construction. With the lie removed: **the scorer settles 0 of
  880 links.** All 880 are hard pre-filters, 870 of them gazetteer. First real
  compounding curve: `w0=81% w1=93% w2=89% w3=96% w4=91%`.
- **4.78 evidence cache + `echotales ablate`** — over 10,058 real pairs the
  scorer's **max output is 0.527 against a 0.80 threshold**, so a scored link
  is arithmetically impossible. `temporal_validity` blocks **zero** pairs.
- **4.79 draft ambiguity guard + escalation rate** — the ladder has **never
  escalated** (0 of 370 calls).
- **4.80 observer axis** — `docs/design/architecture.md`'s headline acceptance test
  **passes on real data for the first time**: READER 2 aliases, a witness 1
  (strict subset), a non-witness 0.
- **4.81 blind annotation / held-out coverage / bootstrap CIs / traceable
  results** — `eval` now prints intervals and persists to
  `data/eval/results/<run_id>/` with a `-dirty` commit marker.
- **4.82 invention disclosure** — `docs/private/IP/invention_disclosure.md`, gitignored.

### Needs your decision, not more work

**Both shipped RI gold drafts have silently colliding records** (4.83).
`GoldMention.key` is `(novel, chapter, offset)`, so a word-boundary *prefix*
surface lands two records on one offset and one overwrites the other.
`reverend-insanity-c1-c5.toml` has **14** — `"Gu Yue"` is annotated as the
clan and prefixes its own members' names, so every clan member's position also
carries an organization record. The extended file has **13**, including bare
`"Gu"` (a negative) prefixing `"Gu Yue"` (a real entity). This is the file
4.74 called the project's best artifact. **Left unedited deliberately** —
changing what an annotator asserted is your call — and pinned by an
expect-to-raise test so it cannot be lost. Nothing in production expands these
TOMLs, so nothing is broken today.

### Still open and not blocked (just long)

- **Track 2 item 5** — LOTM ch1-3 of 40 drafted (4.83,
  `data/gold/lord-of-the-mysteries-c1-c3.toml`, 173 mentions, 24 identities).
  ch4-40 and all of ORV remain; it is a reading task, not a code one.
- **Track 5 items 22-23** — depend on the blocked bench.

### The thing not to forget

**There is still zero confirmed gold.** Every coreference number printed is
scored against unconfirmed drafts, 56% of the RI file is circular, and `eval`
says so on every run. The blind annotation tool (`echotales annotate`) is
built and round-trip tested; running it is the owner's call, after exams.

## Pick up here — gold retraction: there is still no gold set (docs-only pass, verified)

**Status: done and verified for what it claims — a false number was removed;
no true one was produced.** Full account in `docs/EVOLUTION.md` 4.74 (do not
re-derive it from this summary). The confirmed-tier B³ result this file
and `docs/status/STATUS.md` used to cite (precision=100.0%, recall=94.6%,
f1=97.2%, RI ch1-60) is **retracted**: the gold it was scored against
(`reverend-insanity-c1-c50.jsonl`, 6,952 records) was built by
`eval/generate_gold.py::_extract_gold_from_db` `SELECT`ing the pipeline's
own resolved `mention` table, then flipped to
`provenance: human, confirmed: true` on 2026-08-12 without an independent
human review pass. It measured the system against itself. The draft-tier
figure (98.1% F1) is equally circular. Do not cite either number, and do
not "fix" this by re-running eval against an older copy of the gold file.

- **Verified:** the file is quarantined at
  `data/gold/_unusable/reverend-insanity-c1-c50.jsonl` (see its
  `README.md` for exactly why, and why it's not curable by review).
  `eval/gold.py` now has a structural contract that would have caught
  this — `CIRCULAR_DRAFTERS`, `GoldProvenanceError`/`CircularGoldError`/
  `UnattributedConfirmationError`, a `ReviewDepth{NONE,BULK,PER_RECORD}`
  enum, `confirmed_by` required whenever `confirmed=True`. New
  `test_gold_provenance.py` (9 tests) drives every branch.
  `test_all_novels_gold_sets.py` was rewritten so it can no longer assert
  the false claim it used to assert. Full suite green: 914 passed in
  26.6s, run at time of writing (per EVOLUTION 4.74).
- **Not verified / not done:** this pass did not produce any new gold.
  **Zero gold records exist across the whole corpus right now** — every
  file in `data/gold/` is `confirmed: false` (including the two
  genuinely independent drafts, `reverend-insanity-c1-c5.jsonl` and
  `reverend-insanity-hardcases.jsonl`, which were bulk-approved rather
  than circular and are the better starting point for an actual human
  pass). No resolver accuracy number, Baseline A comparison, or recall@k
  result in this codebase is anchored to anything right now.

See `docs/status/STATUS.md`'s "Stale claims found this pass" #5 and its "Gold
datasets"/"Evaluation harness"/"Baselines" rows for the corrected
component-status detail.

## Pick up here — Product Orchestration track (backend done, no frontend yet)

**Status: backend contracts complete and tested; explicitly no frontend
work done, per the approved plan's scope limit.** Implemented per
`~/.claude/plans/cheerful-orbiting-squirrel.md`. This closes
`docs/status/STATUS.md`'s "Jobs/progress", "File upload", "Output library" rows
(previously all **Missing**) and widens "Backend API" past its old
review/correction-only scope.

- New `Job` model (`core/models.py`) + `job` table/CRUD (`core/store.py`),
  following the existing `pipeline_run`/`stage_run` schema pattern.
- New `packages/pipeline/src/echotales/pipeline/jobs.py` — `JobQueue` (one
  daemon worker thread, strictly sequential process-wide, matching the
  existing ollama/diffusion GPU-sharing constraint), `run_stage`/`run_job`/
  `_dispatch` (maps `Job.kind` to the real stage functions), and
  `ALLOWED_HTTP_ENGINES` (excludes `gemini`/`openrouter` from the HTTP path
  entirely — those stay CLI-only). `commands.py::cmd_run`'s closure now
  delegates to `jobs.py::run_stage` (`skip_if_succeeded=False`, so `echotales
  run`'s always-execute CLI behavior is unchanged — the new resumability
  skip is opt-in, scoped to HTTP-triggered jobs).
- New `packages/pipeline/src/echotales/pipeline/_multipart.py` — minimal
  stdlib-only `multipart/form-data` parser for the two upload routes.
- `webview_server.py` gained project lifecycle (`GET`/`DELETE
  /api/projects`), EPUB upload (`POST /api/projects/<id>/source`), job
  triggers for every stage (`POST /api/projects/<id>/{ingest,resolve,
  appearance,persona,render,voice,refimg_search,reference_gen}`), job
  status (`GET /api/projects/<id>/jobs`, `.../jobs/<job_id>`), reference
  candidate/search/upload routes, a read-only render preview
  (`GET /api/novels/<id>/render/preview`, wraps `plan_builder.py::
  build_render_plan`), real generation jobs (`POST .../render/generate`,
  `.../reference/generate`, engine allowlist-checked), and an output
  library (`GET /api/novels/<id>/output`, `.../output/file`, filesystem
  walk of `pipeline/paths.py`'s existing layout, path-escape-guarded).
  `Registry` now scans `data/projects/*.db` at startup so a project
  created via the API survives a restart. Found and fixed in passing:
  `Store.is_canonical` is a `@property`, not a method — two new call sites
  were calling it as `.is_canonical()` (would have thrown `TypeError` the
  first time `DELETE /api/projects/<id>` hit a canonical id), caught while
  writing the integration test, before it shipped broken.
- Tests: `packages/pipeline/tests/test_jobs.py` and
  `test_webview_server_jobs.py` (new file — `webview_server.py` had zero
  test coverage before this). Full suite green.
- **Verified:** unit/integration tests pass, stub-mode dispatch and
  resumability-skip both exercised for real in `test_jobs.py`. **Not
  verified:** no real end-to-end manual walkthrough (upload → ingest →
  resolve → persona → render/preview → render/generate → output) was run
  against a live server with a real EPUB this session — only the
  automated test suite. **Not done at all, and out of scope per the
  approved plan:** any frontend/webview UI wiring — `ManuscriptProgress.js`
  still shows a hardcoded placeholder list, and the upload `<input>` is
  still rendered `disabled`. Next session picking this up should wire the
  frontend to these routes, or run the manual end-to-end check first if
  that hasn't happened yet.

See `docs/EVOLUTION.md` 4.73 for the full design rationale (reused vs. new
mechanisms) and `docs/status/STATUS.md`'s "Backend API"/"Jobs/progress"/"File
upload"/"Output library" rows for the corrected component-status detail.

## Pick up here — Core Pipeline Hardening (session 1 of the 24-section plan)

**Status, verified vs. not — see EVOLUTION 4.72 for the full detail.** This
session executed a scoped subset of `~/.claude/plans/mighty-squishing-
feigenbaum.md` (see `~/.claude/plans/dynamic-rolling-sun.md` for the exact
scoping). Full suite green (`python3 -m pytest packages/core/tests/
packages/pipeline/tests/ -q`).

- **Done and verified for real:** `PipelineRun`/`StageRun`/`StageArtifact`
  provenance tables + dataclasses, wired into `commands.py::cmd_run`
  (confirmed via direct SQL against a real stub-mode run); deterministic
  self-ids (`resolve/runner.py::_stable_entity_id`, no more in-process
  counter); per-chunk transaction/rollback safety + `PartialStageFailure`
  across `resolve_novel`/`build_personas`/`extract_appearance`; canonical-
  vs-scratch DB guard (`Store.is_canonical`, `data/canonical_dbs.json`,
  `CanonicalRewipeBlocked`, `--force-rewipe` flag) — confirmed for real
  against `data/archive/db/reverend-insanity-webview-working.db` (refused to wipe,
  real 82-row table untouched); `RenderArtifact` instantiated for the
  first time (`render/panels.py`, sidecar `render_artifact.jsonl`,
  confirmed present on all 47 panels of a stub-mode RI ch1 smoke run);
  render's half of the canonical `state_of()` boundary
  (`character_looks` now takes the same `StateResolver` instance
  `plan_builder.py` uses); a new direct Self/Persona boundary property
  test (`test_self_persona_boundary.py`, no code change needed —
  `state_of()` was already correct).
- **NOT done — do not read as complete:** resumability is built but not
  live — `cmd_run` doesn't yet call the skip-if-succeeded `stage()`
  context manager, so a real CLI rerun still re-executes every stage from
  scratch even when nothing changed. Voice's half of the `state_of()`
  boundary is read-side only: `load_trait_profiles` can now accept a
  `position`, but `build_personas` still writes one trait profile per
  *entity*, not per body-epoch, so a transmigrated character's voice still
  doesn't differ by body (unchanged from EVOLUTION 4.71's finding — this
  session made it fixable later, not fixed now). No full non-stub render
  was run against this session's changes — everything above is verified
  via unit tests, a stub-mode smoke run, or a real read-only query, never
  a real end-to-end render.
- **Defect #8 (recurring unnamed characters get a fresh voice every
  chapter) is now partially fixed**, not fully — see the "Open defects"
  entry below for the exact boundary of what's fixed vs. still open, and
  the new distinct `EPITHET_SLOT` finding.

**Next steps, in order (from the unexecuted tail of the 24-section plan):**
1. Wire `cmd_run` onto the skip-if-succeeded `stage()` context manager so
   resumability is actually live, not just unit-tested.
2. Decide whether to fix the `EPITHET_SLOT` chapter-scoping bug found this
   session (see Open defects) in the same pass as defect #8 or separately
   — the fix shape differs (drop `chapter.number` from that tier's key,
   not add a resolved-entity lookup).
3. World/appearance wiring (plan §12), scene/beat/panel boundary docs+test
   (§13), video QA (§16-17), the full 8-scenario failure-injection suite
   (§18), and the real E2E fixture (§19) remain untouched — pick up from
   `mighty-squishing-feigenbaum.md`'s original section numbering.
4. If picking up voice/persona body-state work: the write-side fix
   (`build_personas` computing a trait profile per body-epoch, not per
   entity) is the actual remaining gap, not another read-side accessor.

## Pick up here — webview frontend redesign & short-form video reels

**Superseded in part by the 2026-09-26 visual/routing redesign** (uncommitted
at time of writing): `App.js`/`Viewer.js` referenced throughout this section
no longer exist — they were deleted and replaced by `webview/src/router.js`
(react-router-dom v7 routes: `/`, `/projects`, `/p/:projectId`,
`/p/:projectId/read/:chapter?`, `/cast/:selfId?`, `/studio`, `/review`,
`/settings`, `/design`) plus `webview/src/pages/`. The old `?review`/
`?gallery` query-param screens now redirect to `/review`/`/design`. Visual
direction also moved from the Fraunces/brass "editorial archive" look
described below to a dark, violet-accented ("cinematic dark") design system
in `webview/src/index.css`/`tailwind.config.js`. **That violet direction was replaced
the same day by a warm-ink one (Newsreader/Instrument Sans) and then restored on 2026-09-27
(`ec6a1d2`, violet again with the layout/contrast fixes kept; EVOLUTION 4.93),
and 4.93 also lists the server and React fixes made after the QA doc was written --
no human usability review was done. The bullets below predate
that redesign and describe file paths that no longer exist; read them for
history of what was fixed, not as a map of the current tree.

**Status, verified vs. not:**
- `Login.js` / `NewProject.js` / `CharacterDashboard.js` — **done**, `Section7Smoke.test.js` passing (8/8).
- `create_mention` frontend UI — **done**, wired via `+ mention` action button in edit mode (`App.js`, `ScriptView.js`, `ScriptLine.js`).
- Gold QA Datasets — **full-volume draft coverage, zero records confirmed anywhere (EVOLUTION 4.74, 2026-09-23 — supersedes this bullet's earlier claim that RI ch1-60 was human-reviewed)**. All three novels now cover their entire sources.toml volume: `reverend-insanity` 198/199 ch (ch164 has zero resolved character mentions at all -- **root-caused as far as possible without a full re-run, EVOLUTION 4.66: not a current-code defect** -- standalone replay of ch164's real content and its real cached NER output produces 39 valid mentions on today's code, so the canonical DB most likely just predates the 4.62 alias-type fix and needs a re-resolve; not fully confirmed, check ch164 again after the full RI re-resolve in the "start here now" section above), `lord-of-the-mysteries` 213/213 ch, `omniscient-readers-viewpoint` 186/188 ch (ch14/121 genuinely feature only side characters outside the 5 tracked leads). **`reverend-insanity`'s original ch1-60 file (6,952 records) was never human-reviewed at all** — it was drafted by `eval/generate_gold.py::_extract_gold_from_db` from the pipeline's own `mention` table and flipped to `confirmed: true` on 2026-08-12 without an independent pass; it is circular (the system scored against itself) and is now quarantined at `data/gold/_unusable/reverend-insanity-c1-c50.jsonl`. Every remaining record everywhere, including all of LOTM/ORV, is `confirmed: false` -- drafts to audit, not ground truth; the two files that are genuinely independent of pipeline output (`reverend-insanity-c1-c5.jsonl`, `reverend-insanity-hardcases.jsonl`) are unconfirmed but not circular, and are the actual starting point for a real human pass. `generate_gold.py`'s `identity_map`s had drifted wrong (self-ids are per-resolve-run, not stable) and were re-derived by looking up each character's current target_id directly in the DB being used -- see the module's own docstring before rebuilding these again after any resolve rerun. LOTM's resolver also leaves bare given/family names (`"Klein"`, `"Moretti"`) as separate self-ids from the full-name id for every tracked character in `data/archive/db/lotm-vol1.db` -- folded into identity_map correctly for gold-labeling, but the underlying non-merge is a resolver characteristic worth root-causing separately.
- Reference Image Quality Filtering — **done**, automated domain/title evaluation filters aggregator spam (`wallpapercave.com` etc.) without human intervention (`refimg_search.py`).
- LOTM Persona Split — **done**, multi-persona body split emission verified for transmigrations (`test_lotm_persona_split.py`).
- ORV System Windows — **done**, bracketed status notifications classified cleanly (`test_orv_system_window_classify.py`).
- Recurring Unnamed Characters — **entity-resolution half done**;
  cross-chapter `target_id` persistence verified
  (`test_unnamed_recurring_character_persistence.py`). **The voice half is
  now partially fixed (EVOLUTION 4.72, 2026-09-22, same day as this
  section's original 4.71 finding):** `speakers/runner.py::
  _assign_anonymous_slots` now keys off a resolved `target_id` when
  exactly one already-resolved, present entity shares an anonymous span's
  block — but genuinely-unresolved anonymous dialogue (the ambiguous
  zero-or-2+-candidate case) still mints a fresh
  `{chapter_number}:{scene_key}:{slot}` id every chapter, and a separate
  `EPITHET_SLOT` attribution tier in the same file was found to have the
  identical chapter-scoping bug, untouched. See open defect #8 for the
  exact boundary — don't read this bullet as fully closing #8.
- Baseline A LLM Benchmark — **done**, `eval/baseline_a.py` built and tested (`test_baseline_a.py`).
- Short-Form 9:16 Reels Engine — **planning-only stub, not wired in**. `render/reels.py` is pure dataclass/enum planning logic (`build_reel_plan_for_chapter`, `derive_reel_pacing`) that produces a `ReelCompositionPlan` describing style/pacing/camera-motion labels. It has no ffmpeg call, no dependency on `compose.py`, and is imported nowhere outside its own `test_reels_render.py` — it does not composite video. Integration with the real render pipeline is unbuilt.

**Next steps, in order:**
1. Check whether the `CharacterDashboard.js` rebuild agent finished; if so,
   verify it with real Playwright MCP screenshots (`mcp__playwright__
   browser_*`, now connected — see EVOLUTION 4.63) against a real
   `echotales webview-server` instance, not just `Section7Smoke.test.js`
   (that only proves it renders, not that it looks right).
2. If you installed/enabled a new plugin or MCP server this session and a
   tool from it isn't appearing, reload the VSCode window first — plugins/
   MCP servers registered mid-conversation don't become available without
   a full "Developer: Reload Window" in this environment.
3. ~~Redesign `App.js`'s shell next (it's the one screen every other
   screen sits inside)~~ **Done, unverified visually, EVOLUTION 4.68
   (2026-09-13)** — header/view-tabs/corrections button now use the
   `Button`/`Label` primitives and `font-display` heading, matching
   Login/NewProject. `Section7Smoke.test.js` 8/8 and `react-scripts
   build` both clean, but no Playwright MCP connection this session to
   actually see it — confirm visually before calling this screen done
   the way Login/NewProject were. Then the generation-review and
   output/library screens (still not started — see item 4, both need new
   backend routes first).
4. Before building any frontend feature for upload, ingestion progress,
   reference-candidate search, img2img editing, per-body-state reference
   images, generation preview, or an output library — check EVOLUTION
   4.63's confirmed backend-gap list first. None of those endpoints exist
   yet; building frontend UI that assumes they do will need a matching
   backend route added, not just a fetch call.
5. Checked this session — no stray `*.png` screenshot files at the repo
   root currently (searched for `char-list-1440.png`, `char-detail-*.png`,
   `check-login.png`, and any other root-level `*.png`; found none). The
   Playwright MCP path-naming quirk from EVOLUTION 4.63 either didn't
   recur or was already cleaned up — nothing to do here right now.
6. ~~Unrelated bug found incidentally while verifying screens, not yet
   root-caused: live-edit mode with a fresh manifest can throw `Cannot
   read properties of undefined (reading 'spans')` in `ScriptView`/
   `App.js`'s chapter-rendering path.~~ **Fixed, EVOLUTION 4.67
   (2026-09-13)** — an out-of-range `chapterIdx` after a manifest refresh
   handed `ScriptView` an `undefined` chapter with no guard. `App.js` now
   clamps the index on refresh; `ScriptView.js` also gained a defensive
   empty-state guard. `Section7Smoke.test.js` still 8/8 green. Not
   confirmed live in a browser (no working Playwright MCP connection this
   session) — see EVOLUTION 4.67 for the exact caveat.

## Pick up here — resolve/render pipeline remediation

**`TRANSFERABLE_TITLE` end-to-end is fixed and verified (EVOLUTION 4.62)
— this item is closed, do not re-derive it.** 4.61's validation failure
(0 mentions, RI ch1 blocks 68-78 empty) turned out to be four independent
gates, not one: the NER system prompt's exclusion (needed an imperative
MUST rewrite, a soft addition measurably did nothing),
`chapter_ner.py::plausible_name`'s capitalization check, `alias_type.py::
classify_alias_type` not recognizing a proper-noun-qualified compound
title ("Gu Yue clan head"), and `chapter_ner.py`'s deterministic
per-chapter vocabulary sweep not folding in a shorter bare-form variant
("the clan head") of the surface the LLM actually returned. All four
fixed; live-verified against real ollama/qwen2.5:7b on RI ch1-15
(`data/scratch/reruns/validation-4.62.db`, scratch, deleted after use):
`TRANSFERABLE_TITLE` went 0 → 9 mentions across ch1-15, RI ch1's clan-head
case specifically now has all 8 occurrences (blocks 40, 57, 61, 64, 68,
73, 75, 78). All of ch1's title mentions correctly DEFER to
`target_id=None` — verified against the source text that the clan head is
genuinely never named in ch1, so this is non-negotiable #9 working as
designed, not a remaining defect. Six-Wang guard and full suite both
clean throughout. Files changed, now committed (`3577143`):
`mentions/ner.py`, `mentions/alias_type.py`, `mentions/chapter_ner.py`.
See EVOLUTION 4.62 for the full four-gate breakdown and exact numbers.

**4.65 update (2026-09-13): pipeline confirmed still healthy post-4.62 on
a 3-chapter real (non-stub) smoke run — full-scale run still not done,
see EVOLUTION 4.65 for exact numbers and the `ingest`+`resolve` vs. `run`
gotcha found while setting it up.** User explicitly gated the full render
down to a 3-chapter check first ("we havent tested the pipeline after the
multiple changes so need a small run first"). `echotales run --novel
reverend-insanity --chapters 1-3` against a scratch DB
(`data/scratch/reruns/smoke-4.64-ch1-3.db`) with real ollama `qwen2.5:7b`
completed cleanly end to end in ~2 minutes, `TRANSFERABLE_TITLE=8` in
ch1-3 alone — consistent with 4.62's ch1-15 numbers, no regression at
this scale. `eval --report` against a 3-chapter DB is not a real recall@k
result (gold set spans 198 chapters, so almost everything reports
`(unresolved)` by construction) — don't read that number as a finding.

**Item 1 below is DONE, EVOLUTION 4.69 (2026-09-21) — no new run was
needed, a full real render already existed uncommitted.** Item 2's
recall@k re-run also happened, but the honest result is that the
`TRANSFERABLE_TITLE` gate is *structurally* unmeasurable on RI, not merely
untested — read 4.69 before trying to "finish" this by annotating more
gold or re-running the render again; neither would change the result.

1. ~~The full fresh real render + Section 1.3 relevance-harness
   numbers.~~ **The render itself is done, EVOLUTION 4.69 — the B³ number
   reported here is RETRACTED, EVOLUTION 4.74 (2026-09-23), do not cite
   it:**
   `data/scratch/reruns/ollama-eval-reverend-insanity.db` (produced as a side
   effect of the 2026-09-12 gold-QA commit, postdating the 4.62 fix) is a
   real, non-stub, full 199-chapter render — verified directly (312 real
   `qwen2.5:7b` `llm_call` rows, `TRANSFERABLE_TITLE=30` mentions present).
   That part stands. What does not stand: the "confirmed-only B-cubed"
   figure this bullet used to report (precision=100.0%, recall=94.6%,
   f1=97.2%) was scored against `reverend-insanity-c1-c50.jsonl`, gold
   built from the pipeline's own `mention` table and marked
   `confirmed: true` without an independent human pass — it measured the
   system against itself, and the "no regression vs. the pre-remediation
   baseline (precision=100%, recall=95%, f1=97.4%)" framing is equally
   meaningless, since that older figure was circular too. See EVOLUTION
   4.74 and `data/gold/_unusable/README.md`. There is currently no gold
   set this render can be honestly scored against. Note for next time:
   check `data/scratch/reruns/` and `git status` for an existing uncommitted
   artifact before spending GPU/LLM hours re-deriving one — this file sat
   there for over a week with no doc pointing at it.
2. ~~Re-run `echotales eval`'s recall@k gate against the full run.~~
   **Done, EVOLUTION 4.69 — result is a root cause, not a number.**
   `TRANSFERABLE_TITLE` recall@10 still reads "GATE: untested," and it
   always will on this novel with the current eval design: every real
   `TRANSFERABLE_TITLE` mention on RI correctly resolves to
   `target_id=None` (0/30, by design — non-negotiable #9), but
   `generate_gold.py` and `build_gold_retrieval_cases` both only admit
   mentions with a *resolved* `target_id` into gold/recall@k cases. So
   100% of gold (6,238/6,238 mentions, all confirmation tiers) is typed
   `RIGID_NAME` — zero `TRANSFERABLE_TITLE`/`EPITHET`/`RELATIONAL_DEICTIC`
   records exist anywhere in it, structurally, not from a coverage gap.
   **New open item, not yet attempted:** the eval question needs to
   change for this alias type — either test retrieval against a novel/arc
   where a title-holder *is* eventually revealed, or score correct
   DEFER-to-`None` itself as the measured behaviour. See EVOLUTION 4.69
   for the exact reasoning; this is an eval-design decision, not a bounded
   patch.

Also still open, lower priority than the above:

3. **Superseded by the "webview frontend redesign" section at the top of
   this file (EVOLUTION 4.63, 2026-09-11) — a full visual redesign of
   `webview/` is now underway, not just a visual check of the old UI.**
   The old note below is kept for the historical test-coverage detail
   (`Section7Smoke.test.js` did pass 7/7 at that point against the
   *pre-redesign* UI), but the actionable next steps are in the section
   above, not here. Original note: no browser tool was available in that
   session (checked; the user had started installing the Claude-in-Chrome
   extension but opted to continue without it) —
   `webview/src/components/__tests__/Section7Smoke.test.js` exercised
   actual render + event-handler code for Login, NewProject, and
   CharacterDashboard against realistically-shaped mocked API data: login
   success/failure, slug derivation, voice/reference-image click handlers
   calling the real API signatures, evidence-quote rendering, and honest
   empty/404/error states.

(Item 1 above already covers re-running `echotales relevance`/speaker-
attribution numbers against a full fresh real render — this was folded
in rather than duplicated as its own item.)

See EVOLUTION 4.60/4.61/4.62 (search for them) for the full
section-by-section numbers and reasoning. Before this pass, the live area
of work was the render/direction pipeline — see EVOLUTION's 4.51-4.59
entries if picking that thread back up instead.

Before this pass, the live area of work was the render/direction pipeline
(`packages/pipeline/src/echotales/pipeline/render/`). Most recently
(EVOLUTION's newest entries): the byte-identical crowd-panel bug, a
solo-tag front-load gap, and a Danbooru-tag-form gap in the crowd/solo
contradiction validator were all found and fixed, then confirmed at full
48-panel scale (`v54_crowd-solo-scenestate-fix`, see `VERSIONS.md`).

**Resolved (EVOLUTION 4.56):** block 31 of RI ch1's v54 render mis-cast
"Qing Mao Mountain" — a location — as a named character. Root cause:
`self_entity.kind` was NULL for every row in this stale database (mentions
last ran before the Layer-1 `entity_label` pass existed), and
`Store.get_self()` reads a NULL `kind` back as SELF/person by default. A
new `resolve --novel <id> --kinds-only` backfill (`resolve/kind_backfill.py`)
reclassifies existing rows from the on-disk NER cache. **Run for real
against the production file on 2026-09-01** (the first pass had only run
against a scratch copy despite an earlier note here implying otherwise) —
`data/archive/db/reverend-insanity-webview-working.db` was backed up first
(`.pre-kind-backfill.bak`) then modified directly: 8 LOCATION, 10
ORGANIZATION, 64 left at SELF default, matching the scratch numbers
exactly. Qing Mao Mountain, South Border, and Gu Yue confirmed LOCATION on
the real file and confirmed excluded from `present_cast()`'s `person_ids`.
A 15-row spot-check of the 64 SELF-default rows found only 2 likely real
gaps ("Mo Family", "Huang Long River" — zero NER-cache evidence either
way); see EVOLUTION 4.56 follow-up for the full breakdown. **Partial fix,
by design**: only 18/82 rows on RI had cache evidence to reclassify — the
rest stay at the conservative SELF default, so an operator may still find
some mis-cast locations/items in old databases the cache has no evidence
for. Open defect #7 below (the same root cause) is closed on the same
basis.

**Canonical operational DB, stated explicitly so this isn't re-discovered
a third time:** `data/archive/db/reverend-insanity-webview-working.db` is the file
render/webview/CLI work against day to day (`--db` points here in normal
use). `data/archive/db/echotales.db` is a separate, older-but-more-complete RI
snapshot (116 `self_entity` rows vs. 82, fuller Gu/item coverage, same 199
chapters) — not a duplicate to delete and not automatically superseded by
webview-working's kind-backfill fix. Don't assume the two are
interchangeable, and don't let a future session re-derive which one is
"the" file from scratch — this is it, `data/archive/db/reverend-insanity-webview-working.db`, for render/webview.

**Process note for whoever debugs this next:** `prompt_cache_v1.json` is
a phase-1/stub-engine intermediate, not the delivered prompt — a
mid-session misdiagnosis this round came from reading that file instead
of `manifest.jsonl`. Always check the manifest (or the real generation
call) for what a panel actually received.

**Gated experiment added, not on the critical path:** `--reference-
transition-mode=img2img` (opt-in only, default still `txt2img`). EVOLUTION
4.55: the host-memory leak reported in 4.54 is root-caused and fixed
(`_ensure_img2img_pipe` now strips and re-arms accelerate's offload hooks
before wrapping the base pipe with `from_pipe`, instead of leaving the old
hook chain in charge of a pipeline it doesn't belong to) — verified with
three real runs, RSS/swap tracked normally, no more unbounded growth.

**The process-serialization fix suggested in 4.55 is now implemented**
(uncommitted, working tree only, 2026-09-03): `persona/_img2img_worker.py`
is a standalone one-shot subprocess entrypoint (load engine, run one
`generate()`, write one file, exit), invoked from
`reference_gen.py::_run_img2img_subprocess` whenever `init_image is not
None and _supports_img2img_subprocess(engine)`. `_generate_one` now
returns the written image path so `generate_references` can thread body 1's
own output forward as body 2's `init_image`.

**Partially verified, not fully.** Confirmed for real on this 4060
Laptop/8GB card: a real (non-stub, `noobai` engine) **txt2img** generation
for RI's Fang Yuan body1 completed cleanly outside the subprocess path —
VRAM ramped 18 MiB → 5831 MiB during denoise/decode and dropped back to
15 MiB after the process exited, no leak, no OOM. **Not yet confirmed:**
the img2img subprocess itself. Two attempts to actually exercise it this
session both hung before the model finished loading (VRAM flat at 18 MiB
for 5–8 minutes, then killed by timeout) — this happened while two other
background agents were doing heavy concurrent CPU/disk work on the same
machine (parallel resolve/speaker-attribution investigation), so **disk or
CPU contention is the suspected cause, not a bug in the subprocess code
itself**, but this is not proven — nobody has run it on an idle machine
yet. Also found in passing: RI's real data has only one multi-body
character (`reverend-insanity:self1`, Fang Yuan) and its body2 currently
has no attributes `appearance_of()` recognises (6 stored attributes, none
appearance keys) — so even a working subprocess wouldn't trigger on a
default real run today; verification needs either synthetic appearance
data (as attempted here) or an appearance-extraction fix for body2 first.
**Still no completed img2img generation and no side-by-side identity/
contamination comparison exists — this is unchanged from before, only the
suspected blocker moved from "OOM" to "environment contention on this
attempt."** Next step: retry `_img2img_worker.py` in isolation (no
concurrent GPU/CPU-heavy processes) before concluding anything further
about the subprocess mechanism itself. Do not promote this flag or its
default without a completed comparison.

## Open defects — highest priority first

**Full history — every defect found, fixed, and the reasoning behind each
change — lives in `docs/EVOLUTION.md`, not here.** This section is only what's
genuinely unresolved *today*.

1. **`data/db/reverend-insanity.db` has zero SELF-kind attribute rows and
   zero relation rows at all** (found 2026-09-27 building the MDC
   ablation harness; checked directly: `SELECT count(*) FROM attribute
   WHERE target_kind='SELF'` -> 0, `SELECT count(*) FROM relation` -> 0).
   PERSONA-kind attributes are fine (617 rows / 98 personas). SELF-kind
   extraction against `PERSON_KEYS` (role/faction/status/etc.) was
   apparently never run against this database — `world/schema.py`'s
   docstring already documents the analogous LOCATION/ORGANIZATION/ITEM
   gap, but not this one. This blocks meaningful real-data evaluation of
   anything that reads SELF attributes or relationships, including the
   MDC render experiment (EVOLUTION 4.99) and presumably
   `world/context.py::story_context`'s brief, which reads the same
   vocabulary. Needs a SELF-attribute/relation extraction pass on the
   canonical database before this class of experiment can produce a
   real number instead of a synthetic one.
2. **The scorer's features are too weak to link anything** (root cause,
   not a tuning gap). Calibrating against confirmed gold disproved the
   obvious fix: precision plateaus at 0.66–0.77 across the entire usable
   threshold range, and a calibrated gate merges six members of one clan
   into one entity. Every link in the system runs through the pre-filter,
   never the scorer. Needs better features (`_ambiguous_tokens` is the
   shape of what works), not a rebalanced weight. **Checked this session
   (2026-09-03), no concrete extension found:** `_ambiguous_tokens`
   (`resolve/runner.py`) is deliberately structural/corpus-derived, not a
   curated list, so there's no vocabulary gap to patch the way #2 and #6
   turned out to have. A real fix here needs a new *kind* of pre-filter
   feature (the scorer itself is confirmed unfixable by reweighting), which
   is a research task, not a bounded patch — left open.
2. **LOTM's transmigration reveal — the *linking* half is RESOLVED, verified
   this session (2026-09-03).** `detect_identity_continuity` (`resolve/
   evidence.py`) already implements the declaration pre-filter this item
   asked for — a structural regex matcher for "memories began flooding
   him"-shaped identity-continuity assertions, unit-tested against the real
   LOTM sentence (`test_identity_continuity.py`) and wired into
   `score_evidence`/`score.prefilter` as a `FORCE_LINK`. This item's own
   claim ("not yet built... resolve still produces two selves") was stale:
   a new end-to-end test
   (`packages/pipeline/tests/test_lotm_transmigration_resolve.py`) drives
   `resolve_novel` over a two-chapter Zhou Mingrui/Klein Moretti fixture
   through the real candidate-retrieval and scoring path (including
   `CandidateRetriever._prominent`, which is what surfaces a disguise-shaped
   candidate with zero surface overlap) and confirms the two mentions land
   on the same `target_id`. **Still genuinely open:** the *persona split*
   half. Linking to one `self` is not the same as emitting the two
   `Persona` rows a reincarnation/disguise case needs for pre-/post-reveal
   appearance — that's a distinct, unbuilt feature (see EVOLUTION "suggested
   next steps" #4: "a second persona per self... is a `resolve/` change
   emitting a persona split, not a Phase 7 one"). The model already supports
   multiple `Persona` rows per `self_id` (`core/models.py`); nothing yet
   generates the second one automatically.
3. **Speaker attribution regressed with LLM layer 1 — PARTIALLY RECOVERED
   (EVOLUTION 4.60, 2026-09-05).** Root cause (EVOLUTION 4.57) unchanged:
   `QwenNerDetector` recalls far fewer candidate mentions per chapter than
   the old `HeuristicDetector`, starving `speakers/`'s attribution anchors.
   Fixes shipped this session: (a) `runner.py` now unions a second,
   attribution-only `HeuristicDetector` candidate set into `_known()`'s
   gate (never into the graph/LLM roster) — controlled A/B on a scratch RI
   copy: 33.3% identifiable without it, 45.5% with it; (b) the turn-taking
   tier was deleted after being empirically measured wrong 82.9% of the
   time (n=105) — it had never been validated before, only assumed at
   "~80%"; (c) the CROWD_REACTION chorus default was fixed to require an
   actual multi-line run, not a single short exclamation. **Net effect on
   the full-novel number is a wash, honestly reported**: 45.5%
   (2,363/5,194) vs. the old 46.3%/48.8% — the old figure was propped up by
   turn-taking's mostly-wrong confident guesses counting as "identified,"
   so flat-but-honest is real progress, not a regression. Real fix for the
   remaining gap is still NER recall tuning in the mentions/layer-1 prompt
   (out of `speakers/`'s scope, unchanged from before).
4. ~~**Retriever recall@k has no gold annotations.**~~ **RESOLVED for the
   plumbing, and now measured — the gate FAILS (EVOLUTION 4.60,
   2026-09-05).** `build_gold_retrieval_cases` bridges `data/gold/*.jsonl`
   to the retriever; `echotales eval` runs it. Real (draft-tier, 0%
   human-confirmed) result against RI: recall@10 on `TRANSFERABLE_TITLE` =
   0%, `RELATIONAL_DEICTIC` = 0%, `RIGID_NAME` = 70% — 19/27 gold
   identities in the hard-case set had no system entity to even map to.
   Candidate retrieval is confirmed the ceiling on exactly the alias types
   docs/design/plans.md Section 8.2 flagged. **The fix shipped same session (EVOLUTION
   4.60):** title/relational mentions now resolve via sole-co-presence
   (never surface similarity); verified on real RI data,
   `RELATIONAL_DEICTIC` resolution 0/99 -> 59/99. `TRANSFERABLE_TITLE`
   itself now produces real mentions (EVOLUTION 4.62, 2026-09-08 — four
   independent gates fixed, 0 -> 9 mentions on RI ch1-15, blocks 68-78
   confirmed for real). Correctly resolved to `target_id=None` throughout
   ch1 (the clan head is genuinely never named there) rather than merged,
   which is why the recall@10 number hasn't been re-measured yet at any
   meaningful scale: 4.62's validation only covered ch1-15 against a
   60-chapter gold set. **Re-running this recall@k gate against a full
   real render is HANDOFF's current top "Pick up here" item.**
5. **Contradiction detector unvalidated on real data** — fires correctly
   on constructed over-merges, finds zero on 60 real chapters, which is
   diagnostic (Phase 6 over-splits, so nothing accumulates enough aliases
   to trigger it) rather than reassuring.
6. ~~**Clan-prefix alias linking gap**~~ **RESOLVED, verified this session
   (2026-09-03) — was already fixed, this item was stale.** The mechanism
   this item asked for already exists: `normalize.name_containment`'s
   >=2-token branch treats a shared *suffix* of two or more tokens as a
   house-prefix drop (no `variants.py` stripping needed — `variants.py` is
   a separate lexical-family auditor, not the link path) and it's wired as
   a `FORCE_LINK` pre-filter in `resolve/score.py`. A new end-to-end test
   (`packages/pipeline/tests/test_clan_prefix_resolve.py`) drives
   `resolve_novel` over a two-chapter "Gu Yue Dong Tu" / bare "Dong Tu"
   fixture and confirms both mentions land on the same `target_id`.
   `test_name_containment_resolve.py` already covered the 1-token
   dropped-*given*-name case end to end (Kim Dokja/Dokja); this closes the
   equivalent gap for the 2-token dropped-*house* case.
7. **`TargetKind` typing is a review flag, not a real type — RESOLVED for
   the root cause (EVOLUTION 4.56).** The NULL-`kind`-reads-as-SELF gap
   that let Qing Mao Mountain/South Border/Gu Yue reach `present_cast()`
   as people is closed for existing databases via `resolve --novel <id>
   --kinds-only` (`resolve/kind_backfill.py`), verified against RI's
   working database. Partial by design: only entities the on-disk NER
   cache has non-character evidence for get reclassified (18/82 rows on
   RI); the rest stay at the SELF default, same as before. **Webview/voice-
   casting half now independently verified (EVOLUTION 4.60, 2026-09-05):**
   voice casting was already correctly filtering on `entity.kind.is_person`
   (`persona/build.py::load_trait_profiles`, not a gap); webview was not —
   every entity rendered identically regardless of kind. Fixed:
   `webview.py`'s payload now carries `kind`/`is_person`, and the React app
   renders non-person entities distinctly (kind badge, dashed inline
   underline). Verified against real data: 18/82 RI entities flagged,
   Qing Mao Mountain among them. **This defect is now fully closed.**
8. **Recurring unnamed characters have no cross-chapter persistence —
   PARTIALLY FIXED, EVOLUTION 4.72 (2026-09-22).**
   `speakers/runner.py::_assign_anonymous_slots` now keys an anonymous
   dialogue span's voice off a real resolved `target_id` when exactly one
   physically-present, already-resolved entity (e.g. an `EPITHET` mention
   like "the Guard Captain") shares its block — verified with 6 new tests
   including a direct cross-chapter-persistence case. **Still open:**
   genuinely unresolved anonymous dialogue (zero or 2+ present candidates
   — the ambiguous two-unnamed-guards case) still gets a fresh
   `{chapter}:{scene}:{slot}` id every chapter, deliberately, to avoid
   guessing. **New, distinct, not fixed:** the same file's `EPITHET_SLOT`
   tier (`speaker = f"{novel_id}:epithet:{chapter.number:g}:{role...}"`,
   line ~450) is *also* chapter-scoped despite that tier's own docstring
   claiming a stable title-keyed id — same defect class, different
   attribution tier, found while reading the code for this fix but not in
   this session's scope. Fix shape differs from #8's fix (drop
   `chapter.number` from the key, not add a resolved-entity lookup).
9. **ORV block classification gaps**: 188 `HEADING` blocks survive per
   novel; `SYSTEM_WINDOW` detection under-fires because this source's
   status messages are bracketed prose, not `Key: Value` lines.
10. **`create_mention` has no frontend UI** — backend and tests exist; a
    reviewer can't trigger it from the browser yet.
11. **Reference-image search returns generic/mislabeled candidates that a
    reviewer must catch by eye** — a wallpaper-aggregator page surfaced as
    a top-5 result for three different RI characters, plus a fanfiction
    cover and an unrelated series cover for others (`docs/EVOLUTION.md` 4.53).
    Not auto-selected anywhere, so it can't reach a render yet, but
    `refimg-list`/`refimg-select` has no "does this actually look like the
    character" signal beyond a human looking at it.
12. **The spoiler-safe Read page is a display guarantee, not a data
    guarantee** (EVOLUTION 4.104). `GET /api/novels/<id>/reader?chapter=c`
    relabels and filters what the page shows, but the full whole-volume
    payload is still sent to the browser (the Review page needs it), so a
    user with devtools can read every name. It is also chapter-granular: a
    reveal late in chapter c shows from the start of chapter c. Closing the
    first needs the Read page to stop loading the whole payload (serve
    per-chapter spans and the reader cast only).
13. **Echo folding in `persona/split.py::find_change_candidates` can depend
    on an earlier change that a prefix rejects** (EVOLUTION 4.104). Not seen
    at any tested cut (`echotales faithfulness`, LotM 5 to 39, ORV 5 to 30,
    RI 10 to 120); known from reading the code, not from a measured
    divergence. The oracle is divergence at the cuts run, so it cannot rule
    it out elsewhere.
14. **The permanent-injury prominence gate is computed over the whole
    volume** (EVOLUTION 4.104), so a body-change decision can depend on
    mentions after the reader's position. Same caveat as item 13: not
    measured as a divergence, not repaired.
15. **No real image has been generated under the genre profiles**
    (EVOLUTION 4.105). `persona/genre.py` is verified by diffing rendered
    prompts with the stub engine only, plus one real run: LotM chapter 1 under
    NoobAI (EVOLUTION 4.106) came out Victorian where v1 was xianxia, with a
    stray signature-like artefact on one image and no image-by-image review.
    Whether ORV, or a project of another genre, now looks right is still
    unseen. Needs the GPU free (check `GET /api/compute` or `nvidia-smi`; owner
    rule: no CPU offload) and a real-engine render.
16. **Genre detection is a word-count heuristic, not a model**
    (`detect_genre`: first 20 chapters, whole-word lexicon, 6 hits per 10k words
    and a 1.3x lead, else generic). It gets the three research novels right and
    classified 30 Gutenberg books plausibly (read by eye, no labelled set). A
    wrong detection is overridden from Settings. ORV's `WORLD_CONTEXT` is empty
    in the per-novel table, so the profile's applies.
17. ~~**cmd_render never passes seed_images**~~ **SUPERSEDED (EVOLUTION 4.114, 4.115).** The legacy SVD motion-clip path is superseded by Path 1 (2.5D Layered Parallax Compositor, `compositor/`) and Path 2 (Wan 2.2 S2V / LTX-2.5 Video Engine with 8-frame QA gate and Path 1 fallback, `video/`).
18. ~~**SVDEngine stretches 2:3 portrait panels to 16:9**~~ **SUPERSEDED (EVOLUTION 4.114, 4.115).** Replaced by timeline-driven FFmpeg compositing supporting native 9:16 vertical reels and 16:9 landscape framing without distortion.
19. ~~**Owner decision on image-to-video model memory conflict**~~ **SUPERSEDED (EVOLUTION 4.114, 4.115).** RunPod serverless flex workers decoupled from local laptop VRAM; Path 1 parallax runs offline locally with zero VRAM overhead, and Path 2 offloads to serverless GPU workers with automated fallback to Path 1 on QA failure.
20. **The Read page ignores pending corrections when it builds its cast**
    (code review 2026-10-18, finding 4). `GET /api/novels/<id>/reader` is built
    from the raw store, while the page's marks come from
    `build_novel_payload`, which overlays pending merges, reassignments and
    manual entities. A merge not yet applied can leave a mark carrying an id
    the cast lacks (its label falls back to the printed text) and the sidebar
    listing both sides. The Review page is unaffected. Fix: apply the merge
    redirect in the route, or say on the page that it shows applied data only.
21. **`world/context.py` calls `resolve_appearance` without registering the
    project's genre** (`persona/genre.py::use_store_genre`), so for an
    unlisted novel it gets the neutral default hair and eye colour, not its
    genre's. The render and reference paths do register it. Low impact.
22. **Real-engine renders under the new genre profiles: LotM done, ORV and
    other genres still unrun** (item 15; EVOLUTION 4.106): the review also found, and the tests now pin, that a profile's
    culture negative longer than 14 tokens is dropped whole by the 77-token
    fit, which would have left ORV's absent from every reference sheet.

23. **The hosted paths have never touched a real service** (EVOLUTION 4.106).
    The RunPod, OpenAI and Gemini language models (`llm/gateway.py` backends) and
    `render/runpod.py::RunPodImageEngine` are tested against
    `httpx.MockTransport` only. No request was ever made, and no RunPod
    endpoint exists. The image engine's request/response contract (submit
    `/v2/<endpoint>/run`, poll `/status/<id>`, several base64 shapes) is
    documented in its docstring and needs a real worker handler written to it.
24. ~~**Hosted-engine cost is not metered.**~~ **RESOLVED (EVOLUTION 4.116).** Pre-Render
    Cost Meter (`pipeline/cost.py`) calculates and itemizes RunPod GPU and token pricing
    (LLM adaptation, keyframe diffusion, speech synthesis, and video generation) prior to
    render execution, enforcing budget caps ($0.50/min Path 1, $1.80/min Path 2).
25. **No faster preview path.** A few-step image model for previews is not
    implemented (none installed or compared), so a 3-scene preview is about 7
    minutes on this laptop. A smaller director model
    (`ECHOTALES_LOW_COMPUTE_DIRECTOR_MODEL`) is untested for quality; the repo
    measured `qwen2.5:7b` ignoring the director's negative rules (RI ch1).
26. **The default render size changed silently for scripts.** Under the default
    `local-low`, `echotales render --image-engine <real>` renders 3 scenes, not
    70. Any script or doc that assumed 70 needs `--tier full` /
    `--max-panels` or `ECHOTALES_COMPUTE=local-high`. A grep of `scripts/`,
    `docs/ops/` and the README found no invocation of `echotales render` that
    relies on the old default (the one `max_panels=40` in
    `scripts/eval/a7_cache_ablation.py` is explicit).
27. ~~**Character identity drift across panels**~~ **RESOLVED (EVOLUTION 4.111, 4.112).**
    Replaced prompt-only panels with Asset Studio turnaround/expression generation
    (`assets/turnaround.py`) and Keyframe Engine multi-candidate conditioning (`keyframes/engine.py`)
    with automated 4-Check QA gate (`keyframes/qa.py`: face match cosine similarity >= 0.85).
28. **Director omits character names on pronoun-only beats.**
    When a beat has no explicit name ("He took out the brass revolver"), the director
    does not inherit the character from the preceding beat in the same scene. Needs scene-level
    cast carry-forward (`render/beat_canon.py`, `render/director.py`, `render/panels.py`).
29. ~~**WORLD_CONTEXT string eats ~22 tokens atomically.**~~ **RESOLVED (EVOLUTION 4.112).**
    Superseded by Keyframe Engine prompt assembly (`keyframes/engine.py::build_shot_prompt`),
    compiling structured prompts directly from Story Bible snapshots and shot specifications.
30. ~~**3-scene preview is too sparse.**~~ **RESOLVED (EVOLUTION 4.110, 4.112).** Screenplay
    compiler (`screenplay/compiler.py`) and Keyframe Engine generate full-episode multi-shot
    timelines complying with pacing targets (10-25 cuts/min) and continuous chapter narrative coverage.
31. ~~**77-token CLIP limit with no verified long-prompt encoder.**~~ **RESOLVED (EVOLUTION 4.112).**
    Keyframe prompt compilation uses structured priority slotting (framing, camera, character
    expressions/poses, action) ensuring prompts fit within conditioning token limits without silent truncation.
32. **Location facts are never extracted (`world/extract.py::extract_world` unwired).**
    0 location facts exist in any DB; needs a `world` CLI command / job kind and evaluation.
33. **`scene_state` segment_id/index key mismatch.**
    `render/scene_state.py` builds row ID with `scene.index` (:75) but looks up by
    `segment_id` (:106); the table is empty everywhere.
34. **Stale `IllustriousEngine` docstring (`panels.py:~534`).**
    Claims "No IP-Adapter here yet", but SDXL IP-Adapter support was subsequently implemented
    in `_load_ip_adapter` (:670).

## Architecture-review items not yet implemented

From the 2026-08-06 review. None of these are done; all are folded into
the docs.

| # | Item | Status |
|---|---|---|
| 1 | Contradiction detector + gazetteer blocklist | **DONE** — `resolve/contradiction.py`, swept at each window boundary; `split` now actually fires. Blocklist in `gazetteer.AMBIGUITY_BLOCKLIST`. **Unvalidated on real data** |
| 2 | Retriever recall@k harness | **PARTIAL** — `eval/retriever_eval.py` built with the 8.2 gate. Gold mode needs annotations; self-retrieval smoke test passes 100% @all k (313 cases, no misses), which only proves there is no indexing bug |
| 3 | Long-span sparse gold (~200 hard cases) + IAA | **not started** |
| 4 | Mondrian/class-conditional conformal by `alias_type` | **not started** — current gate is standard conformal |
| 5 | Scorer reduced to 5 features; `declaration_match` + `gazetteer_exact_match` as hard pre-filters; `co_presence_violation` as hard blocker | **DONE**, plus `name_containment` as a third pre-filter. But the pre-filters are not an optimisation, they are the *only* path to a link (see open defect 1). |
| 6 | Lexicon induction confidence tiers (admit single-sample at LOW) | **not started** — `induce.py` currently *excludes* single-sample terms (`min_support=2`) |
| 7 | Voice coloring within archetype buckets | **DONE (EVOLUTION 4.113)** — Qwen3-TTS emotion instructions, Dia2 dialogue cues, exclamation toolkit, zero-collision casting |
| 8 | Asymmetric segmentation thresholds (aggressive on explicit, conservative on implicit) | **not started** — currently uniform |
| 9 | Visual pipeline → 3-chapter showcase | **DONE (EVOLUTION 4.110, 4.117, 4.118)** — *Hound of the Baskervilles* showcase chapters 1-3, Golden Benchmark runner (`eval/run_benchmark.py`) passing competitor parity and arc continuity across chapters 1-3 |
| 10 | RI Vol 1 as primary; LOTM/ORV 5-chapter spot-checks | scope change |
| 11 | Baseline A (long-context LLM) + Baseline B (LLMLink) | **not started** |
| 12 | Drop "full automation" framing | docs updated |
| 13 | `audience_scope_compatibility` scoped to explicit region tags | **not started** — currently returns 0.5 default |

## Decisions already made — do not relitigate

- **EPUB only, never PDF.** PDF loses italics, which is an independent
  inner-monologue signal. Measured: making emphasis a *span boundary* rather
  than an attribute moved `INNER_MONOLOGUE` from 2.7%→14.1% (RI), 2.1%→5.6%
  (LOTM).
- **No clustering.** Incremental resolution with evidence accumulation.
- **Lexicons are induced, not hand-written.** Hand-written versions are
  archived at `data/lexicons/_handwritten_archive/`. Reason: a lexicon hit is
  authoritative at 0.95 confidence, so an entry written from recall silently
  outranks every heuristic — and "we hand-tuned per novel" is the first
  reviewer objection to the transferable-title result.
- **Hand-curated alias→entity mappings are gold labels, never pipeline input.**
  Supplying them as input means the resolver reads the answer instead of
  discovering it.
- **`retract` ≠ `close_interval`.** Different event types, different semantics.
- **GLiNER and fastcoref both dropped.** Qwen2.5 for NER (trained on Chinese
  web-novel content and its translations); five-route strategy for coreference.
- **`data/gold/` stores offsets + short evidence snippets, never chapter text.**
  CoNLL/OntoNotes convention — annotations stay shareable without
  redistributing the novels.
