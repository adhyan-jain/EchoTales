# Decisive experiment: results

**Date** 2026-10-14 · **HEAD** `6c7e2c2` (branch `validation/evidence-pass-2026-09-24`; untracked research files only, no tracked file modified, nothing committed).
**Protocol** [PREREGISTRATION.md](PREREGISTRATION.md), written before the harness existed. **Harness** `decisive_harness.py`. **Per-case data** `DECISIVE_EXPERIMENT_RESULTS.json` (1,260 cases, 8 MB). Evidence tags: **[OBS]** measured here; **[HIST]** from an earlier document, not re-verified; **[INFER]** inference.

## Provisional outcome

**NO-GO FOR THIS MECHANISM.**

* The *shared, live policy enforcement* part of T adds nothing. On every consumer that runs repository code, T and the straightforward fix B2 are identical (0 exposures, 0 omissions), and it is B1, today's production path, that fails. That is a bug-fix list. [OBS]
* The *transitive lineage over derived artifacts* part helps only on synthetic lineage that no code in the repo can produce. A short naive transitive check (B2x) already closes every leak class except post-registration manifest edits. What is left for T is a registrar HMAC (standard integrity), cycle fail-closed (no leak, an invalid-lineage policy) and a content scan that a post-hoc baseline (B2xs) matches. [OBS]
* This does not authorise production changes, GPU spend, further sampling or paper drafting. B2 is supported as an engineering fix, not as a contribution.

## 1. Stage 1: what existed, what was run

* `probe_inventory.py` is an **observation printout** (P1-P9). It does not execute B1/B2/T and has no oracle, seeds or comparison. A new harness was therefore written. Nothing under `packages/` and no existing probe/test/doc was modified (`git status` shows only untracked files; `git diff --stat` is empty).
* No production caller exists for `VisualMemorySelector`, `EpistemicLeakageValidator`, `compile_minimal_disclosure` or `resolve_alias`. `emit_scoped_reference` appears under `packages/*/src` only as its definition and re-exports (`persona/__init__.py`, `reference_gen.py:806`). Nothing in `packages/*/src` derives an artifact from a parent artifact. The only digest helper, `compute_asset_input_digest`, is unkeyed and has no caller [HIST: inventory section 4C]. [OBS for the grep]

Commands and results (CPU only, no network, no API key read):

| Command | Result |
|---|---|
| `.venv/bin/python docs/research/technical_contribution_probes/probe_inventory.py` | P1-P9 reproduced unchanged (P1 `WU=()`, P2 private fact reaches reader panel, P3 brief drops retraction, P4 `resolve_alias`=`[]` for WU, P5 field loss, P6 selector stale after retraction, P8 p=5 k=10 fallback / k=100 selected) |
| `.venv/bin/python -m pytest -o addopts="" -q` on the 9 inventory test files | **136 passed** in 5.7 s |
| `.venv/bin/python -m pytest -o addopts="" -q docs/research/technical_contribution_probes/test_decisive_harness.py` | **22 passed** in 6.8 s |
| `.venv/bin/python docs/research/technical_contribution_probes/decisive_harness.py` | 1,260 cases, ~45-55 s, 0 execution errors |
| `ECHOTALES_LLM_MODE=stub .venv/bin/python docs/research/technical_contribution_probes/e2e_b1_stub_render.py` | ran; **inconclusive** (section 8) |

The full 1,277-test suite was **not** run; no full-suite regression claim is made. The 136 + 22 tests check implementations and harness against their own fixtures, not production use.

## 2. Oracle and its validation

Rules, uncertainty handling and the three-valued artifact verdict are in PREREGISTRATION.md section 1 (story containment, observer door with witness rows, disclosure `<= k`, **positional** retraction, persona-binding gate; no PLAUSIBLE states generated; disclosed-but-not-yet-true and true-but-not-yet-disclosed are both inadmissible; artifact verdicts `FORBID` / `UNVERIFIABLE` / `ADMIT` from ground-truth derivation). A test (`test_oracle_does_not_reference_candidate_code`) checks the oracle source names no `StateResolver`, `state_of`, `RowPolicy`, `Store` or `compile_render_state`.

**Differential check** (before any comparison): oracle vs `RowPolicy` vs production `state_of` on the 300 fuzz worlds, 15,000 consumer comparisons: **0 mismatches** each. Over the fuzz facts, each rule is the sole reason some fact is hidden (knowledge time 7,323; story interval 8,377; retraction 1,323; observer door 15,767 instances), so the agreement is not vacuous. [OBS]

**Consequence for interpretation**: the oracle was validated against `state_of`, so B2 is correct on the consumer classes by construction. Those rows cannot show B2 wrong; they show that today's consumers (B1) diverge from `state_of`. The oracle and `RowPolicy` encode one specification by one author: agreement shows implementation fidelity, not that the specification is the right one.

## 3. Results: non-derived consumers

Consumers: persona attributes (ATTR), director-brief facts (BRIEF), aliases (ALIAS), relations (REL), alias to holder resolution (RESOLVE), render-cache key. Exposure counted per fact, omission per group (attribute group = (target, key)). 40 seeds per class (fuzz: 300 seeds).

| Class | Queries | B1 queries failed | B1 exposures | B1 omissions | B2 exp / omit | T exp / omit |
|---|---|---|---|---|---|---|
| X1 retrospective reveal | 160 | 160 | 80 | 160 | 0 / 0 | 0 / 0 |
| X2 foreshadow | 120 | 80 | 160 | 0 | 0 / 0 | 0 / 0 |
| X3 retraction | 160 | 80 | 0 | 240 | 0 / 0 | 0 / 0 |
| X4 observer split | 690 | 690 | 4,897 | 297 | 0 / 0 | 0 / 0 |
| X5 alias / title / relation | 1,200 | 638 | 432 | 380 | 0 / 0 | 0 / 0 |
| FZ fuzz | 3,000 | 2,904 | 13,748 | 3,573 | 0 / 0 | 0 / 0 |
| XB all admissible (must still be exposed) | 120 | 0 | 0 | 0 | 0 / 0 | 0 / 0 |
| X8-cache key after a retraction | 40 | 33 (over-invalidation) | stale-serve 0 | n/a | 0 | 0 |
| XP persona binding unknown to the character (policy-ambiguous, strict oracle; excluded from totals) | 120 | 80 | 240 | 0 | 0 / 0 | 0 / 0 |

* **Totals (scored classes, XP excluded)**: B1 **19,317** unauthorized exposures and **4,650** unjustified omissions; B2 **0 / 0**; T **0 / 0**. Execution errors: 0 for every system. B2 and T expose the admissible facts in the benign class XB, so their zeros are not produced by emitting nothing.
* B1 also fails on **production-reachable** queries (`k == int(p)`): X1 40 exposures; X2 80; X3 240 omissions; FZ 5,407 exposures and 1,252 omissions over 6,055 reachable consumer calls. The remainder fail on coordinates production cannot express (`k != int(p)`; production never exercises `p != k`).
* Every B1 failure comes from **actual production code paths**: `compile_render_state`/`appearance_of`, `_facts_as_of`, and, for RESOLVE, the unwired `StateResolver.resolve_alias`. They reproduce the documented D1 (p-only attributes), D2 (retraction erases past belief) and P1-P4 (observer-blind brief and attributes; no observation door in `resolve_alias`). X5 failures were not root-caused one by one: they mix ALIAS/REL via `compile_render_state` and RESOLVE via `resolve_alias`.
* **X8-cache**: B1's state digest over-invalidates in 33/40 cases (a retraction beyond `k` changes the digest although the admissible set is unchanged) and served no stale key. That is a cost, not a leak. B2's and T's keys track the admissible set exactly.
* **Kill criterion A fires on the consumers**: B2 has 0 exposures and 0 omissions on every non-derived class. **Kill criterion E fires too**: B2 and T are identical on all 5,610 consumer queries; no advantage from shared code or architecture is claimed.

## 4. Results: derived artifacts (all lineage is synthetic)

B1 is **not applicable**: production passes `reference_images=[]`, so no derived artifact reaches an output. Cells are **failed queries of N** (a query fails if the system accepts a `FORBID` artifact [E], accepts an `UNVERIFIABLE` one [U], or rejects an `ADMIT` one [O]); the letter shows which. 40 seeds per class.

| Class (fixture) | N | B2 | B2x | B2xs* | B3 (existing selector) | T |
|---|---|---|---|---|---|---|
| X7 chain, all admissible | 160 | 0 | 0 | 0 | 0 | 0 |
| X7 late fact in parent | 160 | 80 E | 0 | 0 | 0 | 0 |
| X7 diamond | 160 | 80 E | 0 | 0 | 0 | 0 |
| X7 depth 3 | 160 | 80 E | 0 | 0 | 0 | 0 |
| X9 text derived from an asset | 160 | 80 E | 0 | 0 | 0 | 0 |
| X7 observer witness | 360 | 0 | 0 | 0 | 0 | 0 |
| X2 forward-reveal asset | 120 | 0 | 0 | 0 | 80 E | 0 |
| X8 stale (retraction after registration) | 120 | 0 | 0 | 0 | 80 E | 0 |
| XT missing parent (depth 2) | 160 | 160 U | 0 | 0 | 160 U | 0 |
| XT missing parent, late fact behind it | 160 | 160 E+U | 0 | 0 | 160 E+U | 0 |
| XT cycle | 160 | 160 U | 160 U | 160 U | 160 U | 0 |
| XT manifest edited: parent dropped | 160 | 160 E+U | 160 E+U | 160 E+U | 160 E+U | 0 |
| XT manifest edited: fact dropped | 160 | 160 E+U | 160 E+U | 160 E+U | 160 E+U | 0 |
| XT manifest edited in an ancestor | 160 | 160 E+U | 160 E+U | 160 E+U | 160 E+U | 0 |
| XT emitter under-declared, **text** content | 160 | 80 E | 80 E | **0** | 80 E | 0 |
| XT emitter under-declared, **image** (opaque) content | 160 | 80 E | 80 E | 80 E | 80 E | **80 E** |

(*B2xs = B2x plus a content scan; **post-hoc diagnostic, not pre-registered**, see Deviations.)

Totals over the 2,680 artifact queries (exposures / unverified / omissions): B2 1,280 / 1,120 / 0; B2x 480 / 640 / 0; B2xs 400 / 640 / 0; B3 720 / 880 / 0; **T 80 / 0 / 0**, and all 80 are the one class below. Omissions are 0 for every system, including T on the classes where an admissible artifact must still be accepted (clean chain; late-in-parent at `k >= L`; under-declared text at `k >= L`; stale at `k < r`). Execution errors: 0.

**Counterexample (kill criterion D)**: T accepts an artifact whose true derivation contains an inadmissible fact in every `XT-underdeclared-image-s0 … s39` (queries with `k < L`; e.g. `XT-underdeclared-image-s0`, `(p=6, k=6, READER)` and `(p=6, k=62, READER)`, artifact `u`). The registrar signed a manifest that omits a dependency and the content is opaque, so neither tag nor scan can see it. This is the case pre-declared as outside T's threat model (PREREGISTRATION criterion D), so it is reported as a **limitation, not a D failure**. It still means T gives no guarantee against an under-declaring emitter for images, the realistic modality. Every other system fails the same queries.

**What each component buys over B2x**: the tag check removes the three manifest-edit classes (B2x: 480 exposures and 480 unverified); the cycle check removes 320 unverified exposures with no leak; the content scan removes under-declared text, which B2xs shows an ordinary scan also does. Source of all of it: **synthetic**. The repo has no registrar, tag, content-bearing derivation or parent link produced by code.

**Kill criterion B**: T omissions = B2 omissions = 0 everywhere, so it does not fire (T does not reach zero exposures by suppression).
**Kill criterion C**: fires for every artifact row. T's advantage over B2/B2x/B3 exists only on lineage the application cannot produce or validate: a **research-prototype result, not a demonstrated system capability**.

## 5. Ablations (T's `RowPolicy` flags; same cases; exposures / unverified / omissions)

| Ablation | Predicted | Observed (classes that changed) | Prediction |
|---|---|---|---|
| A1 no knowledge time | X1, X9 | exposures: X1 240, X4 460, X5 964, X7-late 160, X7-diamond 320, X7-depth3 320, X9 160, XT-tamper-drop-parent 80, XT-underdeclared (text+image) 160 (80 of it the baseline), X7-observer-witness 40 | X1, X9 hold; more classes broke than predicted |
| A2 no story interval | X2 | exposures: X2 240, X3 120, X5 604, X2-forward-asset 80 | X2 holds; also X3, X5 |
| A3 retraction as interval end | X3 (omission) | omissions: X3 240, X8-stale 40; no new exposures | holds |
| A4 no observer door | X4 | X4 4,902 exp / 74 omit, X5 3,760 / 168, X7-observer-witness 160 exp | X4 holds; also X5 |
| A5 own-facts-only lineage | X7, X9 | X7 late 80, diamond 240, depth3 240; missing parent 320 U; missing-parent-late 160 E + 160 U; cycle 320 U; tamper-in-parent 80 E + 80 U | X7 holds; **X9 not broken** |
| A6 snapshot not live | X8 | X8-stale 80 exposures | holds |

Baseline T carries exactly the 80 pre-declared under-declared-image exposures, which also appear in every ablation row. Attribution is clean for A3 and A6 and acceptable for A1, A2, A4: the extra classes do contain the same dimension (X3's flashback query needs the story interval; X5 has observer and disclosure dependence). Two honest mismatches with the pre-registration: my predicted class lists were too short, and **A5 does not break X9**, because T's content scan (the text fixture embeds the parent's token) rejects the leak without any lineage traversal. In this fixture X9 is protected by the scan, not by transitive closure.

## 6. Kill-criterion decisions

| Criterion | Decision | Basis |
|---|---|---|
| A | **Fires on consumers**; does not fire on artifacts | B2 0/0 on all non-derived classes. B2 (own facts only) leaks on artifacts, but B2x does not on X7/X8/X9/missing parent |
| B | Does not fire | T omissions 0 |
| C | **Fires** for all artifact advantage | Lineage synthetic; nothing in the repo produces it |
| D | Only the pre-declared `XT-underdeclared-image` counterexample; none on any claimed class | section 4 |
| E | **Fires on consumers**; on artifacts the residual edge over B2x is tag/cycle checking | sections 3-4 |

## 7. Deviations (disclosed before interpreting)

1. **B2xs was added after seeing the first results.** The first full run had B2, B2x, B3, T. B2x's failure on under-declared text raised the question of whether T's edge needs T, so B2xs was added and the suite rerun. The pre-registered systems' counts on the classes inspected before and after (X9, cycle, tamper-drop-fact, tamper-in-parent, under-declared text) were unchanged. B2xs is labelled post-hoc everywhere.
2. **XP** (persona binding stamped READER only, character observer) is reported separately and excluded from totals. The strict oracle reading (an unwitnessed persona is not known to the character) is a policy choice; `state_of` draws nothing there too (P1). B1 additionally exposes persona facts through the observer-blind brief there.
3. **X6 absent evidence** has no separate class, and unknown-attribute fallback text is not modelled. XB is the over-suppression guard for facts that exist.
4. Plan **X9** is a text artifact whose content embeds its parent's fact token. **X5** relational facts are the REL consumer. Fuzzy (PLAUSIBLE) intervals were not generated (declared out of scope).
5. The plan's end-to-end stub render ran for B1 only and was inconclusive (section 8). T is not wired into production, so no T render exists.
6. `METHODS_PAPER_EXPERIMENT_PLAN.md` was **not edited** (untracked, no way to restore it); this document is the versioned results record for it.

## 8. End-to-end stub render (B1 only): inconclusive

`e2e_b1_stub_render.py` builds a temporary store (one character with a retrospective-reveal fact, a fact retracted at ch50 but held at ch5, and an ordinary fact), runs real `render_panels` with the stub engine and stub LLM for the reader and a character observer. The prompt draws the character (`1boy, male focus, solo, ...`) but contains **none** of the three attribute values, including the admissible one, so the run does not test the policy (the mechanical path emitted no appearance clause for the wide shot). Nothing is concluded from it and the script prints `INCONCLUSIVE`. A conclusive end-to-end test needs a beat for which production emits a close-up appearance clause; that was not pursued. It would be prompt-level only in any case.

## 9. Runtime

Summed wall time per system across the suite (single process, no repetition, not reliable): B1 8.2 s, B2 6.4 s, T 3.3 s, B2x 0.7 s, B2xs 1.0 s, B3 0.9 s. These are dominated by per-call `StateResolver` construction and store round trips, not policy cost. No overhead claim is made.

## 10. Novelty gate (independent of this experiment)

Passing this experiment would not have made the method novel, and it did not pass anyway.

| Item | Classification |
|---|---|
| Consumers calling `state_of(p,k,o)` instead of `appearance_of` / `_facts_as_of` | **Ordinary correction of existing bugs** (verified defect; B2 fixes it) |
| Separate story and disclosure positions, observer door, positional retraction | **Standard bitemporal / access-control semantics**, already in `state_of` |
| Transitive label check over declared parents, fail closed on a missing parent | **Provenance tracking over declared dependencies / standard information-flow control**; B2x does it |
| Registrar HMAC over manifests, cycle rejection | **Standard integrity checking**; synthetic here |
| Content scan for undeclared dependence in text | **Output-side leakage check** (cf. the repo's `EpistemicLeakageValidator`); matched by B2xs |
| T as a whole | **Synthetic prototype behaviour**, not a verified production capability |
| Shared live enforcement across consumers | **No measurable advantage** over per-consumer `state_of` |

Closest-prior-art questions still open (no literature search was done here; items are **[HIST]** from `ECHOTALES_NEXT_RESEARCH_DECISION.md`): (1) whether Jularr checks parent asset hashes or only the top-level chapter; (2) VividWorld and NovelViz could not be located earlier; (3) whether Narrative World Model (arXiv 2607.05577) has multi-character observer access control; (4) IFC for LLM prompts and agent memory (FIDES, APPA, SPA as cited) and C2PA-style signed lineage as the standard form of the tag and closure behaviour; (5) database provenance (why/where provenance, semiring annotations) and bitemporal SQL for the live-revalidation part. None needs resolving to act on this result, because the mechanism fails earlier.

## 11. Limits

* Constructed worlds; one author wrote the generator, oracle, B2 and T. Seeds were fixed in advance, but class designs could favour or disfavour a system. B2x and B2xs exist to bound that.
* The shipped databases contain none of the distinguishing events, so nothing here is evidence about the corpus. All zero-error rows for B2 and T are synthetic and, for consumers, partly tautological (section 2).
* Prompt and metadata level only; no pixel or perceptual claim. Raw narration in the director prompt is not filtered by any system (plan section 7).
