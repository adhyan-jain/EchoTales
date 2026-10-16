# Technical contribution inventory

**Date**: 2026-10-14 · **Branch**: `validation/evidence-pass-2026-09-24` · **HEAD**: `6c7e2c2` ("Reveal-Aware Visual Memory Phases 1 and 2").
**Scope**: a code-grounded inventory of what exists, what production actually calls, and what is missing. It makes **no novelty claim**. An independent literature assessment is a separate step.
**Companions**: [CLAIM_TO_EVIDENCE_MATRIX.md](CLAIM_TO_EVIDENCE_MATRIX.md), [METHODS_PAPER_EXPERIMENT_PLAN.md](METHODS_PAPER_EXPERIMENT_PLAN.md).
**Evidence tags**: **[OBS]** observed by running code or reading the exact lines cited. **[INFER]** inference from [OBS]. **[HIST]** taken from a prior document and not re-verified here.

## 0. Repository state and what was run

- Tree at start: HEAD `6c7e2c2`. Untracked: the LLM-annotation and adjudication artifacts (`data/eval/adjudication/`, `scripts/review/llm_annotate.py`, `docs/research/PRE_ADJUDICATION_*`, `ECHOTALES_*`, etc.). These are **not** part of the system under inventory and were left untouched.
- Added by this task (all untracked, nothing committed or pushed): the three documents named above and `docs/research/technical_contribution_probes/probe_inventory.py`. No existing file was modified. `DECISION_LOG.md` and the StoryTrace firewall were not touched.
- No API, GPU, model, or network use. Shipped databases were opened `mode=ro` for counting only.
- Commands run:

```bash
.venv/bin/python docs/research/formal_narrative_compiler/probes/probe_audit.py      # re-run of prior probes at HEAD
.venv/bin/python docs/research/technical_contribution_probes/probe_inventory.py     # new probes P1..P9
.venv/bin/python -m pytest -o addopts="" packages/core/tests/test_state.py packages/core/tests/test_disclosure.py \
  packages/core/tests/test_visual_memory.py packages/core/tests/test_interval.py packages/core/tests/test_observer_axis.py \
  packages/pipeline/tests/test_scoped_reference.py packages/pipeline/tests/test_plan_builder.py \
  packages/pipeline/tests/test_render_cache_key.py packages/pipeline/tests/test_render_contract.py   # 136 passed in 4.5 s
```

The 136 passing tests show the implementations satisfy their own fixtures. They do not show production use (see section 3). The full 1,277-test suite quoted in `CLAUDE.md` was **not** re-run.

## 1. Which prior conclusions still apply at HEAD

Prior records: [ECHOTALES_NOVELTY_LEDGER.md](ECHOTALES_NOVELTY_LEDGER.md), [formal_narrative_compiler/NOVELTY_DECISION.md](formal_narrative_compiler/NOVELTY_DECISION.md), [reveal_aware_visual_memory/](reveal_aware_visual_memory/), [FINAL_STATISTICAL_CLAIMS_GATE.md](FINAL_STATISTICAL_CLAIMS_GATE.md). Their rejection reasons were re-checked against the current source.

| Prior finding | Status at HEAD | Evidence |
|---|---|---|
| Production render ignores references (`reference_images=[]`) | **Still true** [OBS] | `render/panels.py:2740` |
| Visual selector has no production caller | **Still true** [OBS] | `build_render_plan(...)` at `panels.py:2713-2733` passes no `visual_registry`; the other caller, `webview_server.py:995-1005`, also omits it. The only callers of `visual_registry=` are in `packages/pipeline/tests/test_plan_builder.py:263,277` |
| Prior defect D1: post-cutoff fact leaks into the reader panel | **Still reproduces** [OBS] | `probe_audit.py` A: the ch100-narrated scar appears in the ch5 drawn attributes |
| Prior defect D2: a retracted fact erases past belief on the image path | **Still reproduces** [OBS] | `probe_audit.py` B: `state_of` returns "white" at ch20, the drawn attributes are `{}` |
| Shipped databases contain no distinguishing cases | **Still true** [OBS] | see section 7 |
| Theorems T1-T3 are standard snapshot / bitemporal consequences | Not re-assessed (literature, out of scope) [HIST] | |

## 2. Architecture as built

```
EPUB -> ingest (chapters/blocks) -> spans -> mentions (gazetteer+NER)
      -> resolve/runner.py (retrieve -> evidence -> ScoringModel -> ConformalGate -> link/create/defer)
      -> SQLite store: alias_binding, attribute, self_persona_binding, relation, observation  (all READER-stamped)
           |
           |  persona/split.py, appearance_extract.py, detect_observations.py write facts
           v
      +------------------ per-modality READERS of the store ------------------+
      | IMAGE   panels.render_panels                                           |
      |   compile_render_state -> compile_generation_state -> StateResolver    |
      |     .state_of            (persona ids; observer+knowledge-time aware)  |
      |   appearance_of          (attributes; story-time start only)           |
      |   apply_canon / resolve_appearance / apply_transient_overrides         |
      |   story_context -> LLM director (own filter: learned chapter only)     |
      |   build_render_plan -> state_digest -> compute_render_cache_key        |
      |   engine.generate(reference_images=[])                                 |
      | VOICE   voice/runner.run_voice: whole-novel trait profiles, no position|
      | VIDEO   per-chapter composite of the above; no state input             |
      | NOT CALLED IN PRODUCTION: VisualMemorySelector, emit_scoped_reference, |
      |   compile_minimal_disclosure, EpistemicLeakageValidator,               |
      |   StateResolver.resolve_alias                                          |
      +-----------------------------------------------------------------------+
```

### 2.1 Stage table

Columns follow the requested attributes. "Story pos / reveal pos / observer" describe what the stage actually does. Line ranges are in the current files.

| Stage and code | Input -> output | Story pos / reveal pos | Observer / identity | Provenance and confidence | Cache and invalidation | Production status and tests |
|---|---|---|---|---|---|---|
| Ingest, spans, mentions (`pipeline/ingest`, `spans`, `mentions`) | EPUB -> chapters, spans, mentions | Chapter order only | None | Mention confidence | Not applicable | Active |
| Entity resolution: `resolve/runner.py` (group resolve ~`:430-520`), `retrieve.py:243-303`, `evidence.py:108,380-384`, `gate.py` | Mention group -> link, create, or defer; writes `AliasBinding` | **Implicit reveal order only**: processed in discourse order, so profiles contain only earlier chapters (module docstring `runner.py:1-12`). No explicit position parameter | **None.** Every binding is stamped `OBSERVER_READER` (`runner.py:407`, `title_holders.py:451,516`, `transmigration.py:155`) | Scorer probability, conformal gate, `ResolutionEvent` with `read_set_hash` (`runner.py:_log`) | Event log. No render cache | Active. **`EvidenceContext.temporal_certainty` is never set by any caller, so `temporal_validity` is constant 1.0 in production** [OBS: `grep -rn temporal_certainty` finds only `evidence.py:108,384`] |
| Store (`core/store.py`) | Facts with `interval`, `learned_at_pos`, `observer_id`, `retracted_at`, `truth_status` | Two axes stored: story interval and `learned_at_pos` | `observer_id` column exists; **all shipped rows are READER** (section 7) | Row ids, `source_row_id`, evidence text | None | Active |
| World state: `core/state.py` `StateResolver.state_of` `:207-353`, `_visible_to_observer` `:81-139` | (target, timeline, p, o, k) -> aliases, attributes, relations, persona ids, read set | **p and k are separate parameters** (`position`, `knowledge_pos`); k defaults to the chapter of p on MAIN_TIMELINE (`:233-243`) | Character scope sees only facts it authored or has an `observation` row for (`:105-120`); persona bindings are scope-filtered without the observation door (`:322`) | Fuzzy certainty (CERTAIN/PLAUSIBLE), `ReadSetRecorder` refs | Read set returned | Called from the image path and CLI `query`. Tests: `test_state.py`, `test_observer_axis.py` |
| Alias resolution by observer: `StateResolver.resolve_alias` `:428-456` | (surface, p, o) -> candidate holders | p and k | Does **not** pass `observations`, so a character observer is always empty (probe P4) | Certainty | None | **No production caller** [OBS: only `tests/test_state.py:485-498`] |
| Compiled state: `compile_generation_state` `:751-813`, `_fold_target` `:648-748`, `GenerationState` `:509-634` | cast -> per-target persona and attributes, allowed/forbidden fact sets, read set, digest | Digest excludes p, k and observer **by design** (`:616-634`) | Persona ids via `state_of`; attributes via the persona reader | `provenance_refs`, `read_set` | `digest()` = blake2b over targets + hashed read set | Active for the **image path only** (`panels.py:2085-2093, 2205-2214`; `plan_builder.py:68-95`) |
| Minimal disclosure: `core/disclosure.py:146+`, `plan_builder.py:98-125` | task spec -> subset of `GenerationState` | as above | as above | `dropped_facts` | as above | **Experiment only**: gated by `use_mdc=False` default; used by `scripts/eval/mdc_disclosure_ablation.py` |
| Appearance read: `persona/reference_gen.py:appearance_of` `:164-211` | persona -> {key: value} | **Only `interval.from_lb <= position`** (`:208`) | **None**: ignores `observer_id`, `learned_at_pos`, `truth_status` | None | feeds `persona_reader`, so it enters the digest | Active; the image path's actual attribute source |
| Director brief: `world/context.py:_facts_as_of` `:124-147`, `story_context` `:160-218` | chapter, blocks -> text brief for the LLM director | **Only `learned_at_pos.chapter <= chapter`**; never reads the story interval | **None** (no observer parameter); excludes retracted rows (`is_standing`) | None | Prompt cache key = `chapter:lead:beat_digest:db_fingerprint[:crowd]` (`panels.py:2347-2350`), **no observer**; db fingerprint = file `mtime_ns:size` (`:1695-1703`) | Active (`panels.py:2370`) |
| Canon and text overrides: `apply_canon`, `resolve_appearance`, `apply_transient_overrides` (`panels.py:1398-1406`) | appearance dict -> modified dict | Chapter-keyed canon file; beat text | None | None | Enter the prompt, so enter the cache key via `request.prompt` | Active. **Adds attributes that are not in the graph** |
| Plan and cache: `plan_builder.py:128-252`, `render/contract.py:149-173`, `render/cache_key.py:31-60` | state + prompt + engine params -> `render_cache_key` | `plan_digest` includes chapter, beat id, state digest | no observer field | `RenderArtifact` records seed, persona ids, digests | Key hashes version, state digest, plan digest, prompt, negative prompt, backend, checkpoint, LoRAs, reference **paths**, weight, seed, size, steps, guidance | Active. Reference paths are hashed but `reference_images` is always `[]` |
| Visual memory (Phase 1): `core/visual_memory.py` `VisualAssetRecord :195`, `VisualAssetRegistry :421`, `VisualMemorySelector :470-755` | (self, p, k, o, policy) + registry -> selected asset or prompt-only fallback with reasons | **p and k separate** in `VisualRequest` (`:379`) | Persona via `state_of(p, k, o)`; per-fact observation check for character observers (`:560-587`) | `FactProvenance` snapshots; transitive closure over `parent_asset_ids` (`:328-360`) | `compute_asset_input_digest :758` is defined but has no caller in `src` [OBS] | **Not called by production.** 10 tests in `test_visual_memory.py` |
| Scoped emission (Phase 2): `persona/scoped_reference.py:emit_scoped_reference :74-420` | (self, p, k, o) -> prompt, optional PNG, JSON manifest, registry entry | p and k separate; `resolve_admissible_attributes` | Observer scope via `state_of` | Manifest with `source_facts`, `parent_asset_ids` | `asset_id` = novel, self, persona, `p`, `k.chapter`, 8 hex of prompt digest (no observer, policy, seed) | **Not called by production** (only lazy re-export `reference_gen.py:804-810`; `tests/test_scoped_reference.py`) |
| Leak check: `core/readset.py:EpistemicLeakageValidator :143-170` | (state, text) -> substring check against `forbidden_facts` | none | none | none | none | **No production caller.** Tests only |
| Voice: `voice/runner.py:198-207` | whole-novel trait profiles -> casting + synthesis | **None** (the code states this explicitly) | None | None | None | Active. Position- and observer-blind by design |

## 3. Does production enforce one narrative-state policy across modalities?

**No. [OBS]** There are separate, partial implementations. Within the image path alone, three readers apply three different filters:

| Reader | story-time containment | knowledge time (k) | observer | retraction |
|---|---|---|---|---|
| `StateResolver.state_of` | fuzzy interval | `learned_at_pos <= k` | scoped + observations | positional (belief kept until retraction) |
| `appearance_of` (draws the attributes) | `from_lb <= p` only | none | none | drops any retracted row at every position |
| `_facts_as_of` (director brief) | none | `learned chapter <= chapter` | none | drops any retracted row at every position |

Observed consequences (probe keys refer to `probe_inventory.py`):

- **P1.** A character observer draws nobody: `compile_render_state(observer_id="WU")` returns `persona_bindings=()` even when WU holds an observation of the persona's attribute. Persona bindings are READER-stamped and `state_of` filters them by scope without the observation door (`state.py:322`). So `render --observer <character>` produces no character panels from the shipped data model. [OBS on a synthetic store; the claim about shipped bindings follows from section 7: 0 non-READER bindings.]
- **P2.** An attribute stamped with a character's observer id (private knowledge) reaches the READER panel, because `appearance_of` ignores `observer_id`. Latent only: no shipped row has a non-READER observer.
- **P3 / D1 / D2.** The brief and the drawn attributes drop retracted rows at every position, so a past belief disappears. The prior D1 leak (retrospective reveal) reproduces on the drawn attributes.
- **Voice and video** receive no state at all.
- The `GenerationState` "single compile" guarantee therefore covers: persona id, the persona attributes returned by `appearance_of`, and the digest. It does not cover the director's brief, canon injection, transient overrides, or any non-image modality.

## 4. Candidate mechanisms

### Candidate A: shared narrative-state compilation

- **Implemented**: `compile_generation_state` produces one immutable object per cast and position; the image prompt, plan and cache key read from it (`panels.py:2085-2125`, `plan_builder.py:186-252`). Its docstring cites a real mismatch it removed (prompt used the in-chapter position, key used the chapter start).
- **Not implemented**: a compiler. The "compile" is a fold of `state_of` results (`_fold_target`), with no per-modality target representation, no lowering step, and no verifier. Text brief, voice, video and visual-reference selection are outside it. The disclosure minimiser (`compile_minimal_disclosure`) is off in production.
- **What it demonstrably provides**: drawn persona and cache key agree by construction for the image path. That is an engineering consistency fix, not a policy-enforcement mechanism.
- **Verdict**: **integration of existing queries and prompt-building helpers** [INFER from the stage table]. The semantics are not enforceable across modalities because the other readers do not use it.

### Candidate B: separate story-time and reveal-time enforcement

- **Implemented in the query**: `state_of(position=p, knowledge_pos=k)` (`state.py:207-353`). Probe P8 (selector) and the prior D1 probe show p and k behave independently there.
- **Fact sources**: aliases, attributes, relations and persona bindings all carry both axes in the store. [OBS]
- **Not end-to-end**: the active consumers that draw attributes and write the director brief use p-only (`appearance_of`) or k-only (`_facts_as_of`) filters. The production default sets k from p (`panels.py:2085` passes no `knowledge_pos`, so k = chapter of p), meaning **production never exercises p != k**. The only p != k path is the unused selector (`plan_builder.py:206`: `discourse_cutoff or DiscoursePosition(chapter=int(at))`).
- **Verdict**: **partial**. Represented in the core query and in unused code. Not enforced in the consumers that matter. Two-axis temporal queries are standard bitemporal practice; whether the combination is distinctive is a literature question.

### Candidate C: provenance-closed derived artifacts

What the selector does (`visual_memory.py:484-629`), checked by tests and probes:

| Property | Result |
|---|---|
| Source-fact identity | `FactProvenance.fact_ref` strings from `observable_ref` (`readset.py:58`) |
| Transitive dependencies | Closure over `parent_asset_ids` (`:328-360`). Probe P7: a missing parent is rejected (`transitive_lineage_violation`); a 2-cycle terminates and is admitted; reached by `visited` sets |
| Retractions | Checked against **registration-time snapshots** only (`:603`). **P6**: after a store-side retraction at ch20, `state_of(p=7,k=30)` returns `{}` but the selector still returns `selected` |
| Observer restrictions | Asset scope check plus per-fact observation check for character observers (`:527-587`) |
| Policy changes | Policy is an input to `select`; not stored for revalidation |
| p vs k | **P8**: p=5, k=10 -> `fallback_prompt_only (cutoff_exceeded)`; k=100 -> `selected` |
| Cache identity | `asset_id` omits observer, policy and seed; `compute_asset_input_digest` is unused; the render cache hashes reference **paths** and receives `[]` |

Defects found:

- **P5**: `VisualAssetRegistry.register` rebuilds the record by hand when the transitive cutoff has to rise (`:431-451`) and drops `story_pos`, `discourse_cutoff`, `observer_id`, `policy`, `prompt`, `manifest_path` (reset to defaults). Observed: a record emitted for observer `WU` / `retrospective` comes out of the registry as `READER` / `in_sequence`. Not a selection leak today because `observer_scope` is copied, but registry state diverges from the manifest on disk.
- **Lineage is declarative.** `emit_scoped_reference` takes `parent_asset_ids` from the caller and builds the prompt only from facts; no code conditions an image on a parent image (`engine.generate` receives no references). So transitive closure is checked over metadata that nothing in the codebase currently produces from real derivation.
- **Selector-level versus pixel-level**: all guarantees are over prompt/metadata provenance. Nothing measures whether a generated image exposes a withheld fact, and production does not feed references to the backend (EVOLUTION 4.47 reasons it removed IP-Adapter conditioning).

**Verdict**: **partial / optional**. A correct snapshot-based DAG filter exists with tests; it is not wired to production, ignores live-store changes, and has no real derived artifacts to protect.

### Candidate D: observer- and time-scoped identity resolution

- **What resolution actually does**: BM25 + context cosine retrieval (`retrieve.py:243-303`) -> evidence vector -> 5-feature log-linear scorer -> conformal gate. Sequential processing gives implicit reveal-time scoping. There is **no observer input** anywhere in resolution, and `temporal_validity` is constant (section 2.1).
- **The observer/time-scoped alias mechanism that exists** is `StateResolver.resolve_alias` (`state.py:428-456`): a candidate filter. It has no production caller, and for character observers it returns empty even when an observation exists (**P4**: `state_of(...).aliases` contains the alias, `resolve_alias` returns `[]`).
- **Measurable benefit over baseline**: none is measured. The ledger records silver-label-only in-domain numbers and zero human-confirmed labels [HIST].
- **Verdict**: **unimplemented as a decision mechanism**. What exists is rule-based/feature-based linking plus an unused filter. Nothing here is a distinct decision rule with a measured advantage.

### Candidate E: end-to-end multimodal consistency

- Verified call paths: image only. Voice and video take no compiled state (`voice/runner.py:198-207`). The text-to-director path uses a different reader. `render --observer` is the only observer entry point (`cli.py:389`, `commands.py:1104-1146`); there is no observer flag for voice or video.
- A shared SQLite store is the only thing the modalities share. That is not a consistency guarantee, and the code says so for voice.
- **Verdict**: **unimplemented**.

## 5. Previously rejected directions revisited

| Direction | Why it was rejected | Does the current code support a narrower surviving mechanism? |
|---|---|---|
| Standalone formal compiler (N3) | Theorems are standard snapshot/bitemporal results; production violates them | No. The compile is a fold of `state_of`; the formal properties are checked on `state_of` and not on the consumers that diverge from it. Still rejected as a standalone contribution |
| Visual-reference selector (N4) | Prior art overlap; no distinguishing real cases; not in production | No new support: still unused, snapshot-only retraction (P6), registry field loss (P5), declarative lineage. Remains rejected as a paper; retained as a possible product fix |
| Generic cache invalidation (N7) | Covered by dependency-tracking literature | `GenerationState.digest` is a hashed read set over consulted facts; the render key also hashes the whole prompt, so the digest is partly redundant. Nothing precise beyond N7. Still rejected |
| Generic provenance / IFC | Standard IFC over a DAG | The selector is a label check over a DAG of `FactProvenance`. Same conclusion |
| Broad knowledge-graph integration | Not a methods contribution | Unchanged |

## 6. Verified defects and bypasses (for engineering, not claims)

1. `appearance_of` and `_facts_as_of` bypass the observer and knowledge-time axes of `state_of` (P1-P3, D1, D2).
2. `render --observer <char>` draws no characters on a READER-stamped store (P1).
3. `resolve_alias` ignores observations (P4); no caller.
4. `EvidenceContext.temporal_certainty` is never populated, so the scorer's temporal feature is constant.
5. `VisualAssetRegistry.register` loses six fields (P5).
6. Selector retraction is snapshot-based (P6).
7. `EpistemicLeakageValidator`, `compile_minimal_disclosure`, `emit_scoped_reference`, `VisualMemorySelector` have no production caller.
8. `GenerationState.persona_facts` (`state.py:716-720`) is read by neither observer nor knowledge-time filters; it only feeds the digest, so the effect is over-invalidation.
9. `webview_server.py:995-1005` builds a plan with no observer, no `gen_state` and no in-chapter position, so its digest can differ from the render's.
10. The director prompt-cache key has no observer. Whether the cached prompt contains observer-dependent clauses was **not** verified, so this is a risk and not a demonstrated bug.
11. `apply_canon` and `apply_transient_overrides` inject attributes from outside the graph into every panel prompt.

## 7. What the shipped data can and cannot test

Read-only counts (`mode=ro`):

| Database | attributes | retracted attrs | non-READER attrs/aliases/bindings | relations | observations (observers) |
|---|---|---|---|---|---|
| reverend-insanity (199 ch) | 617 | 0 | 0 | 0 | 12 (11) |
| lord-of-the-mysteries (40 ch) | 558 | 0 | 0 | 0 | 0 |
| omniscient-readers-viewpoint (40 ch) | 0 | 0 | 0 | 0 | 0 |

No retractions, no character-stamped facts, no relations, and an attribute-level proxy for `p != k` ("learned chapter later than story start") finds none. Any experiment on the distinguishing cases therefore needs constructed data. This matches [ECHOTALES_NOVELTY_LEDGER.md](ECHOTALES_NOVELTY_LEDGER.md).

## 8. Bottom line

- Genuinely present: a bitemporal fact store with two temporal axes and an observer axis (`state_of`), an image-path state compile that keeps prompt and cache key in agreement, and an unused snapshot-based provenance selector with a test suite.
- **Not established**: a distinct technical contribution. The mechanisms that would make one (single policy enforced in all consumers; derived-asset closure over real derivations; observer-aware identity decisions) are either unimplemented or unwired.
- The only integration-level question that code can answer cheaply is whether enforcing one admissibility policy at every consumer removes the leaks in section 3. That is an engineering result unless the experiment plan shows something beyond integration.
