# Per-novel knowledge base (dossiers, glossary, future briefs)

Status 2026-11-28: code built and unit-tested; real runs are IN PROGRESS and resumable. This file is a handoff, not a
results report: the measured sections below are marked NOT YET MEASURED where the sweep has not produced them.

## What exists

Package `packages/pipeline/src/echotales/pipeline/knowledge/`:

- `dossier.py`: `build_dossiers(store, client, novel_id, chapters, only_entities=, force=, say=) -> MapReport`,
  `dossier_at(store, novel_id, entity_id, chapter, whole_novel=True, extrapolate=True) -> Dossier`,
  `first_in_person_chapter(store, novel_id, entity_id)`. One READER call per chapter window, shown only the entities
  the stored mentions place there. A fact is kept only if its quote is verbatim in its block, the entity has a stored
  mention in that block (else a yes/no model question) and no rival name sits in the quote; appearance facts need the
  model's `in_person` flag. Rows are `attribute` rows (people's looks on the body persona via `persona_at`; role and
  affiliation on the self), evidence `"quote" [chN #block model]`. A changed single-valued key (hair, eyes, skin,
  build, apparent age) closes the earlier interval via the new `Store.set_attribute_interval`; innate keys of the first
  row reach back to the body start; costume and condition end with their chapter.
- `glossary.py`: `build_glossary(store, client, novel_id, other_dbs, keep=40)`, `load_glossary`, `candidates`,
  `contexts_for`. Candidates are spaCy noun chunks recurring over chapters and rare in the contrast novels; a model
  keeps world terms; each entry is drafted from up to 12 contexts spread over the volume; every claim is `text` (its
  quote must occur in the contexts, else demoted) or `general_knowledge`. Stored as derived artifact `kb:glossary:<novel>`.
- `future_brief.py`: `build_brief(store, novel_id, chapter)`, `build_briefs`, `load_brief`. Per entity: prominence,
  first mention, first in person (from the dossier map's presence records), last chapter, chapters after, matters_later
  (3 or more later chapters), role line, setups (same entity plus the same event verb in a later sentence; verbs common
  to the volume are learned and ignored). Stored as `kb:brief:<novel>:<chapter>`.
- CLI: `echotales --db <abs path> knowledge build --novel <id> [--chapters A-B] [--only-entities ...] [--stages dossier,glossary,brief] [--contrast-db DB ...]`.
  Resume key: `kb:dossier-map:<novel>:<chapter>:<model>:<scope>` artifacts.
- Tests: `packages/pipeline/tests/test_knowledge_dossier.py`, `test_knowledge_glossary_brief.py` (fake LLM).
  Full suite: 3200 passed, 29 skipped. Ruff clean on the touched files.

## Runs and settings

- Scratch DBs: `data/scratch/kb/reverend-insanity.db`, `data/scratch/kb/lord-of-the-mysteries.db` (copies; `data/db/` untouched).
  Always pass ABSOLUTE `--db` paths (a relative path inside a worktree silently creates an empty DB).
- Real-model check: the RI ch1 gemma2:9b run is recorded in `llm_call` (10 reader calls, model gemma2:9b), so it was real, not stub. Worktrees have no `.env`: runs need `ECHOTALES_MODEL_BACKEND=ollama ECHOTALES_LLM_MODE=local ECHOTALES_LLM_LOCAL_HOST=http://localhost:11434` (set in `scratchpad/kb.sh`).
- Model for the sweep: `qwen3:8b` (`ECHOTALES_READER_MODEL=qwen3:8b`), `num_ctx` 4096 (`ECHOTALES_LLM_LOCAL_NUM_CTX=4096`): gemma2:9b still spilled to CPU at 4096 while others share the GPU (coordinator finding). The 13 ch1 facts are from gemma2:9b (a 21% CPU spill at num_ctx 8192 on that run, a rule violation, disclosed); everything else is qwen3:8b. Verify `ollama ps` shows 100% GPU during a batch.
- Measured on RI ch1: 4 windows, 20 facts proposed, 13 accepted, 1 dropped as not present, 123 s (includes model load).
  At about 2 minutes per chapter the 199-chapter sweep is about 7 hours of GPU time plus lock waits.
- qwen3:8b versus gemma2:9b benchmark on 20 chapters: NOT DONE. gemma2:9b was used without it.

## Background job (leave running; resumable)

`/tmp/claude-1000/-home-adhyan-Desktop-EchoTales/b76a1e83-d8df-44b7-b17e-adfd395f96cc/scratchpad/pipeline.sh` runs, each
step under `flock /tmp/echotales-gpu.lock`: RI glossary plus briefs ch1-3, LotM glossary plus briefs ch1-3, then the RI
dossier sweep over chapters 1-199 in batches of 3 (lock held per batch). Log: `.../scratchpad/pipeline.log`
(ends with `PIPELINE-DONE`). Check: `tail pipeline.log`; `ps aux | grep pipeline.sh`; count done chapters with
`sqlite3 data/scratch/kb/reverend-insanity.db "select count(*) from derived_artifact where id like 'kb:dossier-map:%'"`.
To continue after a stop, rerun the same script; finished chapters are skipped.

## Still to do (exact commands)

1. Wait for the sweep (or run more of it): `.../scratchpad/sweep.sh /home/adhyan/Desktop/EchoTales/data/scratch/kb/reverend-insanity.db reverend-insanity 1 199 3`.
2. Read Bai Ning Bing's dossier at ch1 (id `reverend-insanity:self:0035e71331`, first in person expected from ch45):
   `dossier_at(store, "reverend-insanity", "reverend-insanity:self:0035e71331", 1.0)`. His ch1 mentions are unresolved in
   the DB (empty `target_id`), so ch1 itself yields no facts for him; his look can only come from later chapters and is
   returned flagged `extrapolated`. If no later chapter describes his look, say so.
3. Measure: fact precision on a random 30 accepted facts (check each quote against the chapter text), coverage before
   and after (entities with at least 1 and at least 3 appearance facts; before: hair_color 9, eye_color 5 entities, 0 for
   Bai Ning Bing), runtime per chapter, glossary entries for "elder", "clan head" (RI) and three LotM terms, the RI ch1
   brief. Write JSON into `data/eval/knowledge/` and fill this file. Quotes in committed files at most 8 words.
4. The qwen3:8b versus gemma2:9b benchmark on 20 chapters (set `ECHOTALES_READER_MODEL=qwen3:8b`, use `force`/separate DB copy).

## Known weaknesses seen so far

- gemma2:9b labelled "his hair was disheveled" as hair_color (a style); key semantics are model-dependent.
- The clan head's "middle-aged" (ch1 block 37) was not extracted in the first ch1 run; roles are stated per window only.
- Facts are written on MAIN_TIMELINE only; past-life and memory timelines are not separated except through the body split.
- Mentions with an empty `target_id` (for example ch1 "Bai Ning Bing") are invisible to the map pass.
