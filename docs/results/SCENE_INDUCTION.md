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

# v2 (2026-11-28): HANDOFF, work in progress (not finished, no v2 numbers yet)

Branch `worktree-agent-af27213abf94196be`, based on v1 commit 7670e1b. The agent stopped at the context limit before
the measured v2 table existed. Nothing below is a result unless a number is given.

## Done
- **ORV score 0, root cause (measured):** not an ingest bug and not wrong gold. Ingest keeps `* * *` as a NON_DIEGETIC
  block. In ORV chapters 1-10 every `* * *` is the chapter-final marker (last block); interior separators first appear
  in chapter 14 (22 of them in ch 14-40, almost all real cuts, "After a while..."). So induction on chapters 1-10 sees no
  interior separator and cannot learn it; v1's only accepted convention was numbered list lines. Fix direction: the
  whole-chapter model sees separators as ordinary numbered blocks; also consider a learn range wider than 10 for novels
  whose first volume has no interior separators.
- `segment/embed.py` (nomic-embed-text via ollama, cached, `get_embedder()` returns None when down) and
  `discontinuity.score_chapter(..., embedder=)` (TF-IDF fallback, `EMBED_TOPIC_SCALE` 2.5 untuned). `nomic-embed-text` is pulled.
- `segment/llm_segment.py`: whole-chapter scene listing (numbered blocks cut to 40 words, windows of 60 with overlap 15,
  cut trusted from the window where it is most interior, same-place merge), `segment_chapter_llm(chapter, llm)`.
- `scenes.py`: `combine_llm_cuts` (accept an LLM cut when its snapped boundary score >= p75 of the learn chapters, or enough
  model votes), `analyse_chapter_scenes(..., method="whole_chapter"|"per_boundary", embedder=, llm_scenes=, accept_score=)`,
  `SceneCutConfig.method/embedder`, `prior_loops_from_scenes`.
- **Presence (Fang Zhi):** cause = the speaker attribution at RI block 55 names Fang Zhi (an elder says "Fang Zhi's side has
  a young genius"); `speaks` short-circuited the model. Fix in `presence.py`: a speaker block that is also a DIALOGUE_REFERENCE
  block of the same entity does not count as speaking; the no-model fallback counts a narration mention only when the name is
  a clause subject outside a complement clause (spaCy dependency parse), for most of its mentions. With no model: clan head
  present; Fang Yuan, Fang Zhi, Bai Ning Bing referenced. Not yet re-verified with the model.
- Owner gold for RI ch1 (`data/gold/segment/ri_ch1_owner.json`): cuts exactly {31, 79}; scenes 0-30 (prior loop), 31-78, 79-89.
  `scripts/eval/segment_ri_ch1_check.py` updated to these expectations (not run).
- Gold: `data/gold/segment/scene_boundaries.json` now has a `dbs` map, RI ch1 corrected (cut 80 -> 79), new labels for RI 4,6-10,12,14,
  LotM 5,6,9,10, ORV 14-40 (13 new cuts around separators). Still 43 cuts over 4 novels; the target of 60 over 5 is NOT met.
  `scripts/eval/segment_gold_add.py` holds the new labels. Coverage "candidates" means only separators/top-scored boundaries were read.
  Second-pass re-read of labels NOT done. `negatives` are stored but not yet used by the scorer.
- `scripts/eval/segment_pd_to_scratch.py` builds a scratch DB from a Gutenberg txt (A Study in Scarlet, `data/scratch/segment/a-study-in-scarlet.db`,
  chapters 1-14, Part II starts at 8; plan: learn on 1-7). No Scarlet labels written yet.

## Measured so far (qwen3:8b, first prompt, TF-IDF, v1 gold of 22 cuts; `data/scratch/segment/v2_run1.log`)
The model over-segments: LLM cuts accepted unfiltered give precision 0.03-0.08 (RI learn P .05, LotM learn P .03). Held-out F1 with the
p90 score filter: LotM .36, ORV .20, RI 0, P&P 0. These are WORSE than the 0.6 target. After this run the prompt got a scene-length prior and a
same-place merge (see `llm_segment.py`); that version was started as `v2_run2` (learn split, qwen3:8b and gemma2:9b) but had not finished
(GPU lock held by other agents).

## Remaining
1. Run `flock /tmp/echotales-gpu.lock python scripts/eval/segment_v2_eval.py --models qwen3:8b gemma2:9b --split learn --out data/scratch/segment/v2_run2.json`
   (needs `PYTHONPATH=packages/core/src:packages/pipeline/src`), read per-chapter cut counts in `data/scratch/segment/llmcache/`, fix over-segmentation on learn
   chapters only, then run `--split all` for held-out and write `data/eval/segment/scene_induction_v2.json`.
2. Reach 60+ cuts over 5+ novels (add Scarlet via `cand.py`-style reading, P&P), second-pass re-check every label, add the model comparison.
3. Run the RI ch1 check with the model; check prior-loop on segment 0 (needs the order pass over a multi-window chapter, `resolve_story_order`).
4. Add unit tests with a fake LLM for `llm_segment`, `combine_llm_cuts`, the presence fix, embedder fallback; run the full suite (baseline ~3210) and ruff.
5. Fill in the v2 tables here and the RI ch1 verdict.

# v2.1 (2026-11-28): HANDOFF, GPU-blocked, no accuracy numbers yet

Branch `worktree-agent-a93507cfba5b73f84`. Nothing below is a result unless a number is given.

## Done
- **New cutter, `segment/place_tags.py`:** the model tags each non-heading block (windows of 25, 35 words shown, num_ctx 4096,
  qwen3:8b stays 100% GPU) with `place`, `time_shift` (SAME/LATER/EARLIER) and `time_anchor`, reusing the previous place string
  while unchanged. Code then decides cuts: place distance across a block (mean over 3 blocks each side; nomic embedding, or token
  Jaccard when no embedder), peak picking, threshold, `min_gap`, optional cap = `cap_rate` x blocks (per-novel learned prior), and a
  time-jump score. `scenes_from_tags` returns `LLMScene`s so `combine_llm_cuts`, prior-loop and presence code are unchanged.
  `SceneCutConfig.method` now defaults to `"place_tags"` (`place_params` optional); `runner.py` passes method/embedder/params through.
  Not implemented: approach 2 (constrained top-K choice); try it if the tag cutter fails the learn split.
- **Gold:** 60 cuts over 5 novels (RI, LotM, ORV, P&P, A Study in Scarlet). Scarlet read in full (14 chapters, second pass over every
  cut/ambiguous boundary); `learn_max` in the gold file makes Scarlet learn on chapters 1-7, held-out 8-14 (Part II, new place and time).
  P&P gained 5 chapters of candidate-level labels. Script: `scripts/eval/segment_gold_add2.py`.
- **Scripts:** `segment_tag_run.py` (tags gold chapters into `data/scratch/segment/tagcache/<model>/`, GPU lock held per chapter),
  `segment_tag_tune.py` (grid search on LEARN chapters from the caches, then `--split held --params`; reports false cuts on the labelled
  hard `negatives` as `hard_negative_false_cuts`; embedding and token distance both run).
- **Tests:** `packages/pipeline/tests/test_scene_v2.py` (21, fake LLM: llm_segment merge, combine_llm_cuts, place tags, embedder
  fallback, presence heuristic and parser). Ruff clean.

## Why no numbers
The shared GPU lock was contended by 3 other agents; a chapter took 7-13 minutes mostly waiting (RI ch1-5 tagged, 5 of ~50 learn
chapters). Scratch DBs are not in git: copy `data/scratch/segment/` from the previous worktree. Only RI ch1 was inspected: qwen3:8b
tagged blocks 0-30 place "unknown", found the cut at 31, MISSED 79 (kept the same mountain), and marked LATER on many blocks, so
expect `time_weight` to tune to about 0 and the prompt to need the withheld-identity / parallel-action rule made stronger (or approach 2).

## Remaining (in order)
1. `PYTHONPATH=packages/core/src:packages/pipeline/src python scripts/eval/segment_tag_run.py --model qwen3:8b --split learn` (resumes).
2. `segment_tag_tune.py --models qwen3:8b --split learn`; fix the prompt on learn chapters only.
3. Tag `--split held`, then `segment_tag_tune.py --split held --params <best>`; gemma2:9b only when `ollama ps` shows 100% GPU at
   num_ctx 4096 (it spilled 9-21% to CPU). Write `data/eval/segment/scene_induction_v2.json`.
4. RI ch1 check: `segment_ri_ch1_check.py` still uses the v1 call; pass `method="place_tags"` and `place_params`; expect cuts {31, 79},
   prior loop on segment 0, ritual cast. Worktrees have no `.env`: CLI runs need `ECHOTALES_MODEL_BACKEND=ollama ECHOTALES_LLM_MODE=local`.
5. Fill the v2 per-novel, model-comparison and RI ch1 tables.

# v2.1 measured results (2026-11-28, qwen3:8b, prompt p4, rule cutter `both=True, min_gap=1`)

Parameters were chosen on the learn chapters only; held-out is report-only (70 chapters tagged, tag cache
`data/scratch/segment/tagcache/qwen3_8b_p4/`). Machine-readable: `data/eval/segment/scene_induction_v2.json`.
Baseline = v1 "full" row of `data/eval/segment/scene_induction.json` (held-out column).

| novel | split | chapters | TP | FP | FN | P | R | F1 | v1 held F1 |
|---|---|---|---|---|---|---|---|---|---|
| reverend-insanity | learn | 10 | 4 | 6 | 4 | .40 | .50 | .44 | |
| lord-of-the-mysteries | learn | 10 | 5 | 4 | 2 | .56 | .71 | .63 | |
| omniscient-readers-viewpoint | learn | 2 | 0 | 0 | 1 | 0 | 0 | 0 | |
| pride-and-prejudice | learn | 5 | 0 | 1 | 4 | 0 | 0 | 0 | |
| a-study-in-scarlet | learn | 7 | 2 | 5 | 4 | .29 | .33 | .31 | |
| **pooled** | learn | 34 | 11 | 16 | 15 | .41 | .42 | .42 | |
| reverend-insanity | held | 4 | 2 | 1 | 1 | .67 | .67 | .67 | .40 |
| lord-of-the-mysteries | held | 2 | 0 | 6 | 3 | 0 | 0 | 0 | .36 |
| omniscient-readers-viewpoint | held | 16 | 1 | 9 | 14 | .10 | .07 | .08 | 0 |
| pride-and-prejudice | held | 7 | 0 | 5 | 4 | 0 | 0 | 0 | .20 |
| a-study-in-scarlet | held | 7 | 1 | 4 | 8 | .20 | .11 | .14 | n/a |
| **pooled** | held | 36 | 4 | 25 | 30 | .14 | .12 | .13 | |

Hard negatives falsely cut: learn 2 of 38, held 1 of 11.

**Verdict: the tag cutter does not meet the 0.6 target.** Held-out F1 is 0.13 pooled, driven by recall (30 of 34 gold cuts missed,
mostly ORV where the gold is dense). It beats v1 only on RI and ORV (tiny counts); it is worse on LotM and P&P held-out. The
learn-to-held drop (0.42 to 0.13) shows the prompt and `min_gap` do not transfer.

## RI ch1 named check (`scripts/eval/segment_ri_ch1_check.py`): 7 of 12 pass
Cuts found {31, 35}, expected {31, 79}. Passing: Fang Yuan present in 0-30 and 79-89; clan head present in 31-78; Bai Ning Bing and
Fang Zhi referenced and not present. Failing: cuts exactly {31, 79}; Fang Yuan not present in 31-78 (he is listed present);
Fang Yuan referenced in 31-78; prior-loop flag on segment 0 (none flagged); cut 31 time relation (tagged LATER, not EARLIER).

Diagnosis: the tags are wrong, not the cut rule. The model re-labels the continuous clan scene: place changes from "Qing Mao
Mountain" to "Gu Yue Village" at block 36 with time LATER, which fires a cut near 35, and at 75-79 the place becomes "the third
floor of the garret" with time SAME, so the real cut at 79 is never both-place-and-time. The "500 years ago" anchor lands on block
80 instead of the prior-loop segment 0. No fix applied: a general fix was not clearly justified and tuning on RI ch1 is excluded.

# v3 measured results (2026-11-28, qwen3:8b, judge prompt j1, candidate union + pairwise boundary judge)

Rule chosen on the 34 learn chapters only, from an interpretable grid (`data/scratch/segment/v3_rule.json`): **place alone, min_gap 5**
(cut when the judge says `same_location = no`, suppress cuts within 5 blocks of the previous one). Held-out was judged once after the
prompt was frozen. Machine-readable: `data/eval/segment/scene_induction_v3.json`. Script: `scripts/eval/segment_v3_eval.py`.

| novel | split | TP | FP | FN | P | R | F1 | v1 held F1 | v2.1 held F1 |
|---|---|---|---|---|---|---|---|---|---|
| reverend-insanity | learn | 4 | 24 | 4 | .14 | .50 | .22 | | |
| lord-of-the-mysteries | learn | 5 | 38 | 2 | .12 | .71 | .20 | | |
| omniscient-readers-viewpoint | learn | 0 | 8 | 1 | 0 | 0 | 0 | | |
| pride-and-prejudice | learn | 0 | 8 | 4 | 0 | 0 | 0 | | |
| a-study-in-scarlet | learn | 2 | 13 | 4 | .13 | .33 | .19 | | |
| **pooled** | learn | 11 | 91 | 15 | .11 | .42 | .17 | | |
| reverend-insanity | held | 1 | 12 | 2 | .08 | .33 | .125 | .40 | .67 |
| lord-of-the-mysteries | held | 2 | 11 | 1 | .15 | .67 | .25 | .36 | 0 |
| omniscient-readers-viewpoint | held | 7 | 141 | 8 | .05 | .47 | .086 | 0 | .08 |
| pride-and-prejudice | held | 1 | 5 | 3 | .17 | .25 | .20 | .20 | 0 |
| a-study-in-scarlet | held | 1 | 17 | 8 | .06 | .11 | .074 | n/a | .14 |
| **pooled** | held | 12 | 186 | 22 | .06 | .35 | .103 | | .13 |

Hard negatives falsely cut: learn 3 of 38, held 2 of 11 (v2.1: 2 of 38 and 1 of 11).

**Verdict: not met.** Held-out pooled F1 is 0.103 against a target of 0.5 and against v2.1's 0.13. Recall rose (0.35 vs 0.12) but
precision collapsed (0.06): 186 false cuts, 141 of them in ORV. v3 is at or above v1 held-out F1 only on ORV and equal on P&P; it is
below v1 on RI and LotM. The judge says "different location" on almost every boundary it is shown, so the place-only rule cuts
nearly everywhere and `min_gap` is what decides the result. Because the learn split has only 26 gold cuts, the chosen rule
(learn F1 0.17) is barely above the next grid entries (0.14 to 0.16), so the selection is weak evidence.

Held-out examples (silver gold may be wrong). Several "false negatives" had judge answers of no/no/no and were removed only by
`min_gap 5` (RI ch21 block 37 after a cut at 36), so the gap rule, not the judge, lost them. Anchors are in the JSON `examples`
key.

## RI ch1 named check (`ri_ch1_check_v3.json`): 7 of 13 pass
Cuts found {19, 31, 45, 55, 79}, expected {31, 79}: FAIL (both gold cuts are found, with three extra). Segment 0 layer is "present",
no prior-loop segment: FAIL. In 31-78 the clan head is present, but Fang Yuan is listed present (FAIL) and not referenced (FAIL), elders
are not found (FAIL); Bai Ning Bing and Fang Zhi are referenced and not present: pass. In 79-89 Fang Yuan is present: pass.

## Default
`DEFAULT_RULE` in `scenes.py` is now the learn-chosen rule. `method="judge"` was NOT made the default (held-out 0.103 is below
v2.1's 0.13).
