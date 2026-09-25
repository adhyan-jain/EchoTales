# Ablation plan — only implemented mechanisms

**2026-09-25.** Each ablation corresponds to code that exists. Reference set: the LLM-drafted silver set, unless the plan adds a small human-annotated sample (see `PUBLICATION_READINESS.md`).

| # | Ablation | Hypothesis | Metric | Expected interpretation | Runnable now? | Engineering cost |
|---|---|---|---|---|---|---|
| A1 | **No observer state** (all queries as READER) vs full | Observer scoping changes which identities a party can resolve, and therefore what is rendered | Per-observer alias-set size; spoiler leakage = rendered or named identities the observer has not witnessed, across all reveal scenes | Full: 0 leakage for non-witnesses; ablated: leakage equals every reveal | **Yes** (`state_of(observer=...)`; `render --observer`) | Low: a script over the 3 reveals; the render needs the GPU (~5 min/chapter) |
| A2 | **No knowledge position** (knowledge = end of volume) | Without knowledge time, a witness "knows" before the reveal | Pre-reveal visibility of revealed names per witness | Full 0 before the reveal; ablated 1 | **Yes** (the `knowledge_pos` argument) | Low |
| A3 | **No story-position scoping in rendering** (query at final position) vs per-panel position | Position scoping selects the body valid at the panel's position | Share of panels whose selected persona differs from the one valid at that position (reincarnation case) | Differs for all pre-rebirth panels | Needs a flag in `plan_builder` (position=inf) | Low (small code flag) |
| A4 | **No hard constraints** (`no-copresence-blocking`, `no-prefilters-at-all`) | Hard constraints prevent wrong merges | Links made; B³/CEAF-e precision after re-resolve | Blocking removal lets 2,888–3,072 blocked pairs through; the precision effect needs a re-resolve | Cache re-score: **yes** (Table 6). Precision effect: needs a re-resolve per condition | Medium (~15 min/condition, cached NER) |
| A5 | **No gazetteer compounding** | Compounding carries most links and cuts cost | Forced links; silver recall after re-resolve | 1,376 → 704 forced links (measured); recall drop to be measured | Partly (the cache re-score is done) | Medium |
| A6 | **No typed alias resolution** (all aliases as rigid names) | Typing prevents generic descriptors and transferable titles from merging identities | False merges on the hardcases set; silver precision | More wrong links on titles and deictics | Needs a re-resolve flag (the `REQUIRES_RERESOLVE` list) | Medium |
| A7 | **No state digest in the cache key**, holding the prompt and plan digest fixed | With the prompt fixed, only the digest can make state-change-specific artifacts distinct (without that control, the observer contrast changes the prompt too, so the hypothesis is untestable) | (a) Stale artifacts served after a state change; (b) artifacts reused vs regenerated over a sequence of state edits | Without the digest: stale identity served after a reveal; with it: regeneration only for dependent panels | **Yes** in stub mode (`--image-engine stub`, no GPU) | Low: a stub-mode script replaying state edits and counting cache hits |
| A8 | **No learned scorer** (already the de facto state) | The scorer adds nothing | Links, precision | Identical, as measured (0 scorer links) | **Yes** | None (report as a negative result) |

**Not included, because the mechanism is not implemented or not exercised:**
- no retraction (0 real retractions);
- no timelines (0 non-main facts);
- no Self/Persona split (one real case; the re-resolve flag does not exist);
- audio observer conditioning (not implemented).

**Minimum set for a paper:** A1, A2, A7 (the observer mechanism and its generation effect, all runnable cheaply); A4 or A5 as a re-resolve on one condition (causal evidence for the resolution design); and A8 stated.
