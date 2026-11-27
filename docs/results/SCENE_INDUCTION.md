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
