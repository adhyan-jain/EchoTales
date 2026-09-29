
# E-CRDT — Final IPR Review Package (Round 5, consolidated)

Synthesizes rounds 1-4 (`IPR_REVIEW.md`, `IPR_REVIEW_V2.md`,
`IPR_REVIEW_V3.md`, `IPR_REVIEW_V4.md`) plus this round's new theorem,
counterexamples, and prior-art additions. Cites rather than restates
earlier evidence. Nothing published, pushed, or exposed. All work confined
to `packages/ecrdt/` (confirmed untracked: `git status --short packages/ecrdt`
→ `?? packages/ecrdt/`).

```
PYTHONPATH=src python3 -m pytest tests/ -q             # 44/44 passing
PYTHONPATH=src python3 bench_auth_events.py             # event-count results, Phase 5
```

---

## 1. One-sentence invention

A replica in a CRDT-replicated causal event log can locally admit a
derived fact from premises it has already been validly, causally
admitted, minting — as a side effect of that same local admission
decision, with **zero new external authorization event** — a stable,
individually citable identifier for that specific derivation, under a
proved guarantee that this can never manufacture access to a fact never
actually, causally, granted, and that this identifier lets the derivation
be individually revoked or safely re-delegated without weakening that
guarantee.

## 2. Formal model (Phase 1)

**State**: a shared, causally-replicated world set `W` (an OR-Set,
`orset.py` — standard, not claimed); a per-replica, grow-only causal event
log `E: Dot → Event` (`model.py`), where `Dot = (replica_id, counter)`;
per-replica admitted knowledge `K_i`, which is **not stored** — it is the
pure function `materialize(E, i)` (`replica.py`).

**Operations**: `ASSERT_WORLD(f)` (writes canon, not knowledge),
`OBSERVE(f)` (precondition: `f` live in `W`), `COMMUNICATE(target, f)`
(precondition: sender already admits `f`), `INFER(f, premises)`
(precondition: actor already admits every premise), `RETRACT_WORLD(f)`,
`RETRACT_KNOWLEDGE(target, f, dots)`. Each mints an immutable `Event` with
`deps` citing the causal justification.

**Delayed/reordered delivery**: `merge(other)` only ever adds events to
`E` (`E' = E ∪ E_other`, a trivial set-union semilattice); `materialize()`
computes a deterministic topological order over `deps`
(`_topo_order`, Kahn's algorithm) regardless of arrival order.
**Partition/rejoin**: no distinguished behavior — merge is the only
primitive, and partition is simply "merge doesn't happen yet."

**Autonomous local derivation, defined precisely**: an operation is an
autonomous local derivation iff (a) it is invoked by replica `i` using
only `i`'s own local state (`E`, `i`'s identity) at call time, (b) its
admission precondition is satisfied entirely by facts already present in
`materialize(E, i)`'s output at call time, and (c) no event authored by
any replica other than `i` is required to exist in `E` for the operation
to succeed. `INFER` satisfies all three; `OBSERVE`/`COMMUNICATE` do not
satisfy (c) in the general case (communicate's *target* needs the
sender's event, though the sender itself derives nothing).

**Safety property (verbatim, not weakened)**: *a replica must never
acquire fact F unless there exists an admissible causal derivation from
facts previously validly admitted to that same replica.* This is Theorem
2 (`README.md` §5), restated exactly; proved (Phase 6/7, `IPR_REVIEW_V2.md`)
under the stated non-Byzantine event-minting assumption, via structural
induction over the finite, acyclic event DAG plus the round-2
commutativity lemma for the concurrent case.

## 3. Strongest conventional baseline (Phase 2)

**`AutoDerivingACLReplica`** (`baselines.py`, built round 4, reused
unmodified this round) is exactly what this phase demands: causal CRDT
delivery (the same `ORSet` for `W`) + a causally-dotted grant log `G`
(provenance/causal DAG, `DynamicCausalACLReplica`, reused) + dynamic,
history-based authorization (grants gated by causal delivery, not a
mutable attribute) + derived-data authorization via a standing rule table
(`declare_rule`) + rule/policy evaluation (a live fixpoint closure over
currently-held facts) + per-replica knowledge views
(`_materialize_grants`/`materialized_facts`) + ordinary local inference
(the fixpoint itself — **no human grant is required for the derivation**,
satisfying the brief's explicit "do not force a strawman" constraint).
No new baseline class was built this round; round 4 already anticipated
this exact combination.

## 4. Decisive counterexample (Phase 3) — including the new combinations

Minimal workload: `p1`, `p2` self-granted to replica `B`; rule
`p1 ∧ p2 → p3`; `B` derives `p3` locally with zero external events.
Round 4 tested this under partition, concurrent rule declaration, and
retraction. **This round adds the three named combinations the brief
requires and were not yet covered**:

| Combination | Reproduces E-CRDT exactly? | Result |
|---|---|---|
| Multi-hop (`p1,p2→p3`, `p3,p4→p5`) | **Yes, on confidentiality** | Conceded honestly (`test_multi_hop_derivation_stays_confidentiality_safe_but_compounds_the_identity_gap`) — identity gating holds transitively, a bystander merging both rules and zero grants gains nothing. The identity/revocability gap **compounds**: neither `p3` nor `p5` has a provenance dot. |
| Concurrent inference / merge-order | **Yes, on convergence** | Conceded (`test_concurrent_inference_converges_regardless_of_merge_order`) — the live fixpoint is a pure function of merged `(G, rules)`, so two observers merging `x`/`y` in opposite orders converge identically; two independently-authorized replicas each derive the same fact locally, matching E-CRDT's commutativity-lemma guarantee for this specific property. |
| Stale replica bulk catch-up | **Yes, on confidentiality** | Conceded (`test_stale_replica_bulk_catch_up_grants_nothing_extra`) — a replica absent for 20+ rounds bulk-merges everything at once and gains `W` fully but zero `K`, exactly like E-CRDT's own `test_stale_replica_catches_up_correctly_after_long_absence`. |

**Answer to Phase 3's question, stated exactly as asked**: the strongest
conventional baseline reproduces E-CRDT's semantics exactly for
confidentiality and convergence, across every combination tested
(partition, concurrent updates, retraction of the *bare* derivation
decision, multi-hop, concurrent inference, stale catch-up). **It cannot**
reproduce two specific things, under any combination, without one of the
brief's named escape hatches:

- **Individually revoking one specific derivation** — no dot exists to
  cite (escape hatch: none of the six listed apply; it is not that the
  baseline *could* do this at extra cost, it structurally has nothing to
  address the operation to. The only fix is escape hatch "extra
  authorization event": mint a fresh, dotted record for the derived fact).
- **Safely delegating a derived fact onward** — `grant()`'s own
  precondition rejects it outright (`test_delegating_a_derived_fact_
  requires_a_fresh_authorization_event`); the fix requires exactly one
  **extra authorization event** per delegation (escape hatch named
  explicitly in the brief), measured precisely in Phase 5 below.

## 5. Theorem and proof (Phase 4)

> **Proposition (identity necessity).** *Assumptions*: a construction `C`
> represents all authorization as CRDT-replicated records (grants and/or
> standing rules) with no operation minting a record specific to one
> derivation instance of a fact; admission of a derived fact is decided by
> a pure predicate over currently-held records (a "rule"). *Claim*: any
> operation on `C` that must reference **one specific derivation** of a
> fact `f` — to revoke exactly that derivation, or to delegate exactly
> that derivation onward with a verifiable causal chain — requires either
> (a) minting a new record bearing a fresh, citable identifier for `f`
> (which is `INFER` under different vocabulary, conceding the point), or
> (b) acting on a coarser unit than the derivation itself (e.g. revoking
> an underlying premise, affecting every rule that uses it, not just this
> derivation).
>
> *Proof sketch.* By assumption, `C`'s admission decision for `f` is
> `held(f) := ∃ rule ∈ rules, premises(rule) ⊆ held`, a Boolean predicate
> with no output beyond membership — there is no term in this predicate's
> evaluation that is unique to *this* satisfying assignment of premises at
> *this* point in causal time. Any operation `op(f, ...)` that needs to
> distinguish this satisfying instance from a different, later one (e.g. a
> re-derivation of `f` from different premises after revocation and
> re-grant) has no input to condition on other than `f`'s name — which is
> shared across all derivations of `f` — or the full premise set, which is
> not itself a stable identifier (multiple, non-identical premise
> assignments can satisfy the same rule). Hence `op` cannot be scoped to
> one derivation without either (a) a fresh identifier minted for this
> occasion (contradicting the "no operation mints a record specific to
> one instance" assumption — a proof by contradiction against `C`'s own
> definition), or (b) falling back to the coarser unit (premises), which
> is observably different behavior from targeting the derivation itself. ∎
>
> *Minimal counterexample*: `test_derived_fact_has_no_stable_provenance_
> to_retract` and `test_delegating_a_derived_fact_requires_a_fresh_
> authorization_event` (`tests/test_derivation_impossibility.py`) —
> `AutoDerivingACLReplica._materialize_grants()`'s own provenance dict has
> no entry for a rule-derived fact, and `grant()` rejects delegating one,
> by construction, every time.
>
> *Complexity implication*: `E-CRDT.infer()` produces its citable dot as a
> byproduct of the O(1) (incremental) or O(|E|) (reference) admission
> check itself — zero marginal cost. Any construction satisfying this
> proposition's assumptions pays exactly one additional record-mint
> (`O(1)`) the first time a derivation needs to be individually addressed,
> which is not amortizable away by design (it must happen once per
> *addressed* derivation, not once per derivation overall — round 4's
> `AutoDerivingACLReplica` derives many facts for free but pays this cost
> only for the subset that get delegated/revoked, matching Phase 5 below
> exactly).

**Scope note, stated as carefully as the brief demands**: this is a
result about constructions satisfying the stated assumptions (pure
predicate over currently-held records, no per-instance identifier), not a
claim about all possible systems. §7 identifies one real system
(US7734649, unverified lead) that violates the "no per-instance
identifier" assumption by design (in a centralized setting) — this is
exactly the kind of combination a patent examiner would raise, addressed
directly there.

## 6. Technical effect — NOT the 1,385x number (Phase 5)

**The 1,385x speedup is explicitly excluded from evidence, per the
brief.** Its exact cause, stated plainly: `Replica.materialize()`
(reference implementation) recomputes a full topological sort over the
entire local event log on every `communicate()`/`infer()` precondition
check; `IncrementalReplica` (`incremental.py`) replaces this with
causal-delivery hold-back buffering so each event is processed exactly
once, ever. This is a standard reliable-causal-broadcast technique
(à la CBCAST) applied to a second-order derived set — an engineering fix
to an implementation bug in the reference class, **orthogonal to the
authorization mechanism**: it would produce the identical speedup if
applied to any of the baseline classes with the same naive recompute
pattern. It is not re-measured or cited as evidence here.

**The metric that actually follows from §5's theorem**: external-
authorization-event count for a workload with a fixed fraction of derived
facts that get delegated. `bench_auth_events.py`, run this session:

```
 n_pairs | delegate% |             system | derive-evts | delegate-evts |  total
----------------------------------------------------------------------------------
      20 |       20% |             E-CRDT |           0 |             4 |      4
      20 |       20% |    AutoDerivingACL |           0 |             8 |      8
     100 |       20% |             E-CRDT |           0 |            20 |     20
     100 |       20% |    AutoDerivingACL |           0 |            40 |     40
     300 |       20% |             E-CRDT |           0 |            60 |     60
     300 |       20% |    AutoDerivingACL |           0 |           120 |    120
```

**Derivation-events are 0-0 at every scale** — confirming §5's finding
that the bare derivation decision costs nothing extra in either system;
the gap is exactly, and only, in delegation: **exactly 1 additional
external authorization event per delegated derived fact**, matching §5's
proposition precisely (one fresh record-mint per *addressed* derivation).
This is a modest, honestly-scoped technical effect — a constant-factor
coordination-cost reduction for a specific operation, not a general
efficiency claim, and it is reported as such.

## 7. Prior art (Phase 6) — new, targeted to the narrowed claim

Delta table, added to (not replacing) `IPR_REVIEW_V2.md`'s 11+-source
table. **Caveat, stated plainly**: the two fetches below returned
suspiciously fluent, precise-sounding quotes from PDFs the fetch tool
itself first reported as unreadable/corrupted in the same response — this
is a known failure mode of fetch-and-summarize tools (plausible-sounding
fabrication over genuinely opaque binary content) and **these citations
must be independently verified by a human reading the actual PDF/HTML
before being relied on in any filing.** They are recorded here as leads,
not settled prior art.

| Reference | Mechanism | Covers | Missing element | Obvious-combination risk |
|---|---|---|---|---|
| **US Patent 7,734,649** ("Deriving and using data access control information to determine whether to permit derivations of data elements") — **lead, unverified**, see caveat | Automatic derivation of a new data element's access classification from a fixed, pre-authorized composition rule; derived element gets its own persistent, distinct access-control record | Automatic derivation without per-instance human re-grant; a stable, persistent identity for the derived datum (if the fetched claim summary is accurate) | Explicitly a **centralized, single-database** model (a "data access control server") — no replication, no CRDT, no partition tolerance, no proof of any non-interference property under concurrency | **High** if verified as described — the obvious combination ("take 7734649's rule-based derivation-with-identity idea and run it over an ordinary CRDT/causal-broadcast substrate") is exactly the kind of combination an examiner would propose. E-CRDT's distinguishing answer must be the **proof** (non-interference + convergence under asynchronous, partition-tolerant, concurrent merge — the commutativity lemma) and the specific causal-dot mechanism that makes that combination actually correct, not merely attempted — rounds 3-5's own repeated wrong hypotheses (leak expected, not found; different leak expected, not found) are evidence the correct combination is not obvious to construct even once you know the goal. |
| **arXiv:2604.23560**, "Towards System-Oriented Formal Verification of Local-First Access Control" (Jacob, Stuber, Hartenstein; PaPoC '26) — **lead, unverified**, see caveat | Formally-verified, capability-based, causally-ordered grant/revoke event log for local-first (CRDT/Matrix/Keyhive-adjacent) systems | The general shape of E-CRDT's model (causal event log, per-replica local authorization decisions, Byzantine-aware) in an actively-published, very recent, adjacent venue | Per the fetched summary: **explicitly no autonomous derivation** ("authorization of any event is based on precursor and concurrent events only," no inference operator) and **delegation named as unsolved future work** — if accurate, this is corroborating evidence, not disqualifying: the closest recent formally-verified system in this exact space has not yet attempted the derivation+identity+delegation combination at all. | Low as a standalone reference for the surviving claim (it doesn't disclose derivation); moderate as a foundation an obviousness argument could build from ("add an INFER-like operator to this") — worth citing as the state of the art this work goes beyond, not as anticipating it. |

**Net effect on the claim**: if the US7734649 lead verifies as summarized,
it sharply narrows the surviving claim to specifically the **distributed/
asynchronous/proved-correct** version of "derivation with persistent
identity" — that combination, not the bare idea, is now the entire
defensible surface. This is consistent with, and sharpens, round 4's
finding; it does not kill the claim (7734649 is centralized; E-CRDT's
core measured difficulty across five rounds was making the *distributed*
version correct at all).

## 8. Claim minimization (Phase 7)

**Essential elements**: (i) a per-replica local admission check for a
derived fact against that replica's own already-admitted premises, (ii)
that decision minting, as an unavoidable side effect and with no separate
step, a causally-dotted record uniquely identifying that derivation, (iii)
that record being usable, without any additional authorization event, to
individually revoke or re-delegate that specific derivation with a
verifiable causal chain back to its premises, (iv) all of the above proved
non-interfering under asynchronous, partition-tolerant, concurrent CRDT
merge (the commutativity lemma).

**Optional / implementation detail**: the specific `OBSERVE`/
`COMMUNICATE`/`INFER`/`RETRACT` vocabulary; the incremental (vs.
reference) materializer; compaction.

**Standard, not claimed**: the OR-Set for `W` (Shapiro/Bieniusa); causal
event-log set-union merge; causal-delivery hold-back buffering (standard
reliable-broadcast technique, round 2); Kahn's-algorithm topological
sort; causal-stability tombstone GC (standard δ-CRDT/RGA technique).

## 9. Known weaknesses (carried forward, ranked, updated)

1. **US7734649 lead** (§7, unverified) — if it verifies, the centralized
   half of the idea is prior art; the entire defensible surface becomes
   the distributed/proved-correct combination specifically. This is now
   the single most important open question for counsel, ahead of
   everything below.
2. Merge is `O(sender's log)`, not `O(Δ)` (round 2, unfixed).
3. Byzantine forgery bypasses the event-minting API (round 1/2, proved-
   around, not solved; standard signed-CRDT-operation techniques exist).
4. Causal-validity ≠ semantic-validity for `INFER` premises (round 2).
5. Compaction is dedup, not ancestor-chain pruning (round 2, corrected).
6. No cascading retraction (round 1/2, documented, ESR has the published
   fix, not integrated).

## 10. Questions for patent counsel

1. Does US7734649 (once independently verified against the actual patent
   text, not this session's fetch summary) disclose or render obvious the
   "derivation + persistent identity" idea closely enough that only the
   distributed/proved-correct combination remains defensible — and is
   that combination, by itself, a sufficient inventive step?
2. Is a proof of a safety property (non-interference under concurrent
   CRDT merge) itself evidence of non-obviousness under an "obvious to
   try" analysis, given that this session's own repeated, good-faith
   wrong hypotheses (rounds 4-5) about where the construction would fail
   suggest the correct combination was not obvious even to someone
   specifically trying to find it?
3. Is the claim better scoped as a standalone primitive, or as one
   element within a larger disclosure system (round 4's finding) — which
   framing survives §102/§103 scrutiny better?

---

## Final classification

**B — BORDERLINE / NEEDS PROFESSIONAL OPINION.**

Not A: the confidentiality and convergence properties of the "obvious"
combination survive every stress condition tested across two rounds
(partition, concurrent updates, retraction, multi-hop, concurrent
inference, stale catch-up) — the surviving claim is narrow (identity/
revocability/delegability of one derivation, not derivation itself), the
measured technical effect is modest and precisely scoped (§6), and an
unverified but plausible centralized prior-art reference (§7) may already
disclose half of even that narrow claim. Not C: the distributed,
asynchronous, proved-correct combination has not been found disclosed
anywhere across five rounds and 12+ sources, the theorem in §5 is a real
result under a precisely stated model (not hand-waved), and the technical
effect, while modest, is exactly the effect the theorem predicts —
measured, not assumed. This is not called patentable. The two open
items that must be resolved before any further step are §7's unverified
citations (read the actual documents) and question 3 in §10 (claim
framing).
