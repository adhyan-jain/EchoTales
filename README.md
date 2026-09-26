# EchoTales

A pipeline that reads a volume of a web novel and builds a **bitemporal
narrative knowledge graph**, then uses it to drive a full-cast audiobook and a
manga-style visual adaptation.

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
scripts/             eval/, paper/, review/, maintenance/, reproduce_results.sh
docs/                README.md is the index: HANDOFF (current state), EVOLUTION (history),
                     design/, results/, status/, paper/, ops/, archive/
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
- **Copyright.** For internal coursework only. Not for distribution. Source
  texts are not redistributed by this repository and must be supplied by the
  user.
