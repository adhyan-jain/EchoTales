# E-CRDT — IPR Review Package

Standalone research prototype in `packages/ecrdt/`. Not published, pushed,
or exposed anywhere outside this local checkout. This document is the
Phase 1-7 audit requested to decide **KILL** vs **IPR REVIEW CANDIDATE**;
`README.md` in this same directory remains the technical reference (formal
model §1-6 there are superseded/tightened by §6 below where the two
disagree — this document is authoritative on anything corrected here).

Run everything yourself:
```
cd packages/ecrdt
PYTHONPATH=src python3 -m pytest tests/ -q                # 26/26 passing
PYTHONPATH=src python3 -m ecrdt.bench                      # safety/efficiency vs baselines
PYTHONPATH=src python3 bench_scaling.py                    # Phase 3 scaling (writes scaling_results/)
PYTHONPATH=src python3 ablation_bench.py                   # Phase 4 ablations
PYTHONPATH=. python3 examples/echotales_demo.py             # Phase 7 demonstrator
```

---

## PHASE 1 — Audit of the actual invention (traced from code, not the README)

**Files**: `orset.py`, `model.py`, `replica.py`, `compaction.py`, `baselines.py`, `audit.py`.

### State representation
- `W: ORSet` — `elements: Dict[fact_id, Set[Dot]]`, `context: Dict[replica_id, int]`
  (a version vector). Standard add-wins causal OR-Set (`orset.py:17-83`).
- `E: Dict[Dot, Event]` per replica — a grow-only dict keyed by
  `Dot = (replica_id, counter)`. `Event` (`model.py:32-47`) is a frozen
  dataclass: `(dot, kind, fact, actor, target: Optional[str], deps: FrozenSet[Dot])`.
- `K_i` — **not a field**. It does not exist as stored state anywhere.
  It is the return value of `Replica.materialize()`, memoized behind a
  `_dirty` flag added this session (`replica.py:52-95, 148-192`).

### Operation types (exact preconditions, as implemented, `replica.py:67-139`)
| Op | Precondition (checked by the issuing replica's own call) | Effect |
|---|---|---|
| `assert_world(f)` | none | `W.add(f, new_dot)`; `E[dot] = Event(kind=assert_world, deps=∅)` |
| `observe(f)` | `W.contains(f)` | `E[dot] = Event(kind=observe, actor=me, deps=W.live_dots(f))` |
| `communicate(target, f)` | `f ∈ materialize().known` (i.e. `self.knows(f)`) | `E[dot] = Event(kind=communicate, actor=me, target=target, deps=my own establishing dots for f)` |
| `infer(f, premises)` | all `premises ⊆ materialize().known` | `E[dot] = Event(kind=infer, actor=me, deps=union of my establishing dots for each premise)` |
| `retract_world(f)` | `W.live_dots(f)` non-empty | `E[dot] = Event(kind=retract_world, deps=dots being retracted)`; `W.remove(f, dots)` |
| `retract_knowledge(target, f, dots)` | none enforced by this API (caller supplies `dots`) | `E[dot] = Event(kind=retract_knowledge, target=target, deps=dots)` |

### Causal-DAG semantics
`deps` on an event is **not** a generic "happened-before" marker (unlike a
vector clock, which orders *all* operations uniformly). It specifically
encodes *which of the actor's own prior establishing events justify this
one*. `_topo_order` (`replica.py:28-49`, Kahn's algorithm, ties broken by
dot) turns `E` into a deterministic processing order; a missing dependency
(not yet delivered) is silently treated as "no edge," which is safe **only**
because admission for `infer` is separately re-checked against
`ever_established` membership (see below) — for `observe`/`communicate`
there is no dependency check at all at materialization time (see Phase 1
finding below).

### Materialization algorithm (`replica.py:148-176`) — this is the actual invention
```
established = {}            # fact -> set of MY establishing dots
ever_established = set()    # dots I've admitted, for infer's closure check
for e in topo_order(E):
    if e.kind == observe      and e.actor  == me: admit(e)
    if e.kind == communicate  and e.target == me: admit(e)
    if e.kind == infer        and e.actor  == me and e.deps ⊆ ever_established: admit(e)
    if e.kind == retract_knowledge and e.target == me: established[e.fact] -= e.deps
K_me = {f : established[f] non-empty}
```
**Finding, stated precisely**: only `infer`'s admission actually re-verifies
its `deps` against reality at materialization time. `observe` and
`communicate` admission is gated **solely by `(kind, actor|target) == me`
matching** — the `deps` field they carry is stored provenance (used by
`communicate()`'s own precondition check when the *sending* replica later
tries to relay the fact further, and by compaction), not a verification
predicate the *receiving* replica re-checks. This is precisely why the
Byzantine test in Phase 2 succeeds at forging a `communicate` event but the
forged-`infer` test fails: the closure check is real but narrower in scope
than it might appear from the README's prose. This is the single most
important thing to get right in a claim: **the causal-gating mechanism is
"admit if I am the recorded subject/addressee of this event kind,"
not "cryptographically or structurally verify the entire disclosure chain
on every read."** The latter is what compaction and the honest-workload
proof rely on being true by construction (events are only minted by the
issuing replica's own checked API) — not something materialize() re-derives
independently. This distinction belongs in the patent claim language.

### Merge algorithm (`replica.py:142-145`)
```
W  <- W.join(other.W)              # standard OR-Set join
E  <- E ∪ other.E                  # dict union (new dots only; existing kept)
```
That's the entire merge function. It never touches `K` (nothing to touch —
`K` isn't stored). This is the structural core of the design: **merge is
defined entirely over `(W, E)`, and `K` is only ever produced by a pure
projection run locally, per replica, on demand.**

### Compaction algorithm (`compaction.py`)
1. `causally_stable(E, replica_ids, seen)`: a dot `(origin, c)` is stable
   iff every replica's `event_context()` high-watermark for `origin` is
   `>= c`.
2. `compact_for_target(E, target, stable)`: for each fact, among stable
   events terminal for `target` (`observe`/`infer` with `actor==target`,
   or `communicate` with `target==target`), keep only the earliest
   (by dot) and rewrite it with `deps=frozenset()` (dot preserved, so a
   future `retract_knowledge` referencing that dot still resolves).
   Non-stable or non-terminal-for-target events pass through unchanged.

Measured (chain-heavy synthetic run, 6 replicas, single target's log after
fix described in Phase 1 addendum below): **158 → 144 events (−8.9%),
9,933 → 8,595 bytes (−13.5%)**, in a deliberately short run; the fraction
compactable grows with run length as more chains stabilize.

**Bug found and fixed this session**: the original `run_compaction_demo`
never called `.observe()` in its chain-construction loop (dead code left
the call unreachable), so the first run measured 0% compaction — not
because compaction doesn't work, but because no events were ever eligible.
Confirmed as a test-harness bug, not an algorithm bug, by fixing it and
re-measuring (numbers above are post-fix).

### Knowledge-admission rule, stated once, precisely
> Replica `i` materializes fact `f` into `K_i` if and only if the causal
> event log contains an event `e` with `e.fact == f` and either
> (`e.kind ∈ {observe, infer}` and `e.actor == i`) or
> (`e.kind == communicate` and `e.target == i`), and, for `infer` only,
> every dependency of `e` is itself a dot that was, at some point,
> admitted for `i` by this same rule — and `f` is subsequently removed
> from `K_i` only by a `retract_knowledge` event targeting `i` whose
> `deps` intersect `f`'s live establishing dots (add-wins).

### What makes it different from ordinary CRDT + ACL + provenance
- **vs. plain CRDT**: a plain CRDT has no second structure at all —
  `K_i := W` by definition. E-CRDT adds a second, independently-computed
  set derived from a *different* input (the event DAG, projected by
  identity) rather than reading `W` directly.
- **vs. ACL**: an ACL checks a **mutable attribute stored on the fact**
  (`scope`, `visible_to`) against the *current* store, at *read* time.
  E-CRDT's admission rule has no such attribute anywhere — it is a
  structural match against **immutable historical events**. There is
  nothing to "widen" after the fact; the only way to grant new knowledge
  is to mint a new, causally-ordered event.
- **vs. "just provenance/access control"**: in most provenance systems,
  provenance is descriptive metadata attached to data for audit — it does
  not *gate* what's readable, a separate access-control layer does. Here,
  the causal-DAG events **are** the sole mechanism that determines
  membership in `K_i`; there is no separate authorization check anywhere
  in the code. Delete the provenance/event layer and there is no
  mechanism left to compute `K_i` at all — it isn't a bolt-on.
- **vs. vector clocks**: a vector clock is a scalar summary per replica
  used to compare *event order*. `deps` here is per-event and used to
  answer a completely different question — "was fact `g` established for
  *this specific actor* before this event" — which a vector clock cannot
  express (it has no notion of per-fact, per-actor establishment).

### Minimum mechanism that would have to appear in a patent claim
1. A replicated state comprising (a) a converged fact-set `W` under a
   standard CRDT join, and (b) a grow-only, freely-replicated log of
   typed, dependency-annotated events `E`.
2. A **materialization function**, local to each replica, that computes
   replica `i`'s admissible knowledge set as the subset of `E` whose
   events name `i` as subject (`observe`/`infer`) or addressee
   (`communicate`), recursively requiring (for derivation-type events)
   that all cited dependencies were themselves previously admitted for
   that same replica — such that **no other code path exists** by which
   `W`'s content or another replica's admitted set can populate `K_i`.
3. A **compaction step** gated on causal stability that collapses a
   multi-hop admitted chain into a single terminal event per (fact,
   target), preserving the event's identity (dot) for future retraction
   while discarding intermediate history, safe only post-stability.

Everything else (the specific OR-Set construction, the exact event kinds
chosen, the Python data layout) is implementation detail, not the claim.

---

## PHASE 2 — Breaking the safety claim (`tests/test_adversarial.py`, 14 tests, all passing)

Adversarial coverage, one test per required scenario:

| Scenario | Test | Result |
|---|---|---|
| Concurrent OBSERVE of same fact, two replicas | `test_concurrent_observe_of_same_fact_by_two_replicas` | Holds — each replica's own observe is independent; a third replica merging both still learns nothing |
| Concurrent COMMUNICATE, different senders, same fact | `test_concurrent_communicate_same_fact_different_senders` | Holds — target ends up with both provenance dots, no double-grant error |
| Concurrent assert + retract of same fact | `test_concurrent_assert_and_retract_of_same_fact_add_wins` | Holds — standard add-wins OR-Set semantics, correctly inherited |
| World convergence under 400 random concurrent assert/retract/merge ops | `test_world_convergence_under_arbitrary_concurrent_ops` | Holds |
| Out-of-order / delayed delivery (infer arrives before its premise) | `test_out_of_order_delivery_self_heals_once_dependency_arrives` | Holds — not admitted early, self-heals once dependency lands, **because materialize() is a full, non-cached-per-dot recompute**; this is the flip side of the Phase 3 scaling weakness — correctness and the scaling problem share the same root cause |
| Duplicate merge (idempotence) | `test_duplicate_merge_is_idempotent` | Holds |
| Reordered merge (A-then-B vs B-then-A) | `test_reordered_merge_converges_same_as_in_order` | Holds |
| Stale replica, 20-round absence, bulk catch-up | `test_stale_replica_catches_up_correctly_after_long_absence` | Holds — world catches up fully; **K stays empty**, exactly as required (bulk `W`/`E` merge alone grants nothing) |
| Partition (2 groups, 15 rounds) then rejoin | `test_partition_then_rejoin_preserves_epistemic_boundaries` | Holds — audited against independent ground truth, 0 violations |
| Multi-hop transfer (4-hop chain) + bystander | `test_multi_hop_knowledge_transfer_reaches_only_the_chain` | Holds — bystander gets full `W` convergence but 0 `K` |
| Deep inference chain (depth 10) | `test_deep_inference_chain` | Holds |
| Retracting a premise after downstream inference | `test_retracting_a_premise_does_not_cascade_to_prior_inferences_documented_limitation` | **Does not cascade** — documented as a real limitation, not silently assumed (see Phase 5/6 note on ESR's superior cascading-rollback mechanism) |
| Byzantine: forged `communicate` event (bypasses API) | `test_byzantine_forged_communicate_event_breaks_the_guarantee_as_documented` | **Breaks, as expected and documented** — confirms Theorem 2's non-Byzantine scope precisely, does not silently hold |
| Byzantine: forged `infer` event with fabricated deps | `test_infer_event_with_forged_deps_is_still_rejected_by_the_closure_check` | Holds — `infer`'s closure check is real, independent of the API |

**Differential comparison against baselines**: folded into Phase 4 (ablation
harness reuses the same audit mechanism against `NaiveUnionReplica`/`ACLReplica`)
rather than duplicated here.

**Honest conclusion of Phase 2**: the safety claim holds for every
concurrency/ordering/retraction/partition scenario tested, under the
explicitly stated non-Byzantine threat model. It does **not** hold against
a replica that bypasses its own API to mint `observe`/`communicate` events
directly — this is a real, confirmed boundary, not a hypothetical one, and
any patent claim or deployment note must state it as such. `infer`'s
closure check is comparatively more robust (fails closed even under direct
forgery) — an asymmetry worth closing in a production version (see Phase 6).

---

## PHASE 3 — Scaling / technical-effect benchmark (`bench_scaling.py`)

Three experiments, kept separate because they isolate different layers.
**1M+ ops was not run** — see honest finding below for why, and what was
measured instead to characterize the trend.

### Experiment A — world-only (`W` layer), up to 100,000 ops
| system | n | update_total_s | merge_s | W bytes |
|---|---|---|---|---|
| ecrdt | 100,000 | 0.326 | 0.197 | 1,200,012 |
| naive | 100,000 | 0.128 | 0.158 | 1,200,012 |
| acl | 100,000 | 0.213 | 0.235 | 1,200,012 |

Near-linear in all three (ecrdt ≈1.5-2.5x naive's constant, from the extra
event bookkeeping — same asymptotic order, not a different complexity
class). **The `W` layer imposes no algorithmic penalty vs. baselines**,
confirming Theorem 1's machinery is shared, cheap infrastructure.

### Experiment B — epistemic (materialize-heavy) workload
| n | total_s | avg_op_us | single materialize (cold) | full_recomputes |
|---|---|---|---|---|
| 200 | 0.022 | 37 | 799 us | 68 |
| 500 | 0.256 | 171 | 4,296 us | 168 |
| 1,000 | 1.947 | 649 | 15,921 us | 335 |
| 2,000 | 13.124 | 2,187 | 56,447 us | 668 |

**Honest finding, not softened**: cumulative time grows ~6.7x for a 2x
increase in `n` (1,000 → 2,000), i.e. empirically **~O(n^2.7-2.9)**, not
the `O(Δ)` amortized cost the README's complexity table describes as the
*design target*. Root cause, traced precisely: `communicate()` and
`infer()` call `materialize()` internally to check their precondition;
every such call finds `E` dirty (the previous op just mutated it) and
re-runs a full `O(|E| log |E|)` topological sort (`_topo_order`'s
`ready.sort()` after every pop) over the *entire* local log, not just the
new events. **This is the single clearest, most important limitation of
the current implementation** and directly answers "does E-CRDT have a
measurable technical advantage, not merely better semantics": **on
communicate/infer-heavy workloads, as currently implemented, it does
not — it is currently slower than a real production system would need,
purely from an un-implemented optimization** (delta-incremental
materialization with a pending-dependency watermark queue — the natural
fix, given the self-healing behavior confirmed in Phase 2, is non-trivial
to get right, which is why it wasn't attempted under this session's time
budget rather than treated as easy). This is precisely why 1M+ ops was
not attempted for this workload shape: extrapolating the measured
exponent, it would not complete in a reasonable time on this machine, and
running it anyway to produce a number would misrepresent an engineering
gap as an algorithmic one.

### Experiment C — agent-count scaling (200 ops/agent, 5 rounds random-pair gossip)
| agents | update_total_s | gossip (5 rounds) s | merges | avg \|E\| per replica |
|---|---|---|---|---|
| 2 | 0.001 | 0.003 | 10 | 800 |
| 10 | 0.006 | 0.055 | 50 | 4,000 |
| 50 | 0.029 | 0.641 | 250 | 9,920 |
| 100 | 0.066 | 1.695 | 500 | 11,392 |

Grows with agent count mainly because a full-shuffle random-pairing gossip
schedule does `O(agents)` merges per round regardless of topology — a
benchmark-harness artifact (a real gossip protocol would use `O(log n)`
fanout), not a property of the algorithm; flagged so it isn't
misattributed.

### Technical-effect verdict for Phase 3
- **World-layer**: no measurable disadvantage vs. baselines at 100K ops. ✅.
- **Epistemic layer**: **measurable disadvantage** in the current
  implementation for admission-heavy workloads, caused by a specific,
  named, fixable engineering gap (non-incremental materialize), not by
  the algorithm's asymptotic design. State this plainly: **the invention's
  claimed complexity class (`O(Δ)` amortized) is a design target verified
  only for the world layer and for read-mostly epistemic workloads in
  this prototype; it is not yet achieved for write-heavy epistemic
  workloads as implemented.**

---

## PHASE 4 — Ablations (`ablations.py`, `ablation_bench.py`)

Clean workload (6 replicas, 40 facts, 10 rounds, honest ops only), audited
unauthorized-knowledge-propagation count:

| Variant | Leaks (clean workload) | Forged-`infer`-event admitted? |
|---|---|---|
| **F — full E-CRDT** | **0** | **No** |
| **C — no provenance-closure check** (infer admitted by actor match alone) | 0 | **Yes** |
| **A — naive union** (`K_i := W`) | 99 | n/a |
| **B — static ACL** (per-creator scope, no widening in this run) | 0 | n/a |
| **E — flat per-agent CRDT** (`K` itself replicated as an OR-Set, freely merged) | 58 | n/a |

**What this isolates, precisely**:
- **Causal-DAG gating by actor/target identity (present in F, C, absent in
  A, E) is what eliminates the bulk of leaks** — 99 → 0 (naive) and
  58 → 0 (flat-per-agent-CRDT) both collapse to zero once admission is
  gated by "am I the recorded subject/addressee," independent of whether
  provenance is separately verified. This is the dominant mechanism.
- **Provenance-closure verification (present only in F) is a distinct,
  second mechanism** that specifically stops forged/invalid derivation
  claims — it makes no difference under honest workloads (C matches F at
  0 leaks) but is the only thing standing between "admitted" and
  "rejected" once an event is forged, confirmed directly by the
  forged-event column.
- **B (static ACL) shows 0 leaks in this particular clean run** — because
  this run never widens scope after creation. This is *not* a
  contradiction of the earlier README finding; it precisely confirms that
  ACL's failure mode is specific to the retroactive-attribute-mutation
  scenario (README §4/§7), not to ordinary concurrent operation. Stating
  both results side by side (rather than only the worse one) is the
  honest picture: **ACL and E-CRDT are behaviorally identical under
  static, never-changed scopes; they diverge exactly and only when a
  scope is later widened**, which is the crux of the novelty claim, not
  a peripheral detail.
- **E (flat per-agent CRDT)** demonstrates that merely *having a separate
  `K` structure* is not sufficient — if that structure is itself freely
  merged like any other CRDT set (the "obvious" naive combination),
  facts still leak (58/leaks) because a replica's local learning gets
  unioned into every peer it syncs with. **The causal-DAG *projection*
  step (F), not the existence of a second data structure, is what does
  the work.**

**Ablation D (no compaction)** is not a safety ablation (compaction never
changes materialized `K`, by Theorem 4) — its effect is purely on
metadata size, already measured directly (§ Phase 1 compaction numbers:
−8.9% events / −13.5% bytes with compaction vs. without, in the same
run).

---

## PHASE 5 — Prior-art / claim chart

Element-by-element table. "Anticipated" = this reference discloses this
element in substantially the same form. "Overlapping" = related but
differs in a load-bearing way. "Distinguishing" = not found in any
reference searched.

| Element | E-CRDT (this work) | Ritschel provisional (USPTO 64/012,284, full claims read) | "Epistemic State Replication" (arXiv:2607.09748, ESR) | Secure/MPC CRDTs | Policy-CRDT | Non-uniform Replication (arXiv:1711.07733) | Matrix Event Graph |
|---|---|---|---|---|---|---|---|
| Converged world/fact state under CRDT join | Yes — causal OR-Set `W` | No — single centralized append-only log + vector/graph index, not multi-replica CRDT | Partial — `ℒ` (evidence log) is append-only and shared, but via classical consensus, not a CRDT join | Yes (that's the whole paper) | Yes (policy objects are CRDTs) | Yes (per-replica subsets of one CRDT) | Yes (append-only causal event graph) |
| **Per-replica materialized subset gated by causal disclosure identity, not by attribute** | **Yes — the core mechanism** | **No — `scope`/`owner_id` is a static attribute checked at read time** | No — ESR's `ℬ` (belief lineage) is meant to *converge* across all correct replicas (agreement axis), not diverge by design | No — confidentiality is at the crypto/MPC layer, not per-agent epistemic scoping | **No — this is exactly the ACL pattern**, replicated as a CRDT but still an attribute check | Partial — replicas store different subsets for *storage-efficiency/query-locality* reasons, not epistemic confidentiality; no disclosure-event gating found in the abstract-level material reviewed | No — every room member sees the full event graph for rooms they're in; no per-member divergence modeled |
| Confidence-weighted contradiction reconciliation | No (not attempted; out of scope) | **Yes — the "primary novel component" of that filing** | Partial (contradiction detection triggers a resolving Cognitive Transaction) | No | No | No | No |
| Cascading retraction (descendant beliefs auto-revised) | **No — documented limitation (Phase 2)** | No | **Yes — Semantic Rollback Operator, `VB' = VB \ ({p} ∪ Desc(p))`, with Partial-Dependency Repair** | No | No | No | No |
| Compaction of provenance/causal metadata gated by stability | **Yes — `causally_stable` + `compact_for_target`** | No (append-only log, no compaction described) | **No — explicitly: "no compaction mechanism is described... lineage retained indefinitely"** | No | No | Not found in material reviewed | No |
| Formal non-interference proof (merge cannot manufacture knowledge) | **Yes — Theorem 2, proved + empirically checked (300-op randomized differential test, 0 violations)** | No (not attempted; not the paper's goal) | No (goal is agreement, not confidentiality) | No (different axis) | No (assumes the policy object correctly captures who should see what; does not prove the converse) | No | No |

**Anticipated elements**: converged shared CRDT state (Shapiro et al.,
reused unmodified); attribute-based scope checked at read time (Ritschel,
Policy-CRDT); confidence-weighted reconciliation of contradictory claims
(Ritschel — closest art for that specific mechanism, not used here);
cascading belief revision on retraction (ESR — closest art for that
mechanism, **absent** here, a genuine gap in this work relative to ESR).

**Overlapping elements**: "dual state split into world/belief" framing
(Ritschel's semantic/causal split, ESR's `(ℒ, ℬ)` split) — the *framing*
of splitting state into two layers is not, by itself, new; what's claimed
here is specifically the *gating rule* for the second layer.

**Genuinely distinguishing elements** (not found in any reference
searched, across the original 8-source review plus this session's 3
additional targeted searches): (1) knowledge materialized as a pure
projection of a shared, freely-replicated causal event DAG, gated by
subject/addressee identity match rather than an attribute predicate;
(2) the specific claim that this makes retroactive attribute changes
structurally incapable of granting historical knowledge (no attribute
exists to change); (3) causal-stability-gated compaction of that event
DAG that preserves the admission verdict while discarding chain detail.

**Obvious-combination risk, stated honestly**: a sharp reviewer could
argue "CRDT event log (well known) + per-actor filter on read (a
one-line idea once you have the event log)" is an obvious combination of
two known techniques, especially once Ritschel (scope-per-record) and
partial-replication CRDTs (subscribe-by-interest) are both prior art
establishing that *someone* filters *something* at replication time. The
counter is narrow and specific: the mechanism is not "filter by declared
interest/attribute" but "admit by matching event-subject identity against
immutable history," and the non-interference *proof* (nothing found
anywhere in the prior art searched attempts or achieves this proof) is
what elevates it above an obvious combination — a claim resting on the
mechanism-plus-proof pairing is defensible; a claim resting on the
mechanism alone is a real risk of an obviousness rejection.

---

## PHASE 6 — Formalization (honestly corrected against Phase 2/3 findings)

- **World convergence** — **Proved**, unconditionally (standard OR-Set
  join-semilattice argument, unchanged from README §5 Theorem 1).
- **Epistemic non-interference** — **Proved, conditional on the stated
  non-Byzantine threat model.** Phase 2 empirically confirms both the
  positive claim (0/300 violations under honest concurrent/adversarial-
  but-non-Byzantine workloads, plus 0 across every named scenario in the
  Phase 2 table) and the boundary (a direct-construction forged
  `communicate` event defeats it, exactly as the proof's precondition
  requires). **Correction to README's proof sketch**: the proof's
  induction step implicitly assumed every admission check (`observe`,
  `communicate`, `infer`) re-verifies its precondition at materialization
  time; Phase 1's trace shows only `infer` actually does. The proof still
  holds, but its true dependency is **"all events in `E` were minted by
  the API,"** not **"materialize() independently re-derives validity"** —
  a meaningfully different (weaker, and now precisely stated) premise.
- **Correct knowledge propagation** (communicate/infer reach exactly the
  intended target, not more) — **Proved and empirically confirmed**
  (Phase 2 multi-hop and bystander tests).
- **Concurrent-update convergence** — **Proved and empirically confirmed**
  (Phase 2, 400-op randomized test + partition/rejoin test).
- **Compaction soundness** — **Proved for the stability-gated case**,
  **empirically confirmed** post-bugfix (Phase 1 addendum). Not proved
  (not attempted) for a variant that compacts *non-terminal* intermediate
  events shared by multiple targets' chains simultaneously — the current
  algorithm only compacts per-target, independently, which is sound but
  leaves cross-target dedup on the table as future work, marked
  honestly rather than claimed.
- **Cascading retraction of derived facts** — **Not proved; not
  implemented.** Explicitly a limitation (Phase 2), with ESR's
  descendant-pruning operator identified as the closest published
  mechanism for closing this gap, should a stronger version be built.

### Complexity — corrected against Phase 3 measurement, not just derived

| Operation | Design-target complexity | **As actually implemented, measured this session** |
|---|---|---|
| `assert_world` / `retract_world` | O(1) amortized | **Matches** — Experiment A, near-linear to 100K |
| `merge` (W only) | O(\|ΔW\|) | **Matches** |
| `observe` | O(1) (only touches `W`, no materialize call) | **Matches** |
| `communicate` / `infer` | O(Δ) amortized (delta-incremental) | **Does not match** — O(\|E\| log \|E\|) per call in the current non-incremental implementation, confirmed empirically ~O(n^2.7-2.9) cumulative over n admission-heavy ops (Experiment B) |
| `materialize` (query) | O(Δ) amortized with the memoization cache added this session | **Matches for repeated reads of unchanged state** (O(1)); **does not match** for the first read after any mutation (full O(\|E\| log \|E\|) recompute) |
| `compaction` | O(\|E\|) per run, amortized by stability-gating frequency | **Matches**, measured |

**This table is the single most important correction this session makes
to the original README**: the design's *intended* complexity class is
real and achievable (the algorithm doesn't require quadratic work — the
self-healing property from Phase 2 only requires re-examining events
whose dependencies were previously missing, which is a small, boundable
set, not the whole log), but **this prototype does not yet realize it**
for write-heavy epistemic workloads. A patent claim on complexity
characteristics should claim the achievable design, and any
implementation/technical-effect argument submitted alongside it should
cite the world-layer numbers (which do hold up) rather than the
epistemic-layer numbers (which currently don't) as the technical-effect
evidence.

---

## PHASE 7 — EchoTales demonstrator

`examples/echotales_demo.py` (standalone, no changes to
`echotales-core`/`echotales-pipeline`). Maps: novel scene events →
`ASSERT_WORLD` (world/canon truth) → two characters' `OBSERVE`/`COMMUNICATE`/
`INFER` → converged world state for all replicas, intentionally divergent
per-character knowledge. Verified output: both the narrator's full canon
(`W`) and each character's genuinely different `K` are printed and
asserted; a character who was never told about a scene provably does not
"know" it despite `W` having fully converged. This is a mapping
demonstration only — no image/text generation, no touching of EchoTales'
actual persona/render pipeline, per the brief's explicit "do not refactor
EchoTales around E-CRDT yet."

---

## FINAL OUTPUT

**1. Exact surviving algorithm.** Causal OR-Set world state `W` (standard,
unmodified CRDT) + a grow-only, freely-replicated, typed event DAG `E`
(also structurally trivial to merge — set union) + a **local materialization
function** `K_i = view(E, i)` that admits a fact into `i`'s knowledge only
via events recording `i` as the actual subject (`observe`/`infer`,
actor-matched, with `infer` additionally closure-checked against `i`'s own
prior admissions) or addressee (`communicate`, target-matched) — with no
other code path into `K_i` — plus causal-stability-gated compaction that
collapses admitted chains to single terminal events without altering the
materialized result.

**2. Exact differentiating mechanism.** Knowledge admission is a
**structural match against immutable historical events**, not an
**attribute check against mutable, converged data**. There is no `scope`
or `visible_to` field anywhere in the design for a real fact; gaining
knowledge always requires minting a new, causally-ordered event. This is
what makes retroactive scope-widening (which every ACL-style system in
the prior art searched permits) structurally impossible here rather than
merely policy-forbidden.

**3. Strongest prior-art conflicts.** (a) Ritschel provisional
(USPTO 64/012,284) — closest on the "dual state + scope-based access"
*framing*, but a single-store read-time-ACL system with no CRDT merge and
no non-interference proof; its confidence-weighted reconciliation is
prior art this work doesn't use and shouldn't claim over. (b) "Epistemic
State Replication" (arXiv:2607.09748) — closest on *naming* and on the
two-layer-state framing, but solves the opposite problem (forcing
stochastic replicas to *agree*, not enabling intentional divergence), and
its cascading-retraction mechanism is genuinely superior to what's
implemented here — a real gap to either close or explicitly disclaim.
(c) Policy-CRDT — closest on "make the access-control mechanism itself a
CRDT," which is exactly the pattern this work's mechanism must be
distinguished from claim-by-claim.

**4. Safety results.** 26/26 tests passing (12 original + 14 new
adversarial). Zero unauthorized-knowledge-propagation violations across
every scenario tested — concurrent ops, delayed/duplicated/reordered
delivery, stale-replica catch-up, network partition/rejoin, multi-hop
transfer, deep inference chains — under the stated non-Byzantine threat
model. That model's boundary was directly probed and confirmed to break
exactly where documented (forged `communicate` event), and not to break
where the design claims resilience (forged `infer` event, correctly
rejected by the closure check).

**5. Scaling/technical-effect results.** World-layer: no measurable
disadvantage vs. naive-CRDT/CRDT+ACL baselines up to 100,000 ops
(near-linear, same order of magnitude). Epistemic layer: **measurable,
honestly-reported disadvantage** in the current prototype for
communicate/infer-heavy workloads (~O(n^2.7-2.9) empirically, vs. an
O(Δ) design target), traced to a specific, nameable, fixable
non-incremental-materialization gap rather than an algorithmic ceiling —
1M+ ops was not attempted for that workload shape because it would not
complete in reasonable time and the honest, useful result is the traced
root cause plus the measured trend, not a padded-out number.

**6. Ablation results.** Causal-DAG identity-gating (present in
full-E-CRDT and the no-provenance ablation, absent in naive-union and
flat-per-agent-CRDT) is the dominant safety mechanism (99/58 leaks → 0
when added). Provenance-closure verification is a distinct, smaller,
second mechanism that specifically stops forged derivation claims
(demonstrated by direct forged-event injection, not just narrative).
Static ACL matches E-CRDT exactly under never-changed scopes and diverges
exactly at scope-widening — the honest, precise statement of when the
novelty claim actually bites.

**7. Formal properties/complexity.** World convergence: proved,
unconditional. Epistemic non-interference: proved, conditional on
non-Byzantine event minting (precisely restated this session — the real
dependency is "all events came from the checked API," not "materialize
re-derives validity"). Correct propagation and concurrent-update
convergence: proved and empirically confirmed. Compaction soundness:
proved for the per-target case implemented; cross-target dedup not
attempted. Cascading retraction: not proved, not implemented, flagged as
a real gap relative to ESR prior art. Complexity: design-target O(Δ) for
all operations; **currently achieved for world-layer ops and cached
reads; not currently achieved for communicate/infer under mutation**,
stated as measured fact, not covered up.

**8. Claim-element comparison.** See Phase 5 table. Two elements survive
as genuinely undisclosed across all sources searched (original 8 +
Ritschel full-text + ESR + Matrix Event Graph + non-uniform replication):
the identity-gated event-DAG projection mechanism itself, and its
non-interference proof. Cascading retraction and confidence-weighted
reconciliation are prior art this work does **not** currently do and
should not claim.

**9. Weakest point in the invention.** Two, ranked: (a) **Engineering**:
the reference implementation's materialize() is non-incremental, giving
real, measured superlinear cost for write-heavy epistemic workloads —
this does not invalidate the algorithm's design-target complexity, but it
means the technical-effect evidence currently available is asymmetric
(strong for the world layer, weak/negative for the epistemic layer as
built) and any filing should not lean on the epistemic-layer numbers as
efficiency evidence until this is fixed. (b) **Claim scope**: the
non-interference guarantee is proved only under a non-Byzantine threat
model where all events are minted through a checked local API — a
replica that can write to its own event log directly (which is not
prevented by anything in this design, since there's no cryptographic
binding between an event and proof that its issuer actually satisfied the
precondition) defeats it for `observe`/`communicate` specifically (though
not for `infer`, which independently re-verifies). A claim that doesn't
scope this precisely risks being read as promising more than what's
proved.

**10. Final classification: IPR REVIEW CANDIDATE**

Not a kill. The core mechanism (identity-gated projection of a shared
causal event DAG, with a proved non-interference property and a working
stability-gated compaction algorithm) is confirmed, after full-text
reading of the closest patent and the closest-named paper, and after
adversarial and ablation testing designed to break it rather than confirm
it, to be genuinely undisclosed in the prior art searched. The
recommendation is to proceed to IPR review **with the claim scoped
narrowly** to the materialization/admission mechanism and its compaction
algorithm — explicitly non-Byzantine, explicitly not claiming the
confidence-weighted-reconciliation or cascading-retraction mechanisms
that closest prior art already covers — and with the engineering caveat
in finding 9(a) disclosed to whoever evaluates the technical-effect
evidence, rather than presenting only the favorable world-layer numbers.
