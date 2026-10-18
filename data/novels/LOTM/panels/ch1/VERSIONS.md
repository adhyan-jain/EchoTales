# LotM ch1 panel version index

Render-output tracking only (see data/novels/RI/panels/ch1/VERSIONS.md for the format). Output is gitignored.

## v1
The first real LotM render: 40 panels, drawn in the xianxia style (long hair, hanfu, East Asian screens) because every
style lookup fell back to Reverend Insanity's. Its original manifest was overwritten by a Studio test render on
2026-10-18 and rebuilt from prompt_cache_v1.json as v1/manifest.reconstructed.jsonl (negative prompts not recoverable).
Verdict: wrong genre for this book.

## v2_genre-victorian-10panel-noobai
2026-10-18. First render under the genre profiles (persona/genre.py, Victorian gothic): `--max-panels 10` (10 scenes) made
33 images in 22 minutes on an RTX 4060 Laptop, gemma2:9b director at num_ctx 4096 then NoobAI XL, on a scratch copy of
the database. Verdict from a viewer's point of view: the style is right (tailored coats, cravats, gloves and a revolver,
arched windows, a brown-haired grey-eyed protagonist) and consistent across the panels looked at; not reviewed panel by
panel; one panel carries a stray signature-like artefact.

## v3, v4, v5: abandoned (1 to 2 images each)
2026-10-18. Test slices stopped on purpose, each built on a prompt or locale bug found by the one before: v3 rendered blocks
8 to 40 only (lost who was in the scene: silhouettes) and still carried "a moonlit moor" from "wood" in "wooden"; v4 and v5
put a panelled study on every panel because a scene's only place hit was "temples" (a body part). Kept only as a record.

## v6_bedroom-slice-final2
2026-10-18. Blocks 0 to 40, 2 scenes, after the setting fixes (render review of v2, commits b22fc1a to 97ab2a5): the
setting and key objects rank above mood, no duplicate quality tags, the director no longer copies "day, bright_sunlight",
it is shown the whole scene's place and hour, and a scene with no place cue inherits the chapter's. Verdict from a
viewer's point of view: one consistent wood-panelled bedroom with lamps, a bed, a desk, a notebook and a revolver on the
desk across the panels; the same black coat and ruffled jabot. NOT fixed: hair shade and face shape still vary from panel
to panel (every panel is prompt-only, no reference conditioning), and there is no blood or head wound (that text is
after block 40). Not a full chapter.

## Loose files in ch1/
The p0*.png files, manifest.jsonl and cache_index.json directly under ch1/ are from a Studio stub render on 2026-10-18,
before Studio renders got their own version directory. They are placeholders, not a render.
