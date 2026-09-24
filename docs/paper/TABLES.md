# Report tables — generated, do not hand-edit

Regenerate with `python3 scripts/make_paper_artifacts.py`.
Every number traces to a file under `data/eval/`; nothing here is typed by hand.

### Table 2 — Dataset characteristics and structural validation

| File | Records | Silver | Circular | Surface-trivial | Validator |
|---|---|---|---|---|---|
| `reverend-insanity-c1-c5.jsonl` | 343 | 343 | 0 | 100.0% | FAIL |
| `reverend-insanity-hardcases.jsonl` | 89 | 89 | 0 | 63.6% | FAIL |
| `reverend-insanity.jsonl` | 7,879 | 3,457 | 4,422 | 100.0% | FAIL |

*Source: data/eval/validation/*.json (echotales eval --validate-gold)*

*Surface-trivial = share of mentions whose identity is recoverable from the surface string alone. A file near 100% cannot measure an identity resolver; see docs/EVAL_RETRIEVER.md section 1.*


### Table 4 — Coreference metrics, current run

| Metric | P (%) | R (%) | F1 (%) |
|---|---|---|---|
| MUC | 100.0 | 96.8 | 98.4 |
| B3 | 100.0 | 96.3 | 98.1 |
| CEAF-e | 89.0 | 48.9 | 63.1 |
| CoNLL | 86.5 | 86.5 | 86.5 |
| B3 (project variant) | 100.0 | 95.8 | 97.8 |

*Source: data/eval/results/reverend-insanity-1790291709-f0cf184d/metrics.json (gold: data/gold/reverend-insanity.jsonl, db: data/reruns/ner-window-ri.db)*

*Scored against an LLM-derived SILVER reference set, not human gold, with no inter-annotator agreement. See docs/GOLD_DATASET_README.md. B3/MUC are TAUTOLOGICAL on a surface-trivial gold set and must not be quoted as accuracy; CEAF-e is entity-based and is the discriminative one here.*


### Table 5 — Retriever Recall@K by alias type

| Alias type | n | @1 | @5 | @10 | @20 |
|---|---|---|---|---|---|
| **Overall** | 45 | 62.2% | 77.8% | 84.4% | 95.6% |
| EPITHET | 1 | 100.0% | 100.0% | 100.0% | 100.0% |
| RELATIONAL_DEICTIC | 4 | 0.0% | 25.0% | 25.0% | 50.0% |
| RIGID_NAME | 31 | 77.4% | 83.9% | 90.3% | 100.0% |
| TRANSFERABLE_TITLE | 9 | 33.3% | 77.8% | 88.9% | 100.0% |

*Source: data/eval/results/reverend-insanity-1790291711-f0cf184d/metrics.json (gold: data/gold/reverend-insanity-hardcases.jsonl, db: data/reruns/ner-window-ri.db)*

*Scored against an LLM-derived SILVER reference set, not human gold, with no inter-annotator agreement. See docs/GOLD_DATASET_README.md. n is small for the hard alias types; single cases move TRANSFERABLE_TITLE by roughly 11 points and RELATIONAL_DEICTIC by 25.*


### Table 6 — Ablations over 15,796 cached evidence vectors

| Condition | Pairs | Force-link | Blocked | Reached scorer | Scorer would link |
|---|---|---|---|---|---|
| full | 15,796 | 1,318 | 2,888 | 11,590 | 0 |
| no-gazetteer-compounding | 15,796 | 448 | 2,888 | 12,460 | 0 |
| no-declaration | 15,796 | 1,273 | 2,888 | 11,635 | 0 |
| no-name-containment | 15,796 | 1,285 | 2,888 | 11,623 | 0 |
| no-relational-copresence | 15,796 | 1,314 | 2,888 | 11,594 | 0 |
| no-temporal-scoping | 15,796 | 1,318 | 2,888 | 11,590 | 0 |
| no-copresence-blocking | 15,796 | 1,329 | 0 | 14,467 | 0 |
| no-prefilters-at-all | 15,796 | 0 | 0 | 15,796 | 0 |

*Source: data/eval/ablation/reverend-insanity.json (echotales ablate --out, db: data/reruns/ner-window-ri.db)*

*Re-scores cached evidence; it does not re-run resolution. 'Scorer would link' is 0 under every condition because the scorer's output is capped below its threshold (docs/SCORER_DIAGNOSIS.md), so this table measures the pre-filters. Not answerable from the cache: no-alias-typing, no-self-persona-split, no-truth-status.*


### Table 7 — Baselines vs EchoTales, chapters 1-10 (356 silver mentions)

| System | LLM calls | Prompt tokens | Wall time | Mentions | B3 P (%) | B3 R (%) |
|---|---|---|---|---|---|---|
| Baseline A (long-context) | 1 | 24,302 | 129 s | 10 | 100.0 | 0.2 |
| Baseline B (dual-LLM memorisation) | 177 | 142,835 | 354 s | 133 | 95.4 | 4.6 |
| EchoTales | 0 | — | — | 359 | 100.0 | 79.1 |

*Source: data/eval/baseline_comparison.json (scripts/baseline_comparison.py)*

*Scored against an LLM-derived SILVER reference set, not human gold, with no inter-annotator agreement. See docs/GOLD_DATASET_README.md. The gold for this range is surface-trivial, so B3 recall here measures extraction coverage, not coreference quality. EchoTales' calls column counts resolution only; its upstream NER calls are excluded.*


### Table 6a — Gazetteer compounding by window (size 40)

| Window | Gazetteer share of links | n (links in window) |
|---|---|---|
| w0 | 72.8% | 217 |
| w1 | 78.7% | 267 |
| w2 | 84.7% | 288 |
| w3 | 81.8% | 362 |
| w4 | 82.1% | 335 |

*Source: data/eval/compounding/reverend-insanity.json*

*Reported WITH the denominator on purpose: a rate without its n invites reading an early window of four links at 100% as evidence.*

