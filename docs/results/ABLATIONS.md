# Ablations: observer (A1, A2), cache (A7), disclosure (MDC), observer-contrast validation

> Merged on 2026-10-22 from 5 separate documents to keep the docs tree small. Each section below is one original file, text unchanged; its old path is in the section heading. The originals are in git history.

---

<!-- merged-from: docs/results/A1_OBSERVER_ABLATION.md -->
## Source: `docs/results/A1_OBSERVER_ABLATION.md`

# A1 — observer state collapsed to READER

**2026-09-26.** Script `scripts/eval/observer_ablation.py`; result `data/eval/observer_ablation.json`; canonical database `data/db/reverend-insanity.db`.

## Pre-registered rules (fixed in the script's docstring before any number was computed)

- **Reveal events:** every (fact, learned chapter r) in the `observation` table. That gives **3 events over 2 facts**: "Bai Ning Bing" at ch166 and ch197, and "Gu Yue Yao Ji" at ch178.
- **Observers:** all witnesses of the fact, plus the 20 most-mentioned Selves that are neither witnesses nor the target.
- **Positions:** r−1, r, 200. That is **228 queries**, of which 34 are should-know.
- **Should-know:** the observer has an observation of the fact dated at or before the position. This is the system's own record; whether the record is right is a separate question for human review (`HUMAN_REVIEW_PROTOCOL.md`).
- **Leak:** the revealed alias is returned although the observer should not know it.
- **Under-exposure:** the alias is not returned although the observer should know it.
- **Generation leak:** the render plan built for that observer, with the target in the cast, draws the target's persona although the observer should not know it.
- **Condition A1:** the same query answered as `READER`, i.e. the "who" axis removed.

## Result

| | Leak | Under-exposure | Wrong-identity exposure | Generation leak |
|---|---:|---:|---:|---:|
| **FULL** | **0** | 9 | 0 | **0** |
| **A1 (observer → READER)** | **194** | 0 | 0 | **194** |
| Difference | +194 | −9 | 0 | +194 |

**By observer class:**
- Non-witnesses: FULL 0 leaks, A1 **180 / 180** queries.
- Witnesses: FULL 0, A1 14. The 14 are witnesses asking before their reveal.

**By reveal event (leaks, FULL → A1):**
- Bai Ning Bing @166: 0 → 65
- Bai Ning Bing @197: 0 → 61
- Gu Yue Yao Ji @178: 0 → 68

## Reading it honestly

- **FULL leaks 0 by construction**, because "leak" is defined against the system's own observation records. What A1 measures is causal: **removing the observer axis changes the returned identity in 194 of 228 queries**, and the rendered cast in the same 194.
- **The 9 FULL under-exposures are a mismatch between the rule and the system's granularity, not a system error.** The ch178 and ch197 reveals sit at block 7 of their chapters. Asked from the start of the reveal chapter, the witness correctly does not know yet. The pre-registered rule compares chapters only, so it counts them. The result is left as measured and not re-scored.
- **At the generation level, FULL also draws no character for a witness who should know** (0 of 34). Persona bindings are READER-scoped, so every character observer resolves no body. A1's 34 "drawn when known" come only from answering as the reader. **Observer-conditioned rendering is therefore demonstrated as reader vs non-reader, not witness vs non-witness.**
- The scale is small: 3 events, 2 facts. The observer axis is thinly populated on this corpus.

---

<!-- merged-from: docs/results/A2_OBSERVER_ABLATION.md -->
## Source: `docs/results/A2_OBSERVER_ABLATION.md`

# A2 — knowledge time removed, observer kept

**2026-09-26.** Same script, rules and 228 queries as A1 (`docs/results/A1_OBSERVER_ABLATION.md`).

A1 removes *who* is asking. A2 keeps the observer filter and removes *when* they learned. Observations are admitted regardless of their learned date (`knowledge_pos` = +∞), while story position and temporal validity are retained. This isolates the knowledge-time axis inside the observer model.

Mapping to the brief: the requested "story position + temporal state, but no observer-specific filtering" is A1 at the state level (character observers answered from reader-scoped facts at the same position). A2 is the complementary ablation, which the observer model also needs.

## Result

| | Leak | Under-exposure | Generation leak |
|---|---:|---:|---:|
| **FULL** | **0** | 9 | 0 |
| **A2 (knowledge time removed)** | **14** | 0 | 0 |

- Every A2 leak is a **witness asking from before their own reveal**: Bai Ning Bing @166: 5; @197: 1; Gu Yue Yao Ji @178: 8.
- Non-witnesses are unaffected (0): without an observation, removing its date changes nothing.
- The 9 FULL under-exposures disappear under A2 for the same reason they appeared (see A1): the mid-chapter reveal position stops mattering.
- **Generation leak stays 0** because character observers never resolve a persona (READER-scoped bindings). The knowledge-time axis therefore changes names, not drawn identity, on this corpus.

## Conclusion

Both axes are causally active at the state level:
- removing the observer changes 194 of 228 answers (A1);
- removing knowledge time changes 14 (A2), exactly the pre-reveal witness queries.

At the generation level only the reader-vs-character distinction shows (A1). Witness-level rendering is blocked by the READER-scoped persona bindings, which is the documented limitation.

---

<!-- merged-from: docs/results/A7_CACHE_ABLATION.md -->
## Source: `docs/results/A7_CACHE_ABLATION.md`

# A7 — cache-key ablation (isolating the state-derived part of the key)

**2026-09-26.**
- Script: `scripts/eval/a7_cache_ablation.py`.
- Results: `data/eval/a7_cache_ablation_before_fix.json` (shipped key) and `data/eval/a7_cache_ablation.json` (after the fix below).
- Setup: canonical database copies; stub image engine and no LLM client, so prompts are deterministic and no GPU is used. 218 panels from chapters 1, 2, 166, 178 and 197.

## Why the earlier result was confounded

"Keys differ 10/10 across observers" could not isolate the state digest. Between observers the prompt changes too, and `plan_digest` itself hashes each drawn `persona_id` and the `state_digest` (`render/contract.py`).

## Design

**Key conditions**, computed from the *same* captured plan and request objects for every panel:

| | Condition |
|---|---|
| **A** | The key exactly as shipped (`render/cache_key.py`). The harness asserts it reproduces the renderer's own key on every panel. |
| **B** | A, with `state_digest` removed from the key **and** from `plan_digest`. Prompt, plan shape, seed and config are unchanged. |
| **C** | B, plus persona ids removed from `plan_digest`. Nothing state-derived is left except what reaches the prompt. |

**Events.** Each is applied to a fresh database copy and compared with a baseline render pass:

| Event | What changes |
|---|---|
| E0 | Replay, no change |
| E1 | Cast persona hair colour |
| E1b | Cast persona attire |
| E2 | Off-cast persona appearance |
| E3 | New concurrent body for a cast member |
| E4 | Observer switch (reader → a witness) |
| E5 | Alias-only change |
| E6 | Cast Self attribute |

A second pass freezes each panel's prompt at its baseline value; it gave identical numbers here, because no persona edit reached the prompt.

**Ground truth, computed independently of any key:**
- **State-stale** (pre-registered): for any cast member, the `state_of` persona ids, Self attributes, or drawn-persona attributes changed.
- **Drawn-stale** (added after the first run showed state-stale over-counts): only what can reach the generator changed, i.e. the drawn persona or its attributes.

Both are reported.

## Result 1 — the shipped key served stale images (defect found)

Shipped key, drawn-stale truth:

| Event | Drawn-stale panels | Prompt changed | A stale reuses | B stale reuses | C stale reuses |
|---|---:|---:|---:|---:|---:|
| E1 hair colour | 23 | 0 | **23** | 23 | 23 |
| E1b attire | 23 | 0 | **23** | 23 | 23 |

- `state_of` on a Self returns only Self-targeted attributes, while every appearance attribute in the corpus is Persona-targeted. The appearance change therefore reached neither the digest nor the prompt.
- It reaches pixels through the persona's reference sheet, and the key hashes reference *paths*, not bytes (a documented limitation).
- **Fix** (`render/plan_builder.py`): the drawn persona's standing attributes are now hashed into `state_digest`.
- Regression tests: `test_readset_invalidation.py::test_an_appearance_change_on_the_drawn_persona_invalidates` and `…_offstage_persona_does_not`.

## Result 2 — after the fix, the digest is necessary and isolated

Fixed key; counts per condition over 218 panels.

**Drawn-stale truth:**

| Event | Stale | A: stale reuse / unnecessary regen | B | C |
|---|---:|---|---|---|
| E0 replay | 0 | 0 / 0 (218 reused) | 0 / 0 | 0 / 0 |
| E1 hair colour | 23 | **0 / 0** (23 regenerated) | **23 / 0** | **23 / 0** |
| E1b attire | 23 | **0 / 0** | **23 / 0** | **23 / 0** |
| E2 off-cast change | 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| E3 new concurrent body | 0 | 0 / **137** | 0 / 0 | 0 / 0 |
| E5 alias only | 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| E6 Self attribute | 0 | 0 / **137** | 0 / 0 | 0 / 0 |
| E4 observer switch | 188 | 0 / 0 | 0 / 0 | 0 / 0 |

**State-stale truth** (pre-registered): A is exact on every event. B and C additionally reuse stale artifacts on E3 and E6, 137 each.

## Reading it honestly

1. **The controlled isolation survived.** With prompt, plan shape, seed and config identical, removing the state digest (B, C) serves **46 stale artifacts** (E1 + E1b) that the full key (A) correctly regenerates. This holds only after the fix: before it, all three conditions served them stale.
2. **The digest over-invalidates.** A regenerates **274** panels whose generator inputs did not change: a new concurrent body that is not drawn (E3), and a non-visual Self attribute (E6). This follows from hashing all bound persona ids and Self attributes, a deliberate auditability choice. At the one recorded NoobAI timing (22 s/panel on the local RTX 4060), that is about **1.7 GPU-hours of avoidable re-rendering**. This is an **estimate, not a measurement**.
3. **Observer separation does not need the digest.** For the observer switch (E4), 182 of 188 changed panels also changed prompt, and all conditions separate them (406 unique keys in each). The digest adds nothing there on this corpus, so the earlier "keys differ 10/10" result was driven by prompt and plan differences, not the digest.
4. **Reuse works when nothing relevant changes.** E0, E2 and E5 reuse all 218 panels under every condition. At the same 22 s/panel estimate, a replay avoids about 80 GPU-minutes. That is a property of caching in general, not of the state digest.
5. **Aliases are still not in the key** (E5: 137 name changes, 0 regenerations). Whether a name change should re-render an image is a policy question; it is documented, not changed.
6. **Not measured:**
   - GPU time: the stub engine generates nothing.
   - Stub wall-clock: 155–245 s per 218-panel pass, dominated by planning and state queries, identical across conditions, so it is not informative about generation cost.
   - The effect of the reference-image *bytes*: sheets were not regenerated here.

**Technical effect, stated plainly:** the state-derived digest is what makes an appearance change produce a new cache identity when the prompt does not change. That is a correctness effect (no stale identity served). It is not a computational saving; the digest as designed costs extra re-rendering.

---

<!-- merged-from: docs/results/MDC_DISCLOSURE_ABLATION.md -->
## Source: `docs/results/MDC_DISCLOSURE_ABLATION.md`

# Minimal Disclosure Compiler — disclosure ablation

**2026-09-27.** Script `scripts/eval/mdc_disclosure_ablation.py`; result
`data/eval/mdc_disclosure_ablation.json`; canonical database
`data/db/reverend-insanity.db` (render + cast_naming experiments) plus an
explicitly synthetic in-memory fixture (dialogue_brief experiment, built in
the script itself — see below for why). New module
`packages/core/src/echotales/core/disclosure.py`
(`TaskSpec`/`DisclosureResult`/`compile_minimal_disclosure`); new tests
`packages/core/tests/test_disclosure.py` (13 cases, all passing); one
behavior-preserving refactor to `state.py` (`_fold_target` extracted from
`compile_generation_state`'s loop body, existing suite unchanged); render
integration `plan_builder.py::compile_render_state_minimal` +
`build_render_plan(..., use_mdc=False)`, opt-in and fully revertable.

This is the first of three planned candidates (Minimal Disclosure Compiler,
Temporal-Epistemic Delta Compiler, Counterexample-Guided Generation) being
evaluated for whether they constitute a genuine algorithmic contribution
worth an IPR review. **This document does not claim patentability** — that
determination happens after a separate prior-art/IPR review, per the
explicit scope of this investigation.

## Pre-registered rules (fixed in the script's docstring before any number was computed)

- **Render targets:** the 15 most-mentioned Selves in `reverend-insanity.db`
  with a `self_persona_binding` row (all of the top 20 have one, checked
  directly before writing the harness).
- **Render positions:** chapters 20, 100, 190 of a 199-chapter volume. 45
  queries total.
- **Four conditions:** FULL (every distinct store fact, no filtering at
  all), TOPK (`world/context.py::_ranked`'s existing cap applied to the
  observer-valid candidate's attributes — the one truncation mechanism
  already shipped here), OBSERVER (`compile_generation_state` unmodified,
  today's production behavior), MDC (`compile_minimal_disclosure` with
  `plan_builder.RENDER_TASK_SPEC`).
- **Metric:** evidence_count = |aliases| + |attributes| + |relationships|
  selected. Evidence-reduction % is measured **against OBSERVER**, not
  FULL — the FULL→OBSERVER gap is the already-measured observer-filtering
  effect from `docs/results/A1_OBSERVER_ABLATION.md`, not this module's
  contribution.
- **Leakage gate:** `EpistemicLeakageValidator` run against each MDC
  selection's own serialized content; a pass/fail gate (0 failures
  required), not a percentage.

## A confound found while building this harness

`reverend-insanity.db` has **zero** SELF-kind attribute rows and **zero**
relation rows (`SELECT count(*) FROM attribute WHERE target_kind='SELF'` →
0; `SELECT count(*) FROM relation` → 0), checked directly before writing a
single line of the harness. `world/schema.py`'s own docstring already
documents this gap for LOCATION/ORGANIZATION/ITEM ("10 locations and 35
organisations with zero facts attached to any of them"); it turns out
SELF-kind extraction against `PERSON_KEYS` (role/faction/status/...) was
never run against this database either. PERSONA-kind attributes exist and
are populated (617 rows across 98 personas: gender/age_band/archetype/
big_five/register on every persona, rarer visual keys on a handful).

Consequence: the render experiment's real-data "evidence" for a SELF target
is aliases only — attributes and relationships are 0 in *every* condition
because there is nothing in the graph to select from, not because MDC did
anything. This is itself a reportable finding, filed to HANDOFF, not a
limitation of the harness.

Because of this, the coverage-plus-dependency-closure mechanism — the part
of MDC that actually needs attributes and relationships to do interesting
work — cannot be exercised on real data at all right now. A second
experiment, `dialogue_brief`, runs against a small, explicitly labeled
**synthetic** in-memory fixture (three Selves, role/faction/status/
personality attributes, two relationships, built in the eval script) to
test that mechanism, per the user's own instruction to use synthetic
adversarial cases where real corpus coverage is missing. A third
experiment, `cast_naming`, runs several real top-mentioned Selves through
one MDC batch call to exercise the one mechanism real data *can* test:
cross-cast alias disambiguation.

## Result — render (real data, 45 queries over 15 targets)

| Condition | Avg. evidence/target |
|---|---:|
| FULL (unfiltered) | 2.20 |
| TOPK (`_ranked` cap) | 1.56 |
| OBSERVER (`compile_generation_state`) | 1.56 |
| **MDC** | **0.00** |

**Evidence reduction vs. OBSERVER: 100.0%.** Leakage gate: **0/45 failures**.

TOPK and OBSERVER are identical here because the only non-zero evidence
category (aliases) is untouched by `_ranked` (that function caps
attributes only, and there are none to cap on this corpus) — a real,
reportable mismatch between what `_ranked` was built for (a text brief) and
what this comparison asked of it, stated plainly rather than smoothed over.

MDC selects **zero** self-level facts for every render query because
`RENDER_TASK_SPEC` was built by reading `panels.py::character_looks`
directly (`panels.py:1369-1373`): it calls only
`gen_state.persona_for(...)` and `gen_state.appearance_for(...)`, never
`TargetState.self_attributes`, relationships, or aliases. An end-to-end
smoke test (a synthetic single-character case, not part of the pre-
registered ablation) confirmed the actual `CharacterRenderSpec` a real
panel would draw from is unchanged under MDC — the dropped evidence was
never something the render prompt read, not evidence dropped by accident.

## Result — dialogue_brief (synthetic fixture)

Task: `required_keys={SELF: {role, faction, status}}`, `require_relationships=True`,
`require_persona=False`. Two Selves queried (`s_hunter`, related to both an
onstage `s_elder` and an offstage `s_rival` who is not in the batch).

| | OBSERVER | MDC |
|---|---:|---:|
| Evidence count | 11 | 7 |
| Reduction vs. OBSERVER | — | **36.4%** |

- `unsatisfied_keys`: none — every required key had a candidate fact.
- **OBSERVER kept the offstage rivalry** (`rel:RIVAL_OF:s_rival`, true —
  `compile_generation_state` includes every SELF relationship
  unconditionally).
- **MDC kept only the onstage relationship** (`rel:DISCIPLE_OF:s_elder`,
  true) — the cross-referenced-cast filter dropping a relationship to an
  entity that is not part of this generation call, which no existing
  mechanism in this codebase does.
- Read-set subset invariant held: `True`. Leakage gate: valid.

This is the one result that demonstrates the coverage-plus-dependency-
closure mechanism doing something a naive top-k-by-priority filter over the
same candidate set could not: `_ranked`-style truncation has no concept of
"is the other end of this relationship even in the room," so it would keep
or drop a relationship based on key priority alone, irrespective of whether
the destination entity is part of the current generation call.

## Result — cast_naming (real data, alias disambiguation)

Five real top-mentioned Selves queried together, naming-only task
(`require_persona=False`, `require_name=True`, no attribute requirement).

| | OBSERVER | MDC |
|---|---:|---:|
| Alias count | 14 | 5 |

Read-set subset invariant held: `True`. This is the real-data analog of
`TestAmbiguousTitleDisambiguation` — with 5 real characters batched
together, `compile_generation_state` keeps every observer-valid alias for
each (up to ~2-3 apiece), while MDC's `_disambiguating_aliases` keeps
exactly one per target unless two targets' primary picks collide, landing
at 5 total (one per target, no collisions in this real sample) versus 14.

## Reading it honestly

- **The render result (100% reduction) is real but structurally hollow on
  this corpus**: it reflects that `compile_generation_state` bundles
  self-attributes and relationships into every `GenerationState`
  unconditionally, and the render prompt reads none of them — a genuine,
  previously undocumented gap this investigation surfaced (see HANDOFF),
  but one where MDC's "selection" work reduces to "everything was 0
  anyway except the one category (aliases) that also gets dropped because
  `require_name=False`." The *mechanism* (task-conditioned exclusion) is
  real; the *magnitude* on this task, on this corpus, is inflated by a data
  gap unrelated to MDC's own design.
- **The dialogue_brief result (36.4% reduction, correct relationship
  retained, incorrect one dropped) is the one that actually exercises
  dependency closure and cross-referenced-cast coverage**, and it only
  exists because real data could not supply the SELF-level facts needed to
  test it. This is exactly the honest-assessment risk flagged in the
  approved plan (render might show a hollow result) materializing, and the
  fairer second task the plan added specifically to hedge against it paying
  off.
- **Where this reduces to "ordinary filtering renamed" and where it does
  not:** the render result alone would not survive that objection — a
  task that needs zero self-level facts and gets zero is not evidence of a
  minimization *algorithm*, just evidence that an unconditional inclusion
  was wasteful. The dialogue_brief result is where the objection is
  actually tested and (on this synthetic case) survives: the
  cross-referenced-cast relationship filter is a real coverage decision
  with no analog in `_ranked`'s priority-and-cap truncation or in
  `compile_generation_state`'s unconditional inclusion, and the "never
  widen beyond `state_of`'s candidate set" subset invariant held in every
  condition tested (asserted in `test_disclosure.py::TestMinimalDisclosureReadSet`
  and re-checked here against real and synthetic data alike).
- **Scale is small.** One real corpus, one synthetic fixture, three Selves
  in the dependency-closure case. This is a first measurement, not a
  validated result across novels or task types.

## Whether this is distinct enough for a patent-agent/IPR review

Not a determination this document makes. What can be said from the
evidence above: the mechanism is not reducible to top-k retrieval or
ordinary RAG chunk-selection (the candidate set itself carries bitemporal
and observer-conditioned structure no flat-corpus retrieval system
represents), and the dependency-closure/cross-referenced-cast coverage
decision is demonstrably different in kind from both `_ranked`'s
static-priority cap and `compile_generation_state`'s unconditional
inclusion — but this was shown on one synthetic fixture, not yet on a
second real corpus or a second, independently-designed task. Worth carrying
into a prior-art review; not yet strong enough to skip one.

## What's next

1. File the SELF-attribute/relation extraction gap on `reverend-insanity.db`
   to `docs/HANDOFF.md` — it blocks re-running this experiment meaningfully
   on real data, and blocks other work (`world/context.py`'s brief is
   presumably just as starved for SELF-level content as this experiment
   found).
2. Proceed to the Temporal-Epistemic Delta Compiler (priority 2), reusing
   the dormant `Store.invalidate_by_facts`/`derived_artifact` primitive per
   the approved plan, rather than the live but render-only
   `GenerationState.digest()` path.

---

<!-- merged-from: docs/results/OBSERVER_CONTRAST_VALIDATION.md -->
## Source: `docs/results/OBSERVER_CONTRAST_VALIDATION.md`

# Observer-contrast validation — generation and read-set invalidation

**Run 2026-09-25 on the local RTX 4060.** Closes `docs/archive/COMPLETION_PLAN.md`
item 18, open since the observer axis was built, and removes the "never run
against a real image engine" caveat that qualified the project's two strongest
technical claims.

```bash
for OBS in READER reverend-insanity:self:a8bdaf3bfb; do
  echotales --db data/scratch/reruns/ner-window-ri.db render \
      --novel reverend-insanity --chapters 169 --block-range 1-10 --max-panels 3 \
      --image-engine noobai --observer "$OBS" --skip-motion --skip-compose \
      --panel-dir "data/novels/RI/panels-obs-<tag>"
done
```

Everything is held constant except the observer: same chapter, same blocks,
same checkpoint (NoobAI XL), same seed, same engine settings.

---

## 1. The result

| | `READER` | a character who never witnessed the reveal |
|---|---|---|
| Panels generated | 5 | 5 |
| **Reference-conditioned** | **5** | **0** |
| **Prompt-only** | 0 | **5** |
| Cache key identical across the two runs | **no** — 10/10 blocks differ | — |
| Pixels identical across the two runs | **no** — 10/10 blocks differ | — |

Per block, the manifest records what the generator was told:

```
block 1   READER       conditioned_on = ['Bai Ning Bing', 'Fang Yuan']
          non-witness  conditioned_on = []
block 5   READER       conditioned_on = ['Fang Yuan', 'Bai Ning Bing']
          non-witness  conditioned_on = []
block 9   READER       conditioned_on = ['Bai Ning Bing']
          non-witness  conditioned_on = []
```

And the delivered prompt itself diverges:

```
READER       2boys, male focus, guofeng illustration, chinese ink painting,
             xianxia, medium shot, Bai Ning Bing, black…

non-witness  1boy, male focus, solo, guofeng illustration, chinese ink
             painting, xianxia, medium shot, a figure, stand…
```

## 2. Why this is the claim and not a trick

Three things make this a property of the data model rather than of two
hand-written prompts.

**The character is named in one and anonymous in the other.** The reader's
panel says `Bai Ning Bing`; the non-witness's says `a figure`. Nothing in the
render path substitutes that string — the prompt assembler asks the graph who
is present and receives a different answer.

**The cast count changes.** `2boys` versus `1boy … solo`. The observer who
never witnessed the reveal does not merely lack her name; **she is not in
their scene at all**, so the composition itself differs. A redaction step
applied to a finished image cannot produce that.

**The cache key changes, on every block.** `render/cache_key.py` derives the
artifact key from `plan.state_digest`, which hashes the facts the graph
returned. Different observer → different read set → different digest →
different key → a genuinely separate cached artifact. This is the composition
the disclosure calls P3 ∘ P6, observed working: the excluded information never
reaches the prompt because the query never returned it.

## 3. What this closes

- **`COMPLETION_PLAN` item 18** — the two-observer contrast, the paper's
  central figure. Artifacts at `data/novels/RI/experiments/observer-contrast/reader/` and
  `data/novels/RI/experiments/observer-contrast/nonwitness/`, 5 panels each, 1.4–1.6 MB per PNG.
- **The stub-mode caveat on P6 and P7.** Both had read "wired and unit-tested
  but never run against a real image engine." They have now run.
- **Phase 11, the multimodal proof of concept** — text → resolved state →
  render plan → generated artifact, with the graph query as the only variable.

## 4. What it does not close

- **This is a with-identity / without-identity contrast, not two different
  depictions of the same person.** The strongest possible version — the same
  scene as the Wu clan *believes* it versus as the reader knows it, where both
  observers see a character but a *different* one — needs a `FABRICATED` alias
  (a sustained disguise) in the corpus. Reverend Insanity has none
  (`docs/results/EXPERIMENT_RESULTS.md` Section 2). Lord of the Mysteries is the
  candidate.
- **No claim about image quality.** No rendered pixel in this project has ever
  been scored; the CLIPScore bench remains unbuilt. These five panels show the
  mechanism reaches the generator, not that the output is good.
- **Five panels is a demonstration, not a benchmark.** Bounded deliberately —
  `--max-panels 3 --block-range 1-10` — because GPU time is for answering a
  specific question and stopping.

## 5. A caveat worth carrying into the paper

The non-witness render drops the character rather than depicting her as a
stranger. That follows from every `self_persona_binding` row carrying
`observer_id = READER`, so a character observer can resolve an alias but never
a persona (`docs/results/EXPERIMENT_RESULTS.md` Section 3).

Arguably a witness who knows someone's name should also know their face, and
the intended semantics is probably "depict her without the reveal-dependent
attributes" rather than "omit her". The binding row already carries an
`observer_id` column; `detect_observations.py` simply has no writer for it.
Until that exists the contrast is sharper than the model really intends —
worth stating plainly rather than presenting the starker figure as the design.


---

## 6. Exact records for the contrast run

| | READER | non-witness (`reverend-insanity:self:a8bdaf3bfb`) |
|---|---|---|
| `state_of(Bai Ning Bing, position=169)` aliases | 2 | 0 |
| `state_of(...)` persona_ids | `…:0035e71331:body1` | none |
| Plan `characters` | 1 | 0 |
| `state_digest` | `de02bdbf43ff8294` | `3ce2442598531a35` |
| Block 1 cache key | `5066f03cc44fef0a` | `a27b42d9057e64a3` |
| Block 1 output | `data/novels/RI/experiments/observer-contrast/reader/ch169/v1/p001_b0001.png` | `data/novels/RI/experiments/observer-contrast/nonwitness/ch169/v1/p001_b0001.png` |
| Seed | CLI default, identical for both runs | identical |

## 7. Controlled read-set invalidation

`packages/pipeline/tests/test_readset_invalidation.py` — five tests on a
controlled store, stub path, no GPU. The claim has two halves and both hold:

| State change | Cache key |
|---|---|
| None (rebuild the same plan) | **unchanged** |
| Attribute added to a character **in** the panel's cast | **changes** |
| Attribute added to a character **not** in the cast | **unchanged** |
| New body bound to a cast character | **changes** |
| New alias for a cast character | **unchanged** — see below |

The offstage case is the one that matters: it is what makes this precise
invalidation rather than "any change busts every cache".

**A limit this exposed.** `render/plan_builder.py` hashes persona ids and
attributes into `state_digest`, **not aliases**. A revelation that only adds a
name to a character therefore does not invalidate a panel that already depicts
them. The test pins this as current behaviour so a future change to it is a
deliberate decision, and the disclosure's P6 should describe the read set as
"embodiment and attribute facts", not "all facts consulted".
