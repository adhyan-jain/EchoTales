# EchoTales

A pipeline that reads a volume of a web novel and builds a **bitemporal
narrative knowledge graph**, then uses it to drive a full-cast audiobook and a
manga-style visual adaptation.

The graph answers one query:

```
state_of(target, timeline, position, observer=READER)
  -> {aliases, attributes, relationships, persona, truth_status}
```

Everything downstream — voice selection, prosody, reference images, panel
casting — consumes that query. **The graph is the research contribution.** Audio
and visual are demonstration surface.

See [`HANDOFF.md`](HANDOFF.md) for current status and open defects,
[`architecture.md`](architecture.md) for the model, [`details.md`](details.md)
for per-file detail, and [`plans.md`](plans.md) for the full specification.

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
packages/core/       models, store, state_of()  — imports nothing from pipeline
packages/pipeline/   ingest, spans, segment, mentions, speakers, anaphora, resolve
apps/api/            orchestration and correction UI
data/raw/            source EPUBs (not committed)
data/gold/           annotations — offsets and short evidence snippets only
data/lexicons/       genre-neutral seed + per-novel induced vocabulary
data/<CODE>/         one novel's outputs: panels/, video/, audio/, references/,
                     canon/ — each versioned per run (`pipeline/paths.py`)
data/scene-references/  hand-collected composition/character images (input)
data/voice/          VCTK (read speech) and CREMA-D (91 actors, six emotions)
tools/               annotation CLI, replay debugger
```

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
  standard conformal prediction requires. Mitigated with Mondrian
  (class-conditional) calibration keyed on `alias_type` and within-novel
  calibration, but a residual violation remains and is reported as a limitation.
- **Annotation covers hard cases, not full volumes.** The primary gold set is
  ~200 sparse, long-span decision points. Dense annotation exists for only 5
  chapters per novel. Standard coreference metrics therefore rest on a small
  sample; the long-span hard-case results are the defensible claim.
- **No global collision-free voice assignment.** In a long cultivation novel the
  co-occurrence graph over principals is near-complete, so the chromatic number
  exceeds any archetype-appropriate palette. Colouring runs within archetype
  buckets and residual collisions between non-co-occurring minor characters are
  accepted and logged.
- **Visual pipeline is a 3-chapter showcase**, not a volume-scale system.
- **Phase 6 thresholds are untuned.** See `HANDOFF.md` Section 4.1.
- **Copyright.** For internal coursework only. Not for distribution. Source
  texts are not redistributed by this repository and must be supplied by the
  user.
