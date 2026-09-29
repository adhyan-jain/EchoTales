# E-CRDT: World Convergence with Provable Epistemic Non-Interference

Standalone research prototype. Imports nothing from `echotales-core` or
`echotales-pipeline`. EchoTales itself is unaffected; this package exists to
determine whether a genuine, patentable invention exists on the axis
described below, independent of the narrative-KG work.

Run it:
```
cd packages/ecrdt
PYTHONPATH=src python3 -m pytest tests/ -q      # 12/12 passing
PYTHONPATH=src python3 -m ecrdt.bench           # synthetic benchmark + report
```

---

## 1. Formal problem

Replica state `R_i = (W, K_i, P_i)`:
- `W` — canonical/world state, shared, must converge across all replicas.
- `K_i` — replica `i`'s own knowledge: a subset of (or private additions to)
  `W`, intentionally different per replica.
- `P_i` — causal/provenance structure recording *how* `i` came to know
  what it knows.

Operations: `ASSERT_WORLD`, `OBSERVE`, `COMMUNICATE`, `INFER`, `RETRACT`.

Goal: **world convergence** (all `W_i` reach the same fixed point under
merge, standard CRDT strong eventual consistency) **+ epistemic
non-interference** (merging replica `j` into replica `i` must never cause
`K_i` to gain a fact unless a real causal disclosure or inference path to
`i` exists — merging cannot manufacture knowledge).

---

## 2. Prior art map

Searched: epistemic/knowledge CRDT, secure/private CRDT, access-controlled
replication, observer-scoped distributed state, causal knowledge
propagation, distributed belief/state synchronization, information-flow
CRDT, multi-principal replicated state, privacy-preserving eventual
consistency, causal consistency + knowledge, semantic CRDTs, plus patent
search on USPTO/Google Patents.

| Reference | What it actually covers | Gap relative to the target |
|---|---|---|
| **Shapiro et al. 2011 / Bieniusa et al. 2012** (causal OR-Set, δ-CRDTs) | The join-semilattice machinery this prototype's `W` layer reuses directly (add/remove dots, causal context, delta dissemination). | No epistemic layer at all — a CRDT set converges to one shared value for every replica by definition; there is no notion of "converges but some replicas legitimately don't see it." |
| **"Secure / General-Purpose Secure CRDTs"** (INESC-TEC 2020/2023, MPC-based) | Cryptographically hides *operation content* from the network/servers using MPC so ops can be computed on encrypted state. | Orthogonal axis: hides data from untrusted infrastructure, not from other legitimate replicas. Says nothing about causal-disclosure-gated knowledge between trusted-but-differently-informed agents. |
| **Consistency Types for Replicated Data (CTRD)**, arXiv:1907.00822 | A static type system enforcing information-flow *between consistency levels* (weak data can't taint strongly-consistent data) in a replicated language. | Different axis entirely: it's a security-lattice-over-consistency-levels type discipline, not an observer-identity-indexed knowledge model with a proven non-interference theorem on merge. |
| **Policy-CRDT** (remove-wins access-control-policy CRDT) | Makes the *access control policy itself* a conflict-free replicated object. | This is exactly "CRDT + ACL," which the brief requires killed if that's all the mechanism is. Read-time attribute check against a converged store — same structural weakness (see §4) as the baseline this prototype benchmarks against. |
| **Partial replication of CRDTs** (Guerreiro et al.) | Propagate ops only to replicas "interested" in an object, to save bandwidth; interest is usually a static subscription. | Optimizes *what gets sent*, not what a replica is *entitled to have materialized as knowledge* once received; doesn't define or prove a non-interference property. |
| **Distributed/DEL epistemic logic** (Fagin/Halpern/Moses; "Consistent Update Synthesis via Privatized Beliefs," arXiv:2406.10010) | The correct formal home for "what do agents know / believe," including privatized Kripke models and *goal-directed synthesis* of an update (action model) that changes exactly the target agents' beliefs and no one else's. | Prescriptive and centralized: given a goal formula, *synthesize* an action model achieving it; assumes a single controller with full model access, not an open asynchronous system of replicas independently gossiping and merging without a synthesizer. No CRDT-style merge algorithm, no tombstones/retraction under concurrency, no bandwidth/complexity story. |
| **"Distributed Causal Memory with Confidence-Weighted Reconciliation and Governed Multi-Agent Access"** (Ritschel, provisional patent, USPTO 64/012,284, filed 2026-03-20 — read in full from the docx, not just the abstract) | Closest hit. Dual semantic-embedding + causal-triple storage, confidence-weighted contradiction reconciliation, and a `scope` field (`shared` / `private_agent` / `private_user` / `restricted_group`) checked **at read time** against a **single, centrally-replicated append-only log** (one persistence layer, one vector index, one graph store — not a CRDT of independently-diverging replicas). | Confirmed, by reading the actual claims text, that this is (a) not a multi-replica CRDT-merge setting at all — no vector clocks, no concurrent-write conflict handling beyond confidence scoring, no offline-then-reconverge model; (b) its access control is a static attribute (`scope`/`owner_id`) evaluated against the converged store, i.e., structurally identical to the "CRDT + ACL" pattern this brief requires killed. It does not model, or claim, that merging cannot manufacture knowledge, and it has no causal-disclosure-path requirement — widening `scope` (a supported operation in that architecture) instantly grants retroactive access to history, exactly the failure mode benchmarked in §5. **Must be cited and distinguished in any filing; does not, on its own, kill the candidate.** |
| **Crypto fog-of-war** (Xaya `fog-of-war`: blinded two-party DH sighting test) | A narrow two-party "is X visible to Y" cryptographic primitive for one specific game mechanic. | Explicitly not a general consistency model or merge algorithm; author's own docs call it "the original sight-only instrument," not reusable as a general primitive. |
| **MELD** (arXiv:2608.16357, per-claim status CRDT for agent memory) | Append-only per-claim status CRDT ("verified / disputed / retracted") for coherent publish/subscribe across agentic memories. | Converges a *status label* on claims everyone eventually sees the same way — the opposite of intentional per-replica divergence; doesn't address observer-scoped knowledge at all. |

**Verdict on prior art:** no single reference combines (a) CRDT-style
independent-replica merge under partition/concurrency, (b) a
non-interference *property with a proof*, gated by causal disclosure events
rather than static attributes, and (c) compaction of that provenance to
bounded steady-state size. The Ritschel patent is the closest and must be
cited, but it is a single-store, read-time-ACL system, not a
replica-merge consistency model — a materially different mechanism, not a
restyled version of the same one.

**This candidate survives the kill list**: it is not ordinary CRDT
union/intersection (§3's projection function is not a lattice join — see
below), not just ACL filtering (§4 shows the concrete divergence), not just
vector clocks (vector clocks order events; they don't gate a second-order
derived set), and not just provenance/access control (provenance here is
the load-bearing mechanism that *defines* `K_i`, not descriptive metadata
attached after the fact).

---

## 3. The algorithm

### 3.1 State

- `W`: causal OR-Set over fact ids (`orset.py`) — standard join-semilattice,
  no novelty claimed.
- `E`: a grow-only DAG of immutable `Event`s (`model.py`), one per
  operation, keyed by `Dot = (replica_id, counter)`. `E' = E_i ∪ E_j` is
  itself a trivial semilattice (set union) — this is the wire format that
  is freely, fully gossiped between all replicas. It is *public metadata*:
  everyone eventually agrees on the full shape of "who did what, causally,"
  including the existence of a `COMMUNICATE(A→B, f)` event — without that
  necessarily meaning a merging replica learns the *content* of `f`.
- `K_i`: **not stored** — computed by `Replica.materialize()` as a pure
  projection of `E` onto replica `i`'s own subject/addressee events, in
  causal (topological) order, with add-wins tombstone handling for
  `RETRACT_KNOWLEDGE`.

### 3.2 Operations (`replica.py`)

- `ASSERT_WORLD(f)` — adds `f` to `W`; creates an event with no
  `deps`. Deliberately **not** an OBSERVE: writing a fact into the world
  is a distinct act from perceiving/knowing it (a design choice validated
  by `test_assert_alone_does_not_grant_knowledge`).
- `OBSERVE(f)` — precondition: `f` is live in the caller's own `W`. Creates
  an event with `deps` = the live assert-dots being observed, `actor = i`.
- `COMMUNICATE(target, f)` — precondition: caller's own `materialize()`
  already contains `f`. `deps` = the caller's own establishing dots for
  `f`. `target = j`.
- `INFER(f, premises)` — precondition: all `premises ⊆ materialize()`.
  `deps` = the union of the caller's establishing dots for each premise.
- `RETRACT_WORLD(f)` / `RETRACT_KNOWLEDGE(target, f, dots)` — tombstone
  events carrying the exact dots being retracted, giving add-wins
  semantics under concurrency (a concurrent re-OBSERVE after an
  out-of-order RETRACT survives — see `test_retract_knowledge_is_add_wins_under_concurrency`).

### 3.3 Merge

```
merge(R_i, R_j):
    W_i  <- W_i.join(W_j)          # standard causal-CRDT join
    E_i  <- E_i ∪ E_j              # set union of immutable events
    # K_i is NOT touched directly. It is re-derived on next materialize().
```

### 3.4 Materialization (`Replica.materialize`)

Walk `E` in topological (causal) order. For replica `me`:
- `OBSERVE` with `actor == me`, or `COMMUNICATE` with `target == me`, or
  `INFER` with `actor == me` **and all its deps already established for
  `me`** → add `f` to `known[f]` (with the establishing dot, for
  provenance / future retraction).
- `RETRACT_KNOWLEDGE` with `target == me` → subtract exactly its `deps`
  dots from `known[f]` (add-wins).
- `K_me = {f : known[f] non-empty}`.

**This is the whole mechanism.** Every other event kind (someone else's
`OBSERVE`, someone else's `COMMUNICATE` to a third party, `ASSERT_WORLD`
by anyone) is *visible in `E`* after a merge — a replica can see that an
event happened — but is structurally inert with respect to that replica's
own `K`. There is no code path from "`E` contains an event mentioning
`f`" to "`f ∈ K_me`" that does not pass through `actor == me` or
`target == me`.

### 3.5 Compaction (`compaction.py`)

Once an event is **causally stable** — every replica's event-context
high-watermark covers its dot (`causally_stable`, the same stability test
used for tombstone GC in δ-CRDTs/RGA) — a multi-hop disclosure chain
terminating at a given target (`assert → observe(A) → communicate(A→B) →
communicate(B→C)`) can be collapsed into a single synthetic terminal event
for that target, discarding the intermediate chain but preserving the dot
identity (so future retractions by dot still resolve) and the existence
fact ("C is, causally, entitled to know this"). This is only sound for
stable events — an event still reachable by an in-flight, not-yet-merged
retraction cannot be safely compacted, exactly as CRDT tombstone GC cannot
outrun causal stability.

**Threat model, stated explicitly**: non-Byzantine replicas, matching the
standard CRDT literature. `COMMUNICATE`/`INFER` preconditions are enforced
locally by the *issuing* replica's own API before an event is minted.
Extending to signed events / Byzantine replicas is future work, not
attempted here.

---

## 4. Precise novelty gap vs. "CRDT + ACL"

The concrete, benchmarked distinction (see `baselines.py`,
`test_acl_baseline_retroactive_widen_is_a_measurable_leak`):

- **ACL/scope systems** (Policy-CRDT, the Ritschel patent's `scope` field,
  and the `ACLReplica` baseline built here to match) store a *static
  attribute* on the fact (`visible_to`, `scope`, `owner_id`) and check it
  **at read time** against whatever the converged store currently holds.
  If that attribute is later widened — a normal, supported operation in
  every ACL system — every replica that already synced the underlying
  data **instantly and retroactively** gains access to history it was
  never causally sent. There is no way, from inside that model, to
  distinguish "I was told this" from "the label on it changed."
- **E-CRDT** materializes `K_i` exclusively from first-class disclosure
  *events* in the causal DAG. There is no attribute to widen: gaining
  knowledge of `f` after the fact requires minting a *new*
  `COMMUNICATE`/`OBSERVE`/`INFER` event, which is itself causally ordered
  and auditable, and which cannot be backdated to grant knowledge of
  something that happened before it.

This is the theorem the benchmark exists to check, not just assert.

---

## 5. Proof sketches

**Theorem 1 (World convergence).** `W` is a join-semilattice (§3.1); `join`
is commutative, associative, and idempotent (standard OR-Set proof,
reused unmodified — verified by
`test_orset_join_is_commutative_associative_idempotent` and the CRDT
literature cited above). Under eventual delivery of all deltas, every
replica's `W` converges to the same fixed point. ∎ (not novel; required
scaffolding.)

**Theorem 2 (Epistemic non-interference).** For any replica `i` and any
sequence of merges, `f ∈ K_i^after \ K_i^before` implies there exists an
event `e ∈ E^after \ E^before` with (`actor(e) = i` and `e.kind ∈
{observe, infer}`) or (`target(e) = i` and `e.kind = communicate`), such
that `e` establishes `f` and `deps(e) ⊆` already-established dots for `i`.

*Proof.* By construction, `materialize()`'s only write sites into `known`
are gated by `actor == me` or `target == me` (§3.4); no other branch
exists. `merge` only ever adds elements to `E` (never removes, never
rewrites an event, never writes to `K` directly — §3.3). By structural
induction on the (finite, acyclic — enforced by `_topo_order`, which
raises on a cycle) event DAG: every event in `E^after` was originally
minted by some replica's own operation API (`assert_world` / `observe` /
`communicate` / `infer` / `retract_*`), each of which checks its stated
precondition against that *replica's own* materialized state before
minting the event (§3.2). Hence any event with `target = i` or `actor = i`
that newly appears in `E^after` was created by a genuine
`COMMUNICATE(·→i, f)`, `OBSERVE(i, f)`, or `INFER(i, ..., f)` call whose
precondition held at creation time. Merge cannot synthesize such an event;
it can only carry forward events that some replica actually created. ∎
(Holds under the stated non-Byzantine threat model.) Empirically checked
by `test_merge_cannot_grant_unearned_knowledge`,
`test_infer_does_not_leak_to_others`, and the randomized differential test
`test_ecrdt_zero_unauthorized_leaks_under_random_workload` (300 random ops
over 5 replicas, audited against independently-tracked ground truth, zero
violations).

**Theorem 3 (Causal monotonicity).** The projection `materialize(E, i)` is
monotonic in `E` under set inclusion, except across an explicit
`RETRACT_KNOWLEDGE(i, f, dots)` tombstone: `E ⊆ E'` (via a merge that
only ever adds events) implies `K_i(E) ⊆ K_i(E') ∪ {retracted-and-not-re-established facts}`.
Follows directly from `materialize` never removing an entry except via a
matching `retract_knowledge` event, and the add-wins dot-subtraction
semantics giving newer/concurrent establishing dots priority over an
older retraction (§3.2, `test_retract_knowledge_is_add_wins_under_concurrency`).

**Theorem 4 (Compaction soundness).** For a causally-stable event `e`
terminal for target `i`, replacing `e`'s `deps` with `∅` (while preserving
`e.dot`) does not change `materialize(E, i)`'s output set `K_i`, because
(a) `e` itself is already the terminal establishing event for that fact —
its own deps are only consulted for `infer` events to check premises were
*at some point* established, and stability guarantees no future event can
retroactively invalidate that; (b) `e.dot` is preserved, so any future
`RETRACT_KNOWLEDGE` referencing that dot still resolves correctly.
Compaction is unsound for non-stable events (a concurrent retraction could
still be in flight) — enforced by gating on `causally_stable()` before
compacting.

**Theorem 5 (Concurrent updates).** Both `W` (a join-semilattice) and `E`
(a set-union semilattice) tolerate arbitrary concurrent, out-of-order
merges and converge under only the standard CRDT requirement of eventual,
causally-consistent delivery (an event is only *processed* by
`materialize`'s topological sort once its deps are present — no ordering
requirement is placed on `merge` itself, only on when a valid
topological order can be computed, which `_topo_order` verifies by
raising on missing/cyclic dependencies).

---

## 6. Complexity

Let `|F|` = live facts, `|R|` = replicas, `|E|` = total events, `d` =
average unstabilized dependency-chain depth.

| Quantity | Naive-union CRDT | CRDT+ACL | E-CRDT (this work) |
|---|---|---|---|
| Per-replica state (steady state, post-compaction) | `O(\|F\|)` | `O(\|F\|)` (facts) + `O(\|F\|)` (scope tags) | `O(\|F\|)` (`W`) + `O(\|F\| · \|R\|)` worst case / `O(\|F\|)` typical after per-target compaction (§3.5, Theorem 4) for the events that terminate at this replica |
| Merge cost (delta) | `O(\|ΔW\|)` | `O(\|ΔW\| + \|Δscope\|)` | `O(\|ΔE\|)` (delta event-set union) + `O(\|ΔE\| · d)` for materialization before stabilization, `O(\|ΔE\|)` after (Theorem 4) |
| Bandwidth per replica | `O(\|F\|)` (everyone always replicates everything) | `O(\|F\|)` (same — ACL only filters at read, not at replication) | `O(\|F\|)` for `W` + `O(\|E\|)` for the causal DAG, compactable to `O(\|F\|)` per disclosed fact once stable |
| Confidentiality guarantee at the replication layer | none — `K_i := W` | none — full `W` is replicated to every node; only the *query result* is filtered | **replication-layer**: a replica need not even receive undisclosed events (compaction/partial-gossip can omit non-terminal-for-me events); **materialization-layer**: proven (Theorem 2) regardless |

Benchmark numbers (`ecrdt.bench`, 8 replicas, 60 facts, 12 rounds with a
4-round network partition, seed=7; see §7 for the retroactive-widen
variant):

```
system     bandwidth_B  metadata_B  merge_us  update_us  unauth_leak
ecrdt            50352       46512     15.17      13.64            0
naive              3840           0     11.45       0.00          181
acl                8800        4960     14.50       0.00           24
```

Compaction demo (6 replicas, 40 facts, chain-heavy scenario, single target
replica's event log): **158 → 144 events (−8.9%), 9,933 → 8,595 bytes
(−13.5%)** in a deliberately small run; the reduction grows with run
length since compaction only fires on causally-stable chains.

Convergence (full-mesh random-pair gossip, no partition, 8 replicas, 40
facts): **6 rounds** to full `W` agreement — identical mechanism across
all three systems (Theorem 1 / Theorem 5 machinery is shared), included as
a sanity check that the epistemic layer imposes no convergence-speed
penalty on `W` itself.

**Honest cost callout**: E-CRDT's raw bandwidth in this small,
uncompacted run is ~6-13x the naive/ACL baselines' `W`-only bandwidth,
because it is paying for the full causal-disclosure DAG. That is the
explicit price of the confidentiality property in §4 that neither
baseline provides — compaction (Theorem 4) is what keeps that cost bounded
in steady state rather than growing without limit; a full economic
comparison would need a longer-running, partially-compacted trace than
this benchmark's scope.

---

## 7. Unauthorized knowledge propagation (the headline experiment)

Two scenarios (`run_scenario(retroactive_widen=False/True)`), each audited
against independently-tracked ground truth (`audit.py`, not the systems'
own bookkeeping):

```
baseline scenario (no scope widening)
system     unauth_leak
ecrdt                0
naive               181
acl                  24

with retroactive ACL scope widening
system     unauth_leak
ecrdt                0
naive               181
acl                  49    (+25 from the widen step alone)
```

- **`ecrdt`: 0 leaks in every run**, including a 300-op randomized
  differential test (`test_ecrdt_zero_unauthorized_leaks_under_random_workload`).
- **`naive`** leaks by construction — `K_i := W`, so every replica
  "knows" everything anyone ever asserted, ~181 unauthorized
  (replica, fact) pairs in this run. This is the null hypothesis: what
  "just merge the CRDT" gets you.
- **`acl`** leaks even without deliberate widening (24), because in this
  baseline the creating replica is scoped `visible_to={creator}` at
  `ASSERT_WORLD` time — i.e., an ACL system's ordinary convention of
  "the author can read what they wrote" **conflates authorship with
  epistemic acquisition** (E-CRDT keeps these separate by design:
  `test_assert_alone_does_not_grant_knowledge`). This is not a bug in the
  baseline; it is exactly the structural property being contrasted.
  Retroactively widening scope for a batch of facts (the `acl` gap this
  brief specifically asks to test for) adds **25 more** leaks with zero
  additional causal events — a fact becomes "known" purely because a
  label changed.

---

## 8. Implementation

`packages/ecrdt/src/ecrdt/`:
- `orset.py` — causal OR-Set (`W`), standard construction.
- `model.py` — `Event`/`Dot`, the causal disclosure DAG (`P`).
- `replica.py` — `Replica`: operations, `merge`, `materialize` (`K_i`
  projection — the novel part), compaction accounting hooks.
- `compaction.py` — causal-stability detection + provenance compaction.
- `baselines.py` — `NaiveUnionReplica`, `ACLReplica` (fair, working
  implementations of the two "must not count as novel" combinations).
- `audit.py` — ground-truth non-interference checker used by both the
  test suite and the benchmark.
- `bench.py` — synthetic multi-agent world generator (observation,
  communication, inference, concurrent updates, retraction, network
  partition/merge) + the metrics harness (`python3 -m ecrdt.bench`).

`packages/ecrdt/tests/test_ecrdt.py` — 12 tests, all passing: world
convergence (commutative/associative/idempotent join), the
assert-does-not-imply-knowledge distinction, the core non-interference
property (direct + randomized-differential), communicate/infer disclosure
and non-leakage, add-wins retraction under concurrency, and both baseline
comparison scenarios.

`EchoTales` demonstration layer: **not built this session** — the brief
scopes it as "use EchoTales only as a demonstration layer" and the
priority given limited time was proving the algorithm itself (formal
model, proofs, prototype, benchmark) rather than wiring a thin novel→
world-state→multi-reader demo on top. The mapping is straightforward given
what exists (`W` = the novel's resolved-mention/persona graph facts,
`OBSERVE` = a reader/character encountering a scene, `COMMUNICATE` =
in-story dialogue disclosing information between characters, `INFER` =
reader/character deduction) but is cosmetic relative to the algorithm — it
was left out to keep this session's budget on the parts that determine
patentability, and can be added on request.

---

## 9. Final report

- **Candidate**: E-CRDT — world convergence with provable epistemic
  non-interference, materialized via causal-disclosure-event projection
  rather than attribute-based access control.
- **Formal problem**: §1.
- **Exact algorithm**: §3 (causal OR-Set `W` + grow-only event DAG `P` +
  the `materialize()` projection function, with causal-stability-gated
  compaction).
- **Closest prior art**: Ritschel provisional patent (USPTO 64/012,284) —
  dual semantic/causal storage + scope-based access control, but a
  single-store, read-time-ACL system with no multi-replica CRDT merge and
  no non-interference proof. Also material: Policy-CRDT (ACL-as-CRDT),
  CTRD (information-flow types for consistency levels, different axis),
  DEL belief-update synthesis (correct formal home for the epistemics, but
  centralized/prescriptive, no merge algorithm). Full table in §2.
- **Precise novelty gap**: knowledge is materialized as a *projection of a
  replicated causal event DAG gated by disclosure-event identity*
  (who is the actual subject/addressee of a real OBSERVE/COMMUNICATE/INFER),
  not as a *static attribute checked against a converged store*. This
  closes a concrete, measured leak (§7, the ACL-widening scenario) that
  every ACL/scope-tag system — including the closest prior art found —
  structurally permits.
- **Proof properties**: world convergence (Theorem 1, standard), epistemic
  non-interference (Theorem 2, the novel result, proved and empirically
  checked including a randomized differential test), causal monotonicity
  (Theorem 3), compaction soundness (Theorem 4), concurrent-update
  convergence (Theorem 5).
- **Implementation**: `packages/ecrdt/`, 12/12 tests passing, standalone,
  zero dependency on EchoTales core/pipeline.
- **Benchmark**: §6–7. Zero unauthorized-knowledge-propagation events for
  E-CRDT across all scenarios and a 300-op randomized workload, vs. 181
  (naive union) and 24–49 (CRDT+ACL, worse under retroactive scope
  widening) for the baselines. Convergence speed and `W`-layer cost are
  unaffected by the epistemic layer; the epistemic layer's own metadata
  cost is bounded by causal-stability compaction (Theorem 4, measured
  −8.9% events / −13.5% bytes in a short synthetic run).
- **Technical effect**: a distributed system can replicate a single
  converged world state to all nodes while making it *structurally
  impossible* (not merely policy-forbidden) for a node to materialize
  knowledge of a fact it was never causally disclosed — including under
  concurrent updates, retractions, and later changes to who is "allowed"
  to see what.
- **IPR candidate / kill call**: **survives as a narrow, real candidate.**
  Not a kill — the mechanism is genuinely distinct from CRDT+ACL, vector
  clocks, and provenance-as-metadata, and the closest prior art found (the
  Ritschel patent) does not disclose a multi-replica merge algorithm or a
  non-interference proof. The honest caveat: novelty is narrow and sits
  specifically in *how knowledge is materialized from a shared causal DAG
  at merge time*, not in the broader "epistemic CRDT" framing, which
  overlaps substantially with DEL-based privatized-belief work and
  ACL-CRDT combinations once you strip the "prove it structurally rather
  than check it by attribute" distinction away. Any filing should claim
  narrowly around Theorem 2's mechanism (disclosure-event-gated
  materialization + its compaction algorithm), cite the Ritschel patent
  and Policy-CRDT as closest art to distinguish from, and not claim the
  general "world convergence + observer divergence" framing as if it were
  unclaimed territory — DEL/privatized-belief work already occupies that
  framing; the algorithmic mechanism for achieving it in an
  asynchronous, partition-tolerant, CRDT-merge setting is what's new.

No publishing, pushing, or external exposure performed, per instructions.
