# data/

Everything the pipeline reads or writes. Only small, authored or measured files
are tracked (see `.gitignore`: data/ is ignored by default and tracked by
exception). Every default path in the code comes from
`packages/pipeline/src/echotales/pipeline/paths.py`.

| Folder | What it holds | Tracked |
|---|---|---|
| `sources.toml` | one block per novel: source file, adapter, chapter range | yes |
| `canonical_dbs.json` | databases `resolve` refuses to wipe (`Store.is_canonical`) | yes |
| `db/<novel-id>.db` | **the** database for each novel: the run of record | no |
| `novels/<CODE>/` | everything generated for one novel (below) | notes only |
| `gold/` | reference sets: offsets and short evidence snippets, never chapter text | partly |
| `eval/` | every measured result a doc or table cites | yes |
| `corrections/` | review-desk correction logs (JSONL, replayable) | yes |
| `lexicons/` | seed vocabulary (tracked) and induced lexicons / NER caches (regenerable) | seed only |
| `raw/` | source EPUBs. Copyrighted: never commit | no |
| `voice/` | TTS voice banks (VCTK, CREMA-D, EARS), ~38 GB | no |
| `external/` | downloaded benchmarks (LitBank) | no |
| `cache/` | regenerable caches (webview thumbnails) | no |
| `exports/` | generated static sites and review HTML (`echotales webview`, `review`, `graph`) | no |
| `scratch/` | disposable: rerun and test databases, debug output. Safe to delete | no |
| `archive/` | retired snapshots kept for provenance (older databases, cache backups) | no |

## `novels/<CODE>/`

`CODE` is the short code in `paths.NOVEL_CODES` (`RI`, `LOTM`, `ORV`), else the
novel id.

```
novels/RI/
  README.md                  what is here and which render is current
  panels/ch<N>/v<M>_<name>/  one render per version; VERSIONS.md logs each one
  video/ch<N>/v<M>/          the composited chapter video for that render
  motion/                    motion clips
  audio/                     the default voice run (manifest.jsonl, ch<N>/)
  audio-runs/<name>/         other voice runs kept for comparison (e.g. ears-native)
  references/                character reference sheets
  scene-references/          hand-picked composition / character images (input)
  canon/                     wiki-sourced appearance canon (tracked)
  experiments/               renders made for one measurement (observer-contrast/)
```

## Where things were before 2026-09-27

The layout was restructured on 2026-09-27 (`docs/EVOLUTION.md` 4.94). Result
files under `eval/` record the path that was true when they ran, so they still
name the old locations:

| Old | New |
|---|---|
| `data/reverend-insanity.db` | `data/db/reverend-insanity.db` |
| `data/webview-working/{lord-of-the-mysteries,omniscient-readers-viewpoint}.db` | `data/db/` |
| `data/webview-working/reverend-insanity.db` | `data/archive/db/reverend-insanity-webview-working.db` |
| `data/echotales.db`, `echotales2.db`, `lotm-vol1.db` | `data/archive/db/` |
| `data/{det,llm}*.db`, `lotm-ch1-test.db`, `scratch_qa.db` | `data/scratch/db/` |
| `data/reruns/` | `data/scratch/reruns/` |
| `data/RI/` | `data/novels/RI/` |
| `data/lord-of-the-mysteries/`, `data/audio/lord-of-the-mysteries/` | `data/novels/LOTM/` |
| `data/audio-ears*/` | `data/novels/RI/audio-runs/ears*/` |
| `data/RI/panels-obs-{reader,nonwitness}/` | `data/novels/RI/experiments/observer-contrast/` |
| `data/scene-references/` | `data/novels/RI/scene-references/` |
| `data/webview/`, `data/review/` | `data/exports/` |
| `data/diag/`, `data/debug-test-novel/`, `data/RI/scratch/` | `data/scratch/` |
