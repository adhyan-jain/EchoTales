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

*Source: data/eval/results/reverend-insanity-1790239909-c2c98d76/metrics.json*

*Scored against an LLM-derived SILVER reference set, not human gold, with no inter-annotator agreement. See docs/GOLD_DATASET_README.md. B3/MUC are TAUTOLOGICAL on a surface-trivial gold set and must not be quoted as accuracy; CEAF-e is entity-based and is the discriminative one here.*


### Table 5 — Retriever Recall@K by alias type

| Alias type | n | @1 | @5 | @10 | @20 |
|---|---|---|---|---|---|
| **Overall** | 1765 | 99.9% | 100.0% | 100.0% | 100.0% |
| RIGID_NAME | 1765 | 99.9% | 100.0% | 100.0% | 100.0% |

*Source: data/eval/results/reverend-insanity-1790239909-c2c98d76/metrics.json*

*Scored against an LLM-derived SILVER reference set, not human gold, with no inter-annotator agreement. See docs/GOLD_DATASET_README.md. n is small for the hard alias types; single cases move TRANSFERABLE_TITLE by roughly 11 points and RELATIONAL_DEICTIC by 25.*


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

