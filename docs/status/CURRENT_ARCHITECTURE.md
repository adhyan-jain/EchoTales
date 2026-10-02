# EchoTales — current architecture

**Written 2026-09-29, as part of a cleanup/refactor pass** (see
`docs/status/REFACTOR_REPORT.md` for what changed and why). This is the page
a new researcher reads first — what EchoTales is, how it's structured, what's
production vs. research vs. historical, and the exact commands to run it or
reproduce results — without reading years of session notes first.

## What EchoTales is

A pipeline that reads a web-novel volume, builds a bitemporal narrative
knowledge graph, and drives a full-cast audiobook plus a manga-style visual
adaptation from it. **The graph is the research contribution; audio and
visual are demonstration surface.** See `README.md` and
`docs/design/architecture.md` for the full model (three-axis time, `state_of()`,
the ten non-negotiables) — this page is the map, not the territory.

## Package map

| Package | Classification | Why |
|---|---|---|
| `packages/core` | **CORE PRODUCTION** | Models, `Store`, `state_of()`/`StateResolver`, `disclosure.py`. Imports nothing from `packages/pipeline` — verified by grep (`from echotales.pipeline` returns empty in `packages/core/src/`), matching the paper's structural claim. |
| `packages/pipeline` | **CORE + SUPPORTING PRODUCTION** | All 13 subpackages (`ingest`, `spans`, `mentions`, `segment`, `speakers`, `anaphora`, `resolve`, `persona`, `voice`, `render`, `eval`, `world`, `llm`) are reachable from `cli.py`/`commands.py`, directly or transitively. `webview_server.py` is both the job/correction HTTP API and how `webview-server` is served. |
| `packages/research` | **RESEARCH — arena, one-way dependency** | Pre-registered experiments (`python -m echotales.research list\|run <experiment> [--stub]`) that import core+pipeline; nothing imports it back (`packages/research/tests/test_import_direction.py`). Results under `data/eval/research/<HID>/<run-id>/`; verdicts in `docs/research/DECISION_LOG.md`. |
| `packages/ecrdt` | **RESEARCH — standalone, isolated** | Zero dependencies, zero imports in either direction with core/pipeline, its own `pyproject.toml`. Investigates a separate, independent research question (provable epistemic non-interference under CRDT merge) — not part of the EchoTales pipeline and not a dependency of it. Can be understood, tested, and benchmarked entirely on its own. |
| `webview/` | **SUPPORTING PRODUCTION** | React review/production UI, consumes `webview-server`'s HTTP API. |
| `scripts/` | mixed — see below | `eval/`, `paper/`, `review/`, `maintenance/` are all load-bearing: every one is invoked by `scripts/reproduce_results.sh` or is a direct CLI-consistency dependency (verified). |
| `docs/EVOLUTION.md` / `docs/HANDOFF.md` / `docs/archive/*` | **HISTORICAL** | Append-only session log, current-pickup-point doc, and superseded plans/validation passes — by design, not a cleanup target. Read `docs/status/STATUS.md` instead of these for current state. |

## The core/pipeline boundary

`packages/core` never imports from `packages/pipeline` — this is a structural
claim the project makes (generation pipelines don't need to understand the
novel), enforced by `tools/check_deps.py` in CI, and verified independently
during this cleanup pass with a direct grep. It held.

## CLI entrypoints (all live, none orphaned)

`cli.py` → `commands.py::DISPATCH`, one handler per subcommand, each lazily
importing its real module:

`ingest`, `resolve`, `appearance`, `persona`, `voice`, `render`, `eval`,
`query`, `graph`, `export`, `webview`, `webview-server`, `run` (whole
pipeline in dependency order), `review`, `ablate`, `observations`,
`annotate`, `relevance`.

Every one of these was traced to a live import during this cleanup pass —
none is stubbed, orphaned, or dead.

## Where things live

```
packages/core/       models, store, state_of(), disclosure.py  (imports nothing from pipeline)
packages/pipeline/   ingest -> spans -> mentions -> resolve -> persona -> render -> voice -> eval;
                     webview_server.py is also the job / correction HTTP API
packages/research/   research arena; imports core+pipeline, never imported by them
packages/ecrdt/      standalone research prototype — see packages/ecrdt/README.md
webview/             React review and production UI
scripts/             eval/, paper/, review/, maintenance/, reproduce_results.sh
docs/                README.md is the index: HANDOFF (current state), EVOLUTION (history),
                     status/ (this file + STATUS.md + REFACTOR_REPORT.md), design/, results/, paper/, ops/, archive/
data/                README.md is the map (db/, novels/, gold/, eval/, scratch/, archive/)
```

## Pipeline stage order

`ingest` → `mentions` (gazetteer + NER) → `anaphora` (local resolution) →
`resolve` (global cross-chapter identity resolution) → `persona` (bodies/
appearance/canon) → `render` (panel direction + image generation) → `voice`
(casting + synthesis) → per-chapter video composite. See CLAUDE.md and
`docs/design/architecture.md` Section 6 for the full detail.

## Running it

```bash
source .venv/bin/activate
python3 -m pytest packages/core/tests packages/pipeline/tests   # 1,206 tests, no GPU needed (research: add packages/research/tests; 1,277 total across all suites, 2026-10-02)
python3 -m pytest packages/ecrdt/tests                          # 48 tests, separate suite
scripts/reproduce_results.sh                                    # regenerates every paper table/figure from committed artifacts
```

Everything is stub-first: `ECHOTALES_LLM_MODE=stub` and `--image-engine
stub`/`--engine stub` run the full pipeline deterministically with no GPU
and no network. Real runs use `ollama` locally or the Anthropic API.

`--db <path> render --novel <id> ...` — `--db` is a *global* flag before the
subcommand.

## What's intentionally experimental

- **`packages/ecrdt`** — a separate research question (epistemic
  non-interference under CRDT merge), not coupled to EchoTales, kept
  deliberately isolated so it can act as a demonstrator later without
  requiring EchoTales to depend on it.
- **`core/disclosure.py` (Minimal Disclosure Compiler)** — priority 1 of 3
  IPR-review candidates, opt-in only (`use_mdc=False` default everywhere).
  See `docs/status/STATUS.md`'s component matrix and
  `docs/results/MDC_DISCLOSURE_ABLATION.md`.
- **The resolver's learned scorer** — contributes 0 links on the canonical
  run; kept as documented, measured infrastructure, not claimed as a
  contribution. See `docs/status/STATUS.md`'s Scorer row.

## Patent / IP material

`docs/private/IP/` (gitignored) holds the invention disclosure and prior-art
bibliography — never referenced from a public doc, never summarized here.
`packages/ecrdt/IPR_REVIEW*.md` documents that package's own separate IPR
review process (five rounds, its own determination).
