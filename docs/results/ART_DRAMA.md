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

## Round 2 (2026-11-28): drama compiler v2, branch `claude/art-drama-v2`

### Opus verdict on the 13-panel round 1

- **B (drama compiler on Z-Image) wins**: it beats A on drama (red sky, wind, dark grade, blood, hard shadows) and keeps relevance. B becomes the storyboard path's compiler.
- **D (NoobAI img2img at 0.35-0.55) is dropped**: nearly identical to B at extra cost.
- **C (NoobAI tags) stays comparison-only**: off-text on most panels, striking abstract peaks. Defaults are not changed to NoobAI.

### B's failures and what B2 does about each (all driven by schema enums and cast facts, no novel names)

1. **Age not drawn** (clan head about 30, 15-year-old Fang Yuan an adult): `drama_identity_sentence` writes visible markers from `age_band` right after the head of the character clause, before hair and clothes (middle-aged: greying temples, lined face, mature heavy build; teen: youthful soft round face, slight narrow frame, smaller stature; elder: lined weathered face, frail build, white hair only when the cast gives no hair, a beard only when the cast's facts give one). The compiler's `_ADULT_FACE` clause is removed for those bands because it said "adult face with a defined jaw". Unit tests check the markers survive in the compiled prompt and precede the scene paragraph.
2. **Gender wrong on the referenced inset**: the fixture's Bai Ning Bing is now male (the v1 fixture said female, so the sheet drew a woman). His look is still invented and flagged (`invented_look=True`). Every character clause carries a gender noun (man, woman, boy, girl); a test checks it for all 13 panels.
3. **IMAGINED / REFERENCED_INSET sat in the room**: `_isolated_brief` drops place, setting, crowd and staging except the Light line, and replaces the paragraph with an isolated figure floating in an abstract void in the layer's palette (`_VOID`), plus the layer's glow light.
4. **People added to no-identity panels** (a man in black in the detonation, two figures above the eyes): `is_people_free` (empty cast, no crowd) removes every people-bearing sentence ("across half the face and body", foreground silhouettes, wind in the hair and cloth, the people shot sentences, shape sentences naming a subject) and adds an explicit "no people, no bodies, no faces and no silhouettes" line. An eyes-only panel gets "one single pair of eyes filling the frame edge to edge, irises with reflected lights and rain, no forehead, nose, mouth, second person or figures" instead of "eyes and brow". The fixture's detonation paragraph lost its "tiny dark figures". The first B2 render still drew a man in black in the detonation and small figures behind the eyes, because the genre lead (section 0) says "mature faces ... hanfu robes": people-free panels now get the lead without that people clause (`style_lead(people=False)`), and p05, p06 and p12 were re-rendered (the other 10 B2 images are from the first pass). After that the sheets show no extra people on p05 and p12.
5. **Composition tamer than the reference**: peaks with people get "extreme perspective, strong foreshortening, a diagonal composition and a dynamic pose"; the layer accent is now "one intensely saturated X accent light raking across the scene" (a light, not a tint).
6. **FX barely visible**: peak speed and focus lines are 2.6x wider, denser (240 and 160 lines, was 150 and 90) and 1.6x more opaque; the peak vignette is +0.40 (was +0.22). The `drama_fx` switch stays.

Not changed: arm C tags and the NoobAI workers are untouched; arms C and D were not rerun.

### B2 compiled prompts (style lead omitted; it is section 0, verbatim the genre lead)

#### p07_clanhead

- `framing`: A medium shot.
- `grade`: Low-key lighting: deep shadows swallow most of the frame, the subject lit only by the stated light source with a soft rim light, a dark moody cinematic grade, dim and never bright or evenly lit.
- `drama`: A muted colour palette and a calm, composed frame.
- `character:The clan head`: The clan head is a middle-aged man with greying temples, a lined face with creases at the eyes and mouth, and a mature heavy build, black topknotted hair, wearing a white ceremonial robe.
- `staging`: Light: candlelight in a dark temple at night
- `composition`: A middle-aged man in a white ceremonial robe kneels with his palms pressed together in prayer before rows of wooden ancestral tablets on an altar, candles burning in front of them.
- `setting`: Setting: an ancestral temple at night.

#### p10_bainingbing

- `framing`: A medium shot.
- `grade`: A cold glow around the figure against deep darkness, hard rim light, high contrast.
- `drama`: A dark palette with one intensely saturated cold pale-blue glow around the subject.
- `character:Bai Ning Bing`: Bai Ning Bing is a young man with long straight black hair, an adult face with a defined jaw and mature proportions, wearing a flowing white robe with pale sleeves.
- `staging`: Light: a cold pale glow in darkness
- `composition`: Bai Ning Bing, cold and composed, stands alone as an isolated figure floating in an abstract void filled with a soft cold pale-blue glow, pictured as a vision. No room, no walls, no furniture, no ground and no other people anywhere in the frame.

#### p12_eyes

- `framing`: An extreme macro close-up of one single pair of eyes, filling the whole frame edge to edge.
- `grade`: Hard chiaroscuro: one strong light source, hard-edged black shadows, deep inky blacks and high contrast.
- `drama`: The irises hold small reflected lights and streaks of rain, and nothing else is in the frame: no forehead, no nose, no mouth, no second person, no figures. Rough ink-brush texture at the edges of the frame. Extreme perspective, the force of it radiating diagonally toward the viewer. A dark desaturated palette with one intensely saturated cold teal-green accent light raking across the scene.
- `composition`: An extreme close-up of a pair of clear, bright young eyes only, reflecting the glimmer of lantern light, nothing else of the face in frame.
- `staging`: Light: night, glimmering lantern light reflected in the eyes

#### p13_young

- `framing`: A tilted dutch-angle medium shot, the horizon slanting.
- `grade`: Hard chiaroscuro: a single strong rim light, hard-edged black shadows across half the face and body, deep inky blacks and high contrast.
- `drama`: Rough ink-brush texture at the edges of the frame. Wind whips the hair and the cloth sideways in long streaming lines. Extreme perspective, strong foreshortening, a diagonal composition and a dynamic pose. Tall vertical composition, the subject filling the frame from head to feet. A dark desaturated palette with one intensely saturated cold teal-green accent light raking across the scene.
- `character:Fang Yuan`: Fang Yuan is a 15-year-old boy with a youthful soft round face with no lines or stubble, a slight narrow frame and a noticeably smaller stature, black hair, a smooth youthful face and a slim boyish build, wearing a plain dark blue robe.
- `staging`: Light: night, rain at the window, dim lamplight
- `composition`: A fifteen-year-old boy stands at a window in the night rain, looking at his own soft, pale palms, rain blowing in over the sill.
- `setting`: Setting: a small room at night in the rain.
### Run and sheets

Arms A, B2 and B2_fx (picture-level FX) on the same 13 panels and seeds (4200 + panel index), 832x1216, Z-Image Turbo only, one subprocess, under `flock /tmp/echotales-gpu.lock`, nothing offloaded. Wall: A 521 s, B2 479 s for 13 images each (plus a 3-image B2 re-render of p05, p06, p12). `ART_ONLY=p05_detonation,... --phase zimage` re-renders chosen panels for B2.

Sheets (local only; reference slices are copyrighted, nothing under `data/scratch` is committed): `data/scratch/art_drama_v2/sheets/<panel_id>.png` in the v2 worktree `/home/adhyan/Desktop/EchoTales/.claude/worktrees/art-drama-v2/`, columns ref | A | B_v1 (round 1, read from `.claude/worktrees/art-drama/data/scratch/art_drama/B/`) | B2 | B2_fx. Images in `.../art_drama_v2/{A,B2,B2_fx}/`, prompts in `prompts.json`, stats in `stats_zimage_full.json`.

Reproduce: `flock /tmp/echotales-gpu.lock python scripts/eval/art_drama_bakeoff.py --phase all` (v2 runs prompts, zimage, fx, sheets).

### Hand-off notes

- Tests: `packages/pipeline/tests/test_art_drama.py` (18, one per fix); full core+pipeline suite 3285 passed, 29 skipped.
- The Bai Ning Bing look stays invented (white robe, cold glow); only his gender is now set from the story time.
- Z-Image has no CFG, so "no X" sentences are weak: the people-free result came from removing people-bearing wording and the people clause of the style lead, not from the prohibition alone.
- Open: peak perspective sentence is also written for the eyes-only panel (harmless but odd); B2 is not yet wired into the storyboard render path as its compiler.
