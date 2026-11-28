# Art drama bake-off (2026-11-28)

Goal: Z-Image's relevance with NoobAI's drama. Branch `claude/art-drama`. This write-up states what was built and measured; it does **not** judge which arm is best (Opus judges from the sheets).

## Arms

| Arm | What it is |
|---|---|
| A | Z-Image Turbo, production compiler (`_compile_composed`), neutral one-line framing per shot |
| B | Z-Image Turbo, drama compiler `render/drama.py::compile_drama`: a table from schema enums (`Purpose`, `Shot`, `Shape`, `Layer`) to a framing sentence, a light sentence (peaks only) and a `drama` block (ink texture, wind when the panel text has motion, foreground framing, composition by shape, dark desaturated palette with one accent colour per layer). `STYLE_ANCHOR` (genre style lead) stays section 0; framing, grade and drama sit before the identity sentences. Calm beats keep their graded light and get no chiaroscuro or dutch angle |
| C | NoobAI XL 1.1 txt2img, tag prompt `compile_noobai_tags` from the same `Panel` (score tags, count, identity, shot, scene, drama tags). Comparison only, never the default (D58) |
| D35 / D45 / D55 | Arm B's picture as the init of a NoobAI img2img pass (strength 0.35 / 0.45 / 0.55, 28-step schedule so 9 / 12 / 15 denoise steps) with arm C's tags. Own subprocess (`render/_noobai_i2i_worker.py`), so Z-Image and NoobAI are never resident together |
| `*_fx` | Same picture with the FX layer `pages/drama_fx.py` on: focus or speed lines at peaks, per-layer contrast and vignette, screentone on memory and lore, and (in `render_storyboard_strip(..., drama_fx=True)`, default off) a burst plus brush-style SFX behind each SFX letter. The sheets show `A_fx`-style picture-level FX only (`B_fx`, `D45_fx`; `A_fx` and `C_fx` are in the folders); the burst and brush SFX only appear in a strip render, covered by a unit test, not by the sheets |

Same seed per panel across arms (4200 + panel index), 832x1216 for every image. 13 panels (the brief said 12 but listed 13): fixture `packages/pipeline/tests/_art_bakeoff_panels.py`. The Bai Ning Bing look is an invented, flagged look (no dossier look exists in this checkout): white gown, cold glow. The cliff hair (long black) and the accuser's face are invented texture, not plot facts.

## Runtime and VRAM (RTX 4060 Laptop 8 GB, nothing offloaded, all under `flock /tmp/echotales-gpu.lock`)

| Arm | Seconds per image (mean) | Peak VRAM | Notes |
|---|---|---|---|
| A | 32.3 | 5.78 GiB denoise, 2.63 encode | 13 images, wall 528 s incl. about 44 s model load |
| B | 33.1 | 5.78 GiB denoise, 2.66 encode | wall 508 s |
| C | 21.3 | 5.41 GiB denoise, 1.57 encode | 13 images, wall 302 s |
| D35 / D45 / D55 | 9.6 / 11.6 / 13.7 | 5.43 GiB | one subprocess, 40.8 s load once, 1.60 GiB encode; wall 505 s for 39 images incl. load |

Token budget: nothing fell off. Z-Image (Qwen3 encoder, no 77-token limit): arm A prompts 217-221 tokens, arm B up to 302. NoobAI tag prompts are 57-130 tokens; the worker's compel chunking encodes all of them (1-2 chunks of 75), nothing cut.

## Compiled prompts, 3 panels (style lead omitted from the list; it is section 0, verbatim the genre lead)

### p01 hero (peak)

**Arm A**

- `framing`: A shot from a low angle.
- `grade`: Golden-hour light: a low sun, long soft shadows, warm rim light on the subject and cooler shadows, a muted cold blue-grey grade.
- `character:Fang Yuan`: Fang Yuan is a man with long black hair, an adult face with a defined jaw and mature proportions, wearing a torn deep-green robe soaked with blood.
- `staging`: Light: a blood-red dusk sky behind the cliff
- `composition`: Fang Yuan stands alone at the edge of a bare cliff, his torn deep-green robe soaked in blood, a wide pool of blood spreading beneath his feet, wind tearing at his hair and robe, far below him rows of fighters in pale robes.
- `setting`: Setting: a cliff edge at dusk.

**Arm B**

- `framing`: An extreme low-angle full-body shot from the ground looking up, the figure monumental against the sky.
- `grade`: Hard chiaroscuro: a single strong rim light, hard-edged black shadows across half the face and body, deep inky blacks and high contrast.
- `drama`: Ink-wash brush texture at the edges and fine blood-like ink splatter. Wind whips the hair and the cloth sideways in long streaming lines. Dark out-of-focus silhouettes in the foreground frame the view. Tall vertical composition, the subject filling the frame from head to feet. A dark desaturated palette with a single blood-red accent.
- `character:Fang Yuan`: Fang Yuan is a man with long black hair, an adult face with a defined jaw and mature proportions, wearing a torn deep-green robe soaked with blood.
- `staging`: Light: a blood-red dusk sky behind the cliff
- `composition`: Fang Yuan stands alone at the edge of a bare cliff, his torn deep-green robe soaked in blood, a wide pool of blood spreading beneath his feet, wind tearing at his hair and robe, far below him rows of fighters in pale robes.
- `setting`: Setting: a cliff edge at dusk.

**Arm C** (positive)

`score_9, score_8_up, score_7_up, very aesthetic, absurdres, solo, fang yuan, 1boy, long black hair, torn green robe, chinese clothes, blood on clothes, blood on face, blood pool, from below, full body, looking up, cliff, mountain, sunset, red sky, wind, dutch angle, dramatic lighting, chiaroscuro, hard shadows, rim light, high contrast, ink wash, sumi-e, ink splatter, dark, desaturated, limited palette, red accent, blood, wind, windswept hair, flowing clothes, motion lines, dynamic pose`

### p07 clan head praying (calm)

**Arm A**

- `framing`: A medium shot.
- `grade`: Low-key lighting: deep shadows swallow most of the frame, the subject lit only by the stated light source with a soft rim light, a dark moody cinematic grade, dim and never bright or evenly lit.
- `character:The clan head`: The clan head is a middle-aged man with black topknotted hair, an adult face with a defined jaw and mature proportions, wearing a white ceremonial robe.
- `staging`: Light: candlelight in a dark temple at night
- `composition`: A middle-aged man in a white ceremonial robe kneels with his palms pressed together in prayer before rows of wooden ancestral tablets on an altar, candles burning in front of them.
- `setting`: Setting: an ancestral temple at night.

**Arm B**

- `framing`: A medium shot.
- `grade`: Low-key lighting: deep shadows swallow most of the frame, the subject lit only by the stated light source with a soft rim light, a dark moody cinematic grade, dim and never bright or evenly lit.
- `drama`: A muted colour palette and a calm, composed frame.
- `character:The clan head`: The clan head is a middle-aged man with black topknotted hair, an adult face with a defined jaw and mature proportions, wearing a white ceremonial robe.
- `staging`: Light: candlelight in a dark temple at night
- `composition`: A middle-aged man in a white ceremonial robe kneels with his palms pressed together in prayer before rows of wooden ancestral tablets on an altar, candles burning in front of them.
- `setting`: Setting: an ancestral temple at night.

**Arm C** (positive)

`score_9, score_8_up, score_7_up, very aesthetic, absurdres, solo, 1boy, middle-aged, white robe, chinese clothes, kneeling, praying, topknot, beard, cowboy shot, temple, altar, candles, tablets, night, indoors, teal accent`

### p12 eyes only (peak, no identity)

**Arm A**

- `framing`: A close-up portrait.
- `grade`: Low-key lighting: deep shadows swallow most of the frame, the subject lit only by the stated light source with a soft rim light, a dark moody cinematic grade, dim and never bright or evenly lit.
- `composition`: An extreme close-up of a pair of clear, bright young eyes only, reflecting the glimmer of lantern light, nothing else of the face in frame.
- `staging`: Light: night, glimmering lantern light reflected in the eyes

**Arm B**

- `framing`: An extreme close-up cropped tight on the eyes and brow, filling the whole frame.
- `grade`: Hard chiaroscuro: a single strong rim light, hard-edged black shadows across half the face and body, deep inky blacks and high contrast.
- `drama`: Rough ink-brush texture at the edges of the frame. A dark desaturated palette with a single cold teal-green accent.
- `composition`: An extreme close-up of a pair of clear, bright young eyes only, reflecting the glimmer of lantern light, nothing else of the face in frame.
- `staging`: Light: night, glimmering lantern light reflected in the eyes

**Arm C** (positive)

`score_9, score_8_up, score_7_up, very aesthetic, absurdres, solo, extreme close-up, eye focus, portrait, extreme close-up, eyes, eye focus, reflection, night, dutch angle, dramatic lighting, chiaroscuro, hard shadows, rim light, high contrast, ink wash, sumi-e, ink splatter, dark, desaturated, limited palette, teal accent`

## Sheets (local only; the reference slices are copyrighted and nothing under `data/scratch` is committed)

`/home/adhyan/Desktop/EchoTales/.claude/worktrees/art-drama/data/scratch/art_drama/sheets/<panel_id>.png`, columns: ref | A | B | B_fx | C | D35 | D45 | D55 | D45_fx. Images per arm in `.../art_drama/<arm>/<panel_id>.png`, prompts in `prompts.json`, stats in `stats_*.json`. Reference slices (hand-picked from `data/scratch/reference/ri_manhua/ch01/`) are listed in `scripts/eval/art_drama_bakeoff.py::REFERENCE`.

Reproduce: `flock /tmp/echotales-gpu.lock python scripts/eval/art_drama_bakeoff.py --phase all` (phases: prompts, zimage, noobai, i2i, fx, sheets).

## Known limits

- The sheets' FX columns are picture-level only; lettering FX (burst, brush SFX) are not on the sheets.
- Reference slices are webtoon strips, so the reference column has a different aspect ratio.
- Defaults unchanged: Z-Image via the production compiler stays default; the drama compiler, FX layer (`drama_fx=False`) and NoobAI arms are opt-in.
- Tests: `packages/pipeline/tests/test_art_drama.py` (10); full core+pipeline suite 3278 passed, 29 skipped.
