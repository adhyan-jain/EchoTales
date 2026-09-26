# Validation baseline — 2026-09-24

The checkpoint this session's evidence pass started from, recorded so every
later claim has a stated "before". Mechanically re-checkable: each row names a
command, not a recollection.

## Environment

| | |
|---|---|
| Date | 2026-09-24 |
| Branch | `validation/evidence-pass-2026-09-24`, cut from `master` |
| Commit at start | `6aed9f9` ("feat(eval): extend gold QA datasets to full-volume coverage") |
| Working tree at start | **115 dirty paths** — 50 modified, 65 untracked |
| Python | 3.12.13 (Clang 22.1.3), uv-managed `.venv` at repo root |
| GPU | NVIDIA RTX 4060 Laptop, 8,188 MiB, idle at session start |
| LLM | Ollama `qwen2.5:7b` (Q4_K_M, 4.7 GB), `ECHOTALES_LLM_MODE=local` |
| Test suite | **1,038 passed, 0 failed, 0 skipped**, 35.5s |

```bash
source .venv/bin/activate
python3 -m pytest packages/               # 1038 passed  (raw: data/eval/baseline/)
git rev-parse HEAD                        # 6aed9f9
```

**Note on counting tests.** `pyproject.toml` sets `addopts = "-q"`, so passing
`-q` again produces `-qq` and pytest prints **no summary line at all** — which
is why the count has been reported by eye before now. Run without `-q`.

## What was preserved

Weeks of work were untracked and one `rm` from gone: the entire ablation
harness, evidence cache, bootstrap stats, result persistence, blind-annotation
tool, observer-axis writer, render contract/plan builder, ten test files, and
**all of `docs/`**. Committed as `ce36528` before anything was changed.

**Honest scope caveat on that commit.** Four tracked files it touches
(`eval/gold.py`, `eval/draft.py`, `cli.py`, `commands.py`) carried uncommitted
modifications from *earlier* sessions before this one began, and this session
then edited them further. The two sets are not separable in git, because the
earlier ones were never committed. No clean line was drawn, and pretending one
was would be the same class of error this pass exists to remove.

Also committed: the two non-circular gold files, previously gitignored while
all three *circular* ones were tracked (`5383210`).

## Status at checkpoint

Legend — **VERIFIED**: measured on real data, command reproducible.
**EXPERIMENTAL**: implemented, its own code or docs defer the verdict.
**UNVERIFIED**: asserted or unit-tested only, never measured.
**MISSING**: confirmed absent by grep/read.

| Item | Status at checkpoint | Evidence |
|---|---|---|
| Observer-conditioned `state_of` **query** | VERIFIED | RI Bai Ning Bing ch200: READER 2 aliases, witness 1, non-witness 0 |
| Observer axis **populated** | UNVERIFIED at scale | `observation` rows exist in **1 of 27** databases (`provenance-ri.db`, 12 rows); `observations` is not a stage in `cmd_run` |
| Truth status / retraction **query semantics** | VERIFIED | `state.py:123-129`, `test_state.py::TestRetractionVersusIntervalEnd` |
| Retraction **writer** | **MISSING** | `contradiction.py::retract_alias_bindings` has zero callers; `retracted_chapter IS NOT NULL` is **0 rows across all 27 DBs** |
| Self/Persona split | VERIFIED for sequential reincarnation | RI `self1` → `body1`/`body2`. **0** personas bound to >1 self; **0** non-MAIN-timeline bindings; **0** `FABRICATED` aliases anywhere |
| Concurrent bindings / disguise / body-swap / dream-persona | UNVERIFIED | `packages/core/tests/test_state.py` only; absent from every database |
| Three-axis time | EXPERIMENTAL | All three defined; **no fact is ever written to a non-MAIN timeline** |
| Learned scorer | VERIFIED as inert | Settles 0 of 880 links; max output 0.527 over 10,058 pairs vs a 0.80 threshold |
| Ablation harness | VERIFIED | 9 conditions over the real evidence cache |
| NER windowing fix (EVOLUTION 4.76) | UNVERIFIED at checkpoint | Landed + unit-tested; real effect unmeasured — **this pass measures it** |
| Retriever recall@K by alias type | MISSING at checkpoint | No `--gold` flag; block gated on always-empty `confirmed`; the one alias-diverse file gitignored |
| Confirmed gold | **MISSING** | 0 records corpus-wide, and by owner decision this pass does not create any |
| Baseline A | EXPERIMENTAL | Built, 2 tests, **never executed**; no output artifact exists |
| Baseline B | MISSING at checkpoint | Did not exist |
| `GenerationState` multimodal compiler | **MISSING** | Zero hits repo-wide. Visual half exists (`build_render_plan`); the **voice path never calls `state_of` or touches `Persona`** |
| Paper figures/tables | MISSING | No figure or table generation script exists |
| Invention disclosure | EXPERIMENTAL | `docs/private/IP/invention_disclosure.md` exists (gitignored); `docs/status/STATUS.md:153` still says it does not |

## Known blockers at checkpoint, and what became of them

| Blocker as documented | Reality |
|---|---|
| "ollama unreachable from a sandboxed Claude Code shell" | **Wrong diagnosis.** The daemon was simply not running. `ollama serve` brought it up in **1 second**, and `localhost:11435` was reachable throughout. |
| "LINK-KG verification needs network" | **Resolved.** Full paper fetched and verified; see `docs/paper/PRIOR_ART_LINKKG.md`. |
| CLIPScore pixel QA needs a ~1.7 GB download | **Still blocked.** Deprioritised, not attempted. |
| Observer-contrast render figures need a GPU | GPU is free; gated behind the re-run's use of it. |

## Repository hygiene

- `.env` holds live OpenRouter / Gemini / NVIDIA / CivitAI keys. It is
  correctly gitignored and **was never committed** (verified against all refs
  with `git log --all -- .env`). Its values were printed into a session
  transcript on 2026-09-24; rotating them is cheap insurance.
- `data/db/reverend-insanity.db` is a **0-byte trap**. The canonical RI database
  is `data/archive/db/reverend-insanity-webview-working.db`.
- `docs/private/IP/` is gitignored (`.gitignore:160`) and must stay so — the repository
  is public, and publishing a disclosure is itself a disclosure.

## Reproducing this baseline

```bash
source .venv/bin/activate
python3 -m pytest packages/                                   # 1038 at checkpoint
echotales --db data/archive/db/reverend-insanity-webview-working.db eval \
    --novel reverend-insanity --gold data/gold/<file>.jsonl --validate-gold
echotales --db data/archive/db/reverend-insanity-webview-working.db eval \
    --novel reverend-insanity --gold data/gold/reverend-insanity-hardcases.jsonl
```

Results persist to `data/eval/results/<run_id>/metrics.json` with commit,
seed, database, gold path and platform; validation reports to
`data/eval/validation/<file>.json`.
