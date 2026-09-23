# EchoTales — completion plan (pipeline repair, evidence, novelty, product)

**Written 2026-09-23.** Working plan across research publication, patent, and
product. `HANDOFF.md` stays "what do I pick up next"; `EVOLUTION.md` stays the
append-only history; `plans.md` is the original pre-build spec. This file is
the forward multi-track plan those point at.

---

## Status at time of writing

**Landed and verified** (EVOLUTION 4.74/4.75, full suite 928 passed):

- Circular gold quarantined to `data/gold/_unusable/` with a README recording
  what happened. The retracted headline: B³ P=100.0% R=94.6% F1=97.2%.
- `eval/gold.py` now enforces the contract that was previously only a comment:
  `CIRCULAR_DRAFTERS`, `CircularGoldError`, `UnattributedConfirmationError`, a
  `ReviewDepth` enum (NONE/BULK/PER_RECORD), a required `confirmed_by`, and
  `GoldSet.circular`. 9 tests in `test_gold_provenance.py`.
- MUC, B³ (textbook), CEAF-e and CoNLL F1 built in `eval/coref_score.py` as
  pure partition math with no `Store` dependency, wired into `cmd_eval`.
  14 hand-computed tests in `test_coref_metrics.py`. CEAF-e's assignment step
  is a hand-written Jonker-Volgenant (scipy is not a declared dependency),
  cross-checked against scipy on random matrices.
- `baseline_a.py`'s false "100% human-confirmed" docstring corrected; README's
  false Mondrian-calibration claim corrected; docs reconciled.

**Landed and unit-tested, real-data effect NOT measured** (EVOLUTION 4.76,
2026-09-23, full suite now 942 passed):

- Track 1 items 1–2 below. `mentions/ner.py` now sends overlapping
  `NER_WINDOW_CHARS=6_000`/`NER_WINDOW_OVERLAP=600` windows over the whole
  chapter instead of `text[:6000]`, and `item` was added to the NER label
  vocabulary. `ner_pass_fingerprint()` invalidates the on-disk NER cache once
  so stale entries from the truncated prompt aren't served under the fixed
  code. 14 new tests in `test_chapter_ner.py`.
- **Track 1 item 3 (the real ollama re-run that measures whether this
  actually moves CEAF-e/mention-recall/speaker-attribution) has NOT been
  run** — ollama was unreachable from the session that landed the fix. The
  truncation defect itself is re-measured against real data (see Context
  item 3 below); the fix's effect on real output is unknown. Treat every
  number in this file's "Status" sections as pre-fix until that re-run
  happens and is reported.

**Not started:** Tracks 2–7 below, and Track 1 item 3's measurement.

---

## Context — three things that shaped this plan

### 1. The gold set does hold ground, in part

An earlier pass of this analysis claimed the gold set was worthless. That was
correct for the `gold-auto-builder` records and **wrong for the rest**.

The `claude-sonnet-5` / `claude-opus-5` records carry real quoted source text
in `context`, and at least one note *contradicts the pipeline*: "The legendary
Gu that drives the rebirth. **An item, not a character — the pipeline currently
types it as a character.**" A label that disagrees with the system cannot have
been derived from the system. Those are genuine annotations by a different
model family (Claude) than the one under test (`qwen2.5:7b`), reading the
novel rather than the database.

**3,889 independent cross-model records exist**, all on RI: 3,457 in the main
file (60 chapters, incl. 1,641 `not_an_entity` negatives), 343 in `c1-c5`
(26 identities, 5 chapters, with negatives), 89 hard cases (51 chapters).
Cross-model annotation is a real, publishable methodology. Weaker than human
gold and must be labelled as such — but it is evidence.

Still circular: 4,422 RI records and **100% of LOTM (6,756) and ORV (4,836)**,
all `gold-auto-builder` — `SELECT`s from the pipeline's own `mention` table.
No model read any text for those.

Anything previously bulk-approved is treated as unconfirmed, per the project
owner's instruction that it will be redone properly later.

### 2. The product is not good enough, and code discipline is not an answer to that

An earlier pass wrote "the scan found no hidden rot," meaning the code is
honest about itself. That is not an answer to whether anyone would enjoy using
the output. The visual output is below the bar and this plan treats that as a
measurement problem, not an opinion.

### 3. The finding that reorders everything

`mentions/ner.py:175`:

```python
f"Passage:\n{text[:6000]}\n\n"
```

Every chapter is hard-truncated at 6,000 characters before the NER call.

| Novel | Chapters | Over 6,000 chars | Median length | **Text reaching NER** |
|---|---|---|---|---|
| RI | 199 | 199 (100%) | 11,556 | **52.4%** |
| LOTM | 40 | 40 (100%) | 11,982 | **49.2%** |
| ORV | 40 | 39 (98%) | 12,365 | **50.2%** |

**About half of every novel has never been seen by the mention layer.** Not
"low recall" — structurally invisible.

The precise mechanism: `_locate()` searches the *whole* chapter for each
surface form the model returns, so an entity named anywhere gets all its
occurrences found. The damage is confined to entities that appear **only** past
6,000 characters — those are never named, so never located. That is exactly the
observed pattern: Bai Ning Bing is gold-annotated at offsets 6746/6864/8818 of
a 13,100-char chapter 1 and has zero mentions until chapter 108, where the
system does build a rich entity for her.

This is the likely common cause of most defects chased separately for months:

- The CEAF-e gap (22 gold identities, 8 system clusters; 14 never linked to any
  entity). **Zero over-merging** in the sample — the failure is entities never
  created.
- Speaker attribution stuck at 45.5%.
- The scorer "structurally too weak" (observed probability range 0.049–0.349
  against a 0.80 threshold) — starved of candidates.
- The contradiction detector finding almost nothing — nothing accumulates.
- The gazetteer not compounding — half the aliases are never observed.

Second, independent bug in the same file: `ner.py:114-116` types
`label: "one of: character, location, organization"`. **`item` is never
offered**, though `resolve/runner.py::_KIND_BY_LABEL` already maps it. That is
the literal mechanism behind the annotator's note above.

Neither is a research problem. Both are localized patches to one file.

**Both patches landed 2026-09-23 (EVOLUTION 4.76) — see the Status section
above.** This section is left as originally written because it is the
finding that motivated the fix, not a live description of the code; the
table above is the pre-fix baseline the eventual re-run (Track 1 item 3)
needs to be compared against, and that re-run has not happened yet.

---

## Track 1 — Repair the pipeline (first; everything downstream is starved)

**Items 1–2 landed 2026-09-23 (EVOLUTION 4.76); item 3 is the open item in
this track.**

1. **DONE. Chunk the NER passage** (`mentions/ner.py`, `QwenNerDetector.detect_with_context`).
   Replace `text[:6000]` with overlapping windows over the full chapter.

   Design worked out before this plan was written, and it is simpler than it
   looks because `_locate()` already searches the full text:
   - window ≈ 6,000 chars (the proven-safe size against `num_ctx=8192`),
     overlap ≈ 600 so a name on a seam is not lost;
   - one `client.complete` call per window, same system prompt and roster;
   - for each window's result call `_locate(entities, FULL_text, confidence)` —
     no offset arithmetic is needed at all;
   - union the resulting spans, dedupe on `(start, end, text)` keeping the max
     score, sort by start.

   Cost: median chapter 11,556 chars → 3 calls instead of 1. State that
   honestly against `architecture.md` §7's call-budget rule; do not hide it.
   `mentions/chapter_ner.py:182-186` already calls `detect_with_context` and
   has its own chunking path — check it for interaction before changing.

2. **DONE. Add `item` to the NER label vocabulary** (`ner.py:114-116` + `_NER_SYSTEM`).
   Prompt/schema change only; `_KIND_BY_LABEL` (`resolve/runner.py:243-247`)
   already handles it.

3. **OPEN — not yet run. Re-run and measure the delta.** Full real re-resolve of RI against a
   scratch DB in `data/reruns/`, then `eval`.
   **Prediction recorded before the run:** CEAF-e recall rises well above
   32.1%, mentions per chapter roughly doubles, speaker-attribution
   identifiability rises from 45.5%. Report the delta whether or not it is
   favourable. If it does not move, the diagnosis is wrong and the plan changes.

4. **Only then** re-examine the scorer. `resolve/experimental_clan_features.py`
   (untracked) proposes 5 features and its own docstring says none are wired in.
   `given_name_proximity` and `role_collocation_match` key off attested
   co-occurrence and look viable; the other three need `EntityProfile` plumbing
   that does not exist. The scorer's measured weakness may be substantially a
   starvation artifact — do not touch until after the re-run.

---

## Track 2 — Evidence and metrics

5. **Re-draft LOTM and ORV gold the independent way.** Read the chapter text
   and write TOML identity lists (`reverend-insanity-c1-c5.toml` format),
   expanded by `eval/draft.py::expand_draft`. Done in-session, no API spend,
   same method and model family as the existing good RI gold. Replaces both
   circular files.
   - **Blocking prerequisite — DONE (EVOLUTION 4.79).** `expand_draft` expands
     a surface to *every* occurrence with no ambiguity check. Its docstring says this is only valid
     because ch1–5 happen to use each surface for one referent, and that a
     volume-scale range "would need to fail loudly on an ambiguous surface."
     Implement that guard first — a surface listed under two identities, or
     flagged `ambiguous`, must raise rather than silently mislabel.
     Implemented as `AmbiguousSurfaceError` + `_assert_unambiguous`, which
     runs before the store is touched (an ambiguous draft is a drafting
     error; reporting it should not require the novel to be ingested) and
     names *every* offending surface at once rather than one per round. Both
     shipped TOML drafts still expand unchanged — `c1-c5` to its recorded 343
     mentions, `c1-c60-extended` to 3,927 — so the guard is not a false
     positive on the project's one genuinely independent draft.

   **PARTIAL: LOTM chapters 1-3 of 40 drafted 2026-09-24** as
   `data/gold/lord-of-the-mysteries-c1-c3.toml` — 173 mentions, 24 identities,
   18 negatives, read from the chapter text without consulting the pipeline's
   entity list for that novel. It does **not** replace the 100%-circular
   `lord-of-the-mysteries.jsonl` yet; three chapters is a start. ORV untouched.

   **A second guard fell out of doing it, and it found a defect in the
   shipped RI drafts.** `GoldMention.key` is `(novel_id, chapter, offset)`, so
   two listed surfaces where one is a *word-boundary prefix* of the other
   ("Klein" / "Klein Moretti") both match at the same offset and one silently
   overwrites the other. A *suffix* is harmless ("Fang Yuan" inside "Gu Yue
   Fang Yuan" starts 8 chars later), which is why `_prefix_collisions` checks
   prefixes specifically. Drafting LOTM produced 5 such collisions in a file
   that otherwise expanded without a single warning — and the same check then
   found **14 in `reverend-insanity-c1-c5.toml`** (the project's one genuinely
   independent draft, EVOLUTION 4.74) and **13 in the extended file**. In
   c1-c5, "Gu Yue" is annotated as the *clan* and prefixes its own members'
   names, so every member's offset also carries an organization record; in the
   extended file bare "Gu" is a `not_entity` prefixing "Gu Yue", making a real
   entity's position also a negative. **Those two files are left unedited on
   purpose** — changing what an annotator asserted is the owner's call — and
   pinned by an expect-to-raise test so the finding cannot be lost.

6. **OPEN (needs a second model family, i.e. network/API access).
   Multi-model agreement as the honest substitute for human IAA.** Draft a
   shared subset with a second, non-Claude model family and report agreement
   (the Cohen's κ statistic, between annotators that are models). Costs no
   human time. It is *not* IAA and the paper must say so in those words.

7. **DONE (built; the annotation pass itself is the owner's to run).
   Blind human-verification tool.** Extend `review.py::write_jsonl` (its docstring already says "for
   scripting or seeding annotation"); show surface + source window only, never
   the system's `target_id`; write `confirmed_by` + `ReviewDepth.PER_RECORD`
   into the gold format the guard already enforces.

   Built as `eval/blind_review.py` + `echotales annotate`. A task carries the
   surface and a ±240-char source window and nothing else; `FORBIDDEN_TASK_FIELDS`
   makes "no system field leaks" an enforced property rather than a habit, and
   a pre-filled answer is refused too (a suggested answer anchors just as the
   system's would). Tasks are shuffled by an explicit seed and `--sample` is
   applied *after* shuffling — early chapters are the easy case and annotating
   the first N mentions would overstate agreement. A blank task is **skipped,
   never defaulted**: a blank is "nobody looked", and counting it as agreement
   is precisely 4.74's failure. Round-tripped end to end against RI.

8. **Wire the orphaned metrics.** `llm/router.py::report()` returns
   `escalation_rate` and has zero callers — surface it in `cmd_eval`. The
   `llm_call` table already persists every call.

9. **DONE. Held-out conformal coverage.** `eval/calibrate.py::calibrate_from_gold`
   calibrates and reports on the identical sample set, so the (1−α) guarantee
   is never validated out-of-sample. Split by chapter range (not randomly —
   knowledge time only moves forward), calibrate on the earlier range, report
   empirical coverage on the later.

10. **DONE. Statistical rigor + persistence.** Example-level paired bootstrap with
    95% CIs on every reported number. Persist under `data/eval/results/<run_id>/`
    by **reusing `core/pipeline_run.py`** — `ensure_pipeline_run`/`stage`/
    `record_artifact` are fully built with zero callers today. Add a `--seed`
    global. Add `scripts/reproduce_results.sh`.

    All four built: `eval/stats.py` (percentile bootstrap CIs + paired
    bootstrap with an explicitly-labelled bootstrap p-value, not a t-test),
    `eval/persist.py` (writes `data/eval/results/<run_id>/metrics.json` with
    commit — **carrying a `-dirty` marker, since this repo's numbers have come
    from an uncommitted tree for most of its life** — database, gold path,
    seed, platform; registered as a `StageArtifact` through the previously
    caller-less `pipeline_run.py`), a global `--seed`, and
    `scripts/reproduce_results.sh`.

    **A bug this caught in its first run, worth recording:** the CI was first
    computed by keying gold `(chapter, offset)` against `mention.offset`
    directly, and reported **0.4%**. Gold offsets are chapter-absolute and
    `mention.offset` is block-local — the exact defect EVOLUTION 4.75
    documents in `score_b3`. Rewired through `coref_score._system_partition`
    (the single existing translation) it reads **98.6% [98.3%, 98.9%],
    n=6,238**, consistent with MUC/B³ recall. Writing that lookup a third
    time is how the original bug happened.

---

## Track 3 — Ablations and the gazetteer compounding curve

**All of Track 3 landed 2026-09-23 (EVOLUTION 4.77 for items 11–12, 4.78 for
13–15), verified against real RI data.**

11. **DONE. Fix the resolution-provenance bug that blocks the compounding claim.**
    `resolve/runner.py:481,516` hardcodes `ResolutionMethod.SCORED` at every
    `_apply_link` call site **even when a prefilter force-linked the mention**.
    `ConformalGate.decide` already computes the distinction and folds it into a
    `rationale` string that is then discarded (`ResolutionOutcome` is never
    persisted). Thread the `PrefilterVerdict` through `decide` →
    `resolve_group` → `_apply_link`, and add `rationale` to
    `resolution_event.payload` (already a free-form JSON column — no schema
    change). `ResolveReport.by_method` then becomes the real "% resolved by
    gazetteer vs declaration vs scorer vs DEFER" for free.

12. **DONE. The compounding curve.** The mention-detection half already exists and is
    only printed, never stored: `MentionReport.gazetteer_hit_rate_by_window`
    (`mentions/runner.py:63-65`, populated at `392-426`). Persist it, and add
    the resolver half from item 11. This is the project's headline "the
    gazetteer compounds" claim as a measured curve rather than an assertion —
    and the Track 1 fix should visibly change its shape.

    **First measurement, RI, window size 40 — it compounds, then plateaus:**
    `w0=81%(n=145) w1=93%(n=166) w2=89%(n=201) w3=96%(n=223) w4=91%(n=227)`.
    A real rise from the first window, not a monotone climb. Reported with the
    per-window link count on purpose: a rate without its denominator invites
    reading an early window of four links at 100% as evidence. Both halves
    persist to `data/eval/compounding/<novel>.json`, each stage writing its own
    half so neither clobbers the other. **Caveat: this curve was measured on
    the pre-Track-1 mentions** (the shipped DB's), so it is the baseline the
    post-NER-fix curve must be compared against, not a final number.

13. **DONE. Build the evidence cache the ablation story assumes.** The docs claim
    ablations "cost no additional LLM passes because they re-score cached
    evidence vectors." **That cache does not exist** — `EvidenceVector` lives
    only in memory during `resolve_group`. Add a `scoring_evidence` table
    populated via the same `score_evidence` monkeypatch pattern
    `eval/calibrate.py::collect_samples` already uses. Without it every
    ablation is a full re-resolve.

    Built as `scoring_evidence` (table) + `eval/evidence_cache.py`
    (`capture_evidence` context manager, `load_evidence`), opt-in via
    `resolve --capture-evidence [--evidence-run-tag TAG]`. **Real capture: RI
    = 10,058 (mention, candidate) pairs.** Opt-in rather than always-on
    because a production resolve should not pay for an evaluation artifact,
    and the patch is restored in a `finally` so a run that dies mid-volume
    does not leave a traced `score_evidence` installed process-wide.

14. **DONE. Make the pre-filters ablatable.** `ScoringModel.ablate` can only zero the
    5 scored features. The hard pre-filters — including `gazetteer_exact_match`,
    which carries essentially every real link — are outside the weighted model
    and cannot be ablated at all. Add a `disabled_prefilters` parameter to
    `prefilter()`. Without this the "no gazetteer compounding" ablation, the
    paper's central claim, is inexpressible.

    Done via `PREFILTER_GATES` + `prefilter(..., disabled_prefilters=...)`,
    threaded through `ConformalGate.disabled_prefilters`. A disabled gate
    *falls through* to the next one rather than erasing the evidence, which is
    the counterfactual an ablation actually wants — and it matters: disabling
    the gazetteer gate raises `NAME_CONTAINMENT` force-links from 2 to 74,
    because the gazetteer had been short-circuiting before containment could
    fire. Item 11's finding makes this item load-bearing rather than
    completist: zeroing the five scored weights would change nothing, because
    nothing reaches them.

15. **DONE. `echotales ablate` subcommand** (`cli.py` + `commands.py::_DISPATCH`,
    following `cmd_eval`'s shape). Conditions: no temporal scoping, no alias
    typing, no Self/Persona split, no truth status, no gazetteer compounding.

    Built as `eval/ablate.py` + `cmd_ablate`. **Scope correction, stated
    rather than quietly narrowed:** of the five conditions named above only
    *no temporal scoping* and *no gazetteer compounding* are answerable by
    re-scoring cached evidence. *No alias typing* is decided in the mentions
    stage, upstream of any evidence vector; *no Self/Persona split* and *no
    truth status* change which entities exist and what `state_of` returns,
    neither of which the resolver consulted. Those three are declared in
    `REQUIRES_RERESOLVE` and **printed on every `ablate` run**, so their
    absence reads as "the cache cannot answer this" rather than "this axis did
    not matter". Four extra cache-answerable conditions were added
    (`no-declaration`, `no-name-containment`, `no-relational-copresence`,
    `no-prefilters-at-all`).

    **First real run (RI, 10,058 pairs) — and it independently confirms item
    11 from a different direction.** `scorer-would-link = 0` under *every*
    condition, including `no-prefilters-at-all` where all 10,058 pairs reach
    the scorer. Measured probability distribution over those pairs:
    `min=0.047 p50=0.076 p90=0.208 p99=0.312 max=0.527` against a 0.80
    threshold. The scorer is not weakly calibrated — **its maximum output over
    every real pair in the novel is 0.53, so linking at 0.80 is arithmetically
    impossible.** (`gate.py`'s calibration comment cites a 0.049–0.349 range
    from a smaller sample; the full-volume range is 0.047–0.527, still wholly
    below the threshold.) Second finding: `no-temporal-scoping` changes
    nothing at all — `blocked` stays at 2,051, all of which come from
    `co_presence_violation`, so the temporal blocker fires on **zero** pairs.

---

## Track 4 — Novelty: make the observer axis real

The most distinctive mechanism in the codebase, and currently **unexercised on
real data**. Verified against `data/webview-working/reverend-insanity.db`:
every row in `self_persona_binding` (83), `alias_binding` (9,469) and
`attribute` (536) is stamped `READER`; the `observation` table is **empty**;
there is no `add_observation` in `store.py`; and no generation path accepts an
observer. `architecture.md`'s headline acceptance test —
`state_of(observer=WU_CLAN)` differing from `observer=READER` — cannot return
anything different today.

Schema, model and query logic all exist. The writer and the wiring do not.

**Items 16–17 landed 2026-09-23 (EVOLUTION 4.80). The acceptance test passes
on real data for the first time. Item 18 (the two figures) is open — it needs
a real render, which needs a GPU.**

16. **DONE. Populate observations.** Add `Store.add_observation`, and a detector that
    records who witnessed a reveal — reusing `present_cast()`
    (`anaphora/local.py:376`) for scene co-presence and `detect_reveals.py`,
    which already computes reveal events and stamps them `OBSERVER_READER`
    unconditionally (`detect_reveals.py:254`).

    Built as `Store.add_observation`/`add_observations`/`observations_for`,
    `readset.observable_ref` (a stable per-fact id, derived from the fact
    rather than a row id so a re-resolve does not reset every character's
    knowledge), `anaphora/local.py::present_cast_ids`, and
    `resolve/detect_observations.py` + `echotales observations`.
    `state.py::_visible_to_observer` now consults observations, which is what
    makes a character observer able to see anything at all.

    **Granularity corrected by measurement, not assumption.** The first
    implementation used the reveal's own block, matching
    `reveal_target_for_block`. It produced **zero** observations from all
    three RI reveals — each reveal block held exactly one person mention, the
    revealed character, who is excluded by definition. Block granularity is
    right for panel casting (who is in this frame) and wrong for witnessing
    (who is in the room). Widened to the enclosing `NarrativeSegment`:
    **3 reveals, 3 with a co-present witness, 13 observations across 11
    observers.**

17. **DONE. Thread `--observer` through query and render.** `cli.py:121` already has
    it on `query state-of`; extend to `render`, and pass into
    `plan_builder.py::build_render_plan` / `panels.py::character_looks`, which
    already take a `StateResolver`.

    Done by putting the observer on the `StateResolver`
    (`default_observer=`) rather than threading `observer_id` through each
    call. An observer is a property of the viewing context, and a per-call
    parameter would have to be passed identically through every `state_of`
    site below the CLI — any one missed would silently fall back to READER
    and reintroduce exactly the spoiler the axis exists to prevent.
    `render --observer` and `observations` are both on the CLI.

    **`architecture.md`'s headline acceptance test, run for real (RI,
    Bai Ning Bing, chapter 200):** READER sees 2 aliases
    (`Bai Ning Bing`, `Bai Ningbing`); a witness present at the reveal sees
    **1** — a strict subset; a non-witness sees **0**. Reproducible from the
    CLI with `query state-of --observer <id>`.

18. **OPEN (needs a GPU render). Two deliverables no other system can produce:**
    - the same scene rendered as the Wu clan believes it vs as the reader knows
      it;
    - the same scene rendered as believed at chapter N vs after the retraction.

    These exercise the observer axis and `retract`-vs-`close_interval`
    simultaneously, and they are the paper's central figure.

---

## Track 5 — Product quality, measured rather than argued

Nobody knows how good this can get, because **no pixel has ever been scored**.
`render/relevance.py` scores the *prompt* against the source text; `CLIPModel`
is never used for image embedding anywhere (only `CLIPTokenizer`, for
counting). `QATier` and `VisualQAResult` are fully typed in
`render/contract.py` and never instantiated. There is no `render/bench/`.

19. **Build CLIPScore pixel QA** into `render/bench/`, filling the existing
    `VisualQAResult`/`QATier` types. `transformers` and `torch` are already
    installed — no new dependencies, no cloud spend. Metrics:
    image-vs-delivered-prompt agreement, image-vs-source-beat agreement, and
    CLIP-I identity consistency across panels of one persona.

20. **Score the 1,183 panels already on disk, retrospectively across v1→v54.**
    Converts "is it getting better?" into a curve, and is the only way to know
    whether 44 versions of work moved anything.

21. **Record what truncation discards.** The render manifest stores only the
    final prompt (`manifest.jsonl` keys: `block_index`, `chapter`,
    `conditioned_on`, `image_path`, `negative_prompt`, `prompt`) — no record of
    what was dropped. Add `assembled_tokens` / `delivered_tokens` /
    `dropped_parts` to the manifest and `RenderArtifact`.

22. **Optimise within the 77-token budget, as a research contribution.**
    Measured: the pipeline assembles a median 154 tokens per panel against a
    usable 75 (`persona/prompt.py:614-619`), and v54's *delivered* prompts are
    median 26 words across 87 panels. Roughly two-thirds of what the graph
    knows never reaches the image, and tier-3 (setting, lighting) is dropped
    first on every panel. Performing well under a hard constraint is exactly
    the result that generalises when the constraint lifts. Concretely: measure
    which tiers survive, A/B compression strategies against the item-19
    harness, report the quality-vs-budget curve. Nobody has published that for
    a knowledge-graph-conditioned generation pipeline.

23. **Stage-wise error attribution.** With 19–22 in place, attribute
    final-panel wrongness across NER recall → resolution → direction → budget
    truncation → checkpoint. Both the product roadmap and a genuinely novel
    contribution; no narrative→image pipeline reports it.

24. **Deferred until after exams:** the T5-encoder direction (FLUX/SD3 have no
    77-token limit — that, not "bigger model", is the real architectural
    argument) and the ~$5–10 RunPod bake-off. Tradeoffs found in the audit:
    hosted engines **ignore reference images entirely**, Gemini refuses this
    novel's gore outright, OpenRouter's free tier stops at 2 images.

25. **Close Phase 1's own exit criterion.** `cache_key.py`/`plan_builder.py`
    *are* wired (EVOLUTION 4.72 — `docs/VISUAL_RENDERING.md` is stale on this)
    but were only ever exercised in stub mode. Run one real render, change the
    seed, confirm the cache invalidates instead of serving a stale image.

---

## Track 6 — Patent disclosure (VIT files; they need the document)

26. **DONE (draft written; the LINK-KG verification in item 27 blocks
    sending it).** Write `docs/IP/invention_disclosure.md` — **never committed publicly** —
    covering six mechanisms: Self/Persona split with concurrent
    temporally-scoped bindings; observer-scoped knowledge time; `retract` vs
    `close_interval`; fuzzy-interval partial-order story time;
    graph-conditioned panel rendering with a state-derived cache key; and
    **observer-conditioned generation** (Track 4), the strongest and newest.

    Written 2026-09-24. `docs/IP/` added to `.gitignore` (line 160) and
    verified uncommittable with `git check-ignore` — the repo is public, and
    publishing a disclosure is itself a disclosure. Each mechanism separates
    *verified* from *asserted*, which matters here: §2.5 and the generation
    half of §2.6 are **stub-mode only and have never run against a real image
    engine**, and the document says so in the place counsel would look rather
    than in a footnote. §4 lists what is explicitly NOT claimed (no Mondrian
    calibration, no validated accuracy number, no working scorer, no
    production-validated render).

27. **PARTIAL — table written, LINK-KG verification still OPEN (needs
    network).** Prior-art table: LINK-KG (arXiv:2510.26486), LlmLink (COLING 2025),
    BookNLP, LitBank, standard bitemporal databases, temporal KG literature.
    **Verify the four LINK-KG claims in `plans.md:800-806` against the actual
    paper** — they are the sharpest material available and are currently
    asserted, not checked.

28. **DONE.** Every legal conclusion as an **"ASSERT — VERIFY WITH COUNSEL"**
    callout.
    Claim only what is implemented: no Mondrian calibration (not built,
    ~100–150 lines away, and blocked on confirmed gold regardless).

    Context: the repo is public (first commit 2026-08-07). Making it private
    does not undo disclosure. Filing — not silence — is what unlocks publishing
    and demoing. VIT handles the filing; they need this document.

---

## Track 7 — Documentation

29. Fold every recommendation above into the repo's own docs, in each file's
    voice: `README.md` (scope, known limitations), `architecture.md` (observer
    axis becoming real; NER windowing), `plans.md` (evaluation methodology:
    cross-model annotation, multi-model agreement), `details.md` (per-file),
    `docs/STATUS.md` (component matrix rows), `docs/VISUAL_RENDERING.md` (stale
    Phase-1 wiring claim; the new bench), `HANDOFF.md` (pick-up-here), and a new
    dated `EVOLUTION.md` section per landed change. **`EVOLUTION.md` is
    append-only** — never edit it to fix a stale claim.

30. Invoke the `docs-sync` subagent after each substantial track lands, per
    `CLAUDE.md`.

---

## Sequencing

| Order | Work | Why here |
|---|---|---|
| 1 | Track 1 items 1–2 (NER chunking + `item` label) | Everything downstream is starved until this lands |
| 2 | Track 1 item 3 — real re-run + measured delta | Confirms or refutes the diagnosis before more is built on it |
| 3 | Track 3 items 11–12 (provenance + compounding curve) | Cheap, and the re-run is when the curve becomes interesting |
| 4 | Track 5 items 19–21 (CLIPScore bench, retrospective scoring) | Independent; answers the product question with data |
| 5 | Track 2 item 5 (LOTM/ORV re-draft) | Long, incremental, interleaves across sessions |
| 6 | Track 4 (observer axis) | The novelty payload; wants a repaired pipeline under it |
| 7 | Track 3 items 13–15 (evidence cache, ablations) | Needs the re-run's data to be worth running |
| 8 | Track 2 items 6–10 (agreement, coverage, CIs, persistence) | Final evidence layer |
| 9 | Track 5 items 22–23, Track 6, Track 7 | Contribution framing, once numbers exist |
| — | Track 2 item 7 (blind annotation tool) | Built early, **run by the owner after exams** |
| — | Track 5 item 24 (T5 / RunPod) | **After exams** |

---

## Verification

- **Track 1:** `echotales --db data/reruns/<scratch>.db run --novel reverend-insanity`
  end to end on real ollama, then `eval`. Compare against the pre-fix numbers in
  EVOLUTION 4.75 (CEAF-e P=88.3 R=32.1 F1=47.1, MUC 99.4, B³ 99.3). Check
  specifically that Bai Ning Bing now has chapter-1 mentions near offsets
  6746/6864/8818.
- **Track 2:** `expand_draft` raises on a deliberately ambiguous TOML surface;
  re-drafted LOTM/ORV show `circular-drafted = 0` under `GoldSet.coverage()`.
- **Track 3:** `ResolveReport.by_method` shows a non-trivial split (today it is
  100% `SCORED` by construction, which is a lie); `echotales ablate` produces
  one row per condition with 95% CIs.
- **Track 4:** on real data, `query state-of --observer <character>` returns a
  strictly smaller fact set than `--observer READER` for a concealed identity,
  and two renders of one scene under different observers differ in the cast
  depicted. This is `architecture.md`'s own acceptance test, run for real for
  the first time.
- **Track 5:** the retrospective CLIPScore curve over v1→v54 is produced and
  inspected; a real render with a changed seed yields a different image.
- **Throughout:** full suite green (`928 passed` at time of writing), ruff and
  mypy clean on files touched, pre-existing findings left alone.
