# EchoTales — working notes for Claude Code

A pipeline that reads a web-novel volume, builds a bitemporal narrative
knowledge graph, and drives a full-cast audiobook plus a manga-style visual
adaptation from it. **The graph is the research contribution; audio and
visual are demonstration surface.** Read [README.md](README.md) first — it
states scope, the "why this is hard" framing, and known limitations more
concisely than anything below.

## Where the real documentation lives

Do not try to hold this project's architecture in your head from this file
alone — read the source doc for the thing you're touching:

- [`architecture.md`](architecture.md) — the bitemporal model, `state_of()`,
  and Section 11's ten non-negotiables (below).
- [`plans.md`](plans.md) — the full phase-by-phase specification.
- [`details.md`](details.md) — per-file design rationale.
- [`HANDOFF.md`](HANDOFF.md) — **the session log.** Every real bug found,
  every fix shipped, every open defect, in chronological numbered sections
  (currently past 4.51). **Read the last 2-3 sections before starting render
  or persona work** — it is the actual current-state-of-the-world doc, more
  current than any of the others.
- [`EVOLUTION.md`](EVOLUTION.md) — architecture decisions and reversals over
  time, with the measured reason each one happened.

If you fix something and it's the kind of finding future sessions need
(a root cause, a measured result, a defect that's only partly fixed), add a
new numbered section to HANDOFF.md rather than leaving it only in a commit
message. That log is what makes a fresh session productive in five minutes
instead of an hour of re-discovery.

## Layout

```
packages/core/       models, store, state_of() -- imports nothing from pipeline
packages/pipeline/   ingest -> spans -> segment -> mentions -> anaphora ->
                      resolve -> persona -> world -> render -> voice -> eval
webview/              React correction/review UI
data/<CODE>/          one novel's outputs (panels/, video/, audio/, references/),
                      versioned per run -- see pipeline/paths.py
data/gold/             annotations: offsets + short evidence snippets only,
                      never chapter text
```

`packages/core` importing from `packages/pipeline` is a CI failure —
"generation pipelines do not need to understand the novel" is a claim the
project makes structurally, not just in prose.

Pipeline stages run roughly in this order (see `cli.py` subcommands:
`ingest`, `resolve`, `appearance`, `persona`, `voice`, `render`, `eval`,
`query`, `graph`, `export`, `webview`): raw EPUB -> chapters/blocks ->
spans -> mentions (gazetteer + NER) -> identity resolution -> personas
(bodies/appearance/canon) -> world context -> panel direction + image
generation -> voice casting + synthesis -> per-chapter video composite.

## Setup and testing

```bash
source .venv/bin/activate      # uv-managed venv already present at repo root
python3 -m pytest packages/pipeline/tests/ -q     # ~400 tests, no GPU needed
```

Everything is stub-first: `ECHOTALES_LLM_MODE=stub` and `--image-engine
stub`/`--engine stub` run the full pipeline deterministically with no GPU
and no network, which is how CI and most iteration works. Real runs use
`ollama` locally (`qwen2.5:7b`, see `config.json` / `.env`) or the Anthropic
API; `config.json`'s `render.direction_first` toggle controls whether panel
direction (LLM) and image generation (local diffusion) run as two decoupled
passes so ollama and a local diffusion pipeline never share the GPU at once.

Running a real render against a novel needs `--db <path> render --novel
<id> ...` — `--db` is a *global* flag before the subcommand, not after it.
`data/reruns/*.db` are scratch copies used to test extraction fixes against
real data without touching the canonical `data/<novel>.db`.

## Non-negotiables (architecture.md Section 11)

1. No clustering — incremental resolution with evidence accumulation
2. Chapter ≠ time — three-axis temporal model
3. Self ≠ persona (continuity of consciousness vs. a body/identity)
4. Generic descriptors never enter the graph
5. Retraction ≠ interval end
6. Volume-first processing
7. High-precision automation with a bounded, measurable review queue —
   escalation rate is a reported metric, not a failure mode
8. The gazetteer compounds (gets cheaper and more accurate deeper into a volume)
9. Precision over recall in local resolution
10. Delivery markers override scene sentiment

## Conventions this codebase actually follows

- **Comments explain why, never what.** Every non-trivial function in this
  repo carries a comment naming the specific bug, measurement, or failure
  mode that shaped it — often with a HANDOFF section reference. Match that
  style: cite the measured failure, not a restatement of the code.
- **"Verified, not asserted."** HANDOFF entries distinguish a fix that was
  run against real data (with numbers) from one that's only "should work."
  Do the same — a real render/query beats reasoning about the code.
- **Versioned output directories, and name them.** Render/voice output goes
  under `data/<novel>/panels/vN/` etc. (`pipeline/paths.py::next_version`)
  so a rerun never silently overwrites the previous one. `v1`-`v9` had
  descriptive suffixes (`v9_short-clause-scene-restored`); `v10`-`v40`
  didn't, and turned into 31 directories nobody could tell apart without
  re-reading HANDOFF by date. **Every new version gets a short suffix**
  (`next_version` doesn't add one — pass it explicitly, e.g.
  `v44_carry-forward-cast-fix`), and a one-line entry in that novel's
  `data/<novel>/panels/ch<N>/VERSIONS.md` (what was tried, and an honest
  verdict from a viewer's point of view) **at the same time**, not as a
  follow-up. See `data/RI/panels/ch1/VERSIONS.md` for the format and the
  backfilled history of what v10-v43 actually were (or, for v10-v27,
  weren't — genuinely undocumented, said so rather than guessed).
- **Config split**: `.env` for environment-dependent values (LLM mode,
  hosts), `config.json` for values a human hand-edits directly (gateway
  host/model, render two-phase toggle). Don't add a third mechanism.
- **Source novels are never committed** (`data/raw/`, `*.epub` etc. are
  gitignored) — they're copyrighted texts supplied locally. Never write
  code that assumes they exist in git, and never add one to a commit.
- **CLIP's 77-token budget is a hard constraint** on every image-prompt
  path (`persona/prompt.py::fit_to_budget`) — a prompt field is a priority
  ranking, not reading order, and low-priority clauses are expected to fall
  off the end silently. When editing prompt assembly, check what actually
  survives truncation, not just what was appended.
- Commit conventions are in `.claude/RULES.md` (not shared with the repo,
  local only): push commits individually, never a `Co-Authored-By: Claude`
  trailer, no emoji or `§`-style symbols in commit messages.
- **After a considerable change, invoke the `docs-sync` subagent** (Agent
  tool, `.claude/agents/docs-sync.md`) before ending the turn — a new
  pipeline stage, a call path rerouted, a bug fixed that a doc calls open,
  a new flag/config value. This is how HANDOFF.md and friends stay true
  rather than drifting (see 4.49/4.50: a fix documented as "not yet
  implemented" was actually already half-written and broken). Skip it for
  trivial edits (typos, formatting, comment-only changes).

## Current known issues

See HANDOFF.md's latest numbered section for the actual current state —
it changes every session. As of Section 4.51, the live area of work is
the render/direction pipeline (`packages/pipeline/src/echotales/pipeline/render/`):
getting the LLM art director to draw only what a beat actually supports —
the correct cast, not an invented or out-of-scene one; the correct gender
default for someone unstated; a bounded panel count; and, per 4.51, a
beat's own narrated physical state (torn robes, blood, disheveled hair)
actually appearing on screen instead of the canon default — the
prompt-level bug there is fixed, but the fix doesn't reliably survive
CLIP's 77-token budget and the checkpoint doesn't reliably render it even
when it does. `.claude/agents/image-gen-debugger.md` is scoped to exactly
this area if you're picking up that thread.
