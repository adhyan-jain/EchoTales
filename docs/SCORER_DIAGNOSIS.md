# Scorer diagnosis — why the learned scorer links nothing

**Measured 2026-09-25** on `data/reruns/ner-window-ri.db` (post-NER-fix full
volume, 15,796 cached `(mention, candidate)` evidence vectors). No scorer code
was changed to produce this. SILVER — LLM-derived reference set (Claude), not
human gold; no IAA.

```bash
python3 scripts/scorer_diagnosis.py     # -> data/eval/scorer_diagnosis/{cases,candidates}.csv, summary.json
python3 scripts/scorer_fit_probe.py     # -> data/eval/scorer/{fit_probe,fitted}.json
```

The starvation hypothesis was closed earlier (`docs/NER_WINDOWING_RESULT.md`):
the scorer links nothing on a 57% larger cache. This document asks what does
explain it, and computes each candidate cause before choosing.

**Diagnosis: F — multiple causes, with one structural root.** In order of
weight: **E/D (threshold unreachable because features are dead)**, then
**C (calibration)**, with **A (detection, upstream of retrieval)** dominating
the hard cases. Ranking (**B**) is *not* the problem.

---

## 1. Ranking works

Every silver mention whose correct candidate appears in the evidence cache:

| | |
|---|---:|
| Gold candidate present and scored | 103 |
| **Gold ranked first by the scorer** | **97 (94.2%)** |
| Gold ranked second | 6 |
| AUC, gold score vs best-wrong score | 0.80 |
| Median margin gold − best wrong | +0.044 |

**B (ranking failure) is refuted.** The scorer orders candidates correctly.

## 2. The threshold is unreachable by arithmetic — the root cause

| Weighted feature | Weight | Distinct values over 15,796 pairs | Range |
|---|---:|---:|---|
| `surface_similarity` | 1.2 | 560 | 0.0 – 1.0 |
| `context_embedding_similarity` | 2.0 | 697 | 0.0 – 1.0 |
| `speech_partner_compatibility` | 1.5 | **1** | **always 0.0** |
| `temporal_validity` | 1.0 | **1** | **always 1.0** |
| `first_attested_soft_prior` | 0.4 | 2 | −1.0 or 0.0 |

With bias −4.0, the best achievable logit is
`−4.0 + 1.2 + 2.0 + 0 + 1.0 + 0 = 0.200`, so **the maximum possible probability
is 0.550**. Linking at 0.80 needs a logit of 1.386. A pair with perfect surface
*and* perfect context similarity cannot link. The observed maximum, 0.527, sits
just under the arithmetic ceiling.

So the ceiling is not weak evidence (D in the loose sense) and not a
miscalibrated threshold in isolation (E): **three of five weighted features
carry no information on this corpus**, which removes 2.9 logits of headroom the
threshold was implicitly budgeted against. `speech_partner_compatibility` never
fires; `temporal_validity` never varies (consistent with the ablation finding
that temporal blocking fires on zero pairs).

Across *all* eleven evidence features, seven have gold-vs-wrong AUC of exactly
0.50 — they never vary: `declaration_match`, `name_containment`,
`speech_partner_compatibility`, `temporal_validity`,
`audience_scope_compatibility`, `relationship_deictic_resolution`,
`first_attested_soft_prior`. The ones that do vary separate strongly:
`surface_similarity` 0.998, `gazetteer_exact_match` 0.990,
`context_embedding_similarity` 0.813.

## 3. Every labelled decision is taken before the scorer

The 103 gold candidates' pre-filter verdicts: **101 FORCE_LINK, 2 BLOCK,
0 SCORE.** No labelled pair in the silver corpus has its correct candidate
reach the scorer. The scorer's operating region — pairs the pre-filters leave
undecided — contains **no labelled examples at all**.

This is the blocker for Steps 4 and 5 of the completion plan, and it is a data
blocker, not a modelling one.

## 4. Hard cases mostly never become mentions

| Hard-case outcome (89 records) | n |
|---|---:|
| **Mention never detected** (no system span overlaps the gold span) | **59** |
| Gold identity has no silver support elsewhere (unmapped) | 13 |
| Detected but resolved without scoring | 13 |
| Gold pre-filter BLOCK | 1 |
| Gold pre-filter FORCE_LINK | 2 |

By category, detection failure is where the project claims difficulty:
`relational_deictic` 25 of 29 undetected, `title_transfer` 16 of 17. This
reconciles an apparent contradiction with `docs/EVAL_RETRIEVER.md`, where
TRANSFERABLE_TITLE recall@10 is 88.9%: that evaluation hands the gold span
straight to the retriever and so bypasses detection. **Retrieval is adequate
when given the span; the mention layer rarely produces the span.**

### 4a. What the resolver decides for the hard cases it *does* detect — 2026-09-25

> **Canonical v1 run (EVOLUTION 4.90):** 30 detected, **24 of 24** decidable
> linked correctly, 0 wrong, 58 undetected; the recovered case is "Wang Er"
> (ch175, disguise). The failure taxonomy of the remaining 58 is in
> `docs/FINAL_EVIDENCE_TABLE.md` Section 3. The table below is the 4.84
> database and is kept as measured.

`scripts/hardcase_resolution.py` → `data/eval/hardcase_resolution.json`. Uses
the coreference scorer's own identity mapping, and reports two alignments:
**overlap** (the rule above, which reproduces the 59 exactly) and **exact**
(the scorer's surface-and-offset rule, what B³/MUC actually see).

| Category | n | not detected (overlap) | correct | wrong | unresolved | gold unmapped |
|---|---:|---:|---:|---:|---:|---:|
| **All** | 88 | 59 | **23** | **0** | 0 | 6 |
| reveal | 17 | 7 | 10 | 0 | 0 | 0 |
| disguise | 13 | 2 | 9 | 0 | 0 | 2 |
| body_change | 11 | 8 | 3 | 0 | 0 | 0 |
| title_transfer | 17 | 16 | 1 | 0 | 0 | 0 |
| relational_deictic | 29 | 25 | 0 | 0 | 0 | 4 |

- **Every decidable detected hard case is linked correctly: 23 of 23, no wrong
  links, no deferrals.** That fits non-negotiable 9 (precision over recall):
  the resolver is precise on what it sees. The loss is entirely upstream.
- Under **exact** alignment only 20 are detected (68 not detected): nine
  hard-case spans are found with different boundaries (e.g. a longer name
  span), so the coreference metrics undercount detection slightly relative to
  this table.
- The 6 "gold unmapped" are detected, but their gold identity has no system
  entity, so correct/wrong cannot be decided. They are not counted as correct.
- n is small and SILVER. "23/23" has a 95% Wilson lower bound of about 86%;
  it does not establish a precision figure for the hard types in general.

## 5. Would fitting help? Measured, not assumed

`scripts/scorer_fit_probe.py` fits the existing `ScoringModel` (logistic, no new
architecture) on a **chronological** split — train ≤ ch38 (920 pairs, 68
positive), calibrate ch39–50 (160), test ch51+ (190 pairs, 19 mentions).

| Scorer | LINK coverage | DEFER | NEW | False-link rate |
|---|---:|---:|---:|---:|
| Raw (default weights) | 0.0 | 0.0 | 1.0 | — |
| Fitted | 0.0 | 0.0 | 1.0 | — |
| Fitted + Platt-calibrated | 0.0 | 0.0 | 1.0 | — |

The fit barely moves the model (bias −4.09 vs −4.00; weights within ±0.3 of
defaults): with two informative features and a 7% positive rate, logistic loss
has nothing to push against. **Fitting the existing model does not fix the
scorer**, and — per Section 3 — even a scorer that did link could not be
evaluated where it matters.

## 6. What this justifies, and what it does not

**Not justified, and not built:**
- A fitted or recalibrated production scorer. The probe shows no gain, and
  there are no labels in the scorer's operating region to validate one.
- A bounded LLM investigator for ambiguous cases (completion-plan Step 5).
  Its accuracy "before and after investigation" cannot be measured without
  labelled ambiguous cases, and 67% of the hard cases never reach candidate
  generation at all, so an investigator over candidates would not see them.
  Building it would add architecture to make a documentation claim true.

**Justified by this evidence, and recorded as the next real work:**
1. **Mention detection for relational/deictic and title spans.** This is
   where the hard cases are lost — before retrieval, scoring, or any
   investigator.
2. **Either retire the three dead features or make them fire.**
   `speech_partner_compatibility` depends on speaker attribution reaching the
   resolver; `temporal_validity` needs non-MAIN facts, of which the corpus has
   none. Until then the 0.80 threshold should be recomputed from the achievable
   range, or the decision made comparative (rank + margin), since ranking is
   94% correct.
3. **Labels where the scorer operates.** A blind-annotation pass
   (`echotales annotate`) restricted to SCORE-verdict pairs is the only route
   to evaluating any change in this area.

**Honest summary for the report.** The resolver's quality comes from its
deterministic pre-filters. The learned scorer ranks well but is arithmetically
unable to link, because the features its threshold was designed around are
inert on this corpus; fitting does not rescue it; and the hard cases are lost
upstream, at mention detection.
