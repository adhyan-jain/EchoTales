# Prompt-image alignment (CLIPScore)

**Measured 2026-09-27.** `scripts/eval/clip_score.py`, CLIP ViT-L/14
(`openai/clip-vit-large-patch14`, local cache, no download), seed 20260927.
Result file: `data/eval/clipscore.json`.

**What it measures.** CLIPScore (Hessel et al., 2021) between each rendered
panel and the prompt that produced it, truncated to CLIP's 77 tokens exactly as
the image engine sees it. Panels in one render share style tags, so the mean
alone says little. Each image is therefore also scored against the prompt of a
*different* panel of the same render. "Beats control" counts how often the
image matches its own prompt better than another panel's, which is the
evidence that the image follows the prompt's *content*.

**What it does not measure.** Image quality, character identity consistency
across panels, or whether the prompt itself was a good reading of the text.
It measures alignment between a panel and its prompt, nothing else. No human
rating exists.

| Render | Engine era | Panels | CLIPScore (mean ± sd) | Shuffled-prompt control | Beats control |
|---|---|---:|---:|---:|---:|
| RI ch1 `v54_crowd-solo-scenestate-fix` (current) | NoobAI XL, director prompts | 87 | 66.7 ± 7.6 | 54.3 | **77/87 (89%)** |
| RI ch1 `v9_short-clause-scene-restored` | GuoFeng3 (SD1.5), 2026-08-17 | 21 | 64.9 ± 4.2 | 62.9 | 7/21 (33%) |
| RI ch169 observer contrast, reader view | NoobAI XL | 10 | 69.4 ± 6.0 | 64.4 | 6/10 |
| RI ch169 observer contrast, non-witness view | NoobAI XL | 10 | 71.7 ± 3.0 | 69.8 | 6/10 |
| LOTM ch1 | NoobAI XL | 73 | 54.0 ± 6.6 | 48.4 | 62/73 (85%) |

**Reading it.**
- The current RI pipeline's panels follow their own prompts: 89% score higher
  against their own prompt than against another panel's. The August render
  was near chance (33%), so the director and prompt-budget work between v9 and
  v54 is measurably visible in the images, not only by eye.
- LOTM's absolute scores are lower. Its prompts carry more proper nouns and
  Western period detail that CLIP embeds weakly, but the matched-vs-shuffled
  gap is similar (85%).
- The observer-contrast renders (n = 10 each) are too small to separate the two
  views. Their panels differ in what is drawn, not in how well each follows its
  prompt, so this metric is not the right test for the observer claim.

**Stub renders are excluded.** RI ch169 `v1` in the main panel folder is stub
output (8 KB placeholders). Scoring it would measure nothing.
