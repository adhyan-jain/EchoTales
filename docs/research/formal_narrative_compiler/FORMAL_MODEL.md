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
