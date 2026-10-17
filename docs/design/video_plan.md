# Motion video plan: from held panels to moving shots

**Status: plan only, 2026-10-18. Nothing in this document is built.** The
model figures in Section 3 are a mix of things checked against model cards,
second-hand write-ups and things I do not know. Each one is marked, and none
of them has been measured on this machine (RTX 4060 Laptop, 8 GB VRAM, 15 GB
system RAM). Measuring them is the first job of milestone M3.

Read this alongside `docs/design/VISUAL_RENDERING.md` (the image path), `docs/EVOLUTION.md`
4.23 (the original Phase 9 video design), 4.31 and 4.37 (the author's
watch-throughs) and Section 9 (the 8 GB VRAM conflict between ollama and
diffusion).

---

## 1. What the video path does today

The pipeline, as wired in `commands.py::cmd_render`:

1. **Panels.** `render/panels.py::render_panels` writes one still per beat
   (`render/beats.py::segment_beats`, at most `DEFAULT_MAX_PANELS = 70` per
   chapter) at 832x1248 (2:3 portrait). With `config.json::render.direction_first`
   it runs in two passes. Phase 1 calls the LLM director
   (`render/direction.py::direct_beat`, returning a `PanelDirection` with
   `shot`, `action`, `layout`, `setting`, `lighting`, `mood` and `expression`)
   against a stub image engine and writes `prompt_cache.json`. Then
   `unload_ollama_models` runs. Phase 2 runs NoobAI XL 1.1 from that cache
   with no LLM calls. The manifest row (`PanelImage`) stores the final
   prompt string but **not** the structured `PanelDirection`, so the
   shot size survives only as text inside the prompt ("medium shot").
2. **Motion library.** `render/motion.py::build_motion_library` builds
   at most one clip per tag in a fixed vocabulary (`clash`, `wind`, `flame`,
   `impact`, `idle`). Each clip is a 24-frame PNG sequence at 12 fps, and the
   library is reused across the chapter. `SVDEngine` wraps
   `stabilityai/stable-video-diffusion-img2vid` with `enable_model_cpu_offload`.
3. **Shot plan.** `render/director.py::build_shot_plan` makes one `ShotPlan`
   per block that has a panel. It is `kind="pan"` with a deterministic
   `pan_direction`: dialogue gets `zoom_in`, description gets `pan_left`/`pan_right`
   by parity, and anything else gets `zoom_out`. Exactly two blocks per
   chapter (`CLIPS_PER_CHAPTER`, chosen by `score_blocks`' three tiers) are
   `kind="clip"` instead.
4. **Timeline.** `render/timeline.py::build_timeline` sums each block's
   per-line WAV durations from the voice manifest (`voice/runner.py::AudioLine`
   rows in `audio/manifest.jsonl`, one WAV per span). The picture follows the
   speech, never the other way round. A block without a panel carries the
   previous shot forward (`carried_over=True`).
5. **Compose.** `render/compose.py::FfmpegComposeEngine` renders each shot to
   its own segment. Stills go through `_zoompan_filter`, a linear 1.00 to 1.08
   zoom or a 3% pan at scale 1.05 (constants in `director.py`, marked
   `# TUNING`, first guesses). Clips loop their frames. The segments are
   then concatenated, the WAVs joined (`concatenate_audio`), and the `.ass`
   captions from `render/captions.py` burned in, giving 1080x1920 at 30 fps.
6. **Orchestration.** `render/runner.py::render_videos` reads the root panel
   manifest and the voice manifest and writes `video/ch<N>.mp4`. The Studio
   (`jobs.py::_dispatch`) has `render` (panels only) and `voice` jobs, but
   **no video/compose job**.

**Defects found while reading the code for this plan.** These come from
reading the code, not from running it:

- **The real SVD engine can never produce a clip from the CLI.**
  `build_motion_library` skips any tag that has no `seed_images` entry when
  the engine is not the stub. `cmd_render` calls it without `seed_images`,
  and nothing else in `packages/` passes them. That matches EVOLUTION
  Section 9's unexplained "`0` motion clips despite `--motion-engine svd`". It
  also matches what is on disk: `data/novels/LOTM/motion/ch1/v1/manifest.json`
  is `{}`, and `data/novels/RI/motion/ch1/v44/` holds stub clips (solid colour
  frames).
- `SVDEngine.generate` calls `.resize((1024, 576))` on a 2:3 portrait panel,
  which **stretches** it to 16:9. `compose.py` then crops that back to 9:16,
  keeping about a third of the width.
- `compose.py::_render_segment` hard-codes `-framerate 12` and ignores
  `MotionClip.fps`.
- Motion manifests store stale pre-migration paths (`data/RI/motion/...`).
- `SVDEngine` and the NoobAI/Illustrious engines use `enable_model_cpu_offload`.
  That conflicts with the owner's 2026-10-02 rule: heavy models load straight
  onto the GPU, and nothing parks weights in system RAM.
- **Known ffmpeg behaviour, not yet checked on our output:** `zoompan` rounds
  its crop offset to whole pixels. A slow 8% zoom over 10 s or more moves less
  than one pixel per frame, so it tends to visibly stutter. The usual fix is
  to upscale before `zoompan` or to apply a sub-pixel transform outside ffmpeg.

**What a viewer sees today.** One panel held for the whole of a beat's
narration. A beat can run 20 s or more, because a beat covers up to 14
blocks. The only motion is a small linear drift, plus at most two cutaways
that are currently placeholders. The newest real chapter video is
`data/novels/RI/video/ch1/v5_2026-08-15_watched-review`, and it predates all
of the beat, crowd and relevance work (`data/novels/RI/README.md`).

---

## 2. Target experience, in stages

**Stage A: 2.5D motion on the existing panels (no new generated pixels).**
- **A virtual camera that covers a long beat.** Split one keyframe into
  several shots: wide, then medium on the speaker, then close. Each cut lands
  on a voice-line boundary inside the beat. This is how a held panel stops
  reading as a gallery, and it needs no GPU.
- **Camera moves chosen by shot size and beat type.** Use eased (not linear)
  push-in, pull-out, pan and tilt, plus a short shake on impact lines. The
  move's intensity comes from the line's delivery markers
  (`spans/delivery.py`). That is non-negotiable 10: delivery markers override
  scene sentiment.
- **Depth parallax.** A monocular depth map per keyframe drives a small mesh
  or grid warp, so the foreground moves against the background. Keep the
  amplitude small so that disocclusion holes stay a few pixels wide and can be
  stretched rather than inpainted (see Section 5 on why not inpaint).

**Stage B: image-to-video clips per beat, from the panel keyframe.**
- A 2 to 4 s generated clip, conditioned on the NoobAI panel, for a
  **budgeted** subset of shots per chapter: action peaks and long holds.
  This is the same selection idea as `director.py::score_blocks`. Everything
  else stays Stage A. Full i2v coverage does not fit the time budget at
  70 beats x 199 chapters (Section 8).
- Frame interpolation (RIFE) takes the model's native 8 to 16 fps up to the
  30 fps output.

**Stage C: longer continuity and character consistency.**
- Chain shots within a scene: the next clip starts from the previous clip's
  last frame, or uses first-and-last-frame conditioning where the model
  supports it. Re-anchor on a fresh NoobAI keyframe after a fixed number of
  chained clips.
- An identity gate per clip. A clip that drifts from its keyframe falls back
  to its Stage A shot, and that fallback rate is reported, in the same spirit
  as non-negotiable 7.

---

## 3. Model options for 8 GB, local, no CPU offload

**The hard constraint is the combination**: 8 GB of VRAM, *no*
`enable_model_cpu_offload` or sequential offload, and only 15 GB of system
RAM (about 4 GB was free when I checked). Many "runs on 8 GB" claims online
depend on ComfyUI or diffusers offload, which is exactly what is ruled out.
The way round it is **staged loading**. Encode every motion prompt for a
chapter with the text encoder on the GPU, save the embeddings to disk, free
the encoder, then load the video transformer and VAE. Each model sits fully
on the GPU, one at a time. Transient RAM use during a `safetensors` load is
unavoidable, but resident offload is not needed.

| Option | What it does | VRAM on 8 GB without offload | Speed | Quality fit for this project | Licence |
|---|---|---|---|---|---|
| **Depth Anything V2 Small** + grid warp | monocular depth, then 2.5D parallax | small (about 25M parameters, well under 1 GB, *unmeasured*) | fast; depth is about once per keyframe, and the warp is cheap with `torch.grid_sample` on the GPU | keeps NoobAI's pixels exactly; artefacts at depth edges and on hair and sleeves | Small checkpoint Apache-2.0; **Base and Large are CC-BY-NC-4.0** (check the card) |
| **RIFE** (Practical-RIFE) | frame interpolation | small (*unmeasured*) | fast | good for small motion, smears large motion | MIT (check the repo) |
| **FILM** | frame interpolation | moderate (*unmeasured*) | slower than RIFE | better on large motion | Apache-2.0 (check) |
| **SVD img2vid** (14 frames) / **-xt** (25) | image-to-video, no text prompt; motion set by `motion_bucket_id` | *uncertain*: about 1.5B UNet in fp16 plus a CLIP image encoder. Plausible at reduced resolution with `decode_chunk_size` of 1 to 2; 1024x576 without offload is unverified | *unmeasured* here | trained on landscape footage; tends towards camera drift and melting on stylised art (*community reports, unverified*) | Stability AI Community Licence (commercial use below USD 1M annual revenue, registration required) |
| **LTX-Video 2B** (0.9.x, distilled) | text and image to video; **supports image conditioning** | *uncertain*: about 2B parameters (about 4 GB in bf16) plus a T5-XXL text encoder that must be staged out first | fast for its class per the vendor; *unmeasured* | arbitrary resolution in multiples of 32, so portrait works; style fidelity to ink wash unknown | LTXV Open Weights Licence (source-available; read the commercial terms) |
| **Wan 2.1 T2V-1.3B** | **text-to-video only**; image conditioning in the 1.3B size comes via VACE-1.3B (*check*) | official figure 8.19 GB peak (for T2V at 480p, *with the repo's own offload flags; check*) | slow (minutes per 5 s clip on large cards) | strong motion for its size; I2V-14B is the real i2v model and is out of reach | Apache-2.0 (per listings; check the official repo) |
| **Wan 2.2 TI2V-5B** | text or image to video, 720p at 24 fps | 5B in bf16 is about 10 GB of weights, so **it does not fit without fp8 or GGUF quantisation**; the "8 GB" claims rely on ComfyUI offload | reported about 9 min per 5 s 720p clip on a 4090 (second-hand) | best quality in this list if it can be made to fit | Apache-2.0 per a third-party listing; check the official card |
| **CogVideoX-2B** | **text-to-video only** (the I2V model is 5B) | the card's "4 GB" assumes offload; about 3x that without it (per the card) | slow | dated relative to Wan and LTX | Apache-2.0 for 2B per listings (5B uses the CogVideoX licence; check) |
| **CogVideoX-5B-I2V / 1.5-5B-I2V** | image-to-video | about 10 GB bf16 and about 7 GB int8 per a mirror; *uncertain* | slow | fair | CogVideoX licence (check) |
| **AnimateDiff on SD1.5** (v3 motion module, SparseCtrl RGB for keyframes) | animates an SD1.5 checkpoint | fits at 512x768 (*plausible, unmeasured*) | moderate | **the base would be GuoFeng3, not NoobAI**, which repeats the reversal EVOLUTION records for the manga engine | Apache-2.0 (motion modules; check) |
| **AnimateDiff-SDXL / Hotshot-XL on NoobAI** | motion module inserted into NoobAI's own UNet | *uncertain*: SDXL at 16 frames likely exceeds 8 GB at 832x1248, so it needs a lower resolution where SDXL degrades | slow | **the only i2v-like route where the image model stays NoobAI**; SDXL motion modules are beta-quality (*community view*) | check each module |
| **FramePack** (HunyuanVideo-based, 13B) | long i2v at a "6 GB" headline | **excluded**: the 6 GB depends on heavy CPU offload of 13B weights, which the RAM rule and the 15 GB machine rule out | n/a | n/a | check |

**Owner decision needed before Stage B.** Any i2v model is a *second model
writing pixels for the shot*. The 2026-08-20 rule is "single model per panel,
no repaint pass". The keyframe stays a pure NoobAI image, but the clip's
frames would not be. Depth parallax and RIFE do not repaint content, so I
read Stage A as inside the rule. Stage B needs an explicit yes, and
AnimateDiff-on-NoobAI is the option to raise if the answer is "NoobAI only".

**Cloud.** The 2026-10-17 note says local models only (no RunPod, no OpenAI
key). This plan budgets **$0 of cloud**. If the owner reopens it, the $5 to
$10 envelope would cover a one-off comparison clip from a larger model at
most, not a production path.

---

## 4. How shots are decided

**Reuse, don't re-derive.** Beats (`render/beats.py`), scenes
(`render/scenes.py::group_scenes`), the director's `PanelDirection` and the
voice manifest already hold every input. The new piece is a **shot list**
that sits between `director.py::build_shot_plan` and `compose.py`, and
replaces `ShotPlan`/`TimedShot` once it is proven. Until then it is built
alongside them so the old path keeps working.

**Prerequisite:** persist `PanelDirection` (at least `shot`, `action`,
`layout`, `mood` and `expression`) into the `PanelImage` manifest row, next
to `prompt`. Today it exists only inside phase 1 of the two-phase render.

### `ShotSpec` (new, `render/shots.py`)

```
ShotSpec
  chapter, shot_id ("c1:b12:s2"), beat_index, block_indices, span_ids
  start, end                   # seconds, from the voice manifest's WAV durations
  keyframe_path, keyframe_cache_key   # the PanelImage this shot is cut from
  shot_size: wide|medium|close        # PanelDirection.shot, else parsed from the prompt
  crop: {cx, cy, scale}               # the virtual-camera framing inside the keyframe
  camera: {move: static|push_in|pull_out|pan_l|pan_r|tilt_u|tilt_d|orbit|shake,
           intensity: 0..1, easing: linear|ease_in_out}
  mode: kenburns|parallax|i2v
  motion_prompt: str                  # fitted to the target engine's encoder budget
  seed: int                           # hash(novel, chapter, shot_id), as reference_gen._seed_for does
  transition_in: cut|crossfade|whip
  fallback_mode: kenburns|parallax    # what to render if the i2v clip fails its gate
  provenance: {panel_version, voice_manifest_digest, engine, model_id}
```

### Rules, all deterministic and all `# TUNING` until watched

1. **Split long beats at line boundaries.** A beat longer than about 6 s
   (`director.LONG_BLOCK_SECONDS`) is split into shots of 2.5 to 6 s, cutting
   only between `AudioLine`s. A cut never lands mid-sentence. Every line's
   start time is already known: it is the cumulative sum of WAV durations,
   because `compose.py` joins the WAVs back to back.
2. **Coverage order inside one keyframe.** The first shot follows
   `shot_size`. Later shots tighten: wide, then medium, then close on the
   subject region. For a dialogue line, the subject region is the speaker if
   they are in the panel's cast. Locating a figure needs a detector (a person
   or anime-face detector, or the depth map's nearest connected region). That
   is *uncertain*, so default to a centre-weighted crop and measure how often
   it misses.
3. **Camera move.** Description holds get a slow pan or tilt (tilt suits the
   2:3 to 9:16 crop, which leaves vertical travel). Dialogue gets a push-in
   on the speaker. Action gets a pull-out, or a short shake on a heightened
   impact line. Aftermath gets a slow pull-out. Intensity follows the
   delivery markers, not scene sentiment.
4. **Mode assignment.** Parallax is the default once M2 lands. i2v goes to
   the top-N shots by `score_blocks` (generalised from blocks to shots), N
   per chapter from config. That is the same competitive selection that put
   the two clips on real peaks.
5. **Transitions.** Hard cuts within a beat; a crossfade of about 0.3 s at
   scene boundaries.

### Motion prompts and the genre profile

`persona/genre.py::GenreProfile` has no motion vocabulary. Add two fields,
with any per-novel `attire.py` entry winning as it does for every other
field:

- `ambient_motion`, for example xianxia "robes and hair drifting, mist
  moving, falling leaves"; victorian_gothic "gaslight flicker, fog, rain";
  modern_apocalypse "dust, sparks, flickering lights".
- `camera_temperament`: limits on shake and speed. Victorian gothic is slow
  and steady; modern apocalypse allows handheld shake.

For i2v, **the keyframe already carries identity and style**. The motion
prompt should describe *motion only*: the camera move, the subject's action
(from `PanelDirection.action`) and the ambient motion. It should not restate
appearance. Assemble it as priority tiers through
`persona/prompt.py::fit_tiers_to_budget`, generalised with a tokenizer
parameter: CLIP's 75 usable tokens for AnimateDiff on NoobAI, and T5 limits
for LTX, Wan and CogVideoX (exact limits per model, *check*). SVD has no
text input; `camera.intensity` maps to `motion_bucket_id` and
`noise_aug_strength`. As everywhere in this codebase, check what survives
truncation, not what was appended.

---

## 5. Character and style consistency across clips

IP-Adapter is permanently removed (EVOLUTION 4.47: the sheets carried their
colours and compositions into every panel and did not generalise). The
consistency levers that remain:

1. **The keyframe is the identity.** Every i2v clip starts from a NoobAI
   panel whose appearance clause is the existing consistency mechanism.
   Short clips (2 to 4 s) bound how far a face can drift.
2. **Re-anchor, don't chain forever.** Stage C chains at most K clips from
   generated last frames (K starts at 1 and is measured), then returns to a
   fresh NoobAI keyframe. Drift compounds across chained generations.
3. **First and last frame conditioning**, where the chosen model supports
   multi-keyframe input (LTX-Video advertises frame conditioning at
   arbitrary positions, *check the version*). Both ends of the clip are then
   NoobAI images.
4. **Deterministic seeds** per shot (`hash(novel, chapter, shot_id)`), so a
   re-render reproduces the take and an A/B compares settings, not luck.
5. **An identity gate with fallback** (Section 7). A clip below threshold
   renders as its Stage A shot, and the fallback rate is reported.
6. **Reference sheets are a measurement tool, not a conditioning input.**
   `persona/reference_gen.py` sheets can serve as the gallery that
   identity-similarity scores are computed against. They must not be fed
   back into generation: they are diffusion outputs that drifted, which is
   why IP-Adapter was removed.

**Considered and not proposed:** a per-character LoRA trained on reference
sheets would bake the sheets' drift into NoobAI's weights, and it adds a
training pipeline. Raise it only if keyframe conditioning measurably fails.
Inpainting parallax holes with another model breaks the single-model rule;
keep parallax small instead.

---

## 6. Pipeline changes

**New modules** (under `packages/pipeline/src/echotales/pipeline/render/`;
nothing in `core`, preserving `test_import_direction.py`):

- `shots.py`: `ShotSpec` and `build_shot_list(...)`, built from beats,
  scenes, panel manifest rows (with the persisted direction) and audio lines.
- `camera.py`: eased camera paths, plus a sub-pixel renderer that pipes raw
  frames into ffmpeg (`-f rawvideo` on stdin). This avoids `zoompan`'s pixel
  snapping and the cost of writing PNGs. A 10-minute chapter is 18,000
  frames at 1080x1920.
- `depth.py`: `DepthEngine` Protocol with stub and Depth Anything V2 Small
  backends, caching one `.npy` per keyframe under the video version.
- `parallax.py`: the depth-driven grid warp, with a hole-size measure that
  becomes an eval metric.
- `motion.py`, extended rather than replaced: `MotionClipRequest` gains
  `motion_prompt`, `seed`, `fps`, and portrait `width`/`height` derived from
  the keyframe aspect (fixing the stretch). The engines become `stub`,
  `svd`, and one more, chosen after the M3 spike. Every real engine loads
  straight to `cuda` in fp16 with `low_cpu_mem_usage`, with no offload.
- `interp.py`: RIFE backend with a stub.
- `compose.py`: a `ShotSpec`-driven path that renders kenburns, parallax and
  i2v segments; read `fps` from the clip; crossfades with `xfade` at scene
  boundaries.

**Config split** (no third mechanism). `config.json` gains a hand-edited
`video` block:

```json
"video": {
  "motion_mode": "kenburns",
  "i2v_engine": "none",
  "i2v_clips_per_chapter": 0,
  "depth_engine": "depth-anything-v2-small",
  "interp_engine": "rife",
  "identity_gate": 0.0
}
```

mapped in `config.py` the way `render.direction_first` is, with CLI flags
overriding. `.env` gets nothing new: no hosts are involved.

**A separate `video` stage.** Today `cmd_render` versions the video output
with the *panel* version, so one panel set cannot have two motion takes. Add
`echotales --db <db> video --novel <id> --chapters N --mode parallax
--suffix <name>`, which reads a named panel version and the voice manifest.
`render --skip-compose` and the existing compose path stay as they are until
the new stage replaces them.

**Versioned output.** Write to `data/novels/<CODE>/video/ch<N>/vN_<suffix>/`
via `paths.asset_dir(novel, "video")` and `paths.next_version`. A suffix is
**required**: the stage refuses to run without `--suffix`, because the
v10 to v40 panel history shows what happens otherwise. Each version holds
`ch<N>.mp4`, `ch<N>.ass`, `shots.jsonl` (the `ShotSpec` list, with a header
naming the panel version, voice manifest digest and engines), `depth/`,
`clips/` and `eval.json`. The run appends one line to
`video/ch<N>/VERSIONS.md` when it finishes, following the format in
`data/novels/RI/panels/ch1/VERSIONS.md`; the viewer's verdict is filled in
after it has been watched.

**Jobs and the Studio.** Add a `video` job kind to `jobs.py::_dispatch`,
naming and logging versions the way `_studio_version` and
`_record_studio_version` do (`vN_<mode>-studio`). Over HTTP, allow only
`stub`, `kenburns` and `parallax`, with i2v CLI-only until it has been
measured, as `ALLOWED_HTTP_ENGINES` already does for paid image engines.
The webview already serves `video` outputs with HTTP Range support
(`webview_server.py::_OUTPUT_KINDS`).

**GPU scheduling.** This extends direction-first into explicit phases, run
sequentially by the single job worker:

1. LLM direction (ollama), then `unload_ollama_models`.
2. NoobAI keyframes, then free the pipeline.
3. Depth for every keyframe in the chapter, then free.
4. Encode text for every i2v shot's motion prompt, save embeddings to disk,
   free the encoder.
5. i2v for the budgeted shots, then free.
6. RIFE.
7. CPU compose (ffmpeg).

Before each GPU phase, a `gpu_guard()` helper checks `nvidia-smi` (memory
used, no foreign compute process) and `ollama ps`, and refuses to load
rather than OOM. Run phases 3 to 6 in a subprocess, as
`persona/_img2img_worker.py` does, so the CUDA context and allocator are
fully released between models. Cap CPU parallelism at a few workers. Ask the
owner before any long real run (the RAM rule).

**Tests (stub-first, CI with no GPU):** `ShotSpec` timing sums exactly to
the audio length; cuts fall only on line boundaries; fallback when the gate
fails; version naming and the `VERSIONS.md` line; prompt fitting per
tokenizer; parallax amplitude limits.

---

## 7. Evaluation plan

Each metric below names what it can blame: the gate, the engine or the
model (owner rule 2026-10-15). Results go in `data/eval/video/<date>/` and
write-ups in `docs/results/`.

**Fixed benchmark set.** 12 keyframes and their audio. RI ch1: a solo calm
face, a wounded figure, the crowd at the massacre, a landscape. LotM ch1: an
interior and a figure lying down. ORV: a modern street. Several 30 s
excerpts are cut from the same chapters. Fixed seeds.

**Automatic metrics:**
- **Identity similarity.** Face or figure crops scored against the
  keyframe crop and against that persona's reference sheet. Use
  CLIP ViT-L/14 image embeddings; whether an anime-face embedding model is
  better here is *uncertain*, so measure it. Report the drop over each clip,
  and **separation**: mean same-character similarity across clips minus mean
  different-character similarity. A raw similarity alone says nothing
  without that baseline.
- **Style drift.** CLIP similarity and palette histogram distance
  (`render/palette.py` already reasons about palettes) between clip frames
  and the keyframe.
- **Temporal flicker.** Optical-flow warping error between consecutive
  frames (Farneback via `opencv-python-headless`, a new dependency, or RAFT
  on the GPU), compared with the Stage A shot of the same keyframe as a
  floor.
- **Parallax artefacts.** The largest and mean disocclusion hole, in pixels,
  per shot.
- **Line timing.** For every cut, the distance to the nearest line boundary
  (target 0 by construction; this checks the construction). Also the share
  of dialogue time during which the speaker's panel, or a crop on the
  speaker, is on screen.
- **Cost.** Wall-clock per second of output, peak VRAM
  (`torch.cuda.max_memory_allocated`), and peak process RSS. RSS is a
  pass/fail line given the owner's RAM rule.

**Lip sync is out of scope** (non-goals). The format is narrated manhwa with
no mouth animation, so "lip timing" here means line-to-cut timing, as above.

**Blind review protocol:**
- Show 20 to 30 s excerpts as A/B pairs of the *same* excerpt (current
  zoompan vs Stage A; Stage A vs Stage B), in random order and position,
  with file names hidden. The owner and at least two other viewers take
  part.
- Each viewer gives a forced choice ("which would you keep watching") and a
  1 to 5 rating for *feels alive*, *character recognisable* and *artefacts
  distracting*, plus a free-text defect note tagged from a fixed taxonomy:
  melting face, extra limb, style flip, swimming background, jitter, bad cut.
- **Write the decision rule down before viewing.** Stage A ships if it wins
  at least 60% of forced choices against the current path with no rise in
  "artefacts distracting". Stage B is adopted for a shot class only if it
  beats Stage A on the same shots *and* its gate fallback rate is below an
  agreed ceiling.
- Record raw votes, not just the winner.

---

## 8. Milestones, risks, first step, non-goals

Effort is in focused sessions (about half a day each), from experience of
this repo's pace, and is a rough guess.

| # | Milestone | Effort | Needs GPU | Exit criterion |
|---|---|---|---|---|
| M0 | Make the existing path honest: pass `seed_images` (each tag's best-scoring panel) or remove the dead path; stop the SVD stretch; read `fps` from the clip; drop `cpu_offload` in `SVDEngine`; refresh stale motion manifest paths; a regression test for each | 1 | no (code); yes for one SVD smoke clip | tests green; one real SVD clip on disk, or a measured OOM recorded in EVOLUTION |
| M1 | `ShotSpec` plus the line-timed virtual camera: split long beats, coverage crops, eased sub-pixel moves, `video` CLI stage, versioning, `VERSIONS.md`, `config.json` `video` block | 2–3 | no | one RI ch1 and one LotM ch1 video; blind A/B against v5-style zoompan |
| M2 | Depth parallax (Depth Anything V2 Small), hole metric, Studio `video` job | 2 | small | blind A/B against M1; peak VRAM and RSS recorded |
| M3 | i2v spike: SVD vs LTX-Video 2B vs one quantised Wan 2.2 TI2V-5B on the 12 benchmark keyframes, staged loading, no offload | 2–3 | yes | a table of VRAM, RSS, s/clip and the Section 7 metrics; owner decision on the single-model rule |
| M4 | Budgeted i2v in production (top-N shots per chapter) plus RIFE, identity gate and fallback | 2–3 | yes | fallback rate and blind A/B against M2 on the same shots |
| M5 | Stage C continuity: last-frame or first-and-last-frame chaining within scenes, re-anchoring | 3+ | yes | identity separation does not degrade across chained shots |

**What to try first:** M0's `seed_images` fix plus M1. Together they give the
cheapest high-value change. Nearly all of today's staleness comes from one
panel held for a whole beat, and line-timed coverage cuts inside the panel
address it with zero GPU, zero new models, no change to the single-model
rule, and data the pipeline already stores. M2 is the second step, because
the depth model is small and does not repaint pixels.

**Risks:**
- **VRAM, RAM and offload.** The no-offload rule may rule out every i2v
  model except SVD at reduced resolution. M3 exists to find this out, and
  "none fit" is an acceptable, recordable result.
- **Style drift.** The video models are not trained on guofeng ink wash, so
  clips may slide towards generic anime or photoreal. The style-drift metric
  and the gate catch it.
- **Time at whole-novel scale.** 70 beats x 199 chapters is about 14,000
  keyframes. If one i2v clip costs minutes (*unmeasured*), per-shot i2v for
  the whole novel would take weeks of GPU time. That is why i2v is budgeted
  per chapter and the default stays Stage A.
- **Licences.** SVD's revenue cap; LTXV's source-available terms; Depth
  Anything V2 Base and Large are NC (use Small). Each needs checking against
  the product charter before shipping.
- **Speaker localisation** for coverage crops is uncertain; the centre-crop
  default keeps M1 shippable if it fails.
- **Upstream relevance.** Motion cannot fix a panel of the wrong person
  (EVOLUTION 4.31/4.37). Evaluate motion on panels already judged relevant,
  or the blind test measures the wrong thing.

**Non-goals:**
- Lip sync or mouth animation.
- Text-to-video generation without a NoobAI keyframe.
- i2v on every shot.
- IP-Adapter or any reference-image conditioning.
- Inpainting or a repaint pass over panels.
- Training video models or character LoRAs.
- 14B-class models, FramePack and hosted video APIs.
- Re-timing the voice track to fit the picture; the picture stays locked to
  speech.
- Changing `docs/paper/project_doc`.

---

## Sources checked for Section 3 (2026-10-18; second-hand where noted)

- Wan 2.1 T2V-1.3B 8.19 GB figure: [Hugging Face mirror card](https://huggingface.co/sqwqw/wan2.1-t2v-1.3b), [Novita write-up](https://blogs.novita.ai/wan-2-1-t2v-1-3b-hardware-requirements/)
- Wan 2.2 TI2V-5B speed and VRAM claims: [Unsloth FP8 card](https://huggingface.co/unsloth/Wan2.2-TI2V-5B-FP8), [Immers listing (licence)](https://en.immers.cloud/ai/wan-ai/Wan2.2-TI2V-5B-Diffusers/), [fal guide](https://blog.fal.ai/wan-2-2-api-complete-developer-guide-to-next-generation-video-synthesis/)
- LTX-Video licence: [LTXV OWL 2025-04-17](https://scancode-licensedb.aboutcode.org/ltxv-owl-2025-04-17.html)
- CogVideoX-2B: [model card](https://huggingface.co/zai-org/CogVideoX-2b), [PromptLayer listing](https://www.promptlayer.com/models/cogvideox-2b)
- SVD licence: [img2vid-xt card](https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt/blob/main/README.md), [Stability Community Licence text](https://scancode-licensedb.aboutcode.org/stability-ai-community-2024.html)
- FramePack 6 GB claim: [stable-diffusion-art guide](https://stable-diffusion-art.com/framepack/)
- Not checked online this session (from prior knowledge, marked "check" above): Depth Anything V2 licences, RIFE and FILM licences, AnimateDiff module licences, LTX multi-keyframe conditioning, Wan VACE-1.3B.
