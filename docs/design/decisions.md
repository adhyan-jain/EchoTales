# EchoTales decisions log

A running, plain-language record of **what we decided, why, and what it changed**, written so you can learn the project from it. It is the "why" companion to `docs/HANDOFF.md` (what is open now) and `docs/EVOLUTION.md` (numbered bug and fix history). New decisions are appended; nothing is deleted, only superseded (marked **Superseded**).

How to read an entry: **Decision** (what), **Why** (the measured or stated reason), **Effect** (files and behaviour), **Status** (planned / done / reversed).

---

## 0. The project in one page

EchoTales reads a web-novel volume and builds a **bitemporal narrative knowledge graph**: who exists, which names point at whom, how they look, and *when* each fact became true versus when the reader learned it. From that graph it drives an audiobook (voices) and a manga-style video (images, motion). The graph is the research contribution; audio and video are the demonstration.

Pipeline order: ingest -> segment/spans -> mentions -> (reader pass, new) -> resolve -> speakers -> personas -> appearance -> voice -> render -> compositor/video.

Core ideas you will meet everywhere:
- **Self vs persona**: a Self is a continuous mind (Klein); a Persona is a body/identity it wears (Mr. Fool, a disguise). One Self can have many personas.
- **State of the world** is always asked at a position: `state_of(target, chapter)`. Chapter is not time; story time, reading time and knowledge time are separate axes.
- **Evidence**: every fact should carry the quote that proves it.
- **Stub-first**: everything runs deterministically with no GPU or network in tests (`ECHOTALES_LLM_MODE=stub`).

## 1. Direction decisions (2026-10-22, from the build-plan session)

### D1. Fix the extractor before any new media work
- **Decision**: Phase A (extraction rewrite) must pass its accuracy gates before real image/voice/video backends are built.
- **Why**: the audit of Lord of the Mysteries ch1-40 found 0 appearance attributes for 93 entities, no second personas, speaker accuracy 41% on hand-labelled ch7, and placeholder reference images. Rendering from that bible only produces confident nonsense.
- **Effect**: plan phases A (bible) -> B (review UI) -> C (real media backends) -> D (screenplay/episodes) -> E (Path 2 video). Each ends in a gate; the next starts only when it passes. Calendar estimates were dropped on purpose.
- **Status**: planned, Phase A in progress.

### D2. Reader LLM is local ollama for now
- **Decision**: the chapter reader pass runs on local `qwen2.5:7b` through the existing provider switch. A strong hosted model is a later swap behind the same switch, only if the local model misses the gates, and only after asking.
- **Why**: earlier owner rules: local models only (no RunPod/OpenAI since 2026-10-17) and a $5-10 total cloud budget. The build-plan doc assumed a paid API; this overrides it.
- **Effect**: prompts must be small and schema-light (7B models), with sub-calls if needed.
- **Status**: decided.

### D3. Gold labels come from Claude in-session, spot-checked by you
- **Decision**: Claude labels 5 chapters each of LotM, Reverend Insanity (RI) and Omniscient Reader (ORV): cast, aliases, personas by chapter range, appearance facts with quotes, and the speaker of every line. You check a sample.
- **Why**: labels must not come from the pipeline's own output ("circular gold", rejected in code by `CircularGoldError`).
- **Effect**: new gold files under `data/gold/`, scorer under `eval/`.
- **Status**: planned.

### D4. Gates for Phase A
- **Decision**: speaker accuracy >= 90%, appearance-fact recall >= 85%, persona-link recall >= 90%, entity-kind accuracy >= 95%.
- **Why**: a published method reaches about 90% speaker attribution with the cast list in the prompt (Michel et al.); today's pipeline is far below. The other thresholds keep the review queue bounded (non-negotiable 7).
- **Status**: decided.

### D5. Text-only canon
- **Decision**: delete the hand-written appearance tables (`persona/canon.py`, `render/beat_canon.py`, per-novel `persona/attire.py` entries). Appearance comes only from the book text. A human override becomes a visible correction record.
- **Why**: `canon.py` hard-coded Klein's eyes as "deep grey" and a trench coat while the text says brown eyes and a linen shirt, so renders drew grey eyes.
- **Status**: planned (step A8).

### D6. Review-gated workflow
- **Decision**: analyse automatically -> user reviews flagged items -> lock a versioned bible -> generate. Renders read only a locked snapshot. Edits are correction records re-applied after any re-extraction.
- **Why**: bounded review plus reproducible snapshots enforces quality without trusting every automatic decision, and stops a later edit silently changing an episode already made.
- **Status**: planned (Phase B).

### D7. Licence-clean model stack for anything sold
- **Decision**: product media models must be commercially licensed (Apache/MIT class). NoobAI XL / Illustrious are non-commercial and leave the product path once their replacement passes Gate C. Character LoRAs are not in the plan unless you ask.
- **Why**: a non-commercial model's licence also covers the images it generates.
- **Status**: decided; removal waits for Gate C.

## 2. Phase A implementation decisions

### D8. Version stamping and stale-build refusal (A1) - done 2026-10-22
- **Decision**: every database build records a `PIPELINE_VERSION` (now `"2"`) in `pipeline_run.pipeline_version`. A real (non-stub) render is refused with HTTP 409 when the database's newest stamp is missing, empty, or older.
- **Why**: the field existed but was always empty. LotM's personas were built from "0 spoken lines" before the speaker-join fix and nothing flagged it.
- **Effect**:
  - `packages/pipeline/src/echotales/pipeline/version.py`: `PIPELINE_VERSION`, `staleness_reason()`.
  - `core/pipeline_run.py::ensure_pipeline_run(pipeline_version=...)` stamps new runs and re-stamps a re-entered run.
  - `core/store.py`: `set_pipeline_run_version`, `latest_pipeline_version`.
  - Stage digests used a hard-coded `v1`; they now use the version, so a bump invalidates cached stage results.
  - `webview_server.py::_stale_build_refusal` guards the render routes; the **stub engine is exempt**.
  - Tests: `packages/pipeline/tests/test_pipeline_version.py`.
- **How to use**: bump `PIPELINE_VERSION` whenever extraction output changes meaning.
- **Known limit**: the stamp means "newest code that touched this run", not "every stage was rebuilt".
- **Status**: done, full core+pipeline suite green.

### D10. The reference set is "silver", and the scorer matches by name (A2, started 2026-10-22)
- **Decision**: Claude-drafted labels live in `data/gold/reader/<novel>-ch<NN>.json` with `provenance: "model"` and `confirmed: false`. We call them **silver** in every report; only a person confirming record by record (the `eval/gold.py` contract) makes them gold. The plan's word "gold set" means this silver set until you spot-check it.
- **Why**: the repo already burned itself once: 6,952 labels read back out of the pipeline's own table were reported as human gold (EVOLUTION 4.74). Labels here are drafted from the text only, without looking at pipeline output, which is what keeps them independent.
- **Effect**:
  - `eval/reader_gold.py` scores per-line speaker accuracy (and counts "false dialogue", spans that cover no gold line, e.g. scare quotes), persona links (Fool -> Klein), entity kind, explicit ages, and appearance facts.
  - Gold characters are matched to pipeline entities **by name and alias, never by id**, so the reference stays independent of the pipeline's inventory. The pipeline's speaker column sometimes holds the label itself ("Audrey") rather than an entity id, so an id with no entity row is read as a name; anonymous slot ids never equal a gold name, so an unnamed slot is never correct.
  - A multi-paragraph speech opens a quote in every paragraph and closes only in the last, so a quote runs to its closing mark or the end of the block.
  - Tests: `packages/pipeline/tests/test_reader_gold.py`.
- **First measurement (LotM ch7, current run-of-record DB, scratch copy)**: speakers **16/43 = 37%** (the audit's by-hand count was 16/39 = 41%; same result, different denominator since multi-quote lines are counted separately), **8** pipeline dialogue spans cover no gold line, persona links **1/4** (Fool, Justice, Hanged Man unlinked), age **0/1** (Audrey's 17 not recorded), kind 6/6 on the 6 entities that exist. This is the baseline Phase A must beat; Gate A needs speakers >= 90%.
- **Status**: scorer done and verified on real data; ch7 labelled. Remaining: 5 chapters each of LotM, RI and ORV, with appearance facts and persona events.

## 3. Documentation policy

### D9. Few, living docs
- **Decision**: keep a small set of maintained docs and archive the rest; no new loose docs. Entry points: `README.md`, `CLAUDE.md`, `docs/README.md` (index), `docs/HANDOFF.md` (open work), `docs/EVOLUTION.md` (history), `docs/design/decisions.md` (this file), `docs/design/architecture.md`.
- **Why**: dozens of small docs drift out of date and cannot be trusted.
- **What was done (2026-10-22)**: tracked markdown went from about 190 files to 123. Research docs were **merged, not archived** (your call: the research gave good results), into one file per topic under `docs/research/` (table in `docs/research/README.md`); 16 results docs became 3 under `docs/results/`; duplicate root files (`RUN_STEPS.md`, `Demo_Video_Script.*`) were removed (copies live in `docs/paper/project_doc/`); `docs/status/REFACTOR_REPORT.md` moved to `docs/archive/`. Each merged section keeps the original text and names its old path, and the originals remain in git history.
- **Left alone on purpose**: the 84 files in `docs/research/preregistrations/` (hash-manifested locked records), `docs/research/PREFIX_FAITHFULNESS/`, `PAPER/`, `experiments/` and `technical_contribution_probes/` (read by code or scripts), and `docs/paper/`.
- **Known cost**: relative links inside the locked preregistrations that point at a merged file are now stale; they are records, so they were not edited. Search `docs/research/README.md`'s table to find where a file went.
- **Status**: done.

## 4. Open questions
- Whether the local 7B model reaches Gate A, or the reader must move to a hosted model (needs your approval; see D2).
- Overwriting run-of-record databases in `data/db/` (rebuilds go to `data/scratch/reruns/` first).
- Which model caches to delete, one by one.

## 5. Maintenance rule
Whenever a decision is made or reversed, or a phase step lands, add or update an entry here in the same turn, with the measured result when there is one. Bug-level detail goes to `docs/EVOLUTION.md`; open work to `docs/HANDOFF.md`.
