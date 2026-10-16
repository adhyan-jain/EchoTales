# EchoTales — Adversarial Statistical Audit of Stratified Precision, Confidence Intervals, and V2 Adjudication (V2 Audit)

**Date:** 2026-10-13  
**Status:** VALIDATED & RECONCILED (DEFENSIBLE EVALUATION BASELINE ESTABLISHED)  
**Audit Scope:** Independent mathematical, algorithmic, and database audit of stratum counts, population denominators, sampling designs, variance derivations, and blinding integrity.  
**Resource Footprint:** Zero external API calls, zero credit spend, zero GPU inference. Source CSVs, existing labels, and StoryTrace firewall preserved unmodified.

---

## 1. Executive Summary & Inconsistency Diagnosis

This adversarial audit was commissioned to independently test the mathematical and methodological claims made in `docs/research/PRE_ADJUDICATION_VALIDITY_AUDIT.md`. Rather than accepting reported values because regression tests passed, every row in `data/eval/human_review_200.csv`, `data/eval/human_review_200_annotated.csv`, and the canonical SQLite database `data/db/reverend-insanity.db` was independently parsed from first principles.

### The Discrepancy Found and Its Root Cause

The previous report asserted the following simultaneous claims:
- Total proposed links in sample: $158$ (with $141$ correct, $17$ incorrect).
- Title had $0$ candidate-correct, $2$ candidate-incorrect, and $28$ unresolved.
- Relational had $12$ candidate-correct, $15$ candidate-incorrect, and $8$ unresolved.
- Reported estimated total linked predictions: $\hat{X} = 11,082.6$.
- Reported estimated total correct links: $\hat{Y} = 11,046.9$.
- Reported precision: $\hat{R} = 99.68\%$.

An independent arithmetic check revealed that if one defines "linked predictions" as `correct + incorrect` ($141 + 17 = 158$), the estimator would yield:
$$\hat{X}_{\text{conflated}} = 11,004 + 39(2/30) + 125(27/35) = 11,103.03 \implies \hat{R} = \frac{11,046.86}{11,103.03} = \mathbf{99.494\%}$$

**Our audit diagnosed the exact cause of this mismatch:**
1. **The Code Used Actual System Decisions ($m = 151$ links), Not Model Labels:**  
   In the calculation code, `is_linked` was defined by the actual source system field `predicted_entity != 'UNRESOLVED'`. In the actual sample, the system attempted **$151$ links**, not $158$:
   - `title`: The system linked **$0$ mentions** ($m_6 = 0$); all 30 were abstentions (`NO LINK`).
   - `relational`: The system linked **$22$ mentions** ($m_4 = 22$), of which 12 were candidate-correct and 10 were candidate-incorrect.
   - `easy_name`, `background`, `alias`, `observer_sensitive`: all $30, 34, 35, 30$ were linked.
   - Total linked in sample: $30 + 34 + 35 + 30 + 22 + 0 + 0 = \mathbf{151}$.
2. **The Narrative Conflated Model Labels with System Actions:**  
   The candidate annotator (`gpt-5.6-luna`) assigned the label `incorrect` to **$7$ mentions where the system had abstained** ($2$ in `title`, $5$ in `relational`):
   - In `title`, mentions `R058` ("Wild boar king") and `R189` ("the clan leader") were abstained by the system (`NO LINK`), but the model rater labeled them `incorrect` (citing that "Wild boar king" is an animal, or that "the clan leader" should have been linked to Gu Yue Bo).
   - In `relational`, mentions `R028`, `R029`, `R030`, `R032`, `R036` ("young Miss") were abstained by the system (`NO LINK`), but the model rater labeled them `incorrect` (false-negative abstentions).
   - The narrative in the previous report naively summed all model `incorrect` labels ($10 \text{ linked} + 7 \text{ abstained} = 17$) and declared $141 + 17 = 158$ links, contradicting its own underlying calculation!
3. **Mathematical Resolution:**  
   When `is_linked` is determined by the source system action, $\hat{X} = 11,082.57 \approx 11,082.6$, $\hat{Y} = 11,046.86 \approx 11,046.9$, and $\hat{R} = 99.68\%$ are internally consistent. The discrepancy was an expository error in the previous report's narrative text, which failed to explain that 7 of the 17 "incorrect" labels were abstentions rather than linked predictions.

---

## 2. Traceable Per-Stratum Reconciliation Table

The following table reconstructs every count from the actual 200 source rows (`data/eval/human_review_200.csv`) and the corresponding candidate annotations (`data/eval/human_review_200_annotated.csv`):

| Stratum $h$ | Pop $N_h$ | Sample $n_h$ | Sys Linked $m_h$ | Sys Abstained $a_h$ | Cand-Corr Links $c_h$ | Cand-Inc Links $w_h$ | Cand App Abst $a_{\text{app}}$ | Cand Inapp Abst $a_{\text{inapp}}$ | Stratum Precision $p_h$ | Stratum Abst Rate | Pop Weight $W_h$ |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `easy_name` | 8,933 | 30 | 30 | 0 | 30 | 0 | 0 | 0 | 100.0% | 0.0% | 79.94% |
| `background` | 981 | 34 | 34 | 0 | 34 | 0 | 0 | 0 | 100.0% | 0.0% | 8.78% |
| `alias` | 977 | 35 | 35 | 0 | 35 | 0 | 0 | 0 | 100.0% | 0.0% | 8.74% |
| `relational` | 125 | 35 | 22 | 13 | 12 | 10 | 8 | 5 | 54.55% | 37.14% | 1.12% |
| `observer_sensitive` | 113 | 30 | 30 | 0 | 30 | 0 | 0 | 0 | 100.0% | 0.0% | 1.01% |
| `title` | 39 | 30 | 0 | 30 | 0 | 0 | 28 | 2 | N/A ($0/0$) | 100.0% | 0.35% |
| `unresolved_name` | 6 | 6 | 0 | 6 | 0 | 0 | 6 | 0 | N/A ($0/0$) | 100.0% | 0.05% |
| **Total** | **11,174** | **200** | **151** | **49** | **141** | **10** | **42** | **7** | — | — | **100.00%** |

### Accounting Identities Verified

1. **Sample Action Balance:** Total sample = $151 \text{ linked} + 49 \text{ abstained} = 200$.
2. **Linked Mention Balance:** Total links = $141 \text{ candidate-correct} + 10 \text{ candidate-incorrect} + 0 \text{ uncertain} = 151$.
3. **Abstention Balance:** Total abstentions = $42 \text{ candidate-appropriate} + 7 \text{ candidate-inappropriate (false negatives)} = 49$.
4. **All Model Labels Balance:** $141 \text{ (correct)} + (10 + 7)\text{ (incorrect)} + 42\text{ (unresolved)} = 200$.

---

## 3. Denominator Audit: Known Population vs. Estimated Ratio

### 3.1 Availability in the Full Corpus ($N = 11,174$)

An exhaustive query of table `mention` in `data/db/reverend-insanity.db` demonstrates that link/abstention status (`target_id IS NOT NULL` vs. `target_id IS NULL`) is recorded for **all 11,174 mentions in the novel**.

However, the audit identified an essential temporal nuance:
- **The Frozen Evaluation Sheet (2026-09-25):**  
  `data/eval/human_review_200.csv` was drawn on September 25, 2026, before `resolve/title_holders.py` was introduced (commit `c8bfda9`, September 27). In that baseline state, all transferable titles were unlinked (`target_id = None`).  
  In the population for that state:
  * `easy_name` (8,933), `background` (981), `alias` (977), `observer_sensitive` (113): all $11,004$ linked.
  * `title` (39), `unresolved_name` (6): all $45$ abstained.
  * `relational` (125): exactly $88$ linked, $37$ abstained.
  * **Exact Known Denominator ($X_{\text{pop}}$):** $11,004 + 88 = \mathbf{11,092}$ mentions.
- **The Post-September-27 Database State:**  
  After `c8bfda9`, 30 title mentions were linked, bringing the database total to $11,122$ linked mentions. However, the evaluation sheet evaluates the system *prior* to those title links (`R004` has `predicted_entity = 'UNRESOLVED'`). Using the post-September-27 denominator on pre-September-27 outputs would constitute a version mismatch.

### 3.2 Comparison of Precision Estimators

| Estimator | Formula | Value | Standard Error | 95% Confidence Interval | Interpretation |
|:---|:---|---:|---:|:---|:---|
| **Stratified Ratio Estimator ($\hat{R}$)** | $\frac{\hat{Y}}{\hat{X}} = \frac{11,046.86}{11,082.57}$ | **99.68%** | 0.074% (Taylor) | $[99.53\%, 99.82\%]$ | Standard survey estimator when denominator is treated as a random variable estimated from sample. |
| **Known-Denominator Estimator ($\hat{P}_{\text{known}}$)** | $\frac{\hat{Y}}{X_{\text{pop}}} = \frac{11,046.86}{11,092}$ | **99.59%** | 0.068% (Exact) | $[99.46\%, 99.73\%]$ | Design-based Horvitz-Thompson total divided by exact corpus link count. |
| **Conflated Narrative Estimator ($\hat{R}_{\text{conflated}}$)** | $\frac{\hat{Y}}{\hat{X}_{\text{conflated}}} = \frac{11,046.86}{11,103.03}$ | **99.49%** | 0.081% (Taylor) | $[99.34\%, 99.65\%]$ | Result if candidate-incorrect abstentions are mistakenly counted as proposed links. |
| **Raw Sample Precision (Unweighted)** | $\frac{c_{\text{sample}}}{m_{\text{sample}}} = \frac{141}{151}$ | **93.38%** | 2.02% (Binomial) | $[88.08\%, 96.74\%]$ | Unweighted sample precision over attempted links (under-represents dominant clean stratum). |
| **Conflated Raw Sample Precision** | $\frac{141}{141 + 17} = \frac{141}{158}$ | **89.24%** | 2.47% (Binomial) | $[83.35\%, 93.52\%]$ | The figure quoted in earlier documents, mixing linked errors with abstentions. |

---

## 4. Sampling Design Audit: The "Background" Anomaly

An audit of `scripts/review/prepare_human_review.py` (lines 106–108) revealed a notable implementation detail:
```python
taken = {c[1][0] for c in chosen}
remaining = [r for r in rows if r[0] not in taken]
chosen += [("background", r) for r in rng.sample(remaining, max(0, TOTAL - len(chosen)))]
```

### Finding
The 34 mentions labeled `"category": "background"` were not sampled from the 981 mentions matching the `stratum == 'background'` predicate (mentions linked via scored heuristics). Instead, they were drawn uniformly from `remaining`—the unchosen mentions of the entire novel.
- Cross-referencing those 34 mentions against the database reveals that **31 were actually `easy_name`** and **3 were `alias`**.
- None came from the 981 scored mentions.
- The true underlying sampling design is therefore a **5-stratum design**:
  1. `unresolved_name`: $N = 6, n = 6$ ($100\%$ census)
  2. `title`: $N = 39, n = 30$ ($76.9\%$ sample)
  3. `relational`: $N = 125, n = 35$ ($28.0\%$ sample)
  4. `observer_sensitive`: $N = 113, n = 30$ ($26.5\%$ sample)
  5. `general_pool` (easy_name + alias + scored background): $N = 10,891, n = 99$ ($0.91\%$ sample).

Because all 99 mentions sampled from the general pool were candidate-labeled correct ($100\%$), computing the point estimate under the true 5-stratum design yields:
$$\hat{Y} = 10,891(99/99) + 113(30/30) + 125(12/35) = 11,046.86$$
$$\hat{X} = 10,891(99/99) + 113(30/30) + 125(22/35) = 11,082.57$$
$$\hat{R} = \frac{11,046.86}{11,082.57} = \mathbf{99.6777\%} \approx \mathbf{99.68\%}$$
The point estimate is mathematically identical because all sub-pools in the general pool exhibited $100\%$ candidate accuracy. However, this finding must be documented so that future analyses do not treat the 34 "background" rows as representative of heuristic/scored links.

---

## 5. Variance and Confidence Interval Audit: The Boundary Problem

### 5.1 The Plug-In Sample Variance Illusion

In Taylor linearization:
$$u_{hi} = y_{hi} - \hat{R} x_{hi}$$
In strata where all sampled mentions are linked ($x_{hi} = 1$) and all are correct ($y_{hi} = 1$), the residual is constant: $u_{hi} = 1 - \hat{R}$.
Consequently, the sample variance of the linearized residuals is **identically zero**:
$$s_{uh}^2 = \frac{1}{n_h - 1} \sum_{i=1}^{n_h} (u_{hi} - \bar{u}_h)^2 = 0.0$$

In the provisional sample, this occurred in four strata (`easy_name`, `background`, `alias`, `observer_sensitive`), representing **98.5% of the novel's population**.
As a result:
- The Taylor linearization formula calculated variance **solely from the 35 relational mentions**.
- The 8,933 `easy_name` mentions were assumed to have zero error variance simply because 30 sampled mentions had no observed errors.
- This produced the ultra-narrow interval: $99.68\% \pm 0.14\%$.

### 5.2 Why Plain Plug-In Intervals Are Scientifically Inadequate

In finite-population sampling, observing 0 errors in $n_1 = 30$ draws from $N_1 = 8,933$ **does not prove the remaining 8,903 mentions contain zero errors**.
- By the **Rule of Three**, the 95% upper confidence bound on the error rate in `easy_name` is:
  $$\epsilon_{\text{upper}} \approx \frac{3}{n_1} = \frac{3}{30} = 10.0\%$$
- Under the exact binomial / hypergeometric model ($1 - 0.05^{1/30}$), the 95% upper error bound is **$9.50\%$**.
- If `easy_name` had even a $1.5\%$ true error rate in the unobserved population, there would be $\sim 134$ unobserved errors, pulling true novel precision down to $\sim 98.4\%$, far outside the reported $[99.53\%, 99.82\%]$ interval.

### 5.3 Defensible Reporting Standard

To maintain academic rigor and withstand peer review:
1. **Report the Asymptotic Point Estimate:** $\hat{R} = 99.68\%$ (or $\hat{P}_{\text{known}} = 99.59\%$).
2. **Report the Taylor SE with Caveat:** State that the Taylor plug-in standard error ($0.074\%$) is an asymptotic lower bound that conditions on the observed zero-error sample.
3. **Report the Conservative Finite-Population Lower Bound:** Using the Rule of Three / Clopper-Pearson 95% upper error limit for zero-error strata, the conservative 95% lower bound on precision is:
   $$\hat{R}_{\text{conservative\_lower}} = \mathbf{90.45\%}$$
4. **Publication Directive:** The paper must state that while the point estimate indicates near-ceiling precision ($>99.5\%$), a sample of $n=30$ on the dominant stratum statistically bounds corpus precision above $90.5\%$ at the 95% confidence level.

---

## 6. Separation of Provisional Baseline vs. Human Ground Truth

To guarantee absolute scientific integrity:

1. **Quarantine:** All numbers reported in this audit (including $99.68\%$, $11,046.9$, and $90.45\%$) are **provisional model-assisted baseline metrics** derived from `gpt-5.6-luna`. They are stored in `data/eval/adjudication/provisional_candidate_metrics.json`.
2. **Not Ground Truth:** These figures must never be cited as verified system accuracy.
3. **Adjudication Gate:** The validation script `scripts/review/validate_adjudication_package.py` will refuse to compute publication metrics if any human adjudication fields in `standard_200_v2_blind.csv` or `hardcases_88_v2_blind.csv` are pending or empty when `--require-complete` is passed.
4. **Un-Cued Human Review:** Human adjudicators must work entirely from the V2 blind sheets without viewing candidate annotations or silver reference labels.

---

## 7. Workflow Safety Verdict

**Is the V2 review package safe for manual adjudication?**

### VERDICT: YES, FULLY VALIDATED AND SAFE TO PROCEED

The review package is sound:
1. `standard_200_v2_blind.csv` and `hardcases_88_v2_blind.csv` are 100% blinded, shuffled, and preserve immutable `sample_id`s.
2. The statistical estimators and variance routines have been corrected and fortified against boundary artifacts and denominator ambiguities.
3. The author may begin manual review on `standard_200_v2_blind.csv` immediately, following `ADJUDICATION_GUIDE.md`.
