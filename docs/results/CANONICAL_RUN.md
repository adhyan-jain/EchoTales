# Canonical run — EchoTales v1

**Promoted 2026-09-25.** Every number in `docs/results/FINAL_EVIDENCE_TABLE.md`,
`docs/paper/TABLES.md` and `docs/status/FINAL_ECHOTALES_READINESS.md` comes from the
database below, unless a row says otherwise.

## 0. v1.1 (2026-09-27)

`data/db/reverend-insanity.db` is now **v1.1**: v1 plus the volume-level
title-holder pass (`echotales resolve --title-holders-only`,
`resolve/title_holders.py`, EVOLUTION 4.95). It links 22 "clan head / clan
leader" mentions to Gu Yue Bo (including chapter 1, before he is named), maps
3 epithet speaker lines to him, and gives the never-named Xiong clan head one
identity (8 mentions). Nothing else changed.

| | |
|---|---|
| sha256 | `a269566055ad60b87d2f6cca4d5d509199084420616102561f4863ca04d5475f` |
| v1 | archived at `data/archive/db/reverend-insanity-v1-2026-09-25.db`; the untouched build original stays at `data/scratch/reruns/v1-final-ri.db` (`42107645…`) |
| Re-checked on v1.1 | silver coreference (Table 4), hard-case resolution and taxonomy, observer ablation and evidence: **identical**. Retrieval (Table 5): Recall@1/10/20 identical; **Recall@5 87.0 → 84.8** (one title case moved from rank ≤5 to rank 6–10, because the holder's new title alias competes with the true candidate) |

### LOTM product database (2026-09-27)

`data/db/lord-of-the-mysteries.db` (the 40-chapter product/webview database,
not an evaluation source) was re-resolved with the name-order and
transmigration fixes (EVOLUTION 4.95) and its personas were rebuilt.

| | before | after |
|---|---:|---:|
| person entities | 102 | 93 |
| personas | **0** | 93 |
| resolved mentions | 2,312 | 2,334 |
| Zhou Mingrui / Klein | 177 / 954 (two people) | 1,162 (one) |

The previous file is archived at
`data/archive/db/lord-of-the-mysteries-v1-2026-09-27.db` (sha256 of the
original before `.backup`: `bac041fe…`). The promoted file is `e1f3d63a…`, a
`.backup` of `data/scratch/db/lotm-v1.1.db`. Its offsets predate the current
ingest, so it is not scored against the LOTM silver set; the ch1-20 rerun
below remains the evaluation source.
Known open defect: "Tingen" and "Tingen University" are typed as people.

## 1. Database identity

| | |
|---|---|
| Canonical path | `data/db/reverend-insanity.db` (gitignored, regenerable) |
| Built as | `data/scratch/reruns/v1-final-ri.db`, then copied after a WAL checkpoint; that file is kept as the provenance original |
| sha256 | `42107645f3ffe83ef01aedfb56434fa37a8d4d892dbedcaa48328fd8b0ef3456` (both files) |
| Replaced | a 0-byte file left at that path since 2026-09-13 (the "0-byte trap" in earlier docs); no data was overwritten |
| Code state | branch `validation/evidence-pass-2026-09-24`, commit `cd6f010` (demonstrative fix, EVOLUTION 4.90) plus `bf272de` (pronoun-recovery gate, 4.88) |
| Contents | 199 chapters, 16,360 blocks, 11,174 mentions, 267 entities, 11,092 alias bindings, 98 personas / 98 bindings, 12 observations across 11 observers |

**Previous evaluation database:** `data/scratch/reruns/ner-window-ri.db` (EVOLUTION
4.84), built before two code changes that affect it:
- the pronoun-recovery gate (4.88), which changes span speakers;
- the multi-word demonstrative fix (4.90), which changes mentions.

It is kept for comparison, not deleted. `data/archive/db/reverend-insanity-webview-working.db` is the older webview working copy and is **not** canonical.

## 2. How it was built

Run order matters: `resolve` deletes persona bindings, so personas are rebuilt after the evidence capture (`RUNPOD_MIGRATION.md` Section 4).

```bash
DB=data/scratch/reruns/v1-final-ri.db
echotales --db $DB run --novel reverend-insanity                         # 553 s
echotales --db $DB resolve --novel reverend-insanity --capture-evidence  # ablation cache
python3 -c "from echotales.core.store import Store; \
  from echotales.pipeline.commands import _build_client; \
  from echotales.pipeline.persona.build import build_personas; \
  s=Store('$DB'); build_personas('reverend-insanity', s, client=_build_client(s)); s.conn.commit()"
echotales --db $DB observations --novel reverend-insanity
sqlite3 $DB "PRAGMA wal_checkpoint(TRUNCATE);" && cp $DB data/db/reverend-insanity.db
# since 2026-09-27 a non-canonical build writes its compounding curve under
# data/scratch/eval/compounding/; promote it with the database:
cp data/scratch/eval/compounding/reverend-insanity.json data/eval/compounding/
```

The full run took 12 minutes on the local RTX 4060. That is not 47: NER responses were served from `data/lexicons/reverend-insanity-ner-cache.json`, which is keyed by chapter-text hash. A cold-cache run is the 47-minute figure in `NER_WINDOWING_RESULT.md`.

## 3. Configuration

| | |
|---|---|
| LLM | `qwen2.5:7b` via local Ollama (`ECHOTALES_MODEL_BACKEND=ollama`), `num_ctx` from `.env` |
| LLM attribution tier | chapters 1–3 (`run --llm-attribution-chapters` default) |
| Pronoun speaker recovery | **off** (default since 4.88) |
| Seed | `ECHOTALES_SEED` 20260923 for evaluation bootstrap |
| Link threshold | 0.80 (scorer); links in practice come from pre-filters |
| External API spend | none |

**Determinism.** NER is served from a text-hash cache and is identical. The LLM attribution tier and persona vetting are not deterministic:
- The rebuild reproduced the **aggregate** 46.1% attribution and 98 personas.
- **10 of 29** comparable tier-4 speaker assignments in ch1–3 changed.
- Aggregates are reproducible; individual tier-4 lines are not.

## 4. Reference sets — LLM-DRAFTED SILVER, never human gold

| File | Records used | Provenance | Used for |
|---|---:|---|---|
| `data/gold/reverend-insanity.jsonl` | 1,816 silver (entities) | Claude Sonnet / Opus, non-circular subset | coreference (Table 4) |
| `data/gold/reverend-insanity-hardcases.jsonl` | 88 with identity | Claude | hard cases, retrieval (Table 5) |
| `data/gold/lord-of-the-mysteries-c1-c3.toml` → `.jsonl` | 155 entity records | Claude Opus, drafted without the pipeline's output | generalisation (secondary run) |

Validation reports for each: `data/eval/validation/*.json`. Circular (`gold-auto-builder`) records are excluded everywhere (`GOLD_DATASET_README.md`).

## 5. Commands and artifacts

`scripts/reproduce_results.sh` runs all of this against the canonical database (exit 0, 2026-09-25).

| Command | Artifact |
|---|---|
| `echotales --db data/db/reverend-insanity.db eval --novel reverend-insanity` | `data/eval/results/<run_id>/metrics.json` |
| `... eval --novel reverend-insanity --gold data/gold/reverend-insanity-hardcases.jsonl` | same, hardcases run |
| `... ablate --novel reverend-insanity --out data/eval/ablation/reverend-insanity.json` | Table 6 |
| `python3 scripts/eval/hardcase_resolution.py` | `data/eval/hardcase_resolution.json` |
| `python3 scripts/eval/hardcase_taxonomy.py` | `data/eval/hardcase_taxonomy.json` |
| `python3 scripts/eval/recall_by_category.py` | `data/eval/recall_by_category.json` (Table 5) |
| `python3 scripts/eval/observer_evidence.py` | `data/eval/observer_evidence.json` |
| `python3 scripts/eval/baseline_comparison.py` | `data/eval/baseline_comparison.json` (Table 7) |
| `python3 scripts/eval/scorer_diagnosis.py` | `data/eval/scorer_diagnosis/` |
| `python3 scripts/paper/make_paper_artifacts.py && python3 scripts/paper/plot_paper_figures.py` | `docs/paper/` |

**Secondary run (generalisation):**
- LOTM ch1–20 → `data/scratch/reruns/lotm-gen-ch1-20.db`
- `echotales --db data/scratch/reruns/lotm-gen-ch1-20.db eval --novel lord-of-the-mysteries --gold data/gold/lord-of-the-mysteries-c1-c3.jsonl`
- result in `data/eval/results/lord-of-the-mysteries-1790302402-816d231e/`

**Audio artifact:** `data/novels/RI/audio-runs/ears-native/` (RI ch1, EARS bank, Chatterbox). It was rendered from `ner-window-ri.db`, **not** the canonical database.
- Its attributions do not all match the canonical run. The LLM attribution tier (ch1–3) is not deterministic across runs: **10 of 29** tier-4 lines present in both databases name a different speaker.
- The changes are not corrections. The canonical run credits the elders'-meeting lines to "Gu Yue Fang Yuan", who is not present at that meeting; the earlier run said "Bai Ning Bing", also absent. Neither run was checked line by line beyond ch1.
- This instability is itself evidence for the 4.88 finding: tier 4 is guessing from names near the line.

## 6. Security

- **Scan, 2026-09-25:** `git grep` over tracked files and `git log -p --all` for OpenRouter, Google, NVIDIA, GitHub and generic key patterns found **nothing** in the repository or its history. The same scan over untracked `data/`, `docs/` and `scripts/` found nothing. `.env` has never been tracked.
- **Exposure:** `.env` holds live OpenRouter, Gemini, NVIDIA and CivitAI keys. Their values were printed into an earlier assistant session's transcript. **Rotate all four.** No key value appears in any document.
- **`.env` line 12** is written `CIVITAI_API_KEY =<value>`. The space before `=` makes `source .env` fail in a shell; python-dotenv tolerates it. Fix by removing the space when rotating.
- The invention disclosure (`docs/private/IP/`) is gitignored and must stay out of this public repository.
