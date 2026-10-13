# Correctness properties

Notation as in FORMAL_MODEL.md. "Holds in the spec" means the property is a statement about `Q`/`compile`, never about
pixels or audio. Model-output properties (does the image obey the spec?) are out of scope and are probabilistic.

Summary of what survives:

| Property | Provable? | Holds in current code? | Standard consequence of known techniques? |
|---|---|---|---|
| T1 cutoff faithfulness (P1) | yes, short case analysis | **No** for persona attributes (D1, D3), voiding (D7), director (D8) | Yes: snapshot-read semantics |
| T2 historical belief preservation (P2) | corollary of T1 | **No** (D2, D7, D8) | Yes (bitemporal transaction-time closure) |
| T3 append-only extension is free for earlier cutoffs (P4, restricted) | corollary of T1 | No (follows T1) | Yes (MVCC-style reads at a version) |
| P3 embodiment | structural invariant, not a theorem | Mostly (two resolvers disagree) | Partly |
| P4 general revision correctness | only relative to a closure assumption | digest path: sound under C; read-set path: unsound and unused | Yes (Adapton, build systems); previously killed in-repo |
| P5 cross-modal agreement | trivial *if* single-sourced | **No** (voice, director) | Yes, by construction |

## T1. Cutoff faithfulness (reveal noninterference), P1

**Statement.** For every observer `o ≠ SYSTEM`, target `e`, timeline `tau`, story position `p` and knowledge position
`k`:  `Q(Φ, e, tau, p, o, k) = Q(Φ|≤k, e, tau, p, o, k)`.

Consequently, if `Δ` is any set of facts and witness entries all of whose effective learn times exceed `k` (including
facts whose *story-time interval* lies before `p`), then `Q(Φ ∪ Δ, …, k) = Q(Φ, …, k)`. Facts that describe earlier
story events but are first narrated after `k` are invisible at `k`. A retrospective *omniscient* mode must use
`o = SYSTEM` or `k = ∞`; that is the explicit exception.

**Assumptions.** I3 (`ρ > ℓ`), I4 (`ρ ≠ ⊥ ⇒ s = FALSE`, so truncation's reset `s := TRUE` restores the pre-retraction
state), A3 (deterministic tie order), **A5: canonicity is position-free or `Voided = ∅`** (see D7).

**Proof.** Fix `φ ∈ Φ` and let `φ'` be its image in `Φ|≤k` (absent if dropped). Every filter in `Q` other than `vis`
(timeline equality, `contains(I,p)`, voided set) reads only fields that truncation leaves unchanged, so it suffices to
show `vis_Φ(φ,o,k) ⇔ (φ' present ∧ vis_{Φ|≤k}(φ',o,k))`.
(a) `λ_o(φ) > k` or undefined: `vis_Φ` is false (clause `λ ≤ k`); `φ` is dropped from `Φ|≤k`. Equal.
(b) `λ_o(φ) ≤ k`, `ρ = ⊥`: truncation changes nothing; `vis` reads `s ≠ FALSE` on identical data. Equal.
(c) `λ_o(φ) ≤ k`, `ρ > k`: in `Φ`, `vis` requires `k < ρ`, true. In `Φ|≤k`, `ρ' = ⊥, s' = TRUE`, so `vis` is true. Equal.
(d) `λ_o(φ) ≤ k`, `ρ ≤ k`: by I3 `ℓ < ρ ≤ k`, so `φ` is retained with `ρ` unchanged; in both, `vis` requires `k < ρ`,
false. Equal.
The visible sets coincide. Attribute resolution takes, per key, the visible fact with greatest `ℓ` (ties by A3), a
function of the visible set; alias dedup, relations and bindings are likewise functions of visible sets (bindings use the
same `vis` shape, `state.py` L319-334, with `learned_at_pos` as `λ`). Witness entries `> k` are dropped by truncation and
cannot make a fact visible at `k`, since `λ ≤ k` is required. ∎

**Where the implementation breaks it (executable counterexamples).**
- *D1* persona attributes are admitted by `interval.from_lb <= position` alone. `probe_audit.py` probe A: a scar with
  `from_lb=3, ℓ=100` appears at `k=5` and the digest changes. `prop_cutoff.py`: 3059/6000 queries differ, all in the
  persona channel, 0 in `self_attributes` — empirical support that T1 holds for the `state_of` channel.
- *D7* a VOIDED timeline is dropped at every `k` (violates A5).
- *D8* `world/context.py::_facts_as_of` uses `learned_at.chapter <= chapter`, which satisfies case (a) but violates (c)
  and (d): `is_standing` drops every retracted fact at every `k`.

**Why it matters / what the plain baseline does.** Without the property a ch-100 reveal changes what a ch-5 reader sees,
and every cached artifact at cutoff 5 becomes spuriously stale (digest changes in probe A). **Independent test:**
`prop_cutoff.py` is a model-free differential test; it needs no generation backend.

**Standard-ness.** This is the semantics of reading an append-only log *as of version `k`* (snapshot reads) combined with
transaction-time closure for retraction. The proof is a four-case check. I regard T1 as a correct, useful specification
result, not a deep one.

## T2. Historical belief preservation, P2

**Statement.** If `φ` has `ρ = r` and `k < r`, then `Q(Φ, …, k)` is independent of `r`, and contains `φ` whenever it
contains it in the store where `φ` was never retracted.

**Proof.** Corollary of T1 with `Δ` = the retraction event at `r`: the retraction is the pair `(ρ := r, s := FALSE)`,
whose truncation to `k < r` is the original fact. ∎

**Separation from interval end.** Let `H1`: `φ` true on `[1,∞)`, retracted at 50. Let `H2`: `φ` true on `[1,50)` (closed at
50). For `p=20`, `k=60`: `H1` must return `φ` invisible (never true, as known at 60); `H2` must return it visible (it was
true at 20). A model that encodes retraction by interval end gives the `H2` answer to `H1`. A model that deletes the row
also fails at `k=20` (`H1` must return `φ`). Only `(ρ, positional vis)` gets all three right. This is the classical
valid-time / transaction-time distinction; the point is that Graphiti's `resolve_edge_contradictions` (sets `invalid_at`
and `expired_at` together) cannot make it.

**Implementation breaks:** D2 (persona attribute path), D7, D8.

## T3. Append-only extension is free for earlier cutoffs (restricted P4)

**Statement.** Let `A = F(compile(Φ, args, k))` be an artifact whose only dependence on `Φ` is through `compile` (closure
assumption C). If `Δ` has all effective learn times `> k`, then `digest(compile(Φ ∪ Δ, args, k)) = digest(compile(Φ,
args, k))`, so a content-addressed cache hits, and no artifact with cutoff `≤ k` is recomputed.

**Proof.** T1 gives `compile(Φ∪Δ,…,k) = compile(Φ,…,k)` provided `compile` factors through `Q`; equal inputs to the digest
give equal digests. ∎

**What this buys.** Ingesting chapter `n+1` never re-renders chapters `≤ n`. That is useful at 199 chapters. It is the
same fact as "a reader at a snapshot is unaffected by later commits".
**Implementation:** false today because of D1 (a later persona fact alters earlier digests).

## P4. General revision correctness

**Definition.** An artifact `a` computed from `compile(Φ, args)` is *stale under* `Φ'` iff `compile(Φ', args) ≠ compile(Φ,
args)` (semantic staleness, in terms of the spec rather than the rows read). The dependency is the function `compile`; a
"read set" is only an approximation of it.

**Claim P4-digest.** If (C) every field of every downstream artifact is a function of `Spec` and fixed configuration, and
(H) `digest` is injective on `Spec` up to hash collision, then equal digests imply an unchanged artifact, and unequal
digests recompute it (precision depends on the digest excluding irrelevant fields). *Proof.* Determinism of `F`. ∎ This
is content addressing with early cutoff; the proof is the standard one. **Not new**, and the repo already recorded this
(`packages/ecrdt/INVENTION_DISCOVERY_2026-09-30.md`, Candidate 2).

**Counterexample for the read-set method (`Store.invalidate_by_facts`).** Artifact `a` read `{attr:p1:hair_color:black}`.
A later insertion `hair_color=white` (greater `ℓ`) makes the answer `white`; the changed ref
`attr:p1:hair_color:white` is not in the read set, so the intersection is empty and `a` stays "valid". Read sets of
accepted facts are unsound under insertion without predicate footprints (phantoms). The method is unused in production;
the content digest of the resolved targets does not have this problem.

**Closure assumption C is false in the repo.** The director prompt is produced from `story_context` (D8), the canon
overlay (`apply_canon`), the whole-volume lexicon and the beat text, none of which enter `GenerationState.digest()`; the
director prompt cache uses the DB file's mtime+size. Staleness is therefore *whole-DB coarse* for prompts and
*state-precise* only for the persona channel. P4 holds at the image-cache level only to the extent the prompt is rebuilt
from the compiled state, which it is not.

## P3. Embodiment

**Statement (invariant, not theorem).** For a `Self e` and two positions `p1, p2` with different bound personas, every
`Self`-attached fact visible at both is identical at both, and the persona-attached fields of the spec at `pi` come only
from the persona bound at `pi`.
**Mechanism.** Type separation (`TargetKind.SELF` vs `PERSONA`) and bindings as edges (FORMAL_MODEL §6).
**Gap.** Two resolvers: `state_of` (honest, empty before first appearance) and `persona_at` (total; returns
`bindings[0]` or `:body1`). They can disagree (`plan_builder.py` docstring says so), and the fallback invents a body
rather than reporting none. This is a reconciliation task, not a proof obligation.
**Test without models:** assert `compile` and `persona_at` agree wherever `persona_at` is defined by a CERTAIN binding.

## P5. Cross-modal agreement

**Statement.** If two modalities `m1, m2` call `compile` with the same `(targets, p, k, o, tau)`, their specs agree on all
shared fields and on `admitted`. **Proof.** Both are projections `π_m` of one value `Spec` (A4). ∎ — trivial.
**Implementation:** false. Voice has no `p, k, o`; the director's brief is built on a different code path from the
`GenerationState` the image plan hashes. Agreement is a design discipline (single constructor), not a result.

## Assumption inventory

| Id | Assumption | Status |
|---|---|---|
| A1 | interval endpoints independent | holds by construction; conservative |
| A2 | caller supplies `k` off the main timeline | unenforced |
| A3 | store iteration order deterministic | **unenforced**; tie-breaks on `ℓ` and first-persona choice depend on it |
| A4 | adapters read only `Spec` | false today (canon, lexicon, beat text, `scene_state`) |
| A5 | voiding is position-free or empty | false by design (D7) |
| C | downstream artifacts closed over `Spec` | false today (D8) |
| I3, I4 | `ρ > ℓ`; `ρ ≠ ⊥ ⇒ s = FALSE` | unenforced |
| — | extraction correctness | **out of scope**: nothing here verifies that a fact correctly represents the text; every guarantee is relative to the store |

## Open proof obligations

1. Mechanize T1 (four cases; days of proof-assistant work) or keep the model-free fuzz test as the executable proof
   (`prop_cutoff.py`, render path).
2. State a retrospective mode (`p < k` with facts learned after the panel position, for a flashback panel) as an explicit
   modality with its own cutoff `k' > k`. The code derives `knowledge_pos` from the position's chapter and has no such mode.
3. Treat `correct()` (extraction revision) as a transaction-time operator and prove which cutoffs it can affect. Without
   transaction time on facts the property cannot be stated.
4. Monotonicity in the observer lattice (`W_o ⊆ W_o'` ⇒ `Q_o ⊆ Q_o'`) **fails** under the "latest `ℓ` wins" collision rule
   (more knowledge can replace a value), so any such statement must be about `admitted` refs, not about values.
