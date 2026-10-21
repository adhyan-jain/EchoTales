# EchoTales: Human-Adjudication Guide (v2 Protocol)

**Package Location**: `data/eval/adjudication/`  
**Protocol Reference**: [`docs/results/GOLD_AND_ANNOTATION.md`](file:///home/adhyan/Desktop/EchoTales/docs/results/GOLD_AND_ANNOTATION.md)  
**Methodological Audit**: [`docs/research/AUDITS_AND_ADJUDICATION.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/AUDITS_AND_ADJUDICATION.md)  
**Publication Strategy**: [`docs/research/AUDITS_AND_ADJUDICATION.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/AUDITS_AND_ADJUDICATION.md)  

---

## 1. Overview & Blinding Guardrails

This package provides a **fully blinded, spreadsheet-ready adjudication interface** for author validation of the EchoTales entity resolution evaluation suite.

To guarantee rigorous reviewer blinding and eliminate cognitive anchoring:
1. **No Category Cues**: Sampling strata (`category`) are stripped from the active review view.
2. **No Silver Reference Cues**: Silver ground truth (`reference_set_decision`) is stripped from the standard review view.
3. **Un-Cued Presentation Order**: Rows are pseudo-randomly shuffled (seed `20261013`) so errors and abstentions do not appear in predictable chapter or stratum clusters.
4. **Stable Provenance**: Every row preserves its canonical, immutable `sample_id` (`R001`–`R200` for standard sheet; `H001`–`H088` for hard cases).
5. **Independent Review**: Model annotations from `gpt-5.6-luna` are quarantined in [`model_annotations_reconciliation.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/adjudication/model_annotations_reconciliation.csv) until manual review is completed.

---

## 2. Active Review Files (V2 Un-Cued Presentation)

| File | Rows | Target Evaluated | Primary Review Task |
|---|---:|---|---|
| [`standard_200_v2_blind.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/adjudication/standard_200_v2_blind.csv) | 200 | System prediction (`predicted_entity`) | Judge whether the system's proposed link or abstention is correct. |
| [`hardcases_88_v2_blind.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/adjudication/hardcases_88_v2_blind.csv) | 88 | Silver reference label (`target_reference_entity`) | Judge whether the silver reference identity correctly captures the referent under character shifts. |
| [`v2_metadata_mapping.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/adjudication/v2_metadata_mapping.csv) | 288 | Reference mapping | Registry linking `presentation_order` to original stratum and silver labels. |

*(Legacy V1 ordered files `standard_200_blind.csv` and `hardcases_88_blind.csv` remain archived for backwards compatibility).*

---

## 3. Schema & Column Definitions

### Input Context Fields (Read-Only)
- `presentation_order`: Integer sequence (1 to 200, 1 to 88). Work sequentially down this column.
- `sample_id`: Stable identifier (`R001`–`R200` or `H001`–`H088`).
- `chapter`: Story chapter number (consult surrounding chapter text if the $\le 200$-character window is insufficient).
- `source_text`: Narrative excerpt with the target mention delimited as `[[mention]]`.
- `mention`: Surface text of the mention.
- `predicted_entity`: System link output (standard sheet only; or `UNRESOLVED`).
- `candidate_entities`: Semicolon-separated entities sharing the surface name in the novel gazetteer.
- `system_decision`: Decision method and alias type (e.g. `LINK (GAZETTEER_EXACT; None)`).
- `system_link_status`: Automatically set to `LINKED` or `ABSTAINED`.
- `target_reference_entity`: Silver identity under evaluation (hard cases sheet only).

### Human Adjudication Fields (To Fill In)
- **`adjudicated_decision`**: **Required**. Enter the precise decision (see Taxonomy below). Shorthand entries `correct`, `incorrect`, and `unresolved` are also accepted and automatically mapped.
- **`adjudicator_confidence`**: **Recommended**. One of `high`, `medium`, `low`.
- **`adjudicator_notes`**: **Required**. 1 concise sentence explaining who the true referent is and citing textual evidence.
- **`adjudication_status`**: Set to `reviewed` when complete, or `needs_second_review` if borderline.
- **`second_review_flag`**: Set to `1` if you want a second reviewer or co-author to independently verify this row; otherwise `0`.

---

## 4. Disambiguated Decision Taxonomy

To resolve the historical ambiguity surrounding `unresolved`, choose the label corresponding to `system_link_status`:

### Case A: System Proposed a Link (`system_link_status == 'LINKED'`)
- **`correct_link`** *(shorthand: `correct`)*: The linked entity is the true referent in the story context.
- **`incorrect_link`** *(shorthand: `incorrect`)*: The system linked to the wrong person, or the mention does not refer to a person/place/organization (e.g. an animal, clan name, or idiom).
- **`uncertain_link`** *(shorthand: `unresolved`)*: Narrative context is too ambiguous to confirm or refute the link.

### Case B: System Abstained (`system_link_status == 'ABSTAINED'`, i.e. `predicted_entity == 'UNRESOLVED'`)
- **`appropriate_abstention`** *(shorthand: `unresolved`)*: The mention is genuinely ambiguous, generic, non-referential, or unresolvable in context; the system was right not to guess.
- **`inappropriate_abstention`** *(shorthand: `incorrect`)*: The true referent is obvious from context; the system should have linked it (false negative).
- **`uncertain_abstention`** *(shorthand: `unresolved`)*: Reviewer cannot determine whether an entity link should have been made.

### Case C: Hard Cases Sheet (`target_reference_entity`)
- **`correct_reference`** *(shorthand: `correct`)*: The silver reference accurately identifies the referent at that point in the narrative.
- **`incorrect_reference`** *(shorthand: `incorrect`)*: The silver reference identity is flawed or inaccurate.
- **`uncertain_reference`** *(shorthand: `unresolved`)*: Cannot determine referent from narrative context.

---

## 5. Review Execution & Pacing (~2.5–3.0 Hours Total)

1. Open `standard_200_v2_blind.csv` in your preferred editor or spreadsheet tool.
2. Review rows 1 through 200 in `presentation_order`:
   - Fast rows (`easy_name`, prominent characters): ~10–15 seconds.
   - Complex rows (`relational`, `title`, disguised characters): ~30–45 seconds.
   - Pacing: ~100 rows/hour $\implies$ ~2 hours for standard 200.
3. Open `hardcases_88_v2_blind.csv` and review rows 1 through 88:
   - Pacing: ~45–60 minutes.
4. Total review investment: **2.5 to 3.0 hours**.

---

## 6. Programmatic Verification & Metric Reporting

Once adjudications are recorded, validate the package with:

```bash
python3 scripts/review/validate_adjudication_package.py --v2
```

To assert that all rows are 100% adjudicated before finalizing:

```bash
python3 scripts/review/validate_adjudication_package.py --v2 --require-complete
```

This command runs the automated audit pipeline:
1. Verifies 100% row coverage and schema integrity.
2. Computes the **Stratified Ratio Estimator** ($\hat{R} = \hat{Y}/\hat{X}$) with finite population correction (FPC) and Taylor linearization 95% confidence intervals.
3. Computes system abstention rate and abstention appropriateness.
4. Reports model-vs-human agreement and Cohen's $\kappa$ against quarantined model suggestions.
