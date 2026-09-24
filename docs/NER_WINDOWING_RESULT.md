# The NER windowing re-run — measured result

**Run 2026-09-24.** Closes `docs/COMPLETION_PLAN.md` Track 1 item 3, open since
2026-09-23 and described by `HANDOFF.md` as "the measuring re-run. This gates
the most."

The prediction below was **recorded before the run** (COMPLETION_PLAN, written
2026-09-23) and is adjudicated here as recorded — one part of it is refuted.

```bash
echotales --db data/reruns/ner-window-ri.db run --novel reverend-insanity
echotales --db data/reruns/ner-window-ri.db observations --novel reverend-insanity
echotales --db data/reruns/ner-window-ri.db resolve --novel reverend-insanity --capture-evidence
python3 scripts/ner_window_delta.py \
    data/webview-working/reverend-insanity.db data/reruns/ner-window-ri.db
```

Full volume, 199 chapters, `qwen2.5:7b` on a local RTX 4060. **2,806 s (47
min)** for the pipeline, 660 LLM calls, 1.31 M tokens, 0 escalations.

> **The blocker was a misdiagnosis.** Every document recorded this run as
> blocked because "ollama is unreachable from a sandboxed Claude Code shell".
> The daemon was simply not running. `ollama serve` brought it up in **one
> second**. Nothing environmental ever prevented this measurement.

---

## 1. The pre-registered prediction, adjudicated

| # | Prediction (recorded 2026-09-23) | Measured | Verdict |
|---|---|---|---|
| 1 | "CEAF-e recall rises well above 32.1%" | **25.2% → 48.9%** (same gold file, same scorer) | **CONFIRMED** |
| 2 | "mentions per chapter roughly doubles" | 48.1 → 55.1, **+14.6%** | **REFUTED** |
| 3 | "identifiability rises from 45.5%" | 48.8% → **63.0%** | **CONFIRMED** |

**Prediction 2 is refuted, and that is the interesting part.** The fix did not
find many more *mentions*. It found many more *entities*:

| | before | after | change |
|---|---:|---:|---|
| mentions | 9,568 | 10,957 | +14.5% |
| **entities** | **82** | **261** | **+218.3%** |
| mentions past offset 6,000 | 4,626 (48.3%) | 5,353 (48.9%) | +0.6 pp |

The share of mentions past the old 6,000-char cut barely moved, because
`_locate()` already searched the **whole** chapter for every surface form the
model returned. Truncation never hid occurrences of entities the model had
already named; it hid entities appearing **only** past 6,000 characters —
never named, therefore never created, therefore never resolvable.

That is exactly the mechanism `COMPLETION_PLAN` diagnosed, and the entity
count is where it shows. The prediction had the right root cause and the wrong
observable.

---

## 2. The decisive structural check

`COMPLETION_PLAN` named one character in advance. Bai Ning Bing is
gold-annotated at three offsets in chapter 1, all past the truncation point:

| | before | after |
|---|---|---|
| ch1 mentions | **`[]`** | **`[6697, 6814, 8757]`** |
| gold offsets | `[6697, 6814, 8757]` | `[6697, 6814, 8757]` |
| first chapters she appears in | 108, 121, 125, 131, 132 | **1**, 45, 55, 74, 82 |

Three for three, to the character. A named character who was structurally
invisible for 107 chapters is now present from chapter 1.

---

## 3. Coreference metrics, like for like

Same gold file, same scorer, both databases. **Read Section 5 before quoting any of
these.**

| Metric | before | after |
|---|---:|---:|
| B³ precision | 100.0% | 100.0% |
| B³ recall | 95.4% | 96.3% |
| MUC F1 | 97.9% | 98.4% |
| **CEAF-e precision** | 84.1% | **89.0%** |
| **CEAF-e recall** | **25.2%** | **48.9%** |
| **CEAF-e F1** | 38.8% | **63.1%** |
| **CoNLL F1** | 78.1% | **86.5%** |
| gold mentions unresolved | 89 | 67 |

CEAF-e is the metric that moved, and that is coherent rather than lucky: B³
and MUC are mention-linkage metrics a competent string matcher saturates,
while **CEAF-e is entity-based** — it asks whether the system's *clusters*
align one-to-one with the gold's. Missing entities and over-splitting are
exactly what it punishes, and missing entities are exactly what truncation
caused.

---

## 4. Side effects worth recording

**The contradiction detector fires on real data for the first time.**
`docs/STATUS.md` had it as "Experimental — fires on constructed over-merges,
**zero hits on 60 real chapters**". Post-fix: **50 contradictions → 50
splits**. It was not a broken detector; it was starved, exactly as had been
argued for the scorer.

**Entity typing went from mostly unknown to complete.** Adding `item` to the
NER label vocabulary (the second half of EVOLUTION 4.76) moved entity kinds
from `{(unset): 64, ORGANIZATION: 10, LOCATION: 8}` to
`{ITEM: 150, SELF: 91, LOCATION: 12, ORGANIZATION: 8}` — **261/261 typed, 0
unknown** — with 558 mentions now carrying an `item` label that did not exist
in the output before.

**Speaker attribution restructured, not merely improved.** `TURN_TAKING` (478
attributions, previously shown wrong 82.9% of the time) is gone;
`CONTEXTUAL_LLM` (911) and `EXPLICIT` (780 → 1,229) replace it.
`ANONYMOUS_SLOT` fell from 2,930 to 1,920.

**Other detectors now have material to work on:** `TRANSFER=48`, `REVEAL=18`,
`DEATH=105`, `RESURRECTION=5`, `DECEPTION=2`.

**Escalation rate is still 0.0%** — 660 calls, 0 escalations, and only 2
deferrals (0.1%) across 1,532 groups. The bounded-review claim holds; the
bound is currently zero.

---

## 5. What these numbers are NOT

**The B³/MUC figures above are tautological on this gold set and must not be
quoted as accuracy.** The silver subset of `reverend-insanity.jsonl` is 1,816
mentions over **23 distinct surfaces**, 100% recoverable by grouping on the
surface string (`docs/EVAL_RETRIEVER.md` Section 1). Any exact-string matcher scores
~100% precision on it. The pre-fix triple P=100.0/R=94.6/F1=97.2 is
byte-identical to the headline `EVOLUTION.md` 4.74 retracted.

CEAF-e is the one metric in that table with real discriminative power here,
because entity-level clustering is not recoverable from surface strings alone.
The honest claim is therefore narrow and specific:

> **The NER windowing fix roughly doubled entity-level clustering agreement
> (CEAF-e recall 25.2% → 48.9%) and tripled the entity inventory (82 → 261) on
> Reverend Insanity, measured against an LLM-derived silver reference set.**

Not "EchoTales achieves 98% B³".

---

## 6. The finding that reorders the scorer question

`echotales ablate` re-run against the post-fix evidence cache, now **15,796**
pairs (was 10,058, +57%):

```
full                      force-link= 1,318 (8.3%)  reached-scorer= 11,590  scorer-would-link= 0
no-gazetteer-compounding  force-link=   448 (2.8%)  reached-scorer= 12,460  scorer-would-link= 0
no-temporal-scoping       force-link= 1,318 (8.3%)  blocked= 2,888          scorer-would-link= 0
no-copresence-blocking    force-link= 1,329 (8.4%)  blocked=     0          scorer-would-link= 0
no-prefilters-at-all      force-link=     0 (0.0%)  reached-scorer= 15,796  scorer-would-link= 0
```

**`scorer-would-link = 0` under every condition, including the one where all
15,796 pairs reach it.**

This settles the open A/B/C/D/E question in `docs/COMPLETION_PLAN.md`:

- **(A) retrieval starvation — REFUTED as the explanation.** The starvation
  hypothesis was reasonable while the pipeline could not see half of every
  chapter. It now sees all of it, the evidence cache is 57% larger, the entity
  count has tripled — and the scorer still settles nothing. Starvation was
  real and is fixed; the scorer's inertness survived it.
- **(B) + (C) + (D) — supported.** The evidence features cannot express the
  decision, the hard pre-filters carry all 1,318 force-links (1,231 of them
  gazetteer, 93%), and the scorer is unnecessary to this corpus as built.

Two further ablation results reproduce post-fix:

- **The gazetteer carries the system.** Disabling it drops force-links from
  1,318 (8.3%) to 448 (2.8%) — it accounts for **66%** of all links.
  `NAME_CONTAINMENT` rises 33 → 385 as it stops being short-circuited.
- **Temporal blocking fires on zero pairs.** `no-temporal-scoping` changes
  *nothing*: `blocked` stays at 2,888, all of it from
  `co_presence_violation`. The temporal validity gate is inert on this corpus,
  now confirmed on a 57% larger sample.

---

## 7. Retriever, post-fix

Against the hardcases silver set (the only non-trivial evaluation set):

| Alias type | n | @1 | @5 | @10 | @20 | vs pre-fix @10 |
|---|---:|---:|---:|---:|---:|---|
| Overall | 45 | 62.2% | 77.8% | 77.8% | 91.1% | 75.0% → 77.8% |
| RIGID_NAME | 31 | 77.4% | 83.9% | 83.9% | 96.8% | 83.3% → 83.9% |
| TRANSFERABLE_TITLE | 9 | 33.3% | 77.8% | **77.8%** | 100% | 66.7% → **77.8%** |
| RELATIONAL_DEICTIC | 4 | 0.0% | 25.0% | 25.0% | 25.0% | 25.0% → 25.0% |

**The gate still FAILS**, at 77.8% against an 80% threshold — but by 2.2
points rather than 13.3. `RELATIONAL_DEICTIC` did not move at all and is the
weakest part of the system by a wide margin (n=4; directional only).

---

## 8. Status changes this run justifies

- Mention detection: **Partial → Verified** for the truncation defect
  specifically. Effect measured, prediction adjudicated, one part refuted.
- Contradiction detection: **Experimental → Verified as firing** (50 real
  contradictions; whether each is *correct* is unreviewed).
- Scorer: stays **Experimental**, and the starvation defence is now closed.
- Speaker attribution: 45.5% (Section 4.60) → **63.0%**, on a restructured tier mix.
- `docs/STATUS.md`'s standing truth constraint — "nothing below may say or
  imply mention recall, CEAF-e, or speaker attribution improved" — is
  **discharged**. They improved; this document is the measurement.
