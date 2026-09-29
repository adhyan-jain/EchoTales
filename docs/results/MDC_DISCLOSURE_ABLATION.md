# Minimal Disclosure Compiler — disclosure ablation

**2026-09-27.** Script `scripts/eval/mdc_disclosure_ablation.py`; result
`data/eval/mdc_disclosure_ablation.json`; canonical database
`data/db/reverend-insanity.db` (render + cast_naming experiments) plus an
explicitly synthetic in-memory fixture (dialogue_brief experiment, built in
the script itself — see below for why). New module
`packages/core/src/echotales/core/disclosure.py`
(`TaskSpec`/`DisclosureResult`/`compile_minimal_disclosure`); new tests
`packages/core/tests/test_disclosure.py` (13 cases, all passing); one
behavior-preserving refactor to `state.py` (`_fold_target` extracted from
`compile_generation_state`'s loop body, existing suite unchanged); render
integration `plan_builder.py::compile_render_state_minimal` +
`build_render_plan(..., use_mdc=False)`, opt-in and fully revertable.

This is the first of three planned candidates (Minimal Disclosure Compiler,
Temporal-Epistemic Delta Compiler, Counterexample-Guided Generation) being
evaluated for whether they constitute a genuine algorithmic contribution
worth an IPR review. **This document does not claim patentability** — that
determination happens after a separate prior-art/IPR review, per the
explicit scope of this investigation.

## Pre-registered rules (fixed in the script's docstring before any number was computed)

- **Render targets:** the 15 most-mentioned Selves in `reverend-insanity.db`
  with a `self_persona_binding` row (all of the top 20 have one, checked
  directly before writing the harness).
- **Render positions:** chapters 20, 100, 190 of a 199-chapter volume. 45
  queries total.
- **Four conditions:** FULL (every distinct store fact, no filtering at
  all), TOPK (`world/context.py::_ranked`'s existing cap applied to the
  observer-valid candidate's attributes — the one truncation mechanism
  already shipped here), OBSERVER (`compile_generation_state` unmodified,
  today's production behavior), MDC (`compile_minimal_disclosure` with
  `plan_builder.RENDER_TASK_SPEC`).
- **Metric:** evidence_count = |aliases| + |attributes| + |relationships|
  selected. Evidence-reduction % is measured **against OBSERVER**, not
  FULL — the FULL→OBSERVER gap is the already-measured observer-filtering
  effect from `docs/results/A1_OBSERVER_ABLATION.md`, not this module's
  contribution.
- **Leakage gate:** `EpistemicLeakageValidator` run against each MDC
  selection's own serialized content; a pass/fail gate (0 failures
  required), not a percentage.

## A confound found while building this harness

`reverend-insanity.db` has **zero** SELF-kind attribute rows and **zero**
relation rows (`SELECT count(*) FROM attribute WHERE target_kind='SELF'` →
0; `SELECT count(*) FROM relation` → 0), checked directly before writing a
single line of the harness. `world/schema.py`'s own docstring already
documents this gap for LOCATION/ORGANIZATION/ITEM ("10 locations and 35
organisations with zero facts attached to any of them"); it turns out
SELF-kind extraction against `PERSON_KEYS` (role/faction/status/...) was
never run against this database either. PERSONA-kind attributes exist and
are populated (617 rows across 98 personas: gender/age_band/archetype/
big_five/register on every persona, rarer visual keys on a handful).

Consequence: the render experiment's real-data "evidence" for a SELF target
is aliases only — attributes and relationships are 0 in *every* condition
because there is nothing in the graph to select from, not because MDC did
anything. This is itself a reportable finding, filed to HANDOFF, not a
limitation of the harness.

Because of this, the coverage-plus-dependency-closure mechanism — the part
of MDC that actually needs attributes and relationships to do interesting
work — cannot be exercised on real data at all right now. A second
experiment, `dialogue_brief`, runs against a small, explicitly labeled
**synthetic** in-memory fixture (three Selves, role/faction/status/
personality attributes, two relationships, built in the eval script) to
test that mechanism, per the user's own instruction to use synthetic
adversarial cases where real corpus coverage is missing. A third
experiment, `cast_naming`, runs several real top-mentioned Selves through
one MDC batch call to exercise the one mechanism real data *can* test:
cross-cast alias disambiguation.

## Result — render (real data, 45 queries over 15 targets)

| Condition | Avg. evidence/target |
|---|---:|
| FULL (unfiltered) | 2.20 |
| TOPK (`_ranked` cap) | 1.56 |
| OBSERVER (`compile_generation_state`) | 1.56 |
| **MDC** | **0.00** |

**Evidence reduction vs. OBSERVER: 100.0%.** Leakage gate: **0/45 failures**.

TOPK and OBSERVER are identical here because the only non-zero evidence
category (aliases) is untouched by `_ranked` (that function caps
attributes only, and there are none to cap on this corpus) — a real,
reportable mismatch between what `_ranked` was built for (a text brief) and
what this comparison asked of it, stated plainly rather than smoothed over.

MDC selects **zero** self-level facts for every render query because
`RENDER_TASK_SPEC` was built by reading `panels.py::character_looks`
directly (`panels.py:1369-1373`): it calls only
`gen_state.persona_for(...)` and `gen_state.appearance_for(...)`, never
`TargetState.self_attributes`, relationships, or aliases. An end-to-end
smoke test (a synthetic single-character case, not part of the pre-
registered ablation) confirmed the actual `CharacterRenderSpec` a real
panel would draw from is unchanged under MDC — the dropped evidence was
never something the render prompt read, not evidence dropped by accident.

## Result — dialogue_brief (synthetic fixture)

Task: `required_keys={SELF: {role, faction, status}}`, `require_relationships=True`,
`require_persona=False`. Two Selves queried (`s_hunter`, related to both an
onstage `s_elder` and an offstage `s_rival` who is not in the batch).

| | OBSERVER | MDC |
|---|---:|---:|
| Evidence count | 11 | 7 |
| Reduction vs. OBSERVER | — | **36.4%** |

- `unsatisfied_keys`: none — every required key had a candidate fact.
- **OBSERVER kept the offstage rivalry** (`rel:RIVAL_OF:s_rival`, true —
  `compile_generation_state` includes every SELF relationship
  unconditionally).
- **MDC kept only the onstage relationship** (`rel:DISCIPLE_OF:s_elder`,
  true) — the cross-referenced-cast filter dropping a relationship to an
  entity that is not part of this generation call, which no existing
  mechanism in this codebase does.
- Read-set subset invariant held: `True`. Leakage gate: valid.

This is the one result that demonstrates the coverage-plus-dependency-
closure mechanism doing something a naive top-k-by-priority filter over the
same candidate set could not: `_ranked`-style truncation has no concept of
"is the other end of this relationship even in the room," so it would keep
or drop a relationship based on key priority alone, irrespective of whether
the destination entity is part of the current generation call.

## Result — cast_naming (real data, alias disambiguation)

Five real top-mentioned Selves queried together, naming-only task
(`require_persona=False`, `require_name=True`, no attribute requirement).

| | OBSERVER | MDC |
|---|---:|---:|
| Alias count | 14 | 5 |

Read-set subset invariant held: `True`. This is the real-data analog of
`TestAmbiguousTitleDisambiguation` — with 5 real characters batched
together, `compile_generation_state` keeps every observer-valid alias for
each (up to ~2-3 apiece), while MDC's `_disambiguating_aliases` keeps
exactly one per target unless two targets' primary picks collide, landing
at 5 total (one per target, no collisions in this real sample) versus 14.

## Reading it honestly

- **The render result (100% reduction) is real but structurally hollow on
  this corpus**: it reflects that `compile_generation_state` bundles
  self-attributes and relationships into every `GenerationState`
  unconditionally, and the render prompt reads none of them — a genuine,
  previously undocumented gap this investigation surfaced (see HANDOFF),
  but one where MDC's "selection" work reduces to "everything was 0
  anyway except the one category (aliases) that also gets dropped because
  `require_name=False`." The *mechanism* (task-conditioned exclusion) is
  real; the *magnitude* on this task, on this corpus, is inflated by a data
  gap unrelated to MDC's own design.
- **The dialogue_brief result (36.4% reduction, correct relationship
  retained, incorrect one dropped) is the one that actually exercises
  dependency closure and cross-referenced-cast coverage**, and it only
  exists because real data could not supply the SELF-level facts needed to
  test it. This is exactly the honest-assessment risk flagged in the
  approved plan (render might show a hollow result) materializing, and the
  fairer second task the plan added specifically to hedge against it paying
  off.
- **Where this reduces to "ordinary filtering renamed" and where it does
  not:** the render result alone would not survive that objection — a
  task that needs zero self-level facts and gets zero is not evidence of a
  minimization *algorithm*, just evidence that an unconditional inclusion
  was wasteful. The dialogue_brief result is where the objection is
  actually tested and (on this synthetic case) survives: the
  cross-referenced-cast relationship filter is a real coverage decision
  with no analog in `_ranked`'s priority-and-cap truncation or in
  `compile_generation_state`'s unconditional inclusion, and the "never
  widen beyond `state_of`'s candidate set" subset invariant held in every
  condition tested (asserted in `test_disclosure.py::TestMinimalDisclosureReadSet`
  and re-checked here against real and synthetic data alike).
- **Scale is small.** One real corpus, one synthetic fixture, three Selves
  in the dependency-closure case. This is a first measurement, not a
  validated result across novels or task types.

## Whether this is distinct enough for a patent-agent/IPR review

Not a determination this document makes. What can be said from the
evidence above: the mechanism is not reducible to top-k retrieval or
ordinary RAG chunk-selection (the candidate set itself carries bitemporal
and observer-conditioned structure no flat-corpus retrieval system
represents), and the dependency-closure/cross-referenced-cast coverage
decision is demonstrably different in kind from both `_ranked`'s
static-priority cap and `compile_generation_state`'s unconditional
inclusion — but this was shown on one synthetic fixture, not yet on a
second real corpus or a second, independently-designed task. Worth carrying
into a prior-art review; not yet strong enough to skip one.

## What's next

1. File the SELF-attribute/relation extraction gap on `reverend-insanity.db`
   to `docs/HANDOFF.md` — it blocks re-running this experiment meaningfully
   on real data, and blocks other work (`world/context.py`'s brief is
   presumably just as starved for SELF-level content as this experiment
   found).
2. Proceed to the Temporal-Epistemic Delta Compiler (priority 2), reusing
   the dormant `Store.invalidate_by_facts`/`derived_artifact` primitive per
   the approved plan, rather than the live but render-only
   `GenerationState.digest()` path.
