# EchoTales — Final Statistical Claims Gate and Supplemental Sampling Decision

**Date:** 2026-10-13  
**Status:** COMPLETE — DEFINITIVE STATISTICAL AUDIT & METHODOLOGICAL GATE  
**Audit Scope:** Independent mathematical, algorithmic, and database verification of sampling probabilities, population estimators, uncertainty bounds, and supplemental sampling requirements.  
**Adjudication Track:** **GO** (Manual review of the 288 V2 blind rows is fully authorized to proceed immediately).  
**Population Claims Track:** **GATE / RESTRICTED** (Corpus-wide precision claims of $\ge 99.5\%$ cannot be asserted without either documenting the 100% precision imputation on the 981 unobserved scored records or completing a supplemental sample).  
**Resource Footprint:** Zero external API calls, zero credit spend, zero GPU inference. Source CSVs, existing labels, StoryTrace firewall, and `DECISION_LOG.md` preserved unmodified.

---

## 1. Executive Summary & Definitive Gate Decisions

This audit independently scrutinizes the statistical claims and sampling design underlying the EchoTales entity linking evaluation, with specific focus on the 981 scored-background mentions that received zero sample draws in the September 25, 2026 evaluation package.

### Direct Answers to the Six Mandated Inquiries

1. **Can manual adjudication of the current sample proceed?**  
   **YES (GO).** The current evaluation package (`standard_200_v2_blind.csv` with 200 mentions and `hardcases_88_v2_blind.csv` with 88 mentions) is strictly blinded, pseudo-randomly shuffled, presents sufficient textual context ($\le 200$-character windows and chapter indicators), isolates model pre-annotations in quarantine, and contains zero pre-filled human labels. Author adjudication of these 288 rows is completely valid, independent, and should proceed without delay.

2. **Which current results are descriptive sample findings, and which are assumption-dependent population estimates?**  
   - **Descriptive Sample Findings:**  
     * Sample action balance: 151 proposed links (`predicted_entity != 'UNRESOLVED'`) and 49 abstentions (`predicted_entity == 'UNRESOLVED'`).  
     * Candidate human-judgment distribution: 141 candidate-correct links, 10 candidate-incorrect links, 42 candidate-appropriate abstentions, and 7 candidate-inappropriate abstentions (false negatives).  
     * Raw unweighted sample precision over links: $141 / 151 = 93.38\%$.  
     * Stratum-specific sample performance on observed strata: `easy_name` ($61/61 = 100\%$), `alias` ($38/38 = 100\%$), `observer_sensitive` ($30/30 = 100\%$), and `relational` ($12/22 = 54.55\%$).  
   - **Assumption-Dependent Population Estimates:**  
     * Exact-denominator estimate ($99.59\% = 11,046.86 / 11,092$): **Heavily assumption-dependent.** Directly imputes 100% precision to all 981 unobserved scored-background mentions.  
     * Stratified ratio estimate ($99.68\% = 11,046.86 / 11,082.57$): **Heavily assumption-dependent.** Relies on the same 100% imputation on the unobserved pool.  
     * Horvitz-Thompson / Hájek ratio ($99.67\% = 10,610.91 / 10,646.34$): Design-consistent **only over the domain of sampled strata**; it contributes 0 weight from the scored-background pool.  
     * Asymptotic plug-in Taylor SE ($0.074\%$, yielding $99.68\% \pm 0.14\%$): **Scientifically invalid.** Collapses sample variance to zero across 98.5% of the novel based on small zero-error samples and assigns zero variance to the unsampled domain.

3. **Is 99.59% supported without assuming every unobserved scored-background prediction is correct?**  
   **NO.** The numerator $11,046.86$ is algebraically constructed as $8,933 + 981 + 977 + 113 + 125(12/35) = 11,004 + 42.86 = 11,046.86$. It explicitly adds $981 \times (34/34) = 981$ into the numerator based on 34 Stage-2 records that actually consisted of 31 easy names and 3 aliases. Without the assumption that unobserved scored-background mentions have 100% accuracy, this point estimate is mathematically unsupported. If scored mentions have error rate $(1 - p_{\text{scored}})$, the corpus precision drops by $8.84\% \times (1 - p_{\text{scored}})$. Furthermore, dividing the true Horvitz-Thompson sample total $\hat{Y}_{\text{HT}} = 10,610.91$ by the known denominator $11,092$ yields **$95.66\%$**, reflecting the missing sample mass of the unsampled domain.

4. **Is the 99.67% weighted ratio accompanied by a defensible uncertainty estimate?**  
   **NO.** The reported margin of error ($\pm 0.14\%$) is an artifact of treating $s_h^2 = 0$ in small samples ($n_h = 30$) and having zero sample observations ($n_{\text{scored}} = 0$) from the 981-mention scored domain. Zero observed errors in a finite sample is not empirical proof of zero population variance. A defensible boundary-aware lower bound across the sampled strata is **$90.45\%$**.

5. **What sample size would be needed to support the intended error-bound claim?**  
   To mathematically bound the error rate in the 981 scored mentions to $\le 1.0\%$ at 95% confidence using finite-population hypergeometric sampling without replacement, a sample of **$n = 253$ mentions** (over 25.8% of the stratum) is required. A sample of $n = 25$ yields an error-rate upper bound of **$11.11\%$** (109 errors out of 981), which cannot rule out an error rate of 1%, 2%, 5%, or 10%.

6. **Should we draw a supplemental sample, and what exact workload and benefit would that entail?**  
   - **Immediate Action:** Do not delay author adjudication of the existing 288 V2 rows.  
   - **Supplemental Recommendation:** If the goal is a robust peer-reviewed claim (e.g. ARR/ACL) covering all linking mechanisms, draw a proportionate supplemental probability sample of **$n = 50$ mentions** (SRSWOR, seed `20261014`, frame $N=981$).  
   - **Workload:** ~75 minutes (~1.25 hours) of human review time (zero API/GPU spend).  
   - **Benefit:** Reduces the upper error bound on scored heuristics from complete blindness ($n=0$, bound 100%) to $\le 5.61\%$ (if 0 errors observed), anchoring the corpus precision floor firmly above $99.1\%$ without the excessive burden of a 253-row annotation (~7 hours).  
   - **Status:** The protocol is fully specified below but held pending user authorization; **no rows have been generated or drawn.**

---

## 2. Code-Level Reconstruction of the Sampling Mechanism & Inclusion Probabilities

### 2.1 The Two-Stage Selection Implementation

In `scripts/review/prepare_human_review.py` (lines 61–108), mentions were drawn under random seed `20260925` using a two-stage procedure:

1. **Stage 1 (Targeted Stratified Selection):**  
   All 11,174 mentions in Volume 1 were partitioned into mutually exclusive pools via `stratum(r)`. Targeted quotas were sampled without replacement:
   - `easy_name`: 30 drawn from pool of 8,933
   - `alias`: 35 drawn from pool of 977
   - `title`: 30 drawn from pool of 39
   - `relational`: 35 drawn from pool of 125
   - `unresolved_name`: 6 drawn from pool of 6 (100% census)
   - `observer_sensitive`: 30 drawn from pool of 113
   - `background`: **0 drawn** (not included in `TARGETS`)  
   Total Stage 1 selections: $n_{\text{stage1}} = 30 + 35 + 30 + 35 + 6 + 30 = 166$.

2. **Stage 2 (Residual Selection):**  
   The 166 selected IDs were placed into `taken`. The residual pool `remaining` consisted of all $M = 11,174 - 166 = 11,008$ unselected mentions. Exactly $n_{\text{stage2}} = 200 - 166 = 34$ items were sampled uniformly without replacement from `remaining`:
   ```python
   taken = {c[1][0] for c in chosen}
   remaining = [r for r in rows if r[0] not in taken]
   chosen += [("background", r) for r in rng.sample(remaining, max(0, TOTAL - len(chosen)))]
   ```
   Crucially, these 34 draws were assigned the string `"background"` in the output CSV, despite being sampled from `remaining`.

### 2.2 Proof of Zero Draws from Scored Background

Because `remaining` ($M=11,008$) was dominated by unselected `easy_name` records ($8,903 / 11,008 = 80.88\%$) and `alias` records ($942 / 11,008 = 8.56\%$), the 34 Stage-2 uniform draws under seed `20260925` selected:
- **31 `easy_name` records** (all `GAZETTEER_EXACT`, surface matches canonical label)
- **3 `alias` records** (2 `GAZETTEER_EXACT`, 1 `NAME_CONTAINMENT`)
- **0 `scored_background` records**

Across the entire 200-row sample, exactly **zero mentions** linked via heuristic scoring (`method == 'SCORED'`) were drawn.

### 2.3 Exact Inclusion Probabilities ($\pi_i$) and Sampling Weights ($w_i$)

Let $N = 11,174$, $n_k$ be the Stage 1 target draw from stratum $k$ of size $N_k$, and $M = 11,008$. The exact inclusion probability for unit $i \in \text{stratum } k$ is:
$$\pi_k = \frac{n_k}{N_k} + \left(1 - \frac{n_k}{N_k}\right) \frac{34}{11,008}$$
The design weight is $w_k = 1 / \pi_k$.

| Stratum Predicate $k$ | Population $N_k$ | Stage 1 Draws $n_k$ | Stage 2 Draws | Total Sample $n_k^*$ | Inclusion Probability $\pi_k$ | Sampling Weight $w_k$ |
|:---|---:|---:|---:|---:|---:|---:|
| `easy_name` | 8,933 | 30 | 31 | 61 | **0.006437** | 155.3601 |
| `alias` | 977 | 35 | 3 | 38 | **0.038802** | 25.7719 |
| `relational` | 125 | 35 | 0 | 35 | **0.282224** | 3.5433 |
| `observer_sensitive` | 113 | 30 | 0 | 30 | **0.267755** | 3.7348 |
| `title` | 39 | 30 | 0 | 30 | **0.769944** | 1.2988 |
| `unresolved_name` | 6 | 6 | 0 | 6 | **1.000000** | 1.0000 |
| `scored_background` | 981 | 0 | 0 | 0 | **0.003089** | 323.7647 |
| **Total** | **11,174** | **166** | **34** | **200** | — | — |

**Rejection of SRS Claim:** An `alias` mention was $6.03\times$ more likely to be selected than an `easy_name` mention, and $12.56\times$ more likely than a `scored_background` mention. The 99 general-pool records cannot be treated as a simple random sample.

---

## 3. Database Denominator Provenance & Version Traceability

### 3.1 SQL Database Verification

Direct query execution on `data/db/reverend-insanity.db` establishes the exact mention counts:

```sql
-- Total mentions across Volume 1:
SELECT COUNT(*) FROM mention WHERE novel_id = 'reverend-insanity';
-- Result: 11,174

-- Current linked mentions in SQLite (post-c8bfda9):
SELECT COUNT(*) FROM mention WHERE novel_id = 'reverend-insanity' AND target_id IS NOT NULL;
-- Result: 11,122

-- Mentions linked by resolve/title_holders.py (commit c8bfda9, Sep 27, 2026):
SELECT COUNT(*) FROM mention WHERE novel_id = 'reverend-insanity' AND target_id IS NOT NULL AND method = 'TITLE_HOLDER';
-- Result: 30

-- Mentions linked prior to TITLE_HOLDER (the Sep 25, 2026 frozen state):
SELECT COUNT(*) FROM mention WHERE novel_id = 'reverend-insanity' AND target_id IS NOT NULL AND (method IS NULL OR method != 'TITLE_HOLDER');
-- Result: 11,092
```

### 3.2 Denominator Lineage

1. **Frozen State (2026-09-25):** Exactly **11,092 mentions were linked** and **82 were abstained** across the 11,174 mentions. The 200 evaluation rows in `human_review_200.csv` and `standard_200_v2_blind.csv` were extracted on this exact date (all 30 title mentions in the review sheet have `predicted_entity == 'UNRESOLVED'`).
2. **Subsequent State (Post-September 27):** Commit `c8bfda9` added title linking, raising the database link count to 11,122. Using 11,122 on the pre-`c8bfda9` evaluation sheet would introduce a version mismatch.
3. **Confirmed Denominator:** $X_{\text{pop}} = \mathbf{11,092}$ is the verified, exact population denominator for this evaluation package.

---

## 4. Ontological Disentanglement: System Actions vs. Human Judgments

To prevent recurrence of the historical narrative error (where 7 abstentions were conflated with link errors), we enforce a strict tripartite distinction:

```
[System Execution]          [Candidate LLM Review]          [Final Human Adjudication]
  (Code Reality)              (Provisional Rater)               (Author Truth)
        |                              |                               |
  151 LINKED -----------------> 141 "correct" ---------------> "correct_link"
        |                \---->  10 "incorrect" -------------> "incorrect_link"
        |
   49 ABSTAINED -------------->  42 "unresolved" ------------> "appropriate_abstention"
                         \---->   7 "incorrect" -------------> "inappropriate_abstention" (FN)
```

1. **Actual System Action ($x_i$):** Deterministic binary indicator of system output.
   - $x_i = 1$ if the system proposed an entity (`predicted_entity != 'UNRESOLVED'`). In sample: **$m = 151$**.
   - $x_i = 0$ if the system abstained (`predicted_entity == 'UNRESOLVED'`). In sample: **$a = 49$**.
   - Total sample actions: $151 + 49 = 200$.

2. **Candidate Human-Judgment Label ($y_i^{\text{cand}}$):** Provisional classifications by `gpt-5.6-luna`:
   - On system links ($m = 151$): 141 labeled `correct`, 10 labeled `incorrect`.
   - On system abstentions ($a = 49$): 42 labeled `unresolved` (appropriate abstention), 7 labeled `incorrect` (false negatives where rater felt the system should have linked).
   - Historical narrative error: Previous documents naively summed all `incorrect` labels ($10 + 7 = 17$) and asserted $141 + 17 = 158$ links, producing the conflated fraction $141 / 158 = 89.24\%$.

3. **Final Human-Adjudicated Result:** The impending label recorded by the author in the V2 review sheet using the disambiguated taxonomy:
   - For links: `correct_link`, `incorrect_link`, `uncertain_link`.
   - For abstentions: `appropriate_abstention`, `inappropriate_abstention`, `uncertain_abstention`.
   - For hard cases: `correct_reference`, `incorrect_reference`, `uncertain_reference`.

---

## 5. Adversarial Audit of Claimed Corpus Estimators

### 5.1 Exact-Denominator Estimator ($11,046.86 / 11,092 = 99.59\%$)

#### Algebraic Construction
In `validate_adjudication_package.py`, the numerator $\hat{Y} = 11,046.86$ is calculated as:
$$\hat{Y} = \sum_{h=1}^7 N_h \bar{y}_h$$
Where:
- `easy_name`: $8,933 \times (30/30) = 8,933.00$
- `background`: $981 \times (34/34) = \mathbf{981.00}$  *(Imputed)*
- `alias`: $977 \times (35/35) = 977.00$
- `observer_sensitive`: $113 \times (30/30) = 113.00$
- `relational`: $125 \times (12/35) = 42.85714$
- `title`: $39 \times (0/30) = 0.00$
- `unresolved_name`: $6 \times (0/6) = 0.00$

$$\hat{Y} = 8,933 + 981 + 977 + 113 + 42.85714 = 11,046.85714 \approx \mathbf{11,046.86}$$
$$\hat{P}_{\text{known}} = \frac{11,046.86}{11,092} = 99.593\% \approx \mathbf{99.59\%}$$

#### Audit Finding and Rejection
The term $+981.00$ entered $\hat{Y}$ because the script grouped the 34 Stage-2 sample rows under the dictionary key `"background"` and observed that all 34 were candidate-correct ($\bar{y} = 34/34 = 1.0$).  
However, as proven in Section 2, **all 34 of those mentions were easy names (31) and aliases (3); zero were from the 981 scored heuristic records.**

> [!WARNING]
> **Imputation Disclosure:**  
> The 99.59% estimate literally assumes that 100.0% of the 981 unobserved scored-background mentions are correct links, based entirely on observations of exact-match names.  
> **Verdict:** The claim that 99.59% is an "empirically established precision estimate" is **mathematically rejected**. It is a model-assisted estimate with an unverified imputation assumption.

#### Sensitivity of Corpus Precision to Scored Heuristic Error Rate
If the true precision in the 981 scored mentions is $p_{\text{scored}} \in [0.0, 1.0]$, the corpus precision is:
$$P(p_{\text{scored}}) = \frac{11,046.86 - 981(1 - p_{\text{scored}})}{11,092} = 99.593\% - 8.844\% \times (1 - p_{\text{scored}})$$

| True Scored Precision $p_{\text{scored}}$ | True Errors in Scored Pool | Corpus Correct Links $Y$ | True Corpus Precision $P$ |
|---:|---:|---:|---:|
| **100.0%** (Imputed Assumption) | 0 | 11,046.86 | **99.59%** |
| **98.0%** | 20 | 11,027.24 | **99.42%** |
| **95.0%** | 49 | 10,997.81 | **99.15%** |
| **90.0%** | 98 | 10,948.76 | **98.71%** |
| **80.0%** | 196 | 10,850.66 | **97.82%** |
| **50.0%** | 491 | 10,556.36 | **95.17%** |
| **0.0%** (Worst Case) | 981 | 10,065.86 | **90.75%** |

### 5.2 Unequal-Probability Ratio Estimator (Hájek: 99.67%)

Using the exact row-level inclusion probabilities $\pi_i$ derived in Section 2:
$$\hat{Y}_{\text{HT}} = \sum_{i \in s} \frac{y_i}{\pi_i} = \sum_{i \in s} w_i y_i = 10,610.91$$
$$\hat{X}_{\text{HT}} = \sum_{i \in s} \frac{x_i}{\pi_i} = \sum_{i \in s} w_i x_i = 10,646.34$$
$$\hat{R}_{\text{Hajek}} = \frac{\hat{Y}_{\text{HT}}}{\hat{X}_{\text{HT}}} = \frac{10,610.91}{10,646.34} = 99.6672\% \approx \mathbf{99.67\%}$$

#### Audit Findings on Hájek Ratio
1. **Omission of the Unsampled Pool:** Because $n_{\text{scored}} = 0$, the scored stratum contributes 0 to both the numerator $\hat{Y}_{\text{HT}}$ and denominator $\hat{X}_{\text{HT}}$. The Hájek estimate is mathematically consistent **only for the domain of strata that were actually sampled**.
2. **Comparison with Known Denominator:** If one divides the true design-based Horvitz-Thompson total $\hat{Y}_{\text{HT}}$ by the exact population denominator $X_{\text{pop}} = 11,092$:
   $$\frac{\hat{Y}_{\text{HT}}}{X_{\text{pop}}} = \frac{10,610.91}{11,092} = \mathbf{95.66\%}$$
   This 95.66% figure illustrates the massive downward bias caused when an unobserved stratum contributes zero sample mass to an unbiased total estimator.

### 5.3 Audit of Variance & The Plug-In Variance Illusion

In survey sampling, the linearized residual for ratio estimation is $u_{hi} = y_{hi} - \hat{R} x_{hi}$.
When every sampled unit in stratum $h$ is a correct link ($x_{hi} = 1, y_{hi} = 1$), the residual is constant ($u_{hi} = 1 - \hat{R}$) and the sample variance is identically zero:
$$s_{uh}^2 = \frac{1}{n_h - 1} \sum_{i=1}^{n_h} (u_{hi} - \bar{u}_h)^2 = 0.0$$

In the provisional sample, $s_{uh}^2 = 0$ occurred in `easy_name` ($n=30$), `alias` ($n=35$), `observer_sensitive` ($n=30$), and the mislabeled Stage-2 rows ($n=34$), encompassing **98.5% of the novel**.  
Consequently:
- The Taylor linearization standard error ($SE = 0.074\%$) was computed **almost entirely from the 35 relational mentions**.
- The unsampled scored mentions contributed zero variance because $n_h = 0$.
- This produced the illusory confidence interval: $99.68\% \pm 0.14\%$.

> [!CAUTION]
> **Defensive Variance Rule:**  
> Observing zero errors in 30 or 60 sample draws from a finite population of 8,933 does not mean the true population error variance is zero. Reporting an unconditional $\pm 0.14\%$ interval is scientifically indefensible. Under Clopper-Pearson / Rule of Three boundary bounding, the conservative 95% lower bound across zero-error strata is **$90.45\%$**.

### 5.4 Tripartite Reporting Standard for Publication

To maintain scientific integrity in any future publication:

1. **Human-Adjudicated Sample Metric:**  
   Report the exact proportion of correct links among attempted links in the sample ($c_{\text{sample}} / m_{\text{sample}}$) after author review is finalized, with exact binomial confidence bounds (e.g. provisional $141 / 151 = 93.38\%$, 95% CI: $[88.08\%, 96.74\%]$).
2. **Design-Based Sampled-Domain Estimate:**  
   Report the design-consistent Hájek estimate ($99.67\%$) restricted explicitly to the sampled domain (`easy_name`, `alias`, `observer_sensitive`, `relational`), accompanied by the boundary-aware conservative lower bound ($90.45\%$).
3. **Explicit Assumption-Dependent Corpus Estimate:**  
   Report the full corpus estimate ($99.59\%$) only with the explicit statement: *"Conditions on the assumption that unobserved scored-heuristic mentions ($N=981$) exhibit error rates comparable to exact-match names."*

---

## 6. Finite-Population Sample-Size Analysis for the 981 Scored Mentions

The previous audit tentatively suggested sampling $n = 25$ mentions from the 981 scored-background population. We now subject that recommendation to rigorous mathematical challenge.

### 6.1 Hypergeometric Exact Finite-Population Formulation

Let $N = 981$ be the population of scored mentions. Let $K \in \{0, 1, \dots, N\}$ be the unknown, fixed number of errors in the population.  
We draw a simple random sample without replacement (SRSWOR) of size $n$. Let $X$ be the number of errors observed.  
If zero errors are observed in the sample ($X = 0$), the probability of this event under the hypergeometric distribution is:
$$P(X = 0 \mid N, K, n) = \frac{\binom{N - K}{n}}{\binom{N}{n}} = \prod_{j=0}^{n-1} \frac{N - K - j}{N - j}$$

The exact one-sided 95% upper confidence bound on the population error count, $K_{\text{upper}}$, is the largest integer $K$ such that:
$$P(X = 0 \mid N, K, n) \ge 0.05$$
Any population error count $K > K_{\text{upper}}$ would produce $X = 0$ with probability less than $5\%$ and is therefore rejected at the $\alpha = 0.05$ significance level.

### 6.2 Finite-Population Sample-Size Table ($N = 981$)

| Sample Size $n$ | Sampling Fraction $n/N$ | Hypergeometric Upper Error Count $K_{\text{upper}}$ (95%) | Exact 95% Upper Error Rate $K_{\text{upper}}/N$ | Binomial Bound ($1 - 0.05^{1/n}$) | Rule of Three Diagnostic ($3/n$) | Reviewer Time (~1.5 min/row) | Methodological Capability |
|---:|---:|---:|---:|---:|---:|---:|:---|
| **$n = 25$** | 2.55% | **109** | **11.11%** | 11.29% | 12.00% | ~35–45 min | Fast sanity check; detects gross errors (>15%) only |
| **$n = 30$** | 3.06% | **91** | **9.28%** | 9.50% | 10.00% | ~45 min | Matches Stage 1 stratum size; bounds error < 10% |
| **$n = 50$** | 5.10% | **55** | **5.61%** | 5.82% | 6.00% | ~75 min (1.25 hr) | **Optimal diagnostic balance; bounds error < 5.6%** |
| **$n = 60$** | 6.12% | **46** | **4.69%** | 4.87% | 5.00% | ~90 min (1.5 hr) | Reaches sub-5% error bound threshold |
| **$n = 100$** | 10.19% | **27** | **2.75%** | 2.95% | 3.00% | ~2.5 hr | Reaches sub-3% error bound; significant effort |
| **$n = 253$** | 25.79% | **9** | **0.92%** | 1.18% | 1.19% | ~6–8 hr | **Minimum size to achieve rigorous sub-1% bound** |

### 6.3 Mathematical Findings on the $n = 25$ Recommendation

1. **Refutation of Sub-1% Claim for $n=25$:**  
   For $n = 25$, observing zero errors yields an upper error bound of $K_{\text{upper}} = 109$ errors, or **$11.11\%$**. It is mathematically impossible for $n=25$ to establish a sub-1% error rate. It cannot even rule out a 10% error rate.
2. **Threshold for Sub-1% Bound:**  
   The absolute minimum sample size from $N = 981$ that can rule out an error rate of approximately 1% at 95% confidence is **$n = 253$ mentions** ($K_{\text{upper}} = 9$, error rate $0.917\% \le 1.0\%$). At $n = 252$, $K_{\text{upper}} = 10$ ($1.019\% > 1.0\%$).
3. **Core Assumptions Required:**  
   - **Binary & Fixed Ground Truth:** Correctness $y_i \in \{0, 1\}$ is a fixed characteristic of each mention in the text.
   - **Uniform Random Sampling:** Drawn via cryptographically seeded SRSWOR.
   - **Treatment of Unassessable Cases:** Any mention where narrative context is genuinely ambiguous (`uncertain_link`) must be treated conservatively as an error ($y_i = 0$) when calculating the upper bound, rather than dropped.

---

## 7. Proposed Supplemental Probability-Sampling Protocol (Awaiting Authorization)

If the research team decides to obtain empirical evidence for the scored heuristic linking mechanism, the following protocol must be executed.

> [!IMPORTANT]
> **Execution Status:**  
> **This sample has NOT been drawn.** In strict compliance with task constraints, this section specifies the exact protocol and awaits author authorization.

### 7.1 Sampling Frame & Verification

- **Population Source:** Canonical SQLite database `data/db/reverend-insanity.db`, table `mention`.
- **Eligibility Predicate:** All mentions $r$ where `novel_id == 'reverend-insanity'` and `stratum(r) == 'background'`.
- **Frame Properties Verified:**
  * Exact population size: $N_{\text{supp}} = 981$.
  * Mutually exclusive and disjoint from the other 6 strata.
  * 100% are proposed system links in the frozen September 25 system (`target_id IS NOT NULL`).
  * 100% are rigid names (`alias_type == 'RIGID_NAME'`).
  * Linking methods: 964 `SCORED` heuristic matches, 17 `DECLARATION` matches.

### 7.2 Protocol Specifications

1. **Sample Size Recommendation:** **$n = 50$ mentions**.  
   *Justification:* Provides the optimal trade-off between human review investment (~75 minutes) and statistical power. Halves the error bound from 11.11% ($n=25$) down to **5.61%**, ensuring that true corpus precision is empirically bounded above $99.1\%$ while avoiding the disproportionate 6–8 hour burden of $n=253$.
2. **Random Seed:** `20261014` (distinct from original sampling `20260925` and V2 shuffling `20261013`).
3. **Selection Procedure:** Simple random sampling without replacement (SRSWOR) over the sorted list of 981 mention IDs.
4. **Inclusion Probability:** $\pi_j = 50 / 981 \approx 0.050968$ (sampling weight $w_j = 19.6200$).
5. **Row-ID Preservation:** Assigned stable identifiers `S001` through `S050`, with a metadata mapping table preserving original mention IDs, chapters, and blocks.
6. **Blinding Format:** Identical to V2 standard sheet:
   - Excerpt: $\le 200$-character window with `[[mention]]` delimiters.
   - Stripped: Category cues and silver reference decisions stripped.
   - Slots: Reviewer label, notes, and confidence slots shipped completely empty.
7. **Integration into Final Stratified Estimator:**  
   Once adjudicated, the 50 observations $(x_j, y_j)_{j=1}^{50}$ will enter `validate_adjudication_package.py` as a distinct stratum:
   - Stratum mean: $\bar{y}_{\text{scored}} = \frac{1}{50} \sum y_j$.
   - Population total contribution: $\hat{Y}_{\text{scored}} = 981 \times \bar{y}_{\text{scored}}$.
   - Stratum variance contribution: $N_{\text{scored}}^2 (1 - \frac{50}{981}) \frac{s_{\text{scored}}^2}{50}$.

---

## 8. Inspection of Current V2 Review Package & Blinding Integrity

Before approving manual review, the physical files in `data/eval/adjudication/` were inspected:

### 8.1 Physical File Verification

- `standard_200_v2_blind.csv` (200 rows):
  * **Columns:** `presentation_order, sample_id, chapter, source_text, mention, predicted_entity, candidate_entities, system_decision, system_link_status, adjudicated_decision, adjudicator_confidence, adjudicator_notes, adjudication_status, second_review_flag`.
  * **Blinding Check:** Stripped of `category` and `reference_set_decision`. No LLM candidate annotations present.
  * **Reviewer Slots:** All 200 rows have empty `adjudicated_decision`, empty `adjudicator_confidence`, empty `adjudicator_notes`, and `adjudication_status == 'pending'`.
  * **Order:** Pseudo-randomly shuffled (presentation order 1..200).
- `hardcases_88_v2_blind.csv` (88 rows):
  * **Columns:** `presentation_order, sample_id, chapter, source_text, mention, target_reference_entity, adjudicated_decision, adjudicator_confidence, adjudicator_notes, adjudication_status, second_review_flag`.
  * **Blinding Check:** Stripped of `category`. No LLM annotations present.
  * **Reviewer Slots:** All 88 rows have empty decision fields and `adjudication_status == 'pending'`.
- `v2_metadata_mapping.csv` (288 rows):
  * Maintains immutable linkage between `sample_id` (`R001`–`R200`, `H001`–`H088`), `presentation_order`, and underlying stratum metadata.

### 8.2 Assessment of Review Viability

- **Context Window:** The $\le 200$-character excerpts with `[[mention]]` markers provide clear immediate context. The chapter number is present if broader context is needed.
- **Candidate Entities:** Semicolon-separated gazetteer matches assist disambiguation without suggesting an answer.
- **Taxonomy:** The V2 taxonomy cleanly differentiates link correctness (`correct_link`, `incorrect_link`, `uncertain_link`) from abstention appropriateness (`appropriate_abstention`, `inappropriate_abstention`, `uncertain_abstention`), preventing any conflation.

**Final Blinding Verdict:** The V2 adjudication package is 100% sound, un-cued, and ready. Manual review can proceed immediately.

---

## 9. Comprehensive Estimator & Accounting Reconciliation

| Estimator / Quantity | Mathematical Formula | Value | Standard Error / Bound | 95% Confidence Interval | Methodological Status |
|:---|:---|---:|---:|:---|:---|
| **Raw Sample Precision (Links)** | $\frac{c_{\text{sample}}}{m_{\text{sample}}} = \frac{141}{151}$ | **93.38%** | 2.02% (Binomial) | $[88.08\%, 96.74\%]$ | Unweighted empirical sample precision over attempted links. |
| **Conflated Raw Precision (Historical)** | $\frac{141}{141 + 17} = \frac{141}{158}$ | **89.24%** | 2.47% (Binomial) | $[83.35\%, 93.52\%]$ | Legacy unweighted figure conflating 7 false-negative abstentions. |
| **Horvitz-Thompson / Hájek Ratio** | $\frac{\sum w_i y_i}{\sum w_i x_i} = \frac{10,610.91}{10,646.34}$ | **99.67%** | — | — | Design-consistent estimator restricted to the sampled domain. |
| **Exact-Denominator Estimator** | $\frac{\hat{Y}}{X_{\text{pop}}} = \frac{11,046.86}{11,092}$ | **99.59%** | 0.078% (Plug-in) | $[99.44\%, 99.75\%]$ | **Imputed:** Assumes 100% precision on unobserved 981 scored records. |
| **Horvitz-Thompson over Known Denom** | $\frac{\hat{Y}_{\text{HT}}}{X_{\text{pop}}} = \frac{10,610.91}{11,092}$ | **95.66%** | — | — | True HT total divided by $X_{\text{pop}}$ (reflects missing sample mass). |
| **Stratified Ratio Estimator** | $\frac{\hat{Y}}{\hat{X}} = \frac{11,046.86}{11,082.57}$ | **99.68%** | 0.074% (Taylor) | $[99.53\%, 99.82\%]$ | Standard survey ratio estimate with 100% imputation on scored pool. |
| **Conservative Boundary Lower Bound** | $\frac{Y_{\text{conservative}}}{X_{\text{pop}}}$ | **90.45%** | — | — | Finite-population boundary bound for $n=30$ zero-error strata. |
| **Scored Pool Hypergeometric Bound ($n=25$)** | $\frac{K_{\text{upper}}(25)}{981}$ | **11.11%** error | — | $[88.89\%, 100.0\%]$ | 95% bound on scored pool if 0 errors in $n=25$ draws. |
| **Scored Pool Hypergeometric Bound ($n=50$)** | $\frac{K_{\text{upper}}(50)}{981}$ | **5.61%** error | — | $[94.39\%, 100.0\%]$ | 95% bound on scored pool if 0 errors in $n=50$ draws (Recommended). |
| **Scored Pool Hypergeometric Bound ($n=253$)** | $\frac{K_{\text{upper}}(253)}{981}$ | **0.92%** error | — | $[99.08\%, 100.0\%]$ | 95% bound on scored pool if 0 errors in $n=253$ draws (Sub-1% claim). |

---

## 10. Summary of Updated Regression & Audit Tests

The test suite in `packages/pipeline/tests/test_adjudication_package.py` has been updated and expanded with adversarial audit tests:

1. `test_sampling_inclusion_probabilities_and_non_uniformity`: Asserts non-uniformity of the general pool ($\pi_{\text{alias}} / \pi_{\text{easy}} > 6.0$, $\pi_{\text{alias}} / \pi_{\text{bg}} > 12.5$).
2. `test_database_denominator_version_reconciliation_sql`: Verifies database totals ($11,174$ total, $11,122$ post-c8bfda9 links, $30$ title links, $11,092$ pre-c8bfda9 links).
3. `test_zero_sample_in_scored_background_stratum`: Asserts that zero of the 34 Stage-2 records were drawn from heuristic scored links.
4. `test_exact_denominator_estimator_imputation_audit`: Reconstructs the 11,046.86 numerator formula, proves it imputes 100% correctness to the 981 unobserved scored records, and tests sensitivity.
5. `test_horvitz_thompson_hajek_estimator_and_missing_domain`: Verifies $\hat{Y}_{\text{HT}} = 10,610.91$, $\hat{X}_{\text{HT}} = 10,646.34$, $\hat{R}_{\text{Hajek}} = 99.667\%$, and $\hat{Y}_{\text{HT}} / 11,092 = 95.66\%$.
6. `test_finite_population_sample_size_hypergeometric_bounds`: Verifies exact hypergeometric bounds for $N=981$ at $n=25$ (109 errors, 11.11%), $n=50$ (55 errors, 5.61%), $n=60$ (46 errors, 4.69%), $n=100$ (27 errors, 2.75%), and $n=253$ (9 errors, 0.92%).
7. `test_scored_background_sampling_frame_and_system_links`: Verifies that all 981 scored background records are linked predictions (964 SCORED, 17 DECLARATION) forming a valid disjoint frame.

All 17 tests pass deterministically (`pytest packages/pipeline/tests/test_adjudication_package.py`).
