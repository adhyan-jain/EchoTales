# Contributing

## Setup

```bash
scripts/setup.sh --dry-run   # shows your hardware preset and the models it would fetch
scripts/setup.sh             # workspace, web app, .env
```

Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+, ffmpeg.

## Tests

Everything is stub-first: no GPU, no network, no models.

```bash
ECHOTALES_LLM_MODE=stub uv run python -m pytest packages/core/tests packages/pipeline/tests -o addopts="" -q
cd webview && CI=true npm test -- --watchAll=false
```

`make test` runs both. Tests that need gitignored data skip themselves when it is absent.

## Conventions

- **Comments explain why, never what.** Name the measured failure or bug that shaped the code, not a restatement of it.
- **Verified, not asserted.** Say whether a fix was run against real data or only reasoned about.
- `packages/core` never imports from `packages/pipeline` (CI enforces it).
- One config mechanism per kind of value: `.env` for the environment, `config.json` for hand-edited values.

## Never commit

- Book text, EPUBs, or anything derived from a copyrighted novel.
- Databases (`data/db/`), generated media, or model weights.
- Keys or `.env`.

`data/` is ignored by default; a new folder there stays local unless deliberately tracked.

## GPU

Run one GPU job at a time. The language model and the image model must not share a small card; `ECHOTALES_COMPUTE=local-low` (the default) enforces this.
