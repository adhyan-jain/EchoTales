# Pre-registration: decisive technical-contribution experiment

Written **before the harness (`decisive_harness.py`) existed**, so before any system output, per-system total or aggregate had been seen. HEAD `6c7e2c2`, branch `validation/evidence-pass-2026-09-24`. Referenced from `DECISIVE_EXPERIMENT_RESULTS.md`.

## 0. Stage 1 finding: what the existing probe is

`probe_inventory.py` is an **observation printout** (P1-P9). It does not execute B1, B2 or T, has no oracle, no seeds and no comparison. The experiment harness is therefore new: `decisive_harness.py` (+ `test_decisive_harness.py`). No production file and no existing probe/test/doc is modified.

## 1. Oracle (independent; reads only the world *spec*, never a Store, never `state_of`, never T)

A fact `f` is **admissible** for query `q = (p, k, o)` iff all hold:

1. **Story time**: `f.start <= p < f.end` (crisp half-open; `end=None` is open). The suite uses crisp intervals only; fuzzy/PLAUSIBLE bands are **out of scope** (not generated, not scored).
2. **Authorization**: `o=READER` -> `f.observer == READER`. Character `o` -> `f.observer == o`, **or** `f.observer == READER` and `o` has a witness row for `f`. No other inheritance of reader knowledge.
3. **Disclosure time**: effective learned position `<= k`, where effective = the witness position for a witnessed reader fact, else `f.learned`.
4. **Retraction is positional** (non-negotiable 5): if `f.retracted` is set, admissible only while `k < f.retracted`. A retracted belief stays admissible *before* its retraction and is not erased from the past.
5. **Persona-level facts** additionally require an admissible `self->persona` binding for `o` (stamp == `o`, `learned <= k`). Self-level facts do not.

Uncertainty: no PLAUSIBLE states are generated. Facts valid in the fictional timeline but not yet disclosed (`learned > k`) are **inadmissible** (retrospective reveal). Facts disclosed before they become true in story time (`start > p`, `learned <= k`) are **inadmissible** (foreshadow).

**Derived artifacts** get a three-valued oracle verdict from the *ground-truth* derivation (the generator knows what each artifact was really built from, independent of what any manifest declares):

* `FORBID`: some fact in the true transitive derivation is inadmissible for `q`.
* `UNVERIFIABLE`: all true facts are admissible but the stored lineage is damaged (missing parent record, cycle, or manifest edited after registration). Policy: fail closed; accepting it is an **unverified exposure**.
* `ADMIT`: all true facts admissible and lineage intact. An emitter that *under-declared* a dependency (manifest self-consistent but incomplete) is `ADMIT` if the undeclared fact is admissible, `FORBID` otherwise.

**Scoring** (never "correct because it exposes nothing"):
* **Unauthorized exposure** = a fact in a consumer output that is not oracle-admissible (per fact), or an accepted `FORBID` artifact.
* **Unjustified omission** = a *group* with >=1 admissible fact where the output contains none of them (attribute group = (target,key), so supersession of one admissible value by another is not an omission; alias/relation group = the fact), or a rejected `ADMIT` artifact.
* **Unverified exposure** (artifacts only) = accepted `UNVERIFIABLE` artifact; reported separately.

## 2. Systems

* **B1** production path: `compile_render_state` (-> `appearance_of`, `state_of`), `world.context._facts_as_of`, and `StateResolver.resolve_alias`. B1 cannot be given `k` or (for the brief) `o`; it runs with `k=int(p)` and is scored on every query, with the production-reachable subset (`k==int(p)`) reported separately. Derived artifacts: production never consumes references (`reference_images=[]`), so B1 is **not applicable** there.
* **B2** straightforward fix: every consumer calls `state_of(p, knowledge_pos=k, observer_id=o)` itself. Artifacts: own declared facts re-checked live through `state_of`; no parent traversal.
* **B2x** B2 plus a naive transitive check (declared parents followed, visited set, missing parent rejected at any depth, no tag/cycle/content checks). Added because kill criterion E and the K4 test in `ECHOTALES_NEXT_RESEARCH_DECISION.md` ask whether T beats a naive transitive check.
* **B3** the existing unwired `VisualMemorySelector` (snapshot-based), artifacts only. Registry `observer_scope` is set permissively so B3's gate 2 does not dominate.
* **T** synthetic prototype, harness-only: one `RowPolicy` admission function (own implementation over store rows) shared by every consumer and by artifact checks; live revalidation at request time; transitive closure with an explicit stack; fail closed on missing parent, cycle, registrar-HMAC mismatch (checked on every ancestor), and on dependencies *inferred from artifact content* (text artifacts only; opaque image content cannot be scanned) that are inadmissible. T's per-fact policy is a second implementation of the same policy as the oracle; the three-way differential test (oracle / `state_of` / `RowPolicy`) is what licenses treating them as one specification.

Synthetic vs production: every lineage fixture is synthetic (no code path in the repo produces real derived-artifact lineage); T and the B2/B2x adapters are harness code. Only B1 (and B3 / `resolve_alias` as unwired components) execute repository code as shipped.

## 3. Kill criteria (fixed now)

* **A** B2 has 0 unauthorized exposures and 0 unjustified omissions on every consumer and class -> T shows no additional correctness benefit; classify as conventional bug fix.
* **B** T omits more admissible groups than B2 (by more than 2 percentage points of admissible groups) on classes where both are leak-free -> T invalid.
* **C** T's advantage over B2 appears only on synthetic lineage -> "research prototype result", not a demonstrated system capability. (Pre-declared: this will apply to all artifact classes, since no code produces real lineage; recorded now so it is not a post-hoc finding.)
* **D** T has any oracle-confirmed exposure on a class it claims to prevent -> report the counterexample; the oracle is not changed afterwards. T's pre-declared claim set: stale/retracted/future/unauthorized facts on every consumer; missing parent, cycle, post-registration manifest edit, undeclared dependence **in scannable text content**. Pre-declared **outside** T's threat model (limitations, not D failures): undeclared dependence inside opaque image content with a registrar-signed manifest; a lying registrar.
* **E** B2 and T identical on all meaningful cases -> no advantage from architecture or shared code.

Ablations A1-A6 run on T's `RowPolicy` flags (A1 no knowledge-time, A2 no story-interval, A3 retraction as interval end, A4 no observer door, A5 own-facts-only lineage, A6 registration-time snapshot instead of live). Predicted breakage: A1->X1,X9; A2->X2; A3->X3 (omission, not leak); A4->X4; A5->X7,X9; A6->X8.

Seeds: classes use seeds `0..39`, fuzz uses `1000..1299`. Fixed in the harness; no seed selection.

## 4. Deviations log

Recorded in `DECISIVE_EXPERIMENT_RESULTS.md` (section "Deviations"). None at time of writing.
