# Storyboard director: state and handoff (2026-11-28)

Branch `worktree-agent-a3bf9bcac55075841`, built on `claude/adaptation-director` (33698b5 contract). Status: working end to end on RI ch1 with qwen3:8b; benchmark incomplete (see "Not done").

## What exists

Code in `packages/pipeline/src/echotales/pipeline/storyboard/` (contract `schema.py` untouched):
- `inputs.py`: loads blocks, spans, roster, graph scenes; separator split ("..." blocks, only when both halves >= 8 blocks); adapters `presence_for` / `look_for` that import `segment.presence.present_cast` and `persona.looks.look_at` if they exist, else fall back (flags `presence_contract`, `look_contract` are stored in the meta file).
- `director.py`: (1) scene pass, one call over the whole chapter; a mark is kept only if >= 6 blocks from its neighbours and its place or story time or layer differs; (2) presence pass per scene on raw text with no speaker labels (skipped when the real contract exists); (3) one panel-plan call per window (<= 14 blocks, ~520 words), bisected on unparseable output; (4) conversion (letters by line tag, never retyped text; SFX and card text validated) ; (5) audit, repair, audit. Cache by input hash. Output `data/novels/<CODE>/storyboard/ch<N>.json` + `.meta.json` (`paths.storyboard_path`).
- `validators.py`: rules and repairs listed below, each repair logged. `scorecard.py`: section 4 rows plus hand-list presence. `plan_schema.py`, `prompts.py` (grammar, few-shots, scene and presence prompts).
- `Task.STORYBOARD` (model via `ECHOTALES_STORYBOARD_MODEL`, default gemma2:9b: change after the bake-off), config flag `render.storyboard` (default off, not wired to render), CLI `storyboard`.
- Few-shots (4, Pride and Prejudice plus invented): `data/gold/adaptation/storyboard_fewshot.jsonl`. Hand presence list from the owner gold: `data/gold/adaptation/presence_ri_ch1.json`.
- Tests: `packages/pipeline/tests/test_storyboard_director.py` (13, fake model). Full suite was 3206 passed before the last round of edits; rerun it.

Rules checked and repaired: speech_lost, referenced_in_room, name_not_in_cast, speaker_not_present (reader label cleared), crowd_named, crowd_line_not_individualised (distinct invented faces), panel_overstuffed (split by speaker turn), cut_unsignalled, no_cold_open, peak_no_relief, card_empty, inset_layer, invented_no_reason, shape_variety. Reported only: density band, visual_repeat.

## Measured: RI ch1, qwen3:8b, num_ctx 8192, 100% GPU (copy of ri_fresh_v57.db)

Files: `data/eval/storyboard/ri_ch1_qwen3-8b.{json,meta.json,cli.txt}`.
- 112 panels (reference ~84; 1.3 per story block, inside the band), 8 scenes, cold open yes, layers 4, SFX 8, inserts+ECU 15, crowd individuals 17, referenced insets 5, shapes 7, letter kinds 6 (reference 8).
- Violations before repair 19 (speech_lost 5, panel_overstuffed 3, crowd not individualised 3, speaker_not_present 3, card_empty 2, peak_no_relief 2, visual_names_absent 1); after repair 4, all visual_repeat (not repairable).
- Latency 242 s model time for 19 calls (68k prompt, 8k completion tokens), about 4 min per chapter. JSON failures 0 after bisection.
- Earlier iterations (same model): window-level new-scene flag gave 4 false cuts and missed the real one; no scene filter gave 16 scenes; fixed by the scene-pass filter. A model that retyped text instead of tags was fixed by the tag-only letter schema.

## Against the owner gold (`data/gold/segment/ri_ch1_owner.json`, be04cb3)

Gold: scene 1 blocks 0-30 (prior loop, layer past), scene 2 blocks 31-78 (only clan head and elders present), scene 3 blocks 79-89 (Fang Yuan at window, match cut from the clan head's window, eyes withheld).
What the storyboard gets right: cuts at 31 and 79 found and given cut panels; clan head and elders in the ritual; Bai Ning Bing and Fang Zhi as referenced; Fang Yuan's lines in the ritual cleared of speaker.
Where it fails:
1. 8 scenes instead of 3: false splits at 19, 25, 38, 45, 73 (same place or time, model marks differ in wording). Each false split costs an extra cut panel.
2. Scene 1 layer is `present`, gold says `past` (prior loop); scene 3 labelled with the scene-2 time ("late night"), gold says same moment as scene 2's end.
3. Fang Yuan is listed as referenced in the ritual only in some runs; in the first run he was still cast in the ritual (the presence pass is a model read and noisy; the real `present_cast` contract should replace it).
4. Block 79 identity withholding is NOT done: panel p102 is an establishing shot carrying the "pair of clear eyes" narration, then Fang Yuan named in p103. Needs an extreme-close eyes panel with no cast, then the reveal.
5. Bai Ning Bing silent white-clad imagined inset: appears only as a referenced inset in some runs, no look or white clothing (no whole-novel look data yet).
6. Cold open in this run is the repair's hero frame, not an SFX spread; no memory montage tied to volume knowledge; poem lines (block 18) are not lettered as `poem`; kinds dread/whisper/poem/name_card unused.
7. Repeated picture text (4 consecutive duplicates) and generic visuals; the model reuses "robes waving".
8. Hand list used for the scorecard was rewritten to the owner gold cuts (31, 79); the scorecard presence rows match against names only.

## Not done

- gemma2:9b benchmark. `echotales ... storyboard --model gemma2:9b` with `ECHOTALES_LLM_LOCAL_NUM_CTX=6144` exits 0 right after "model backend: ollama" and prints nothing (cause not found; qwen3 works with the identical command; check `cmd_storyboard`, the `client.require_ready` oversize check and exit paths first). gemma2:9b at ctx 8192 spills to CPU (ollama ps showed 9.5 GB, 21% CPU), which is not allowed; ctx 6144 is untested. Until measured, qwen3:8b is the working choice: fits 100% on GPU, 0 JSON failures.
- Pride and Prejudice ch1 (`pnp.db` copy of data/scratch/pnp-e2e-v5-showcase.db, novel `pnp-e2e`) and LotM ch1 (copy of data/db/lord-of-the-mysteries.db) runs and their scorecards.
- Remedies for the failures above are for a follow-up (owner: whole-novel dossiers, glossary and a future brief will feed the director); no redesign started.

## Commands to continue

Scratch DB copies (already made, recreate if /tmp was cleared): `cp data/scratch/e2e_ri/ri_fresh_v57.db <scratch>/ri.db` (from the main checkout's data/), likewise pnp and lotm.

```
cd <worktree>
export PYTHONPATH=$PWD/packages/core/src:$PWD/packages/pipeline/src ECHOTALES_MODEL_BACKEND=ollama ECHOTALES_LLM_MODE=local ECHOTALES_LLM_LOCAL_NUM_CTX=8192 ECHOTALES_LLM_LOCAL_TIMEOUT=900 PYTHONUNBUFFERED=1
flock /tmp/echotales-gpu.lock /home/adhyan/Desktop/EchoTales/.venv/bin/python -m echotales.pipeline.cli --db <scratch>/ri.db storyboard --novel reverend-insanity --chapters 1 --model qwen3:8b --data-root <out> --force --hand-presence data/gold/adaptation/presence_ri_ch1.json
```
Same with `--db <scratch>/pnp.db --novel pnp-e2e` and `<scratch>/lotm.db --novel lord-of-the-mysteries` (omit `--hand-presence`). Tests: `python -m pytest packages/core/tests packages/pipeline/tests -o addopts="" -q -x`. Then set the Task default model, add a Pride and Prejudice and LotM section here, and run `docs-sync`.

## Director v2 (prompt sb-5), built code-only, not yet run on a model

Built on `claude/director-v2` against stubs and unit tests; nothing here has touched ollama or a GPU, so no v2 quality number exists yet.

- **Scenes from the segment stage** (`storyboard/stage_scenes.py`): cuts, prior loops and `SceneAnalysis.time_labels` (read with `getattr`; the field lands with segment v3) replace the director's own scene pass; the v1 pass remains the fallback. Meta flag `scenes_from_stage`.
- **Knowledge cards and a token budget** (`storyboard/cards.py`): per person, look at story time, age, role, what the title means (glossary, by phrase membership), status present or talked about. `assemble` keeps rules, scene line and text; drops few-shots first, then lookahead and the future brief, then shrinks cards (title, role, look), then drops the lowest-ranked card.
- **Prompt sb-5**: shorter rule block; cold open that is not the hero, withheld identity (two lookahead blocks, never drawn), match cut for a simultaneous scene, silent dossier inset for a talked-about person who matters later, foreshadow only as emphasis, screen and poem lettering, emotion per panel, invented panels cite `text:`, `dossier:` or `brief:`.
- **Rules** (`validators.audit_v2` / `repair_v2`, run after v1's): `cold_open_hero`, `withheld_*`, `parallel_cut_unmatched`, `inset_missing`, `inset_has_balloon`, `inset_look_not_dossier`, `layer_mismatch`, `cast_outside_present`, `foreshadow_unanchored`, `foreshadow_depicts_later`, `no_foreshadow`, `invented_no_evidence`, `emotion_missing`. Reported only, not repairable: missing reveal, missing foreshadow, missing emotion, a balloon on an inset.
- **Gold checker** (`storyboard/gold_check.py`, sibling `data/gold/segment/<stem>.checks.json`): `storyboard --gold <gold.json> --check-only <storyboard.json>` scores a saved board with no model. Saved v1 RI ch1 board: 14 of 24 checks pass; it fails cold open (hero), withheld b79, inset look source, poem b18, foreshadow, citations, scene count and the prior-loop layer.
- **Needs a real-model run**: whether the model chooses a non-hero cold open, detects withheld identity from the lookahead, triggers the inset and foreshadow beats, and fits the prompt in 4096 tokens; and the exact `time_labels` shape once segment v3 is merged.
