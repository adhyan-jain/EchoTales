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

**The other three, in the order you want them:**

| File | Answers |
|---|---|
| `EVOLUTION.md` | *Why is it built this way?* The diff between the original spec and reality — which mechanisms were replaced and what evidence replaced them, plus the permanent, append-only session log. **Read before changing a design decision, or to find out what was already tried.** |
| `architecture.md` | The model: three axes of time, self vs persona, observers |
| `details.md` | Per-file detail |
| `plans.md` | The original spec. Amended three times; the amendments win and are marked *(revised)* |

**Last updated:** 2026-09-05.

## Pick up here

**A root-cause remediation pass is in progress (EVOLUTION 4.60).**
Sections 1-5 done. Retriever recall@k gate found real gold and **FAILED**
(recall@10 on `TRANSFERABLE_TITLE`/`RELATIONAL_DEICTIC` = 0%), and Section
5 shipped the fix: title/relational mentions now resolve via sole-co-
presence, never surface similarity, verified on real RI data
(`RELATIONAL_DEICTIC` 0/99 -> 59/99). **`TRANSFERABLE_TITLE` needs a fresh
mentions-extraction run to validate for real (skipped this session to
avoid an LLM/ollama call) — do that next**, then re-run the recall@k gate.
`render/relevance.py` now checks cast/headcount/condition survival
against ground truth. Section 2's non-person-entity typing is fully
closed (panel cast, voice casting, webview). Section 3's speaker
attribution got a real anchor-recall fix (+12.2pp in controlled A/B), the
never-validated turn-taking tier removed (wrong 82.9% of the time), and
the chorus default fixed — net honest full-novel number is flat (45.5%)
since the old figure was inflated by turn-taking's wrong guesses. Section
4's scorer precision plateau reconfirmed unfixable by reweighting (never
exceeds 0.85; every real link still comes from a FORCE_LINK pre-filter).
Next: Section 6 (prompt-assembly priority mechanism), Section 7 (frontend,
after 1-6).

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
   itself still has zero real mentions in the current mention table
   (needs a fresh mentions-extraction run to actually produce them, which
   this session skipped to avoid any LLM/ollama call) — **re-run mentions
   on RI ch1 next and confirm the clan-leader/blocks-68-78 case for real**,
   then re-run this recall@k gate to see if the number moves off 0%.
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
8. **Recurring unnamed characters have no cross-chapter persistence** — a
   named character's retinue or a minor recurring character gets a fresh
   anonymous voice slot every chapter.
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
