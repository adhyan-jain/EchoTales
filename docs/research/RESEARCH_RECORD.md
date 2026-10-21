# EchoTales research record: summary, history, novelty ledger, source inventory, next decision, methods plan, contribution inventory

> Merged on 2026-10-22 from 7 separate documents to keep the docs tree small. Each section below is one original file, text unchanged; its old path is in the section heading. The originals are in git history.

---

<!-- merged-from: docs/research/ECHOTALES_EXECUTIVE_SUMMARY.md -->
## Source: `docs/research/ECHOTALES_EXECUTIVE_SUMMARY.md`

# EchoTales research: executive summary (paste into a fresh conversation)

*Audit Date: 2026-10-13 | Repository: `adhyan-jain/EchoTales` | Branch: `validation/evidence-pass-2026-09-24` @ `6c7e2c2`.*  
*Full details in `docs/research/`: [`ECHOTALES_RESEARCH_HISTORY.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_RESEARCH_HISTORY.md), [`ECHOTALES_NOVELTY_LEDGER.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_NOVELTY_LEDGER.md), [`ECHOTALES_NEXT_RESEARCH_DECISION.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_NEXT_RESEARCH_DECISION.md), [`ECHOTALES_SOURCE_INVENTORY.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_SOURCE_INVENTORY.md).*

---

### Project
EchoTales converts long web-novel volumes into a queryable, bitemporal narrative knowledge graph (story time, discourse cutoff, observer; Self vs. Persona; positional retraction $\neq$ interval end) and drives a manga-style visual adaptation and full-cast audiobook from it. The owner has limited human bandwidth and an absolute minimal GPU budget (~$10–$15 on RunPod).

---

### What Has Been Tried, in Order, and What Happened
1. **The Narrative KG as the Primary Contribution (N1)** (Aug–Sep 2026; paper draft *"Observer- and time-scoped identity in long serialised fiction"*, target WNU 2027 / ACL System Demo).
   *Outcome*: Never rejected; stalled because in-domain evaluation rests entirely on silver LLM labels. The 200-mention human confirmation sample had 0 labels. Claim boundaries already forbid calling time- or observer-scoped state "new in itself".
2. **Killed Side Tracks (N7, N8, N9)**:
   - *State-digest cache invalidation (N7)*: Killed for lack of novelty (subsumed by Adapton, PLDI 2014; *Build Systems à la Carte*). Kept as product infrastructure.
   - *StoryTrace LLM investigator (N8)*: Rejected on evidence (only 2 deferrals across 1,532 groups; hard cases lost at detection).
   - *77-token prompt budget / stage loss (N9)*: Parked (H-JUDGE-V proved attributes are dropped by the image diffusion generator, not the token budget).
   - *Minimal Disclosure Compiler (N5)*: Built, but structurally hollow on real data (RI contains 0 `SELF` attributes and 0 relations in target chapters).
   - *E-CRDT (I1)*: Maintained on a separate IP track; not an academic paper candidate.
3. **Research Arena (R1–R11)** (Oct 2–3, 2026; 33 candidates on rendering under upstream uncertainty, explicitly firewalled from narrative modeling).
   *Outcome*: Killed: confidence-as-posterior (H-CAL; AUROC 0.58), graded voice hedge (H-HEDGE; discrete jumps), confusion-aware casting (H-CCAST; gain −0.002), audio-judge study (H-JUDGE-A; prior art), and the convergence thesis (R2; cross-model disagreement is published in ICLR 2026; action layer is mathematically definitional). Kept: Rule-vs-LLM disagreement (XDIS) as product infrastructure (catches 93% of speaker errors at 20% review). Visual judge finding retained: CLIPScore is at chance (AUROC 0.52).
4. **Formal Narrative Compiler (N3)** (Oct 13, 2026; *"revision-safe compiler from narrative state to multimodal outputs"*).
   *Outcome*: NARROW, trending NO-GO. Proved theorems T1–T3 are standard consequences of snapshot reads and bitemporal transaction-time closure. The legacy pipeline violated them (51.0% violations on adversarial stores, reproduced). Real databases have 0 retractions and 0 retrospective reveals. Guarantees stop at the prompt.
5. **Reveal-Aware Visual Memory / Disclosure-Safe Visual Asset Selection (N4)** ($q = (p, k, o, \pi)$).
   *Outcome*: Broad version fully covered by CANVAS, VideoMemory, Narrative World Model, and NarraWorld. Narrow version overlaps open-source app Jularr (Sep 2026; chapter-gated artwork, fail-closed spoiler guard, context hash, reuse of earlier safe art). The remaining difference reduces to standard Information Flow Control (IFC) on an asset DAG. Shipped databases have 0 instances of the distinguishing events. Production backend never passes references to the image model (`panels.py` L2740-2741 sets `reference_images=[]` due to IP-Adapter color bleeding).
   *Verified Implementation*: Phase 1 & 2 are implemented and committed at HEAD `6c7e2c2` (`visual_memory.py`, `scoped_reference.py`, 26 tests passing). It is an essential Level A engineering fix that eliminates whole-novel attribute leakage in reference generation, but **fails as a standalone research paper**.

---

### Defensible Path to Publication
- **Direction N4 as a standalone paper**: **NO-GO (~80%)**. Keep as an essential product correctness engine.
- **Overall Strategy**: **CONDITIONAL GO on Option C**: Complete the end-to-end observer- and time-scoped identity *systems* paper (N1) for the **WNU 2027 Workshop or ACL 2027 System Demonstrations Track**, folding in the formal compiler harness and the cutoff-scoped visual asset selector as a verified correctness / non-interference engine.
- **The Two Mandatory Conditions**:
  1. The owner records a decision in `docs/research/DECISION_LOG.md` lifting or re-scoping the 2026-10-02 "StoryTrace firewall".
  2. Complete human adjudication on the evaluation sample (`data/eval/human_review_200.csv` and `data/eval/human_review_hardcases_88.csv`).
     *Execution*: Run LLM-assisted pre-annotation using an OpenAI model with reasoning (e.g. `gpt-5.6-luna` or `o3-mini`) under `docs/results/GOLD_AND_ANNOTATION.md` at minimal cost (~$0.15–$0.25 total on user's API key), followed by rapid author adjudication. This unblocks the paper in 1–2 hours instead of 6–8 hours of manual annotation from scratch.
- **GPU Spending**: **$0.00 on RunPod** until the paper is unblocked and a single, pre-registered observer-contrast render figure is required.

---

### Do Not Repeat
- Do not launch new hypothesis hunts in the rendering arena.
- Do not attempt a standalone formal-methods paper claiming snapshot reads or bitemporal transaction-time closure as novel theorems.
- Do not attempt a standalone paper claiming "visual memory / character consistency".
- Do not attempt cache-invalidation or dependency-tracking as a research contribution (Adapton owns it).
- Do not use CLIPScore or LLaVA-7B as automated judges for visual narrative errors (CLIPScore AUROC is 0.52).

---

<!-- merged-from: docs/research/ECHOTALES_NEXT_RESEARCH_DECISION.md -->
## Source: `docs/research/ECHOTALES_NEXT_RESEARCH_DECISION.md`

# Next research decision

**Audit Date**: 2026-10-13  
**Audited Branch & HEAD**: `validation/evidence-pass-2026-09-24` @ `6c7e2c2` (clean tree).  
**Evidence Documentation**: [`ECHOTALES_RESEARCH_HISTORY.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_RESEARCH_HISTORY.md), [`ECHOTALES_NOVELTY_LEDGER.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_NOVELTY_LEDGER.md), [`ECHOTALES_SOURCE_INVENTORY.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_SOURCE_INVENTORY.md).

---

## 1. Executive Decision Summary

| Core Question | Decision | Confidence | Rationale |
|---|---|---|---|
| **N4: Disclosure-safe visual asset selection as a standalone paper** | **NO-GO** (keep as product fix) | **~80%** [INFER] | Core mechanisms are covered by Jularr (PR #451), CANVAS, VideoMemory, and NWM. Narrow delta is standard Information Flow Control (IFC). Shipped novel databases contain zero instances of the distinguishing events ($p \neq k$ persona facts, retractions, observer divergence). Production backend does not consume references (`panels.py` L2740-2741). |
| **Overall Research Strategy: The path to an academic publication** | **CONDITIONAL GO (Option C)** | **~75%** [INFER] | Complete the existing end-to-end observer- and time-scoped identity *systems* paper (N1) for WNU 2027 workshop or ACL 2027 System Demonstrations Track. Fold the formal compiler harness and the Phase 1 & 2 cutoff-scoped visual asset selector into the paper as a verified correctness / non-interference engine. |
| **RunPod / GPU Spending Now** | **$0.00 (Zero)** | **High** | No GPU compute is justified until the evaluation sample is verified and an observer-contrast render figure is pre-registered. |

### The Two Conditions for the CONDITIONAL GO
1. **Lifting or Re-Scoping the 2026-10-02 "StoryTrace Firewall"**:
   On 2026-10-02, the research arena adopted a scope restriction declaring narrative temporal, observer, and identity modeling as "firewalled" product infrastructure (`docs/research/README.md`). The rationale was never recorded in the repo. To publish N1 (with N3/N4 folded in), the owner must explicitly record a decision in `docs/research/DECISION_LOG.md` lifting or re-scoping this firewall.
2. **Completing Human Adjudication on the Evaluation Dataset**:
   The single empirical blocker preventing submission of N1 is that all in-domain evaluation metrics currently rest on silver LLM labels (`docs/paper/PUBLICATION_READINESS.md`). The evaluation dataset comprises:
   - `data/eval/human_review_200.csv` (200 stratified mention rows across 7 strata).
   - `data/eval/human_review_hardcases_88.csv` (88 hard-case entity shifts).
   **Practical Resolution Without 6–8 Hours of Manual Annotation**:
   Instead of spending 6–8 hours manually annotating from scratch, an LLM with reasoning (e.g. `gpt-5.6-luna` or `o3-mini`) can execute pre-annotation under `docs/results/GOLD_AND_ANNOTATION.md` at negligible cost (~$0.15–$0.25 total on the user's API key). The author then performs rapid adjudication over the candidate labels and 1-sentence explanations. This preserves 100% academic integrity while eliminating the time bottleneck.

---

## 2. The Surviving Claim of N4 Stated Exactly (and Why it Reaches Level A, Not B–D)

If Direction N4 were pursued as an independent research contribution, the only claim not already covered by prior art in the ledger would be:

> For a narrative knowledge store with separate story position $p$, discourse cutoff $k$, and observer $o$, a visual asset may be reused for query $q = (p, k, o, \pi)$ only if the union of disclosure labels over **the asset and all its transitive ancestors** (source facts, prompts, parent reference images) is admissible at $q$; the check fails closed when any ancestor's provenance is missing or its image content bytes do not match the manifest. Gating the *current prompt* at cutoff $k$ (as Jularr does) is insufficient when $p \neq k$, when observers differ, or when a parent image was generated under a more permissive disclosure context.

### Why this is Level A (Engineering Integration), Not Level B–D:
1. **Reduces to Standard Information Flow Control (IFC)**:
   This mechanism is classic label propagation through a derivation DAG with a subset inclusion check at the sink context. IFC for LLM prompts and agent memory is an active, established line of work (FIDES, arXiv 2505.23643; APPA, arXiv 2607.24625; SPA, arXiv 2608.27234). Digital asset lineage with cryptographic byte binding is standard infrastructure (C2PA; Runway asset lineage).
2. **Absence of Real Empirical Events**:
   In all shipped databases (*Reverend Insanity*, *Lord of the Mysteries*, *Omniscient Reader's Viewpoint*), there are **0 retrospective persona facts**, **0 retractions**, and only **12 observation rows** (`REPOSITORY_AUDIT.md` D4). The distinguishing cases where N4 departs from Jularr ($p \neq k$, observer authorization, retractions) exist only in synthetic test fixtures.
3. **Production Backend Disconnection**:
   As verified in `render/panels.py` L2740-2741, `render_panels` unconditionally passes `reference_images=[], reference_weight=0.0`. IP-Adapter reference conditioning was deliberately disconnected in production (HANDOFF Section 4.47) due to severe color bleeding across characters. A visual memory paper cannot demonstrate visual benefits if the production renderer never conditions on the selected reference images.

**Conclusion**: Direction N4 reaches **Level A**. It provides immediate engineering value by eliminating whole-novel attribute leakage in reference generation, but fails to substantiate a standalone research paper.

---

## 3. Comparison of Alternatives

| Option | Novelty Potential | Distance from Prior Art | Formal / Method Strength | Implementation Remaining | Real Evidence Available | Human Workload | GPU / API Cost | Target Venue & Genre |
|---|---|---|---|---|---|---|---|---|
| **A. Continue N4 Narrow (Standalone Visual Memory)** | Low | Small: Jularr (k-gating, fail-closed guard, context hash, safe reuse); CANVAS/VideoMemory (visual memory, state anchors) | IFC non-interference on an asset DAG; standard | Medium-large: re-enable backend reference conditioning without reviving 4.47 color contamination; build extraction for $p \neq k$ data | None for the distinguishing cases | High (hand-extracting retrospective/observer facts) | GPU required to render panels | Workshop short paper at best |
| **B. Continue N4 After Blockers** | Low-Medium | Same as Option A until dense $p \neq k$ and observer facts exist | Same | Large: narrative extractor refactor; contamination-safe conditioning backend | None today | Medium (annotation) | GPU | Workshop |
| **C. Finish N1 System Paper; Fold N3/N4 as Correctness Section** *(Recommended)* | Medium-Low as a whole; high as an end-to-end system | Medium: No published system combines bitemporal/observer-scoped identity across 199 chapters with multimodal generation driven by the same query; NWM and NarraWorld are text-only | Systems representation + A1/A2 causal ablations + model-free cutoff faithfulness harness finding 4 real defects | Small: route persona reads through `state_of` (M1 fix); add cutoff harness as permanent pytest; k-gate reference sheets | A1/A2 observer ablations, A7 cache ablation, LitBank, canonical RI run, hard-case analysis; human sample pending | Low (~1–2 hours author adjudication after LLM pre-annotation) | $0 GPU required; ~$0.20 API for LLM pre-annotation; $\le \$5$ optional for one render figure | **WNU 2027 Workshop or ACL 2027 System Demonstrations Track** |
| **D. Negative-Results / Application Note (R2, XDIS)** | Low as method, high as honest finding | High overlap: cross-model disagreement (ICLR 2026), deferral (Deng 2012, Goren 2024); value is product-faithful protocol and parse artifact | Measurement, not new method | Zero (writing only) | Complete, persisted (`data/eval/research/H-XDIS-PS/…`) | None | $0 | Insights / Negative-Results Workshop |
| **E. Stop Research Effort** | — | — | — | — | — | — | — | — |

**Recommendation: Option C (finish the N1 systems paper with N3/N4 folded in), falling back to Option D, then Option E.**  
Option C is the only path that possesses a defensible central claim, established empirical evidence, zero human user study requirements, and minimal dollar cost.

---

## 4. Unresolved Prior-Art Questions (Ranked by Decision Impact)

1. **VividWorld & NovelViz**:
   Neither paper could be located across arXiv, Google Scholar, or GitHub. If either is real and establishes reveal-gated visual reference selection, N4 is completely anticipated. If either performs observer-aware multimodal generation over full novels, N1 is weakened.
2. **Jularr Source Code (`Juloc/Jularr`)**:
   PR #451 establishes chapter-gated artwork generation and reuse of "earlier safe artwork". Does Jularr's implementation recursively check the parent asset's context hash, or only the top-level chapter number?
3. **NarraWorld (arXiv 2609.32401)**:
   The paper promises code "upon publication". Its exact mechanism for belief correction and disclosure scope filtering must be monitored.
4. **Narrative World Model (NWM, arXiv 2607.05577)**:
   Dual story vs. discourse time indexing is confirmed. Does NWM include any multi-character observer access control, or is it strictly author/reader-focused?
5. **Flashback-Aware Depiction ($p < k$)**:
   No prior work was found that explicitly conditions a depiction of past story time on a subsequent narrative reveal. The absence of prior art in literature searches is suggestive, but lacks empirical data in shipped corpora.

---

## 5. Pre-Registered Kill Criteria for N4

| # | Kill Criterion | Evaluation Status |
|---|---|---|
| **K1** | A public system already implements reader-cutoff-gated generation with a fail-closed prompt guard and context-keyed caching. | **Fires**: Jularr PR #451 (merged 2026-09-27) [PUB]. |
| **K2** | Shipped databases contain zero instances of $p \neq k$ persona facts, retractions, or observer-differentiated appearance. | **Fires**: Shipped DBs contain 0 retractions, 0 retrospective facts, 12 observation rows [REPO, D4]. |
| **K3** | Production backend does not consume the selected reference asset. | **Fires**: `render/panels.py` L2740-2741 sets `reference_images=[]`, `reference_weight=0.0` [INSPECT]. |
| **K4** | Every Phase 2 test passes against a simple baseline combining Jularr-style prompt cutoff gating with a $\le 30$-line transitive label-subset check. | **Fires**: The Phase 1 & 2 implementation validates that the selector reduces to transitive label propagation. |
| **K5** | VividWorld or NovelViz, if located, describes reveal-gated reference selection. | **Untested**: Papers could not be located. |

Because **K1, K2, K3, and K4 already fire**, N4 is decisively killed as a standalone research paper.

### Reopening Conditions for N4:
N4 can only be reopened if:
1. Criteria K2 and K3 are reversed: a narrative corpus with real retrospective reveals and character secrets is constructed, AND a reference conditioning backend is implemented that beats EVOLUTION 4.47's color bleeding baseline.
2. A leak class is demonstrated that a standard transitive label-subset check cannot prevent.

---

## 6. Concrete Execution Plan Under Option C (Zero GPU, Negligible API Cost)

1. **Record Firewall Decision**:
   The owner records the formal decision lifting or re-scoping the 2026-10-02 firewall in `docs/research/DECISION_LOG.md`.
2. **Execute LLM Pre-Annotation & Human Adjudication**:
   - Run `scripts/review/llm_annotate.py` across `data/eval/human_review_200.csv` (200 mentions) and `data/eval/human_review_hardcases_88.csv` (88 hard cases) using an OpenAI model with reasoning (e.g. `gpt-5.6-luna` or `o3-mini`).
   - Generates candidate judgments (`correct`, `incorrect`, `unresolved`) and 1-sentence explanations following `docs/results/GOLD_AND_ANNOTATION.md`.
   - Estimated cost: ~$0.15–$0.25 total on user's API key.
   - Author performs rapid review and adjudication over the candidate labels to finalize the evaluation set with 100% human-verified integrity.
3. **Engineering Corrections (Model-Free, CPU)**:
   - Route persona reads through `StateResolver.state_of` (M1 fix in `formal_narrative_compiler/IMPLEMENTATION_PLAN.md`) to resolve defect D1/D2.
   - Turn `docs/research/formal_narrative_compiler/probes/prop_cutoff.py` into a permanent `pytest` property test.
   - Gate reference sheets in `persona/reference_gen.py::_generate_one` by cutoff $k$.
4. **Draft Evaluation Section for WNU 2027 / ACL 2027 Demo**:
   - Report overall precision, stratum-by-stratum metrics, and Wilson 95% confidence intervals from the adjudicated human evaluation set.
   - Present defects D1/D2/D7/D8 found by the cutoff-faithfulness harness and verify that the provenance-scoped compiler eliminates them.
   - Stop there. Do not launch new hypothesis hunts or benchmark expansions.

---

## 7. Strict Conditions Required Before Any RunPod Spending

The owner has a minimal RunPod budget of approximately $10–$15. To avoid squandering GPU funds:

1. **Zero GPU Spend Prior to Paper Unblocking**: No RunPod instances should be provisioned until the human evaluation set is adjudicated and the firewall decision is logged.
2. **Pre-Registered Figure Requirement**: GPU compute may only be spent to generate a single, pre-registered observer-contrast figure (e.g., 2–3 chapters comparing reader vs. character perception) specifically needed for the paper draft (estimated cost $\le \$5.00$).
3. **Probe Validation**: Automated evaluation on images must use a validated visual metric; H-JUDGE-V proved that CLIPScore is at chance (AUROC 0.52) and LLaVA-7B is invalid for narrative attribution errors.
4. **Color Contamination Baseline**: If reference image conditioning is re-enabled on GPU, it must empirically demonstrate that it does not suffer from the character color bleeding documented in EVOLUTION Section 4.47.

---

<!-- merged-from: docs/research/ECHOTALES_NOVELTY_LEDGER.md -->
## Source: `docs/research/ECHOTALES_NOVELTY_LEDGER.md`

# EchoTales novelty ledger (deduplicated)

**Audit Date**: 2026-10-13  
**Audited Branch & HEAD**: `validation/evidence-pass-2026-09-24` @ `6c7e2c2` (clean tree).  

This document provides a canonical, deduplicated audit of every research hypothesis and direction investigated in EchoTales.
One row per canonical direction; alternate titles and subordinate candidates are grouped under it.

Evidence Tags:
- **[REPO]**: Committed document or commit message in repository.
- **[PUB]**: Published literature, specification, or preprint examined.
- **[INSPECT]**: Verified by direct code inspection or test execution in this audit.
- **[INFER]**: Research judgment or analytical inference.
- **UNVERIFIED**: Claimed or reported, but could not be independently confirmed.

Evidence Strength:
- **High**: Executed benchmark/probe reproduced in codebase, or primary source code/paper inspected.
- **Medium**: Executed once historically, or prior art read at abstract/summary level.
- **Low**: Unsubstantiated note, snippet, or unrecoverable deletion record.

---

## A. Narrative Representation, Epistemics & Multimodal Compilation (Inside 2026-10-02 Firewall)

| Research Direction | Main Novelty Claim | Closest Prior Art | Actual Rejection / Narrowing Reason | Evidence Strength | Status | Reopen Condition |
|---|---|---|---|---|---|---|
| **N1. Observer- and time-scoped identity KG**<br>*(Paper: "Observer- and time-scoped identity in long serialised fiction"; Matrix Classes A, C, D)* | Entity identity (Name $\to$ Self $\to$ Persona) scoped by story time, discourse cutoff, and observer over a full 199-chapter web novel driving generation. | EvolvTrip, STAGE, Disney IAAI-18, Living the Novel, NWM (2607.05577), NarraWorld (2609.32401), bitemporal DBs (Jensen et al. 1998). | **Never formally rejected**. Stalled on evaluation: in-domain numbers rest on silver LLM labels; 200-mention human confirmation sample has 0 labels; real data has only 3 reveals, 12 observation rows, 0 retractions. Claim boundaries forbid calling observer/time-scoped state "new in itself" [REPO]. | Medium | **PAUSED — EVIDENCE** + **NARROWED** | 200-mention human confirmation sample labeled; owner formally lifts/re-scopes StoryTrace firewall. |
| **N2. Observer-conditioned generation**<br>*(Observer contrast render; Track 4 item 18; Patent draft "strongest and newest")* | The same narrative scene rendered visually as a character observer believes it vs. as the reader knows it. | NGP, CANVAS, FilmWorld, StoryState (lacks observer viewpoints) [REPO]; Jularr chapter-gated artwork [PUB]. | Evaluated on 5 panels from 1 chapter; character observer yielded 0/5 valid conditioned panels; witness-level visual conditioning unsupported because embodiments are reader-scoped [REPO]; references never passed to backend (`panels.py` L2740) [INSPECT]; voice unconditioned [INSPECT]. | Medium | **PAUSED — EVIDENCE** (superseded by N4) | Multi-chapter render demonstrating pixel contrast under observer shift with a validated visual probe. |
| **N3. Formal narrative compiler**<br>*(Revision-safe compiler from narrative state to multimodal outputs; C-A cutoff semantics, C-B disclosure specs)* | Revision-safe compiler from narrative state to multimodal outputs with proved theorems T1–T3 (prefix faithfulness, belief preservation, incremental stability) and differential test harness. | Snapshot reads / transaction time (Jensen et al. 1998; MVCC); Dyreson & Snodgrass (1998); Adapton (PLDI 2014); NWM (2607.05577); Graphiti; IFC for LLM prompts (FIDES 2505.23643, APPA 2607.24625). | Theorems T1–T3 are standard consequences of snapshot isolation and bitemporal transaction-time closure [PUB]; production pipeline violates them (51.0% violations on adversarial stores due to D1/D2) [INSPECT]; 0 real retractions/reveals in shipped DBs [REPO]; guarantees govern prompt inputs, not generated diffusion pixels [INFER]. | High (probes reproduced) | **NARROWED**, trending **REJECTED — NOVELTY** as standalone formal paper | Real corpus with non-trivial retraction/observer events; theorem beyond snapshot reads; label discipline catching leaks invisible to property tests. |
| **N4. Disclosure-safe, provenance-aware visual asset selection**<br>*(Reveal-Aware Visual Memory; Past-Safe Visual Memory; Scoped Reference Emission)* | Provenance-scoped selector for $q = (p, k, o, \pi)$ enforcing embodiment at $p$, disclosure cutoff at $k$, observer authorization, retraction filtering, recursive DAG lineage, fail-closed fallback, policy-keyed manifests. | Jularr PR #451 (chapter-gated prompt guard, fail-closed fallback, context hash, reuse of earlier safe art) [PUB]; CANVAS (state-keyed visual anchors) [PUB]; VideoMemory (dynamic visual memory) [PUB]; NWM / NarraWorld (discourse vs story time, observer views) [PUB]; Runway / C2PA (asset DAG lineage); IFC prompt lattices. *VividWorld & NovelViz not located (UNVERIFIED)*. | Broad claims (visual memory, consistency, variants, reuse, DAG) fully covered by prior art [PUB]. Narrow algorithmic delta ($p \neq k$, observer authorization, retractions, recursive lineage) reduces to standard IFC over an asset DAG [INFER]; shipped DBs contain 0 real instances of distinguishing cases [REPO]; production backend does not consume references (`panels.py` L2740 `reference_images=[]`) due to IP-Adapter colour bleeding (EVOLUTION 4.47) [INSPECT]. | High (Phase 1 & 2 code fully inspected & verified) | Broad: **REJECTED — NOVELTY**.<br>Narrow: **REJECTED — EVIDENCE + FEASIBILITY** as a paper; **RETAINED** as an essential Level A product fix. | Production backend safely consuming references without colour contamination; real novel dataset with $p \neq k$ and observer facts; distinguishing leak class uncatchable by simple prompt gating. |
| **N5. Minimal Disclosure Compiler (MDC)**<br>*(IPR candidate 1 of 3)* | Task-sufficient minimum projection of observer-valid narrative state via greedy key coverage and relation pruning. | Least-privilege context pruning; task-conditioned RAG filtering. | Real-data evaluation structurally hollow: RI contains 0 `SELF` attributes and 0 relations in target chapters; only synthetic test fixture showed discrimination (36.4%); prior art review never conducted in repo [REPO]. | Low | **PAUSED — EVIDENCE**; novelty **UNVERIFIED** | Real corpus with dense attributes/relations and an independently designed evaluation task. |
| **N6. Temporal-Epistemic Delta Compiler / Counterexample Generation**<br>*(IPR candidates 2, 3)* | Compiling minimal update deltas upon narrative state revisions; counterexample-guided prompt repair. | Incremental computation; CEGIS. | Never started in repository [REPO]; core delta invalidation concepts subsumed by N3's analysis of T3/P4. | Low | **Never Started** | Formal specification distinct from N3. |
| **N7. Cache-key / read-set invalidation; provable completeness**<br>*(Matrix Class F; A7 ablation; E-CRDT Candidate 2)* | Content-addressed caching using SHA-256 digest of consulted facts as a provably complete invalidation key. | Adapton (PLDI 2014); self-adjusting computation; *Build Systems à la Carte*. | Established literature already proves soundness of dynamic dependency graphs; read-set invalidation unsound under insertion and lacks production callers [REPO, INSPECT]. | High | **REJECTED — NOVELTY** (retained as product infrastructure) | None plausible. |
| **N8. StoryTrace bounded evidence investigator** | Deploying an LLM investigator to resolve coreference links in the DEFER band of the scorer. | StoryTrace (owner's companion project). | Labelled candidates are resolved by deterministic pre-filters (101 FORCE_LINK, 2 BLOCK, 0 SCORE); 58/88 hard cases lost at detection; only 2 deferrals across 1,532 mention groups [REPO]. | High | **REJECTED — EVIDENCE** | Mention detector repaired and sufficient candidate volume in the scorer's operating band. |
| **N9. 77-token prompt budget optimization & stage loss**<br>*(Interface/truncation direction; C21, C26, C29)* | Optimizing narrative prompts within CLIP's 77-token limit and stage-wise error attribution. | KathaTrace; Hallucination Snowball (2608.14588); CausalFlow. | Cited as killed in arena notes, but original kill record was deleted (**UNVERIFIED** rejection rationale); H-JUDGE-V later proved missing traits are dropped by the diffusion generator (12.5% rendered), not the token budget [REPO]. | Low | **UNVERIFIED** rejection; **PARKED** in arena | Recovery of original kill record; empirical proof that prompt truncation causes stage-dependent loss. |

---

## B. Rendering Under Upstream Uncertainty (Research Arena; Outside 2026-10-02 Firewall)

| Research Direction | Main Novelty Claim | Closest Prior Art | Actual Rejection / Narrowing Reason | Evidence Strength | Status | Reopen Condition |
|---|---|---|---|---|---|---|
| **R1. Perceptual cost of attribution errors & crossover**<br>*(H-COST v1/v2, H-IOL, C01–C03, C11, C33)* | Perceptual severity of casting errors depends non-linearly on voice distinctiveness; distinctive voices unmask errors. | Selective Abstraction (2602.11908); Conformal Linguistic Calibration; MultiActor-Audiobook; Stevenage (2018). | Not rejected mathematically. Requires ~50 human listeners; H-IOL ideal listener survives at model level (spillover ratio 0.744), but P3 perceptual crossover unsupported without human perceptual data [REPO]. | Medium (machine level) | **PAUSED — FEASIBILITY** (requires human study) | Volunteer human listener pool available. |
| **R2. Disagreement $\to$ safer action $\to$ error manifestation**<br>*(Convergence thesis; H-XDIS, H-GATE-XDIS, H-ACT, C04, C12, C18)* | Rule-vs-LLM disagreement selects a conservative rendering that alters how upstream errors manifest to users. | Cross-model disagreement (ICLR 2026); Deng (2012) / US 9,779,291; Goren et al. (2024); Hallucination Snowball; learning to defer. | Layers 1 and 3 already published in prior art; Layer 2 is mathematically definitional ($R^2 = 0.95$ from reference geometry) [REPO]. XDIS retained as product infrastructure (AUROC 0.943; catches 93% of errors at 20% review) [REPO]. | High | **REJECTED — NOVELTY + TECHNICAL** (definitional); XDIS retained as infra | Evidence that human listener cost diverges significantly from geometric acoustic distance. |
| **R3. Graded voice hedge**<br>*(H-HEDGE, C13)* | Interpolating voice latents expresses graded model uncertainty to listeners. | Latinus & Belin (2012); INSIDE. | 82% of identity shift occurs abruptly at discrete model switch points rather than smoothly [REPO]. | High | **REJECTED — TECHNICAL** | Continuous voice synthesis engine with perceptually linear identity control. |
| **R4. Scorer confidence as posterior**<br>*(H-CAL, C32)* | Coreference scorer tier constants function as well-calibrated posterior probabilities. | Classical calibration literature. | Assumption fails: AUROC 0.573–0.590, ECE 0.179 [REPO]. Useful negative finding: addressee capture is 52.3%. | High | **REJECTED — TECHNICAL** | Calibrated probabilistic model. |
| **R5. Confusion-aware casting**<br>*(H-CCAST)* | Casting algorithm separates predicted-confusable character pairs in acoustic space. | Speaker clustering literature. | Statistical gain −0.0022 (CI spans 0); confusion correlates $r=0.96$ with baseline casting need [REPO]. | High | **REJECTED — TECHNICAL** | None plausible. |
| **R6. Correction allocation**<br>*(H-LEVER, H-FIRST, H-CRN, C26, C31)* | Allocating human review effort by downstream listener leverage. | CAR; AgenTracer; PRELUDE. | Downstream leverage is dominated by first-appearance review (H-FIRST); real correction log too sparse (34 corrections, stale IDs) [REPO]. | Medium | **NARROWED** to H-FIRST; H-CRN **PARKED** | Full LLM-tier ladder execution; fresh correction log with valid entity IDs. |
| **R7. Narrative moment selection**<br>*(H-SELECT, H-COMPL, C20, C23)* | Selecting which $k$ of $N$ narrative beats to illustrate based on reader preference. | ViStoryBench; KathaTrace; visualness literature (2305.10434). | Preconditions verified; reclassified as **PRODUCT-ONLY** by convergence pass; requires manual annotation [REPO]. | Medium | **PAUSED** / Product-only | Annotators available. |
| **R8. Visual abstention under uncertainty**<br>*(H-VRUNG, H-VABST, C22, C14)* | Adjusting visual camera shot framing to abstain from ambiguous character attributes. | IMPLICIT-Bench; default-image studies. | No natural framing hides both gender and hair while remaining legible; attribute-free prompts generate no person [REPO]. | Medium | **PAUSED — TECHNICAL** | Framing technique that conceals both traits legibly; reader study. |
| **R9. Judge validity**<br>*(H-JUDGE-A, H-JUDGE-V, C05, C25, C27)* | Automated multimodal judges fail to detect rendered narrative errors. | SpeakerSleuth (2601.04029); HEAR (2608.29120). | Audio side killed without running (published by SpeakerSleuth/HEAR) [REPO]. Visual side retained as measurement finding: CLIPScore AUROC is 0.52 (chance) [REPO]. | Medium | H-JUDGE-A **REJECTED — NOVELTY**; H-JUDGE-V retained finding | None. |
| **R10. Cross-modal disagreement as error detector**<br>*(H-XMOD, C28, T4)* | Disagreement between visual panels and audio narration localizes narrative state errors. | Multimodal consistency literature. | Zero labels; legitimate artistic non-correspondence destroys detector precision [REPO]. | Low | **PARKED — EVIDENCE** | Labeled multimodal errors. |
| **R11. Triage kill audio/HCI methods**<br>*(C07–C10, C17–C19, C31)* | Long-context multi-voice TTS, casting from text, timbre metrics, uncertainty flags, edit-based preference learning. | Audiobook-CC, Deep Dubbing, MOSS-TTSD, S-VoCAL, SwanBench, CAP, Berke (2017), PRELUDE, LibriQuote. | Mechanism already owned by prior literature, or proposed claim is definitional/tautological [REPO]. | Medium | **REJECTED — NOVELTY** | None. |

---

## C. Separate IP Track

| Research Direction | Main Novelty Claim | Closest Prior Art | Actual Rejection / Narrowing Reason | Evidence Strength | Status | Reopen Condition |
|---|---|---|---|---|---|---|
| **I1. E-CRDT revocable/delegable local derivation** | Conflict-free replicated data type ensuring that merge operations never manufacture narrative knowledge without explicit provenance edges. | Shapiro & Bieniusa CRDTs; US 7,734,649; Ritschel provisional 64/012,284; MELD. | Narrowed across five review rounds to distributed, provably correct merge logic. Maintained on an independent IP track; classified as "B — Borderline IP / Needs Professional Opinion" (`IPR_REVIEW_FINAL.md`) [REPO]. Deliberately stripped of narrative framing; not an EchoTales paper candidate. | Medium | **B — Borderline IP** (Not an academic paper candidate) | Formal patent/legal opinion; $O(\Delta)$ merge optimization. |

---

## D. Deduplicated Foldings

To ensure that duplicate concepts under differing titles are tracked under a single canonical entry:
1. *"Reveal-Aware Visual Memory"*, *"Past-Safe Visual Memory"*, *"Disclosure-safe, provenance-aware visual asset selection"*, C-B *"disclosure-labelled specifications"*, and C10 *"label-checked disclosure"* are unified under **N4**. (C-B and C10 represent its specification-checking half, which also links to N3).
2. *"Temporal-Epistemic Delta Compiler"* and *"Counterexample-Guided Generation"* are folded into **N3** (properties T3/P4) and **N7**.
3. *"Observer-conditioned generation"* (Patent Draft Track 4) is unified under **N2**, with its visual reference successor folded into **N4**.
4. C21, C26, C29 (arena) and Track 5 items 21–23 are unified under **N9** (*77-token prompt budget / interface truncation*).
5. H-SELECT and H-COMPL are unified under **R7** (*narrative moment selection*).
6. H-VRUNG, H-VABST, and the H-ACT image arm are unified under **R8** (*visual abstention*).
7. H-JUDGE-A and H-JUDGE-V are unified under **R9** (*judge validity*).

---

<!-- merged-from: docs/research/ECHOTALES_RESEARCH_HISTORY.md -->
## Source: `docs/research/ECHOTALES_RESEARCH_HISTORY.md`

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
10. **Supporting Artifacts**: `docs/paper/CONTRIBUTION_MATRIX.md`, `docs/paper/PUBLICATION_READINESS.md`, `docs/paper/PAPER_CLAIM_BOUNDARIES.md`, `docs/results/ABLATIONS.md`, `docs/results/ABLATIONS.md`.
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
- **Outcome**: In empirical analysis (`docs/results/EXPERIMENT_RESULTS.md`), 101 candidates were resolved by deterministic rules (FORCE_LINK), 2 were BLOCKED, and 0 candidates reached the score-based operating range. Out of 1,532 mention groups, only 2 deferrals occurred.
- **Status**: **REJECTED — EVIDENCE**. The operating band where an investigator could provide value does not occur with sufficient frequency in the data.

---

### Direction 1d — State-Digest Cache Key & Read-Set Invalidation (N7)
- **Claim**: Content-addressed cache invalidation based on a digest of consulted narrative facts.
- **Outcome**: The mechanism was necessary to fix defect A7 (where 23 panels were served stale after an attire change). However, as a research claim, automatically derived dependency graphs and cache invalidation are completely subsumed by established incremental computation systems (Adapton, PLDI 2014; *Build Systems à la Carte*). Furthermore, read-set invalidation is unsound under fact insertion.
- **Status**: **REJECTED — NOVELTY** as a research contribution. Retained as vital product infrastructure.

---

## 3. Direction 2 — Minimal Disclosure Compiler (MDC) (N5)

1. **Claim**: Compiling a task-minimal projection of an observer-valid narrative state by pruning facts irrelevant to a declared generation task (`packages/core/src/echotales/core/disclosure.py`, commit `22fa812`).
2. **Tested**: Evaluated across 45 render queries on *Reverend Insanity* and 1 synthetic dialogue fixture (`docs/results/ABLATIONS.md`).
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

---

<!-- merged-from: docs/research/ECHOTALES_SOURCE_INVENTORY.md -->
## Source: `docs/research/ECHOTALES_SOURCE_INVENTORY.md`

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
- [`docs/results/GOLD_AND_ANNOTATION.md`](file:///home/adhyan/Desktop/EchoTales/docs/results/GOLD_AND_ANNOTATION.md): Protocol for verifying 200 stratified evaluation mentions and 88 hard cases.
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

---

<!-- merged-from: docs/research/METHODS_PAPER_EXPERIMENT_PLAN.md -->
## Source: `docs/research/METHODS_PAPER_EXPERIMENT_PLAN.md`

# Methods-paper experiment plan: smallest decisive test

**Date**: 2026-10-14 · **HEAD**: `6c7e2c2` · **Status**: proposal only. Nothing in this plan has been run or implemented. It follows from [TECHNICAL_CONTRIBUTION_INVENTORY.md](TECHNICAL_CONTRIBUTION_INVENTORY.md) and [CLAIM_TO_EVIDENCE_MATRIX.md](CLAIM_TO_EVIDENCE_MATRIX.md).

The plan targets the one question the current code can answer cheaply and deterministically: **does enforcing one admissibility policy at every consumer, with live revalidation and transitive closure over derived artifacts, remove exposures that the straightforward fix (each consumer calling `state_of` on its own) does not?** If it does not, the finding is that no technical contribution beyond integration has been established. That outcome is acceptable and should be reported as such.

## 1. Falsifiable main hypothesis

**H.** On an oracle-labelled adversarial suite with distinct story-time and reveal-time cutoffs, observer restrictions, retractions, aliases/titles and derived-asset lineage, a *shared, revalidating admissibility check* (treatment, T) yields **zero** exposures of inadmissible facts in every emitted artifact, while the closest reproducible baselines do not:

- **B1** = the production path as it is at HEAD (`compile_render_state` + `appearance_of` + `_facts_as_of` + `reference_path_for`).
- **B2** = the straightforward fix: each consumer routes through `state_of(p, k, o)` independently, with no shared artifact, no transitive closure and no revalidation (the obvious engineering repair of D1, D2, P1-P3).

**Falsified if** (any one):

1. B2 reaches zero exposures on all classes (then T adds nothing beyond routing consumers through `state_of`; the result is a bug-fix list).
2. T shows exposures in any class (the mechanism does not do what it claims).
3. T reaches zero only by over-suppression: its retained-admissible-fact rate falls more than 2 percentage points below B2's on the classes where both are leak-free (an "emit nothing" policy trivially leaks nothing).

Only a result where B1 > 0, B2 > 0 on specified classes, T = 0, and the ablations (section 4) each break their predicted class would indicate a mechanism beyond integration. Whether that mechanism is *new* is a separate literature decision, not decided here.

## 2. Adversarial test suite (CPU, deterministic)

A seeded generator builds small stores (about 3-6 entities, 2 bodies, 30-60 facts) in `:memory:` SQLite. The oracle is a **separate brute-force implementation** (set comprehension over raw rows: fact is admissible iff interval contains p, `learned_at <= k` [or the observer's witnessed position], observer-authorized, and not retracted at k), written without calling `state_of`, and cross-checked against `state_of` first (a differential test) so the oracle itself is validated.

| Class | Construction | What it separates |
|---|---|---|
| X1 retrospective reveal | fact true at p<=5, `learned_at` ch100, request (p=5, k=10) vs (p=5, k=100) | p-only filter (`appearance_of`) vs k filter |
| X2 forward reveal | fact starts after p but learned before k (foreshadow) | k-only filter (`_facts_as_of`) vs story-interval filter |
| X3 retraction | belief held ch1..49, retracted ch50; requests at k=20 and k=60 | `is_standing` (erases belief) vs positional retraction; also checks that T *keeps* the past belief |
| X4 observer split | reader-stamped fact, character with and without an `observation` row; character-private facts | observer door; character persona bindings (P1) |
| X5 alias/title | transferable title held by A then B; disguise name known to some observers | `resolve_alias`; identity decisions per observer |
| X6 absent evidence | key attribute never stated | over-suppression guard; fallback must say "unknown", not invent |
| X7 derived lineage | asset DAGs depth 1-3: chain, diamond, 2-cycle, missing parent, parent fact admissible only at a later k | own-facts-only filter vs transitive closure |
| X8 stale artifact | artifact built under (p,k,o), then the store gains a retraction or a policy change | snapshot (P6) vs live revalidation |
| X9 derived text | description derived from an asset whose facts include a later reveal | cross-modal lineage; the only class where a shared artifact could matter beyond per-consumer filtering |

Each store yields requests over a grid of (p, k, o). Approx. 10^3 stores x 20 requests is tractable on CPU in minutes.

## 3. Baselines

| Baseline | What it is | Reproducible from |
|---|---|---|
| B1 | Production path as-is | `render/panels.py:character_looks`, `persona/reference_gen.py:appearance_of`, `world/context.py:story_context`, `reference_path_for` |
| B2 | Each consumer calls `state_of(p,k,o)` itself; reference chosen by own-facts filter | New thin adapters over `core/state.py`; no new policy |
| B3 (reference) | The existing `VisualMemorySelector` unchanged, to show what snapshot-only lineage does | `core/visual_memory.py` |
| T | Shared admissibility function consumed by brief, attributes, selector and a derived-text step; revalidates against the live store before reuse; closes transitively | New; to be specified before the run |

B2 is deliberately strong. A weaker baseline (for example the unrepaired production path alone) would only show that known defects exist.

## 4. Ablations (remove one mechanism at a time)

| Ablation | Predicted new exposures | A prediction that fails counts against T |
|---|---|---|
| A1 no knowledge-time filter | X1, X9 | |
| A2 no story-interval filter | X2 | |
| A3 retraction as interval end | X3 (erases past belief: an *over-suppression*, not a leak; measured on the utility metric) | |
| A4 no observer door | X4 | |
| A5 own-facts-only lineage | X7, X9 | |
| A6 snapshot instead of live revalidation | X8 | |

Each ablation must break its predicted class and not unrelated ones; otherwise the mechanism's attribution is unclear.

## 5. Metrics

- **Exposure**: an emitted artifact (prompt string, director brief, reference manifest + parent list, derived text) containing the value or ref of a fact not in the oracle's admissible set. Counted per fact per artifact. Substring matching (as `EpistemicLeakageValidator`) is a lower bound, so report it separately from ref-level lineage exposure.
- **Utility**: fraction of oracle-admissible facts retained in the artifact (guards against over-suppression).
- **Stale-serve**: artifacts reused after one of their source facts became inadmissible.
- **Selector fallback rate** and reasons.
- Report counts with exact binomial intervals; the suite is synthetic, so no population claim is made.

## 6. End-to-end integration test

The standalone selector is not evidence. The check must run the real consumer:

1. Build a constructed database (class X1, X3, X4) into `data/scratch/` with the stub toolchain: `ECHOTALES_LLM_MODE=stub`, `--image-engine stub`.
2. Run `render_panels(..., observer_id=o)` via the CLI path (`echotales --db <scratch.db> render --novel <id> --observer <o> --engine stub`); read `manifest.jsonl` and `render_artifact.jsonl` from the versioned output directory.
3. Apply the oracle to the emitted prompt strings, and to `state_digest` / `plan_digest` for cache identity.
4. Re-run after a store mutation (X8) and verify the cache key changes iff the oracle says a source fact became inadmissible.

For T this requires the production render path to actually call the shared check; for B1 the same run documents today's behaviour. **Audio**: no production voice stage consumes (p, k, o) (`voice/runner.py:198-207`), so an audio end-to-end test is not meaningful until one does. State this as a prerequisite rather than testing a vacuous property.

## 7. Failure analysis and assumptions

- **Raw narration is not filtered.** The director receives the beat's prose; for a character observer that prose contains reader-only information. A fact-level policy cannot remove it. T does not help here unless the prose is regenerated or withheld, which this plan does not test.
- **Prompt-level, not pixel-level.** A clean prompt does not guarantee a clean image. A prior measurement found missing traits are dropped by the generator (12.5% rendered; ledger R9 [HIST]), and the reverse (invented traits) is not measured. A pixel-level claim needs a separate GPU/VLM or human audit and is out of scope.
- **Extraction quality is assumed.** Correct `learned_at`, interval and observer stamps are inputs. Shipped data contains no retractions, no non-READER facts and no relations (inventory section 7), so conclusions are about the policy on constructed stores, not about the corpus.
- **Oracle correctness.** If the oracle and `state_of` disagree in the differential test, resolve that before any comparison.
- **What would falsify the value of the mechanism**: B2 = T on every class; T over-suppresses; A-ablation predictions fail; or X9 shows no case where the shared artifact beats per-consumer filtering.
- **If H holds**, it shows the policy composes and the stale/derived classes need more than routing. It does not show novelty, a quality gain for readers, or any property of generated pixels.

## 8. Resources

| Item | Needs |
|---|---|
| Suite generation, oracle, differential test, B1/B2/B3/T comparison, ablations | CPU only, seconds to minutes, pytest + hypothesis (already in use) |
| End-to-end stub render | CPU only, stub LLM and stub image engine |
| Pixel-level audit, human perception study, real-model director behaviour | GPU and/or API and/or annotators. **Not part of this plan** and not justified before a novelty decision |
| Identity-resolution evidence (C5) | Human adjudication of the existing package. A separate track; this plan does not depend on it |

## 9. Implementation prerequisites (gaps to close before the experiment is meaningful)

1. Specify T (the shared check) and its revalidation rule; today nothing implements it.
2. Make the image path's attribute and brief readers `state_of`-backed (otherwise B1 is the only production comparator and T cannot be exercised end to end). This also fixes D1, D2, P1-P3.
3. Fix `VisualAssetRegistry.register` field loss (P5) and add live revalidation to the selector (P6) before using B3 as a comparator.
4. Populate `EvidenceContext.temporal_certainty` and pass observations in `resolve_alias` (P4) if identity decisions (C5) are to be included.
5. Decide where the experiment lives (`packages/research`, per `CLAUDE.md`) and register it in the research arena; do not edit `DECISION_LOG.md` as part of this proposal.
6. Add at least one modality beyond image that depends on (p, k, o); otherwise cross-modal claims (C6) cannot be tested.

---

<!-- merged-from: docs/research/TECHNICAL_CONTRIBUTION_INVENTORY.md -->
## Source: `docs/research/TECHNICAL_CONTRIBUTION_INVENTORY.md`

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
