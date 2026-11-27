# Webtoon grammar renderer (2026-11-27)

`pages/storyboard_render.py` draws a `Storyboard` (`storyboard/schema.py`) as a vertical-scroll chapter using the
grammar in `MANHWA_DIRECTING_PATTERNS.md` section 3. It is CPU-only, needs no model, and sits beside the existing
`pages` path (that path and its default are unchanged).

```
render_storyboard_webtoon(storyboard, images: dict[panel_id, Path], out_dir, style: StyleTable | None = None,
                          *, faces: dict[panel_id, dict[speaker_id, (x0,y0,x1,y1) normalised]] | None = None) -> list[Path]
```

Writes `slice_001.png ...` (1600 px wide, 1000-1700 px tall), `contact.png` and `layout.json` (cuts, every placed
letter, every overflow). `render_storyboard_strip` returns the whole strip plus placement records (used by tests).
`export_storyboard_webtoon` sends the slices to the existing PNG/PDF/CBZ exporter. CLI:
`echotales pages --novel RI --storyboard sb.json --images <dir of panel_id.png> [--style table.json] --export cbz`.

## What is supported

- **Shapes** (`Shape`): standard, wide, tall, diagonal (slanted top edge, gutter wedge shows), inset (overlaps the
  previous panel's corner, framed, alternates side; imagined layer gets a cool glow), bleed (borderless, fades into
  the gutter), text_only (letters on gutter colour). Pictures are cover-fitted with the crop centred on a face box
  when `faces` is given, else on the salience/skin centroid (`placement.estimate_subject`).
- **Gutters**: a per-layer colour pair (`LayerStyle.gutter_start/end`); a gap fades prev layer end to next layer
  start, so a layer change is a gradient. Length by transition: tight (inserts, reactions, close-ups), beat, scene
  cut, plus extra on a layer change. All of it lives in `StyleTable` (`pages/storyboard_style.py`, JSON
  round-trippable); nothing names a novel.
- **Lettering** for all 11 `LetterKind`s: speech (pill), shout (spiky), whisper (dashed), dread (black fuzzy
  halo), thought (cloud with bubble tail), memory (gold glow ring), narration (box; parchment per layer), time_place
  (card, colour flips on dark or light gutter), name_card (dark label with gold bar and optional subtitle: write
  `"Name | subtitle"`), poem (soft pill on a pale wash), SFX (Lato Black per-glyph wobble, keyline, shadow, shear and tilt,
  colour per layer, size from panel and purpose; cold-open and bleed get big SFX). Antialiased by 3x supersampling.
- **Placement**: grid search over a cost map (salient and skin cells, padded face boxes, other balloons forbidden),
  reading order top-down, narration/poem/time cards centred, name cards left. Tails point at the speaker's face box;
  with one face it is the speaker; with none but a named speaker the tail goes to the panel's skin/salience centroid;
  narration never gets a tail. A panel grows (up to 1.9x) before text is squeezed; font shrinks to a floor; truncation
  and unplaced letters are listed in `overflow`.
- **Layer grades** (a grade, not a repaint): memory (desaturate, gold tint, bloom, vignette), past (slight
  desaturate and warm), imagined (cool tint, glow), lore (ink-wash grey on parchment), dream (lavender bloom).
- **Slicing**: cuts avoid every letter extent plus a margin, prefer gutters, aim at 1350 px.
- Fonts are bundled under `pages/fonts` (Comic Neue and Lato Black, both OFL, copied from the local TeX tree; no
  download). Missing pictures get a placeholder with a head so layout can be tested before any render.

## What is not supported

- No face detector: tails and avoidance use face boxes only if the caller supplies them; otherwise salience. On the
  stand-in art that means an SFX can land on a face (RUMBLE does in the fixture) and a tail aims at the visual centroid.
- No hand-drawn brush SFX, speed lines, screentone or zoom lines (RI's cold-open spread relies on them).
- Diagonal cuts are only on the top edge; no multi-panel diagonal compositions, no side-by-side panels in a row.
- Letter text in an inset is measured against 0.62 of the strip width so it stays legible; a long inset line can
  therefore spill past a narrow inset (it is placed inside the panel rect or reported unplaced).
- Slices may exceed 1700 px when a tall unbroken balloon run leaves no legal cut.
- No right-to-left lettering; Latin script only.
- Speaker positions come only from supplied face boxes; `Panel.cast` order is not used as left/right.

## Evidence

- Fixture: `packages/pipeline/tests/_ri_ch1_storyboard.py`, 26 panels in the RI ch1 structure (cold open, accusers,
  hero with name card, time card, poem, memory montage, defiance, transition, ritual with an imagined inset, reveal).
  Stand-in pictures: RI ch1 v57 panels, local only.
- Output and comparison (local, not committed): `data/scratch/pages_grammar/ri_ch1/` (24 slices, `contact.png`) and
  `data/scratch/pages_grammar/compare_ri_ch1.png` (reference slices 2, 9, 10, 42, 95, 97, 104, 160 above, ours below).
- Tests: `packages/pipeline/tests/test_pages_storyboard_render.py` (no balloon crosses a cut, every letter placed or
  reported, shapes' geometry, gutter pacing and colours, style JSON round trip, exports). 10 pass.

## Honest visual verdict

Structure reads like a webtoon: black battle gutters tightening for close-ups, a long scene gap, a gold-to-white
memory run with glowing-ring captions, white ritual gutters, an imagined inset with a cool glow, a name card, a
"6 HOURS PASS" card and tilted keyline SFX. Balloons are legible (about 46 px at 1600 wide), mostly clear of faces,
and tails land near heads. Against the reference it is clearly behind on three things: (1) the art is the old v57
stand-in, so mood and drama differ from the manhua's painted red/teal spreads; (2) SFX are font-based rather than
brush lettering and are not integrated into the art (no speed lines, no ink bursts); (3) without a face detector
placement is salience-driven, so an occasional balloon or SFX still sits on a face. Ours is a competent layout
engine, not yet the polish of the reference. Closest rows: memory captions, time card, inset, shout balloons.
Furthest: cold-open SFX spread, battle atmosphere.

Run time: about 25-45 s for the 26-panel fixture (grid search and 3x supersampled balloons are not optimised).
