# Formal narrative compiler: model, properties, plan, related work, audit

> Merged on 2026-10-22 from 7 separate documents to keep the docs tree small. Each section below is one original file, text unchanged; its old path is in the section heading. The originals are in git history.

---

<!-- merged-from: docs/research/formal_narrative_compiler/CONTRIBUTION_LEDGER.md -->
## Source: `docs/research/formal_narrative_compiler/CONTRIBUTION_LEDGER.md`

# Contribution ledger

## Category 1 — Already present (no credit taken)

| Mechanism | Where | Note |
|---|---|---|
| Positional retraction distinct from interval end, with observer scope | `core/state.py::_visible_to_observer`, `interval.py::with_end` | tested (`test_state.py` L520-548); classical bitemporal idea |
| Three-valued fuzzy valid time | `core/interval.py` | special case of Dyreson-Snodgrass 1998 |
| Observer axis with witness rows; characters do not inherit reader knowledge | `state.py`, `Store.observations_for` | `test_observer_axis.py`; real data: 12 rows (RI), 0 (LOTM, ORV) |
| Self / Persona split, concurrent bindings | `models.py`, `state_of` persona section | tested; `persona_at` is a second, total resolver |
| Compiled `GenerationState` with deterministic digest, used in the render cache key | `state.py`, `render/plan_builder.py`, `render/cache_key.py` | content-addressed invalidation actually in use |
| Task-conditioned narrowing (never adds a fact) | `core/disclosure.py` | built, off in production |
| Substring leakage validator | `core/readset.py` | built, no production caller |
| Read-set invalidation | `Store.invalidate_by_facts` | built, unused, unsound under insertion (CORRECTNESS §P4) |
| Standing vs transient attribute split | `TRANSIENT_KEYS`, `appearance_of(standing_only)` | keyword-based transient state in `scene_state.py` |

## Category 2 — Missing implementation (required for any claim)

| # | Item | Why needed | Size |
|---|---|---|---|
| M1 | Persona attributes through `Q` (observer, `learned_at`, retraction) instead of `appearance_of`/`from_lb` | fixes D1, D2; makes T1/T2 true for the image path | small (route `persona_reader` through `StateResolver.state_of(PERSONA)`) |
| M2 | Positional voiding (`voided_at` on `NarrativeSegment`) | D7; A5 | small schema + `keep()` change |
| M3 | Certainty and ref on spec fields; explicit `plausible` policy | D5; the "never silently promote" requirement | medium (`GenerationState` schema change; digest version bump) |
| M4 | Opaque `Spec` constructor; director brief built from `Spec` rather than `story_context` | D8; closure assumption C, A4 | medium-large; changes prompts, so a regression render is needed |
| M5 | Label-propagating adapters and a label-subset check replacing the substring validator | enforcement of "admitted" | medium |
| M6 | Voice adapter taking `(p, k, o)` and consuming `Spec` | P5 | medium; voice casting is whole-volume by design today |
| M7 | Invariants I3/I4 enforced at `Store` insertion; `retract_attribute` | proofs assume them | small |
| M8 | Deterministic ordering (A3) | tie-breaks and "first persona" | small |
| M9 | Transaction-time axis for `correct()` | only if extraction revision is in the claim | large; defer or drop |
| M10 | Retrospective modality with explicit `k' > k` | open obligation 2 | small-medium |
| M11 | Real-data instances of retraction and retrospective reveal | D4: none exist in shipped DBs; reviewers will ask | requires extractor work or a hand-annotated slice |

## Category 3 — Candidate research contribution (what survives, and how weak it is)

1. **Primary (C-A).** *Cutoff-faithful, observer-indexed, retraction-aware query semantics for a narrative store, with
   a stated and proved faithfulness theorem (T1), its corollaries (T2, T3), and a model-free differential test that finds
   violations in a real pipeline.* Distinct from prior work only as a composition (C2-C4 in RELATED_WORK): NWM does the
   chapter hard-filter and separates reveal order, without retraction, observer scoping or a stated property.
   **Honest strength: moderate-to-low novelty, correct and useful.** The theorem is snapshot-read semantics.
2. **Complementary (C-B).** *Disclosure-labelled specifications.* A typed `Spec` whose fact-bearing fields carry `Ref` and
   `Cert`, constructible only by `compile`, with modality adapters that propagate labels and a label-subset check.
   Distinct from CineCrew's untyped FilmDSL and from the substring validator. **Honest strength: conjecture (C10); the
   enforcement idea is IFC applied to prompt assembly; novelty depends on a demonstration that it finds real leaks.**
   Evidence available now: D1, D2, D7, D8 were all found by checking the property, not by a label system.

Not claimed: generic incremental invalidation (Adapton / build systems; previously killed in-repo), bitemporality, fuzzy
intervals, DEL-style belief update, anything about model output fidelity.

---

<!-- merged-from: docs/research/formal_narrative_compiler/CORRECTNESS_PROPERTIES.md -->
## Source: `docs/research/formal_narrative_compiler/CORRECTNESS_PROPERTIES.md`

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

---

<!-- merged-from: docs/research/formal_narrative_compiler/FORMAL_MODEL.md -->
## Source: `docs/research/formal_narrative_compiler/FORMAL_MODEL.md`

# Formal model

Status key: **[EXT]** extracted from the code as it exists (cited); **[PROP]** proposed here, not implemented.
The aim is the smallest model that makes the properties in CORRECTNESS_PROPERTIES.md statable. It is deliberately
not a new language.

## 1. Sorts

| Sort | Meaning | Type / order | Code |
|---|---|---|---|
| `D` | discourse position `(chapter, offset)` | total order, lexicographic | `models.py::DiscoursePosition` [EXT] |
| `T_tau` | story time inside timeline `tau` | `R ∪ {±inf}`, total within a timeline; **timelines are mutually incomparable** | `StoryPos`, `_temporal_certainty` [EXT] |
| `Obs` | observers: `READER`, `SYSTEM`, character ids | `SYSTEM` omniscient; others see per `Observation` rows | `enums.py`, `state.py::observer_scope` [EXT] |
| `Self`, `Persona` | continuity of consciousness / a physical embodiment | disjoint id spaces | `models.py` [EXT] |
| `Ref` | stable fact identity independent of row ids | strings `kind:ident:parts` | `readset.py::observable_ref` [EXT] |
| `Cert` | `{C, P, X}` with `C > P > X`, conjunction = min | `Certainty.__and__` | `interval.py` [EXT] |

## 2. Fuzzy interval and `contains`

`I = (f⁻, f⁺, t⁻, t⁺)` with `f⁻ ≤ f⁺`, `t⁻ ≤ t⁺`, `t⁺ ≥ f⁻` (validator `_check_ordering`). A *reading* picks
`f ∈ [f⁻,f⁺]`, `t ∈ [t⁻,t⁺]`; the fact holds at `p` under the reading iff `f ≤ p < t`.

`contains(I,p) = X` if `p < f⁻ ∨ p ≥ t⁺`; `C` if `f⁺ ≤ p < t⁻`; else `P` [EXT].

**Lemma 1 (conservativeness).** `X` iff no reading holds at `p`; `C` implies every reading holds.
*Proof.* A holding reading exists iff `f⁻ ≤ p < t⁺` (choose `f=f⁻`, `t=t⁺`). All readings hold iff
`f⁺ ≤ p < t⁻`. If `t⁻ ≤ f⁺` the `C` band is empty. If readings with `f > t` are excluded as inconsistent, `C` stays
sound (it covers a superset of the readings) and `X` stays exact; `P` may then over-approximate "some but not all
consistent readings". ∎ **Assumption A1:** endpoints are independently bounded; no correlation between `f` and `t` is
represented.

## 3. Facts

A temporal fact `φ = (subj, body, tau, I, ℓ, o, s, ρ)` [EXT: `models.py::TemporalFact`]:

| Field | Type | Meaning |
|---|---|---|
| `body` | `Attr(key,val)` \| `Alias(surface,type)` \| `Rel(type,dst)` | what is claimed. Generic descriptors are rejected at construction (`AliasBinding._reject_generic_descriptors`) |
| `tau` | timeline id | story-time coordinate system |
| `I` | FuzzyInterval | when it holds in story time |
| `ℓ` | `D` | when the **reader** was told (`learned_at_pos`) |
| `o` | `Obs` | stamp: whose assertion this is (the pipeline stamps `READER`) |
| `s` | `{TRUE,FALSE}` | `FALSE` = asserted untrue on arrival, or retracted |
| `ρ` | `D ∪ {⊥}` | `retracted_at`: from this position the claim is known false |

Invariants. **I1** `I` well-formed [EXT, enforced]. **I2** alias type enters the graph [EXT, enforced].
**I3 `ρ = ⊥ ∨ ρ > ℓ`** [PROP: enforced nowhere; Theorem 1 needs it]. **I4 `ρ ≠ ⊥ ⇒ s = FALSE`** [PROP:
`retract_alias` maintains it; `add_attribute` accepts any combination].

Witness map `W_o : Ref ⇀ D` for a character `o` (`Store.observations_for`) [EXT].

**Effective learn time.** `λ_o(φ) = ℓ` if `o = READER` and `φ.o = READER`; for a character `o ≠ φ.o`: `W_o(ref φ)` if
`φ.o = READER` and defined, else undefined; if `φ.o = o`: `ℓ`. [EXT: `_visible_to_observer`]

## 4. Visibility and the query

```
vis(φ, o, k)  ≡   o = SYSTEM
              ∨ ( λ_o(φ) defined ∧ λ_o(φ) ≤ k
                  ∧ ( φ.ρ ≠ ⊥  ?  k < φ.ρ  :  φ.s ≠ FALSE ) )                  [EXT state.py L81-139]
```

`k` is the **knowledge position**. Default: the chapter containing `p` on the main timeline, unbounded elsewhere
(`state_of` L238-243). **Assumption A2:** on non-main timelines the caller supplies `k`.

`Q(Φ, e, tau, p, o, k)`: the facts about `e` with `vis ∧ contains(I_φ, p) ≠ X ∧ φ.tau = tau ∧ φ.tau ∉ Voided`, each
tagged with its `contains` value. Attribute collision rule: per key keep the visible fact with the greatest `ℓ`
(ties go to the later row because the comparison is `≥`). **Assumption A3:** store iteration order is a
deterministic function of the fact set; the code does not guarantee it.

Persona selection: `bind(self, tau, p, o, k)` = persona ids of visible `SelfPersonaBinding`s whose interval does not
exclude `p` (list; concurrent allowed). The drawn persona is the first (store order, A3).

## 5. Revision operators

Let `Φ` be a store (finite set of facts, bindings, observations).

- `ingest(Φ, Δ)`: add facts/observations whose `λ` lies beyond the previously ingested prefix **(append)**.
- `retract(Φ, φ, r)`: set `φ.ρ := r`, `φ.s := FALSE`, `r` ≥ the current ingest frontier **(narrative revision)**.
- `close(Φ, φ, e)`: `I := I.with_end(e)`; explicitly not a retraction (`interval.py::with_end`) **(world change)**.
- `correct(Φ, ·)`: human/extractor error fix that rewrites a fact in place (`corrections.py`) **(extraction
  revision)**. This is the one operator with no semantics in the current store: it destroys the previous belief state
  of the *graph*, as opposed to of an *observer*. A proper treatment needs a third axis, transaction time `x`, which
  `Store` does not carry on facts. [PROP; CONTRIBUTION_LEDGER, category 2]

Truncation (used only to state properties): `Φ|≤k` drops every fact with `λ_o(φ) > k` and every witness entry `> k`,
and for retained facts with `ρ > k` sets `ρ := ⊥, s := TRUE`.

## 6. Embodiment

`Self` ids key identity: aliases, relations and knowledge attach to `Self`; appearance, age, attire and voice timbre
attach to `Persona`. A binding is an edge `(self, persona, tau, I, ℓ, o)`.

- **Continuity.** Changing the persona bound at `p` changes no `Self`-attached fact, since facts are keyed by `subj`
  and bindings are separate edges. [EXT, structural]
- **Standing vs transient.** `TRANSIENT_KEYS = {current_condition}`; `appearance_of(standing_only=True)` drops them
  [EXT]. Scene-level transient state (`SceneState`) is *not* a `TemporalFact`, so it carries no observer or cutoff
  [EXT]. A typed `Transient(scene, key, val)` admissible only inside its scene is [PROP].

## 7. The compile function

Existing signature [EXT]: `compile_generation_state(store, novel, targets, position, observer_id, knowledge_pos,
resolver, persona_reader) -> GenerationState`.

Proposed denotation [PROP]:

```
compile : Store × Scene × Timeline × Position(p,k) × Observer × Modality × Policy -> Spec

Spec = { header : (o, p, k, tau, modality),
         targets: [ { self, personas: [pid],
                      fields: key -> (value, cert ∈ {C,P}, ref ∈ Ref) } ],
         admitted: Set(Ref),                 -- everything the spec may mention
         withheld: Set(Ref, reason),         -- visible in Φ but not admitted; reason ∈ {epistemic, task, policy}
         digest : Hash(canonical(targets, admitted)) }

Policy = { plausible ∈ {exclude, mark},  task ∈ TaskSpec (disclosure.py) }
```

Differences from the code: (i) `fields` carry `cert` and `ref` (D5/D6); (ii) persona attributes come from `Q` on the
persona target, not from `appearance_of` (D1/D2); (iii) `withheld` records *why*, replacing lexical
`forbidden_facts`; (iv) `Spec` has an opaque constructor: only `compile` builds one.

**Admissibility rule (the single place uncertainty is decided).** Under `plausible = exclude`, a fact is admitted iff
`vis ∧ cert = C`. Under `mark`, `cert = P` facts are admitted with the mark and each adapter must render them hedged
or drop them. A field has `cert = C` only if `contains = C` for **every** contributing fact (the `Cert` conjunction).

**Modality projection.** `π_m : Spec -> Spec_m` is a total function of `Spec` alone (**A4:** adapters read nothing
else). `Prompt_m = render_m(π_m(Spec))`, and each rendered span carries the `Ref`s it was built from.

**Missing information.** A required key with no visible fact is reported (`disclosure.py::unsatisfied_keys`) and never
filled by a default inside `compile`. Defaults (genre, `apply_canon`) are applied afterwards as labelled `Spec`
extensions with their own provenance; today they are applied silently (audit §2, Director context).

## 8. What this model is not

It is not a new logic. `Q` is a filter over a finite set; its meaning is first-order and the properties are induction
over that filter. The nontrivial parts are *design choices*: retraction decided by position rather than by interval;
observer defaults to non-inheritance; plausibility decided at the spec boundary.

---

<!-- merged-from: docs/research/formal_narrative_compiler/IMPLEMENTATION_PLAN.md -->
## Source: `docs/research/formal_narrative_compiler/IMPLEMENTATION_PLAN.md`

# Implementation plan (conditional: NARROW)

The gate did not pass cleanly (NOVELTY_DECISION). This plan covers only the NARROW core and is ordered so that it can be
**abandoned after Stage 0 or 1 at low cost**. Nothing here has been started. No GPU, no paid calls; each stage is
unit-test scale.

## Invariants that must stay intact
- `core` imports nothing from `pipeline` (`test_import_direction.py`).
- The existing test suite stays green (`python3 -m pytest packages/core/tests packages/pipeline/tests`).
- Render cache keys change only through a `RENDER_CACHE_VERSION` bump (documented in `cache_key.py`).
- No change to default render output for a store with no retrospective/retracted facts (D4 says that is every shipped DB),
  verified by a before/after `state_digest` comparison on RI and LOTM.

## Stage 0 — Make the property executable (1-2 days)
- Add `packages/core/tests/test_cutoff_faithfulness.py` from `probes/prop_cutoff.py`: seeded random stores; assert
  `compile(S,k) == compile(S|≤k,k)` for the `state_of` channel (passes now) and for the render compile (fails now; mark
  `xfail(strict=True)` with the D-number until Stage 1).
- Add the two regression tests from `probe_audit.py` (probes A and B).
- **Kill criterion:** if the differential test finds no violation outside the persona channel and Stage 1 turns it green
  with a ≤30-line change, this is a bug fix, not a research direction: stop and write a HANDOFF section.

## Stage 1 — Close the persona channel (M1, M7, M8) (2-3 days)
- `plan_builder.compile_render_state`: persona reader derived from `StateResolver.state_of(PERSONA, observer,
  knowledge_pos)` restricted to `APPEARANCE_KEYS`, replacing `appearance_of(position=…)`; `_fold_target` `persona_facts`
  from the same call.
- `TemporalFact` validator for I3/I4; `Store.retract_attribute`.
- Deterministic ordering: `ORDER BY` on every `get_*` used by `state_of` (A3).
- Bump `RENDER_CACHE_VERSION`. Compare digests on RI/LOTM before/after (expect equal, per D4).

## Stage 2 — Positional voiding and a retrospective mode (M2, M10) (2 days)
- `NarrativeSegment.voided_at: DiscoursePosition | None`; `keep()` excludes a voided timeline only when
  `knowledge_pos ≥ voided_at`.
- Explicit `knowledge_pos` override on `compile_*` for flashback panels.
- Tests: the D7 scenario at `k=105` vs `k=125`.

## Stage 3 — Certainty and refs in the spec (M3) (3-4 days)
- `GenerationState` gains `cert` and `ref` per field and a `plausible` policy; `to_dict`/`from_dict`/digest updated.
  Default `exclude` changes behavior (PLAUSIBLE persona facts stop appearing), so gate it with a flag until measured on RI.
- **Kill criterion:** if `exclude` leaves more than a few percent of RI panel characters without a drawn persona, the policy
  is unusable for generation and the uncertainty claim of C-A weakens; fall back to `mark`.

## Stage 4 — Close the boundary (M4, M5) (1-2 weeks, optional, highest risk)
- Build the director brief from `Spec` (not `story_context`); route `apply_canon` and the lexicon through labelled
  extensions.
- Label-propagating prompt assembly with a subset check; a production caller for the validator.
- **Kill criterion:** if re-rendering one RI chapter changes more than the panels the diff explains, or director quality
  visibly regresses, revert and keep Stages 0-3 only.

## Stage 5 — Voice adapter (M6) and the narrow demonstration (about 1 week)
- Stub engines only (`ECHOTALES_LLM_MODE=stub`, `--image-engine stub`). A synthetic 12-chapter fixture with one
  retraction, one retrospective reveal, one body swap, and one observer with a witness row. Ingest chapter by chapter and
  assert: (T3) no artifact with cutoff ≤ n is recomputed when chapter n+1 is added; (T2) the pre-retraction spec is
  byte-identical after the retraction; image, voice and director specs agree on `admitted`.
- Output a table, not a benchmark campaign.

## What would invalidate the design
- A real novel (or a hand-annotated slice) shows the extractor cannot produce retraction/retrospective facts at usable
  precision (M11): the semantics then has no real-world content to protect.
- NWM or a follow-up publishes observer-scoped, retraction-aware retrieval with a stated property.
- Stage 4's boundary closure cannot be achieved without rewriting the director.

## Explicitly out of scope
Tri-temporal `correct()` (M9), any claim about generated pixels or audio, a paper draft, benchmarks, model comparisons.

---

<!-- merged-from: docs/research/formal_narrative_compiler/NOVELTY_DECISION.md -->
## Source: `docs/research/formal_narrative_compiler/NOVELTY_DECISION.md`

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

---

<!-- merged-from: docs/research/formal_narrative_compiler/RELATED_WORK.md -->
## Source: `docs/research/formal_narrative_compiler/RELATED_WORK.md`

# Related work and claim-by-claim novelty comparison

Searched 2026-10-13 (web search plus page fetches). **P** = arXiv preprint, no venue found. Every row says how it
was checked. Items marked *not verified* were recalled from memory and must not be cited without checking.

## 1. Verified references

| Work | Authors / ID / status | How checked | Relevant content (with section) |
|---|---|---|---|
| Narrative World Model: Narratology-Grounded Writer Memory for Long-Form Fiction | Saifullah, Kornmaier, Kazi, Sharma, Kanade, Yadav; arXiv:2607.05577v1 (Jul 2026), **P** | HTML body fetched (read ~92%; tail of Appendix J unread) | §3.2 typed records: event order and **reveal order stored separately**, focalized observer, character/reader knowledge slots, world facts with valid chapter range; §3.3/App. A edges carry `valid_at`/`invalid_at`, closed interval = superseded; §3.5/App. A retrieval = hard filter `source chapter <= n`; §3.1 republishing a chapter re-extracts it and invalidates dependent edges; **no retraction mechanism, no observer-scoped retrieval, no formal guarantee, no multimodal output**; no code link |
| Narrative Knowledge Weaver | Tian et al.; arXiv:2606.05724 (Jun 2026), **P** | search snippets only | entity/event/fact graph; query-time audit of actor, scope, polarity, temporal constraints; QA system. *Body not read.* |
| CANVAS: Continuity-Aware Narratives via Visual Agentic Storyboarding | Mondal, Song, Parmar, Goyal, Pfister, Song, Boyd-Graber; arXiv:2604.13452 (Apr 2026), **P** | HTML fetched (first ~65%) | §3.1 plan P=(C,L,O): appearance/location/object state per shot, defined in prose; §3.2 visual memory, **stale anchors replaced by overwrite, no invalidation step**; no observer/epistemic model; nothing formally guaranteed; project page only, no code |
| Better Call CineCrew: Consistent Ultra-Long Narrative-to-Film Generation | Chen, Dong, Zhou, Ma, Dou, Matusik, Gan; arXiv:2609.07720 (Sep 2026), **P** | HTML fetched | §3.3 **FilmDSL** = "JSON-like object" (global meta, asset refs, production memory, clip list; per clip: action / staging / render spec). No type system, no knowledge or time scoping, no invalidation policy; Alg. 1 regenerates keyframes inside retry loops |
| DramaAgent: Agentic Storytelling Video Generation | Huang, Wu, Chen, Zhang, Cheng, Lan, Wang, Tang; arXiv:2610.00097 (header says 08 Sep 2026 although the id suggests later — verify before citing), **P**; code github.com/AIGeeksGroup/DramaAgent (not inspected) | HTML fetched | §3.4 candidate scoring plus diagnosis-driven local regeneration (K=3, tau=0.80, R=2); temporal score reads only earlier accepted scenes; no dependency graph, no observer model, no theorems |
| Staying In Character: Perspective-Bounded Memory for Book-Based Role-Playing Agents | Tang et al.; arXiv:2606.25632 (Jun 2026), **P** | abstract page only | "visibility-tagged facts" per character; fidelity measured empirically (KBF-QA); no guarantee stated; retraction not covered. *Mechanism not read.* |
| EvolvTrip: Enhancing Literary Character Understanding with Temporal Theory-of-Mind Graphs | Yang et al.; arXiv:2506.13641; code Bernard-Yang/EvolvTrip | search snippet only | per-character mental-state triples tagged with plot segment. *Body not read.* |
| ViStoryBench | ShanghaiTech et al.; CVPR 2026 (per search result) | snippet only | story-visualization consistency benchmark; empirical |
| Story-Iter: A Training-free Iterative Paradigm for Long Story Visualization | Mao, Huang et al.; arXiv:2410.06244; ICLR 2026 (proceedings link found); code UCSC-VLAA/story-iter | search result | image-level iterative reference conditioning; no narrative state |
| Graphiti (getzep/graphiti) | open source; cloned 2026-10-13 at commit `2f0fb35` | **source read**: `graphiti_core/utils/maintenance/edge_operations.py::resolve_edge_contradictions` L748-783; `edges.py::EntityEdge`; `search/search_filters.py` | edges have `valid_at`, `invalid_at`, `expired_at`, `created_at`. A newer contradicting edge **sets the older edge's `invalid_at` and `expired_at` together** (interval-end and supersession are one operation). Temporal filtering is generic date predicates. Grep for observer/perspective/as_of in `graphiti_core`: no concept of observer |
| Adapton: Composable, Demand-Driven Incremental Computation | Hammer, Khoo, Hicks, Foster; PLDI 2014 pp. 156-166, doi 10.1145/2594291.2594324 | search result (abstract) | demand-driven incremental computation. Its soundness theorem is cited by `packages/ecrdt/INVENTION_DISCOVERY_2026-09-30.md`; I did **not** re-read the theorem this session |
| Build Systems à la Carte | Mokhov, Mitchell, Peyton Jones; ICFP 2018 | Hackage page | scheduler x rebuilder taxonomy |
| Supporting Valid-Time Indeterminacy | Dyreson, Snodgrass; ACM TODS 23(1), 1998, pp. 1-57 | search result (abstract) | possible-instants model for uncertain times with credibility/plausibility constructs and a denotational semantics for SELECT |
| A Consensus Glossary of Temporal Database Concepts | Jensen, Snodgrass et al., 1994 (rev. 1998, LNCS 1399) | search result | valid time / transaction time / bitemporal |
| Language-Based Information-Flow Security | Sabelfeld, Myers; IEEE JSAC 2003 | search result | noninterference survey; Goguen-Meseguer credited as origin (original not retrieved) |
| Character Beliefs in Story Generation | Eger, Martens; AIIDE 2017 | search result | dynamic epistemic logic for belief update in story planning |
| A Possible Worlds Model of Belief for State-Space Narrative Planning | Shirvani, Ware, Farrell; AIIDE 2017 | search result | beliefs as possible worlds in narrative planning |
| Provenance Semirings | Green, Karvounarakis, Tannen; PODS 2007 | search result | semiring provenance for queries |
| Foundations of Differential Dataflow | Abadi, McSherry, Plotkin; FoSSaCS 2015 | search result | theory of incremental dataflow |
| Bitemporal agent-memory systems | post-graph-rag (arXiv:2608.24921); Graph-Native Bitemporal Memory Store (arXiv:2607.26520); TGMS (arXiv:2607.10265); WorldDB (arXiv:2604.18478) | snippets only | valid time + transaction time, supersede-not-delete; none read in depth |

*Not verified this session:* Shake (Mitchell, ICFP 2012), Salsa, DRed (Gupta-Mumick 1993), predicate locking, MVCC / snapshot
isolation references. Below they appear only as "known practice".

## 2. Claim-by-claim comparison

Confidence = my estimate that a reviewer in the relevant community would accept the claim as new
(L < 25%, M, H > 70%). These are judgments, not measurements.

| # | Candidate claim | Closest prior work | What prior work actually does | Exact remaining difference | Evidence | Class | Conf. |
|---|---|---|---|---|---|---|---|
| C1 | Story time and discourse/reveal time are separate axes | NWM §3.2; bitemporal glossary | NWM stores event order and reveal order separately; bitemporal DBs separate valid and transaction time | None of substance | NWM §3.2 | Established | L |
| C2 | Chapter-cutoff retrieval cannot leak later facts | NWM §3.5/App. A; Perspective-Bounded Memory | hard filter on source chapter; empirical fidelity | A *stated and proved* property (prefix-faithfulness), including facts that describe earlier story time | NWM; 2606.25632 abstract | Known practice + possible formalization | L-M |
| C3 | Retraction (never true / believed then refuted) is distinct from interval end (true then ceased), positional per observer | Graphiti `resolve_edge_contradictions`; NWM (no retraction); bitemporal transaction-time closure | Graphiti sets `invalid_at` and `expired_at` together on supersession; classical bitemporal can encode "believed until r" as transaction-time closure | Expressible in bitemporal models already. What differs in practice is making it first-class **per observer** and checking it on the compiled output | Graphiti L748-783; Jensen et al. | Established model, uncommon in LLM-memory systems | L-M |
| C4 | Observer-indexed knowledge via witness rows; a character does not inherit the reader's knowledge | Perspective-Bounded Memory (visibility tags); EvolvTrip; Eger-Martens DEL | tags / triples / DEL updates; none gives a cutoff-indexed witness map with a formal prefix property | Combination: witness map x cutoff x retraction in one query algebra | `core/state.py` L81-139 vs papers | Possible new composition | M |
| C5 | Three-valued fuzzy valid time | Dyreson-Snodgrass 1998 | possible instants with credibility/plausibility, full denotational semantics | EchoTales' intervals are a strict special case. **Not new.** Carrying the three-valued result *into a generation spec* is done by neither (and not by EchoTales, D5) | TODS 98 abstract; audit D5 | Established | L |
| C6 | Typed specification between narrative state and renderers | CineCrew FilmDSL; CANVAS plan tuple | untyped JSON / prose-defined state; no knowledge scoping | A spec whose fact-bearing fields carry source refs and certainty and which can only be built through the epistemic query. **Not implemented** (D5, D6) | CineCrew §3.3; CANVAS §3.1 | Possible new composition (unbuilt) | M |
| C7 | Selective invalidation of derived artifacts after a state change | DramaAgent (diagnosis-driven); NWM §3.1 (chapter-level); Adapton / build systems | local regeneration after failed review; per-chapter invalidation; general sound incremental computation | The generic mechanism is established. Only the *cutoff-indexed* corollary (appending later facts never invalidates earlier-cutoff artifacts) is domain-specific, and it is snapshot-read semantics in other words | DramaAgent §3.4; NWM §3.1; `ecrdt/INVENTION_DISCOVERY` Candidate 2 | Known practice (applied) | L |
| C8 | Cross-modal agreement on epistemic state | none found | multi-agent pipelines pass prompts per agent | Agreement by construction if every modality projects one compiled value. EchoTales does **not** currently satisfy it (voice, director bypass) | CineCrew, CANVAS, DramaAgent: no such notion | Unimplemented | M if built |
| C9 | Embodiment: one identity, several bodies; appearance change is not identity change | CANVAS character anchors; VideoMemory (snippet only) | per-character appearance anchors, overwritten or banked | Typed Self/Persona split with intervals and observer-scoped bindings (disguise, concurrent bodies) | `core/models.py` L247-285; CANVAS §3.2 | Possible new composition | M |
| C10 | Label-checked disclosure: prompt content carries provenance labels checked against the admitted set | Sabelfeld-Myers IFC; EchoTales' substring `EpistemicLeakageValidator` | IFC labels in programs; substring check here | Applying a label discipline to multimodal prompt assembly. I found no instance in the generative-video literature, but that is absence of evidence from limited search | searches 2026-10-13 | Unverified conjecture | M-L |

I did not find a paper stating a formal noninterference-style theorem for narrative retrieval or multimodal
specification. That is weaker than "none exists": about 20 queries, snippet-level for most items.

---

<!-- merged-from: docs/research/formal_narrative_compiler/REPOSITORY_AUDIT.md -->
## Source: `docs/research/formal_narrative_compiler/REPOSITORY_AUDIT.md`

# Repository audit — narrative state → multimodal specification

Audited 2026-10-13 against the working tree (branch `validation/evidence-pass-2026-09-24`,
HEAD `e34a628`, 55 modified/untracked entries, none touched). Read-only: no production file was
edited. Executable evidence is in `probes/` (run with `source .venv/bin/activate && python probes/<file>`).

Legend: **[V]** verified by reading code and/or running a probe this session.

## 1. Data flow (what actually runs)

```
EPUB -> ingest -> spans -> mentions -> resolve ---> Store (SQLite)
                                                     Attribute/AliasBinding/Relation  (TemporalFact)
                                                     SelfPersonaBinding, Observation, Segment
                         ┌───────────────────────────┴───────────────────────────────┐
                         │                                                           │
        core/state.py::StateResolver.state_of                         world/context.py::story_context
        (observer+learned_at, retraction, interval filters)           (OWN filter: learned_at chapter only)
                         │                                                           │
   compile_generation_state / compile_render_state                          LLM director brief --> prompt text
     -> GenerationState (targets, allowed/forbidden, digest)                 (render/panels.py ~L2370)
                         │   persona attrs via appearance_of()  <-- bypasses state_of filters
                         ▼
   build_render_plan -> VisualRenderPlan -> compute_render_cache_key -> image backend -> PNG + manifest

   voice/*  : per-character, whole-volume, NO position / observer input  (no state_of call in voice/)
```

## 2. Mechanism table

| Mechanism | Actual implementation | Active call path | Existing tests | Known limitation | Research relevance |
|---|---|---|---|---|---|
| Three-valued fuzzy valid time | `core/interval.py::FuzzyInterval.contains` -> CERTAIN/PLAUSIBLE/EXCLUDED; endpoints are independent bounds [V] | `state.py::_temporal_certainty`, `persona/split.py::persona_at` | `core/tests/test_interval.py` | Endpoints independent; no consistent-reading restriction (conservative, FORMAL_MODEL §2). `StateOfResult.certainty` is computed but **dropped** by `compile_generation_state` (`GenerationState` has no certainty field) [V] | Uncertainty is not carried into the spec: PLAUSIBLE facts become "allowed" silently |
| Discourse-time (learned_at) filter | `state.py::_visible_to_observer` L81-139: `learned > knowledge_pos -> hidden` [V] | `state_of` (aliases, SELF attrs, relations, bindings) | `test_state.py` (`test_a_fact_is_invisible_before_the_reader_learns_it`, `test_a_reveal_applies_retroactively_in_story_time`) | **Not applied** to persona attributes inside `compile_*` (D1) | Core of P1 |
| Positional retraction | `_visible_to_observer` L129-135: `knowledge_pos < retracted_at`, FALSE stamp ignored [V] | `state_of` | `test_state.py` L520-548 | `Store` has `retract_alias` only; no `retract_attribute`; no invariant `retracted_at > learned_at_pos` on `TemporalFact` [V] | Core of P2 |
| Observer axis | `observer_scope`, `Store.observations_for`; a character sees a READER-stamped fact only via an `Observation` row [V] | `state_of(observer_id=...)`, `render --observer` via `StateResolver.default_observer` | `test_observer_axis.py` | Real data: RI has **12** observation rows, LOTM/ORV **0** [V] | P1/P5 beyond READER are synthetic-tested only |
| Self / Persona split | `SelfPersonaBinding` (interval, learned_at, observer); `state_of` returns `persona_ids` (concurrent allowed) [V] | `compile_generation_state`; `panels.py::character_looks` | `test_state.py` body-swap/clone/possession classes; `test_self_persona_boundary.py` | A second resolver `persona/split.py::persona_at` is *total* (returns `bindings[0]` before first appearance, `:body1` when none); it is still the path of `world/context.py` and the fallback in `character_looks` [V] | P3 |
| Compiled state | `core/state.py::GenerationState`, `compile_generation_state` L688, `digest()` L553 [V] | `plan_builder.compile_render_state` <- `panels.py` L2086, L2205 | `pipeline/tests/test_generation_state_wiring.py`, `test_plan_builder.py` | Digest omits observer, position, allowed/forbidden by design (comment L553-563) | The "compile" function itself |
| Minimal disclosure | `core/disclosure.py::compile_minimal_disclosure` (narrows, never adds) [V] | `build_render_plan(use_mdc=True)` only; **off in production** | `core/tests/test_disclosure.py`; `scripts/eval/mdc_disclosure_ablation.py` | Experiment flag, default False | Task-conditioned admission — built, unused |
| Leakage validator | `core/readset.py::EpistemicLeakageValidator` — casefold **substring** match of `forbidden_facts` in text [V] | **No production caller** (only `scripts/eval/` and tests) [V] | `test_state.py::TestGenerationStateAndValidator` | Lexical, not label-based; unused in render | The enforcement gap |
| Read-set invalidation | `Store.record_artifact` L1806, `invalidate_by_facts` L1815 (set intersection) [V] | **Zero production callers**; `derived_artifact` has 0 rows in all three DBs [V] | `test_state.py` L789-798 only | Read set records *accepted* facts only (no predicate footprint) -> unsound for insertion (CORRECTNESS §P4) | Documented-but-dead mechanism |
| Actual staleness control | Content-addressed: `render/cache_key.py::compute_render_cache_key` hashes `plan.state_digest` + prompt + backend + seed ... [V] | `render/panels.py` image cache | `pipeline/tests/test_render_cache_key.py` | Reference images hashed by *path*, not bytes (module docstring). Director prompt cache keyed by **DB mtime+size** (`panels.py` ~L1680): whole-DB invalidation | Closest thing to P4 enforcement |
| Director context | `world/context.py::story_context` -> `_facts_as_of` (learned_at chapter only, `is_standing` only) [V] | `panels.py` ~L2370 -> LLM prompt | none targeting epistemics | Ignores observer, retraction position, interval, truth status; drops retracted facts at **all** positions; `_appearance_brief` applies `apply_canon` (position-free canon table); lexicon built from the *whole volume* (`panels.py` ~L1690) | The largest bypass of the compile boundary |
| Transient scene state | `render/scene_state.py::derive_scene_state` — keyword severity from narration, stored per `Scene` [V] | `panels.py` | `core/tests/test_scenestate.py`, `pipeline/tests/test_scene_state.py` | Keyword matching; not a `TemporalFact`; no observer/cutoff | Standing vs transient exists structurally (`TRANSIENT_KEYS`) |
| Corrections | `pipeline/corrections.py` mutates the live store (rebinds mentions, merges entities, appends an event) [V] | `webview_server.py` | not reviewed | No transaction-time axis on facts: an extraction fix overwrites history | Revision semantics are single-axis |
| Voice | `voice/casting.py`, `voice/runner.py`: per-character, whole-volume; `state.py` docstring says so [V] | `voice` CLI | voice tests (not reviewed) | No position, observer, or persona input -> P5 does not hold across modalities | Cross-modal agreement is currently false |

## 3. Defects found (executable)

**D1 — post-cutoff persona fact reaches the spec (violates P1).** `appearance_of`
(`persona/reference_gen.py` L205-209) and `_fold_target` (`state.py` L653-657) filter persona attributes by
`interval.from_lb <= position` only. A scar acquired in chapter 3 and *first narrated* in chapter 100 has
`from_lb=3`, `learned_at=100`. A reader panel at chapter 5 draws the scar and the digest changes when the
chapter-100 row is inserted. `state_of(SELF attrs)` is correct for the same kind of fact: the persona channel
never calls the observer/learned_at filter. (`probes/probe_audit.py`, probes A and A')

**D2 — retracted belief erased from history (violates P2).** `appearance_of` skips `not attr.is_standing`
(`retracted_at is not None`) at every position. `state_of(PERSONA)` at chapter 20 returns the believed
`hair_color=white`; the compiled/drawn attributes are `{}`. (probe B)

**D3 — differential test.** `probes/prop_cutoff.py`: 300 random stores x 20 cutoffs = 6000 queries, comparing
`compile_render_state(S,k)` with `compile_render_state(S|<=k,k)`. **3059 (51.0%) differ**, all in the persona
channel (`persona_attributes` 2834, `persona_facts` 3059); `self_attributes` differs in **0**. Caveat: the
stores are adversarial by construction (30% retractions, retrospective dating). This is a bug-finder, **not a
prevalence estimate**.

**D4 — latent on real data.** In `data/db/*.db` there are **0** retrospectively-dated persona attributes,
**0** retracted attributes/aliases, and 0 `derived_artifact` rows (RI: 617 persona attributes; LOTM: 558; ORV:
none). The extractor never emits the conditions D1/D2 need, so these defects are real in code but unexercised
by shipped data. Any claim about retraction/retrospective reveals currently rests on synthetic fixtures.
(Read-only SQL, `mode=ro`.)

**D5 — uncertainty promoted.** `compile_generation_state` defaults `include_plausible=True`; `allowed_facts`
strings (`attr:k=v`) carry no certainty; `StateOfResult.certainty` is discarded.

**D6 — `forbidden_facts` is lexical and unenforced.** Built from raw values of facts not allowed; may contain
values that are also allowed via another key; no production caller.

**D7 — voiding is position-free (violates P1/P2 by design).** `StateResolver.keep` (`state.py` L261-262) drops every
fact on a `VOIDED` timeline for every `knowledge_pos`; `NarrativeSegment.canonicity` has no "voided at" discourse
position. A chapter-120 reveal that chapter 100-120 was an illusion therefore removes those facts from a query at
chapter 105, where the reader still believes them, although the module docstring (L28-29) promises they "stay
reachable for what did the reader believe at the time". Verified by code reading and the existing test
(`test_state.py::TestVoidedSpans`), which only checks exclusion and never a pre-reveal query. Not run as a probe.

**D8 — the director path bypasses the compile boundary.** `render/panels.py` (~L2370) builds the LLM brief with
`world/context.py::story_context`, which uses `_facts_as_of` (`learned_at.chapter <= chapter`, `is_standing` only),
`persona_at` (total resolver), `apply_canon` (position-free canon table) and a whole-volume lexicon. No observer, no
retraction position, no certainty, and no `GenerationState`. This is the prompt that decides what the image shows, so
the guarantees of `state_of` cover the *cache key* more than the *content*. Verified by code reading.

## 4. Implemented / unused / documented-only

- **Implemented and used:** `state_of`, `FuzzyInterval`, `GenerationState` + digest, render cache key, observer plumbing (`render --observer`).
- **Implemented, unused in production:** `compile_minimal_disclosure`, `EpistemicLeakageValidator`, `record_artifact`/`invalidate_by_facts`.
- **Absent:** transaction time for extraction revisions; certainty in the spec; voice-side position/observer.
- **Not reviewed in depth:** `docs/research/DECISION_LOG.md` and the arena experiments (instructed not to revive them). `packages/ecrdt` was read only for its prior kill decision (`INVENTION_DISCOVERY_2026-09-30.md`, Candidate 2: cache-invalidation completeness killed on Adapton).
