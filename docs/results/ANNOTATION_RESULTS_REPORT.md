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
