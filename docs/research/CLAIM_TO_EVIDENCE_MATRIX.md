# Claim-to-evidence matrix

**Date**: 2026-10-14 · **HEAD**: `6c7e2c2` · Companion to [TECHNICAL_CONTRIBUTION_INVENTORY.md](TECHNICAL_CONTRIBUTION_INVENTORY.md). Probe keys P1-P9 are in `docs/research/technical_contribution_probes/probe_inventory.py`; D1/D2 are in `formal_narrative_compiler/probes/probe_audit.py`.

No row below is labelled novel, first, state of the art, or publication-ready. A passing unit test shows an implementation satisfies a fixture. It does not show novelty, nor that a generated artifact obeys the tested input constraint.

**Status legend**: *verified* (works as claimed and is exercised by production), *partial* (works in part of the system), *optional* (implemented and tested, not called by production), *broken* (a defect observed), *unimplemented*.

## Summary

| ID | Proposed mechanism | Status |
|---|---|---|
| C1 | One compiled state shared by every consumer of a modality | **partial** (image path only) |
| C2 | `state_of` separates story time (p) from reveal time (k) | **verified** in the core query; **partial** in consumers |
| C3 | p/k separation enforced in production consumers | **broken** (D1, D2, P1-P3) |
| C4 | Provenance-closed derived visual artifacts (selector) | **optional**, with defects P5, P6 |
| C5 | Observer- and time-scoped identity resolution decision | **unimplemented** as a decision mechanism |
| C6 | End-to-end multimodal consistency | **unimplemented** |
| C7 | Cache identity from the consulted-fact read set | **verified** (image path), **partial** value |
| C8 | Label-based leak check of generated inputs | **optional** (no production caller) |
| C9 | Positional retraction: belief persists until the retraction position | **verified** in `state_of`; **broken** on the image path |

---

### C1. Shared narrative-state compilation

| Field | Content |
|---|---|
| Proposed mechanism | One immutable `GenerationState` per cast and position, from which prompt, plan and cache key are all read |
| Problem addressed | Prompt built at the in-chapter position while the plan/cache key used the chapter start, so a mid-chapter body change was in the prompt but not in the key (`state.py:509-526` docstring) |
| Existing implementation | `core/state.py:compile_generation_state :751-813`, `_fold_target :648-748`, `GenerationState :509-634`; `render/plan_builder.py:compile_render_state :68-95` |
| Active call path | Yes, image path only: `render/panels.py:2085-2093` (beat), `:2205-2214` (carry-forward refresh), `:2713-2733` (plan). Not used by the director brief (`panels.py:2370` -> `world/context.py`), voice (`voice/runner.py:198-207`), or video |
| Formal or executable property | Digest changes iff a consulted fact changes; allowed/forbidden sets partition the entity's facts. Checkable by differential tests |
| Existing baseline | The pre-fix path (separate `state_of` calls at different positions), and the flat `appearance_of` read |
| Known counterexamples | Persona attributes come from `appearance_of`, which applies a weaker filter than `state_of` (D1, P2). `canon` and transient overrides add attributes after the compile (`panels.py:1398-1406`). `persona_facts` is not observer/knowledge filtered (`state.py:716-720`) |
| Distinguishing evidence | None yet. It would require showing a class of inconsistency that independent per-modality calls to the same `state_of` cannot avoid |
| Missing work | Route the brief, attribute reads, canon and any text/audio consumer through the compiled object; add a checker that fails if a consumer reads the store directly |
| Status | **partial** |

### C2. Story-time and reveal-time separation in the query

| Field | Content |
|---|---|
| Proposed mechanism | `state_of(position=p, knowledge_pos=k, observer_id=o)`: story-interval containment at p, `learned_at_pos <= k`, observer scope, positional retraction |
| Problem addressed | A fact true at p but narrated after k (a scar acquired in ch3, revealed in ch100) leaking into an early panel; or a fact known to the reader being attributed to a character |
| Existing implementation | `core/state.py:207-353`, `_visible_to_observer :81-139`, `_temporal_certainty :142-152` |
| Active call path | Yes for persona ids (`compile_generation_state` calls `resolver.state_of`) and CLI `query` (`commands.py:305-327`). Production never passes `knowledge_pos`, so k is derived from p (`state.py:233-243`) and **p != k is not exercised by any production caller** |
| Formal or executable property | R3 cutoff independence: adding facts learned after k does not change the result at k. Tested in `core/tests/test_state.py`, `test_visual_memory.py` (hypothesis) |
| Existing baseline | `appearance_of` (p-only) and `_facts_as_of` (k-only) |
| Known counterexamples | None found inside `state_of` by the probes. The counterexamples are the baselines themselves (D1) |
| Distinguishing evidence | Needed: constructed stores where p-only and k-only baselines each fail and the two-axis query does not (plan section 2). Real data cannot supply them (0 retractions, 0 non-READER rows) |
| Missing work | A real or constructed corpus with p != k, retractions and observers; evaluation against the baselines |
| Status | **verified** (query), **partial** (use) |

### C3. The same policy enforced in the production consumers

| Field | Content |
|---|---|
| Proposed mechanism | Every consumer applies the C2 policy (p, k, o, retraction), not a private filter |
| Problem addressed | Spoilers and viewpoint errors in image prompts and director briefs |
| Existing implementation | Not implemented as a single mechanism; three filters coexist (inventory section 3) |
| Active call path | `appearance_of` (`reference_gen.py:164-211`), `_facts_as_of` (`world/context.py:124-147`) are the active readers |
| Formal or executable property | For every emitted artifact, its source facts must be in `state_of(p,k,o)` admissible set |
| Existing baseline | This **is** the current production path |
| Known counterexamples | **D1** (post-cutoff fact in the drawn attributes), **D2** (retracted belief erased), **P1** (character observer draws nobody), **P2** (character-private attribute reaches the reader panel), **P3** (brief drops retracted belief) |
| Distinguishing evidence | A before/after leak count on an oracle-labelled adversarial suite, with each removed mechanism re-introducing its own failures (plan sections 2-4) |
| Missing work | Replace the two readers with `state_of`-backed ones; decide the intended semantics for retraction on the image path; add an artifact-level admissibility check |
| Status | **broken** (observed leaks on constructed stores) |

### C4. Provenance-closed derived visual artifacts

| Field | Content |
|---|---|
| Proposed mechanism | A derived asset is admissible for (p, k, o, policy) only if its own facts and all transitive parent assets' facts are admissible; otherwise a prompt-only fallback with a reason |
| Problem addressed | A reference sheet or image conditioned on a parent that embodies a fact the reader has not yet been told |
| Existing implementation | `core/visual_memory.py:VisualMemorySelector :470-755`, `VisualAssetRecord.transitive_facts :328-343`, `VisualAssetRegistry :421-467`; `persona/scoped_reference.py:emit_scoped_reference :74-420` |
| Active call path | **None.** `build_render_plan(visual_registry=...)` exists (`plan_builder.py:171,205-221`) but `panels.py:2713-2733` never passes it and the backend gets `reference_images=[]` (`panels.py:2740`) |
| Formal or executable property | R1-R6 in `core/tests/test_visual_memory.py` (10 tests), `tests/test_scoped_reference.py`, `tests/test_plan_builder.py:206+`: cutoff independence, lineage inheritance, fallback reasons |
| Existing baseline | `reference_path_for` (`reference_gen.py:788-801`): flat read of a stored path, no cutoff or observer. This is the real legacy path |
| Known counterexamples | **P6**: a retraction written to the store after registration is not seen (selector reads `FactProvenance` snapshots; `state_of` live returns `{}` while the selector returns `selected`). **P5**: `register()` drops `story_pos`, `discourse_cutoff`, `observer_id`, `policy`, `prompt`, `manifest_path`. Lineage is declared by the caller; no code derives an image from a parent image. `asset_id` omits observer, policy, seed. Missing parent: rejected (P7). Cycle: terminates, admitted (P7). Policy change: not stored for re-evaluation |
| Distinguishing evidence | Needed: derived artifacts that really inherit from parents (image-to-image, or text-derived voice descriptions), a case where a naive "filter each asset by its own facts" baseline fails and the closure succeeds, and a pixel-level check that a withheld fact is not visible |
| Missing work | Live-store revalidation or snapshot invalidation on store writes; fix `register`; real derivation producers; pixel-level or description-level audit; production wiring |
| Status | **optional** (with defects P5, P6) |

### C5. Observer- and time-scoped identity resolution

| Field | Content |
|---|---|
| Proposed mechanism | A mention is resolvable to an entity only if the alias binding is valid at the narrative position and known to the observer, using aliases, titles, relations and uncertainty |
| Problem addressed | Linking "the clan head" or a disguise name to the wrong entity, or to the true identity for an observer who has not learned it |
| Existing implementation | Linking: `resolve/runner.py`, `retrieve.py:243-303`, `evidence.py`, `score.py`, `gate.py`. Observer-scoped candidate filter: `StateResolver.resolve_alias state.py:428-456` |
| Active call path | Linking: yes, all bindings READER-stamped (`runner.py:407`). `resolve_alias`: none. `EvidenceContext.temporal_certainty` is never set, so `temporal_validity` is constant 1.0 (`evidence.py:108,380-384`) |
| Formal or executable property | None stated for the decision rule. `test_state.py:485-498` tests the filter on fixtures |
| Existing baseline | The existing scorer + gate pipeline (this is the production path); silver labels only, zero human-confirmed labels (ledger N1) |
| Known counterexamples | **P4**: with an explicit observation, `state_of(...).aliases` contains the alias and `resolve_alias` returns `[]` |
| Distinguishing evidence | A decision rule that uses (p, k, o) information absent from the baseline features, and a measured error difference on adjudicated data against that baseline |
| Missing work | Define and implement the rule; populate `temporal_certainty`; pass observations in `resolve_alias`; human-adjudicated gold including reveal cases |
| Status | **unimplemented** as a decision mechanism |

### C6. End-to-end multimodal consistency

| Field | Content |
|---|---|
| Proposed mechanism | One admissible state flows into text, image and audio instead of each stage rebuilding context |
| Problem addressed | A panel, a narration and a voice describing different versions of a character at a given reader position |
| Existing implementation | Image path only. Voice is position- and observer-blind by design (`voice/runner.py:198-207`: "a first attempt did exactly that [compiled one per chapter] and changed no output") |
| Active call path | Image: yes. Text brief: separate reader. Voice, video: no state |
| Formal or executable property | Cross-modal: every emitted artifact's facts subset of one shared admissible set |
| Existing baseline | The independent per-stage reads currently in production |
| Known counterexamples | Section 3 table: three readers, three filters, within one modality |
| Distinguishing evidence | Needs a second modality that actually consumes position/observer-dependent state (voice casting is a whole-novel property today) |
| Missing work | A modality beyond image that depends on (p, k, o); a shared representation; an end-to-end checker |
| Status | **unimplemented** |

### C7. Cache identity from the consulted-fact read set

| Field | Content |
|---|---|
| Proposed mechanism | The cache key includes a digest over exactly the facts the compile consumed, so changes to unconsulted facts do not invalidate |
| Problem addressed | Stale reuse after an attire change (23 stale reuses, A7 re-run) and needless re-render when only the observer changed (30 panels) (`state.py:616-634` docstring) |
| Existing implementation | `GenerationState.digest`, `core/readset.py` (`hash_read_set`, `ReadSetRecorder`), `render/cache_key.py:31-60`, `render/contract.py:149-173` |
| Active call path | Yes: `panels.py:2751` |
| Formal or executable property | Completeness (a consulted-fact change changes the key) and minimality (an unconsulted change does not). Tests in `test_render_cache_key.py`, `test_render_contract.py` |
| Existing baseline | Path-existence caching (`if image_path.exists(): skip`), replaced by this key |
| Known counterexamples | The key also hashes the full prompt, so the state digest is partly redundant. Reference **paths** are hashed but references are always `[]`. `persona_facts` is not observer-filtered (over-invalidates). Read-set invalidation under insertion is unsound per the ledger N7 [HIST] |
| Distinguishing evidence | The ledger already records this direction as rejected on novelty (dependency-tracking literature). Nothing here narrows it |
| Missing work | None for a methods claim; it is product infrastructure |
| Status | **verified** (as infrastructure) |

### C8. Label-based leak check

| Field | Content |
|---|---|
| Proposed mechanism | Check generated prompt text against the `forbidden_facts` set of the compiled state |
| Problem addressed | A withheld name or attribute value appearing in text handed to a generator |
| Existing implementation | `core/readset.py:EpistemicLeakageValidator :143-170`; `forbidden_facts` built in `_fold_target :732-740` |
| Active call path | **None** in `src`, `scripts` or `research` (only tests) |
| Formal or executable property | No forbidden string (length >= 3, case-folded) occurs as a substring of the checked text |
| Existing baseline | No check at all in production |
| Known counterexamples | Substring matching misses paraphrase and pronoun-only reference; it also flags an admissible prompt when a hidden attribute shares a value with an allowed one. **Observed** (ad hoc check, same store API as the probes): `hair_color=black` learned ch1, `eye_color=black` learned ch100, request p=5 gives `allowed=('attr:hair_color=black',)`, `forbidden=('black','eye_color: black')`, and `validate(state, "a man with black hair").is_valid` is `False` |
| Distinguishing evidence | A labelled leak set where the check catches leaks that the filter-only path misses, and false-positive rate on admissible text |
| Missing work | Wire it to the director and attribute output; measure precision/recall against a paraphrase-aware oracle |
| Status | **optional** |

### C9. Positional retraction (retraction is not interval end)

| Field | Content |
|---|---|
| Proposed mechanism | A retracted fact stays visible to an observer at positions before the retraction, and not after |
| Problem addressed | Erasing what the reader believed (a "white hair" that was a wig until ch50) |
| Existing implementation | `_visible_to_observer :129-135` (`knowledge_pos < retracted_at`) |
| Active call path | `state_of` is called, but the drawn attributes and the brief use `is_standing`, which drops any retracted row at every position (`models.py:305-307`) |
| Formal or executable property | For k < retracted_at the fact is returned; for k >= retracted_at it is not |
| Existing baseline | `is_standing`-based filters (production) |
| Known counterexamples | **D2** (`probe_audit.py` B) and **P3**: `state_of` returns it at ch20, the drawn attributes and brief do not. Production writes no attribute retractions at all (the only retraction writer is `contradiction.py:301`, for aliases) and the shipped databases contain none |
| Distinguishing evidence | Needs real or constructed retractions, plus a decision on which view (belief at k, or truth) each modality is meant to render |
| Missing work | A modality-level policy statement; routing the image path through `state_of` semantics |
| Status | **verified** in `state_of`; **broken** on the image path |

---

## Cross-reference: previously rejected directions

| Direction | Rows above that touch it | Standing |
|---|---|---|
| Standalone formal compiler | C1, C2, C9 | Still rejected: the properties hold for `state_of`, not for the consumers (C3) |
| Visual-reference selector | C4 | Still rejected as a paper: optional, defects P5/P6, no real derivations |
| Generic cache invalidation | C7 | Still rejected |
| Generic provenance / IFC | C4, C8 | Still rejected |
