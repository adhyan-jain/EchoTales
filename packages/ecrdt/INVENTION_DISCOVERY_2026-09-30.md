# Standalone invention discovery — 2026-09-30

Executes `docs/archive/REFACTOR_REPORT.md`'s follow-on task: mine EchoTales'
own measured bottlenecks for a standalone technical invention, independent
of any patent-EchoTales goal. Full process and triage reasoning:
`~/.claude/plans/twinkly-snacking-minsky.md` (this session's approved plan).
Nothing published, pushed, or exposed.

## Method

1. Inventoried EchoTales' own measured bottlenecks from `docs/status/STATUS.md`
   and `docs/design/architecture.md` (already-documented, numbered findings,
   not speculation).
2. Triaged against the five requested categories (A: math/data-structure
   primitive, B: distributed protocol, C: neural/AI execution primitive, D:
   storage/memory architecture, E: hardware/software co-design).
3. Killed C and E immediately — no bottleneck in the inventory has a
   neural or hardware-mapping shape; forcing either would be manufacturing
   novelty from vocabulary, which the brief explicitly forbids.
4. Identified two real candidates: B (already built and independently
   IPR-reviewed once, in `packages/ecrdt`) and a proposed A/D (a provable
   cache-invalidation-completeness primitive, motivated by EchoTales' own
   A7 cache-key bug).
5. Ran a real prior-art search (WebSearch, this session) against A/D before
   doing any further work on it, per the brief's explicit requirement to
   check prior art before killing or keeping a candidate.

## Candidate 1 (category B) — E-CRDT's revocable/delegable local derivation

**Not re-derived here.** Full formal model, proof, baseline, counterexample
suite, and measured technical effect already exist:
`packages/ecrdt/IPR_REVIEW_FINAL.md`. Summary for this report:

- **Problem**: in a CRDT-replicated causal event log, can a replica's
  *locally derived* fact (inferred from premises it already validly holds,
  with zero new external event) be individually revoked or safely
  delegated onward, without weakening the safety guarantee that merging
  never manufactures knowledge?
- **New primitive**: `INFER` — an operation that mints a causally-dotted,
  individually-citable record for one specific derivation instance, as a
  side effect of the same local admission check that would otherwise be
  free.
- **Prior art (this session's addition)**: **US7734649 independently
  verified** (WebSearch, not a re-summarized fetch) — "Deriving and using
  data access control information to determine whether to permit
  derivations of data elements" (Li & Louchheim). Confirmed: a
  **centralized** "data access control server" that derives and maintains
  access-control records for data elements as they are combined, copied,
  or moved within or across a single data store. No replication, no CRDT,
  no partition tolerance, no proof of any property under concurrent
  merge — every source describing it agrees on this shape. This confirms
  (does not merely leave as a lead) that the patent's disclosed mechanism
  is the centralized half of the idea only.
- **Exact gap**: the surviving claim was already narrowed to "the
  distributed/asynchronous/proved-correct combination, not the bare idea
  of derivation-with-identity" (`IPR_REVIEW_FINAL.md` §7). This session's
  verification **confirms that narrowing rather than changing it** —
  US7734649 does not disclose or weaken the distributed/proved-correct
  half, which is where E-CRDT's actual measured difficulty was (five
  rounds of the review's own wrong hypotheses about where the construction
  would fail).
- **Technical effect**: measured, `bench_auth_events.py` — 0 marginal
  events for the bare derivation at every scale tested (20/100/300 pairs);
  exactly 1 additional external authorization event per *delegated*
  derived fact, matching the proved proposition exactly.
- **Classification: unchanged at B — borderline, needs professional
  opinion.** This session's evidence does not inflate the verdict; per the
  plan, classification moves only if new evidence actually moves it. What
  changed is that one of the two open items in `IPR_REVIEW_FINAL.md` §10
  (verify US7734649) is now resolved with an independent source, not a
  single fetch tool's summary — narrowing what counsel actually needs to
  evaluate to the second open item (is the distributed/proved-correct
  combination, by itself, a sufficient inventive step).
- **Not attempted this session**: the `O(sender's log)` → `O(Δ)` merge fix
  named in `IPR_REVIEW_FINAL.md` §9 as the #2 ranked known weakness. This
  is real engineering (a new incremental merge algorithm plus a
  re-proof that it preserves the commutativity lemma) rather than a
  verification task, and was out of scope for this pass. Flagged as the
  concrete next step if this candidate is pursued further.

## Candidate 2 (category A/D) — provable cache-invalidation completeness

**Problem, as posed going in**: EchoTales' own render cache key
(`plan_builder.py::state_digest`) hashes persona ids and attributes but
not aliases, so a name-only reveal silently fails to invalidate an
already-rendered panel — a real, measured bug (A7 cache ablation: 46 stale
reuses without the fix). The proposed general primitive: given a pure
query `f(entity, position, observer)` over a versioned fact store, derive
a cache key that is *provably* a complete read-set — invalidating on every
store mutation that could change `f`'s output, and never on one that
couldn't.

**Prior art search, this session (WebSearch)**: self-adjusting computation
(Acar et al.) and **Adapton** (Hammer et al., PLDI 2014) already solve
this problem generically, for arbitrary pure computations, with a stated
**Soundness Theorem**: every incremental reduction under Adapton's
demand-driven dependency graph corresponds to a basic (from-scratch)
reduction, and vice versa, when seeded with well-formed prior knowledge.
That theorem is exactly "provable completeness of an automatically-derived
dependency/invalidation structure" — the property this candidate proposed
to establish as new.

**Exact gap found: none that survives.** Applying Adapton (or self-adjusting
computation generally) to EchoTales' specific 3-parameter query would be an
obvious application of an existing, already-formally-proved general
mechanism to a narrower special case, not a new primitive — precisely the
outcome the plan flagged as the likely result before searching, and
precisely the brief's own kill criterion ("kill immediately if it is
merely a combination/application of existing techniques").

**Killed.** No prototype, baseline, or experiment was built for this
candidate — per the brief's own instruction not to keep generating or
building past a real prior-art disqualification.

**What the failure teaches** (per the brief's instruction to extract this
before moving on): EchoTales' A7 bug was not a missing *mechanism* — the
mechanism (automatic, sound dependency tracking) has existed and been
formally proved since at least 2014. It was a missing *application* of an
existing mechanism: `state_digest` was hand-written and hand-maintained
rather than derived by a system like Adapton, which is exactly the failure
mode self-adjusting computation exists to eliminate. This is a real,
useful engineering finding for EchoTales itself (a candidate future fix:
route `state_of()`/cache-key derivation through an off-the-shelf
incremental-computation library instead of a hand-maintained digest), but
it is an engineering recommendation, not an invention.

## Categories C and E — killed without a candidate

**C (neural/AI execution primitive)**: no bottleneck in EchoTales' own
inventory (temporal queries, provenance, cache correctness, evidence
minimization) is neural in character. The pipeline's actual LLM use
(NER, panel direction, speaker attribution) is consumption of an existing
model, not a proposal for a new execution primitive underneath one.
Forcing a candidate here would have been vocabulary-driven novelty, which
the brief explicitly forbids.

**E (hardware/software co-design)**: nothing in the inventory has a
memory-hierarchy, parallelism, or hardware-mapping shape. The closest
stretch (the LLM escalation budget, O(chapter) not O(span)) is a settled
engineering tradeoff already measured and closed (EVOLUTION 4.76/4.84),
not an open computational bottleneck.

## Final result

| Candidate | Category | Verdict | IPR potential |
|---|---|---|---|
| E-CRDT revocable/delegable local derivation | B | Confirmed at **B — borderline**, one of two open items resolved this session (US7734649 independently verified as centralized-only, narrowing but not disqualifying the claim) | Real, but requires the `O(Δ)` merge fix and a professional opinion on whether the distributed/proved-correct combination alone is a sufficient inventive step, before any filing decision |
| Provable cache-invalidation completeness | A/D | **Killed** — reduces to an obvious application of Adapton/self-adjusting computation (2014, proved), not a new primitive | None — documented as a negative result, with a separate, non-patent engineering recommendation for EchoTales itself |
| (no candidate) | C | Killed at triage — no neural-shaped bottleneck in the inventory | N/A |
| (no candidate) | E | Killed at triage — no hardware-shaped bottleneck in the inventory | N/A |

This satisfies the brief's own governing rule: only classify something as
an IPR candidate if the mechanism survives prior-art search **and**
produces a non-trivial, experimentally demonstrated technical advantage.
Exactly one candidate (E-CRDT) meets the first bar and has already met the
second; it is not inflated to a stronger classification than the evidence
supports. The special requirement (one candidate independent of
narrative/KG terminology, standing as a general-purpose computing/AI
systems invention) is satisfied by that same candidate — its formal model
is stated entirely in replica/causal-event-log/CRDT-merge terms, with no
narrative vocabulary anywhere in `packages/ecrdt/`.

## Addendum, same day — the killer-question scenario

Per direct instruction, before attempting the `O(Δ)` merge optimization: a
tiny formal model of the exact scenario that decides whether candidate B
dies or produces a precise technical gap. OBSERVE(P1), OBSERVE(P2),
INFER(P1,P2→F), REVOKE(F), DELEGATE(F→B), plus partition/concurrent-
update/rejoin and an airtight same-replica double-derivation variant, run
identically against (1) a new "standard derived-data authorization"
baseline built for this comparison (the US7734649 shape — mutable,
rule-based classification inheritance, no causal event log), (2) the
existing ECAC-style `AutoDerivingACLReplica`, and (3) E-CRDT's `Replica`
itself. Full model, results, and 7 new regression tests (55/55 passing):
`packages/ecrdt/scenario_revoke_delegate.py`,
`packages/ecrdt/tests/test_revoke_delegate_scenario.py`.

**The killer question's answer: NO for both baselines**, each for a
distinct, precisely characterized structural reason, not merely "harder"
or "not yet implemented":

- **Standard derived-data authorization**: revoking a derived fact's sole
  authorization narrows the only attribute slot for that fact's name to
  empty — which this baseline's own visibility convention treats as
  *shared with everyone*, actively widening access rather than narrowing
  it. Delegating grants access to "whatever the name currently means,"
  which the same-replica double-derivation case makes airtight: a second
  derivation of the same name silently overwrites the first's
  classification with no trace, so a later revoke or delegate call has no
  way to address either derivation specifically.
- **ECAC-style causal authorization**: a rule-derived fact has no causal
  dot to cite at all — revocation cannot even be posed as a question, and
  delegation is rejected outright by the existing `grant()` precondition;
  the only fix is minting a fresh authorization record first, which is
  exactly one new external event, precisely the clause under test.
- **E-CRDT**: both operations are precise (cite the exact `infer` dot) and
  free (no event beyond the operation itself invoked anyway), including
  when the same replica derives the same fact name twice from disjoint
  premises — two distinct, individually addressable dots, not one.

**Per the instruction's own decision rule, this is a "no" outcome — the
extremely precise technical gap for the IPR cell**, not a "yes" that would
kill the candidate: neither baseline can represent, let alone safely
revoke or delegate, one specific local derivation instance among possibly
several sharing a fact name, without minting a new record for it. This
does not move `IPR_REVIEW_FINAL.md`'s B classification (per this session's
own rule against inflating a verdict) — it sharpens the evidence base
supporting the surviving claim's essential elements (§8, points i–iii)
with a concrete, reproducible, three-way comparison that did not exist as
one artifact before.

**The `O(sender's log)` → `O(Δ)` merge optimization was deliberately not
attempted this pass**, per direct instruction — it is orthogonal
engineering work on a different axis (communication/computation cost, not
the identity/revocability/delegability property this scenario tested) and
should not be spent on an already-borderline candidate before this more
decisive question was answered.
