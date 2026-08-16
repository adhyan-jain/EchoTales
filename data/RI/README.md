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
