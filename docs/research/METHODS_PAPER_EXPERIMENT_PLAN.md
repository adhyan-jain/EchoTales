# Methods-paper experiment plan: smallest decisive test

**Date**: 2026-10-14 · **HEAD**: `6c7e2c2` · **Status**: proposal only. Nothing in this plan has been run or implemented. It follows from [TECHNICAL_CONTRIBUTION_INVENTORY.md](TECHNICAL_CONTRIBUTION_INVENTORY.md) and [CLAIM_TO_EVIDENCE_MATRIX.md](CLAIM_TO_EVIDENCE_MATRIX.md).

The plan targets the one question the current code can answer cheaply and deterministically: **does enforcing one admissibility policy at every consumer, with live revalidation and transitive closure over derived artifacts, remove exposures that the straightforward fix (each consumer calling `state_of` on its own) does not?** If it does not, the finding is that no technical contribution beyond integration has been established. That outcome is acceptable and should be reported as such.

## 1. Falsifiable main hypothesis

**H.** On an oracle-labelled adversarial suite with distinct story-time and reveal-time cutoffs, observer restrictions, retractions, aliases/titles and derived-asset lineage, a *shared, revalidating admissibility check* (treatment, T) yields **zero** exposures of inadmissible facts in every emitted artifact, while the closest reproducible baselines do not:

- **B1** = the production path as it is at HEAD (`compile_render_state` + `appearance_of` + `_facts_as_of` + `reference_path_for`).
- **B2** = the straightforward fix: each consumer routes through `state_of(p, k, o)` independently, with no shared artifact, no transitive closure and no revalidation (the obvious engineering repair of D1, D2, P1-P3).

**Falsified if** (any one):

1. B2 reaches zero exposures on all classes (then T adds nothing beyond routing consumers through `state_of`; the result is a bug-fix list).
2. T shows exposures in any class (the mechanism does not do what it claims).
3. T reaches zero only by over-suppression: its retained-admissible-fact rate falls more than 2 percentage points below B2's on the classes where both are leak-free (an "emit nothing" policy trivially leaks nothing).

Only a result where B1 > 0, B2 > 0 on specified classes, T = 0, and the ablations (section 4) each break their predicted class would indicate a mechanism beyond integration. Whether that mechanism is *new* is a separate literature decision, not decided here.

## 2. Adversarial test suite (CPU, deterministic)

A seeded generator builds small stores (about 3-6 entities, 2 bodies, 30-60 facts) in `:memory:` SQLite. The oracle is a **separate brute-force implementation** (set comprehension over raw rows: fact is admissible iff interval contains p, `learned_at <= k` [or the observer's witnessed position], observer-authorized, and not retracted at k), written without calling `state_of`, and cross-checked against `state_of` first (a differential test) so the oracle itself is validated.

| Class | Construction | What it separates |
|---|---|---|
| X1 retrospective reveal | fact true at p<=5, `learned_at` ch100, request (p=5, k=10) vs (p=5, k=100) | p-only filter (`appearance_of`) vs k filter |
| X2 forward reveal | fact starts after p but learned before k (foreshadow) | k-only filter (`_facts_as_of`) vs story-interval filter |
| X3 retraction | belief held ch1..49, retracted ch50; requests at k=20 and k=60 | `is_standing` (erases belief) vs positional retraction; also checks that T *keeps* the past belief |
| X4 observer split | reader-stamped fact, character with and without an `observation` row; character-private facts | observer door; character persona bindings (P1) |
| X5 alias/title | transferable title held by A then B; disguise name known to some observers | `resolve_alias`; identity decisions per observer |
| X6 absent evidence | key attribute never stated | over-suppression guard; fallback must say "unknown", not invent |
| X7 derived lineage | asset DAGs depth 1-3: chain, diamond, 2-cycle, missing parent, parent fact admissible only at a later k | own-facts-only filter vs transitive closure |
| X8 stale artifact | artifact built under (p,k,o), then the store gains a retraction or a policy change | snapshot (P6) vs live revalidation |
| X9 derived text | description derived from an asset whose facts include a later reveal | cross-modal lineage; the only class where a shared artifact could matter beyond per-consumer filtering |

Each store yields requests over a grid of (p, k, o). Approx. 10^3 stores x 20 requests is tractable on CPU in minutes.

## 3. Baselines

| Baseline | What it is | Reproducible from |
|---|---|---|
| B1 | Production path as-is | `render/panels.py:character_looks`, `persona/reference_gen.py:appearance_of`, `world/context.py:story_context`, `reference_path_for` |
| B2 | Each consumer calls `state_of(p,k,o)` itself; reference chosen by own-facts filter | New thin adapters over `core/state.py`; no new policy |
| B3 (reference) | The existing `VisualMemorySelector` unchanged, to show what snapshot-only lineage does | `core/visual_memory.py` |
| T | Shared admissibility function consumed by brief, attributes, selector and a derived-text step; revalidates against the live store before reuse; closes transitively | New; to be specified before the run |

B2 is deliberately strong. A weaker baseline (for example the unrepaired production path alone) would only show that known defects exist.

## 4. Ablations (remove one mechanism at a time)

| Ablation | Predicted new exposures | A prediction that fails counts against T |
|---|---|---|
| A1 no knowledge-time filter | X1, X9 | |
| A2 no story-interval filter | X2 | |
| A3 retraction as interval end | X3 (erases past belief: an *over-suppression*, not a leak; measured on the utility metric) | |
| A4 no observer door | X4 | |
| A5 own-facts-only lineage | X7, X9 | |
| A6 snapshot instead of live revalidation | X8 | |

Each ablation must break its predicted class and not unrelated ones; otherwise the mechanism's attribution is unclear.

## 5. Metrics

- **Exposure**: an emitted artifact (prompt string, director brief, reference manifest + parent list, derived text) containing the value or ref of a fact not in the oracle's admissible set. Counted per fact per artifact. Substring matching (as `EpistemicLeakageValidator`) is a lower bound, so report it separately from ref-level lineage exposure.
- **Utility**: fraction of oracle-admissible facts retained in the artifact (guards against over-suppression).
- **Stale-serve**: artifacts reused after one of their source facts became inadmissible.
- **Selector fallback rate** and reasons.
- Report counts with exact binomial intervals; the suite is synthetic, so no population claim is made.

## 6. End-to-end integration test

The standalone selector is not evidence. The check must run the real consumer:

1. Build a constructed database (class X1, X3, X4) into `data/scratch/` with the stub toolchain: `ECHOTALES_LLM_MODE=stub`, `--image-engine stub`.
2. Run `render_panels(..., observer_id=o)` via the CLI path (`echotales --db <scratch.db> render --novel <id> --observer <o> --engine stub`); read `manifest.jsonl` and `render_artifact.jsonl` from the versioned output directory.
3. Apply the oracle to the emitted prompt strings, and to `state_digest` / `plan_digest` for cache identity.
4. Re-run after a store mutation (X8) and verify the cache key changes iff the oracle says a source fact became inadmissible.

For T this requires the production render path to actually call the shared check; for B1 the same run documents today's behaviour. **Audio**: no production voice stage consumes (p, k, o) (`voice/runner.py:198-207`), so an audio end-to-end test is not meaningful until one does. State this as a prerequisite rather than testing a vacuous property.

## 7. Failure analysis and assumptions

- **Raw narration is not filtered.** The director receives the beat's prose; for a character observer that prose contains reader-only information. A fact-level policy cannot remove it. T does not help here unless the prose is regenerated or withheld, which this plan does not test.
- **Prompt-level, not pixel-level.** A clean prompt does not guarantee a clean image. A prior measurement found missing traits are dropped by the generator (12.5% rendered; ledger R9 [HIST]), and the reverse (invented traits) is not measured. A pixel-level claim needs a separate GPU/VLM or human audit and is out of scope.
- **Extraction quality is assumed.** Correct `learned_at`, interval and observer stamps are inputs. Shipped data contains no retractions, no non-READER facts and no relations (inventory section 7), so conclusions are about the policy on constructed stores, not about the corpus.
- **Oracle correctness.** If the oracle and `state_of` disagree in the differential test, resolve that before any comparison.
- **What would falsify the value of the mechanism**: B2 = T on every class; T over-suppresses; A-ablation predictions fail; or X9 shows no case where the shared artifact beats per-consumer filtering.
- **If H holds**, it shows the policy composes and the stale/derived classes need more than routing. It does not show novelty, a quality gain for readers, or any property of generated pixels.

## 8. Resources

| Item | Needs |
|---|---|
| Suite generation, oracle, differential test, B1/B2/B3/T comparison, ablations | CPU only, seconds to minutes, pytest + hypothesis (already in use) |
| End-to-end stub render | CPU only, stub LLM and stub image engine |
| Pixel-level audit, human perception study, real-model director behaviour | GPU and/or API and/or annotators. **Not part of this plan** and not justified before a novelty decision |
| Identity-resolution evidence (C5) | Human adjudication of the existing package. A separate track; this plan does not depend on it |

## 9. Implementation prerequisites (gaps to close before the experiment is meaningful)

1. Specify T (the shared check) and its revalidation rule; today nothing implements it.
2. Make the image path's attribute and brief readers `state_of`-backed (otherwise B1 is the only production comparator and T cannot be exercised end to end). This also fixes D1, D2, P1-P3.
3. Fix `VisualAssetRegistry.register` field loss (P5) and add live revalidation to the selector (P6) before using B3 as a comparator.
4. Populate `EvidenceContext.temporal_certainty` and pass observations in `resolve_alias` (P4) if identity decisions (C5) are to be included.
5. Decide where the experiment lives (`packages/research`, per `CLAUDE.md`) and register it in the research arena; do not edit `DECISION_LOG.md` as part of this proposal.
6. Add at least one modality beyond image that depends on (p, k, o); otherwise cross-modal claims (C6) cannot be tested.
