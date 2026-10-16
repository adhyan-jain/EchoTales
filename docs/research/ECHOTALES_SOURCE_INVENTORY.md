# Source inventory for the EchoTales research audit

Everything consulted to produce [`ECHOTALES_RESEARCH_HISTORY.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_RESEARCH_HISTORY.md),
[`ECHOTALES_NOVELTY_LEDGER.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_NOVELTY_LEDGER.md),
[`ECHOTALES_NEXT_RESEARCH_DECISION.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_NEXT_RESEARCH_DECISION.md), and
[`ECHOTALES_EXECUTIVE_SUMMARY.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_EXECUTIVE_SUMMARY.md).

---

## 1. Repository State

| Item | Value | Verification Basis |
|---|---|---|
| **Repository** | `adhyan-jain/EchoTales` | [INSPECT] git remote |
| **Audited Branch** | `validation/evidence-pass-2026-09-24` | [INSPECT] git branch |
| **Audited HEAD** | `6c7e2c2` (*feat(research): implement Reveal-Aware Visual Memory Phases 1 and 2*) | [INSPECT] git log -1 |
| **Base / Master Branch** | `master` @ `6aed9f9` (2026-09-12); 134 commits behind audited branch | [INSPECT] git merge-base |
| **Working Tree** | Clean; all Phase 1 and Phase 2 implementations and tests committed and pushed | [INSPECT] git status |

### Key Commits Carrying Research Decisions
- `6c7e2c2` (2026-10-13): Implementation of Reveal-Aware Visual Memory Phase 1 & 2 (`visual_memory.py`, `scoped_reference.py`, 26 tests, `source_row_id`, `resolve_admissible_attributes`).
- `c90fa40` (2026-10-13): Doc sync, removal of superseded planning docs, update of `CLAUDE.md`, `HANDOFF.md`, and `EVOLUTION.md`.
- `a2a2fe8` (2026-10-13): Formal narrative compiler audit, related work, formal model, properties, and NARROW novelty decision.
- `40102a2` (2026-10-03): Second research experiment round recording.
- `1454e65` (2026-10-03): Research arena aggregate tool, listener model, and visual-beats dataset for the second round.
- `cc1eaa4` (2026-10-02): First round of research arena experiments (H-CAL, H-GATE, H-COST, H-HEDGE, H-SELECT).
- `091c545` (2026-10-02): Research arena package introduction (`packages/research/`).
- `79e28b6` (2026-10-02): Research program documentation, adoption of the "StoryTrace firewall".
- `4651fd5`, `a238198`, `7284221`, `bad0588` (2026-09-29–30): E-CRDT standalone prototype and invention discovery pass.
- `22fa812` (2026-09-29): Minimal Disclosure Compiler (MDC) implementation and ablation.
- `00bcdb1`, `d2cd522` (2026-09-26–27): Evidence-upgrade pass (A1, A2, A7, LitBank).
- `dd7f82e` (2026-09-26): Paper contribution matrix, related work, claim boundaries, and venue analysis.

---

## 2. Repository Documents Inspected

### Architecture & System Documentation
- [`CLAUDE.md`](file:///home/adhyan/Desktop/EchoTales/CLAUDE.md): Project orientation, command reference, test discipline, active research boundaries.
- [`README.md`](file:///home/adhyan/Desktop/EchoTales/README.md): System overview, core dependencies, package structure.
- [`docs/design/architecture.md`](file:///home/adhyan/Desktop/EchoTales/docs/design/architecture.md), [`docs/design/plans.md`](file:///home/adhyan/Desktop/EchoTales/docs/design/plans.md): Multi-stage compilation pipeline, domain entities.
- [`docs/HANDOFF.md`](file:///home/adhyan/Desktop/EchoTales/docs/HANDOFF.md): Engineering handoff log (2026-09-26 through 2026-10-02).
- [`docs/EVOLUTION.md`](file:///home/adhyan/Desktop/EchoTales/docs/EVOLUTION.md): Architectural decision history; Section 4.47 (disconnection of IP-Adapter reference conditioning due to colour and composition contamination).
- [`docs/status/STATUS.md`](file:///home/adhyan/Desktop/EchoTales/docs/status/STATUS.md): Operational status of pipeline modules.

### Research Logs & Audits
- [`docs/research/README.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/README.md): Research scope, StoryTrace firewall policy.
- [`docs/research/DECISION_LOG.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/DECISION_LOG.md): Formal log of all hypothesis decisions across the arena and compiler tracks.
- [`docs/research/EXPERIMENT_STATUS.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/EXPERIMENT_STATUS.md): Real-time tracking of arena experiments.
- [`docs/research/CONVERGENCE.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/CONVERGENCE.md): Parts 1–4; convergence thesis analysis and killing of the disagreement-action-manifestation hypothesis.
- [`docs/research/ENGINEERING_NOTES.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ENGINEERING_NOTES.md): Observations on model behavior, cache performance, and runtime profiling.
- [`docs/research/formal_narrative_compiler/`](file:///home/adhyan/Desktop/EchoTales/docs/research/formal_narrative_compiler/):
  - `NOVELTY_DECISION.md`: NARROW / trending NO-GO decision for standalone formal compiler paper.
  - `RELATED_WORK.md`: Assessment against NWM, Graphiti, Adapton, Jensen et al., Dyreson-Snodgrass, FIDES/APPA.
  - `REPOSITORY_AUDIT.md`: Identification of defects D1–D8 in production state/context resolution.
  - `FORMAL_MODEL.md`: Bitemporal narrative model $(T, \le_T)$, $(D, \le_D)$, $\Omega$, $\mathcal{E}$, $\mathcal{F}$.
  - `CORRECTNESS_PROPERTIES.md`: Theorems T1–T3 and properties P4–P5.
  - `CONTRIBUTION_LEDGER.md`: Disaggregation of compiler claims C-A, C-B into Level A/B/C/D.
  - `IMPLEMENTATION_PLAN.md`: Stages 0–4 for compiler verification.
- [`docs/research/reveal_aware_visual_memory/`](file:///home/adhyan/Desktop/EchoTales/docs/research/reveal_aware_visual_memory/):
  - `PHASE1_IMPLEMENTATION.md`: Audit of active visual reference paths, minimal typed schema, R1–R6 selection rules.
  - `PHASE2_IMPLEMENTATION.md`: Cutoff-scoped asset emission, fact identity (`source_row_id` vs `fact_ref`), JSON provenance manifest.

### Paper Readiness & Evaluation Documents
- [`docs/paper/PUBLICATION_READINESS.md`](file:///home/adhyan/Desktop/EchoTales/docs/paper/PUBLICATION_READINESS.md): Status of the WNU 2027 / ACL 2027 Demo systems submission; identification of the 200-mention human confirmation sample as the sole blocker.
- [`docs/paper/CONTRIBUTION_MATRIX.md`](file:///home/adhyan/Desktop/EchoTales/docs/paper/CONTRIBUTION_MATRIX.md): Classes A–F evaluation matrix.
- [`docs/paper/PAPER_CLAIM_BOUNDARIES.md`](file:///home/adhyan/Desktop/EchoTales/docs/paper/PAPER_CLAIM_BOUNDARIES.md): Strict boundary conditions preventing unsubstantiated claims.
- [`docs/paper/VENUE_ANALYSIS.md`](file:///home/adhyan/Desktop/EchoTales/docs/paper/VENUE_ANALYSIS.md): Target venue selection (WNU workshop vs ACL System Demonstrations).
- [`docs/paper/RELATED_WORK_FINAL.md`](file:///home/adhyan/Desktop/EchoTales/docs/paper/RELATED_WORK_FINAL.md): Prior art survey for the core narrative KG systems paper.
- [`docs/results/HUMAN_REVIEW_PROTOCOL.md`](file:///home/adhyan/Desktop/EchoTales/docs/results/HUMAN_REVIEW_PROTOCOL.md): Protocol for verifying 200 stratified evaluation mentions and 88 hard cases.
- [`docs/results/`](file:///home/adhyan/Desktop/EchoTales/docs/results/):
  - `A1_OBSERVER_ABLATION.md`, `A2_OBSERVER_ABLATION.md`: Verification of epistemic leakage when observer scoping collapses.
  - `A7_CACHE_ABLATION.md`: Detection of stale panel reuse under attire changes.
  - `EXTERNAL_BENCHMARK.md`: LitBank evaluation results.
  - `MDC_DISCLOSURE_ABLATION.md`: Evaluation of Minimal Disclosure Compiler.
  - `SCORER_DIAGNOSIS.md`: Diagnostic run for StoryTrace bounded investigator.

---

## 3. Code Inspected

| Path | Lines / Symbols Inspected | Finding |
|---|---|---|
| [`packages/core/src/echotales/core/visual_memory.py`](file:///home/adhyan/Desktop/EchoTales/packages/core/src/echotales/core/visual_memory.py) | L1–772 (`VisualAssetRecord`, `FactProvenance`, `VisualMemorySelector`, `validate_asset_lineage`, `compute_effective_cutoff`) | Provenance-scoped selector; enforces embodiment (R2), cutoff (R1), observer (R4), retraction (R3), recursive parent lineage (R5), deterministic tie-breaking. Cycle-safe with `visited` set. Content-addressed hashing. |
| [`packages/pipeline/src/echotales/pipeline/persona/scoped_reference.py`](file:///home/adhyan/Desktop/EchoTales/packages/pipeline/src/echotales/pipeline/persona/scoped_reference.py) | L1–395 (`emit_scoped_reference`, `ScopedEmissionResult`, `EmissionStatus`) | Cutoff-scoped emitter. Resolves attributes via `StateResolver.resolve_admissible_attributes`; tracks physical `source_row_id` and semantic `fact_ref`; constructs prompt strictly from admissible attributes; emits `<asset_id>_manifest.json`. |
| [`packages/core/src/echotales/core/state.py`](file:///home/adhyan/Desktop/EchoTales/packages/core/src/echotales/core/state.py) | L355–425 (`resolve_admissible_attributes`), L653–657 (`_fold_target`), L260–268 (`_voided_timelines`), L510–560 (`GenerationState`) | `resolve_admissible_attributes` preserves full `Attribute` models and bitemporal metadata; legacy `_fold_target` had bypassed knowledge cutoff on persona attributes (D1/D2). |
| [`packages/core/src/echotales/core/models.py`](file:///home/adhyan/Desktop/EchoTales/packages/core/src/echotales/core/models.py) | `TemporalFact`, `Attribute`, `FactProvenance` | `source_row_id: int | None = None` added to enable physical SQLite row lineage. |
| [`packages/core/src/echotales/core/store.py`](file:///home/adhyan/Desktop/EchoTales/packages/core/src/echotales/core/store.py) | `get_attributes` | Populates `source_row_id=r["id"]` from SQLite cursor. |
| [`packages/pipeline/src/echotales/pipeline/render/panels.py`](file:///home/adhyan/Desktop/EchoTales/packages/pipeline/src/echotales/pipeline/render/panels.py) | L2740–2741, L2811, L2851 | `render_panels` unconditionally sets `reference_images=[]` and `reference_weight=0.0`. Production backend does not consume reference images. |
| [`packages/pipeline/src/echotales/pipeline/render/plan_builder.py`](file:///home/adhyan/Desktop/EchoTales/packages/pipeline/src/echotales/pipeline/render/plan_builder.py) | L205–224 (`build_render_plan`) | Opt-in `visual_registry` hook invokes `VisualMemorySelector.select`; falls back cleanly to `reference_path_for` when registry is omitted. |
| [`packages/pipeline/src/echotales/pipeline/persona/reference_gen.py`](file:///home/adhyan/Desktop/EchoTales/packages/pipeline/src/echotales/pipeline/persona/reference_gen.py) | L657–676 (`_generate_one`), `appearance_of` | Legacy reference generator queries `appearance_of(..., position=None)`, pooling all-novel attributes without cutoff. |
| [`packages/pipeline/src/echotales/pipeline/world/context.py`](file:///home/adhyan/Desktop/EchoTales/packages/pipeline/src/echotales/pipeline/world/context.py) | L124–136 (`story_context`, `_facts_as_of`) | Director prompts built from chapter-only filtering, bypassing `StateResolver` and observer scoping (defect D8). |
| [`packages/pipeline/src/echotales/pipeline/render/cache_key.py`](file:///home/adhyan/Desktop/EchoTales/packages/pipeline/src/echotales/pipeline/render/cache_key.py) | L1–40 (`compute_render_cache_key`) | Hashes `plan.state_digest` and `request.base.reference_images`. When `reference_images` is empty, reference asset changes do not invalidate panel cache. |
| `packages/pipeline/src/echotales/pipeline/voice/` | Entire directory | Grep for `state_of` or `StateResolver` yields 0 hits; voice generation is completely unconditioned by narrative temporal/observer state. |
| `packages/core/src/echotales/core/readset.py` | `Store.record_artifact`, `invalidate_by_facts` | Zero callers in production rendering (only present in `eval/persist.py`). |

---

## 4. Tests Executed in this Audit (Model-Free, CPU)

Execution environment: Linux, Python 3.12 virtualenv at `.venv`, editable packages `echotales-core` and `echotales-pipeline`. No external API calls, no GPU, zero dollar cost.

| Test Command | Scope | Outcome | Verification Details |
|---|---|---|---|
| `.venv/bin/pytest packages/core/tests/test_visual_memory.py packages/pipeline/tests/test_scoped_reference.py` | Visual memory & scoped reference test suite | **20 passed in 5.92s** | R1–R6 rules verified: embodiment mismatch, cutoff exclusion, observer authorization, retraction filtering, recursive lineage, fallback; scoped emission verified: sequential vs retrospective, body transition, manifest generation, SHA-256 digest sensitivity, tampering detection, legacy compatibility. |
| `.venv/bin/pytest packages/core/tests/` | Entire core test suite | **140 passed in 1.31s** | Confirms zero regressions across core models, interval logic, store operations, state resolution, and disclosure compilation. |
| `python docs/research/formal_narrative_compiler/probes/prop_cutoff.py` | Adversarial cutoff faithfulness probe | **6,000 queries, 3,059 violations (51.0%)** | Confirms that production legacy path violates prefix faithfulness due to whole-novel attribute pooling (D1/D2). |
| `python docs/research/formal_narrative_compiler/probes/probe_audit.py` | Targeted defect probes A, A', B | **Verified** | Proves probe A leaks ch100 scar into ch5 panel; probe A' confirms `state_of` prevents it; probe B confirms retracted attribute visible in `state_of` but dropped from drawn traits. |

---

## 5. Published Prior Art Consulted

| Reference / Paper | Citation / URL | Scope & Method of Examination | Relevance to EchoTales Claims |
|---|---|---|---|
| **Narrative World Model (NWM)** | Saifullah et al., arXiv 2607.05577 (Jul 2026) | Abstract, HTML structure, methodology | Establishes story time vs reveal/discourse time separation, narratological memory, chapter-safe retrieval. Confirms EchoTales' temporal split is not novel in itself. |
| **NarraWorld ("Shared Worlds, Private Minds")** | arXiv 2609.32401v1 (Sep 2026) | Full HTML read (~92%) | Implements shared narrative graph with per-character private belief views, disclosure-scoped retrieval, non-destructive validity intervals. Directly overlaps observer-scoped retrieval claims. |
| **CANVAS** | arXiv 2604.13452 (Apr 2026) | Full HTML read (~90%) | Per-character visual anchors keyed by state; frame-to-frame consistency; reference reuse across shots. Overlaps dynamic visual memory and state-varying appearance. |
| **VideoMemory** | arXiv 2601.03655 (Jan 2026) | Abstract, paper review | Dynamic visual memory bank for character/prop consistency with state updates. Overlaps visual reference reuse. |
| **Story2Board** | arXiv 2508.09983 (Aug 2025) | Abstract, paper review | Shared character reference sheets for storyboard consistency. Overlaps consistent reference generation. |
| **Narrative Knowledge Weaver (NKW)** | arXiv 2606.05724 (Jun 2026) | Abstract, paper review | Query-time audit of actor, scope, polarity, and temporal constraints over narrative facts. Overlaps query-time admissibility filtering. |
| **FilmWorld** | arXiv 2607.19038 (Jul 2026) | Abstract, paper review | State-anchored visual scene generation. Overlaps narrative state conditioning. |
| **Jularr (Spoiler-Safe Chapter Artwork)** | GitHub `Juloc/Jularr` (Issue #407, PR #451, Sep 2026) | PR description, code review notes | **Direct open-source precursor to N4**: chapter-cutoff prompt gating, fail-closed spoiler guard, context hashing, reuse of earlier safe artwork. |
| **FIDES, APPA, SPA** | arXiv 2505.23643, 2607.24625, 2608.27234 | Architecture & security summaries | Information Flow Control (IFC) and non-interference applied to LLM agent contexts and prompts. Proves label-propagation on prompt inputs is standard IFC. |
| **Adapton / Incremental Computation** | PLDI 2014, Hammer et al. | Published paper | Proves incremental dependency tracking and demand-driven cache invalidation are established PL/DB techniques. |
| **Dyreson & Snodgrass (1998)** | *Capturing Valid-Time Indeterminacy* | Classical database literature | Proves three-valued fuzzy temporal intervals are classical database theory. |
| **Jensen et al. (1998)** | *Consensus Glossary of Temporal Databases* | Classical database literature | Proves bitemporal transaction-time closure and snapshot reads are textbook concepts. |
| **Runway Asset Lineage / C2PA** | RunwayML help docs; C2PA Specifications | Specification & implementation review | Establishes parent-asset lineage DAGs and content-addressed manifest integrity as standard digital asset infrastructure. |
| **VividWorld & NovelViz** | Searched across arXiv, Google Scholar, GitHub | **Not located (UNVERIFIED)** | Titles cited in earlier execution notes could not be located; treated as unverified. |
