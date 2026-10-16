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
   Instead of spending 6–8 hours manually annotating from scratch, an LLM with reasoning (e.g. `gpt-5.6-luna` or `o3-mini`) can execute pre-annotation under `docs/results/HUMAN_REVIEW_PROTOCOL.md` at negligible cost (~$0.15–$0.25 total on the user's API key). The author then performs rapid adjudication over the candidate labels and 1-sentence explanations. This preserves 100% academic integrity while eliminating the time bottleneck.

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
   - Generates candidate judgments (`correct`, `incorrect`, `unresolved`) and 1-sentence explanations following `docs/results/HUMAN_REVIEW_PROTOCOL.md`.
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
