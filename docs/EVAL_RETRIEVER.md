# Retriever evaluation — Recall@K by alias type

**Measured 2026-09-24.** The first per-alias-type recall@K this project has
ever produced against annotated data. Every number here is scored against an
**LLM-derived silver reference set, not human gold, with no IAA** — see
`docs/GOLD_DATASET_README.md`.

Reproduce:

```bash
echotales --db data/webview-working/reverend-insanity.db eval \
    --novel reverend-insanity \
    --gold data/gold/reverend-insanity-hardcases.jsonl
```

Machine-readable output lands in `data/eval/results/<run_id>/metrics.json`
under `metrics.silver.recall_at_k`, alongside the commit, seed and platform.

---

## 1. Read this before any number below

**A coreference gold set whose partition can be reproduced by grouping on the
surface string measures string matching, not identity resolution.**

Not hypothetical. Measured across this corpus:

| File | scorable mentions | distinct surfaces | identities | **surface-trivial** | alias types |
|---|---:|---:|---:|---:|---|
| `reverend-insanity.jsonl` (silver subset) | 1,816 | **23** | 20 | **100.00%** | RIGID_NAME only |
| `reverend-insanity-c1-c5.jsonl` | 308 | 34 | 26 | **100.00%** | RIGID_NAME only |
| `reverend-insanity-hardcases.jsonl` | 88 | 44 | 26 | **63.64%** | 4 types |

The first two encode the assertion *"these ~25 strings denote these ~20
people, one-to-one."* Any exact-string matcher reproduces them perfectly.

**Consequence, stated plainly:** scoring the system against
`reverend-insanity.jsonl`'s silver subset returns **B³ P=100.0%, R=94.6%,
F1=97.2%** — byte-identical to the headline `EVOLUTION.md` 4.74 retracted.
4.74 withdrew it for being *circular* (gold drafted from the pipeline's own
`mention` table). This is a **second, independent reason the same number is
meaningless**: even the non-circular subset is a tautology, because the task
it encodes is trivially satisfiable. The figure was doomed twice over, and it
must not reappear under a "silver" label as though relabelling fixed it.

This is now an automated check
(`eval/validate_gold.py::_surface_triviality`) that **fails** any file at ≥99%
and warns at ≥90%, so the mistake cannot be made silently again.

**Therefore `reverend-insanity-hardcases.jsonl` (89 records) is the only
evaluation set in this corpus that measures anything** — and even it is 64%
trivial, so roughly 32 of its mentions carry the actual signal.

---

## 2. Results — hardcases, silver tier, pre-re-run database

44 retrieval cases (18 of 62 identities did not map to a system `target_id`).

| Alias type | n | @1 | @5 | @10 | @20 |
|---|---:|---:|---:|---:|---:|
| **Overall** | 44 | 63.6% | 75.0% | 75.0% | 88.6% |
| RIGID_NAME | 30 | 80.0% | 83.3% | 83.3% | 93.3% |
| TRANSFERABLE_TITLE | 9 | 33.3% | 66.7% | 66.7% | 88.9% |
| RELATIONAL_DEICTIC | 4 | 0.0% | 25.0% | 25.0% | 50.0% |
| EPITHET | 1 | 100% | 100% | 100% | 100% |

**Gate verdict: FAIL.** `retriever_eval.GATE` requires recall@10 ≥ 80% on
`TRANSFERABLE_TITLE`; measured **66.7%**. The gate's own message is the right
reading: *candidate retrieval is the research problem; scorer tuning is
premature.*

### Honest caveats

- **n is small.** 9 TRANSFERABLE_TITLE and 4 RELATIONAL_DEICTIC cases. One
  case moves TRANSFERABLE_TITLE by 11 points and RELATIONAL_DEICTIC by 25.
  Directional, not precise; no confidence interval rescues this n.
- **EPITHET n=1 is not a measurement.** Printed because omitting a row is
  worse than printing one that declares its own n.
- **18 of 62 identities unmapped.** `build_gold_retrieval_cases` maps a gold
  identity to a system `target_id` by majority vote and drops what it cannot
  map. Unmapped identities are disproportionately the hard ones, so the true
  figures are likelier below these than above.
- Scored against the **pre-re-run** canonical database. The post-NER-windowing
  comparison follows separately.

---

## 3. A documented claim this refutes

`docs/STATUS.md` "Stale claims found this pass" #2, and `EVOLUTION.md` Section 4.69,
conclude that the TRANSFERABLE_TITLE recall@k gate:

> "cannot produce a number on this novel no matter how much more gets
> annotated."

**It can, and the table above is one.** Section 4.69 was correct about its actual
subject: `generate_gold.py` only admits mentions carrying a resolved
`target_id`, and real TRANSFERABLE_TITLE mentions on RI correctly resolve to
`None` by design (non-negotiable #9), so gold derived *that way* can never
contain them. It does not generalise to **hand-drafted** gold.
`reverend-insanity-hardcases.jsonl` was written by reading chapter text, and
its 17 TRANSFERABLE_TITLE records carry identities that map to system targets
by majority vote.

What actually blocked the measurement was mechanical, not structural: `eval`
had **no `--gold` flag**, so the corpus's one alias-diverse file was
unreachable from the CLI, and the file itself was **gitignored**. Both fixed
2026-09-24.

`STATUS.md` needs correcting: the gate is measurable, it was measured, and it
**fails**.

---

## 4. Two defects in the measurement path, fixed here

1. **The retriever was evaluated with no context.** `commands.py` built its
   evaluation retriever by calling `observe(..., "", ...)` for every mention,
   zeroing the 0.35 contextual half of `CandidateRetriever.retrieve`'s
   0.65/0.35 lexical/contextual blend. Every recall number the tool would have
   printed described a **lexical-only retriever no production path uses**. Now
   supplied with the mention's real block text.
2. **The gold recall@k block never executed.** It sat inside
   `if confirmed.mentions:`, and confirmed gold has been zero corpus-wide since
   4.74. The only recall figure `eval` ever printed was the self-retrieval
   smoke test, which hardcodes `RIGID_NAME` and reports 100% at every K by
   construction. Now runs on the silver tier.

---

## 5. What this says about the scorer

`EVOLUTION.md` 4.78 established that the learned scorer settles **0 of 880**
links, its maximum output over 10,058 real pairs being 0.527 against a 0.80
threshold. The open question was *why*: starvation (A), insufficient evidence
features (B), hard rules dominating (C), or the scorer being unnecessary (D).

These retrieval numbers bear on (A). At recall@10 of 66.7% for
TRANSFERABLE_TITLE and 25.0% for RELATIONAL_DEICTIC, **the correct candidate is
frequently not in the list the scorer ever sees**. A scorer cannot rank an
entity retrieval never returned, so no amount of reweighting addresses those
cases.

This does not settle the question. It establishes that retrieval is a real,
measured bottleneck on exactly the alias types the project is about, and that
fixing the scorer first would have been the wrong order. The ablation re-run
against the post-NER-fix evidence cache is what separates the remaining
alternatives.


---

## 6. Re-measured with production-exact context — 2026-09-25

Section 2 was measured before commit `ce622aa`, when the evaluation retriever
received each mention's *block* text. Production (`resolve/runner.py`) gives
it `_context_for(mention, chapter.story_text)` — a fixed window around the
surface in the whole chapter. The evaluation now calls that same function.

| Alias type | n | @1 | @5 | @10 | @20 |
|---|---:|---:|---:|---:|---:|
| **Overall** | 45 | 62.2% | 77.8% | **84.4%** | 95.6% |
| RIGID_NAME | 31 | 77.4% | 83.9% | **90.3%** | 100% |
| TRANSFERABLE_TITLE | 9 | 33.3% | 77.8% | **88.9%** | 100% |
| RELATIONAL_DEICTIC | 4 | 0.0% | 25.0% | 25.0% | 50.0% |
| EPITHET | 1 | 100% | 100% | 100% | 100% |

**Gate: PASS** — TRANSFERABLE_TITLE recall@10 88.9% against 80%. That is
one case (7/9 → 8/9) and must be reported with its n.

**This does not change the headline finding.** Retrieval is adequate *when
handed the span*; `docs/SCORER_DIAGNOSIS.md` Section 4 shows 16 of 17
title-transfer mentions and 25 of 29 relational/deictic mentions are never
detected as mentions at all, so in the real pipeline they never reach
retrieval. Relational/deictic retrieval (25% @10) remains weak even when given
the span.
