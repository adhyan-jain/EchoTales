# Pre-registration T4: renaming validity (version 5)

Written and frozen **before the v5 renamer or any v5 run exists**. Repo HEAD `6c7e2c2`, 2026-10-15. Hash in `MANIFEST_T4_v5.json`. v1 to v4 stay unedited. The owner lifted the no-v5 rule ("approved for all") after `GATE_FAILURE_DIAGNOSIS.md` showed the six v4 violations came from **asymmetric protection in the renamer** (one spelling of a token protected, another ciphered) and the seven real-word collisions from renaming only name tokens. CPU only, no model, no spend, no novel text in any output.

**This is a single attempt.** Same cipher seed (20261015), no seed search, no iteration after the gate result. **There is no v6.** If the gate fails, T4 is closed and the violation classes are reported.

## 1. pi_v5 = pi_v4 with three deterministic changes (all other v4 rules unchanged)

1. **Class-level protection.** Let `P_keys = { comparison_key(p) : p in P }` (the repo's own key, which folds case, spacing and a trailing plural `s`). Every vocabulary token `t` with `comparison_key(t)` in `P_keys` is added to `P` (so a singular is protected when its plural is, and the reverse).
2. **Piece splitting.** A letter run is split at every lower-to-upper case transition ("GuMaster" gives "Gu" and "Master"; "MoonlightGu" gives "Moonlight" and "Gu"); each piece is renamed by the v4 rule (protected pieces unchanged; others ciphered with protected substrings of 4 or more letters preserved), and the pieces are rejoined.
3. **Collision closure.** Repeat up to 10 passes: compute the renamed form of every unprotected vocabulary piece; any piece whose renamed form (casefolded) equals a lower-case token occurring in the corpus text, equals a member of `P`, or equals the renamed form of a different vocabulary piece, is added to `P`. Stop when a pass adds nothing. If it has not stabilised after 10 passes the gate fails.

## 2. Gate (all hard; run before any resolver call)

G1, G2, G3, G4 (injectivity), G5 (no real-word collision) exactly as in v4 section 2, on the same 335 surfaces and the same vocabulary. Pass only if every count is 0. The number of vocabulary tokens actually changed is reported (more protection means a weaker control; if fewer than half of the v4 changed tokens remain changed, the report says the control is weak).

## 3. If the gate passes

Runs O1, O2, I, R and the negative control N' and the decision rule are exactly as in `PREREG_T4_renaming_validity_v4.md` section 3 (which reuses v2 sections 3 and 4). N' must show a clear drop in agreement or the test is INCONCLUSIVE.

## 4. What this would and would not establish

Same as v4 section 4: invariance of the deterministic resolver to this renaming on this novel; it does not show an LLM is unaffected.

## 5. Deviations log

None at freeze.
