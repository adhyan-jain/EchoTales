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
