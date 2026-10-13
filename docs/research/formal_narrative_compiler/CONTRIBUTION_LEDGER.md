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
