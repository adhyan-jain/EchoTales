# Engineering notes (research arena)

A running log of every problem hit while building and running the research
arena, the diagnosis, the fix, and the lesson -- the things you would have
learned by building it by hand. Newest at the bottom. Each entry says what
was *measured*, not assumed.

## 2026-10-02: mutation lab, wave 1

### 1. A render job froze the laptop: CPU offload parks the model in RAM

- **Symptom:** load average 15, swap 21/22 GB, the owner's other work
  stalled while `visual_rungs` was loading NoobAI-XL.
- **Cause:** the product engine (`render/panels.py::IllustriousEngine`, also
  used by `NoobAIEngine`) calls diffusers' `enable_model_cpu_offload()`. That
  keeps the *whole* SDXL pipeline (UNet 5.1 GB, two text encoders 1.6 GB,
  VAE 0.16 GB) resident in system RAM and moves one submodule at a time to
  the GPU. Measured ~4.2 GB resident for the process, on a 15 GB machine
  already carrying ~17 GB of browser swap.
- **Fix (research side):** `datasets/visual_beats.py::render_gpu` loads the
  weights straight to cuda (`device_map="cuda"`, fp16) and refuses to start
  unless the GPU is free (`gpu_free`: < 1.5 GB used, nothing loaded in
  ollama). Measured on one 1024x1024 panel: anonymous RAM 1.27 GB, peak VRAM
  6.58 GB, ~45 s including model load. The image is visually identical to the
  product engine's at the same seed.
- **Lesson:** CPU offload trades VRAM for RAM. On an 8 GB card with
  16 GB of RAM it moves the problem rather than solving it. Check the GPU,
  load to it directly, free it before the next model.
- **Open product item:** the product engine still uses CPU offload. The same
  GPU-direct loading (with the VAE fix in 3) would cut its RAM by ~3 GB.
  Not changed in this pass: product changes need their own render
  verification (`data/novels/<CODE>/panels/.../VERSIONS.md`).

### 2. My first OOM diagnosis was wrong

- **Symptom:** the GPU-direct render OOMed with 6.89 GB allocated.
- **First hypothesis:** the text encoders were not freed (6.89 matches
  UNet 4.93 + VAE 0.16 + encoders ~1.6). Moving encoding into a subprocess
  did not change it (6.85 GB).
- **Actual cause:** found from the traceback, not the arithmetic -- the OOM
  was in the VAE *decode*, asking for a 1 GiB buffer.
- **Lesson:** a plausible memory sum is not a diagnosis; read where the
  allocation fails. The subprocess encode was kept anyway: a process exit is
  the one release that cannot leak.

### 3. `enable_vae_tiling()` does nothing at 1024x1024

- **Cause:** in diffusers 0.39 the pipeline-level call is deprecated, and
  even on the VAE module, tiling only engages above `tile_sample_min_size`,
  which defaults to 1024 for SDXL. A 1024x1024 panel never tiles, so the
  decode materialises full-resolution activations while the UNet is still
  resident.
- **Fix:** `vae.enable_tiling()` plus `vae.tile_sample_min_size = 512` and
  `vae.tile_latent_min_size = 64`.
- **Lesson:** "tiling enabled" is not "tiling happening"; check the
  threshold.

### 4. VmRSS overstates memory pressure

- The same render showed 3.8 GB `VmRSS` but 1.27 GB `RssAnon`. The difference
  is the memory-mapped safetensors pages: file-backed and reclaimable, so they
  do not push anything to swap. Watch `RssAnon` (and swap) when judging
  whether a job hurts the rest of the machine.

### 5. A pre-registered method failed because of a sign bug (H-LEVER)

- **Symptom:** the "leverage" correction policy fixed fewer errors than
  random (0.46 vs 1.46 per window).
- **Cause:** leverage was the passage's comprehension change if a line's
  voice were swapped, measured against the *current* rendering. For a line
  that is already wrong, swapping it often helps, so 52% of wrong lines got
  negative leverage (against 8.5% of correct lines) and were never chosen.
- **Fix:** use the magnitude of a line's influence (v2, flagged in the
  registry and DECISION_LOG as a disclosed post-hoc deviation; v1 artifact
  kept).
- **Lesson:** "what would fixing this change?" must not be measured relative
  to a state that already contains the error. Pre-registration made this
  visible instead of quietly tuned away.

### 6. A rational listener never does worse than no information (H-IOL)

- Expected: a full cast with many errors falls below a single narrator (the
  H-COST crossover). The ideal-observer model never crosses within 60%
  errors in 22 of 24 parameter settings: it learns that voices became
  unreliable and falls back to the prior.
- **Lesson:** a crossover in people would mean listeners *over-trust* voice
  cues. That turns H-COST's crossover question into a test of listener
  rationality, which is a sharper question than "do errors hurt".

### 7. Stub runs silently tested nothing

- `ideal_listener` and `confusion_casting` ran green in stub mode on day one
  but produced 0 windows and 0 errors: the synthetic novel was too small for
  the passage filter, and the synthetic ladder makes no errors.
- **Fix:** filter thresholds are parameters, and the stub plants addressee
  captures.
- **Lesson:** a determinism test that passes on empty output proves nothing;
  check that the stub exercises the code.

### 8. The first visual design never truncated anything

- My first prompt builder produced ~45-token prompts, so the "does the error
  survive the CLIP budget" stage could not fire. Real product prompts measure
  a median of 154 tokens before fitting.
- **Fix:** stimuli go through the product's own `build_image_prompt` (style
  anchor 14 tokens, framing, sleeves clause, locale in tier 3). The setting
  is then dropped in 2/20 committed prompts and 10/20 silhouette prompts.
- **Product insight:** a withholding directive (silhouette, distant) sits in
  tier 1 and pushes the *locale* out, so silhouette fallback panels lose
  their setting about half the time.

### 9. Product prompt observation

- "A woman reads a letter in a candlelit library" rendered as a figure
  sitting in a giant black bowl under candlelight: the ink-painting style
  anchor dominates the setting. Recorded as a product quality note; not
  fixed here.

### 10. Confusion-aware casting died for the predicted reason (H-CCAST)

- The pairs the attributor confuses are the pairs that talk to each other,
  which are the pairs a listener most needs to tell apart. Predicted
  confusion correlates 0.96 with that need, so masking errors and keeping
  correct lines distinct are the same knob. The pre-registered risk note
  said this before the run.

### 11. Prior art can kill a hypothesis before any code (H-JUDGE-A)

- "Audio-LLM judges miss voice-only misattribution" was already shown by
  SpeakerSleuth (arXiv 2601.04029: 12 audio LMs prioritise text over
  acoustics and miss even gender switches) and HEAR. A targeted search
  saved building a stimulus pipeline and the API spend.

### 12. Workflow friction

- **Fact-forcing hook:** a local hook demands a facts statement before every
  first write of a new file, so each new module needs a retry.
- **Shared GPU:** ollama and diffusion cannot share the 8 GB card, so the
  experiment order is: render, CLIP probes, release, then llava.
- **CPU fan-out:** 8-worker pools pushed the load to ~12. Cap the workers
  when the owner is working.
- **torchvision:** `transformers` warns that the CLIP processor wants
  torchvision; it falls back to PIL, which is fine.

### 13. Background jobs have a 2-hour ceiling

- The tool that runs background commands stops them at 2 hours. The visual
  batch (about 260 renders at 27 s, then about 1,000 llava calls, then 60
  more renders) needs about 3 hours, so it would have been killed in the
  middle of probing.
- **Fix:** `data/scratch/research/visual_batch.sh`, launched with
  `setsid nohup`. It writes per-step exit codes to `visual_batch.status`.
  Renders are cached by (prompt, seed, engine), so a rerun resumes.
- **Lesson:** estimate total wall time *before* launching, against every
  limit in the chain.

### 14. The GPU guard checked once; another model arrived mid-run

- Twenty-one images into the batch, another process on the machine loaded
  `qwen3:8b` into ollama (1.7 GB of VRAM, about 4 GB of RAM, 400% CPU). The
  render then OOMed asking for 256 MiB. The *second* step's startup guard
  correctly refused to run (`GPU not free ... ollama models loaded
  ['qwen3:8b']`).
- **Lesson:** a free-GPU check is a snapshot. On a shared workstation the
  GPU is a shared resource, so either schedule GPU batches with the owner,
  or make the job check between phases and pause cleanly. The renders are
  cached, so the 21 finished images are not lost.
- **Decision:** the owner schedules the GPU window; the batch waits for
  their go.

## 2026-10-03: visual batch

### 15. An automatic probe must pass its own manipulation check first

- **Symptom:** H-VRUNG run 1 reported "committed rung fails to commit"
  (gender 0.55, hair 0.70). A KILL by the letter.
- **Cause: the instrument, not the images.**
  - The llava gender question offered "unknown", and llava answered
    "unknown" on 85% of *committed* panels.
  - A forced "black or blonde" choice then answered "black" for 7 of 8
    blonde figures (option-order bias).
  - CLIP's 0.95 gender "recovery" included panels with no person at all,
    so it was partly guessing.
- **How it was found:** by looking. Contact sheets of the panels
  (`scratchpad/sheet_*.png`) took two minutes.
- **Fix:** both questions were validated on the 16 committed panels that
  visibly contain a person.
  - Forced-choice gender (man/woman) scores 15/16.
  - An open colour word for hair, parsed (blond, yellow, white -> blonde),
    scores 15/16.
  - Abstention is read from a separate "is there a person" question.
- **Handling:** run 1 is kept as the invalid-instrument run. The re-scored
  run has `probe_version: 2` in its config hash.
- **Lesson:** validate every automatic judge on cases where the answer is
  known *before* it decides a pre-registered kill. "The image is
  ambiguous" and "the probe is broken" look identical in a summary
  statistic.

### 16. My own probe blocked my next experiment

- llava stays resident in ollama for 5 minutes after the last call. The
  next experiment's free-GPU guard saw `llava:7b` loaded and refused to
  render.
- **Fix:** probes use `keep_alive: 30s`, and `llava_unload()` runs after
  each probe loop.
- **Lesson:** a resource guard must account for your own leftovers too.

### 17. Product findings from looking at 60 product-style panels

All three are findings about the product's own prompt assembly and
NoobAI-XL with the guofeng/ink style anchor. None is fixed here:

- **Male figures disappear.** "1boy" plus the ink style drew *no person*
  in 4/10 male committed panels (scenery only) and only a tiny figure in
  2 more. Female panels: 10/10 drawn. The same headcount tag behaves very
  differently by gender.
- **Content drift.** "from behind / back view" produced bare backs in
  every back-view panel, and some committed female panels drifted toward
  partial nudity. A product-safety issue for the negative prompt.
- **Silhouettes leak hair colour** through the rim glow (blonde figures
  glow gold).

### 18. A library major version changed a return type

- **Symptom:** `CLIPModel.get_image_features` returns a
  `BaseModelOutputWithPooling` in transformers 5, not a tensor. H-JUDGE-V
  crashed after all 60 renders.
- **Fix:** take `image_embeds` / `text_embeds` from a full forward pass.
  Sanity check: intended description 0.120 vs an unrelated caption 0.004.
- **Lesson:** run a one-image smoke test of every scoring path *before* a
  long render, not after.

### 19. A 7B VLM can be a constant function

- **Symptom:** llava:7b answered "1" to every "rate 1-10" prompt (it echoes
  the first number in the prompt), even for "a red sports car" against an
  ink-painting figure. Rephrased as yes/no, it answered "no" to every
  description, the correct one included.
- **Lesson:** check that a judge's output *varies* before computing an
  AUROC. A constant judge gives exactly 0.5, which looks like a result.

### 20. `keep_alive` on a request does not always free the model on time

- **Symptom:** H-XDIS sent `keep_alive: "30s"` with every call, yet
  `qwen2.5:7b` was still resident (4.9 GB of VRAM) after the run ended.
- **Fix:** an explicit unload,
  `curl localhost:11434/api/generate -d '{"model":"qwen2.5:7b","keep_alive":0}'`.
  Then confirm that `/api/ps` is empty.
- **Lesson:** end every GPU job with an explicit release and a check, not
  a timer.

### 21. Save the join keys you will need later

- H-XDIS saved confidence, disagreement and correctness, but not the gold
  speaker, quote type or candidate shortlist. Every follow-up then has to
  re-derive them.
- **Fix used here:** a deterministic re-derivation behind an exact-match
  gate (1000/1000 rows). That works only because the probe is
  deterministic.
- **Lesson:** an experiment's trials should carry every field a plausible
  follow-up stratifies on.

### 22. The gold label itself was the confound

- 58/1000 PDNC gold speaker strings ("Kemp", "Lucy") are not keys in
  PDNC's own character list.
- The ladder can never be scored right on those rows, and the LLM cannot
  pick the gold either. Both "error" and "disagreement" fire through the
  same name-format mechanism.
- It surfaced only because I checked an assertion I had written
  confidently ("the gold is always in the shortlist by construction").
- **Lesson:** check every "by construction" claim against the data. A
  shared artifact between a signal and its label inflates any detector.

### 23. The parser, not the model, made half the "disagreements"

- H-XDIS reported qwen at 0.763 accuracy with 149 unparsed answers. All
  of them counted as disagreement.
- On 137 of the 149, qwen answered with the name form the passage itself
  uses ("Syme", "Pooh", "Miss Howard"). The candidate list held PDNC
  *main names* ("Gabriel Syme", "Winnie-the-pooh").
- The parser looks for a candidate string inside the answer, so it never
  matched those answers.
- The convergence pass built the list from text surfaces instead
  (H-XDIS-PS). Accuracy rose to 0.919, and only 9 answers were unparsed.
- **Lesson:** when an LLM answer is matched against a list, measure how
  often the answer is a *variant* of a list entry before reading
  "unparsed" as "disagree". A gold-derived list is not automatically the
  easier condition.

### 24. GPU sharing with another ollama client

- During the convergence pass another client held qwen2.5:7b on the card
  (about 5 GB, 50-97% utilisation) for more than 2 hours.
- The poll (5 minutes; idle = < 600 MiB and < 10% utilisation, twice in a
  row) hit the 2-hour background limit and was stopped. A manual check
  afterwards found the card idle.
- **Lesson:** a GPU wait longer than 2 hours needs re-arming. CPU-side
  preparation (shortlist audit, model downloads, prior-art search) is
  what made the wait cost nothing.

### 25. A runaway TTS render breaks fixed-window ASR

- One Chatterbox render of a line of at most 220 characters ran past
  30 s. whisper-small via transformers then refuses the input unless
  `return_timestamps=True`.
- That render is itself a fidelity failure, which WER now records. It
  also inflated the narrator's mean WER (0.145 vs 0.086).
- **Lesson:** budget for runaway generations in any measurement over TTS
  output. Report duration as a fidelity check, not only as a cost.

### 26. An empty LLM answer is not an answer

- In the S1 rerun, the only 2 live qwen2.5 calls (the GPU had been used by
  another client just before) both returned `""`. That parses as
  "unparsed", which counts as disagree.
- Re-asked directly a minute later with the same prompt, qwen gave a real
  name ("Adye"). The empty strings were transient, probably model-load
  timing.
- **Fix used here:** drop empty responses from the cache and re-ask.
- **Lesson:** an empty response should be retried, not scored. A
  deterministic setting (temperature 0, seed 0) does not make the serving
  stack deterministic.
