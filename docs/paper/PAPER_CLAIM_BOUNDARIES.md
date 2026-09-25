# Paper claim boundaries

**2026-09-25; revised 2026-09-26 after the evidence-upgrade pass.** What the paper may say, what it may say only with a qualifier, and what it must not say. Grounded in `docs/FINAL_EVIDENCE_TABLE.md`, `CONTRIBUTION_MATRIX.md` and `RELATED_WORK_FINAL.md`.

## May claim (with the evidence cited)

1. A representation in which **identity** (which name denotes which persistent Self, and which body a Self has) is scoped by story time and by observer and knowledge position, queryable at any position of a long real text.
2. A pipeline that builds it over a full 199-chapter web-novel volume on a single consumer GPU, with zero model calls at the resolution stage.
3. **On an LLM-drafted silver reference set:**
   - CEAF-e F1 67.4 with B³ precision 100%;
   - every decidable detected hard case linked correctly (24/24 decidable; 30 detected, 6 undecidable), with most hard cases never detected (58/88);
   - retrieval recall@10 89.1% given the span.
4. The same observer query conditions image generation: on one chapter, reader-view panels are identity-conditioned (5/5) and non-reader-view panels are not (0/5).
5. **Findings:**
   - detection, not linking, is the bottleneck for forms of address, relational references and titles;
   - surface-trivial reference sets make MUC/B³ measure string matching;
   - a learned scorer added no links over deterministic evidence rules;
   - two of three pre-registered predictions were refuted;
   - LLM speaker attribution is unstable across runs.

## May claim only with a qualifier

- Observer-conditioned knowledge. It must be framed as extending prior character-knowledge modelling (Disney IAAI-18, EvolvTrip, STAGE, ToM benchmarks) to identity facts and to generation, **not** as introducing character knowledge modelling.
- Generalisation. Report LOTM ch1–3 (B³ recall 62.3, CEAF-e F1 41.4) and the transmigration split as limits.
- Efficiency versus baselines. This is a cost and coverage comparison on a surface-trivial range, not coreference quality.
- Self/Persona. The representation, plus one sequential real case; concurrent cases are tested only on synthetic fixtures.

## Must not claim

- Human-gold accuracy, "ground truth", or human agreement, unless the confirmation sample is done.
- That observer-scoped knowledge or time-scoped narrative state is new in itself.
- That the system handles disguise, possession, transmigration or concurrent bodies on real data.
- That audio or voice is conditioned on narrative state or observer (it is not).
- Witness-level visual conditioning (embodiment bindings are reader-scoped).
- Image or audio quality (not measured).
- Retraction or dream/flashback handling on real data (0 rows).
- Any "first", "novel" or state-of-the-art claim, or comparison numbers against LLMLink, LINK-KG or BOOKCOREF, none of which were reproduced.
- A LitBank comparison against published supervised systems. Our LitBank numbers (standard CoNLL F1 15.9 on the full person key, 42.4 on proper-name mentions) are zero-shot and cover names only. The published 68.1 uses a different mention-detection setting. They may be reported side by side only with that stated, and never as "competitive".
- That the render cache saves GPU time. A7 measured correctness (0 vs 46 stale reuses) and 274 *extra* regenerations. The GPU-hour figure is an estimate; it was not measured.
- The superseded figures: 63.0% attribution (it is 46.1%), or 96.3% as the same-range baseline comparison (it is 78.9%).

## Evidence-upgrade pass (2026-09-26): how each result may be used

| Result | Class | Use in paper |
|---|---|---|
| A1: observer collapsed to READER → 194 state leaks and 194 render-plan leaks (full: 0) across 3 reveals, 228 queries | **Empirical finding** (causal ablation, scored against the system's own records) | Evidence that the observer axis is load-bearing. It is not evidence that the recorded observations are *correct*: witness derivation is unvalidated. |
| A2: knowledge time removed → 14 state leaks, 0 render leaks | Empirical finding | Knowledge time matters at the state level only. At the render level it is currently redundant, because bindings are reader-scoped. Say so. |
| FULL: 9 under-exposures (mid-chapter reveals) | Negative result | Report. Chapter-granular knowledge position is too coarse for mid-chapter reveals. |
| A7: without the state digest, 46 stale reuses (appearance changes); the shipped key had the same defect until it was fixed in this pass | **Engineering correctness finding** | A limitation and correctness note in the system section. **Not a research contribution.** The digest also over-invalidates (274 unnecessary regenerations on binding/offstage events). |
| A7 observer switch: separated by the prompt in every condition | Negative for the digest | Observer separation at render time is prompt-driven; the digest adds nothing there. |
| LitBank: 15.9 / 42.4 standard CoNLL F1 (P1 / P2), sanity check 100 | **External, human-annotated** | The only non-silver number. It shows a precision-heavy, names-only resolver (P2 key-restricted: MUC P 99.0, R 29.2; standard-mode MUC P falls to 48.0 once spurious system mentions count). Frame it as external validity of the design's precision/recall trade-off, not as coreference competitiveness. |
| Human-review package: 200 + 88 rows prepared, 0 labelled | Pending | Nothing may be claimed until it is labelled. With one reviewer, report agreement with silver only, not κ. |

**Engineering vs research vs empirical.**
- *Engineering:* the pipeline, the cache key, the stub-first harness, the fix to the appearance digest.
- *Research:* the representation (identity scoped by story time, observer and knowledge position) and its use to condition generation.
- *Empirical findings:* A1/A2, the detection bottleneck, the surface-trivial metric effect, the refuted predictions, attribution instability, LitBank.
