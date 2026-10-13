# Novelty decision — 2026-10-13

## Decision: **NARROW**, trending NO-GO for a stand-alone formal-methods paper

The original framing — "a revision-safe compiler from narrative state to multimodal output with correctness guarantees" —
**does not survive** as stated. What survives is a small, honest core (C-A, optionally C-B in CONTRIBUTION_LEDGER) that is
a sound *specification and verification* contribution, not a new-algorithm contribution.

## Gate, criterion by criterion

| # | Criterion | Result | Basis |
|---|---|---|---|
| 1 | A specific limitation in the closest prior systems shown from primary sources or executable behavior | **Pass, modest** | NWM §3.5/App. A: chapter hard filter, no retraction, no observer-scoped retrieval, no stated property (HTML read). Graphiti source `edge_operations.py` L748-783: supersession sets `invalid_at` and `expired_at` together; no observer concept (grep). CineCrew §3.3 / CANVAS §3.2 / DramaAgent §3.4: no knowledge scoping, no invalidation/dependency model. These are *absences in the papers/code*; none was executed |
| 2 | EchoTales can address it with a precise formal or algorithmic contribution | **Partial** | The semantics and T1-T3 are statable and provable. But EchoTales **itself violates them** on the image path (D1, D2, D7, D8; 51% differential-test violations on adversarial stores), so the contribution is half-implemented |
| 3 | Properties are not simply standard consequences of database or build-system techniques | **Fail** for T1-T3 and P4/P5 | T1 = snapshot reads; T2 = transaction-time closure; T3 = incremental reads at a version; P4 = content addressing / Adapton (already killed in `packages/ecrdt/INVENTION_DISCOVERY_2026-09-30.md`); P5 = single constructor |
| 4 | At least one important property admits real formal reasoning | **Pass, weakly** | T1 has a complete four-case proof; it is short because the property is simple |
| 5 | Implementable and demonstrable without a human study, training, or expensive generation | **Pass** | all checks are model-free (`probes/`); the cost is engineering time, no GPU |
| 6 | Novelty survives comparison with the closest prior work | **Fail as a primary claim; survives as a composition** | NWM already separates reveal from event order and filters by chapter; the remaining difference is observer-indexed witness semantics + positional retraction + spec-level uncertainty + a stated property |

Criterion 3 is decisive. The brief asks for a contribution beyond "standard consequences of existing database or
build-system techniques". Everything provable here is such a consequence.

## What survives, stated narrowly

A semantics in which (i) a character observer sees a reader-stamped fact only through a witness row; (ii) retraction is a
position, not an interval end; (iii) uncertain valid time is three-valued and the uncertainty is preserved into the
generation specification; with (iv) a proved prefix-faithfulness theorem and (v) a model-free differential harness that
detects violations in a working multimodal pipeline (it found four real defects in this one).

## Why a reviewer would reject a paper on it

1. "Snapshot reads over an append-only log; bitemporal retraction; both textbook." (T1-T3.)
2. "No real data exercises the novel parts": shipped DBs have 0 retractions, 0 retrospective persona facts, 0-12 observation
   rows (audit D4). Every retraction/observer result would be synthetic.
3. "The guarantee stops at the specification." The image may ignore the prompt; extraction may be wrong. The paper cannot
   claim end-to-end correctness, and the guarantees are relative to an unverified extractor.
4. "The system violates its own theorems" until M1-M4 are done, and the headline defect rate (51%) comes from adversarial
   random stores, not from the product.
5. NWM (Jul 2026) is a near neighbour that already published the cutoff / reveal-order ideas.
6. Novelty of C-B rests on an unverified conjecture and a small literature search (about 20 queries, mostly snippets).

## Where it could land

A workshop or short paper (narrative/creative AI, or a PL/DB workshop on provenance for generative pipelines), a thesis
chapter, or an engineering report. **I do not recommend** building a month-long paper around this as a primary
formal-methods contribution. The decision would change to GO only if one of these appeared: (a) a real corpus with
non-trivial retraction/observer structure, (b) a theorem beyond snapshot reads (for example a decidable characterization of
which corrections can affect which cutoffs under a tri-temporal model), or (c) the label discipline finding leaks that the
property test cannot.

## Smallest next implementation step

Stage 0 in IMPLEMENTATION_PLAN.md: turn `probes/prop_cutoff.py` into a permanent `pytest` property test (it currently
shows 51% violations on the render path, so it starts red), then fix M1 by routing the persona reader through
`StateResolver.state_of` and re-run. It is small, falsifiable, needs no GPU, and either confirms the model is worth
continuing or exposes more violations. No production code was changed to reach this decision.
