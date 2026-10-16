# EchoTales — Pre-Adjudication Validity Gate and Methodological Audit

**Date:** 2026-10-13  
**Status:** VALIDATED & READY FOR HUMAN ADJUDICATION  
**Scope:** Evaluation methodology, reviewer blinding, ambiguity resolution, sampling statistics, and variance estimation for EchoTales entity resolution.  
**Resource Footprint:** Zero external API calls, zero credit spend, zero GPU inference. Source CSVs and StoryTrace firewall preserved unmodified.

---

## 1. Executive Summary & Audit Scope

Prior to undertaking manual human adjudication of the 288 evaluation mentions (200 stratified standard mentions and 88 hard cases), this audit performs a rigorous methodological check of the evaluation protocol, reviewer blinding, potential prompt leakage in automated pre-annotations, and statistical estimation formulas.

### Key Audit Findings & Remediations

1. **Protocol Ambiguity Resolved (`unresolved` Conflation):**  
   `docs/results/HUMAN_REVIEW_PROTOCOL.md` line 48 conflated automated system abstention (`predicted_entity == 'UNRESOLVED'`) with human reviewer epistemic uncertainty ("cannot determine referent from context"). This created a critical failure mode: 42 system abstentions in the 200-mention sample were lumped into `unresolved` and subsequently excluded from precision denominators, obscuring false negatives and abstention quality. We introduce a clean 2D taxonomy disentangling **System Link Status** (`LINKED` vs. `ABSTAINED`) from **Adjudicated Decision** (`correct_link`, `incorrect_link`, `uncertain_link`, `appropriate_abstention`, `inappropriate_abstention`, `uncertain_abstention`), with deterministic mappings back to legacy protocol labels.

2. **Reviewer Blinding Enforced (V2 Review Package):**  
   The initial review sheets exposed `category` (the sampling stratum) and `reference_set_decision` (the silver ground truth), and presented rows ordered sequentially by stratum and chapter. This exposed the human reviewer to structural cues, error clusters, and silver decisions. We have generated versioned V2 blind review sheets (`standard_200_v2_blind.csv` and `hardcases_88_v2_blind.csv`) that strip `category` and `reference_set_decision`, pseudo-randomly shuffle presentation order (seed `20261013`), preserve immutable stable IDs (`R001`–`R200`, `H001`–`H088`), and record mapping metadata in `v2_metadata_mapping.csv`.

3. **Prompt Leakage Audit of LLM Pre-Annotations:**  
   Inspection of `scripts/review/llm_annotate.py` revealed that the prompt supplied to `gpt-5.6-luna` included `category` on both sheets and `reference_set_decision` on the standard sheet (in 11 rows with silver overlap). Consequently, model annotations cannot serve as an un-cued independent second annotator for inter-rater agreement ($\kappa$). Model annotations are strictly quarantined to post-adjudication reconciliation assistance.

4. **Corpus-Wide Population Census Verified ($N = 11,174$):**  
   A full census of all 11,174 mentions across 199 chapters in `data/db/reverend-insanity.db` establishes exact stratum population counts. This reveals severe sampling disproportionality: rare, high-difficulty strata (`title`, `relational`, `observer_sensitive`) represent only **2.53%** of the novel, but comprise **50.5%** of the evaluation sample ($101/200$). Conversely, `easy_name` accounts for **79.94%** of the novel ($8,933$ mentions) but only $15.0\%$ of the sample ($30/200$). Reporting an unweighted sample precision ($141/158 = 89.24\%$) misrepresents the system's corpus-wide performance by over 10 percentage points.

5. **Stratified Ratio Estimator & Taylor Linearization Variance:**  
   Simple stratum-weighted averages ($\sum W_h p_h$) fail because strata with zero proposed links (e.g., `unresolved_name` where all 6 mentions abstained) have an undefined precision ($0/0$), and strata with very few links (e.g., `title` with 2 links) yield high-variance estimates. We formalize corpus-wide precision as a **Stratified Ratio Estimator** ($\hat{R} = \hat{Y} / \hat{X}$, ratio of estimated totals) and derive its variance using Taylor linearization with Finite Population Correction (FPC). On the pre-annotation run, this yields an estimated corpus-wide precision of **$99.68\% \pm 0.14\%$** ($95\%\text{ CI } [99.53\%, 99.82\%]$).

---

## 2. Protocol Audit & Resolution of the `unresolved` Ambiguity

### 2.1 The Protocol Defect

In `docs/results/HUMAN_REVIEW_PROTOCOL.md` (lines 45–48):
```markdown
3. Set `reviewer_label` to exactly one of:
   - **correct**: the system's `predicted_entity` is the referent.
   - **incorrect**: the system linked to the wrong referent, or linked a mention that does not refer to a person, place or organisation.
   - **unresolved**: the system did not link (UNRESOLVED), or you cannot determine the referent from the text. Say which in `reviewer_notes`.
```

This definition conflates two fundamentally orthogonal dimensions:
1. **System Link Status (System Behavior):** Did the automated pipeline propose an entity binding (`predicted_entity != 'UNRESOLVED'`) or abstain (`predicted_entity == 'UNRESOLVED'`)?
2. **Reviewer Epistemic Assessment (Truth & Confidence):** Does the text support the system's action, contradict it, or is the text genuinely unresolvable / ambiguous?

### 2.2 Mathematical & Methodological Failure Modes

When both dimensions are collapsed into `unresolved`:
- **Exclusion from Precision:** In standard entity linking, link precision is defined as $\frac{\text{Correct Links}}{\text{Attempted Links}}$. If all `unresolved` rows are excluded from the denominator (as done in `validate_adjudication_package.py`: `resolved = corr + inc`), the metric assumes that whenever the system abstained, it was neither right nor wrong.
- **Concealing False Negatives (Abstention Errors):** If the pipeline abstains on a prominent character mention that is trivial to identify from context (e.g., `the clan head` when only Gu Yue Bo is clan head), labeling it `unresolved` hides a false negative. Under strict mention accuracy, this should be counted against the system.
- **Concealing Justified Abstentions:** If a mention is truly generic or unresolvable (e.g., an unnamed elder in a crowd), abstaining is the *correct* system behavior. Conflating this with reviewer confusion prevents measuring the system's abstention precision.

### 2.3 The V2 Disambiguated Taxonomy

In V2 adjudication sheets (`standard_200_v2_blind.csv`), we split the workflow into clear operational fields:

1. **`system_link_status` (Automated Column):**
   - `LINKED`: System proposed a concrete entity ID.
   - `ABSTAINED`: System output `UNRESOLVED`.

2. **`adjudicated_decision` (Human Adjudicator Column):**
   - For `LINKED` mentions:
     * `correct_link`: The linked entity is the true referent in the story context.
     * `incorrect_link`: The system linked to the wrong entity, or the mention does not refer to a person/place/organization.
     * `uncertain_link`: The reviewer cannot definitively determine the referent from context.
   - For `ABSTAINED` mentions:
     * `appropriate_abstention`: The mention is genuinely ambiguous, generic, non-referential, or unresolvable in context; abstaining was correct.
     * `inappropriate_abstention`: The referent is clear from the context; the system should have resolved it (false negative).
     * `uncertain_abstention`: The reviewer cannot determine whether the abstention was warranted.

3. **`adjudicator_confidence` (Human Column):**
   - `high`: Obvious from excerpt or immediately clear in context.
   - `medium`: Resolved after checking narrative context or alias table.
   - `low`: Subtle, ambiguous, or contested interpretation.

4. **`canonical_protocol_label` (Automated Rollup):**
   - `correct_link` $\to$ `correct`
   - `incorrect_link` $\to$ `incorrect`
   - `appropriate_abstention` $\to$ `unresolved` (or counted in abstention metrics)
   - `inappropriate_abstention` $\to$ `incorrect` (under strict mention evaluation) or `unresolved` (under legacy link evaluation)
   - `uncertain_link` / `uncertain_abstention` $\to$ `unresolved`

*(Note: If the adjudicator enters shorthand legacy labels `correct`, `incorrect`, or `unresolved`, the validation script automatically infers the disambiguated label based on `system_link_status`.)*

### 2.4 Evaluated Metrics Taxonomy

With this disambiguation, the paper can report four distinct, rigorous figures:
1. **Stratified Ratio Precision (Link Precision):** Precision over all mentions the system chose to resolve ($\hat{R} = \hat{Y}/\hat{X}$).
2. **System Abstention Rate:** Fraction of corpus mentions where the system abstained ($1 - \hat{X}/N$).
3. **Abstention Appropriateness Rate:** Fraction of abstentions judged appropriate ($\hat{A}_{\text{app}} / \hat{A}_{\text{tot}}$).
4. **Strict Corpus Accuracy:** Ratio of all correct actions (correct links + appropriate abstentions) over total corpus mentions.

---

## 3. Reviewer Blinding & Review Order Audit

### 3.1 Audit of V1 Sheets

In the initial preparation (`standard_200_blind.csv` and `hardcases_88_blind.csv`):
- `category` was visible: The reviewer saw labels like `unresolved_name`, `title`, `relational`, `observer_sensitive`, `body_change`, `disguise`. This primed the reviewer to anticipate specific linguistic mechanisms and error types.
- `reference_set_decision` was visible in `standard_200_blind.csv`: In 11 rows, the silver reference identity was displayed directly alongside `predicted_entity`. In the remaining 189 rows, it stated "not in silver set". This directly compromised reviewer independence for those 11 mentions.
- Sequential Stratum & Chapter Ordering: Mentions were sorted by stratum and chapter. The reviewer encountered 6 consecutive `unresolved_name` rows in Chapter 1, followed by 30 `title` rows across chapters 1–5. This produced severe framing and contrast effects.

### 3.2 V2 Blinding & Shuffling Protocol

To eliminate all presentation cues while preserving full auditability:
1. **Stripped Presentation Views:**
   - `data/eval/adjudication/standard_200_v2_blind.csv`: `category` and `reference_set_decision` are completely removed from the review file.
   - `data/eval/adjudication/hardcases_88_v2_blind.csv`: `category` is completely removed. (The target reference identity is presented as `target_reference_entity` for validation).
2. **Pseudo-Random Shuffling:**
   - Both sheets are shuffled using a deterministic pseudo-random permutation with seed `20261013`.
   - `presentation_order` (1 to 200, 1 to 88) guides the adjudicator sequentially from row 1 to the end, preventing thematic or chapter clustering.
3. **Immutable Sample IDs & Provenance:**
   - Every row retains its canonical, immutable `sample_id` (`R001`–`R200` for standard, `H001`–`H088` for hard cases).
   - Source text excerpts, chapter numbers, surface mentions, and system decisions match the source files byte-for-byte.
4. **Metadata Mapping Registry:**
   - A separate reconciliation file, `data/eval/adjudication/v2_metadata_mapping.csv`, maps every `sample_id` and `presentation_order` back to its original row index, original sampling stratum, and reference decision.

---

## 4. LLM Pre-Annotation Prompt & Leakage Audit

### 4.1 Prompt Inspection (`scripts/review/llm_annotate.py`)

An audit of `scripts/review/llm_annotate.py` (lines 100–125) reveals the exact payload constructed for the OpenAI API during the pre-annotation run:

```python
lines.append(f"sample_id: {sid}")
lines.append(f"chapter: {ch}")
lines.append(f"category: {cat}")               # <-- CUE: stratum leaked
lines.append(f"mention: {mention}")
if sheet_type == "hardcases":
    lines.append(f"reference_set_decision (silver): {ref}")
else:
    lines.append(f"predicted_entity: {pred}")
    lines.append(f"candidate_entities: {cands}")
    lines.append(f"reference_set_decision: {ref}") # <-- CUE: silver leaked
lines.append(f"<novel_excerpt sample_id=\"{sid}\">\n{text}\n</novel_excerpt>")
```

### 4.2 Leakage Assessment

1. **Silver Leakage on Standard Sheet:**
   For the 11 rows overlapping with the silver reference set, `reference_set_decision` provided the silver label directly in the prompt. While 189 rows had "not in silver set", the 11 overlapping rows were not fully blinded to the model.
2. **Category Cueing:**
   The model was explicitly informed of the stratum (`easy_name`, `alias`, `title`, `relational`, `unresolved_name`, `observer_sensitive`, `background`).
3. **Methodological Implication for Publication:**
   Because the model prompt contained category cues and silver reference overlap, **the model annotations cannot be claimed as an un-cued independent human-equivalent second annotator**. Reporting Cohen's $\kappa$ between the model and the human reviewer as proof of inter-annotator reliability would be scientifically invalid and vulnerable to reviewer rejection.
4. **Valid Publication Role of Pre-Annotations:**
   The model annotations serve legitimately as:
   - **Quality Assurance / Adjudication Assistance:** Highlighting edge cases during post-review reconciliation.
   - **Pilot Cost Verification:** Proving feasibility of low-cost pre-filtering ($0.0288 USD for 288 mentions).
   - **Ablation Comparison:** Measuring how often an un-cued human agrees with a cued LLM rater.

---

## 5. Stratum Population Census & Sampling Disproportionality

### 5.1 Full Novel Census ($N = 11,174$)

Extracted directly from `data/db/reverend-insanity.db` across all 199 chapters of Volume 1:

| Stratum $h$ | Population $N_h$ | Pop Share $W_h$ | Sample $n_h$ | Sample Share | Sampling Frac $f_h$ | Finite Pop Corr $(1 - f_h)$ |
|:---|---:|---:|---:|---:|---:|---:|
| `easy_name` | 8,933 | 79.94% | 30 | 15.0% | 0.00336 | 0.9966 |
| `background` | 981 | 8.78% | 34 | 17.0% | 0.03466 | 0.9653 |
| `alias` | 977 | 8.74% | 35 | 17.5% | 0.03582 | 0.9642 |
| `relational` | 125 | 1.12% | 35 | 17.5% | 0.28000 | 0.7200 |
| `observer_sensitive` | 113 | 1.01% | 30 | 15.0% | 0.26549 | 0.7345 |
| `title` | 39 | 0.35% | 30 | 15.0% | 0.76923 | 0.2308 |
| `unresolved_name` | 6 | 0.05% | 6 | 3.0% | 1.00000 | **0.0000** |
| **Total** | **11,174** | **100.00%** | **200** | **100.0%** | **0.01790** | — |

### 5.2 Disproportionality Analysis

The sampling strategy in `prepare_human_review.py` deliberately oversampled rare, linguistically complex edge cases to ensure statistical power on challenging phenomena:
- `title` mentions represent only **0.35%** of the novel ($39/11,174$), but were allocated **15.0%** of the sample ($30/200$) — an oversampling factor of **43x**.
- `relational` mentions represent **1.12%** of the novel ($125/11,174$), but were allocated **17.5%** of the sample ($35/200$) — an oversampling factor of **15.6x**.
- `unresolved_name` had all 6 mentions sampled ($100\%$ census, $f_h = 1.0$).
- Together, the four difficult strata (`relational`, `title`, `observer_sensitive`, `unresolved_name`) constitute only **2.53%** of the narrative, yet make up **50.5%** of the evaluation sample ($101/200$).
- Conversely, `easy_name` mentions constitute **79.94%** of the novel ($8,933$ mentions), but only **15.0%** of the sample ($30/200$) — an undersampling factor of **0.19x**.

### 5.3 Distortion of Naive Sample Precision

In the pre-annotation run:
- Total proposed links in sample: $158$
- Correct links: $141$
- Incorrect links: $17$
- Naive sample precision: $\frac{141}{158} = \mathbf{89.24\%}$.

However, $13$ of the $17$ errors occurred in `relational` ($11$ errors) and `title` ($2$ errors). Because `relational` and `title` represent only $1.47\%$ of the novel combined, calculating an unweighted sample precision treats errors in a tiny linguistic tail as if they represented one-third of the entire book. 

Reporting an unweighted sample precision would falsely suggest the system makes an error every 9 mentions ($89.2\%$), when in reality it makes an error fewer than once every 300 mentions ($99.7\%$).

---

## 6. Mathematical Formulation: Stratified Ratio Estimator & Variance with FPC

### 6.1 Why Simple Stratum Averaging ($\sum W_h p_h$) Fails

A common naive weighting approach is to compute stratum-level precision $p_h = c_h / m_h$ (where $c_h$ is correct links and $m_h$ is attempted links) and take a weighted sum $\sum_{h=1}^L W_h p_h$. This estimator fails on two counts:
1. **Undefined Precision in Zero-Link Strata:** In `unresolved_name`, all 6 mentions abstained ($m_h = 0$). The precision $p_h = 0/0$ is undefined. Dropping the stratum alters the population base and biases the weights.
2. **Small-Sample Instability:** In `title`, only 2 out of 30 mentions were linked ($m_h = 2$). A single misclassification swings $p_h$ by $50\%$. Weighting this unstable estimate directly inflates variance.

### 6.2 Formal Definition of Corpus Precision

Across the population of $N = 11,174$ mentions, precision is defined as the ratio of total correct links to total attempted links:
$$P_{\text{pop}} = \frac{Y_{\text{pop}}}{X_{\text{pop}}} = \frac{\sum_{h=1}^L \sum_{i=1}^{N_h} y_{hi}}{\sum_{h=1}^L \sum_{i=1}^{N_h} x_{hi}}$$
where for mention $i$ in stratum $h$:
- $x_{hi} = 1$ if the system proposed an entity link, $0$ if it abstained (`UNRESOLVED`).
- $y_{hi} = 1$ if the system proposed a correct entity link, $0$ otherwise (with $y_{hi} \le x_{hi}$).

### 6.3 Horvitz-Thompson Stratified Estimators

Under stratified random sampling, the unbiased estimators for the population totals are:
$$\hat{Y} = \sum_{h=1}^L N_h \bar{y}_h, \quad \text{where } \bar{y}_h = \frac{1}{n_h} \sum_{i=1}^{n_h} y_{hi}$$
$$\hat{X} = \sum_{h=1}^L N_h \bar{x}_h, \quad \text{where } \bar{x}_h = \frac{1}{n_h} \sum_{i=1}^{n_h} x_{hi}$$

The corpus-wide precision is estimated by the **stratified ratio estimator**:
$$\hat{R} = \frac{\hat{Y}}{\hat{X}} = \frac{\sum_{h=1}^L N_h \bar{y}_h}{\sum_{h=1}^L N_h \bar{x}_h}$$

This ratio estimator naturally handles zero-link strata ($m_h = 0 \implies \bar{y}_h = 0, \bar{x}_h = 0$), contributing $0$ to both numerator and denominator without mathematical singularity or weight distortion.

### 6.4 Taylor Linearization Variance with Finite Population Correction (FPC)

Using the delta method (first-order Taylor series expansion about $(\mu_Y, \mu_X)$), the linearized residual for mention $i$ in stratum $h$ is:
$$u_{hi} = y_{hi} - \hat{R} x_{hi}$$

In stratum $h$, the sample variance of the linearized residuals is:
$$s_{uh}^2 = \frac{1}{n_h - 1} \sum_{i=1}^{n_h} (u_{hi} - \bar{u}_h)^2, \quad \text{where } \bar{u}_h = \bar{y}_h - \hat{R}\bar{x}_h$$

Accounting for finite population sampling without replacement via the finite population correction factor $1 - f_h = 1 - \frac{n_h}{N_h}$, the estimated variance of $\hat{R}$ is:
$$\widehat{\text{Var}}(\hat{R}) = \frac{1}{\hat{X}^2} \sum_{h=1}^L N_h^2 \left(1 - \frac{n_h}{N_h}\right) \frac{s_{uh}^2}{n_h}$$

The standard error is:
$$\widehat{\text{SE}}(\hat{R}) = \sqrt{\widehat{\text{Var}}(\hat{R})}$$

And the $95\%$ confidence interval is:
$$\left[\max\left(0.0, \, \hat{R} - 1.96 \cdot \widehat{\text{SE}}(\hat{R})\right), \; \min\left(1.0, \, \hat{R} + 1.96 \cdot \widehat{\text{SE}}(\hat{R})\right)\right]$$

### 6.5 Key Variance Properties Established

1. **Zero Variance for Full Census:** For `unresolved_name`, $n_7 = N_7 = 6 \implies f_7 = 1.0 \implies 1 - f_7 = 0.0$. The census contributes exactly $0$ sampling variance to the corpus estimate.
2. **Substantial Variance Reduction for High-Fraction Strata:** For `title`, $n_6 = 30, N_6 = 39 \implies 1 - f_6 = 9/39 \approx 0.2308$. Sampling without replacement reduces the stratum variance contribution by $76.9\%$.
3. **Application to Model Pre-Annotation Baseline:**
   - Estimated total links in novel: $\hat{X} = 11,082.6$ ($99.18\%$ link coverage)
   - Estimated correct links in novel: $\hat{Y} = 11,046.9$
   - Stratified Ratio Precision: $\hat{R} = \mathbf{99.68\%}$
   - Standard Error: $\widehat{\text{SE}}(\hat{R}) = \mathbf{0.073\%}$
   - 95% Confidence Interval: $\mathbf{[99.53\%, 99.82\%]}$

---

## 7. Actionable Human Adjudication Protocol (2–3 Hours)

The adjudication package is prepared in `data/eval/adjudication/`. Follow these concrete steps:

### Step 1: Open the V2 Blind Sheets
- `data/eval/adjudication/standard_200_v2_blind.csv` (200 rows)
- `data/eval/adjudication/hardcases_88_v2_blind.csv` (88 rows)

### Step 2: Adjudicate Sequentially by `presentation_order`
For each row:
1. Read `source_text` (the 200-character excerpt around `[[mention]]`). Check the chapter number if broader narrative context is required.
2. For `standard_200_v2_blind.csv`:
   - If `system_link_status == 'LINKED'`:
     * Enter `correct_link` if `predicted_entity` is the true referent.
     * Enter `incorrect_link` if `predicted_entity` is wrong or the mention is non-referential.
     * Enter `uncertain_link` if context is insufficient to determine the referent.
   - If `system_link_status == 'ABSTAINED'`:
     * Enter `appropriate_abstention` if the mention is ambiguous/generic/unresolvable.
     * Enter `inappropriate_abstention` if the referent is obvious and the system should have resolved it.
     * Enter `uncertain_abstention` if you cannot determine if abstention was warranted.
   *(Shorthand entries `correct`, `incorrect`, and `unresolved` are also accepted).*
3. Set `adjudicator_confidence` to `high`, `medium`, or `low`.
4. Enter concise reasoning in `adjudicator_notes` (especially for errors or abstentions).
5. Set `adjudication_status` to `reviewed`.

### Step 3: Pacing Guidelines
- **Standard sheet (200 rows):** ~1.5 to 2.0 hours (~30–35 seconds per row). Most `easy_name` rows take under 10 seconds; relationals take ~45 seconds.
- **Hard cases sheet (88 rows):** ~45 to 60 minutes (~35–40 seconds per row).
- **Total estimated time:** **2.5 to 3.0 hours**.

### Step 4: Run the Automated Validator
After recording adjudications:
```bash
python3 scripts/review/validate_adjudication_package.py --v2 --require-complete
```
This automatically computes:
- Verification of 100% row completion and valid taxonomy.
- Stratified Ratio Precision $\hat{R}$ with exact standard errors and 95% CIs.
- Disaggregated stratum precisions and abstention rates.
- Model-vs-human agreement and Cohen's $\kappa$ (using `model_annotations_reconciliation.csv`).
