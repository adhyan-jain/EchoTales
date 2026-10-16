# EchoTales research history: every direction, what happened to it, and why

**Audit Date**: 2026-10-13  
**Auditor**: Independent Research Auditor (Antigravity), model-free verification.  
**Repository State Audited**: `adhyan-jain/EchoTales`, branch `validation/evidence-pass-2026-09-24`, HEAD `6c7e2c2` (commit *feat(research): implement Reveal-Aware Visual Memory Phases 1 and 2*), clean tree.  
**Base / Master**: `master` @ `6aed9f9` (2026-09-12); 134 commits behind audited branch.  

Companion documents:
- [`ECHOTALES_NOVELTY_LEDGER.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_NOVELTY_LEDGER.md) (deduplicated table)
- [`ECHOTALES_NEXT_RESEARCH_DECISION.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_NEXT_RESEARCH_DECISION.md) (actionable recommendation and kill criteria)
- [`ECHOTALES_SOURCE_INVENTORY.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_SOURCE_INVENTORY.md) (source citations, file links, and test records)
- [`ECHOTALES_EXECUTIVE_SUMMARY.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_EXECUTIVE_SUMMARY.md) (executive transfer summary)

---

## Evidence Labels Used Throughout

| Tag | Meaning |
|---|---|
| **[REPO]** | Stated in a committed repository document, test suite, or commit message. |
| **[PUB]** | Published peer-reviewed or preprint prior art, checked and verified. |
| **[INSPECT]** | Verified directly in this audit by inspecting code or executing model-free tests. |
| **[INFER]** | Research judgment or analytical inference from verified facts. |
| **UNVERIFIED** | Reported in prior notes or prompts, but could not be independently confirmed in source code or published literature. |

---

## 0. Two Framing Realities

1. **Phase 1 & Phase 2 Implementation is Committed and Passing [INSPECT]**:
   Unlike earlier audits conducted on older commits (e.g. `c90fa40`), HEAD is now `6c7e2c2`. The Phase 1 and Phase 2 implementations of Reveal-Aware Visual Memory exist in the repository:
   - `packages/core/src/echotales/core/visual_memory.py` (772 lines; typed asset models, bitemporal selector, DAG lineage validation).
   - `packages/pipeline/src/echotales/pipeline/persona/scoped_reference.py` (395 lines; cutoff-scoped reference emitter, JSON provenance manifest).
   - 20 model-free unit and property tests in `packages/core/tests/test_visual_memory.py` and `packages/pipeline/tests/test_scoped_reference.py` pass cleanly in 5.92s.
   - However, empirical and pipeline inspection reveals that **no production backend consumes reference images** (`render/panels.py` L2740-2741 unconditionally passes `reference_images=[]`), and shipped databases contain **zero instances of the distinguishing events** ($p \neq k$ persona facts, retractions, or multi-observer appearance divergence).
2. **The 2026-10-02 "StoryTrace Firewall" [REPO]**:
   On 2026-10-02, a project decision firewalled research contributions touching narrative temporal, observer, identity, alias, or consistency modelling (`docs/research/README.md`, `hypotheses.toml`). The core narrative knowledge graph was classified as "Product infrastructure. Firewalled as a research contribution."
   The rationale for this firewall was never recorded in the repository. As a result, both the formal narrative compiler (2026-10-13) and the visual-memory asset selection directions sit squarely within this firewalled zone. Pursuing an academic publication on end-to-end observer- and time-scoped narrative systems requires an explicit decision from the owner to lift or re-scope this firewall.

---

## 1. Chronology at a Glance

| # | Period | Research Direction | Primary Status |
|---|---|---|---|
| **1** | 2026-08-07 → 09-26 | Observer- and time-scoped identity KG as the primary contribution (N1) | **PAUSED — EVIDENCE** + **NARROWED** |
| **1a** | 2026-09-23 → 26 | Observer-conditioned visual generation (N2) | **PAUSED — EVIDENCE** |
| **1b** | 2026-09-23 | 77-token prompt budget optimization & stage loss (N9) | **UNVERIFIED** rejection record / **PARKED** |
| **1c** | 2026-09-25 | StoryTrace bounded evidence investigator for DEFER-band coreference (N8) | **REJECTED — EVIDENCE** |
| **1d** | 2026-09-26 | State-digest cache key & read-set invalidation (N7) | **REJECTED — NOVELTY** (kept as product infra) |
| **2** | 2026-09-27 | Minimal Disclosure Compiler (MDC) (N5) | **PAUSED — EVIDENCE**; novelty **UNVERIFIED** |
| **2a** | 2026-09-27 | Temporal-Epistemic Delta Compiler / Counterexample Generation (N6) | **Never started** (superseded by N3) |
| **3** | 2026-09-29 → 30 | E-CRDT distributed derivation & provable cache completeness (I1) | **B-Borderline IP** (CRDT); completeness **REJECTED — NOVELTY** |
| **4** | 2026-10-02 | Research Arena: 33 candidates on rendering under upstream uncertainty (R1–R11) | 9 **REJECTED — NOVELTY**, 6 parked, 18 evaluated |
| **5** | 2026-10-02 → 03 | Mutation lab & experimental rounds (H-CAL through H-XDIS) | Mixed; see Section 5 |
| **6** | 2026-10-03 | Convergence thesis: disagreement → action → error manifestation (R2) | **REJECTED — NOVELTY + TECHNICAL** (XDIS kept as infra) |
| **7** | 2026-10-13 | Formal narrative compiler: revision-safe compiler with T1–T3 guarantees (N3) | **NARROWED**, trending **REJECTED — NOVELTY** |
| **8** | 2026-10-13 | Reveal-Aware Visual Memory / disclosure-safe visual asset selection (N4) | Broad: **REJECTED — NOVELTY**; Narrow: **REJECTED — EVIDENCE + FEASIBILITY** |

---

## 2. Direction 1 — Observer- and Time-Scoped Identity Narrative KG (N1)

1. **Working Title / Question**: "Observer- and time-scoped identity in long serialised fiction" (`docs/paper/CONTRIBUTION_MATRIX.md`). Can a long web-novel be compiled into a queryable narrative knowledge graph where entity identity (name $\to$ Self $\to$ Persona) is scoped by story time, discourse cutoff, and observer, and can that graph drive multimodal generation?
2. **Original Proposed Contribution**:
   - Two-level identity model separating enduring consciousness (`Self`) from physical embodiment (`Persona`).
   - Three-axis temporal coordinate system: story-world position ($p$), discourse cutoff ($k$), and transaction time.
   - Positional retraction semantics (retraction is a discourse position, not an interval endpoint).
   - Observer-specific knowledge isolation via witness records.
   - End-to-end compilation from `state_of(p, k, o)` to panel prompts and audio casting.
3. **Why Promising**: Existing literary KGs (e.g. STAGE, BOOKCOREF, Living the Novel) collapse identity into static entities or single-chapter buckets. Web novels feature extensive body-swapping, transmigration, secret identities, and deceptive reveals that break standard entity resolution.
4. **Existing Code & Data**:
   - `packages/core/src/echotales/core/`: `state.py`, `models.py`, `interval.py`, `store.py`.
   - Databases for three full-length web novels: *Reverend Insanity* (RI, 199 chapters), *Lord of the Mysteries* (LOTM), *Omniscient Reader's Viewpoint* (ORV).
   - Stratified evaluation sets: `data/eval/human_review_200.csv` (200 mentions across 7 strata) and `data/eval/human_review_hardcases_88.csv` (88 hard-case entity shifts).
5. **Literature Considered**:
   - LlmLink, LINK-KG, BOOKCOREF, EvolvTrip, STAGE, Disney IAAI-18, Living the Novel, TimeChara, ToM benchmarks, E2RAG, NGP, StoryWeaver, CANVAS, FilmWorld, StoryState (`docs/paper/RELATED_WORK_FINAL.md`).
   - Recent near-neighbors: Narrative World Model (Saifullah et al., arXiv 2607.05577, Jul 2026) and NarraWorld ("Shared Worlds, Private Minds", arXiv 2609.32401, Sep 2026).
6. **What Was Tested**:
   - Canonical RI extraction run across 199 chapters.
   - A1/A2 observer ablations: collapsing observer scoping to `READER` leaks 194 character secrets in RI; full model leaks 0.
   - A7 cache ablation: detected 23 stale panel reuses on attire shifts.
   - LitBank external benchmark: CoNLL F1 15.9 full key / 42.4 names.
7. **Results & Failure Modes**:
   - In-domain evaluation numbers currently rest on silver LLM-drafted labels.
   - The 200-mention human confirmation sample (`data/eval/human_review_200.csv`) has 0 completed human labels, which constitutes the single empirical blocker for publication (`docs/paper/PUBLICATION_READINESS.md`).
   - Real data in shipped databases exhibits extreme sparsity for the distinguishing features: only 3 reveals and 12 observation rows in RI, 0 in LOTM/ORV; 0 real retractions.
   - Detection, rather than linking, is the primary failure mode (58 of 88 hard cases were missed at mention detection).
8. **Why Paused / Narrowed**: `docs/paper/PUBLICATION_READINESS.md` determined that a main-track ACL submission was premature without human ground truth. Claim boundaries explicitly forbid claiming that observer-scoped knowledge or time-scoped narrative state is "new in itself". Target was narrowed to WNU 2027 workshop or ACL 2027 System Demonstrations track.
9. **Decision Type**: **Provisional (PAUSED — EVIDENCE, NARROWED)**.
10. **Supporting Artifacts**: `docs/paper/CONTRIBUTION_MATRIX.md`, `docs/paper/PUBLICATION_READINESS.md`, `docs/paper/PAPER_CLAIM_BOUNDARIES.md`, `docs/results/A1_OBSERVER_ABLATION.md`, `docs/results/A2_OBSERVER_ABLATION.md`.
11. **Reopen Condition**: Complete adjudication of the prepared 200-mention evaluation sample and record an explicit decision lifting the StoryTrace firewall.

---

### Direction 1a — Observer-Conditioned Generation (N2)
- **Claim**: The same scene rendered visually as a character observer believes it versus as the reader knows it (`docs/archive/COMPLETION_PLAN.md`, Track 4 item 18).
- **Tested**: Evaluated on 5 panels from 1 chapter.
- **Outcome**: Non-reader character observer produced 0/5 valid conditioned panels because embodiment bindings were reader-scoped. In production, `render/panels.py` L2740-2741 passes `reference_images=[]`, so visual conditioning occurs solely via text prompt tags. Voice generation completely lacks observer inputs.
- **Status**: **PAUSED — EVIDENCE**. Replaced by Direction 8 (visual asset selection).

---

### Direction 1b — 77-Token Budget Optimization & Stage Loss (N9)
- **Claim**: Optimizing prompt construction within CLIP's 77-token budget and attributing error across pipeline stages as a research contribution (`COMPLETION_PLAN.md` Track 5 items 22–23).
- **Outcome**: The direction was killed and cited as killed in subsequent arena notes (`DECISION_LOG.md` H-CRN; `RESEARCH_THEMES.md` T3). However, the specific kill analysis document was deleted from the repository (**UNVERIFIED** rejection rationale). Subsequent experiments (H-JUDGE-V) revealed that missing visual attributes were lost inside the image diffusion generator (only 12.5% rendered), not truncated by the token budget.
- **Status**: **PARKED** in the arena.

---

### Direction 1c — StoryTrace Bounded Evidence Investigator (N8)
- **Claim**: Deploying an LLM agent to investigate ambiguous coreference decisions in the DEFER band of the link scorer (`docs/archive/STORYTRACE_TRANSFER.md`).
- **Outcome**: In empirical analysis (`docs/results/SCORER_DIAGNOSIS.md`), 101 candidates were resolved by deterministic rules (FORCE_LINK), 2 were BLOCKED, and 0 candidates reached the score-based operating range. Out of 1,532 mention groups, only 2 deferrals occurred.
- **Status**: **REJECTED — EVIDENCE**. The operating band where an investigator could provide value does not occur with sufficient frequency in the data.

---

### Direction 1d — State-Digest Cache Key & Read-Set Invalidation (N7)
- **Claim**: Content-addressed cache invalidation based on a digest of consulted narrative facts.
- **Outcome**: The mechanism was necessary to fix defect A7 (where 23 panels were served stale after an attire change). However, as a research claim, automatically derived dependency graphs and cache invalidation are completely subsumed by established incremental computation systems (Adapton, PLDI 2014; *Build Systems à la Carte*). Furthermore, read-set invalidation is unsound under fact insertion.
- **Status**: **REJECTED — NOVELTY** as a research contribution. Retained as vital product infrastructure.

---

## 3. Direction 2 — Minimal Disclosure Compiler (MDC) (N5)

1. **Claim**: Compiling a task-minimal projection of an observer-valid narrative state by pruning facts irrelevant to a declared generation task (`packages/core/src/echotales/core/disclosure.py`, commit `22fa812`).
2. **Tested**: Evaluated across 45 render queries on *Reverend Insanity* and 1 synthetic dialogue fixture (`docs/results/MDC_DISCLOSURE_ABLATION.md`).
3. **Outcome**: On real *Reverend Insanity* data, the reduction was structurally hollow: RI contains 0 `SELF` attributes and 0 relationship rows in the target chapter, so the compiler had nothing to prune. The only discriminating result (36.4% fact reduction) occurred on a synthetic test fixture.
4. **Status**: **PAUSED — EVIDENCE**; novelty against standard least-privilege context pruning was never formally established.
5. **Candidates 2 & 3** (*Temporal-Epistemic Delta Compiler*, *Counterexample-Guided Generation*): Mentioned as subsequent IP targets, but never implemented.

---

## 4. Direction 3 — E-CRDT & Invention Discovery Pass (I1)

- **E-CRDT** (`packages/ecrdt/`): A conflict-free replicated data type ensuring that distributed merge operations never manufacture narrative knowledge without explicit provenance edges. Classified in `IPR_REVIEW_FINAL.md` as "B — Borderline IP / Needs Professional Opinion". Maintained on an independent IP track deliberately separated from academic paper submissions.
- **Provable Cache-Invalidation Completeness**: Category A/D in `INVENTION_DISCOVERY_2026-09-30.md`. **REJECTED — NOVELTY**. Prior art (Adapton, self-adjusting computation) already proves soundness of dynamic dependency graphs. Neural and hardware categories were rejected during initial triage as "vocabulary-driven novelty".

---

## 5. Directions 4–6 — Research Arena, Mutation Lab & Convergence Pass (R1–R11)

Conducted on 2026-10-02 and 2026-10-03. Focused strictly on multimodal rendering under upstream uncertainty (audio casting, visual commitment, moment selection), deliberately firewalled from narrative modeling (`docs/research/DECISION_LOG.md`, `CONVERGENCE.md`).

| Hypothesis / Direction | Core Concept | Result | Status & Reason |
|---|---|---|---|
| **C07, C08, C09, C10, C17–C19, C31** | Long-context multi-voice TTS, casting from text descriptions, timbre metrics, uncertainty flags | Triage kill | **REJECTED — NOVELTY** (subsumed by Audiobook-CC, Deep Dubbing, MOSS-TTSD, S-VoCAL, SwanBench, CAP, PRELUDE, LibriQuote). |
| **H-CAL (R4)** | Scorer tier confidence functions as a well-calibrated posterior | AUROC 0.573–0.590, ECE 0.179 | **REJECTED — TECHNICAL**. Calibration assumption fails. Useful negative finding: addressee capture is 52.3%. |
| **H-HEDGE (R3)** | Voice interpolation provides a smooth perceptual hedge under casting uncertainty | 82% of identity shift occurs at discrete model boundaries | **REJECTED — TECHNICAL**. Continuous perceptual hedging failed on discrete voice models. |
| **H-CCAST (R5)** | Confusion-aware voice casting separates easily confused characters | Gain −0.0022 (CI crosses 0); confusion correlates $r=0.96$ with baseline need | **REJECTED — TECHNICAL**. Algorithmic separation provided zero statistical benefit. |
| **H-JUDGE-A (R9)** | Audio-LLM judges fail to detect voice assignment errors | Literature audit | **REJECTED — NOVELTY** without execution (published by SpeakerSleuth, arXiv 2601.04029; HEAR, arXiv 2608.29120). |
| **H-JUDGE-V (R9)** | Visual judges miss rendered upstream narrative errors | Verified on rendered panels | **Retained as measurement finding**: CLIPScore AUROC is 0.52 (chance) on rendered errors. Missing attributes are dropped by the diffusion model, not the prompt. |
| **H-COST (R1)** | Perceptual cost of upstream errors depends on rendering distinctiveness | Stimuli prepared; requires ~50 human listeners | **PAUSED — FEASIBILITY**. Cannot be validated without human listener studies. |
| **H-IOL (R1)** | Ideal-observer listener model predicts attribution confusion | Survives at model level (spillover ratio 0.744); crossover unverified | **PAUSED — FEASIBILITY**. Requires human perceptual data. |
| **H-VRUNG / H-VABST (R8)** | Visual abstention by adjusting shot framing under uncertainty | Prompt masking | **PAUSED — TECHNICAL**. No standard framing hides both gender and hair while remaining legible. |
| **H-SELECT / H-COMPL (R7)** | Optimal moment selection for narrative beat illustration | Preconditions verified | **RECLASSIFIED PRODUCT-ONLY**. Engineering feature, not a standalone research claim. |
| **H-XDIS (R2)** | Cross-model rule vs. LLM disagreement detects errors | AUROC 0.943; detects 93% of errors at 20% review rate | **Retained as product infrastructure**. High operational value for active learning. |
| **Convergence Thesis (R2)** | *Disagreement $\to$ safer action $\to$ altered error manifestation* | Full audit | **REJECTED — NOVELTY + TECHNICAL**. Layer 1 (cross-model disagreement) published in ICLR 2026; Layer 3 published by Deng 2012 and Goren 2024; Layer 2 is mathematically definitional ($R^2 = 0.95$ from reference geometry). |

---

## 6. Direction 7 — Formal Narrative Compiler (N3)

Reconstructed from `docs/research/formal_narrative_compiler/` (2026-10-13).

### 6.1 Original Proposal
"A revision-safe compiler from narrative state to multimodal outputs with formal correctness guarantees."
Proposed theorems:
- **T1 (Prefix Faithfulness)**: An output compiled at discourse cutoff $k$ depends only on facts disclosed at or before $k$.
- **T2 (Historical Belief Preservation)**: A belief held at $k$ is preserved in compilation at $k$, even if subsequently retracted at $k' > k$.
- **T3 (Incremental Stability)**: Appending facts disclosed at $k' > k$ does not alter outputs compiled at cutoff $k$.

### 6.2 Recorded Outcome & Audit Basis
**NARROW, trending NO-GO as a standalone formal paper**.
Evaluated against the 6 research gate criteria in `NOVELTY_DECISION.md`:
- Criterion 3 failed: the provable properties are standard consequences of snapshot isolation and bitemporal transaction-time closure.
- The pipeline itself violated the properties: adversarial probing (`probes/prop_cutoff.py`) revealed **51.0% violations** (3,059 of 6,000 queries) due to legacy whole-novel attribute pooling (defects D1, D2, D7, D8).
- Shipped databases contain zero retractions and zero retrospective reveals, meaning any empirical demonstration would be entirely synthetic.
- The formal guarantee governs only the text prompts and conditioning specifications, not the pixels produced by the downstream diffusion model.

### 6.3 Point-by-Point Evaluation

| Point | Finding | Basis | Classification |
|---|---|---|---|
| **Cutoff/prefix faithfulness resembles snapshot / bitemporal reads** | Theorem T1 is mathematically equivalent to reading an append-only log under transaction-time closure at version $k$. | literature (Jensen et al. 1998; MVCC) + judgment | (c) literature + (d) judgment |
| **Historical belief preservation under positional retractions** | Theorem T2 corresponds to classical bitemporal valid-time vs. transaction-time separation. Graphiti closes `invalid_at` and `expired_at` simultaneously, but the theoretical distinction is standard in database literature. | code inspection of Graphiti (`edge_operations.py`) + literature | (a) code inspection + (c) literature |
| **Independence of earlier cutoffs from later appended facts** | Theorem T3 states that future transactions do not mutate past snapshots. Violated in production because legacy `appearance_of` ignored cutoffs. | executable probe (`probes/prop_cutoff.py`, 51% violations reproduced) | (b) executable probe |
| **Story time vs. reveal time already published** | Narrative World Model (NWM, arXiv 2607.05577) already separates event chronology from narrative discourse reveal order and enforces chapter-gated retrieval. | literature inspection of NWM | (c) literature |
| **Uncertain valid time** | EchoTales' three-valued fuzzy intervals (`CERTAIN`, `PLAUSIBLE`, `EXCLUDED`) are a specialization of classical valid-time indeterminacy (Dyreson & Snodgrass, 1998). | literature inspection | (c) literature |
| **Cache invalidation & incremental computation** | Digest-based caching and dependency tracking are fully anticipated by Adapton (PLDI 2014) and *Build Systems à la Carte*. | literature inspection | (c) literature |
| **Information Flow Control (IFC) on prompts** | Applying label-propagation lattices to prompt assembly is active prior art (FIDES, arXiv 2505.23643; APPA, arXiv 2607.24625; SPA, arXiv 2608.27234). | literature search | (c) literature + (d) judgment |
| **Weak real-data coverage** | Shipped databases contain 0 retractions, 0 retrospective persona facts, and 12 observation rows. | SQL inspection of `data/novels/` | (a) code inspection |
| **Compiler guarantees vs. generator semantics** | Guarantees govern compiler output (prompts, specifications), but generative diffusion models frequently omit prompt constraints (H-JUDGE-V: 87.5% setting drop rate). | empirical measurements from arena | (b) executable probe + (d) judgment |
| **Disconnected production paths** | Defects D1, D2, D7, D8: `render/panels.py` and `world/context.py` bypassed `GenerationState` via whole-novel text scans. | code inspection | (a) code inspection |

---

## 7. Direction 8 — Reveal-Aware Visual Memory / Disclosure-Safe Visual Asset Selection (N4)

### 7.1 Evolution of Titles and Claims
1. *"Reveal-Aware Visual Memory for Long-Form Narrative Adaptation"*: Broad framing emphasizing dynamic visual memory banks, character consistency, body variant transitions, reference asset reuse, and dependency DAGs.
2. *"Past-Safe Visual Memory"*: Narrowed to preventing spoiler leakage from future narrative chapters into early character reference depictions.
3. *"Disclosure-safe, provenance-aware visual asset selection for nonlinear narrative adaptation"*: Mathematically formulated as a query $q = (p, k, o, \pi)$ with 7 formal selector gates (Section 5 of `ECHOTALES_NEXT_RESEARCH_DECISION.md`).

### 7.2 Detailed Prior-Art Audit

| Prior Work | Established Capabilities | Overlap with Proposed EchoTales Claims | Non-Overlapping Delta / Gaps | Verification Method |
|---|---|---|---|---|
| **Jularr (Juloc/Jularr PR #451)** | Chapter-gated artwork generation; fail-closed spoiler guards; spoiler-safe context hashes; reuse of earlier safe artwork. | **Directly overlaps**: discourse cutoff gating at $k$, fail-closed fallback, content-addressed caching, reference asset reuse. | Does not decouple story position $p$ from cutoff $k$ (no flashbacks); lacks observer authorization; no recursive DAG lineage. | [PUB] PR #451 and issue #407 inspected. |
| **CANVAS (arXiv 2604.13452)** | Per-character visual anchors keyed by state; frame-to-frame consistency; reference reuse across shots. | **Overlaps**: dynamic visual memory, time-varying appearance, reference asset reuse. | Text-only narrative state; does not model reveal cutoffs or observer knowledge. | [PUB] Full HTML read (~90%). |
| **Narrative World Model (arXiv 2607.05577)** | Dual story-time vs. reveal-time indexing; narratological memory; chapter-gated retrieval. | **Overlaps**: decoupling of story time and reveal time; spoiler prevention. | Text-generation focus; no visual reference management or image conditioning. | [PUB] Abstract and paper structure inspected. |
| **NarraWorld (arXiv 2609.32401)** | Shared narrative graph with per-character private belief views; disclosure-scoped retrieval; non-destructive intervals. | **Overlaps**: observer-indexed knowledge isolation; private vs. public views. | Text-only; lacks visual generation and recursive asset lineage. | [PUB] Full HTML read (~92%). |
| **VideoMemory (arXiv 2601.03655)** | Dynamic memory bank of visual and semantic descriptors updated across narrative shots. | **Overlaps**: visual memory for long-form character consistency. | No narrative disclosure gating or provenance DAGs. | [PUB] Abstract inspected. |
| **Story2Board (arXiv 2508.09983)** | Shared character reference sheets for multi-panel storyboard consistency. | **Overlaps**: reusable reference sheet generation. | Static reference sheets; no temporal evolution or narrative state. | [PUB] Abstract inspected. |
| **Narrative Knowledge Weaver (arXiv 2606.05724)** | Query-time audit of actor, scope, polarity, and temporal constraints over narrative facts. | **Overlaps**: query-time admissibility checks. | Text-only QA system; no visual reference compiler. | [PUB] Abstract inspected. |
| **Runway Asset Lineage / C2PA** | Cryptographic parent-asset lineage DAGs and content-addressed manifest verification. | **Overlaps**: recursive asset lineage, manifest hashing, byte binding. | Generic media provenance; lacks narrative temporal/epistemic semantics. | [PUB] Documentation inspected. |
| **FIDES, APPA, SPA (IFC for LLMs)** | Information Flow Control lattices enforcing non-interference on LLM prompts. | **Overlaps**: label-propagation lattice on prompt inputs. | General agent security; not specialized for narrative adaptation. | [PUB] Papers inspected. |
| **VividWorld & NovelViz** | Cited in earlier prompts as narrative reference systems. | **UNVERIFIED**: Could not be located across arXiv, Google Scholar, or GitHub. | No substantiated claims can be made. | [PUB] Targeted search failed. |

---

## 8. Audit of Phase 1 and Phase 2 Implementation Evidence (HEAD `6c7e2c2`)

Unlike the earlier audit at `c90fa40` where Phase 1 and Phase 2 were uncommitted, HEAD `6c7e2c2` contains the complete implementation. An independent inspection of the working tree verifies the following technical facts:

### 8.1 Verification of Specific Technical Questions
1. **Source Fact Identity**:
   - Persisted SQLite rows have `source_row_id: int` populated from the autoincrement primary key (`models.py`, `store.py`).
   - Semantic assertions are identified by `fact_ref: str` via `observable_ref(attr)` in `readset.py` (e.g. `attr:persona_id:hair_color:black`).
   - Epistemic attestation tuples in `FactProvenance` record `(fact_ref, learned_at_pos, valid_interval, retracted_at, observer_id, truth_status, certainty, source_row_id)`.
2. **Auxiliary Prompt Sources (Canon, Demographics, Attire, Fallback)**:
   - In `scoped_reference.py`, `include_canon` defaults to `False`. When `True`, it overlays static canon dictionaries which are un-scoped.
   - Demographics are extracted strictly from admissible `Attribute` rows; if missing, they fall back closed to `"unknown"` / `"adult"` without scanning whole-novel prose.
   - Fallback text: If no grounded appearance attributes are admissible, `emit_scoped_reference` returns `FALLBACK_PROMPT_ONLY`, generating a generic prompt without character traits.
3. **Whole-Novel Context Bypass**:
   - `emit_scoped_reference` completely bypasses legacy `appearance_of(..., position=None)` and `gather_appearance_passages`. Attributes are resolved strictly through `StateResolver.resolve_admissible_attributes(..., knowledge_pos=effective_cutoff, position=story_pos, observer_id=observer_id)`.
   - However, legacy `reference_gen.py` remains in the codebase and still uses the whole-novel bypass.
4. **Recursive Parent Asset Lineage & Cycles**:
   - `VisualAssetRecord` methods (`transitive_facts`, `transitive_parent_ids`, `compute_effective_cutoff`) use a `visited: set[str]` accumulator, guaranteeing termination on cyclic dependencies.
   - Missing parent assets fail closed with `TRANSITIVE_LINEAGE_VIOLATION`.
5. **Manifest Tampering & Byte Integrity**:
   - Manifests record `prompt_digest` and `image_content_digest` (SHA-256 of output image bytes).
   - In `test_scoped_reference.py`, altering image bytes triggers content-hash divergence.
6. **Query Policy & Cache Identity**:
   - Asset IDs and manifests incorporate story position, discourse cutoff, policy, and prompt SHA-256 digest (`ref_{novel_id}_{self_id}_{persona_id}_p{p}_k{k}_{digest}`).
7. **Production Backend Consumption**:
   - **Crucial Negative Finding**: `packages/pipeline/src/echotales/pipeline/render/panels.py` L2740-2741 unconditionally instantiates `PanelImageRequest` with:
     ```python
     reference_images=[],
     reference_weight=0.0,
     ```
   - **No production panel render passes reference images to any diffusion engine.** Reference conditioning was disconnected in production (HANDOFF Section 4.47) due to severe IP-Adapter color bleeding and composition contamination.
8. **Observer Semantics & Retraction Coverage**:
   - Real shipped databases contain only 12 observation rows in *Reverend Insanity* and 0 in other novels. Shipped databases contain 0 real retractions. All multi-observer and retraction tests operate over synthetic fixtures.
9. **Backward Compatibility**:
   - `build_render_plan` in `plan_builder.py` maintains an opt-in `visual_registry` hook. When omitted, it preserves legacy behavior with 100% test compatibility.

---

## 9. Evaluation of Contribution Levels (Direction 8)

The proposed contribution of Direction 8 is evaluated across four academic contribution tiers:

- **Level A (Engineering Integration of Established Techniques)**:
  Applies Information Flow Control (IFC) and non-interference over an asset derivation DAG with bitemporal narrative coordinates $(p, k, o, \pi)$.
  **Supported by Current Code**: Yes. Fully implemented, robustly tested (20/20 tests passing), content-addressed manifests serialized.
- **Level B (New Narrative-Specific Asset Selection Algorithm & Enforceable Policy)**:
  Requires an algorithm whose properties cannot be expressed as standard IFC label propagation over a bitemporal lattice.
  **Supported by Current Evidence**: No. Mathematically, the selector reduces to transitive label union and subset inclusion against the sink context $(p, k, o)$.
- **Level C (Formally Characterized Compositional Guarantee with Novel Capability)**:
  Requires proving non-interference across generative models or demonstrating an end-to-end capability not achieved by prior art.
  **Supported by Current Evidence**: No. The guarantee stops at prompt text; downstream diffusion models can hallucinate concealed features. Jularr already provides cutoff gating, fail-closed spoiler guards, context hashing, and safe asset reuse.
- **Level D (Competitive Research Paper as a Standalone Visual System)**:
  Requires real-world empirical validation showing superior narrative consistency or spoiler prevention on a real corpus.
  **Supported by Current Evidence**: No. Production backends do not consume references (`reference_images=[]`), and shipped novel databases contain 0 instances of the distinguishing events ($p \neq k$ persona facts, retractions, observer divergence).

**Conclusion**: Direction 8 reaches **Level A**. It is an indispensable, high-integrity product fix that prevents whole-novel attribute leakage in reference generation, but **does not support a standalone research paper**.
