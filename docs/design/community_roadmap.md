# EchoTales community roadmap: adapt any story yourself

Written 2026-11-16 at the owner's request, as the plan to follow after that date by whichever model or
person picks the work up. It is self-contained: read this, then `docs/HANDOFF.md`, then the last ten sections
of `docs/EVOLUTION.md`.

## 0. Pick up here (handoff written 2026-11-16, when the session was stopped)

All background tasks were stopped on the owner's instruction. Nothing is running. `origin/master` is current
with everything that was reviewed. Two pieces of work were cut off and are saved, unreviewed:

| Work | Where it is | State | What to do |
|---|---|---|---|
| Voice quality check | Merged to master (commit `70ad1a3`). Adds `voice/qa.py`, `voice/levels.py`, retries in `voice/runner.py`, a CLI entry, tests. | Reviewed and merged. Suite re-run (27 passed, full 89 voice suite passed). Loudness normalization and runaway speech retries active. | Done. Extended in M0 with Voice Actor Banks and dynamic prosody modulation. |
| Director rework | Branch `director-v2`, worktree `.claude/worktrees/director-v2`. | Stopped a few minutes in; no code written, no commits. | Start it again from the task description in M0 below. The full brief that was given to the agent is the eight stages listed there. |


Finished and on master today (details in `docs/EVOLUTION.md` 4.154 to 4.165 and decisions D53 to D59):

- Disguise looks are stored separately and never become a character's innate look; reader facts are visible to `state_of`.
- A prompt compiler, long prompts encoded whole, monochrome manga as the default mode, colour as the second mode.
- Z-Image Turbo as a local image worker (weights in `~/.cache/echotales/zimage`; `gguf` and `bitsandbytes` in the venv).
- A 24-scene benchmark of both image models; decision D58: Z-Image draws every panel.
- The first real director-to-image render, which showed the director is the weak link (4.164).

How to produce the good-looking panels today (hand-written scene briefs, not the real director path):
`data/scratch/panel_rework/benchmark.py` and `compare.py` show how to build a `PanelBrief`, compile it and
render it through `LocalZImageWorker`. The real path is `echotales render` with
`ECHOTALES_RENDER_PROMPT_COMPILER=true ECHOTALES_RENDER_IMAGE_MODEL=z-image-turbo`; it works but is not good yet.

Still waiting on the owner: `reader/speakers_pass.py` and its test (uncommitted in the main checkout; the
speaker fixes avoid them by design, see M0); the Shadow Slave and Northern Blade files; a RunPod key; GitHub
billing for CI; whether paid closed-model APIs may be used for the cloud tier.

The main checkout (`/home/adhyan/Desktop/EchoTales`) is still on an old commit with the owner's uncommitted
files. `git pull` there after committing or stashing those files to get today's work.

Scratch outputs worth keeping (all under `data/scratch/`, not in git): `panel_rework/bench_20261116_162505/`
(benchmark sheets), `panel_rework/run_20261116_zimage/` (ten-panel comparison), `panel_rework/e2e_20261116_1528/`
(the real-path baseline), `image_probe/` (first Z-Image probe), `audio_qa/`, `lead_check/` (real-model builds of
three books, chapters 1 to 21, with speaker scores), `speaker_diag/REPORT.md` (why speaker lines are missed).

## 1. The goal, in the owner's words

"As an anime/manga fan myself, I want to impress the community to be able to freely use this tool and visualise
to the extreme all the novels that didn't get an anime/manga adaptation and all the crazy good manhwas that don't
have an anime adaptation." The target is the best free tool and the best repository in this field.

What that means concretely:

- **Free and local first.** Anyone with a gaming laptop can run it on a book or manhwa they own. Bigger machines
  and rented GPUs give better output through the same interface.
- **Four adaptations, one engine.** Novel to full-cast audiobook, novel to manga, novel to anime, manga/manhwa
  to anime. All of them read the same story graph.
- **The story graph is the reason this tool is different.** It knows who each character is, what they look and
  sound like at chapter N, who is in a scene, and what the reader has learned so far. Every feature below must
  use it; a feature that could be built without it is a lower priority.

## 2. Where the project stands (2026-11-16, `origin/master` at `ff915f0` or later)

| Part | State | Evidence |
|---|---|---|
| Story graph (ingest, resolve, reader, `state_of`) | Works, tested, audited per stage | 2,051 tests; `echotales audit` |
| Who speaks each line | 95% on Lord of the Mysteries, 82% ORV, 69% Reverend Insanity (model-drafted references) | EVOLUTION 4.157 |
| Full-cast audio | Produces speech and an M4B; never listened to critically; a quality check is being built | worktree `audio-qa` |
| Panel images | Two local models behind one compiler: Z-Image Turbo (scenes) and NoobAI (anime look). Hand-written scene briefs look good; the real director path does not | EVOLUTION 4.160 to 4.164 |
| Director (scene to shot list) | The weak link: repeated portraits, lost crowds, wrong locations | EVOLUTION 4.164 |
| Video | Pan-and-zoom motion comic works; local LTX clips work with a quality gate; subtle motion only | EVOLUTION 4.148 to 4.154 |
| Studio (web app) | Works for build, review, lock, voice, render; hand-written server; several screens thin | `webview/` |
| Manga pages (layout, speech bubbles) | Not built: output is loose panels | |
| Manga/manhwa as input | Not built | |
| Cloud tier | Mock-tested only; needs a RunPod key | EVOLUTION 4.106 |

Work that was in flight is described in section 0.

## 3. Rules that keep this from going wrong again

These come from what actually went wrong in the first three months.

1. **Look at real output before building more.** Every milestone ends with one real run on a real book that a
   person watches or listens to. A feature is not done because its tests pass.
2. **One vertical at a time.** Finish a mode until it is showable before starting the next.
3. **Fix the earliest stage.** A wrong picture is usually a director or graph problem, not an image-model one.
   Measure which stage dropped the information before changing anything (EVOLUTION 4.164 is the model example).
4. **Measured or absent.** No number on screen or in the README that was not measured; record how.
5. **Record as you go.** Each change gets its `docs/EVOLUTION.md` section and, if it is a choice,
   a `docs/design/decisions.md` entry in the same commit series.
6. **Hardware rules.** One model on the GPU at a time; check it is free; never offload weights into RAM; wrap
   GPU commands in `flock data/scratch/gpu.lock` when more than one job may run.
7. **Never commit book text, manhwa pages or media made from them.** Public samples come from public-domain or
   original stories only.
8. **Keep tasks small.** One task, one acceptance check, one commit. Give an implementing model the files, the
   failing test to write first, the command that proves it, and a do-not-touch list.

## 4. Milestones

Order matters. Each milestone lists what to build, how to know it is done, and what it unlocks.

### M0. One chapter that is good, end to end (finish the wrap-up)

The project has no showable output yet. Nothing below starts until this exists.

- **Director v2** (eight stages: map the losses; output schema; shot variety; brief and compiler; a
  conservation check; batching; a real run compared with the baseline in
  `data/scratch/panel_rework/e2e_20261116_1528/`; a model bake-off). For each panel the director must return: cast ids present; per character position, pose,
  expression and condition (wounds, torn clothes); others present (who, how many, where relative to the lead);
  the location taken from the text with concrete background; time and weather; props; shot size and angle.
  Add a shot-variety rule (no two consecutive panels with the same shot size and subject). `brief_from_direction`
  must read every field and receive the beat text. Add a conservation check: every person, place and prop the
  beat text states is in the brief or counted as dropped, reported by `echotales audit`.
- **Director bake-off.** Same five scenes, every local language model on disk, scored on the dropped-field
  count. Pick by the number.
- **Batching.** The image model loads once per chapter, not once per panel (86 s per image today, 32 s of it
  drawing).
- **Named characters look different.** Each named character gets a fixed description from `state_of` and a
  stated position; where the book gives nothing to tell two apart, a stable assumed marker that is never written
  to the graph.
- **Compiler gaps the benchmark briefs exposed** (`render/compiler.py`; found 2026-11-16 while writing 24 varied
  briefs): only the first character gets an expression, and no character has a position; no style or wardrobe
  line for genres other than xianxia on the Z-Image profile (Victorian, modern, Regency fall back to generic
  text); no child or teenager nouns; no creature or non-human entity; crowd wording assumes a lead is present;
  scenery-only panels still get people and wardrobe tags on the NoobAI profile; a "same face as" link between
  two characters (twins) does not exist. Each is a small, testable change.
- **Model roles are settled** (decision D58, EVOLUTION 4.165): Z-Image Turbo draws every panel; no routing.
  Fix the six compiler defects the benchmark exposed, listed at the end of EVOLUTION 4.165 (a gate in every
  xianxia picture, people added to scenery, indoor drawn outdoors, the warm smile, bright pages for dark
  scenes, weak creature anatomy).
- **Audio: Voice Actor Bank & Dynamic Prosodic Modulation.** The old VCTK bank (monotone university students)
  is retired as the primary voice bank for story characters. Supported via `voice/actor_bank.py`: curated Voice Actor
  Banks with archetype mapping (`COLD_DOMINANT`, `HOTHEADED_RIVAL`, `VENERABLE_MASTER`, `DRAMATIC_NARRATOR`),
  ESD (Emotional Speech Dataset: 5 acted emotions), and LibriTTS-R (2,400+ restored audiobook narrators).
  Voice actors tune their delivery dynamically (`voice/delivery.py` and `voice/pitch.py`): pace accelerates on
  exclamations (1.12x) and action narration (1.05x), decelerates on solemn/formal dialogue (0.90x), pitch inflects up
  on exclamations (+1.5 semitones), and drops into resonance on elders/menacing lines (-2.0 semitones). Exclamations
  condition on authentic shouted reference takes.
- **Show, Don't Tell: Visual Narration Pruner.** In visual adaptation modes (manga, motion comic, anime video),
  prose narration is pruned of redundant visual descriptions (`render/narration_pruning.py`: physical postures,
  movements, clothing, facial gestures, immediate setting) that the image already conveys. Only non-visual elements
  (inner thoughts, psychological reflections, historical lore, unseen sensory cues, time skips) are kept as
  voiceover / narrative captions. In audiobook mode (M4B), full narration is preserved untouched.
- **Done when:** one public-domain chapter (Pride and Prejudice 1 to 3, or a Sherlock Holmes story) runs from
  upload to M4B, panels and a motion-comic video from the Studio without touching the terminal, and the owner
  would show it to a friend. Record a two-minute screen capture. Put it at the top of the README.


### M1. Novel to manga: real pages, not loose panels

Fans share pages. This is the cheapest mode to compute and the most shareable output.

- **Page composer.** Panel layout templates chosen from the shot list (splash for a reveal, wide for an
  establishing shot, a stack for an exchange); right-to-left manga, left-to-right comic, and vertical webtoon
  strip. Deterministic; no model.
- **Lettering done by code, never by the image model.** Speech bubbles placed from the dialogue spans with the
  speaker's tail pointing at their position in the panel (the director already knows it); narration boxes;
  thought bubbles for inner speech; shouted lines styled from the delivery marker; sound-effect text as an
  optional layer. Fonts with open licences.
- **Export.** PNG pages, PDF, CBZ, webtoon strip.
- **Identity over a volume.** A character reference sheet per character per time interval, approved in the
  Studio, then used by whatever identity method the image model supports (fixed description today; a LoRA per
  main character trained on a rented GPU; reference adapters where a model has them).
- **Vision check.** Several candidates per panel; a local vision model answers the checklist (who is present,
  hair, outfit, count) and the best passing one is kept. Report pass rate and regenerations.
- **Done when:** a full chapter exports as a readable manga with correct bubbles, and the same character is
  recognisable on every page in a blind look by someone who has not read the prompts.

### M2. Manga and manhwa to anime

The art already exists and is professional, so this mode sidesteps the hardest problem (drawing) and gives
the biggest reaction for the least generation. Likely the mode fans care about most.

- **Input.** A folder, CBZ or PDF of pages; vertical webtoon strips sliced at gutters.
- **Page understanding.** Panel detection and reading order; speech-bubble and text detection; text recognition
  (English first, then Korean, Japanese, Chinese); which character speaks each bubble; the same character
  recognised across panels. Candidates to evaluate, none adopted: the Magi family of manga models for panels,
  text and speaker association; manga-ocr and PaddleOCR for text; a general vision-language model as fallback.
  Verify licences and memory needs from the model cards before choosing.
- **Into the same graph.** Characters, speakers and scenes go into the existing store so casting, voices,
  review and corrections all work unchanged. A reviewer fixes a wrong speaker once and it holds.
- **Clean plates.** Remove bubbles and text by inpainting so the art can move; keep the original lettering as
  an optional subtitle track.
- **Motion, cheapest first.** (1) Camera moves and cuts timed to the voiced lines (already built).
  (2) Depth-based parallax so a still gains layers. (3) Image-to-video on panels that have action, held to the
  original frame by a start-and-end check (the clip gate exists). (4) Interpolation between two consecutive
  panels of the same shot. Candidates: LTX-Video (already integrated), FramePack and Wan image-to-video for
  local or rented GPUs, an anime-trained model such as Index-AniSora on a rented GPU, ToonCrafter for
  in-betweens. Measure on the same ten panels before adopting any.
- **Sound.** Voices from the existing cast system; subtitles from the recognised text; optional music and
  ambience tracks the user supplies; generated sound later.
- **Done when:** one chapter of an openly licensed or self-drawn comic becomes a two-to-three-minute voiced
  episode a fan would watch to the end.

### M3. Novel to anime

Built from M0 to M2: the director's shot list, panels as keyframes, the motion ladder from M2, voices and
subtitles. New work:

- **Episode composer.** Scenes into acts, a cold open, a title card, a recap from the graph ("previously"),
  a next-episode card.
- **Keyframe chaining.** Each clip starts and ends on approved panels so drift cannot build up; clip length
  from the voiced line; motion strength from the delivery marker (the "narrative-timed keyframe chaining" idea
  in `video_plan.md`). Keep it only if it beats fixed-length clips on the same chapter.
- **Cloud tier for quality.** Reference-conditioned keyframes from a multi-reference editing model and a larger
  video model on a rented GPU, behind the same engine interface, with a cost ledger and a hard cap.
- **Done when:** one chapter becomes an episode with continuous motion in at least the action scenes, on the
  cloud tier, and a motion-comic version on the laptop tier, from the same project.

### M4. Features only a story graph can give (the community hooks)

- **Adaptation packs.** A shareable file holding the cast, descriptions per time interval, voice casting, shot
  lists, approved reference prompts and corrections, keyed to chapter hashes, with no book text and no quotes.
  Someone who owns the same book loads the pack and renders the community's adaptation locally. This is the
  feature that lets fans collaborate on a series that has no adaptation without anyone distributing the book.
- **Spoiler-safe companion.** "Who is this again?" at chapter N: character cards, relationships, timeline and
  a glossary that never reveal later chapters. Exports as a static site.
- **Long series.** Incremental builds for novels of a thousand or more chapters; resume anywhere; time and
  cost estimates before a run; aliases that differ between translations merged by the reviewer once.
- **Languages.** State plainly what is English-only today; add source-language support in the order the
  community asks.
- **Casting and direction controls.** Voice auditions, clone your own voice for a character, per-line
  delivery, regenerate one panel with edited direction, pick among candidates.

### M5. Make it the repository people point to

- **Install in one command.** A setup script that detects the GPU, downloads only the models that fit, shows
  each model's licence, and runs the sample book. A Docker image. Hardware presets: 8 GB laptop, 12 to 24 GB
  desktop, rented GPU.
- **Engine plug-ins.** One registry per engine kind (language model, image, speech, video) with a declared
  interface, tier, licence, memory need and measured speed, so the community can add a new model in one file.
  This replaces the scattered lists in `render/panels.py`, `voice/engine.py`, `llm/client.py` and `compute.py`.
- **A public benchmark.** Speaker attribution, character consistency across panels and scene fidelity on
  public-domain books, with the scoring scripts. If other tools report numbers on it, the repository matters
  beyond its own features. Hand-checked references, not model-drafted ones.
- **README as the product page.** The demo video first, then three commands, then the comparison table filled
  only with measured numbers, then how it works.
- **Housekeeping.** A code licence; a contribution guide; the 3,000-line `render/panels.py` and the hand-routed
  server split up only when a milestone needs to touch them; dead code removed.

## 5. What to do first, in order

1. Finish or discard the in-flight work in section 2.
2. M0, in the order listed there. Director v2 first; it decides the quality of every visual mode.
3. M1 lettering and pages, because it turns existing panels into something shareable within days.
4. M2 input side (page understanding), then its motion ladder.
5. M4 adaptation packs and the companion, then M3, then M5 continuously as each mode becomes showable.

## 6. Risks, stated once

- **Copyright.** The tool is bring-your-own-book and runs locally. The project never hosts or ships text,
  pages or media made from works it has no right to. Adaptation packs carry no text. Public demos use
  public-domain or original work.
- **Quality ceiling on a laptop.** Local output will not match products built on the largest closed models.
  The answer is honesty per tier and the features those products lack, not pretending otherwise.
- **Scope.** Five modes is a lot for one person. The order in section 5 exists so that stopping after any
  milestone still leaves something finished.
- **Evaluation.** Current accuracy figures rest on model-drafted references for three books. Treat them as
  regression checks until the benchmark in M5 exists.
