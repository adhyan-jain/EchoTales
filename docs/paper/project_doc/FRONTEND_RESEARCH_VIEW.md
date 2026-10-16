# Research view in the webview

A page that shows the project's research claim (name-keyed memory leakage in LLM reading of fiction) for a demo:
a dashboard of stored results and a live probe that runs one local model on three arms of one real passage.
Everything on it is labelled "Exploratory results; human labelling pending" (labels are text-derived; event selection
by the model-drafter; owner spot-check pending).

## Start it

```bash
source .venv/bin/activate
python scripts/chimera/build_demo_items.py          # once; needs data/raw/pd_gutenberg/pg<ID>.txt; writes data/scratch/demo/probe_items.json
cd webview && npm ci && npm run build && cd ..       # or `npm start` for hot reload on :3000
ollama serve                                         # for the live probe only; models: qwen2.5:7b llama3.1:8b mistral:7b-instruct phi4-mini gemma2:9b
echotales webview-server --source <any>.db:<id>:"<label>" --static-dir webview/build
```

`--source` is mandatory for the server but the Research page does not use it. For a demo with no novel loaded, point it at an
empty scratch database: `python -c "from echotales.core.store import Store; Store('data/scratch/demo/demo.db').close()"` and use
`--source data/scratch/demo/demo.db:demo:"Research demo" --corrections-dir data/scratch/demo/corrections`.

Page URL: **http://127.0.0.1:8787/research** (with `npm start`: http://localhost:3000/research). Linked from the "Research"
button in the account header and from "Tools" in the project sidebar. If a server password is set, the usual sign-in applies.

The server is single-threaded: while a probe runs (a few seconds, up to about 30 s with a cold model) other requests wait.

## What each section shows, and where the numbers come from

All files are under `data/eval/chimera/` and are only read, never written.

| Section | Shows | Source |
|---|---|---|
| Headline cards | Reference model (gpt-5.6-luna) gap, pooled local-model gap, share of the gap recovered by cue-preserving renaming | `pd_final_pooled.json` (`luna_only.all_v2_v3_v6`, `valid_pool.all_v2_v3_v6`); `pd_v5/analysis.json` (`pools.G2_valid.recovered_fraction`) |
| Gap by model and dataset | Per-model A-minus-B gap with 95% event-cluster interval for v2 (19 events), v3 (12 books), v6 (7 events, did not replicate), plus the valid local pool and the three-dataset pool | `pd_adversarial_checks.json` (`per_model_cluster`, v2/v3); `pd_final_pooled.json` (`v6_per_model`, `valid_pool`, `luna_only`); pre-registered verdicts from `pd_v3/analysis.json`, `pd_v5/analysis.json`, `pd_v6/analysis.json` |
| Cue-preserving renaming (B3) | Premature rate and plain-control accuracy for A (original), B (letter cipher), B3 (pseudonyms that keep gender / first-vs-surname cues) | A rate from `pd_memory_free_validity.json` (`premature_A`); B = A minus `gap_A_minus_B` and B3 = A minus `gap_A_minus_B3` from `pd_v5/analysis.json` (pairs-weighted over v2 and v3); control accuracy `ctrl_acc_*` from `pd_v5/analysis.json` (plain mean over model-dataset cells). Valid local models come from `pd_final_pooled.json` `per_dataset_valid_models` |
| Dose-response | Mean gap by how many of 5 local models recognise the book (post hoc) | `pd_dose_response.json` |
| Live probe | One item, one local model, three arms: windows (cut to the marked sentence), candidates, answer, seconds per arm and total, one-line verdict | `data/scratch/demo/probe_items.json` (built by `build_demo_items.py` from the frozen study prompts) and local ollama |
| Validity gate and planned study (collapsed) | G2a / G2b per model and dataset; the lean / core / wide confirmatory designs with GPU hours and cost | `pd_memory_free_validity.json`, `pd_final_pooled.json` (v6); `confirm_runpod_plan.json` |

Measured timings are read from `docs/paper/project_doc/figures/demo_timings.json` when present (shown under the probe).

Reading the probe: every item is pre-reveal, so the true identity is not yet knowable. "Premature: true identity" means the
model answered the true-identity letter; "Abstains" (UNDETERMINED) is the correct first-reader answer; "Other candidate" is
a different letter. A model that is premature under original names but abstains under renamed text is using memory of the
book. The six items are illustrative (chosen where stored runs show the effect most clearly, in six different books);
headline numbers use all items.

## Probe details and safety

- `POST /api/research/probe {item_id, model, arms?}`; temperature 0, seed 20261016, `num_ctx` 2048, `num_predict` 24, ollama
  JSON-schema `format` whose enum is that arm's candidate letters plus UNDETERMINED (the study's decoding).
- Allow-list: only the five local models. No paid API is reachable from this route.
- One probe at a time; refused if under 1 GiB RAM is available; refused (and unloaded) if ollama placed any of the model in
  system RAM; the model is unloaded (`keep_alive` 0) after the last arm, also on failure.

## Commands

```bash
python scripts/chimera/build_demo_items.py [--texts data/raw/pd_gutenberg] [--out data/scratch/demo/probe_items.json]
python -m pytest packages/pipeline/tests/test_research_demo.py -o addopts="" -p no:cacheprovider -q
cd webview && CI=true npx react-scripts test --watchAll=false
```

## Measured on this machine (RTX 4060 Laptop 8 GiB, 15 GiB RAM, item GG-pre073, 2026-10-16)

Seconds per arm A / B / B3 and total, server-side (`figures/demo_timings.json`). Cold = model not in GPU memory, so arm A includes the load (weights in the OS file cache); warm = model preloaded in GPU memory with the same options.

| Model | Cold | Warm |
|---|---|---|
| qwen2.5:7b | 4.08 / 0.66 / 0.60, total 5.34 s (load 3.58 s) | 0.63 / 0.67 / 0.55, total 1.85 s |
| llama3.1:8b | 3.76 / 0.48 / 0.40, total 4.64 s (load 3.28 s) | 0.57 / 0.47 / 0.44, total 1.48 s |

Load time depends heavily on the file cache: the very first qwen2.5:7b probe after boot took 9.07 s (7.22 s load), and probes
run while npm/jest were using RAM took 11.9-25.5 s. `GET /api/research/summary`: median 0.95 ms server round trip over 30
requests (9.5 kB); in headless Chromium the page's fetch took 2.1 ms and DOMContentLoaded was at 51 ms.

On this item qwen2.5:7b answers the true identity (F, James Gatz) under original names and abstains under both renamings;
llama3.1:8b answers F under original names and under the cipher, and E under pseudonyms.

Screenshots: `figures/ui_01_research_overview.png`, `ui_02_gap_by_model.png`, `ui_03_cue_and_dose.png`, `ui_04_live_probe_result.png`.
