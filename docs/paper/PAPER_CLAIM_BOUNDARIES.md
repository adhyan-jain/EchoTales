# Paper claim boundaries

**2026-09-25.** What the paper may say, what it may say only with a qualifier, and what it must not say. Grounded in `docs/FINAL_EVIDENCE_TABLE.md`, `CONTRIBUTION_MATRIX.md` and `RELATED_WORK_FINAL.md`.

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
- Any "first", "novel" or state-of-the-art claim, or comparison numbers against LLMLink, LINK-KG, BOOKCOREF or LitBank that were not reproduced.
- The superseded figures: 63.0% attribution (it is 46.1%), or 96.3% as the same-range baseline comparison (it is 78.9%).
