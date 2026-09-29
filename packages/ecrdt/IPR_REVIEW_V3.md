
# E-CRDT — IPR Review Package, Round 3 (baseline-reconstruction attack)

Adds to `IPR_REVIEW_V2.md` (still authoritative on every point this round
does not touch); does not restate it. This round runs exactly one new
test the brief's Step 4 specifically demanded and V1/V2 had not yet run:
build the *strongest fair* baseline — CRDT + causal delivery + ACL, with
grants themselves causally-dotted rather than a mutable attribute — and
see whether it reproduces E-CRDT's confidentiality property. Nothing
published, pushed, or exposed. All work confined to `packages/ecrdt/`.

```
PYTHONPATH=src python3 -m pytest tests/ -q        # 36/36 passing (33 + 3 new)
```

---

## The new baseline

`DynamicCausalACLReplica` (`src/ecrdt/baselines.py`): same `ORSet` for `W`
as every other baseline; a `grant(target, fact)` operation mints an
immutable, causally-dotted `GrantEvent` (same `Dot` scheme as an E-CRDT
`Event`) only if the granter's own materialized access already includes
the fact — the identical fairness precondition as E-CRDT's `communicate`.
No local attribute mutation, no retroactive widening, no epistemic
vocabulary (`OBSERVE`/`COMMUNICATE`/`INFER`) — just ACL semantics gated by
a causally-replicated grant log instead of a converged, mutable store.
This is the "obvious combination" a competent engineer reaches for once
told "gate access by causal history, not by an attribute," without having
seen E-CRDT's design.

## Result 1 — it is not a strawman, and it is not distinguishable on
## confidentiality alone

`tests/test_dynamic_acl_baseline.py::test_dynamic_causal_acl_matches_ecrdt_zero_leaks_under_random_workload`
runs the identical 300-op, 5-replica, differential-audit methodology as
`test_ecrdt.py::test_ecrdt_zero_unauthorized_leaks_under_random_workload`
against this baseline. **Result: 0 leaks — identical to E-CRDT.**

**This directly narrows V2's Phase 1 claim.** V2 stated: *"identity-gated
admission over a freely-replicated causal event log... is the whole
claim."* This round shows that specific mechanism (grants/observations
gated by causal delivery rather than converged-store attribute check) is
reproducible in full by a standard combination of three off-the-shelf
techniques — an OR-Set, causal delivery, and ACL grant records — with no
epistemic-DAG vocabulary at all. Per the user's own stopping rule ("if the
strongest baseline can reproduce the core E-CRDT behavior by a
straightforward combination of known techniques, kill it"), **the plain
identity-gated observe/communicate mechanism, taken alone, does not
survive this attack and must not be claimed as the invention.**

## Result 2 — the surviving gap: no GRANT-equivalent of INFER

`test_infer_has_no_dynamic_acl_equivalent_counterexample` is the Step 6
concrete counterexample. Setup: replica `a` causally holds two premises
(`p1`, `p2`, self-granted after being asserted into `W`). On `Replica`,
`a.infer("derived", premises=["p1","p2"])` is admitted locally, in O(1),
with a valid provenance chain, and **zero new events from any other
party**. On `DynamicCausalACLReplica`, there is no operation that can
reach the same state: `"derived"` was never independently asserted into
`W`, so `self_grant("derived")` is rejected by its own precondition (the
same test asserts this directly, not by inspection). The *only* way to
give `a` access to `"derived"` under this baseline is an explicit `GRANT`
from some other party — who would need to already know, in advance, that
`a` holds `p1`+`p2` and that `"derived"` follows from them. That is either
(a) per-derivation, omniscient administration (a distinct/new grant for
every derivable combination, decided by someone else, ahead of time), or
(b) a blanket over-grant that reopens exactly the confidentiality leak
Result 1 showed this baseline otherwise avoids. Neither is the same
operation as `infer()`: a replica deriving new, correctly-scoped knowledge
from its own causally-established holdings, autonomously, without any
other party's involvement.

`test_dynamic_causal_acl_grant_precondition_is_fair_not_a_strawman`
additionally confirms the baseline's `grant` precondition is exactly as
strict as E-CRDT's `communicate` precondition (rejects a grant for a fact
the granter hasn't itself self-granted) — the comparison in Result 1/2 is
not an artifact of a looser baseline.

---

## Refined claim-scale statement (supersedes V2 Phase 1's on this one point)

> The surviving claimable mechanism is **not** "identity-gated admission
> over a causal event log" in general — that is now shown reconstructible
> by standard CRDT+causal-delivery+ACL. It is specifically: **a replica's
> ability to autonomously admit a new, causally-scoped fact derived from
> facts it has already been causally granted, by verifying — against its
> own immutable local history alone, with no new event from any other
> party — that every cited premise was itself previously admitted for
> that same replica; with a proved guarantee (Theorem 2 + the Phase 7
> commutativity lemma, IPR_REVIEW_V2.md) that this derivation can never
> manufacture access to a fact the replica was not, through some causal
> chain, actually granted.** Plain OBSERVE/COMMUNICATE-style identity
> gating is supporting machinery, now conceded to be standard; INFER's
> closure check plus the non-interference proof around it is the part
> this round's attack could not dissolve.

This is a narrower claim than V2's own Phase 1 statement, arrived at by
actually running the reconstruction the brief demanded rather than by
argument alone — consistent with this package's round-over-round pattern
(V2 narrowed V1's compaction claim the same way, by measuring instead of
assuming).

## What this changes in V2's other conclusions

- Prior-art table (V2 Phase 6): unchanged — MAP-Graph remains the closest
  analog specifically to the INFER closure check, which is now understood
  to be the *entire* surviving claim, not one part of a three-part
  combination. This makes MAP-Graph's distinction (centralized,
  static-attribute, query-time-recursive, "not a proof") the single most
  important prior-art distinction in any filing, more important than the
  Ritschel distinction (which mainly concerned the now-conceded
  observe/communicate mechanism).
- Ablations (V2 Phase 5): unchanged and now read differently — ablation D
  (closure-only, no identity gating, 52 leaks) already showed identity
  gating is necessary; this round's baseline shows identity gating is
  *also* not sufficient to distinguish from prior art on its own, since a
  standard ACL reconstruction gets the same 0-leak result without any
  epistemic-DAG concept. The two results together, not either alone,
  are what correctly locate the claim on INFER specifically.
- Weaknesses list (V2 Phase 7, "remaining weaknesses, ranked"): add a new,
  more fundamental item above the existing five — **the mechanism's
  useful surface area is now narrower than previously framed**: it is a
  derivation/provenance-closure primitive, not a general disclosure
  system. Whether that narrower primitive alone is worth a filing (vs. a
  detail better described as a feature of a larger disclosure system) is
  now the first question for a patent professional, ahead of the
  Byzantine/merge-scaling items.

---

## Updated classification

Still **A — IPR REVIEW CANDIDATE** (V2's label), but the candidate is now
understood to be *narrower* than V2 itself believed when it wrote that
label — this round is a downgrade-by-precision, not a new upgrade. See
the final answer delivered to the user in this session for the mapping
onto the user's three-tier scale (STRONG / BORDERLINE / KILL).
