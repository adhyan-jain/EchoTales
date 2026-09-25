# Experiment table (paper-ready)

**2026-09-26.**

Reference type:
- **S**: LLM-drafted silver reference set.
- **H**: human-annotated external key.
- **R**: the system's own records (causal ablation).
- **C**: controlled or stub experiment.

**No experiment below is scored against human-annotated gold for the primary novel.**

| Experiment | Purpose | Baseline | Ablation | Data | Metric | Result | Ref. | Status |
|---|---|---|---|---|---|---|---|---|
| Core resolution | Entity-level coreference quality | — | — | RI, 1,816 silver mentions | CEAF-e F1; B³ P | 67.4; 100.0 | S | Done |
| Baseline comparison | Cost and coverage vs simple LLM designs | Long-context LLM; two-LLM memory | — | RI ch1–10, 356 mentions | B³ recall; LLM calls | 0.2% / 4.6% / **78.9%**; 1 / 177 / 0 | S | Done; measures extraction coverage |
| Hard cases | Where identity resolution fails | — | — | 88 hard-case records | detected; correct/wrong among decidable | 30; **24 / 0**; 58 undetected (address 16, relational 15, title 11, pronoun 10) | S | Done |
| Retrieval | Candidate generation given the span | — | — | 46 hard-case spans | Recall@1/5/10/20 | 67.4 / 87.0 / **89.1** / 95.7 | S | Done |
| A1 observer collapse | Causal effect of the observer axis | Full state | observer → READER | 3 reveals, 228 queries | leaks (state; render plan) | 0 → **194**; 0 → **194** | R | Done |
| A2 knowledge time | Causal effect of knowledge time | Full state | knowledge_pos = +∞ | same | leaks (state; render plan) | 0 → **14**; 0 → 0 | R | Done |
| A7 cache key | Does the state digest separate state-dependent artifacts? | Full key (A) | digest removed (B); all state-derived parts removed (C) | 218 panels, 8 events | stale reuse; unnecessary regeneration | Fixed A: 0 stale reuse; B/C: 46 stale reuse; A: 274 unnecessary regenerations | C | Done; the shipped key's appearance defect was found and fixed |
| Observer render contrast | Observer-conditioned generation on a real engine | Reader view | non-reader view | RI ch169, 5 blocks, NoobAI XL | identity-conditioned panels | 5/5 vs 0/5 | C (real engine) | Done, reader vs non-reader only |
| LitBank | Externally comparable, human-annotated number | LitBank paper's supervised system (68.1, not reproduced) | P1 full person key vs P2 names only | 100 docs, 24,180 / 2,665 key mentions | CoNLL F1 (standard) | **15.9** / **42.4** | **H** | Done; zero-shot, names only, not comparable to supervised numbers |
| LOTM generalisation | Transfer to a second web novel | — | — | LOTM ch1–3, 155 mentions | B³ R; CEAF-e F1 | 62.3; 41.4; transmigration split into two Selves | S | Done; a documented failure |
| Human confirmation | Does silver transfer to human judgement? | — | — | 200 + 88 mentions | precision; κ | **Not run: no labels** | H (pending) | Waiting on reviewers |
