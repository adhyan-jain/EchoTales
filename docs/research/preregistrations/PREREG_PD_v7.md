# Pre-registration PD v7: prospective test that the leakage gap is larger for famous than obscure books (version 1)

Written and frozen **before any v7 model call**. Branch `chimera/system-adapters`, 2026-10-16. Hashes in `MANIFEST_PD_v7.json`. Nothing in PD v1 to v6 is changed.

**Why v7.** The report's dose-response finding (5.22: the per-event gap rises with how well the book is recognised) is **post hoc**. v7 tests its simplest consequence **prospectively**: on books and events fixed in advance and classified as famous or obscure by an objective rule before any model saw them, the leakage gap should be larger for the famous class.

**Fame rule (fixed before opening any candidate text).** On 2026-10-16 04:54 UTC the Project Gutenberg Top-100 EBooks lists (yesterday, last 7 days, last 30 days) were saved in `PD_v7_fame_snapshot.txt`. An event's book is **famous** if its title or Gutenberg id appears in any of the three lists, otherwise **obscure**; the events file records the class and the evidence per event, and the verifier recomputes the class from the snapshot. **This rule measures one month of download counts, not literary fame**: The Green Mummy and The Secret of Chimneys count as famous because of download spikes, and The Valley of Fear is obscure by the rule although it is a Holmes novel. That is a limitation of the proxy, stated now.

## 1. Design

- **Events:** the nine in `PD_events_v7_additions.json` (5 famous: GM, CH, LP, BS, LF; 4 obscure: MS, CS, RR, VF), none from a book used before; weak oracles flagged in `PD_EVENTS_V7_NOTES.md` (LP: identity name saturates the prefix and the spoken equation is in the gap; CH: no alias in the anchor and only 8 pre-cutoff mentions; MS: implicit equation 19,445 characters before the anchor; VF: obscure by rule but a Holmes novel; RR: surname cue). The set is **below the intended size** (target 12 to 16, 6 per class); it was not padded.
- **Items and arms:** the PD v2 to v6 machinery: arms A, B, B2 (two ciphers), the alias-only closed book and the title-assisted probe M2; the cue-preserving arm B3 is built but not asked. Prompts, windows, candidate lists, seeds, schema-constrained JSON, temperature 0 as before. Each cell once.
- **Models:** the five local models (`qwen2.5:7b`, `llama3.1:8b`, `mistral:7b-instruct`, `phi4-mini`, `gemma2:9b`); `gpt-5.6-luna` only within the remaining budget if run, budget-guarded.
- **Validity (G2):** a model is valid if B-versus-B2 agreement on this set's real plain controls is at least 90% and its PD v3 synthetic A-versus-B agreement is at least 80%.

## 2. Hypotheses and decision rules (fixed now)

- **Event-level quantity:** each event's gap (A minus the mean of B and B2 over its pre-reveal items), averaged over the models in the pool.
- **H1 (primary):** over the valid local models, mean event gap for famous events minus obscure events is at least **+10 points** with a one-sided permutation p below 0.05 (20,000 shuffles of the event fame labels, seed 20261020).
- **H2:** the same condition for Luna alone, if run.
- **H3:** recognition (share of valid local models naming the identity under M2 with the original names) is higher for famous than obscure events with permutation p below 0.05.
- **Verdict:** **SUPPORTED** if H1 and H3 hold; **PARTIALLY SUPPORTED** if H1 or H2 holds without both H1 and H3; **NOT SUPPORTED** if neither H1 nor H2 holds; **INCONCLUSIVE** if fewer than 3 valid local models or fewer than 4 events in a stratum.
- **Power, stated in advance:** with 5 famous and 4 obscure events the smallest attainable one-sided permutation p is 1/126 (about 0.008), so only a large difference can reach 0.05; a failure to reach it is "not detected at this power", not absence.
- **Secondary (descriptive):** results dropping LP, CH and VF (weak or proxy-ambiguous classes); the continuous version (event gap against M2 recognition count, as in 5.22); per-model values.

## 3. Limits stated before the run

Nine events; a coarse and partly inappropriate fame proxy; model-selected events not owner-verified; weak oracles listed above; local 7B to 9B models; one run per cell; public-domain Western fiction (English, one translation); a result concerns LLM behaviour on these novels, not EchoTales or web serials.

## 4. Safety and deviations

No novel text is written to the repository (texts live in the git-ignored `data/raw/pd_gutenberg_v7/`); the Luna key, if used, is read only inside a subshell and never printed. Deviations log: none at freeze.
