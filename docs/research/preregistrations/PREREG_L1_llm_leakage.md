# Pre-registration L1: LLM leakage and evidence-gated linking (version 1)

Written and frozen **before any model call**. Repo HEAD `6c7e2c2`, 2026-10-15. Frozen artefacts and their SHA-256 are in `MANIFEST_L1.json`. A change after freezing is a new version file (`PREREG_L1_..._v2.md`, `L1_prompts_v2.json`), never an edit.

**Label provenance (applies to every number this experiment will produce).** All reference labels are **silver**: for gold-sourced items the model-drafted gold identity (`provenance: model`, `confirmed: false`); for system-sourced items (3 clan-head items, 30 plain controls) the pipeline's own link. **No human label is used.** Reveal chapters come only from repository structured data, never from a model. Results are never described as accuracy against truth, as reader-view correctness, or as human-verified.

## 1. Questions and hypotheses

- **C1a (leakage).** Given only a chapter prefix, does an LLM name the final-truth identity of an alias that the prefix does not entitle it to, and does that drop when names in the prompt are consistently renamed?
- **C1b (evidence gating).** Does requiring the model to cite prefix spans, then checking that those spans (names masked) entail the identity, remove premature naming without destroying correct links?
- **Auxiliary (premise on this corpus).** Without any passage, does the model resolve aliases of this web serial above chance, and does that vanish under renaming (a closed-book memorisation probe, T3 style)?

## 2. Differences from the owner's brief (stated up front)

1. **Primary set is 4 items, not 23.** The brief says to take reveal chapters from repo data and to drop items that have none. Applying that rule to the 23 pre-reveal candidates leaves **4**: CP-001, CP-002, CP-003 (clan head; reveal chapter 6 from the title-holder pass's alias binding) and CP-017 (reveal chapter 166 from an `observation` row; the mapping of that mention to the revealed entity rests on the silver label). The other 19 have no repo-derived reveal chapter and are **dropped from the primary set**. I examined and rejected using `alias_binding.learned_chapter` for them: those rows are re-learned at nearly every chapter where a name appears (gazetteer artefact), not reveals. Chapter references inside the gold notes are model-written and are not used. Consequence: **the primary premature-resolution comparison is inconclusive by design** (section 7). It will be reported as counts.
2. **Closed-book arm (C) uses only non-string-trivial items** (surface shares no capitalised token with any candidate name; otherwise string matching, not memory, answers). That is 15 items.
3. **Determinism.** The model's page does not mention `temperature` or `seed` (UNVERIFIED). They are not sent. Each arm runs once. The model is a reasoning model; `reasoning_effort: "none"` is requested (UNVERIFIED that it is accepted).

## 3. Data and sets (derivation code: `scripts/chimera/l1_llm_leakage.py`, sha256 in manifest)

70 entity items of the 72-item sheet (the 2 not-entity controls are excluded). Candidate list: the sheet's `candidates` column (about 11 names; same list and order in every arm; names only, ids stripped).

- **Primary P\*** = tier-P items with a repo-derived reveal chapter strictly after the cutoff chapter c and a silver truth letter present in the candidate list: **n = 4** (dry-run output `data/eval/chimera/l1_dryrun.json`).
- **Plain controls** = 30 plain-name items (silver label = pipeline's own link; circular, used only as sanity and for the renaming-validity check).
- **Other pre-reveal** = 19 items with no repo-derived reveal chapter: **exploratory, descriptive only**, never called premature.
- **Closed-book set** = 15 non-string-trivial items with a truth letter.
- 8 items have no truth letter (silver identity absent from the candidate list); they are excluded from accuracy.

## 4. Arms (same items, same candidate list; prompts in `L1_prompts_v1.json`, hashes in the manifest)

- **A.** Prefix only: the last 1,200 characters of text ending at the end of the sentence containing the mention (earlier chapters used if the chapter is shorter), original names. Nothing after the mention's sentence is shown.
- **B.** The same window with every renamed token replaced under the **T4 v3 pi** (`build_pi` in `t4_renaming.py`, seed 20261015): window, mention surface and candidate names. The renaming is applied to the prompt only, never to a resolver's normalisers. T4's resolver-normaliser commutation gate (which failed) is not what is tested here; validity is empirical (rule R1).
- **C.** Closed-book: alias + candidate list + chapter number, no passage, novel not named; original and renamed (C_orig, C_ren).
- **D.** Gated: call 1 returns an identity letter and up to two verbatim spans. A span not found verbatim in the window invalidates the answer. If the claimed identity's name tokens do not appear in the cited spans the link is **automatically rejected** (no second call). Otherwise call 2 sees only the cited spans, the surface and the claimed name with all vocabulary names masked as [Nk], and answers ENTAILED or NOT_ENTAILED. Accept only on ENTAILED; otherwise the output is UNDETERMINED.
- All arms allow the answer `UNDETERMINED`. Anything unparsable is `INVALID` and counts as a non-answer.

## 5. Metrics

- **Premature-resolution event (P\* items):** the arm's answer equals the silver final-truth letter (for D: and accepted). Rate per arm with Wilson 95% interval, plus distance = reveal chapter minus c (5, 5, 5, 32).
- **Control accuracy:** answer equals the silver label on the 30 plain controls, per arm.
- **Leakage.** A minus B on all items with a truth letter (paired bootstrap, 10,000 resamples, seed 20261016); C_orig minus chance and C_orig minus C_ren on the closed-book set.
- **Baselines.** Uniform chance = mean of 1/(candidates) over the set (about 1/11); always-most-frequent-candidate = the candidate with the most pipeline mentions in chapters up to c.
- **Gating cost:** D accuracy and abstention rate on the controls versus A.

## 6. Decision rules and what each outcome means (fixed now)

- **R1 renaming validity.** The control is *valid* only if A and B give the **same letter on at least 98% of the 30 plain controls, which with n = 30 means 30 of 30**. Otherwise it is declared **invalid** and the A-versus-B gap, and the C_orig-versus-C_ren gap, are **not interpreted**. Report the number either way.
- **R2 primary (n = 4).** Pre-declared **inconclusive** whatever the counts. Report k/4 per arm with the exact upper bound (0 of 4 gives 52.7%). No statement about C1a or C1b may be drawn from it. It is an existence check on four items.
- **R3 closed-book memorisation.** If C_orig has at least **4 of 15** correct (exact one-sided binomial p = 0.041 against p0 = 1/11) and the Wilson lower bound exceeds the chance baseline: "this model resolves aliases of this serial above chance without a passage" (premise support for one model on one serial, silver labels). If C_ren is within chance and R1 is valid, the drop is evidence of name-linked memory. Otherwise: no evidence of memorisation for this model on these items; **this narrows the claim to this model and does not kill it for larger models**.
- **R4 gating.** If, on the controls, D's accuracy is within 5 percentage points of A and D abstains on more of the four P\* items than A: "gating lowers naming without destroying correct links on this tiny set" (descriptive, not inferential). Any other pattern is reported as it is.
- **R5 nulls.** A null on any arm is reported as a null. No arm is rerun, no prompt is edited, no item is added or removed after seeing results.

## 7. Power (stated before the run)

P\*: n = 4. With 0 events the exact 95% upper bound is 52.7%; no difference between arms can be detected. Closed-book: n = 15; the smallest above-chance result that is significant is 4 correct (26.7%). Controls: n = 30 (the validity rule needs all 30). The test is therefore informative for the **renaming-validity question and the closed-book premise**, and **not** for the central premature-resolution question until human reveal chapters exist (planned follow-up L1-H: the same prompts rerun on the pre-reveal items with human `reveal_chapter` labels, which requires its own cost approval and a new version note).

## 8. Spend and safety

Model `gpt-5.6-luna` (OpenAI), prices $0.20 per 1M input and $1.20 per 1M output tokens from OpenAI's pricing and model pages fetched 2026-10-15 through a summarising tool (tag `[SUMM]`). The runner refuses to run without an explicit `--budget-usd` equal to the owner-approved amount, reads the key only from the environment and never prints it, stops before any call whose worst-case cost would exceed the budget, and stores only hashes, letters and span offsets (no prompt text, no novel text). The first call is a canary: if the API rejects a parameter the run stops at a cost of about zero. **Nothing runs until the owner replies approved with a number.**

## 9. What is sent to the provider

Prompts contain up to 1,200 characters of novel text per item (copyrighted, held locally). Sending these to an external API is an outward-facing act and is part of what the owner approves with the spend. Results files contain none of it.

## 10. Deviations log

None at freeze.
