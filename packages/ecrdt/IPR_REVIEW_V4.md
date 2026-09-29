
# E-CRDT — IPR Review Package, Round 4 (the derivation trilemma)

Adds to `IPR_REVIEW_V3.md` (still authoritative on the confidentiality
finding); does not restate it. This round asks a harder question than
round 3's single counterexample: can *any* fair "CRDT + dynamic
authorization + provenance" construction reproduce local derivation
(`Replica.infer()`) safely under partition, delayed/out-of-order delivery,
retraction, and concurrent updates — the four conditions this package
already takes seriously for E-CRDT itself (`test_adversarial.py`) —
**without minting an additional authorization event**? Nothing published,
pushed, or exposed. All work confined to `packages/ecrdt/`.

```
PYTHONPATH=src python3 -m pytest tests/ -q        # 41/41 passing (36 + 5 new)
```

---

## The trilemma

Any construction that (i) represents authorization as CRDT-replicated
records (grants/attributes) plus provenance metadata, and (ii) allows
deriving new facts from currently-held ones via a *standing rule* (no
fresh per-instance grant), must land on one of three horns:

- **(A) Reject/omit the derivation** — structurally cannot reproduce
  `infer()` at all. **Proved, round 3**: `DynamicCausalACLReplica` has no
  operation for it.
- **(B) Evaluate the rule against instantaneously-held state** — the
  fairest, hardest attempt: `AutoDerivingACLReplica` (new this round),
  built directly on top of `DynamicCausalACLReplica`.
- **(C) Mint a fresh authorization event for the derived fact anyway** —
  concedes the point; this is `infer()` under ACL vocabulary.

## What was actually found for horn (B) — corrected once, honestly

**The initial hypothesis for this round was wrong, and the tests that
checked it are kept as the record of that, not deleted.** The expectation
going in was that a shared, CRDT-unioned rule table would reintroduce
`ACLReplica`'s retroactive-widen leak (round 1) once merged across
replicas — a concurrently-declared alternative rule for the same fact
name looked like it should let one replica's premises "leak through"
another's rule. **It does not.**

`test_concurrent_rule_declaration_does_not_leak_because_identity_gating_survives_it`
and `test_partition_then_rejoin_rule_merge_stays_confidentiality_safe`
(both under the identical differential-audit methodology used everywhere
else in this package) show **zero leaks**, including after a full-mesh
merge of both replicas' grant logs *and* rule tables, and including after
an explicit partition/rejoin cycle. The reason, found by tracing the code
rather than assumed: `_materialize_grants()`'s `target == me` gating
(inherited unchanged from `DynamicCausalACLReplica`, itself proved safe in
round 3) sits *underneath* the rule-closure fixpoint. A rule can only ever
fire against facts a replica holds **under its own identity** — a merged
rule table and a merged grant log never combine across replica identities,
because nothing in the closure computation ever looks at another
replica's holdings. **Horn (B), built this carefully, is confidentiality-
safe under concurrent updates and partition/rejoin.** This is a real,
measured negative result, not a hedge — round 3's confidentiality finding
generalizes to standing-rule derivation too, which is a *stronger* result
for the baseline than originally expected, and it is reported as such.

## What horn (B) genuinely cannot do: give the derived fact an identity

Two results survive, unrelated to confidentiality, both proved by
construction:

**Retraction** (`test_derived_fact_has_no_stable_provenance_to_retract`):
a rule-derived fact has no entry in `_materialize_grants()`'s own
provenance dict — it was never established via a `G` record, only via a
live re-evaluation of the rule table. There is nothing a
`retract_knowledge`-equivalent operation could cite to revoke *this
specific derivation* of the fact, as distinct from some other, later
derivation of the same fact name from different premises. E-CRDT's
`provenance[fact]` is exactly this stable dot-set; the baseline has no
analogue at all.

**Delegation** (`test_delegating_a_derived_fact_requires_a_fresh_authorization_event`):
`grant()`'s own precondition (inherited unchanged) checks `G` only, which
never contains a rule-derived fact. A replica that has locally derived
`"derived"` and wants to hand it to another replica cannot — `a.grant("b",
"derived")` raises `ValueError` by construction, every time, regardless of
delivery order (delayed delivery does not change this — there is nothing
to deliver out of order, since the operation is rejected before any event
is minted). The only way to make a derived fact delegatable is to mint a
new authorization record naming it explicitly — which is `infer()` under
ACL vocabulary, horn (C), conceded.

**One honest side-note, not part of the original ask but worth recording**:
because horn (B)'s rule closure is a pure, live re-evaluation of currently-
held state rather than an append-only accumulator (`ever_established` in
`replica.py`), it is *more* aggressive than E-CRDT at un-deriving a fact
once a premise's grant is revoked — E-CRDT's documented "no cascading
retraction" limitation (round 1/2, `test_retracting_a_premise_does_not_
cascade_to_prior_inferences_documented_limitation`) does not apply to
horn (B) in the same way. This is not a point in the baseline's favor for
the IPR question (it still can't identify or delegate the derivation), but
it is a genuine, narrower difference and is recorded rather than glossed
over.

---

## Precise, final statement of the proved boundary

> Local derivation (`INFER`) with a proved, per-replica non-interference
> guarantee is reproducible by a standing-rule ACL construction **for the
> single property of confidentiality** — that much is conceded, and round
> 3's narrower claim (identity-gated observe/communicate alone is not
> novel) is reinforced, not reversed. What is **not** reproducible without
> minting an additional authorization event is the derived fact's own
> **stable, citable identity** — the specific dot that makes a derivation
> individually revocable, individually distinguishable from a different
> derivation of the same fact, and safely delegable onward with a real,
> verifiable provenance chain. This is a narrower, more precisely bounded
> claim than "derivation is impossible to reproduce" — the honest result
> of this round is that reproduction is *possible* for the derivation
> itself but *not possible* for what a real system needs to do with a
> derived fact next (revoke it precisely, or pass it on), without falling
> back to per-instance authorization events, i.e. `INFER` by another name.

## What this changes in V2/V3's conclusions

- V3's claim-scale statement (INFER/closure-derivation as the surviving
  claim) stands, but should be read specifically as claiming the
  **identity/provenance mechanism around a derivation**, not the bare
  admission decision — this round found the bare admission decision alone
  is, in fact, reproducible safely by a careful standing-rule
  construction. The claim's defensible core narrows further to: *dots as
  stable, individually-revocable, individually-citable identities for
  each derivation instance*, proved non-interfering, in a CRDT-merge
  setting.
- This makes the comparison to MAP-Graph (round 2, closest prior art)
  sharper, not weaker: MAP-Graph's recursive-ancestry propagation is
  exactly a "rule fires against currently-held state" construction (horn
  B), re-evaluated at query time — the same shape this round tested and
  found confidentiality-safe but identity-less. The distinguishing
  argument for any filing should lead with the identity/delegation gap
  found here, not the confidentiality argument used through round 3.

## Updated classification

Unchanged from V3: **BORDERLINE / NEEDS PROFESSIONAL OPINION** (see the
final answer delivered to the user this session). This round does not
move the needle on STRONG vs. BORDERLINE — it replaces one argument for
the boundary (a leak that didn't hold up) with a better one (a structural
identity/delegation gap that did), which is a more defensible position to
hand to a patent professional, not a stronger or weaker one.
