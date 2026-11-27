# Look by epoch (2026-11-27)

Code: `packages/pipeline/src/echotales/pipeline/persona/looks.py`, wired in `render/compiler.py::character_brief`
(switch off with `ECHOTALES_LOOK_BY_EPOCH=0`). Measurement: `scripts/eval/look_by_epoch.py`; raw output in
`data/eval/looks/` (`ri_ch1.json`, `lotm_ch1.json`, `pnp_ch1.json`, `summary.json`).

## Failure fixed (RI ch1, render v57)

Every character got the same genre-default sentence ("long black hair tied up in a topknot with a hairpin ... an adult
face"), and Fang Yuan had one look for the whole chapter although the text separates epochs (cliff after 500 years,
torn deep-green robes, block 5; the reborn youth with "young and soft, pale palms", block 83).

## Contract

```python
look_at(store, novel_id, entity_id, *, chapter: float, block: int, client=None) -> Look
Look: look_id, entity_id, epoch_label, age_band, gender, description, facts[{field, value, source_block, invented, reason}]
      (+ hair, eyes, build, face, outfit, condition, marks, block_from, block_to)
```

How: scene windows (break blocks, the first reset statement such as a rebirth, size cap) -> one `Task.READER`
(gemma2:9b) read per window the character is in -> every value kept only if the block it cites holds most of its words and
it is short enough for a prompt -> epochs split where the stated age band changes -> gaps filled from a per-novel slot bank
(stored once, each new person at least 3 of 5 dimensions away from all earlier ones), flagged `invented` with a reason.
Age comes from cue words in sentences about the character (a model band is accepted only when its cited block carries
the same cue; at 7B it called the clan head "young adult" and the 500-year-old "teen" from stray words). Gender: stored/owner
value, then pronoun counts; no name-suffix rules. A condition (torn, blood) belongs to its own epoch only.

## Results, chapter 1

RI (Fang Yuan has 2 looks, as required):

| Entity | Epoch | Look |
|---|---|---|
| Fang Yuan | blocks 0-30, ageless-ancient | chestnut brown hair with a few silver strands, long and loose, broad-shouldered, deathly pale, deep green robes, covered in blood, torn to shreds, numerous wounds |
| Fang Yuan | blocks 31-91, teen | chestnut brown hair, long and loose, slim boyish build, narrow face, charcoal grey robe (invented, the cliff's green is not carried) |
| Gu Yue clan head | whole chapter, middle-aged | dark brown hair graying at the temples, graying sideburns, broad-shouldered, ceremonial white robes (stated, block 37) |
| Fang Zhi | whole chapter, adult | black hair, medium-length, lean build, ochre robe (all invented; text states nothing about his body) |

Distinctness (pairs of characters co-present in a scene window; distinct = differ on >=2 of hair, age band, clothes,
build/face). "Before" = persona facts plus `identity_lock` stored defaults, without the scene-look model call.

| Novel | Pairs | Before | After |
|---|---|---|---|
| RI ch1 (3 entities) | 3 | 2 | 3 |
| LotM ch1, entities with >=3 present blocks | 5 | 5 | 5 |
| LotM ch1, all 22 detected (mostly NER noise: "Ouch", "Hey") | 127 | 97 | 127 |
| P&P ch1 (3 entities, one is a place) | 3 | 3 | 3 |

The "before" metric is weak: its defaults already differ by id hash in clothes colour. What it does not capture is the
measured v57 collapse (same topknot sentence), age band, and epoch changes, so the table understates the gain on RI; the
epoch result (2 looks for Fang Yuan against 1) is the main one.

## Unmeasured / known weak

- No image was rendered with the new prompts; the prompt text and `identity_sentence` output were not compared in a render.
- Age is mostly cue-word regex; a chapter with no age word gives `adult` flagged invented. Model reads are noisy at 9B too
  (a stray "clear eyes" was handed to the clan head from a neighbouring block).
- Epochs are cut only at scene breaks and the first reset statement of a chapter; a mid-scene change of age is missed.
- Looks are per chapter; cross-chapter continuity of invented values relies on the slot bank, not on re-reading.
- LotM/P&P were run on scratch DBs whose entities are noisy; Klein is split over several entities there.
- One model call per character per window on the director pass; the image pass reads the cache and falls back to a
  deterministic (unmodelled, uncached) build when there is none.

---

# v2 (2026-11-28): no word lists decide anything. STATUS: CODE DONE, MEASUREMENT NOT DONE (handoff)

Branch `worktree-agent-af97977aee6c946b5`. Code: `persona/looks.py` (rewritten), tests `packages/pipeline/tests/test_looks.py` (10, fake LLM),
`scripts/eval/look_by_epoch.py` (windows now from `scene_cut_blocks`). Full suite 3206 passed, ruff clean on touched files.

## Done
- Evidence-quoted reads: every value carries a verbatim quote and block; kept only if the quote is in that block (case, space and
  punctuation normalised, `find_quote`), the value shares content words with the quote, and a second model check
  (`Verdicts.states_value`) agrees. Age band: model check only; no supporting quote means UNKNOWN, invented `adult`, flagged.
- Attribution: nearest preceding person mention in the block from the mention table (`graph_attribution`), else the model must pick the
  owner by NAME from the people the store names in the shown blocks plus the next block (so "a pair of clear eyes", RI block 79,
  revealed as Fang Yuan in 80, is not the clan head's; tested with a fake LLM, owner gold scene 3).
- Epoch boundaries: one chapter question per chunk ("does the text state that a body changes ..."), quotes verified, cut at the scene
  window containing the event (`scene_cut_blocks`: the scene-cut module's `load_scene_cuts` if importable, else break-shaped blocks;
  RI ch1 breaks give windows 0-4, 5-30, 31-86, 87-91). What carries across a boundary follows the event's `affects` groups.
- Whole-novel facts first: `dossier_facts` reads `StateResolver.state_of` (story time, end-of-novel knowledge point) for the persona,
  keeps a fact only if its evidence quote is found verbatim in the chapter it was learned in; current-chapter facts only inside the epoch;
  transient condition never crosses chapters. Then per-chapter reads, then the slot bank. Not exercised on real data yet (the KB agent's
  dossier rows were not available in the RI copy).
- Gender: stored/owner value, else `persona/gender.py` (`_current_gender`, `gender_lean_basis`); pronoun regex deleted.
- Setting: one cached model read per novel (`look_setting:<novel>`) gives garment family and colours; no manhua flag.
- `COMPILER_BAND`: middle-aged and ageless-ancient were mapped to "adult", which `_identity_head` never writes, so stated ages never reached
  the prompt; now middle-aged -> "middle-aged", elderly and ageless-ancient -> "elder".

## Findings while measuring (important)
- The worktree has no `.env`, so a bare run silently uses the STUB model (`model='stub'`, empty answers, instant). Real runs need
  `ECHOTALES_MODEL_BACKEND=ollama ECHOTALES_LLM_MODE=local ECHOTALES_LLM_LOCAL_HOST=http://localhost:11434`. My first RI run was a stub run:
  its output (adult, invented, "plain everyday clothes") is NOT a result.
- Resource rule: gemma2:9b at num_ctx 8192 spilled 21% to CPU; at 4096 it still spilled 9% (GPU shared with other agents, ~5.6 GB used).
  qwen3:8b at num_ctx 4096 loaded 100% GPU. Use `ECHOTALES_LLM_LOCAL_NUM_CTX=4096 ECHOTALES_READER_MODEL=qwen3:8b` and check `ollama ps`
  shows 100% GPU. (gemma2:9b vs qwen3:8b comparison and the event-question recall check were queued behind the GPU lock, not finished.)
- Surface names for Fang Yuan include noisy aliases ("sir", "my lord", "this one"), which widen presence; verification absorbs it but it
  costs calls. The clan head in the RI DB is `reverend-insanity:self:7fc3b9af53` ("The clan head", label alias "Gu Yue Bo").

## Remaining (in order)
1. Run on RI ch1 with a real model, scratch copy (the copy is at the session scratchpad `v2/ri.db`; re-copy from `data/db/reverend-insanity.db`, never write to it):
   `PYTHONPATH=packages/core/src:packages/pipeline/src ECHOTALES_MODEL_BACKEND=ollama ECHOTALES_LLM_MODE=local ECHOTALES_LLM_LOCAL_NUM_CTX=4096 ECHOTALES_READER_MODEL=qwen3:8b ECHOTALES_LLM_LOCAL_HOST=http://localhost:11434 flock /tmp/echotales-gpu.lock .venv/bin/python scripts/eval/look_by_epoch.py <scratch.db> reverend-insanity 1 data/eval/looks/v2/ri_ch1.json --model-calls`
   Check: Fang Yuan epoch 0-30 torn deep-green robes, dishevelled hair, blood (block 5), old only if a quote supports it; epoch from 31 young with pale palms (block 83);
   clan head middle-aged (block 37), not given "clear eyes"; elders loose white garments (block 39). If the event question returns nothing, tune
   `EVENT_SYSTEM` (gemma returned no events on blocks 29+ at 4096; qwen3:8b untested).
2. Same for LotM ch1-2 (`data/db/lord-of-the-mysteries.db` copy) and P&P (`data/scratch/pnp-e2e-v5-showcase.db` copy, public domain).
3. Silver gold (<= 8-word quotes, "silver, not owner-checked") per character per epoch for RI ch1, LotM ch1-2, P&P ch1; then a metrics script: fact precision, fact recall,
   age-band accuracy, epoch-boundary accuracy, distinctness of co-present pairs; v1 column from `data/eval/looks/{ri,lotm,pnp}_ch1.json` (v1 code is commit ed44787).
4. Compiled prompts for RI blocks 5, 37, 39, 83: build `character_brief(store, novel, self_id, story_position_of(1, block, nblocks), scene=<obj with .client>)` then
   `compile_prompt(PanelBrief(...))` with the default Z-Image profile (natural family, never truncated) and the SDXL tag profile; print what survives
   `persona/prompt.py::fit_to_budget` (77 CLIP tokens). If age, condition, clothes fall off, reorder priority (age band, condition, clothes). Paste into this doc.
5. Owner conflict to note: owner gold calls the clan head old; the text (block 37) says "middle-aged appearance"; we follow the text.
6. Grep the diff for remaining constants that decide: none in `looks.py` except `_BREAK` (punctuation-only shape check), `_MAX_WORDS` (length caps), `_CARRY_BREAKS` and
   `AGE_BANDS` (closed label sets the model is asked to output, not cues in prose), `_name_match` (compares the model's answer to the graph's own names). Re-verify after step 1.
7. Run docs-sync once measured; commit without trailers; do not push.
