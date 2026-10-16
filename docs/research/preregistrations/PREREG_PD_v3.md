# Pre-registration PD v3: confirmatory test on 12 unused public-domain books, renaming-validity bar 80% (version 1)

Written and frozen **before any model sees a v3 item**. Branch `chimera/system-adapters`, 2026-10-16. Hashes in `MANIFEST_PD_v3.json`. PD v1 and v2 and all their results are unchanged and on record (v1 NOT SUPPORTED; v2 INCONCLUSIVE at the 95% bar; post-hoc sensitivity: PARTIALLY SUPPORTED at 85%, SUPPORTED at 80%).

**Why v3.** PD v2 showed a positive real-book gap and a zero unseen-text gap for all six models (Luna +35.2 points), but no model reached the 95% renaming-validity bar, and the only readings that issue a verdict used a bar chosen after the data. v3 tests the same hypothesis on **books that no earlier version used**, with the bar fixed in advance, so that a result can be called confirmatory.

**The 80% bar (owner decision, 2026-10-16: "anything 80+ is good enough").** 95% was an arbitrary convention of mine. 80% is the owner's stated convention for acceptable agreement; it is not tuned on v3 data. It was chosen after seeing the v2 sensitivity table, which is why the v2 sensitivity reading stays post hoc and v3 is the confirmation. The known cost of a lenient bar (the original-versus-renamed disagreement on plain controls is partly memory, section 5.15 of the report) is carried as a stated limit, not removed.

**Label provenance (every number).** Text-derived reveal oracle (the book's own explicit reveal sentence found by exact search; a conservative cutoff before it). Event, cast and anchor selection by a model-drafter; **not owner-verified**; weak oracles listed per event in `PD_EVENTS_V3_NOTES.md` (BR, LA, YR, EL, CO, IM, PG). No human label anywhere.

## 1. Design (identical to PD v2 except where stated)

- **Events:** the 12 in `PD_events_v3_additions.json` (12 books, 12 authors, 2 translations), none used in v1 or v2.
- **Items, arms, windows, candidates, seeds, prompts, constrained output, 8 plain controls per event, arms A / B / B2, closed book C_orig / C_ren / C_ren2, 62 synthetic unseen-text items:** exactly as `PREREG_PD_v2.md` and `PD_prompts_v2.json`.
- **Models:** the five local models of v2 (`qwen2.5:7b`, `llama3.1:8b`, `mistral:7b-instruct`, `phi4-mini`, `gemma2:9b`); no paid model is run unless the owner separately approves an exact cost estimate, in which case `gpt-5.6-luna` is added as the reference comparator and reported separately from the local pool and then in the pool.

## 2. Hypothesis and decision rules (fixed now)

- **H:** on unseen books, models that pass the renaming-validity bar name a hidden identity more often with original names than with renamed names (A minus the mean of B and B2), while the same renaming makes no difference on unseen synthetic text.
- **R0 (validity bar):** A and B give the same answer on at least **80%** of the plain controls. Reported alongside: the strict 95% flag, A versus B2 and B versus B2 agreement.
- **Pooled primary statistic:** among models passing R0, the gap pooled over (model, item) pairs with an item bootstrap (5,000 resamples, seed 20261016); the synthetic gap pooled likewise; difference-in-differences.
- **Verdict:** **SUPPORTED** needs (i) pooled gap at least **+10 points** with 95% interval above 0, (ii) difference-in-differences above 0 with interval above 0, (iii) closed-book `memory_present` (at least k of 12 events, k the smallest value whose exact one-sided binomial probability under chance 1 in 8 is at most 0.05) in at least **3** models passing R0. **PARTIALLY SUPPORTED:** (i) holds but not (ii) or (iii). **NOT SUPPORTED:** (i) fails. **INCONCLUSIVE:** fewer than 3 models pass R0.
- **Secondary (descriptive, not verdict-bearing):** per-model gaps; damage-adjusted gap; the most-mentioned-candidate baseline; abstention; post-reveal accuracy; premature rate per event and its rank correlation (Spearman) with the number of models that name the identity closed book; sensitivity of the pooled gap with the weakest oracle (BR) and with all events flagged weak in the notes dropped; the 95% reading.

## 3. Limits stated before the run

Event and cast selection not owner-verified; 12 events; spoken or implied reveals for several; two translations; the 80% bar admits models whose renaming disagreement on plain controls is partly memory (so the gap can be partly self-referential); constrained decoding; local 7B to 9B models only; one run per cell; the unseen-text synthetic control is the same 62 items as v2 (not fresh), so only the book set is confirmatory; a result concerns LLM behaviour on public-domain novels, not EchoTales or web serials.

## 4. Safety and deviations

No novel text is written to the repository; no API key is read and no paid call is made by the local runs. Deviations log: none at freeze.
