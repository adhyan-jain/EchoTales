# Report tables — generated, do not hand-edit

Regenerate with `python3 scripts/paper/make_paper_artifacts.py`.
Every number traces to a file under `data/eval/`; nothing here is typed by hand.

### Table 2 — Dataset characteristics and structural validation

| File | Records | Silver | Circular | Surface-trivial | Validator |
|---|---|---|---|---|---|
| `lord-of-the-mysteries-c1-c3.jsonl` | 173 | 173 | 0 | 100.0% | FAIL |
| `reverend-insanity-c1-c5.jsonl` | 343 | 343 | 0 | 100.0% | FAIL |
| `reverend-insanity-hardcases.jsonl` | 89 | 89 | 0 | 63.6% | FAIL |
| `reverend-insanity.jsonl` | 7,879 | 3,457 | 4,422 | 100.0% | FAIL |

*Source: data/eval/validation/*.json (echotales eval --validate-gold)*

*Surface-trivial = share of mentions whose identity is recoverable from the surface string alone. A file near 100% cannot measure an identity resolver; see docs/results/EVAL_RETRIEVER.md section 1.*


### Table 4 — Coreference metrics, current run

| Metric | P (%) | R (%) | F1 (%) |
|---|---|---|---|
| MUC | 100.0 | 95.8 | 97.9 |
| B3 | 100.0 | 94.2 | 97.0 |
| CEAF-e | 89.8 | 53.9 | 67.4 |
| CoNLL | 87.4 | 87.4 | 87.4 |
| B3 (project variant) | 100.0 | 93.6 | 96.7 |

*Source: data/eval/results/reverend-insanity-1790467742-9d0aed88/metrics.json (reference: data/gold/reverend-insanity.jsonl, db: data/scratch/db/ri-titleholders.db)*

*Scored against the LLM-DRAFTED SILVER REFERENCE SET -- not human-annotated, no inter-annotator agreement. See docs/results/GOLD_DATASET_README.md. B3/MUC are TAUTOLOGICAL on a surface-trivial reference set and must not be quoted as accuracy; CEAF-e is entity-based and is the discriminative one here.*


### Table 5 — Retriever Recall@K by alias type, production query context

| Alias type | n | @1 | @5 | @10 | @20 |
|---|---|---|---|---|---|
| **Overall** | 46 | 67.4% | 84.8% | 89.1% | 95.7% |
| EPITHET | 1 | 100.0% | 100.0% | 100.0% | 100.0% |
| RELATIONAL_DEICTIC | 4 | 0.0% | 50.0% | 75.0% | 75.0% |
| RIGID_NAME | 32 | 84.4% | 90.6% | 90.6% | 96.9% |
| TRANSFERABLE_TITLE | 9 | 33.3% | 77.8% | 88.9% | 100.0% |

*Source: data/eval/recall_by_category.json (scripts/eval/recall_by_category.py, db: data/db/reverend-insanity.db at v1.1; v1.2 mentions are identical)*

*LLM-DRAFTED SILVER REFERENCE SET (hardcases file), not human-annotated, no IAA. The reference span is handed to the retriever, so this measures retrieval, not detection. n is small for the hard types: one case moves TRANSFERABLE_TITLE about 11 points and RELATIONAL_DEICTIC 25. With the CLI's snippet context instead, overall @10 is 84.8%.*


### Table 6 — Ablations over 16,538 cached evidence vectors

| Condition | Pairs | Force-link | Blocked | Reached scorer | Scorer would link |
|---|---|---|---|---|---|
| full | 16,538 | 1,376 | 3,072 | 12,090 | 0 |
| no-gazetteer-compounding | 16,538 | 704 | 3,072 | 12,762 | 0 |
| no-declaration | 16,538 | 1,325 | 3,072 | 12,141 | 0 |
| no-name-containment | 16,538 | 1,341 | 3,072 | 12,125 | 0 |
| no-relational-copresence | 16,538 | 1,373 | 3,072 | 12,093 | 0 |
| no-temporal-scoping | 16,538 | 1,376 | 3,072 | 12,090 | 0 |
| no-copresence-blocking | 16,538 | 1,390 | 0 | 15,148 | 0 |
| no-prefilters-at-all | 16,538 | 0 | 0 | 16,538 | 0 |

*Source: data/eval/ablation/reverend-insanity.json (echotales ablate --out, db: data/db/reverend-insanity.db)*

*Re-scores cached evidence; it does not re-run resolution. 'Scorer would link' is 0 under every condition because the scorer's output is capped below its threshold (docs/results/SCORER_DIAGNOSIS.md), so this table measures the pre-filters. Not answerable from the cache: no-alias-typing, no-self-persona-split, no-truth-status.*


### Table 7 — Baselines vs EchoTales, chapters 1-10 (356 silver mentions)

| System | LLM calls | Prompt tokens | Wall time | Mentions | B3 P (%) | B3 R (%) |
|---|---|---|---|---|---|---|
| Baseline A (long-context) | 1 | 24,302 | 129 s | 10 | 100.0 | 0.2 |
| Baseline B (dual-LLM memorisation) | 177 | 142,835 | 354 s | 133 | 95.4 | 4.6 |
| EchoTales | 0 | — | — | 369 | 100.0 | 78.9 |

*Source: data/eval/baseline_comparison.json (scripts/eval/baseline_comparison.py)*

*Scored against the LLM-DRAFTED SILVER REFERENCE SET -- not human-annotated, no inter-annotator agreement. See docs/results/GOLD_DATASET_README.md. The reference set for this range is surface-trivial, so B3 recall here measures extraction coverage, not coreference quality. EchoTales' calls column counts resolution only; its upstream NER calls are excluded.*


### Table 6a — Gazetteer compounding by window (size 40)

| Window | Gazetteer share of links | n (links in window) |
|---|---|---|
| w0 | 73.5% | 234 |
| w1 | 79.3% | 285 |
| w2 | 85.0% | 301 |
| w3 | 81.7% | 367 |
| w4 | 82.0% | 338 |

*Source: data/eval/compounding/reverend-insanity.json*

*Reported WITH the denominator on purpose: a rate without its n invites reading an early window of four links at 100% as evidence.*

