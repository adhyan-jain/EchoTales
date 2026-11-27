# Per-novel scene-cut induction and presence (2026-11-27)

Code: `packages/pipeline/src/echotales/pipeline/segment/{discontinuity,induce,implicit,scenes,presence,cuts}.py`.
Raw numbers: `data/eval/segment/scene_induction.json`, `data/eval/segment/ri_ch1_check.json`,
induced conventions per novel: `data/eval/segment/conventions/`. Scripts: `scripts/eval/segment_induction_eval.py`,
`scripts/eval/segment_ri_ch1_check.py`.

**Status: the pipeline works end to end and is wired behind `SceneCutConfig`, but the measured accuracy is low.
Do not rely on it for the director yet without the review step.**

## Gold (silver, small)

`data/gold/segment/scene_boundaries.json`: 22 cuts over 25 chapters of 4 novels (RI, LotM, ORV, Pride and Prejudice).
Drafted by reading, not human-verified. "Ambiguous" cuts are neither rewarded nor penalised. Only block indices and
anchors of at most 5 words are stored. Learning uses chapters 1-10 of each novel; chapters above 10 are held out
(RI 21, 45; LotM 26, 36; ORV 24, 33; P&P 12, 22, 40). With 22 cuts, one cut moves a novel's recall by 15-30 points.

## Boundary results (exact match after canonicalisation to the first substantive block)

Baseline `score_top6pct`: the top 6% change-score boundaries per chapter, no markers, no model.
`induced_strong`: only conventions that cut alone. `full`: induced + qwen3:8b judging top candidates + story order.

| Novel | Config | P | R | F1 | Held-out F1 |
|---|---|---|---|---|---|
| RI | baseline | .19 | .57 | .29 | .20 |
| RI | full | .22 | .71 | .33 | .40 |
| LotM | baseline | .05 | .33 | .09 | .00 |
| LotM | full | .13 | .67 | .22 | .36 |
| ORV | baseline | .00 | .00 | .00 | .00 |
| ORV | full | .00 | .00 | .00 | .00 |
| P&P | baseline | .08 | .17 | .11 | .33 |
| P&P | full | .05 | .17 | .07 | .20 |

`induced_strong` is 0/22 everywhere: no convention reached the 50% hit rate.

## Induced conventions (learned on chapters 1-10)

| Novel | Accepted | Support | Hits | Lift | Strength |
|---|---|---|---|---|---|
| RI | none (`……` has support 2) | | | | |
| LotM | `symbol:...` (a one-line ellipsis block) | 14 | 4 | 2.85 | weak; model confirmed 3/3 |
| ORV | `short:w4-8\|title\|none\|inline` (numbered list lines, a false convention) | 3 | 2 | 6.6 | strong |
| P&P | none | | | | |

Honest reading: in this data an ellipsis or symbol block is a pause far more often than a scene break, so a
shape alone cannot mark a cut. The ORV convention is spurious (numbered ranking lines) and the model confirmation
only vetoes. The thresholds (support 3, lift 2.5, strong at hit rate 0.5) were set by this measurement: lift 3.0
rejected LotM's `...`, the only shape that sits on real LotM cuts. They are tuned on 22 cuts and should be re-measured.

## Change score

Top-8 recall of gold cuts by score alone: 13 of 22 (59%); top 12: 16 of 22. Mean percentile of a gold cut is
0.27 (0.5 = chance). Variants tried and dropped: 120-word windows (top-8 recall 9/22), per-chapter percentile
normalisation, single features (topic alone 0.35, location alone 0.50 = no signal). No sentence-embedding model
is installed in .venv (`sentence_transformers` absent), so the topic feature is IDF-weighted cosine on the volume.

## RI ch1 named check (qwen3:8b), 8 of 11 checks passed

- Cut at 31: found (also 35, 49, 73 are false cuts). Labelled NEW_SCENE with relation LATER: wrong; the honest
  label from the text is UNKNOWN until block 80 states "500 years ago", and the story order pass did not use it.
- Cut at 80: missed (ranked 11th by score, not judged). Story order flagged segment 4 as the prior loop; wrong
  (should be segment 0, the cliff), because the segments were wrong.
- Presence: 0-30 Fang Yuan present; 31-79 clan head present, Fang Yuan and Bai Ning Bing referenced only (the v57
  failure is fixed); 80-91 Fang Yuan present. Failure: Fang Zhi was classified present in 31-79.

## What is representable, what is not

A cut carries `cut_type` and `time_relation` (`cuts.SceneCut`), saved in `derived_artifact` (`scene_cuts:<novel>:<ch>`).
A prior loop maps to `SegmentType.REGRESSION_PRIOR_LOOP` with layer `FLASHBACK_OWN`; core enums were not changed.
Unmeasured: unresolved-name presence on novels without mentions (P&P has none), LotM presence beyond a spot check,
the whole-novel run time.
