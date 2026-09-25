# EchoTales — Handoff

**Purpose: current open tasks only, ephemeral.** This file answers "what do
I work on next" and nothing else — it should be readable in under a
minute. The history of how the system got here (every fix, every
completed defect, the reasoning behind each change) lives in
`EVOLUTION.md`, not here. A render-version number (`v44`, `v51`, `v54`,
...) is tracked in the relevant novel's `panels/ch<N>/VERSIONS.md`, never
here and never in `EVOLUTION.md` — a HANDOFF/EVOLUTION section number
(like "4.52") is not a render version, and the two must never be
conflated.

**The others, in the order you want them:**

| File | Answers |
|---|---|
| `EVOLUTION.md` | *Why is it built this way?* The diff between the original spec and reality — which mechanisms were replaced and what evidence replaced them, plus the permanent, append-only session log. **Read before changing a design decision, or to find out what was already tried.** |
| `architecture.md` | The model: three axes of time, self vs persona, observers |
| `details.md` | Per-file detail |
| `plans.md` | The original spec. Amended three times; the amendments win and are marked *(revised)* |
| `docs/COMPLETION_PLAN.md` | *What to build next and why*, across research/patent/product. The forward multi-track plan (2026-09-23), including the `ner.py` 6,000-char truncation finding that reorders the work. **Read this before starting a new track.** |

**Last updated:** 2026-09-24.

## Pick up here — 2026-09-25 (finalization pass, EVOLUTION 4.90)

- **Canonical database:** `data/reverend-insanity.db`, sha256 `42107645…`. Every script defaults to it (`docs/CANONICAL_RUN.md`). Per-claim status is in `docs/FINAL_EVIDENCE_TABLE.md`.
- **Next research work, in order:**
  1. Transmigration: LOTM's Zhou Mingrui and Klein are resolved as two Selves.
  2. Hard-case detection: address terms 16, relational 15, definite titles 11 (`data/eval/hardcase_taxonomy.json`).
  3. Attribution tier 4: 12 right / 16 wrong, and unstable across runs.
- **Do not re-run** anything that the canonical database already measured; `scripts/reproduce_results.sh` regenerates every artifact in about 10 minutes.

## Earlier — 2026-09-25: completion pass landed; read `docs/FINAL_ECHOTALES_READINESS.md` first

That file is the single status record. The short version:

- **Verified on real data:** observer-conditioned generation on a real image
  engine; observer and knowledge-time query axes; read-set invalidation;
  sequential Self/Persona; both baselines; retriever recall@K; scorer
  diagnosis. Details in EVOLUTION 4.85.
- **The scorer cannot link by arithmetic** (max p = 0.550 vs 0.80) because
  three of its five weighted features are inert on this corpus. Ranking is 94%
  correct. Do not retune weights; see `docs/SCORER_DIAGNOSIS.md` Section 6.
- **Hard cases are lost at mention detection** — the next real research work.
- **Run-order trap:** `resolve` deletes persona bindings. Never run it after
  `run` without rebuilding personas.
- **EARS voice bank** rendered RI ch1 (`data/audio-ears-native/`, EVOLUTION
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

**Session of 2026-09-23/24.** `docs/COMPLETION_PLAN.md` carries DONE markers
per item; `EVOLUTION.md` 4.76-4.83 has the detail. Suite **1,038 passed**
(was 928). **Read this list of blocked items before starting anything.**

### Blocked, in priority order

1. **Track 1 item 3 — the measuring re-run. DONE 2026-09-24.** Full account
   in `docs/NER_WINDOWING_RESULT.md`. The blocker was a **misdiagnosis**:
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

3. **Track 6 item 27 — verify the four LINK-KG claims** (`plans.md:800-806`)
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
- **4.80 observer axis** — `architecture.md`'s headline acceptance test
  **passes on real data for the first time**: READER 2 aliases, a witness 1
  (strict subset), a non-witness 0.
- **4.81 blind annotation / held-out coverage / bootstrap CIs / traceable
  results** — `eval` now prints intervals and persists to
  `data/eval/results/<run_id>/` with a `-dirty` commit marker.
- **4.82 invention disclosure** — `docs/IP/invention_disclosure.md`, gitignored.

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
no true one was produced.** Full account in `EVOLUTION.md` 4.74 (do not
re-derive it from this summary). The confirmed-tier B³ result this file
and `docs/STATUS.md` used to cite (precision=100.0%, recall=94.6%,
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

See `docs/STATUS.md`'s "Stale claims found this pass" #5 and its "Gold
datasets"/"Evaluation harness"/"Baselines" rows for the corrected
component-status detail.

## Pick up here — Product Orchestration track (backend done, no frontend yet)

**Status: backend contracts complete and tested; explicitly no frontend
work done, per the approved plan's scope limit.** Implemented per
`~/.claude/plans/cheerful-orbiting-squirrel.md`. This closes
`docs/STATUS.md`'s "Jobs/progress", "File upload", "Output library" rows
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

See `EVOLUTION.md` 4.73 for the full design rationale (reused vs. new
mechanisms) and `docs/STATUS.md`'s "Backend API"/"Jobs/progress"/"File
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
  against `data/webview-working/reverend-insanity.db` (refused to wipe,
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

**Status, verified vs. not:**
- `Login.js` / `NewProject.js` / `CharacterDashboard.js` — **done**, `Section7Smoke.test.js` passing (8/8).
- `create_mention` frontend UI — **done**, wired via `+ mention` action button in edit mode (`App.js`, `ScriptView.js`, `ScriptLine.js`).
- Gold QA Datasets — **full-volume draft coverage, zero records confirmed anywhere (EVOLUTION 4.74, 2026-09-23 — supersedes this bullet's earlier claim that RI ch1-60 was human-reviewed)**. All three novels now cover their entire sources.toml volume: `reverend-insanity` 198/199 ch (ch164 has zero resolved character mentions at all -- **root-caused as far as possible without a full re-run, EVOLUTION 4.66: not a current-code defect** -- standalone replay of ch164's real content and its real cached NER output produces 39 valid mentions on today's code, so the canonical DB most likely just predates the 4.62 alias-type fix and needs a re-resolve; not fully confirmed, check ch164 again after the full RI re-resolve in the "start here now" section above), `lord-of-the-mysteries` 213/213 ch, `omniscient-readers-viewpoint` 186/188 ch (ch14/121 genuinely feature only side characters outside the 5 tracked leads). **`reverend-insanity`'s original ch1-60 file (6,952 records) was never human-reviewed at all** — it was drafted by `eval/generate_gold.py::_extract_gold_from_db` from the pipeline's own `mention` table and flipped to `confirmed: true` on 2026-08-12 without an independent pass; it is circular (the system scored against itself) and is now quarantined at `data/gold/_unusable/reverend-insanity-c1-c50.jsonl`. Every remaining record everywhere, including all of LOTM/ORV, is `confirmed: false` -- drafts to audit, not ground truth; the two files that are genuinely independent of pipeline output (`reverend-insanity-c1-c5.jsonl`, `reverend-insanity-hardcases.jsonl`) are unconfirmed but not circular, and are the actual starting point for a real human pass. `generate_gold.py`'s `identity_map`s had drifted wrong (self-ids are per-resolve-run, not stable) and were re-derived by looking up each character's current target_id directly in the DB being used -- see the module's own docstring before rebuilding these again after any resolve rerun. LOTM's resolver also leaves bare given/family names (`"Klein"`, `"Moretti"`) as separate self-ids from the full-name id for every tracked character in `data/lotm-vol1.db` -- folded into identity_map correctly for gold-labeling, but the underlying non-merge is a resolver characteristic worth root-causing separately.
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
(`data/reruns/validation-4.62.db`, scratch, deleted after use):
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
(`data/reruns/smoke-4.64-ch1-3.db`) with real ollama `qwen2.5:7b`
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
   `data/reruns/ollama-eval-reverend-insanity.db` (produced as a side
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
   check `data/reruns/` and `git status` for an existing uncommitted
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
`data/webview-working/reverend-insanity.db` was backed up first
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
a third time:** `data/webview-working/reverend-insanity.db` is the file
render/webview/CLI work against day to day (`--db` points here in normal
use). `data/echotales.db` is a separate, older-but-more-complete RI
snapshot (116 `self_entity` rows vs. 82, fuller Gu/item coverage, same 199
chapters) — not a duplicate to delete and not automatically superseded by
webview-working's kind-backfill fix. Don't assume the two are
interchangeable, and don't let a future session re-derive which one is
"the" file from scratch — this is it, `data/webview-working/reverend-insanity.db`, for render/webview.

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
change — lives in `EVOLUTION.md`, not here.** This section is only what's
genuinely unresolved *today*.

1. **The scorer's features are too weak to link anything** (root cause,
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
   plans.md Section 8.2 flagged. **The fix shipped same session (EVOLUTION
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
    cover and an unrelated series cover for others (`EVOLUTION.md` 4.53).
    Not auto-selected anywhere, so it can't reach a render yet, but
    `refimg-list`/`refimg-select` has no "does this actually look like the
    character" signal beyond a human looking at it.

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
| 7 | Voice coloring within archetype buckets | not started (voice pipeline unbuilt) |
| 8 | Asymmetric segmentation thresholds (aggressive on explicit, conservative on implicit) | **not started** — currently uniform |
| 9 | Visual pipeline → 3-chapter showcase | scope change, pipeline unbuilt |
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
