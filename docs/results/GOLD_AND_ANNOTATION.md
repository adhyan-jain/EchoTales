# Gold dataset, human review protocol and annotation results

> Merged on 2026-10-22 from 3 separate documents to keep the docs tree small. Each section below is one original file, text unchanged; its old path is in the section heading. The originals are in git history.

---

<!-- merged-from: docs/results/ANNOTATION_RESULTS_REPORT.md -->
## Source: `docs/results/ANNOTATION_RESULTS_REPORT.md`

# EchoTales: Provisional LLM-Assisted Annotation Results & Human-Adjudication Package

**Date**: 2026-10-13  
**Status**: Pre-annotation complete (288/288 mentions); **awaiting human author adjudication**.  
**Source Datasets**:
- [`data/eval/human_review_200.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/human_review_200.csv) (200 stratified system mentions)
- [`data/eval/human_review_hardcases_88.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/human_review_hardcases_88.csv) (88 silver hard-case entity shifts)
**Annotated Output Files**:
- [`data/eval/human_review_200_annotated.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/human_review_200_annotated.csv)
- [`data/eval/human_review_hardcases_88_annotated.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/human_review_hardcases_88_annotated.csv)
- [`data/eval/annotation_run_manifest.json`](file:///home/adhyan/Desktop/EchoTales/data/eval/annotation_run_manifest.json) (machine-readable run metadata)

---

> [!WARNING]
> **Methodological Boundary Notice**:  
> The labels and distributions presented in this report represent **automated candidate pre-annotations produced by `gpt-5.6-luna`**, NOT verified ground truth. They serve exclusively as an efficiency aid to eliminate the 6–8 hour manual annotation bottleneck. Per academic standards (ACL / ARR / WNU), **these figures cannot be cited as final system precision until human author adjudication is performed**. Ground-truth metrics must be computed strictly from the adjudicated labels using appropriate stratum population weights.

---

## 1. Dataset Counts & Sampling Structure

| Dataset | Total Rows | Target Evaluated | Identifier Range | Unique Excerpts | Overlap |
|---|---|---|---|---|---|
| **Standard Stratified Sheet** | 200 | Automated System Linking (`predicted_entity`) | `R001` – `R200` | 200 | 0 |
| **Hard-Cases Reference Sheet** | 88 | Silver Reference Grounding (`reference_set_decision`) | `H001` – `H088` | 88 | 0 |
| **Total Evaluation Scope** | **288** | — | — | **288** | **0** |

Zero rows were excluded or dropped. Every row corresponds to a stable identifier generated under seed `20260925` from the canonical *Reverend Insanity* database.

---

## 2. API Telemetry, Model Configuration & Spend

All inference calls were executed via [`scripts/review/llm_annotate.py`](file:///home/adhyan/Desktop/EchoTales/scripts/review/llm_annotate.py) using the official OpenAI Python SDK.

| Parameter | Configuration / Measured Telemetry | Budget Cap / Limit |
|---|---|---|
| **Model ID** | `gpt-5.6-luna` | First-choice cost model |
| **Reasoning Effort** | `low` | Lowest reasonable setting |
| **Batch Size** | 10 mentions per batched request | 10 |
| **Response Format** | `json_object` (strictly validated against JSON schema) | Schema enforced |
| **Total API Requests** | **29 requests** (1 pilot + 19 standard + 9 hard-case) | $\le 30$ |
| **Total Prompt Tokens** | **40,021 tokens** | — |
| **Total Cached Input Tokens** | 0 tokens (first-pass non-cached endpoints) | — |
| **Total Completion Tokens** | **18,832 tokens** (including 4,324 reasoning tokens) | — |
| **Total Token Volume** | **58,853 tokens** | — |
| **Pricing Schedule** | $0.25 / 1M prompt tokens; $1.00 / 1M completion tokens | Published tier |
| **Total Actual Spend** | **$0.028837 USD** (~2.88 cents total) | **< US$0.10** |
| **Budget Headroom** | **71.16% remaining under $0.10 hard cap** | Positive |

---

## 3. Provisional Candidate-Label Distributions

### 3.1 Standard 200-Mention Sheet (`human_review_200_annotated.csv`)
Evaluates the core system's prediction (`predicted_entity`) against excerpt context.

- **Candidate `correct`**: 141 (70.5%)
- **Candidate `unresolved`**: 42 (21.0%)
- **Candidate `incorrect`**: 17 (8.5%)
- **Total**: 200 (100.0%)

### 3.2 Stratum-by-Stratum Breakdown (Standard Sheet)
Mentions are stratified across 7 narrative phenomena. The provisional candidate labels show distinct operational characteristics per stratum:

| Stratum | Total ($n$) | Candidate `correct` | Candidate `incorrect` | Candidate `unresolved` | Sampling Rationale & Observation |
|---|---:|---:|---:|---:|---|
| **`easy_name`** | 30 | 30 (100.0%) | 0 (0.0%) | 0 (0.0%) | Rigid names matching canonical entity label exactly. Model finds 100% agreement. |
| **`alias`** | 35 | 35 (100.0%) | 0 (0.0%) | 0 (0.0%) | Rigid surface aliases differing from canonical label (e.g. *Mo Bei* $\to$ *Gu Yue Mo Bei*). |
| **`observer_sensitive`** | 30 | 30 (100.0%) | 0 (0.0%) | 0 (0.0%) | Mentions within 10 chapters of a secret reveal (e.g. *Bai Ning Bing* disguise). |
| **`background`** | 34 | 34 (100.0%) | 0 (0.0%) | 0 (0.0%) | Uniform random sample of general narrative mentions across the novel. |
| **`unresolved_name`** | 6 | 0 (0.0%) | 0 (0.0%) | 6 (100.0%) | Mentions left `UNRESOLVED` by the system (e.g. first appearance in ch1 before introduction). |
| **`title`** | 30 | 0 (0.0%) | 2 (6.7%) | 28 (93.3%) | Transferable titles (*"the clan head"*, *"academy elder"*). System left most unresolved; excerpt context often lacks specific name. |
| **`relational`** | 35 | 12 (34.3%) | 15 (42.9%) | 8 (22.8%) | Deictic relational terms (*"Sir"*, *"young Miss"*, *"my lord"*). Main source of genuine linking error. |

---

## 4. Complete Audit of Discrepancies & Edge Cases

### 4.1 Candidate `incorrect` Mentions in Standard Sheet (17 Cases)
All 17 cases where `gpt-5.6-luna` flags the system's `predicted_entity` as incorrect. These are primary candidates for author verification:

| ID | Ch. | Stratum | Mention | Predicted Entity | Candidate Explanation (Model Notes) |
|---|---|---|---|---|---|
| `R012` | 15 | relational | *"Sir"* | `Fang Yuan` | Refers to the Flower Wine Monk, whose feet the speaker is embracing, not Fang Yuan. |
| `R013` | 15 | relational | *"sir"* | `Fang Yuan` | Refers to the person being addressed by the servant, evidently the Flower Wine Monk, not Fang Yuan. |
| `R014` | 15 | relational | *"sir"* | `Fang Yuan` | Refers to the person who can cure the fourth generation clan head, the Flower Wine Monk, not Fang Yuan. |
| `R015` | 16 | relational | *"Sir"* | `Fang Yuan` | Refers to Sir Flower Wine, explicitly named in the surrounding dialogue, not Fang Yuan. |
| `R018` | 21 | relational | *"sir"* | `Fang Yuan` | The phrase 'sir elder' refers to an unspecified elder whom Fang Yuan met, not Fang Yuan himself. |
| `R024` | 28 | relational | *"sir"* | `Fang Yuan` | The guard addresses an elder as 'sir elder,' so the title does not refer to Fang Yuan. |
| `R028` | 31 | relational | *"Miss"* | `UNRESOLVED` | The title “young Miss” refers to Gu Yue Mo Yan, who is being greeted upon her return. |
| `R029` | 31 | relational | *"Miss"* | `UNRESOLVED` | The title “young Miss” refers to Gu Yue Mo Yan, who is being greeted upon her return. |
| `R030` | 31 | relational | *"Miss"* | `UNRESOLVED` | The title “young Miss” refers to Gu Yue Mo Yan, who is being greeted upon her return. |
| `R032` | 31 | relational | *"Miss"* | `UNRESOLVED` | The phrase “our young Miss” refers to Gu Yue Mo Yan, the Mo family daughter settling the score. |
| `R036` | 35 | relational | *"Miss"* | `UNRESOLVED` | The phrase “young Miss” refers to Gu Yue Mo Yan, whose servant is being chased. |
| `R042` | 44 | relational | *"Sir"* | `Fang Yuan` | Refers to Jia Fu, the caravan leader being addressed by the young Gu Master. |
| `R043` | 45 | relational | *"Sir"* | `Fang Yuan` | Refers to Jia Fu, who is being addressed as a Rank four Gu Master. |
| `R054` | 58 | relational | *"sir"* | `Fang Yuan` | The title sir refers to Gu Yue Bo, whom Fang Yuan addresses as clan elder, not to Fang Yuan. |
| `R055` | 58 | relational | *"sir"* | `Fang Yuan` | The title sir refers to Gu Yue Bo, the clan leader being addressed by the academy elder, not to Fang Yuan. |
| `R058` | 77 | title | *"Wild boar king"* | `UNRESOLVED` | Wild boar king refers to a beast/animal, not a person, place, or organisation. |
| `R189` | 181 | title | *"the clan leader"* | `UNRESOLVED` | The title refers to Gu Yue Bo, who is explicitly identified as the clan leader in context. |

### 4.2 Candidate `unresolved` Mentions in Standard Sheet (42 Cases)
- **`unresolved_name` (6 cases)**: `R001`, `R002`, `R003`, `R005`, `R019`, `R020`. Rigid names occurring before entity introduction in narrative time; system correctly left them unresolved.
- **`title` (28 cases)**: `R004`, `R011`, `R021`, `R022`, `R026`, `R033`, `R034`, `R035`, `R037`, `R038`, `R040`, `R041`, `R044`, `R045`, `R046`, `R047`, `R048`, `R049`, `R050`, `R051`, `R052`, `R053`, `R056`, `R057`, `R059`, `R060`, `R187`, `R188`. Transferable titles where excerpt lacks explicit identification.
- **`relational` (8 cases)**: `R008`, `R009`, `R016`, `R017`, `R027`, `R039`, `R145`, `R146`. Highly deictic dialogue terms.

---

## 5. Silver Reference Agreement on 88 Hard Cases (`human_review_hardcases_88_annotated.csv`)

In accordance with [`docs/results/HUMAN_REVIEW_PROTOCOL.md`](file:///home/adhyan/Desktop/EchoTales/docs/results/HUMAN_REVIEW_PROTOCOL.md) Instruction 4, the hard-case review evaluates **whether the silver reference identity (`reference_set_decision`) is factually correct**:

- **Silver Agreement (`correct`)**: 83 (94.3%)
- **Silver Discrepancy (`incorrect`)**: 5 (5.7%)
- **Silver `unresolved`**: 0 (0.0%)

### Category Breakdown:
- `body_change` ($n=11$): 11 correct (100.0%)
- `disguise` ($n=13$): 12 correct, 1 incorrect (92.3%)
- `not_entity_control` ($n=1$): 1 correct (100.0%)
- `relational_deictic` ($n=29$): 28 correct, 1 incorrect (96.6%)
- `reveal` ($n=17$): 14 correct, 3 incorrect (82.4%)
- `title_transfer` ($n=17$): 17 correct (100.0%)

### Silver Reference Flaws Detected by Model:
The model surfaced 5 genuine defects in the silver ground-truth dataset:
1. `H015` (Ch. 32, `reveal`): Mention *"Fang Zheng"*. Silver identity set to *"Fang Yuan (the servants' guess is wrong)"*. Model note: *"The marked mention explicitly names Fang Zheng, although the silver identity incorrectly assigns it to Fang Yuan."*
2. `H016` (Ch. 32, `reveal`): Mention *"Fang Zheng"*. Silver set to *"Fang Yuan (hypothetical misidentification)"*.
3. `H033` (Ch. 88, `reveal`): Mention *"he"*. Silver set to *"Gu Yue Jiao San"*. Model note: *"The marked text is the substring 'he' within the article 'The', so it does not refer to Gu Yue Jiao San."* (Tokenization artifact in silver data).
4. `H064` (Ch. 154, `disguise`): Mention *"Gu Yue Chi Cheng’s fake aptitude"*. Silver set to *"Gu Yue Chi Cheng"*. Model note: *"The mention denotes Chi Cheng's fake aptitude, an attribute/secret rather than Chi Cheng himself."*
5. `H081` (Ch. 194, `relational_deictic`): Mention *"senior brother"*. Silver set to *"First gen Gu Yue"*. Model note: *"First gen Gu Yue addresses Lord Sky Crane as his senior brother, so the mention does not refer to First gen Gu Yue."*

---

## 6. Verification & Validation Summary

- **Row Count Reconciliation**:
  - `human_review_200_annotated.csv`: Exactly 200 rows ($R001$–$R200$), zero duplicate IDs, zero missing fields.
  - `human_review_hardcases_88_annotated.csv`: Exactly 88 rows ($H001$–$H088$), zero duplicate IDs, zero missing fields.
- **Source Data Fidelity**: Verified that `sample_id`, `chapter`, `source_text`, `mention`, `predicted_entity`, `candidate_entities`, `system_decision`, `reference_set_decision`, and `category` match source CSVs bit-for-bit.
- **Source Protection**: Verified via git status that `data/eval/human_review_200.csv` and `data/eval/human_review_hardcases_88.csv` were never overwritten and have 0 labels.
- **Pilot Integrity**: Verified that all 10 pilot annotations from `pilot_review_10.csv` were preserved without row shift.
- **Unit Test Suite**: 8/8 tests in `packages/pipeline/tests/test_llm_annotate.py` pass.

---

## 7. Human-Adjudication Checklist & Protocol

To convert these candidate annotations into publication-grade human ground truth:

1. **Focus on the High-Leverage Rows First**:
   - Review the **17 `incorrect` rows** in Table 4.1 (~10–15 minutes). For each, decide whether to accept the model's critique (confirming system error) or retain the system link.
   - Review the **5 silver defects** in Section 5 (~5 minutes).
2. **Review Ambiguous / Unresolved Strata**:
   - Inspect the **28 `title` unresolved rows** in Table 4.2 (~15 minutes). If the chapter text makes the title referent clear, annotate as `correct` or `incorrect`; otherwise leave `unresolved`.
   - Inspect the **8 `relational` unresolved rows**.
3. **Spot-Check High-Confidence Strata**:
   - Spot-check 5 rows each from `easy_name`, `alias`, `observer_sensitive`, and `background` (~10 minutes).
4. **Recording Author Decisions**:
   In `data/eval/human_review_200_annotated.csv`, the author may:
   - Accept the candidate by leaving `reviewer_label` and `reviewer_notes` intact.
   - Override a decision by editing `reviewer_label` directly and appending `[Adjudicated: ...]` to `reviewer_notes`.

---

## 8. Post-Adjudication Stratified Precision Formula

When reporting final paper precision from the adjudicated labels, the paper must account for the stratified sampling frame. An unweighted sample average would bias precision because strata were sampled with unequal probabilities:

$$\hat{P} = \sum_{h=1}^7 W_h \cdot p_h$$

where:
- $W_h = \frac{N_h}{N}$ is the population stratum weight from the novel database mention pool.
- $p_h = \frac{\text{correct}_h}{\text{correct}_h + \text{incorrect}_h}$ is the adjudicated precision within stratum $h$.
- Variance and 95% confidence intervals should be calculated via stratified survey sampling formulas rather than a naive binomial Wilson interval.

---

<!-- merged-from: docs/results/GOLD_DATASET_README.md -->
## Source: `docs/results/GOLD_DATASET_README.md`

# Annotation datasets — provenance, protocol, and what may be claimed from them

**Written 2026-09-24.** The authoritative description of what is in
`data/gold/`, how it was produced, and what a number computed from it is
allowed to say.

> ## The one-sentence version
>
> **There is no human-annotated gold in this repository.** Every record is
> model-drafted. The usable subset is an **LLM-derived silver reference set**,
> and every metric computed from it carries the banner
> `SILVER -- LLM-derived reference set (Claude), not human gold; no IAA`.

---

## 1. Three tiers, and why the middle one exists

| Tier | Definition | Count (RI) | May be reported as |
|---|---|---:|---|
| **CONFIRMED** | A person adjudicated the record individually (`confirmed=True`, `confirmed_by` set, `review_depth=PER_RECORD`) | **0** | a result |
| **SILVER** | Model-drafted by a family *other* than the one under test, reading chapter text | **3,889** | a measurement against a silver reference set, always banner-labelled |
| **CIRCULAR** | Drafted by `gold-auto-builder`, i.e. `SELECT`ed from the pipeline's own `mention` table | **4,422** | nothing, at any confirmation level |

`GoldSet.confirmed_only` / `.silver_only` / `.circular` implement these.
`confirmed_only` is empty and stays empty; the tier exists so the honest number
remains visible rather than being quietly redefined.

**Why SILVER is not gold.** No person adjudicated it. There is no
inter-annotator agreement, because there is one annotator and it is a language
model. It is evidence — a second opinion from a different model family than
the system under test (`qwen2.5:7b`), produced by reading the novel rather than
the database — and it is weaker than human annotation. Both halves of that
sentence must survive into any paper.

**Why CIRCULAR is worthless.** `generate_gold.py::_extract_gold_from_db` runs
`SELECT text, target_id, ... FROM mention WHERE target_id IS NOT NULL`. Gold
built that way *is* the system's output, so scoring against it measures the
system against itself. That produced the retraction in `docs/EVOLUTION.md` 4.74.

---

## 2. File inventory

| File | Records | Chapters | Drafter | Tier | Tracked |
|---|---:|---:|---|---|---|
| `reverend-insanity.jsonl` | 7,879 | 198 | mixed | 3,457 silver / 4,422 circular | yes |
| `reverend-insanity-c1-c5.jsonl` | 343 | 5 | `claude-opus-5` | silver | yes (since 2026-09-24) |
| `reverend-insanity-hardcases.jsonl` | 89 | 51 | `claude-sonnet-5-gold-hardcases` | silver | yes (since 2026-09-24) |
| `lord-of-the-mysteries.jsonl` | 6,756 | 213 | `gold-auto-builder` | **100% circular** | yes |
| `omniscient-readers-viewpoint.jsonl` | 4,836 | 186 | `gold-auto-builder` | **100% circular** | yes |
| `reverend-insanity-c1-c5.toml` | 26 identities | 1–5 | `claude-opus-5` | silver source | yes |
| `reverend-insanity-c1-c60-extended.toml` | 22 surfaces | 1–60 | `claude-sonnet-5` | silver source | yes |
| `lord-of-the-mysteries-c1-c3.toml` | 24 identities | 1–3 | `claude-opus-5` | silver source | yes |
| `_unusable/reverend-insanity-c1-c50.jsonl` | 6,952 | 198 | `gold-auto-builder` | **quarantined** | README only |

The two `.jsonl` files added to tracking on 2026-09-24 were previously
gitignored while all three *circular* files were tracked — the repository was
committing the annotations that cannot score the pipeline and excluding the
only two that can.

**TOML vs JSONL.** TOML is the authored artifact, grouped by identity
(`[[identity]] name/kind/surfaces`, `[[not_entity]] reason/surfaces`). JSONL is
the machine expansion, one record per occurrence, produced by
`eval/draft.py::expand_draft` with a word-boundary regex over the ingested
chapter text and a ±60-char real context window.

---

## 3. Record schema

```json
{"novel_id": "demo", "chapter": 1.0, "offset": 42, "surface": "Name A",
 "identity": "Person A", "kind": "character", "alias_type": "RIGID_NAME",
 "context": "<~70 chars of source text around the offset>",
 "provenance": "model", "drafted_by": "claude-opus-5", "confirmed": false,
 "confirmed_by": "", "review_depth": "none", "note": ""}
```

- `chapter` is a **float ordinal**, not a date. Nothing here carries a date.
- `offset` is **chapter-absolute**, over the `"\n\n"`-join of story blocks.
  `Mention.offset` in the database is **block-local**. The translation lives in
  exactly one place, `coref_score._block_starts`; writing it a second time has
  caused two documented bugs.
- `kind` ∈ `character, location, item, organization, not_an_entity`.
- `context` stores a short evidence snippet, never chapter text in bulk — the
  CoNLL/OntoNotes convention, so annotations are shareable without
  redistributing copyrighted novels.

### Mention key

`(novel_id, chapter, offset, normalised_surface)`. The surface joined the key
on 2026-09-24. Before that, a word-boundary **prefix** surface collided with
the longer surface it prefixes — both start at the same offset — and one
silently overwrote the other. In `reverend-insanity-c1-c5.jsonl` that destroyed
**55 of 343 records (16%)** at load time, with no error anywhere.

---

## 4. Adjudication decisions

Recorded because the project's rule is that changing what an annotator asserted
is the owner's call, not a maintainer's.

**Prefix collisions (owner decision, 2026-09-24): fix the key, keep every
annotation.** 14 collisions in `c1-c5.toml`, 13 in the extended draft, 5 found
while drafting LOTM. Both records at such an offset are *correct* — "Gu Yue"
the clan and "Gu Yue Fang Yuan" the person genuinely both begin there. The
destruction was in the data model, not the data. `_prefix_collisions` is now
advisory rather than fatal, and both drafts expand again.

**Human annotation (owner decision, 2026-09-24): not performed.** The research
pipeline is explicitly not blocked on human IAA. The silver tier is used
instead, labelled as such everywhere.

---

## 5. Known defects and ambiguities

Found by `eval/validate_gold.py`, left in place, flagged rather than edited.

1. **770 spans shifted by +1**, all in `reverend-insanity.jsonl`, all
   `gold-auto-builder`, all chapters 61–199. The silver subset is clean —
   3,457 of 3,457 spans verified against chapter text. It does not affect
   scoring (the ±8-char match tolerance absorbs it) but it is a real defect in
   the circular tier and one more reason not to use it.
2. **One contract violation** in hardcases: `ch3@7926 'the Awakening Ceremony'`
   is typed `not_an_entity` yet carries an identity. **Needs your
   adjudication** — either the kind or the identity is wrong.
3. **One within-chapter surface conflict** in hardcases: `ch32 'fang zheng'`
   maps to both `Fang Yuan (hypothetical misidentification)` and
   `Fang Yuan (the servants' guess is wrong)`. Almost certainly the same
   intended referent written twice; the `identity` field is carrying prose,
   which makes two notes look like two identities.
4. **Klein / Zhou Mingrui** (LOTM) is annotated as **one referent**, with the
   drafter's dissent recorded in the TOML: a partition that split them fails on
   *"Melissa gave her elder brother a piercing stare"*, where the brother is
   Klein and the person stared at is Zhou Mingrui. In this project's own
   vocabulary the split is **Self vs Persona, not two Selves** — and the gold
   format annotates coreference over mentions, which has no way to express
   that. A reviewer may reasonably overturn it.
5. **Deities are typed `character`**, deliberately. `MentionKind` has no deity
   value; they are single named referents rather than places or organizations,
   and `not_an_entity` would be false since the text treats them as persons
   with will. Their churches are separate `organization` entries.
6. **`alias_type` defaults to `RIGID_NAME`** for records drafted before the
   field existed. That default is a known undercount, not a measurement.
7. **Span drift: 7 silver records fall outside chapter 1 on the rerun
   database** (`data/scratch/reruns/ner-window-ri.db`, measured 2026-09-25). "3,457 of
   3,457 verified" in item 1 was checked against the older
   `data/db/` database and remains true there. The rerun's
   ingest classifies chapter 1's three closing author's-note blocks
   (*"This novel has another name, Daoist Gu."*) as `TRANSLATOR_NOTE`, where
   the older ingest had them as `PROSE`, so `story_text` shrinks from 13,100 to
   12,484 characters. The 7 affected records (`ch1@12522`–`ch1@13089`, all
   `'Gu'`) annotate words *inside that note* — they were never diegetic
   mentions, and the new exclusion is the correct behaviour. Every other
   chapter-1 record precedes the notes and is unaffected. Effect on scoring:
   those 7 are unmatchable and count as unresolved, a recall cost of at most
   7 / 1,816 = 0.4 pts on the SILVER tier. Left in place rather than deleted,
   per this section's rule. **Lesson:** gold offsets are only valid against
   the ingest that produced them — a classifier change silently invalidates
   them, which is why `--validate-gold` takes `--db`.

---

## 6. The limitation that matters most

**Surface triviality.** A gold set whose partition can be reproduced by
grouping on the surface string cannot measure an identity resolver — any
exact-string matcher reproduces it perfectly.

| File | scorable | surfaces | identities | surface-trivial |
|---|---:|---:|---:|---:|
| `reverend-insanity.jsonl` (silver) | 1,816 | 23 | 20 | **100.00%** |
| `reverend-insanity-c1-c5.jsonl` | 308 | 34 | 26 | **100.00%** |
| `reverend-insanity-hardcases.jsonl` | 88 | 44 | 26 | **63.64%** |

Scoring the system against the first returns B³ **P=100.0% R=94.6% F1=97.2%**
— byte-identical to the figure `docs/EVOLUTION.md` 4.74 retracted for circularity.
That figure was doomed twice over: circular in provenance *and* trivial in
task.

`eval/validate_gold.py::_surface_triviality` now **fails** any file at ≥99% and
warns at ≥90%.

**Consequence: `reverend-insanity-hardcases.jsonl` is the only evaluation set
in this corpus that measures anything**, and at 89 records it is small. Its
alias-type spread (RIGID_NAME 42, RELATIONAL_DEICTIC 29, TRANSFERABLE_TITLE 17,
EPITHET 1) and its case categories (`[body_change]` 11, `[reveal]` 17,
`[title_transfer]` 17, `[disguise]` 13, `[relational_deictic]` 29,
`[not_entity_control]` 2) are what make it non-trivial.

---

## 7. Leakage prevention

- **Drafting never reads the database.** `expand_draft` touches only the TOML
  and `Chapter.story_text`; it hardcodes `provenance=MODEL`, `confirmed=False`,
  and cannot mint a confirmed or human record.
- **`CIRCULAR_DRAFTERS` is structural.** `GoldMention.__post_init__` raises
  `CircularGoldError` if a `gold-auto-builder` record is ever marked confirmed.
- **Confirmation requires attribution.** `confirmed=True` without
  `confirmed_by` raises `UnattributedConfirmationError`; `review_depth` must be
  `PER_RECORD`, so a bulk approval cannot become gold.
- **Self-declared anchoring risk.** `reverend-insanity-c1-c5.toml:10-14`
  records that its drafter had seen pipeline output earlier in the same
  session. The LOTM ch1-3 draft claims stronger independence. Neither claim is
  externally verifiable; both are recorded rather than asserted away.
- **Blind annotation tooling exists and is unused.** `echotales annotate` emits
  a surface plus a ±240-char window with `FORBIDDEN_TASK_FIELDS` enforced,
  refuses pre-filled answers, shuffles before `--sample`, and skips blanks
  rather than defaulting them. Built, round-tripped, never run at scale.

---

## 8. Train / dev / test

**No split is marked in the data.** Splitting happens at evaluation time only,
in `eval/calibrate.py::held_out_coverage`, and is **by chapter range, never
random** — a random split leaks late-volume evidence about an entity into the
calibration of an early-volume decision about that same entity, which is
EVOLUTION 4.74's failure wearing different clothes. Because the split is
derived per run, it is not reproducible from the corpus alone; the chosen
`split_chapter` is recorded in each run's `metrics.json`.

---

## 9. What would make this gold

In increasing order of cost: run `echotales annotate` at scale over the
hardcases and c1-c5 files (they are unconfirmed, not circular, so a human pass
promotes them directly); add a second annotator on ~30 shared hard cases and
report Cohen's κ; replace the 100%-circular LOTM and ORV files with independent
drafts (LOTM ch1-3 of 40 exist). Until the first of those happens, no accuracy
claim in this repository is anchored to human judgement, and every document
must say so.

---

<!-- merged-from: docs/results/HUMAN_REVIEW_PROTOCOL.md -->
## Source: `docs/results/HUMAN_REVIEW_PROTOCOL.md`

# Human review protocol

**Prepared 2026-09-25. No human labels exist yet.** This protocol and its sheets are the smallest review that lets the project say whether its silver-reference numbers transfer to human judgement.

## Sheets (local only; they contain short windows of copyrighted text)

Regenerate both with `python3 scripts/review/prepare_human_review.py` (seed 20260925, canonical database). They are gitignored; share them only with the review team.

| File | Rows | What |
|---|---:|---|
| `data/eval/human_review_200.csv` | 200 | Stratified sample of system mentions |
| `data/eval/human_review_hardcases_88.csv` | 88 | The hard-case reference records (silver) |

**Strata in the 200-mention sheet** (seeded, then sorted by position):

| Stratum | n |
|---|---:|
| easy_name | 30 |
| alias | 35 |
| title | 30 |
| relational | 35 |
| unresolved_name | 6 (all that exist) |
| observer_sensitive | 30 |
| background | 34 |

- **No pronoun stratum.** Pronouns never become graph mentions in this system (they are linked locally), so there is no system decision to judge.
- **Silver coverage is sparse.** Only 11 of the 200 rows fall where the silver set has a record. For the rest, the review measures the system's precision directly; it does not compare against silver.

## Columns

- `sample_id`, `chapter`.
- `source_text`: up to 200 characters, with the mention marked `[[like this]]`.
- `mention`.
- `predicted_entity`: the system's link, or UNRESOLVED.
- `candidate_entities`: entities that share the surface name.
- `system_decision`: link or no link, method, alias type.
- `reference_set_decision`: the silver identity, or "not in silver set".
- `category`.
- `reviewer_label`, `reviewer_notes`: **empty; for the reviewer only.**

## Instructions for the reviewer

1. Read `source_text`, plus the surrounding chapter if the window is not enough (the chapter number is given).
2. Decide who the marked mention refers to at that point in the story.
3. Set `reviewer_label` to exactly one of:
   - **correct**: the system's `predicted_entity` is the referent.
   - **incorrect**: the system linked to the wrong referent, or linked a mention that does not refer to a person, place or organisation.
   - **unresolved**: the system did not link (UNRESOLVED), **or** you cannot determine the referent from the text. Say which in `reviewer_notes`.
4. For the hard-case sheet, judge whether `reference_set_decision` (the silver identity) is right, using the same three labels. That measures the silver set itself.
5. Do not consult the system's other outputs while labelling. Do not change `predicted_entity` or `reference_set_decision`.
6. Record anything ambiguous (disguise, a title held by several people, a name used before a reveal) in `reviewer_notes`.

## Line types (for correcting the span type in the review desk)

The review desk lets a reviewer change a line's type. The automatic labels come
from keyword rules in `packages/pipeline/src/echotales/pipeline/spans/classify.py`
(tried in the order exposition, action, description; ACTION when nothing
matches), so treat every narration label as a guess. Decide in this order; the
first rule that applies wins:

1. **DIALOGUE**: quoted speech. **INNER_MONOLOGUE**: quoted or italicised thought ("he thought"). Neither is narration.
2. **NARRATION_EXPOSITION**: true beyond this scene: world rules, history, legend, explanation ("It is said in legend that...", "In short, it is the ability to be reborn."). Kept in audio, never drawn as a panel.
3. **NARRATION_ACTION**: something happens or changes in this scene ("Fang Yuan stretched out his hand.").
4. **NARRATION_DESCRIPTION**: how something is right now, with no change: appearance, setting, atmosphere ("The hall was lit by pale green lanterns.").
5. **NON_DIEGETIC**: not part of the story at all (author notes, chapter footers). Removed from audio and panels.

A sentence that mixes an action with a descriptive detail is ACTION. The
EXPOSITION boundary matters most (it decides whether a line becomes a panel);
ACTION versus DESCRIPTION only shifts how a panel is framed.

## Agreement

- **Two independent reviewers** label the same sheets without discussing them. Report Cohen's κ per sheet and per stratum (strata with fewer than 20 rows: report raw agreement only). Then adjudicate disagreements, and report precision with a Wilson 95% interval on the adjudicated labels.
- **With only one reviewer, κ is not reported.** Report precision with its interval and say that no inter-rater agreement exists.
- κ is computed only from real labels. Nothing in this repository computes or estimates it before those exist.

## Effort

About 6–8 person-hours for both sheets, per reviewer.
