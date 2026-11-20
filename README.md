# EchoTales

Turn a web-novel volume into a full-cast audiobook and a manga-style adaptation, driven by a
**bitemporal narrative knowledge graph** that tracks who is who, and when, across the whole book.
Everything runs on your own machine; the stub modes need no GPU and no network.

## Demo

A demo video is coming. None has been recorded yet, so there is no link here on purpose.

## Install and run

```bash
scripts/setup.sh      # detects your GPU, lists each model and its licence, asks before downloading
make demo             # stub-mode demo on a sample book, no GPU
make serve            # the studio, at http://127.0.0.1:8787
```

`scripts/setup.sh --dry-run` shows the hardware preset it would pick (`laptop-8gb`, `desktop-24gb` or `cloud`)
and changes nothing. A CUDA Docker image is available through `docker compose up`.
`uv run echotales engines --commercial-safe` lists every engine whose licence has been checked as allowing
commercial use; engines whose licence has not been checked are left out, not guessed.

In the studio (http://127.0.0.1:8787): create a project, upload an EPUB, then use the five-step "Make the
audiobook" panel. Language models run locally through ollama; speech and image generation need a GPU. The stub
modes (`ECHOTALES_LLM_MODE=stub`) run everything without one.

## Measured results

Every number below comes from a committed record and names it. Where nothing was measured the cell says so.
No other tool has been run on the same material, so this table compares EchoTales' own options, not competitors;
that comparison needs the public benchmark (below) to be filled in by other people.

| What | Result | Measured on | Source |
|---|---|---|---|
| Speaker attribution, reader on `gemma2:9b` | Lord of the Mysteries 95.4%, Omniscient Reader 77.9%, Reverend Insanity 76.2% | ch 1-3 (and held-out ch 21) of each volume, against **model-drafted** references | `docs/EVOLUTION.md` 4.124 |
| Image model, Z-Image Turbo vs NoobAI XL | Z-Image better in 11 of 12 scene categories; 32.3 s vs 21.7 s per image, peak 5.78 vs 5.42 GiB | 24 briefs, 160 images, 8-GB laptop GPU; scored by one reviewer by eye | `docs/EVOLUTION.md` 4.165 |
| Local video, LTX-Video 2B distilled | about 12 s denoise plus 6 s decode per 4 s clip, 7.0 GB peak (torch) with the model warm; 27-70 s per clip with reloads | 512x768, 97 frames, 8-GB laptop GPU | `docs/EVOLUTION.md` 4.146 |
| Speaker attribution on the public benchmark | not measured yet | Pride and Prejudice, Sherlock Holmes | `data/eval/benchmark/` holds the references |
| Audiobook listening quality | not measured: nobody has listened blind | | `docs/HANDOFF.md` "Pick up here" |

The speaker references behind the first row were drafted by a model, not checked by a person, so those
percentages are regression numbers, not accuracy claims (see "Known limitations").

### Public benchmark

`python -m eval.run_benchmark public status` (or `uv run echotales benchmark status`) lists the references in
`data/eval/benchmark/`: speaker attribution and scene fidelity on Pride and Prejudice and Sherlock Holmes
(public domain), cross-panel identity and scene fidelity on two Pepper&Carrot episodes (CC BY 4.0). They hold
offsets and hashes only, never book text, and **every item is still a model's draft** (`checked_by_human: false`).
`echotales benchmark check` walks a file so a person can accept or edit each item; `score` prints a banner saying
NOT human-verified until that is done. Scoring is deterministic; run `lines` to get what to attribute from your own
copy of the book.

## How it works

The graph answers one query:

```
state_of(target, timeline, position, observer=READER)
  -> {aliases, attributes, relationships, persona, certainty}
```

(`StateOfResult` also carries a `truth_status` field, defaulted to `TRUE`,
but `state_of()` never assigns it from the underlying fact — as of the
2026-09-24 validation pass it is inert on every call. `certainty`, which
*is* set from the accepted facts, is the field that actually distinguishes
"we know this" from "this is the best reading available".)

Everything downstream — voice selection, prosody, reference images, panel
casting — consumes that query. **The graph is the research contribution.** Audio
and visual are demonstration surface.

The pipeline, in order: EPUB to chapters and blocks, spans, mentions (name list plus NER), identity resolution
(incremental, with evidence accumulation, no clustering), a reader pass for speakers and appearance facts, personas
(a body or identity, kept apart from the self), panel direction and image generation, voice casting and synthesis,
then a per-chapter video. Each engine in it is declared once, with its licence, memory need and measured speed, in
`packages/pipeline/src/echotales/pipeline/engines/registry.py`; adding a model is one entry there.

See [`docs/HANDOFF.md`](docs/HANDOFF.md) for current status and open defects,
[`docs/design/architecture.md`](docs/design/architecture.md) for the model, [`docs/design/details.md`](docs/design/details.md)
for per-file detail, and [`docs/design/plans.md`](docs/design/plans.md) for the full specification.

## Why this is hard

The target content is translated Chinese and Korean web fiction, where naming
is volatile in ways Western-fiction tooling does not anticipate:

- One character carries dozens of surface forms, and the set *shifts* over the
  story. Two mentions may share no characters yet denote one person; two may be
  textually identical yet denote different people.
- Titles transfer between holders. The same title at chapter 20 and chapter 300
  is frequently a different person.
- Chapter number is not a time coordinate. A chapter may hold present action, a
  dream replaying a third party's past, and past-life memory.
- Identity is revealed, faked, and retracted. A retraction ("was never true") is
  a different operation from an interval end ("stopped being true").

## What this is, and is not

**High-precision automation with a bounded, measurable review queue.** The
escalation rate — the share of decisions routed to human review — is a
*reported metric*, not a failure mode.

This deliberately replaces an earlier "full automation, no human in the loop"
framing, which contradicted the correction interface, the DEFER queue, active
learning from correction behaviour, and translator-handoff confirmation — all of
which are part of the design. A system that quantifies and bounds its review
burden is a stronger claim than one that pretends to need none.

The identity resolver is honestly characterised as **a hand-tuned rule system
with a learned tiebreaker over five dense features** — not a learned model. The
rare, high-precision signals (explicit identity declarations, exact matches on
confirmed aliases) are hard pre-filters, because they would never accumulate
enough gold instances for a fitted weight to mean anything.

## Scope

| | Scope |
|---|---|
| **Primary novel** | Reverend Insanity Vol. 1 (ch 1–199) — carries the headline results |
| **Spot-checks** | LOTM and ORV, 5 chapters each, for generalisation only |
| **Gold set** | ~200 hard decision points across a full volume, plus 3×5 dense chapters for MUC/B³/CEAF |
| **Audiobook** | Primary novel only (~21,000 spans) |
| **Visual** | **3-chapter showcase** (~40 panels), chosen to demonstrate temporal reference sheets |

Multi-novel breadth is deliberately sacrificed. Hard-case accuracy across one
full volume demonstrates the contribution better than three shallow novels.

## Layout

```
packages/core/       models, store, state_of()  (imports nothing from pipeline)
packages/pipeline/   ingest -> spans -> mentions -> resolve -> persona -> render -> voice -> eval;
                     webview_server.py is also the job / correction HTTP API
webview/             React review and production UI
eval/                benchmark harness; eval/public/ is the public benchmark (python -m eval.run_benchmark public)
scripts/             eval/, paper/, review/, maintenance/ (incl. the lint ratchet), reproduce_results.sh
docs/                README.md is the index: HANDOFF (current state), EVOLUTION (history),
                     design/, results/, status/, paper/, archive/
data/                README.md is the map. The parts you touch:
  db/<novel-id>.db     each novel's database (run of record)
  novels/<CODE>/       everything generated for one novel: panels/, video/, audio/, ...
  gold/ eval/          reference sets and every measured result
  scratch/             disposable: reruns, test databases, debug output
```

Every default output path comes from `packages/pipeline/src/echotales/pipeline/paths.py`;
nothing else in the code names a folder under `data/`.

`core` importing `pipeline` is a CI failure, because "generation pipelines do
not need to understand the novel" is a claim the paper makes.

## Setup

```bash
uv sync --python 3.12          # 3.12 exactly: ML wheels lag newer
uv run pytest
make verify                    # tests, then the ruff and mypy ratchet (a count may fall, never rise)
```

## Configuration

Copy `.env.example` to `.env`. The pipeline runs against a stub by default, so
the whole thing is testable with no GPU and no network:

```
ECHOTALES_LLM_MODE=stub        # stub | local | api | hybrid
ECHOTALES_MODEL_BACKEND=stub   # stub | ollama | anthropic
```

Per-task model selection lives in `packages/pipeline/.../llm/tasks.py`. No call
site names a model, so switching development (ollama) to production (API) is one
config value.

## Source texts

Source novels are **not** committed. Place your own copies in `data/raw/` and
register them in `data/sources.toml`.

`data/gold/` stores character offsets and short evidence snippets rather than
chapter text — the CoNLL/OntoNotes convention — so annotations can be shared
with collaborators without redistributing the novels.

## Languages

EchoTales is English-only for now. The name gazetteer, the speaker rules and the dialogue-quote handling were
built and measured on English text, and a book in another language would build without an error and be wrong
without saying so. The Studio upload screen shows the same statement (the upload reply carries a `language` field).
Other source languages will be added in the order people ask for them.

## Known limitations

Stated here because they are load-bearing, not incidental.

- **Exchangeability violation in conformal prediction.** The gazetteer is
  designed to make decisions easier as the volume progresses; that is the
  compounding contribution. It also breaks the exchangeability assumption
  standard conformal prediction requires. **Not yet mitigated**: `resolve/
  gate.py` implements standard (non-Mondrian) conformal calibration — a
  single global `alpha` over the whole score distribution, not a
  class-conditional split keyed on `alias_type` (see `docs/HANDOFF.md`'s
  "Architecture-review items not yet implemented" item 4, "not started").
  The residual violation is unmitigated, not merely residual, and is
  reported as an open limitation.
- **There is currently no confirmed gold set at all.** Every file in
  `data/gold/` is draft coverage — model-drafted, `confirmed: false` — and
  the one file that previously read `confirmed: true` (RI ch1-60, 6,952
  records) was retracted 2026-09-23: it was built by reading the
  pipeline's own resolved output back out of its database, so scoring
  against it measured the system against itself (`docs/EVOLUTION.md` 4.74).
  It is quarantined at `data/gold/_unusable/`. Full-volume draft coverage
  exists for all three novels; two small files
  (`reverend-insanity-c1-c5.jsonl`, `reverend-insanity-hardcases.jsonl`)
  are independent of pipeline output but still unconfirmed. No standard
  coreference metric or long-span hard-case result in this repository is
  currently anchored to human-reviewed ground truth.
- **The "independent" RI silver set is also trivially easy, for a second,
  unrelated reason.** Measured 2026-09-24:
  `reverend-insanity.jsonl`'s silver subset is 1,816 mentions over only 23
  distinct surface strings, 100% recoverable by grouping on the literal
  surface — no coreference resolution required to score well on it.
  `reverend-insanity-c1-c5.jsonl` is 100% recoverable too, over 308 scorable
  mentions and 34 surfaces. Scoring
  it reproduces exactly the B³ P=100.0/R=94.6/F1=97.2 that `docs/EVOLUTION.md`
  4.74 already retracted for a different reason (gold drafted from the
  pipeline's own output). `reverend-insanity-hardcases.jsonl` (63.6%) is the
  only evaluation set in this repository that measures anything. An
  automated check (`eval/validate_gold.py::_surface_triviality`) now fails
  any gold file that scores ≥99% recoverable this way.
- **No global collision-free voice assignment.** In a long cultivation novel the
  co-occurrence graph over principals is near-complete, so the chromatic number
  exceeds any archetype-appropriate palette. Colouring runs within archetype
  buckets and residual collisions between non-co-occurring minor characters are
  accepted and logged.
- **Visual pipeline is a 3-chapter showcase**, not a volume-scale system.
- **Phase 6 thresholds are untuned.** See `docs/HANDOFF.md` Section 4.1.
- **Copyright.** Code is Apache-2.0 (see `LICENSE`, `NOTICE`). Source texts are
  not redistributed by this repository and must be supplied by the user.
