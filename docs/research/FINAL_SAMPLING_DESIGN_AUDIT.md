# EchoTales — Final Sampling-Design Audit and Adjudication Go/No-Go

**Date:** 2026-10-13  
**Audit Status:** COMPLETE — DECISION RECORD ISSUED  
**Decision A (Manual Adjudication):** **GO** (Review package is valid, blinded, and ready).  
**Decision B (Corpus-Wide Statistical Inference):** **CONDITIONAL GO / RESTRICTED GO** (Population estimates require documented probability weighting and boundary caveats).  
**Resource Footprint:** Zero external API calls, zero credit spend, zero GPU inference. Source CSVs, existing labels, and StoryTrace firewall preserved unmodified.

---

## 1. Executive Summary & Audit Mission

This audit performs an independent, code-level and database-level verification of the sampling design, population link denominators, estimator validity, and reviewer blinding in EchoTales.

### Core Discoveries at a Glance

1. **The 99 General-Pool Observations Are NOT a Simple Random Sample:**  
   The previous audit described the evaluation design as a 5-stratum sample where 99 mentions were drawn from a general pool of $10,891$. **This claim is mathematically rejected.** In `prepare_human_review.py`, mentions in the general pool were sampled through two sequential stages with wildly disparate inclusion probabilities:
   - `alias` mentions: $\pi_i = 0.038802$ (weight $w = 25.77$)
   - `easy_name` mentions: $\pi_i = 0.006437$ (weight $w = 155.36$)
   - `scored_background` mentions: $\pi_i = 0.003089$ (weight $w = 323.76$)  
   An alias mention was **6.0x more likely** to be selected than an easy name, and **12.5x more likely** than a scored background mention. They cannot be treated as an unweighted simple random sample.

2. **The 981 Scored Background Mentions Were Never Sampled ($n = 0$):**  
   The 34 mentions labeled `"category": "background"` in `human_review_200.csv` did not come from the 981 mentions linked via scored heuristics. They were drawn uniformly from `remaining` (which consisted of $80.8\%$ unselected easy names and $8.6\%$ aliases). As a result, 31 were `easy_name` and 3 were `alias`. **Zero mentions** from the 981 scored heuristic pool were drawn. The sample contains zero empirical observations on that specific linking method.

3. **The 11,092 Population Link Denominator Is Exact and Version-Matched:**  
   Direct SQL inspection of `data/db/reverend-insanity.db` confirms that on 2026-09-25 (prior to commit `c8bfda9`, which introduced `resolve/title_holders.py` on September 27), exactly **11,092 mentions were linked** and **82 were abstained** across the 11,174 population mentions. The 200 evaluation rows in `human_review_200.csv` reflect this exact pre-`c8bfda9` pipeline output (all 30 titles have `predicted_entity == 'UNRESOLVED'`). The later count of 11,122 links reflects post-September-27 title linking and must not be used for this review sheet.

4. **Horvitz-Thompson Design-Consistent Precision Reconciled at 99.67%:**  
   Weighting each sampled row by its exact inverse inclusion probability ($w_i = 1/\pi_i$) yields a Horvitz-Thompson / Hajek estimated precision of **$\hat{R}_{\text{HT}} = 99.667\% \approx \mathbf{99.67\%}$**, closely reconciling with the Stratified Ratio Estimator ($\hat{R} = 99.68\%$) and the Known-Denominator Estimator ($\hat{P}_{\text{known}} = 99.59\%$).

---

## 2. Code-Level Reconstruction of the Sampling Algorithm

An exact inspection of `scripts/review/prepare_human_review.py` (lines 61–108) reveals the two-stage sampling mechanism executed under seed `20260925`:

```python
pools: dict[str, list[Any]] = {}
for r in rows:
    pools.setdefault(stratum(r), []).append(r)

chosen: list[tuple[str, Any]] = []
for name, n in TARGETS.items():
    pool = pools.get(name, [])
    chosen += [(name, r) for r in rng.sample(pool, min(n, len(pool)))]

taken = {c[1][0] for c in chosen}
remaining = [r for r in rows if r[0] not in taken]
chosen += [("background", r) for r in rng.sample(remaining, max(0, TOTAL - len(chosen)))]
```

### Detailed Answers to the Six Algorithmic Questions

1. **Selection of `easy_name` rows:**  
   In Stage 1, 30 rows were sampled uniformly from `pools['easy_name']` ($N=8,933$). In Stage 2, 31 additional rows matching the `easy_name` predicate were sampled from `remaining` and assigned `category = 'background'`. Total `easy_name` rows in sample: **61**.
2. **Selection of `alias` rows:**  
   In Stage 1, 35 rows were sampled uniformly from `pools['alias']` ($N=977$). In Stage 2, 3 additional rows matching the `alias` predicate were sampled from `remaining` and assigned `category = 'background'`. Total `alias` rows in sample: **38**.
3. **Selection of the 34 "background" rows:**  
   They were drawn via `rng.sample(remaining, 34)` where `remaining` consisted of all $11,008$ unselected mentions in the novel ($11,174 - 166$). They were **not** drawn from `pools['background']`.
4. **Selection of `observer_sensitive`, `title`, `relational`, and `unresolved_name`:**  
   In Stage 1, they were drawn uniformly from their respective pools:
   - `unresolved_name`: $6 / 6$ ($100\%$ census).
   - `title`: $30 / 39$ ($76.9\%$ sample).
   - `relational`: $35 / 125$ ($28.0\%$ sample).
   - `observer_sensitive`: $30 / 113$ ($26.5\%$ sample).
   The remaining unselected records in these strata entered `remaining` for Stage 2, but none happened to be selected under seed `20260925`.
5. **Multiple procedures, exclusion effects, and replacements:**  
   Because Stage 1 selected cases were excluded from Stage 2 via `taken`, every mention had at most one selection. No manual replacements occurred. However, this two-stage structure directly altered Stage 2 conditional inclusion probabilities.
6. **Mutual exclusivity and exhaustiveness of sampling frames:**  
   The predicate `stratum(r)` forms a strict if-elif hierarchy partitioning all 11,174 mentions into 7 mutually exclusive and exhaustive pools before selection begins.

### Mathematical Derivation of True Inclusion Probabilities ($\pi_i$)

Let $N = 11,174$ be the population. Let $H_k$ be stratum $k$ of size $N_k$, with Stage 1 target $n_k$.  
In Stage 1, the probability of selection for $i \in H_k$ is $P(\text{Stage 1}) = \frac{n_k}{N_k}$.  
If not selected (probability $1 - \frac{n_k}{N_k}$), unit $i$ enters `remaining`, which has size $M = N - \sum_{j} n_j = 11,174 - 166 = 11,008$.  
In Stage 2, $n_{\text{rem}} = 34$ units are sampled uniformly from `remaining`.  
The total inclusion probability is:
$$\pi_i = \frac{n_k}{N_k} + \left(1 - \frac{n_k}{N_k}\right) \frac{34}{11,008}$$

For `scored_background` ($N = 981$), which was not in TARGETS ($n_k = 0$):
$$\pi_i = \frac{34}{11,008} \approx 0.00308866$$

### Population Frames, Sample Draws, and Inclusion Probabilities Table

| Stratum Predicate $k$ | Population $N_k$ | Stage 1 Target $n_k$ | Stage 2 Draws | Total Sample $n_k^*$ | Inclusion Prob $\pi_k$ | Sampling Weight $w_k = 1/\pi_k$ |
|:---|---:|---:|---:|---:|---:|---:|
| `easy_name` | 8,933 | 30 | 31 | 61 | **0.006437** | 155.36 |
| `alias` | 977 | 35 | 3 | 38 | **0.038802** | 25.77 |
| `relational` | 125 | 35 | 0 | 35 | **0.282224** | 3.54 |
| `observer_sensitive` | 113 | 30 | 0 | 30 | **0.267755** | 3.73 |
| `title` | 39 | 30 | 0 | 30 | **0.769944** | 1.30 |
| `unresolved_name` | 6 | 6 | 0 | 6 | **1.000000** | 1.00 |
| `scored_background` | 981 | 0 | 0 | 0 | **0.003089** | 323.76 |
| **Total** | **11,174** | **166** | **34** | **200** | — | — |

**Conclusion on 5-Stratum General Pool:** The claim that 99 general-pool records form an SRS of $10,891$ is rejected. Alias mentions were sampled at a rate $6.0\times$ higher than easy names and $12.5\times$ higher than scored background mentions.

---

## 3. Full-Population System-Link Denominator Verification

### 3.1 SQL Provenance and Version Traceability

Direct query on `data/db/reverend-insanity.db` establishes:

```sql
-- Total mentions across Volume 1
SELECT COUNT(*) FROM mention WHERE novel_id = 'reverend-insanity';
-- Result: 11,174

-- Current linked mentions in SQLite (post-c8bfda9)
SELECT COUNT(*) FROM mention WHERE novel_id = 'reverend-insanity' AND target_id IS NOT NULL;
-- Result: 11,122

-- Mentions linked by resolve/title_holders.py (commit c8bfda9, Sep 27, 2026)
SELECT COUNT(*) FROM mention WHERE novel_id = 'reverend-insanity' AND target_id IS NOT NULL AND method = 'TITLE_HOLDER';
-- Result: 30

-- Mentions linked prior to TITLE_HOLDER (the Sep 25, 2026 state)
SELECT COUNT(*) FROM mention WHERE novel_id = 'reverend-insanity' AND target_id IS NOT NULL AND (method IS NULL OR method != 'TITLE_HOLDER');
-- Result: 11,092
```

### 3.2 Denominator Lineage Reconciliation

1. **The 11,092 Denominator:**  
   Applies to the exact frozen pipeline outputs evaluated in `human_review_200.csv` (where all 30 titles are `predicted_entity == 'UNRESOLVED'`). It is reproducible directly from the database without relying on sample estimates.
2. **The 11,122 Denominator:**  
   Represents a subsequent pipeline version after title-linking was committed on September 27 (`c8bfda9`). It does not apply to the 200 review sheet mentions.
3. **Verdict:** $X_{\text{pop}} = \mathbf{11,092}$ is the verified, exact population denominator for this evaluation package.

---

## 4. Reconstructed Estimands and Point Estimates

### 4.1 Formal Definitional Framework

- **Attempted Link Indicator ($x_i$):** $x_i = 1$ if the system proposed an entity (`predicted_entity != 'UNRESOLVED'`), $0$ if it abstained.
- **Link Correctness Indicator ($y_i$):** $y_i = 1$ if $x_i = 1$ and the linked entity matches narrative ground truth ($y_i \le x_i$).
- **System Abstention Indicator ($a_i$):** $a_i = 1 - x_i$.
- **Abstention Appropriateness ($v_i$):** $v_i = 1$ if $x_i = 0$ and the mention denotes an unresolvable or non-entity referent.
- **Human Epistemic Uncertainty:** Recorded in `adjudicator_confidence` (`low`) or `adjudicated_decision` (`uncertain_link` / `uncertain_abstention`).

### 4.2 Reconciled Precision Metrics

| Metric / Estimator | Formula | Value | Standard Error | 95% Confidence Interval | Methodological Status |
|:---|:---|---:|---:|:---|:---|
| **Horvitz-Thompson / Hajek ($\hat{R}_{\text{HT}}$)** | $\frac{\sum w_i y_i}{\sum w_i x_i} = \frac{10,610.91}{10,646.34}$ | **99.67%** | — | — | Design-consistent estimator using exact $\pi_i$ weights. |
| **Known-Denominator ($\hat{P}_{\text{known}}$)** | $\frac{\hat{Y}}{X_{\text{pop}}} = \frac{11,046.86}{11,092}$ | **99.59%** | 0.078% | $[99.44\%, 99.75\%]$ | Horvitz-Thompson total divided by exact corpus link count. |
| **Stratified Ratio Estimator ($\hat{R}$)** | $\frac{\hat{Y}}{\hat{X}} = \frac{11,046.86}{11,082.57}$ | **99.68%** | 0.074% | $[99.53\%, 99.82\%]$ | Standard survey ratio estimate treating link count as sample-estimated. |
| **Conservative Boundary Lower Bound** | $\frac{Y_{\text{conservative}}}{X_{\text{pop}}}$ | **90.45%** | — | — | Finite-population boundary bound for $n=30$ zero-error strata. |
| **Raw Sample Precision (over links)** | $\frac{141}{151}$ | **93.38%** | 2.02% | $[88.08\%, 96.74\%]$ | Unweighted sample precision over attempted links. |
| **Conflated Sample Precision** | $\frac{141}{158}$ | **89.24%** | 2.47% | $[83.35\%, 93.52\%]$ | Legacy unweighted figure conflating 7 abstentions with link errors. |

---

## 5. Audit of Confidence Intervals and Claimed Lower Bound

1. **Plug-In Variance Illusion:**  
   Taylor linearization produces $\text{SE} = 0.074\%$ because sample variances in `easy_name`, `background`, `alias`, and `observer_sensitive` are identically zero ($s_{uh}^2 = 0$). This treats $98.5\%$ of the novel as having zero sampling error simply because 30 sampled items had no errors.
2. **Zero-Draw Domain Problem:**  
   Because the 981 scored background mentions had zero sample draws ($n = 0$), there is zero direct empirical data on that domain.
3. **The 90.45% Lower Bound:**  
   Under the Rule of Three / Clopper-Pearson 95% upper limit for $n=30$ ($\epsilon_{\text{upper}} \approx 9.50\%$), the conservative lower bound across zero-error strata is **$90.45\%$**.
4. **Publishable Standard:**  
   Point estimates ($>99.5\%$) may be reported, but confidence intervals of $\pm 0.14\%$ cannot be defended without stating that they condition on zero errors in small stratum samples.

---

## 6. Audit of LLM Pre-Annotation Leakage

* Inspection of `scripts/review/llm_annotate.py` confirms that the candidate prompt supplied `category` on both sheets and `reference_set_decision` for 11 overlapping standard rows.
* **Strict Enforcement:** All candidate labels from `gpt-5.6-luna` are quarantined in `data/eval/adjudication/model_annotations_reconciliation.csv`. They are strictly excluded from the V2 blind sheets (`standard_200_v2_blind.csv`, `hardcases_88_v2_blind.csv`).

---

## 7. Two Distinct Decisions

### Decision A — Can Manual Adjudication Proceed?
### VERDICT: GO (PROCEED WITH MANUAL ADJUDICATION)
* **Justification:** The V2 blind sheets (`standard_200_v2_blind.csv` and `hardcases_88_v2_blind.csv`) are 100% blinded, shuffled, and preserve immutable `sample_id`s. Every row presents valid text excerpts and system decisions. Row-level human judgments will be completely meaningful and independently valid.

### Decision B — Can the Study Make Corpus-Wide Statistical Claims?
### VERDICT: CONDITIONAL GO / RESTRICTED GO
* **Justification:**  
  1. The study **CAN** report:
     - Sample-level descriptive metrics ($141/151 = 93.38\%$).
     - Exact stratum-level performance for the sampled categories (`easy_name`: $100\%$, $n=61$; `alias`: $100\%$, $n=38$; `observer_sensitive`: $100\%$, $n=30$; `relational`: $54.55\%$, $n=35$).
     - The Hajek / Horvitz-Thompson weighted precision point estimate ($99.67\%$) and known-denominator precision ($99.59\%$), under the documented assumption that unobserved scored mentions ($N=981$) perform similarly to exact-match mentions.
  2. The study **CANNOT** claim:
     - An unconditional design-based confidence interval of $\pm 0.14\%$ for the entire novel.
     - Direct empirical verification of the 981 scored heuristic mentions ($n = 0$).
  3. If unconditional design-based inference with sub-1% intervals is required for ARR/ACL, a future supplementary sample of $n=25$ from the 981 scored mentions should be annotated. For workshop/demo submissions, the restricted conditional report is fully defensible.
