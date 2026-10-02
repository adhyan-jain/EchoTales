# Card: H-CAL, is upstream confidence a usable posterior?

- **Problem:** confidence-conditioned rendering needs confidences that rank errors.
- **Hypothesis:** the ladder's tier constants are monotone and reach AUROC ≥ 0.6 on human gold.
- **Data:** PDNC, 28 novels, 36,991 quotes.
- **Method:** `transforms/attribution_probe.py` runs the product's `attribute_span` with paragraph-bounded context; strict and lenient scoring.
- **Result:**
  - **Killed.** AUROC 0.59.
  - EXPLICIT tier: 0.95 stated vs 86.7% measured. PROXIMAL tier: 0.75 stated vs 63.8% measured.
  - 52% of errors are addressee capture.
- **Limitations:**
  - the LLM tier is excluded;
  - coverage is only 9.9%, because the regex tiers are tuned for web-novel tags.
- **Role:** infrastructure finding. It gates every policy candidate (C04, C11's policy half).
- **Reproducibility:** `python -m echotales.research run attribution_calibration`.
