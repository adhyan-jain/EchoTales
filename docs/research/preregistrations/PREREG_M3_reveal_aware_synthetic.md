# Pre-registration M3: construct validity of the premature-resolution metric on synthetic worlds (version 1)

Written and frozen **before the M3 code exists or runs**. Repo HEAD `6c7e2c2`, 2026-10-15. Hash in `MANIFEST_M3.json`. A change is a new version file.

**Label provenance.** All labels are by construction from the world specification (synthetic). No model, no LLM, no human, no novel text, no spend. Nothing here describes real-world performance.

## 1. Question

The SIO v1 result (M2 = 0 for the shipped resolver) was vacuous: the resolver never uses reveals, so it cannot be premature. **Question:** does the premature-resolution metric (plus reader-view and omniscient-view accuracy) separate four systems that differ in how they treat disclosure? This tests the metric's *construct validity*, not any system's merit. The result for the reveal-aware systems is partly true by construction and is reported as such.

## 2. Worlds

The SIO v1 generator structure (12 chapters, 6 characters, 2 reveals per world, exactly one co-present named mention in alias chapters, perfect mention detection), re-implemented in a new module with the **reveal sentence template as a parameter**. Seeds 0 to 39, each with all four templates = **160 worlds, 320 reveals**. Templates, fixed now:

- T0 `{Alias}, in truth, was {Y}.`  (design template)
- T1 `{Alias} was none other than {Y}.`  (design template)
- T2 `Everyone now understood: {alias} was {Y} all along.`  (held out: detector patterns are NOT written for it)
- T3 `{Y} had been {alias} all along.`  (held out)

The oracle reads only the world spec: reader-warranted referent of an alias mention is UNDETERMINED (no link is correct) before the end of the sentence containing the reveal and Y from then on; omniscient referent is Y throughout.

## 3. Systems (all deterministic, CPU, no LLM)

- **S0** the shipped resolver `resolve_novel` default, unchanged.
- **S_abstain** S0, but every RELATIONAL_DEICTIC mention is left unlinked (UNDETERMINED), never uses reveals.
- **S_retro** volume-first: for every detected reveal, rebind every mention of that alias surface, in every chapter, to Y (the same logic as the title-holder pass, applied to aliases).
- **S_causal** reader-observer: an alias mention is linked to Y only if its position is at or after the start of the detected reveal sentence; otherwise left unlinked. Alias mentions with no detected reveal keep S0's label.

**Reveal detectors** (S_retro and S_causal each run under each): D_oracle (reveals read from the spec, upper bound); D_repo (the repository's `REVEAL_PATTERNS` only, which capture no alias, so an alias is attached only if the sentence subject is the nearest preceding deictic mention in the same sentence; if it cannot be attached, no reveal is detected); D_plus (D_repo plus two patterns written for T0 and T1: `(alias), in truth, was (Name)` and `(Alias) was none other than (Name)`).

## 4. Metrics (per mention, Wilson 95%; counts are mentions)

- **Premature**: among pre-reveal alias mentions, share linked to Y.
- **Reader accuracy**: pre-reveal alias mention correct iff unlinked; post-reveal correct iff linked to Y.
- **Omniscient accuracy**: alias mention (pre or post) linked to Y.
- **Over-commit**: alias mention linked to a person other than Y.
- Detection recall of each detector per template. Everything also by reveal distance (2, 3, 4).

## 5. Decision rules (fixed now) and meanings

- **R1 replication**: S0 has premature = 0 and omniscient accuracy = 0 (matches SIO v1: the earlier zero was vacuous). A different value means the new worlds changed the resolver's behaviour and is reported.
- **R2 sensitivity of the metric**: S_retro under D_oracle has premature = 100% of pre-reveal alias mentions and omniscient accuracy 100%, while S_causal under D_oracle has premature = 0 and reader accuracy 100%. If the metric does not separate S_retro from S_causal, the metric is declared insensitive.
- **R3 trade-off**: omniscient accuracy ordering S_retro > S_causal while reader accuracy ordering S_causal > S_retro, under D_oracle (this is the claim that a system tuned for final truth is penalised by the reader view).
- **R4 detection brittleness (not by construction)**: recall of D_repo and D_plus on T0, T1 (design) versus T2, T3 (held out), and the consequent premature and reader-accuracy values of S_retro and S_causal under those detectors. Whatever happens is reported; a large drop on held-out templates means rule-based reveal detection is brittle.
- **R5**: S_abstain has reader accuracy equal to its pre-reveal share and 0 on post-reveal; it is the "do nothing" floor and shows the metric needs both terms.

## 6. What may be claimed

Only: the metric separates these four synthetic systems (construct validity), and rule-based reveal detection does or does not generalise across four templates. **Not** claimed: that any system is faithful on real text; that D_plus is a good detector (it is fitted to T0 and T1 by design); that S_causal "solves" disclosure (it succeeds by construction under D_oracle).

## 7. Power

320 reveals, 80 per template. With 0 events in n the Wilson upper bound is about 3.7 / n x 100 percent; it cannot detect rates below roughly 1 to 4 percent per template cell.

## 8. Deviations log

None at freeze.
