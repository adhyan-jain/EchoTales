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
     *Execution*: Run LLM-assisted pre-annotation using an OpenAI model with reasoning (e.g. `gpt-5.6-luna` or `o3-mini`) under `docs/results/HUMAN_REVIEW_PROTOCOL.md` at minimal cost (~$0.15–$0.25 total on user's API key), followed by rapid author adjudication. This unblocks the paper in 1–2 hours instead of 6–8 hours of manual annotation from scratch.
- **GPU Spending**: **$0.00 on RunPod** until the paper is unblocked and a single, pre-registered observer-contrast render figure is required.

---

### Do Not Repeat
- Do not launch new hypothesis hunts in the rendering arena.
- Do not attempt a standalone formal-methods paper claiming snapshot reads or bitemporal transaction-time closure as novel theorems.
- Do not attempt a standalone paper claiming "visual memory / character consistency".
- Do not attempt cache-invalidation or dependency-tracking as a research contribution (Adapton owns it).
- Do not use CLIPScore or LLaVA-7B as automated judges for visual narrative errors (CLIPScore AUROC is 0.52).
