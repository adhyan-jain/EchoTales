# Reverend Insanity — pipeline output

**Asset type, then chapter, then version.** One chapter made the old
chapter-first layout look fine; two hundred would not. Every render lands in a
new `vN_` directory instead of overwriting the last, so any two runs can be
watched back to back — the rule adopted after a render silently destroyed the
reference video an earlier review had been written against.

    panels/ch1/vN_<date>_<what-changed>/    one render's panel PNGs + manifest
    video/ch1/                              finished mp4s and segment sets
    audio/ch1/vN_<engine>/                  synthesis output + casting manifest
    motion/ch1/                             SVD motion clips
    references/sheets-v2/                   current IP-Adapter character sheets
    references/sheets-v1/                   superseded
    scratch/ch1/                            one-off prompt/composite experiments

Paths come from `pipeline/paths.py` (`novel_root`, `asset_dir`,
`next_version`); the directory *is* the novel, so nothing below it repeats the
novel id.

## Version history — ch1 panels

| version | what changed |
|---|---|
| v0a/v0b | earliest panel experiments (`panels_v2` / `panels_v3`) |
| v1  | per-paragraph generation — 89 near-duplicate panels |
| v2  | drama-weighted selection, 14 panels |
| v3  | 70-panel budget, mechanical prompts (`--no-director`) |
| v4  | scene-grouped generation, no reference conditioning |
| v5  | before the mob-detection / locale-cue fixes |
| v6  | before the `solo` prompt-tag fix |
| v7  | before the appearance / age / gender fixes |
| v8  | long character clause — scene starved by CLIP's 77-token cap |
| v9  | short clause (`detailed=False`) — environment renders again |

## Not stored here, deliberately

`data/gold`, `data/lexicons`, `data/corrections`, `data/raw`, `data/reruns`
and `data/webview-working` hold one file *per novel*, keyed by novel id
(`config.py`'s `gold_path` / `lexicon_path`). Moving RI's entries out of them
breaks that lookup. `data/scene-references` is genre-wide composition
reference, not RI's. `data/voice` is the shared VCTK corpus (~23 GB).

## Crowd rendering — a measured dead end on this checkpoint

Four rounds of prompt work (v10–v13) failed to put a crowd in frame next to a
named character. Every lever was tried and verified in real generation:

| lever | result |
|---|---|
| removed the `solo` tag | no crowd |
| removed the `1boy` count tag | no crowd |
| crowd stated in the director's setting prose | no crowd |
| IP-Adapter dropped entirely on wide shots | no crowd (but much better depth) |
| leading Danbooru count tags (`crowd, 6+boys`) | no crowd |

The same checkpoint *does* render a dense crowd when the prompt contains **no
named foreground character** (verified standalone: "a large angry crowd of
cultivators on a mountain path" produced a full battlefield). So GuoFeng3
(SD1.5) can draw a hero, and can draw a crowd, but not both in one image at
1024px. That is a model-capacity limit, not a prompt-engineering one, and no
further prompt work will move it.

Two ways forward, neither of them prompt tweaks:

1. **A stronger checkpoint** — Illustrious XL or Pony Diffusion V6 XL (SDXL
   anime finetunes, ~7–8 GB at FP16, fits this card with the cpu-offload
   already wired in `SDXLEngine`). Multi-subject composition is the specific
   thing SDXL improves on SD1.5, and SDXL IP-Adapter exists so character
   consistency survives the switch.
2. **Cut, don't compose** — a hero panel and a crowd-reaction panel as two
   consecutive cuts. This is what manhwa actually does with this beat, it
   needs no new model, and the panel-per-beat machinery already supports it.
   Compositing the two into one frame was tried and looked pasted.

## Panel versions, 2026-08-18

| version | engine | what changed |
|---|---|---|
| v22 | illustrious | crowd composes, render flat, generic anime faces |
| v24 | animagine | checkpoint swap only; richer shading, still Japanese drift |
| v25 | refined | Animagine composes, GuoFeng3 repaints @ 0.35 — Chinese roof lines, guanmao caps |
| v26 | animagine + IP-Adapter | first panels shaped by `data/scene-references/` |
| v28–v31 | refined | pre-chunking: **22 panels for 92 blocks**, single panels held 12–16 blocks |
| v32+ | refined | 4 blocks per panel (48 panels for ch1), scene-local crowds |

`*.base.png` next to a panel is the pre-repaint SDXL frame — keep it to tell
"the base composed badly" apart from "the refiner destroyed a good frame".

## Canon inputs (not generated, not versioned per run)

- `canon/wiki-appearance.json` — imported by `echotales persona wiki-canon`.
  Precedence is hand-authored `persona/canon.py` > this file > extraction.
- `../scene-references/` — hand-collected composition and character images,
  consumed by `render/scene_refs.py`.

## Videos

`video/ch<N>/v<K>_<date>_<label>/` — same scheme as `panels/`, one directory
per finished render, each holding `ch<N>.mp4` plus its `segments/` and any
`.ass` subtitle file. New runs are versioned automatically by
`pipeline/paths.py::next_version`; the directories below were the earlier
loose files, sorted into the scheme by hand.

| version | what it was |
|---|---|
| v1 2026-08-13 | first end-to-end cut |
| v2 2026-08-13 | manga engine (GuoFeng3) |
| v3 2026-08-13 | scene-grouped panels replacing per-block |
| v4 2026-08-14 | SVD motion clips added |
| v5 2026-08-15 | the cut that was watched end to end; six findings came out of it |

`compare/` holds before/after excerpts cut for review, not full chapters.

**No video has been produced since 2026-08-18's panel work** (chunked beats,
scene-local crowds, beat-first prompts, sequential panel numbering) — the
newest here predates all of it.
