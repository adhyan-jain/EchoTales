# Pre-registration PD v2: repaired re-run of the public-domain disclosure benchmark (version 1)

Written and frozen **before any model sees a v2 item**. Branch `chimera/system-adapters`, 2026-10-16. Hashes in `MANIFEST_PD_v2.json`. PD v1 (`PREREG_PD_reveal_benchmark.md`) and its results are unchanged and remain on record: v1 verdict NOT SUPPORTED, with only `gpt-5.6-luna` passing the renaming-validity gate.

**Why v2 (owner request, 2026-10-16: "go ahead with 2 and 3").** The v1 result left the leakage question open for four local models, because their A-minus-B gaps (+9 to +44 points) could not be separated from renaming damage (R0 agreement 57% to 86%). The v1 diagnosis named three causes, and v2 repairs exactly those: (1) answer-format noise (Mistral 35 invalid answers over real and synthetic items), (2) only 21 plain controls, so the 95% gate had a one-item resolution of 4.8 points, (3) no way to tell renaming damage from a one-cipher artefact. v2 also adds more events (point 3 of the owner's request) and computes the "most-mentioned candidate" baseline that v1 listed but never computed.

**Label provenance (every number).** Labels are **text-derived** (the book's own explicit reveal sentence, found by exact search; the cutoff is a fixed position before it). The *selection* of events, reveal sentences and cast lists was made by model-drafters (7 events in v1, 12 in `PD_events_v2_additions.json`) and is **not yet verified by the owner**; each can be re-checked by exact search. Nothing is human-verified. Label quality caveats per event are in `docs/research/PD_EVENTS_V2_NOTES.md` (weakest oracles: MC, DL, SA).

## 1. What changes from v1 (everything else is identical, including the item windows, candidate lists and seeds)

- **Events:** the 7 v1 events plus 12 new ones from 12 further books (19 events, 19 books). Frozen files `PD_events_v1.json`, `PD_events_v2_additions.json`.
- **Plain controls:** up to **8 per event** (the two non-identity cast names with the most prefix mentions, four evenly spaced mentions each), instead of 3.
- **Arms:** A original; B all proper nouns renamed by the T4 v5 cipher (seed 20261015, as v1); **B2** the same cipher with an independent seed (20261016). Closed book: C_orig, C_ren, C_ren2.
- **Output:** the final instruction becomes a JSON answer request and the runner supplies an ollama JSON-schema `format` whose enum is the candidate letters plus UNDETERMINED (`PD_prompts_v2.json`). Context 2048 tokens, `num_predict` 24, temperature 0, seed 20261016, GPU only, no CPU offload.
- **Models (local, free):** `qwen2.5:7b`, `llama3.1:8b`, `mistral:7b-instruct`, `phi4-mini`, `gemma2:9b` (retried; it failed the VRAM check in v1 and is reported "not run" again if it fails). **No paid model is run in v2** (cumulative cap: $0.0275 left, not enough for a 3-arm run). Each cell runs once.
- **Synthetic unseen-text control:** the same 62 L2U items, arms A and B, same output constraint.

## 2. Metrics and decision rules (fixed now)

- **R0, per model:** A and B give the same answer on at least **95%** of the plain controls (unchanged threshold, now over about 150 controls, so at most about 7 disagreements). Also reported: A versus B2 and B versus B2 agreement (damage measured without the original text), and an 85% "lenient" flag used only for a labelled sensitivity analysis, never for the verdict.
- **Premature rate** per arm: share of pre-reveal alias items answered with the revealed identity's letter. **Gap** = rate(A) minus the mean of rate(B) and rate(B2), item-level bootstrap (5,000 resamples, seed 20261016).
- **Damage-adjusted gap (descriptive):** gap minus (1 minus R0 agreement), a crude upper bound on how much of the gap renaming damage alone could produce.
- **Baseline:** premature rate if a model always answered the candidate with the most mentions in the prefix; reported per run.
- **Positive control (closed book):** `memory_present` if C_orig names the revealed identity for at least k of the 19 events, where k is the smallest value whose exact one-sided binomial probability under chance 1 in 8 is at most 0.05; C_ren and C_ren2 reported beside it.
- **Pooled primary statistic:** among models passing R0, the gap pooled over (model, item) pairs, bootstrapping items; synthetic gap pooled likewise; difference-in-differences.
- **Verdict (all must hold for SUPPORTED):** (i) pooled gap at least **+10 points**, 95% interval above 0; (ii) pooled DiD above 0 with the interval above 0; (iii) `memory_present` in at least **3** models passing R0. **PARTIALLY SUPPORTED:** (i) holds but not (ii) or (iii). **NOT SUPPORTED:** (i) fails. **Declared change from v1:** if fewer than **3** models pass R0, the verdict is **INCONCLUSIVE (validity-limited)**, not NOT SUPPORTED, because condition (iii) cannot then be met and the outcome would reflect missing power, not the absence of an effect. Each outcome is reported as it falls.
- **Secondary (descriptive):** abstention, post-reveal accuracy, plain-control accuracy in A and B, premature rate by distance, per-model gaps for models failing R0 (always labelled "not interpretable as memory").

## 3. Limits stated before the run

Event and cast selection is the model-drafter's and not owner-verified; several new events have weak oracles (a spoken or implied reveal, a cutoff close to the reveal), listed in the notes file; six of the 19 books are translations; hints before the explicit sentence may let a careful reader infer early, so the contrast, not raw accuracy, is the target; candidate lists anchor; constrained decoding can change a model's behaviour relative to free text, so v2 gaps are not directly comparable with v1 gaps; local 7 to 9 billion parameter models only; one run per cell; a result is about LLM behaviour on famous public-domain novels, not about EchoTales or web serials.

## 4. Safety

No novel text is written to the repository; texts come from a local Gutenberg copy in the scratchpad. No API key is read and no paid call is made.

## 5. Deviations log

None at freeze.
