# Implementation plan for Antigravity: finishing the EchoTales manhwa and anime adaptation

Written 2026-11-28 by the planning session (Claude Opus), to be handed to Antigravity (agy).
Read this whole file before starting. Then read `CLAUDE.md`, `README.md` and `docs/HANDOFF.md` ("Pick up here").

## 0. Goal

Turn web-novel chapters into a professional-feeling manhwa (vertical webtoon) and an anime-feel short video.

- **Novels:** Reverend Insanity (RI), Lord of the Mysteries (LotM) and Omniscient Reader's Viewpoint (ORV), chapters 1-10.
- **Quality bar:** the real manhua or webtoon of each novel, compared objectively side by side. "Better than last time" is not the bar; the finished product is.
- **Reporting rule:** do not report "good" to the owner until every scorecard row in `docs/results/MANHWA_DIRECTING_PATTERNS.md` section 4 is at or past the reference. If a row cannot be beaten locally, report it as an honest blocker.

## 1. Ground rules (owner, non-negotiable)

1. **Learn, do not hand-code.** Never hand-code a novel's conventions: no regex, cue-word lists or name lists per novel. Learn from the text, using a learn split and a held-out split. Never tune on held-out chapters or on the named check chapters (RI ch1 owner gold).
2. **Whole-novel knowledge.** Every directing decision uses knowledge of the whole novel: the dossiers (look at story time), the glossary and the future brief. Drama and curiosity are wanted. Inventing plot facts is forbidden. Every invented panel cites its evidence.
3. **Local only.** No cloud runs and no OpenAI. Every local tool is approved:
   - NoobAI and Illustrious (the default only if they win the side by side)
   - LoRA training, ControlNet and IP-Adapter
   - image-to-video models
   - 9B LLMs
4. **Laptop load** (RTX 4060 8 GB, 15 GB RAM):
   - One GPU job at a time, under `flock /tmp/echotales-gpu.lock`.
   - ollama and the image model never share the GPU; each model runs in its own subprocess.
   - LLMs at least 90% on the GPU. qwen3:8b is the default. gemma2:9b at ctx 8192 spills 21% to CPU, which is too heavy.
   - **qwen3:14b: exactly one run, and only after telling the owner first** so they can close other apps.
   - LoRA training at 768 px, not 1024.
5. **Data safety:**
   - Never write to `data/db/`; use scratch copies.
   - Never touch the main checkout's uncommitted changes (`/home/adhyan/Desktop/EchoTales` has many modified files that belong to the owner).
   - Never commit novel text, manhua images or model weights. Quotes in committed files are anchors of at most 5 words.
6. **Commits:**
   - The author is the owner only: no "Co-Authored-By" trailers and no "Generated with" lines.
   - No emoji and no section symbols.
   - Small commits. Do not push unless the owner asks.
7. **Renders:**
   - Every render goes in a NEW versioned folder `data/novels/<CODE>/panels/chN/vNN_<short-suffix>/`, created in the main checkout's data folder.
   - At the same time, append a one-line entry to that chapter's `VERSIONS.md`: what was tried, and an honest verdict from a viewer's point of view.
8. **Code style:** comments explain *why*, citing the measured failure, never *what*. Make surgical changes and reuse existing code.
9. **Formatting:** never run `ruff --fix` or `ruff format` on the whole repo. One earlier run touched 147 unrelated files. Lint only the files you changed.

## 2. Environment

- **Integration branch:** `claude/adaptation-director`, in the worktree `/home/adhyan/Desktop/EchoTales/.claude/worktrees/adaptation-director`. Branch per task:
  `git -C /home/adhyan/Desktop/EchoTales worktree add .claude/worktrees/<name> -b claude/<name> claude/adaptation-director`.
  Merge back into `claude/adaptation-director`, then delete the worktree and branch.
- **Python:** `/home/adhyan/Desktop/EchoTales/.venv/bin/python`.
- **Real LLM runs need these environment variables.** Without them you silently get the deterministic stub:
  `ECHOTALES_MODEL_BACKEND=ollama ECHOTALES_LLM_MODE=local ECHOTALES_LLM_LOCAL_HOST=http://localhost:11434 PYTHONPATH=packages/core/src:packages/pipeline/src`
- **Tests** (the suite was about 3414 passed / 29 skipped on 2026-11-28):
  `PYTHONPATH=packages/core/src:packages/pipeline/src .venv/bin/python -m pytest packages/core/tests packages/pipeline/tests -o addopts="" -q`
- **Scratch data:**
  - Knowledge base: `/home/adhyan/Desktop/EchoTales/data/scratch/kb/{reverend-insanity,lord-of-the-mysteries}.db`
  - Scene caches and the frozen v5 config: `.claude/worktrees/adaptation-director/data/scratch/segment_v5b_scratch/` (`outlinecache/`, `v5_FROZEN_8b_think_raw40.json`)
  - The scratch DBs the scene gold reads from are listed under `dbs` in `data/gold/segment/scene_boundaries.json`. Their files are in the v5b scratch folder above.
- **Process traps:**
  - Kill processes by PID only. `pgrep -f`/`pkill -f` inside `bash -c` matches its own shell.
  - Wait on a job with `while kill -0 PID; do sleep 30; done`.
- **Downloads** are slow (0.1-1 MB/s). A resumable downloader for the Illustrious-XL and SDXL ControlNets may still be running; check `ps` and the HF cache.

## 3. State as of 2026-11-28 (all on `claude/adaptation-director`)

| Area | State | Key files / numbers |
|---|---|---|
| Storyboard contract | done | `storyboard/schema.py` (Layer, Purpose, Shape, Shot, LetterKind incl. SCREEN, Panel.duration_s/emotion/withheld) |
| Scene cuts | v5 is the default, below target | `segment/outline.py`, `cast.py`, `storytime.py`, `presence.py`, `scoring.py`. Held-out ±1 pooled F1 **0.32** against a 0.5 target (v2.1 was 0.14). RI ch1 named check 12/14: the cut lands at 80 instead of 79, and the clan-head duplicate has since been fixed by KB linking. ORV ch1 has a false cut at 32. See `docs/results/SCENE_INDUCTION.md` |
| Scene gold | audited | `data/gold/segment/scene_boundaries_audited.json` (primary; blind kappa about 0.5), `ri_ch1_owner.json` (OWNER gold), `lotm_ch1_silver.json`, `orv_ch1_silver.json` and their `.checks.json` files |
| Knowledge base | partly verified | `knowledge/` dossier, glossary, future_brief and link. RI fact precision is 0.67; the verifier fix gives about 0.86 in-sample, and facts have NOT been rebuilt with it. Bai Ning Bing's look comes from later chapters: male, white-clad youth, white or silver hair, blue eyes. The ch1 clan head is linked to Gu Yue Bo. LotM and ORV glossaries have not been built. See `docs/results/KNOWLEDGE_BASE.md` |
| Looks | v2 code, unmeasured | `persona/looks.py` |
| Director | v2 built, first real run in progress | `storyboard/director.py`, `stage_scenes.py`, `cards.py`, `gold_check.py`, `prompts.py` (sb-5). v1's board scores 14/24 on the owner-gold checks; a hand-built gold board scores 24/24 |
| Art | B2 drama compiler and FX wired into `pages --storyboard --draw zimage` | `render/drama.py`, `pages/storyboard_art.py`, `pages/drama_fx.py`, `docs/results/ART_DRAMA.md` |
| Art v3 (A1) | code only, no image made yet | `render/_sdxl_art_worker.py`, C2 tag compiler, `scripts/art/train_character_lora.py`, `scripts/art/build_lora_set.py`, `scripts/eval/art_bakeoff_v3.py`, `docs/results/ART_V3.md`. **No real identity sheets exist**: the turnarounds on disk are grey stubs |
| RI ch1 final render | in progress on branch `claude/final-ri1` | the target folder is `data/novels/RI/panels/ch1/v58_director-v2-drama/`. Merge that branch first if it is committed; check its `docs/HANDOFF.md` note |

## 4. Work plan (in order; each task is one branch, measured, then merged)

### T0. Land the ch1 render
- History note (2026-11-28): `claude/adaptation-director` was rewritten before pushing to `master`, to drop a file with verbatim novel lines. `claude/final-ri1` was branched from the OLD commit `ed0ef32`. Before merging it, run `git rebase --onto claude/adaptation-director ed0ef32 claude/final-ri1`, and check that `data/eval/storyboard/*.json` storyboards are not committed (they contain novel text).
- If `claude/final-ri1` has commits, review them, run the tests and merge.
- Look at v58 against the reference slices, and write the honest verdict in VERSIONS.md if it is missing.
- If the render did not finish, finish it:
  1. Scene stage, v5.
  2. Director v2 on qwen3:8b.
  3. `storyboard --gold data/gold/segment/ri_ch1_owner.json --check-only <board.json>`.
  4. `pages --storyboard --draw zimage`, with FX on.
- Required general rule, if it is not already in: a withheld-identity panel whose reveal falls in the next segment moves into that segment, together with the boundary. This fixes the RI ch1 cut at 80 instead of 79.
- **Accept when:** the owner-gold check passes all 24 items, or every failure is listed with its cause.

### T1. Knowledge base completion (G2)
1. Rebuild the RI facts with the new verifier (value must overlap the quote, plus the who-is-this-about check). Re-sample 30 facts at seed 8. Target precision is at least 0.9.
2. Build dossiers for every person present or referenced in ch1-10 of RI, LotM and ORV, over all chapters each DB has. Use a light background run that can resume.
3. Build glossaries and future briefs for LotM and ORV, covering ch1-10 plus later chapters. Spot-check 5 entries per novel; they must be novel-specific (Beyonder and Sequence for LotM; constellation, scenario and system window for ORV).
- **Accept when:** the precision table, the coverage counts and the samples are in `docs/results/KNOWLEDGE_BASE.md`.

### T2. Looks v2 measurement (G3)
- Compile prompts for RI ch1 blocks 5, 37, 39 and 83, then LotM ch1 and ORV ch1 main characters. Ages come from the dossiers, in years where known:
  - Fang Yuan: 15 in the main line, an adult in the prior loop.
  - Bai Ning Bing: a youth.
- Fix the C2 tag compiler: it emits "mature male" for youths. Use the stated age, or the youth band, from the dossier.
- **Accept when:** a v1 vs v2 table, and every age, gender, hair and attire value is correct with its quote.

### T3. Art bake-off v3 and character identity (A1, G5)
1. Confirm the downloads have finished (Illustrious-XL v0.1, the small SDXL ControlNets, optionally the xinsir union model).
2. Run `scripts/eval/art_bakeoff_v3.py --phase run --arms B2,C2_noobai,C2_illustrious,D`, then `--phase sheets`, on the 13 panels in `tests/_art_bakeoff_panels.py`.
3. Judge each arm side by side against the reference manhua slices on four axes: drama (light, angle, energy, linework), relevance to the text, identity and age. Pick the winner as the art default.
4. With the winning model, generate identity sheets for Fang Yuan (both ages), Bai Ning Bing, Gu Yue Bo, Klein and Kim Dokja: front, three-quarter and profile; neutral and expressive. Only Kim Dokja's look comes from later chapters. Approve them by the local vision check plus a visual review.
5. Train one LoRA per main character at 768 px: `scripts/art/build_lora_set.py`, then `scripts/art/train_character_lora.py`. Re-run the bake-off with the LoRAs.
6. Optional: Z-Image ControlNet `alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1` (lite, 2 GB), if B2 wins and needs pose control.
- **Accept when:** the winner beats B2 on drama without losing relevance or identity, and the identity vision check shows at least 90% same person across 10 panels per main character.

### T4. Lettering and composer polish (G6)
- Balloons must never cover a face: use face detection, or the panel's subject box.
- SCREEN letters for phone UI and system windows, which ORV needs.
- POEM lettering.
- Pacing (gutters per beat) inside the ranges in `docs/results/WEBTOON_GRAMMAR.md`.
- **Accept when:** a side-by-side of a full chapter strip against the reference.

### T5. Voice (G7)
- Fix the tempo and pitch artefacts noted in the 2026-11-22 showcase verdict (`docs/HANDOFF.md`, `voice/`).
- Per-line emotion from the storyboard `emotion` field.
- **Accept when:** a listening check on 20 lines per novel, with artefacts gone.

### T6. Anime video (G8, A2)
- **Motion comic:** camera moves per shot type, parallax layers, animated FX, timing from TTS duration, NVENC encode. Reuse `compositor/` and `video/`.
- **Image-to-video** for peak and action shots only. Use Wan 2.x small or LTX-2 distilled (`video/wan.py` and `video/ltx.py` exist), fully on the GPU if it fits. Test one shot first.
- Music beds and SFX.
- **Accept when:** a side by side with a real manhua-drama or anime episode.

### T7. LotM ch1 and ORV ch1
- Run the whole chain on each. Check against `lotm_ch1_silver.json` and `orv_ch1_silver.json`, and their `.checks.json`.
- Get the reference manhwa slices from the owner (`echotales comic fetch <url>`; the owner picks the source).

### T8. Full run
- RI, LotM and ORV ch1-10 with the showcase settings: hybrid NER, `--tier full`, `ECHOTALES_COMPUTE=local-high`.
- Score each chapter against the reference.
- Run the docs-sync agent or equivalent (`docs/HANDOFF.md`, `docs/EVOLUTION.md`).
- Send the final report to the owner: each scorecard row at or past the reference, or an honest blocker.

### Optional, any time the GPU is free
- **Scene cuts to the 0.5 target.**
  - Ideas not yet tried: a second verification pass that checks only the proposed cuts; per-novel separator conventions; one qwen3:14b run (owner notice first).
  - Never tune on held-out.

## 5. Where the competition falls short, and what we must keep (from the 2026 research)
- **Their weak spots, which are our selling points:**
  - inconsistent visual style (47.1% of viewers complain)
  - flat voice acting (46.7%)
  - novel-like dialogue and copy-pasted designs
  - chapter-at-a-time adaptation that ignores the future plot
  - invented plot with no provenance
- **Keep these strengths:**
  - locked identity per body, looks at story time
  - whole-novel knowledge cards
  - quote-verified facts
  - per-beat directing grammar
  - a bounded review queue
- **Where they are ahead, and we must close the gap:**
  - real animation (Seedance, Kling)
  - art polish through per-character LoRAs
  - industrial scale

## 6. Reporting
- After each task: append the measured numbers to the relevant `docs/results/*.md` and a "Pick up here" line in `docs/HANDOFF.md`.
- Tell the owner briefly: the result first, then done / not done / needs you.
- The owner has ADHD: lead with the answer, short bullets, one decision at a time with your recommendation.
