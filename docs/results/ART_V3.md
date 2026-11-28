# Art bake-off v3 (2026-11-28): code ready, GPU run pending

Branch `claude/art-v3` (from `claude/adaptation-director`). Owner decision 2026-11-28: every local method may be used to reach a real manhwa or anime look (NoobAI, Illustrious, character LoRA, ControlNet, IP-Adapter); the art model is chosen only by side-by-side quality against the real manhwa. NoobAI is no longer comparison-only for local output. Nothing here has been run on a GPU: the session that wrote it was forbidden to load a model. Everything below marked "not measured" is exactly that.

## What was built

| Piece | File |
|---|---|
| Arm C2 tag compiler | `packages/pipeline/src/echotales/pipeline/render/drama_tags.py` (`compile_c2`, `identity_tags`, `scene_tags`) |
| Illustrious profile | `render/compiler.py` `PROFILES["illustrious-xl-0.1"]` (plus an `engines/registry.py` entry, so `model_profile()` accepts it; the default stays Z-Image) |
| SDXL art worker (checkpoint, LoRA, img2img, ControlNet) | `render/_sdxl_art_worker.py`, `render/sdxl_control.py` |
| LoRA trainer | `scripts/art/train_character_lora.py` |
| Training-set builder | `scripts/art/build_lora_set.py` |
| Bake-off v3 driver | `scripts/eval/art_bakeoff_v3.py` |
| Tests (47) | `packages/pipeline/tests/test_art_v3.py` |

## Arm C2

Same Panel and PanelBrief as B2, compiled to Danbooru tags in priority order: quality, count, LoRA trigger, identity, shot, scene, drama. Identity tags come from the cast look facts (`CharacterBrief`: gender, age band, hair, eyes, features, attire, condition, expression, pose), scene tags from the panel's own composition, place, light and visual text. The drama vocabulary is B2's: dutch angle, from below, foreshortening, chiaroscuro, rim light, backlighting, speed lines, ink wash, one accent per layer. The B2 rules carry over, with a negative prompt doing the work Z-Image cannot do:

- empty cast: `no humans`, and `1boy, 1girl, person, silhouette, face, hands ...` in the negative;
- eyes-only: `solo, extreme close-up, eye focus, eyes, macro, reflection`; `nose, mouth, lips, forehead, body ...` in the negative;
- imagined or referenced inset: `solo, simple background, black background, floating, <glow> aura`, no scene tags, `background, scenery, landscape, room ...` in the negative;
- age and gender are tags (`teenager, youthful, slim`; `middle-aged, mature male, wrinkles`; `old man, wrinkled skin, white hair`), and a crowd gets `6+boys` with no `1boy`.

Illustrious gets the same tags with `masterpiece, best quality, amazing quality, very aesthetic, absurdres` and without NoobAI's `score_*` tags.

Compiled prompts (NoobAI, positive):

- p12 eyes only: `score_9, score_8_up, score_7_up, very aesthetic, absurdres, solo, extreme close-up, eye focus, eyes, close-up, macro, reflection, night, lantern, chiaroscuro, dramatic lighting, hard shadows, high contrast, ink wash, sumi-e, dark, desaturated, limited palette, speed lines, emphasis lines, motion blur, teal accent`
- p10 Bai Ning Bing inset: `score_9, score_8_up, score_7_up, very aesthetic, absurdres, solo, 1boy, male focus, mature male, black hair, long hair, flowing white robe, robe, chinese clothes, wide sleeves, expressionless, simple background, black background, floating, blue aura, glowing, blue theme, cowboy shot`

## Weights on disk (HF cache `~/.cache/huggingface/hub`)

The link measured about 0.1 to 0.5 MB/s, so downloads were queued by value and run detached (`scratchpad/art_v3/dl.py`, resumable; rerun the same snapshot_download calls to resume).

| Weights | Size | Licence | Status at write time |
|---|---|---|---|
| `Laxhar/noobai-XL-1.1` (NoobAI-XL 1.1, Illustrious-based) | already there | fair-ai-public-license-1.0-sd | on disk |
| `OnomaAIResearch/Illustrious-xl-early-release-v0` (Illustrious-XL v0.1, diffusers layout, UNet+TE+VAE only) | about 7 GB | fair-ai-public-license-1.0-sd (HF metadata: "other"; share-alike, non-commercial style terms, same as NoobAI) | downloading |
| `diffusers/controlnet-canny-sdxl-1.0-small` (fp16) | 0.32 GB | OpenRAIL++ | downloading |
| `diffusers/controlnet-depth-sdxl-1.0-small` (fp16) | 0.32 GB | OpenRAIL++ | queued |
| `xinsir/controlnet-union-sdxl-1.0` promax (openpose, lineart, depth, canny in one) | 2.5 GB | Apache-2.0 | queued last; does not fit 8 GB beside the UNet |
| `madebyollin/sdxl-vae-fp16-fix` (trainer VAE) | 0.33 GB | MIT | NOT queued; the trainer downloads it on first run |

Not downloaded on purpose: full-size SDXL ControlNets (canny and depth 2.5 GB each, openpose 5 GB). UNet 5.1 GB plus a 2.5 GB ControlNet does not fit 8 GB without CPU offload, which the owner forbids; the `-small` ones (0.32 GB) fit. Openpose therefore needs the union model (or a card above 8 GB) and `sdxl_control.validate` refuses it without `allow_big`; the union pipeline is not wired (`NotImplementedError` in the worker).

Illustrious-XL v0.1 is the only Illustrious base that is open without a login (v1.0 and v2.0 are gated or paid). A well-regarded manhwa-style fine-tune was not downloaded: at this link speed one more 7 GB checkpoint is hours, and NoobAI-XL is already the strongest Illustrious-family anime base on disk. Add a candidate by putting its diffusers folder in the HF cache and a key in `drama_tags.CHECKPOINTS` and `art_bakeoff_v3.CHECKPOINT`.

## Z-Image Turbo structural conditioning: yes

`alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1` (Apache-2.0): canny, depth, pose, HED, gray, inpaint and tile in one union ControlNet; files `...Union-2.1-8steps.safetensors` (6.71 GB) and `...-lite-2601-8steps.safetensors` (2.02 GB). diffusers 0.39 (installed) has `ZImageControlNetPipeline`, `ZImageControlNetModel`, `ZImageControlNetInpaintPipeline`, `ZImageImg2ImgPipeline`. Not downloaded, not wired (the lite file is the only one plausible on 8 GB next to the 6 GB Z-Image transformer; unmeasured). Z-Image has no IP-Adapter.

## Character LoRA

Trainer: diffusers `train_text_to_image_lora_sdxl.py` v0.35.0, pinned by sha256, fetched into `~/.cache/echotales/tools` on first use. Kohya sd-scripts was rejected because it pins its own torch/diffusers/transformers (second venv, GBs of wheels over this link). `datasets<5` was added to the shared venv (datasets 5 pulls huggingface-hub 2, which breaks transformers 5; this was hit and reverted to hub 1.27.0).

Settings for 8 GB: fp16, gradient checkpointing, bitsandbytes 8-bit Adam, batch 1 with 4 accumulation, rank 16 (4-64), VAE and text embeddings precomputed once and freed, 768 px. The script has no aspect bucketing, so `build_lora_set.py` letterboxes everything to one square. Expected VRAM, not measured: about 7-8 GB at 768 px (default), 9-11 GB at 1024 px (likely OOM on the 4060 Laptop). Output: `<out>/pytorch_lora_weights.safetensors`. The text encoders are not trained, so the worker attaches the LoRA per job.

### Identity images available (the blocker)

`build_lora_set.py --list` on 2026-11-28:

- **Fang Yuan (RI)**: 12 files in `data/novels/RI/references/turnarounds/reverend-insanity_self_476821534c/...body1/` (view_front, view_side, view_back, turnaround_sheet, expression_sheet, 7 expr_*). **0 usable**: they are stub renders from 2026-10-20 (6.5-12.5 KB, 1080x1920 or 1920x1080), and only 3 distinct files exist.
- **Klein (LotM)**: 12 files, **0 usable**, byte-identical to Fang Yuan's (same md5s).
- **Kim Dokja (ORV)**: no turnaround folder exists. 0 files.

A LoRA cannot be trained from these. The builder rejects any file under 30 KB or whose hash occurs more than once. To get a set: generate real identity sheets, approve them (Studio), or pass approved panel crops with `--extra` (real renders of Fang Yuan exist under `data/novels/RI/panels/ch1/v54_*`; they are NoobAI renders, so a LoRA trained on them would learn NoobAI's own Fang Yuan). Fewer than 8 images memorises poses; the trainer warns.

## ControlNet hook

`--control '{"kind":"canny","image":"layout.png","scale":0.6}'` on the driver adds control to every SDXL arm (never to B2). Kinds: `canny`, `lineart` (adaptive-threshold line map, canny weights), `depth` (Depth-Anything-V2-Small from `data/models/`), `openpose` (pre-drawn skeleton only, union model, refused on 8 GB). Combines with img2img (arm D) and with a LoRA.

## Commands for the GPU agent (one model per process, each under the lock)

```
cd /home/adhyan/Desktop/EchoTales/.claude/worktrees/art-v3
PY=/home/adhyan/Desktop/EchoTales/.venv/bin/python
# 0. check downloads finished: Illustrious folder has unet/ text_encoder/ text_encoder_2/ vae/
ls ~/.cache/huggingface/hub/models--OnomaAIResearch--Illustrious-xl-early-release-v0/snapshots/*/unet
# 1. prompts only (CPU)
$PY scripts/eval/art_bakeoff_v3.py --phase prompts
# 2. arms; the driver takes the lock itself, one subprocess per model
$PY scripts/eval/art_bakeoff_v3.py --phase run --arms B2,C2_noobai,C2_illustrious,D
$PY scripts/eval/art_bakeoff_v3.py --phase sheets
# 3. LoRA (only after a real set exists)
$PY scripts/art/build_lora_set.py --character fang_yuan --out data/scratch/lora_sets/fang_yuan --tags "<identity tags>"
$PY scripts/art/train_character_lora.py --data data/scratch/lora_sets/fang_yuan --out data/scratch/lora/fang_yuan --base noobai --dry-run
$PY scripts/art/train_character_lora.py --data data/scratch/lora_sets/fang_yuan --out data/scratch/lora/fang_yuan --base noobai
$PY scripts/eval/art_bakeoff_v3.py --phase all --arms C2_noobai,C2_illustrious,D --lora fang_yuan=data/scratch/lora/fang_yuan/pytorch_lora_weights.safetensors
```

Output: `data/scratch/art_v3/<arm>/<panel_id>.png`, `prompts.json`, `stats_<arm>.json`, `sheets/<panel_id>.png` (ref | arms) and `sheets/all_<n>.png` (four panel strips stacked). Same seeds as earlier rounds (4200 + panel index), 832x1216.

## Known limits

- No image has been generated by this code. C2 tag quality is a compile-time check against the 13 fixture panels, not a render.
- The `--phase prompts` output is the only thing runnable without weights; `--stub` runs the whole plumbing with solid-colour images.
- The C2 keyword tables (garments, hair styles, scene words, expressions) are generic vocabulary, not novel names, but they only cover what the 13 panels and a few common words need; an unmapped garment or hair phrase falls back to the raw phrase if it is four words or fewer.
