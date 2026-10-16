# Pre-registration PD v6: final confirmatory test on 7 fresh books with all instruments fixed in advance (version 1)

Written and frozen **before any v6 model call**. Branch `chimera/system-adapters`, 2026-10-16. Hashes in `MANIFEST_PD_v6.json`. Nothing in PD v1 to v5 is changed.

**Why v6.** Every earlier leakage verdict was reached on books the analysis later re-used, with rules changed between versions, and the strongest numbers (PD v4) were a re-evaluation of already-seen gaps. v6 is the one test on **books no earlier step has touched** (7 books by 7 authors, none in v1 to v3, texts first read after the events were frozen) with every instrument from v2 to v5 fixed beforehand: the two renaming ciphers (arms B, B2), the cue-preserving pseudonym arm (B3, PREREG_PD_v5), the memory-free validity gate (G2, PREREG_PD_v4), the title-assisted memory probe (M2, PREREG_PD_v4), and event-cluster inference (the resampling unit is the event, added after the external adversarial review, report 5.19). It is small (7 events), so it has low power; that is stated now.

**Labels.** Text-derived oracle: the book's explicit reveal sentence located by exact search; the 7 events (`PD_events_v6_additions.json`) were selected by a model-drafter and are not owner-verified; weak oracles flagged in `PD_EVENTS_V6_NOTES.md` (CM weak; GR medium-weak; PN's identity label is ambiguous with the old Major Effingham). No human labels.

## 1. Design

- **Items:** 124 (54 pre-reveal, 14 post-reveal, 56 plain controls); arms A, B, B2, B3 per item; per event the alias-only closed book (C_orig, C_ren, C_ren2) and the title-assisted probe M2 (M2_orig, M2_ren, M2_ren2). Prompts, windows (1,200 characters), candidate lists, seeds, schema-constrained JSON, temperature 0 as in v2 to v5. 538 calls per model. Each cell once.
- **Synthetic unseen-text control:** not re-run; each model's PD v3 synthetic A-versus-B agreement (same 62 items, same prompts) is its G2b.
- **Models:** the five local models (`qwen2.5:7b`, `llama3.1:8b`, `mistral:7b-instruct`, `phi4-mini`, `gemma2:9b`); `gpt-5.6-luna` within the owner's extra budget ($0.20 granted for unattended work, ceiling total $0.4824), budget-guarded, parsed JSON, reported as the reference comparator and included in the pool if it passes G2.

## 2. Decision rules (fixed now)

- **Valid model:** B-versus-B2 agreement on this set's real plain controls at least 90% and PD v3 synthetic A-versus-B agreement at least 80%.
- **Pooled statistics over valid models, event-cluster 95% intervals (5,000 resamples, seed 20261019):** gap A-B (A minus the mean of B and B2); gap A-B3; recovered fraction R; event sign test for gap A-B.
- **Verdict:** **SUPPORTED** needs (i) gap A-B at least +10 points with the interval above 0, (ii) gap A-B3 at least +10 points with the interval above 0 (the gap survives restoring name cues), (iii) M2 memory present (at least k of 7 events, k the smallest value whose exact one-sided binomial probability under chance 1 in 8 is at most 0.05) in at least 3 valid models. **PARTIALLY SUPPORTED:** (i) holds but not both (ii) and (iii). **NOT SUPPORTED:** (i) fails. **INCONCLUSIVE:** fewer than 3 valid models.
- **Pooled fresh-book report (descriptive):** v3 and v6 together (19 events), same statistics, using the stored v3 runs and v6 runs for models valid in each set; plus sensitivity dropping CM and GR.
- **Not claimed:** with 7 events a sign test cannot reach p below 0.0156 and an interval lower bound near 0 is expected for modest effects; a failure to reach (i) is read as "not detected at this power", not as absence of an effect.

## 3. Limits stated before the run

7 events, model-selected, not owner-verified; one translation (813); three weak or ambiguous oracles; G2b from v3 (not re-measured); the pseudonym arm is heuristic (gender from pronouns, English-style names); local 7B to 9B models plus one API model; one run per cell; public-domain Western fiction only; a result concerns LLM behaviour on these novels, not EchoTales or web serials.

## 4. Safety and deviations

No novel text is written to the repository (texts live in the git-ignored `data/raw/`); the Luna key is read only inside a subshell and never printed. Deviations log: none at freeze.
