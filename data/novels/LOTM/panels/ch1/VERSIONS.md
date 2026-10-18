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

## Loose files in ch1/
The p0*.png files, manifest.jsonl and cache_index.json directly under ch1/ are from a Studio stub render on 2026-10-18,
before Studio renders got their own version directory. They are placeholders, not a render.
