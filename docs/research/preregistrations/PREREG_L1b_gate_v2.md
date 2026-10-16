# Pre-registration L1b: evidence gate v2 (M1), version 1

Written and frozen **before any L1b model call and before the L1b runner exists**. Repo HEAD `6c7e2c2`, 2026-10-15. Hashes in `MANIFEST_L1b.json`. L1 v1 (`PREREG_L1_llm_leakage.md`) and its results are unchanged and are reported unchanged; this is a new version, not an edit.

**Label provenance (every number).** Reference labels are **silver** (model-drafted gold; the pipeline's own link for system-sourced items). Reveal chapters come only from repository structured data. No human label is used.

## 1. Why v2, and what the designer has already seen

v1 of the gate over-rejected: control accuracy fell from 29/30 (ungated, arm A) to 14/30 (gated, arm D). **The designer has already seen all v1 outcomes for all 72 items**, including aggregate failure categories on the controls (cited spans that were not verbatim substrings; plain-name claims judged not entailed although the mention itself names the candidate; the name-absence auto-reject firing on such claims). The dev/test split below therefore **cannot be blind to those categories**. The v2 changes are generic rules derived from the failure *categories*, written without looking at any individual item's v1 span or entailment text, and no rule is tuned after the v2 run. This limitation is reported with every v2 number.

## 2. Gate v2 (the only changes from v1)

1. **Prompt D1 v2** (`L1_prompts_v2.json`): asks for spans copied character for character and for UNDETERMINED when no exact quote supports the answer. D2 is byte-identical to v1.
2. **Tolerant span check**: a cited span is valid if, after collapsing whitespace, unifying curly and straight quotes and casefolding, it is a substring of the equally normalised window. The v1 exact-substring test is replaced by this.
3. **Surface-identity rule**: if the chosen candidate's name shares a capitalised token (not a determiner such as "The", "A", "An") with the expression of interest itself, the link is accepted without the second call (the name is in the mention the reader sees). Logged as `surface_identity`.
4. **Kept from v1**: the name-absence auto-reject (a claimed name not occurring in the cited spans is rejected, unless rule 3 applies), the masked entailment call, abstention as UNDETERMINED.

The candidate lists, windows (1,200 characters, prefix only), model (`gpt-5.6-luna`), token caps and `reasoning_effort: none` are those of L1. Temperature and seed are not sent. Each item is run once.

## 3. Items and split

The 70 entity items of the pilot sheet (as L1). Split by hash, fixed now: an item is `dev` if `int(sha256("L1v2-split-20261016-" + item_id)) mod 2 == 0`, otherwise `test` (33 dev, 37 test; all four primary items CP-001, CP-002, CP-003, CP-017 are in test). Because the rules are generic and fixed, the model is run on **all 70 items once**; the **primary evaluation is the test split**, with dev and all-items reported separately and labelled. The v1 A and B outputs for the same items are reused (not rerun) as the ungated comparison.

## 4. Metrics

On the plain controls (test split n = 16; all 30 reported): accuracy of the gated output against silver, ungated A, always-most-frequent-candidate, and the share accepted by `surface_identity` vs entailed vs rejected. On the four primary items: how many gated outputs name the silver final identity, and how many are accepted. Gate-path counts. Wilson 95% intervals.

## 5. Decision rules (fixed now)

- **P1 (keeps correct links):** on the test-split controls, gated accuracy is within 5 percentage points of ungated A, i.e. loses at most 1 of 16 relative to A.
- **P2 (still blocks premature naming):** on the four primary items, at most 1 is accepted as the silver final identity (v1 accepted 0 of 4 under the same gate logic; the clan-head claims fail the name-absence rule because the revealed name is not in the prefix).
- **Pass** = P1 and P2: "a gate that keeps correct links and blocks the not-entailed premature ones on this small set". **Fail** otherwise, reported as a fail.
- **Interpretation guard:** because rule 3 accepts plain-name controls by string identity, passing P1 shows only that the gate no longer rejects trivial correct links; it is not evidence that the entailment check is sound. The entailment path is evaluated by its own count (items accepted via the entailed path and, among them, matches to silver). Any pass is on silver labels, one model, n small.

## 6. Power

Test-split controls n = 16: one-item resolution is 6.3 points; P1 cannot detect smaller losses. Primary items n = 4. The result is descriptive.

## 7. Spend and safety

Expected cost about $0.01 at the L1 rates; the runner takes an explicit `--budget-usd` and stops before any call whose worst case would exceed it; the key is read only from the environment and never printed. **Nothing runs until the owner approves an amount.** The run sends up to 1,200 characters of novel text per item to the provider (outward-facing; the owner approves it with the spend).

## 8. Deviations log

None at freeze.
