# Pre-registration T4: renaming validity (version 4)

Written and frozen **before the v4 renamer or any v4 run exists**. Repo HEAD `6c7e2c2`, 2026-10-15. Hash in `MANIFEST_T4_v4.json`. v1, v2 and v3 stay unedited. Reopened by the owner ("see as you see fit, we need the best results") after the gate-versus-engine diagnosis (`GATE_FAILURE_DIAGNOSIS.md`), which attributed all 11 v3 gate violations to the repo's character-level normaliser merging spacing, case and plural variants, not to a bug in the gate. CPU only, no model, no spend, no novel text in any output.

**This is a single attempt.** One cipher seed (20261015, as before), no seed search, no iteration after the gate result. If the gate fails, T4 is closed for good and the violation classes are reported.

## 0. Why a letter cipher

`comparison_key` casefolds, removes all spacing and punctuation, removes a trailing possessive, folds a trailing plural `s` (when the string is longer than 4 characters and does not end in `ss`, `us` or `is`), and strips honorifics. A **length-preserving, case-preserving, letter-for-letter substitution that fixes `s`, `u` and `i`** commutes with every one of these operations on name surfaces. The token-level renamer of v3 could not, because a spacing variant ("Gu Master" vs "GuMaster") changes where the token boundaries fall.

## 1. pi_v4 (frozen)

1. **Cipher.** A permutation sigma of the 23 letters other than `s`, `u`, `i`, drawn with `random.Random(20261015)` from the sorted list of those letters; `s`, `u`, `i` map to themselves; upper and lower case map consistently; non-letters are unchanged.
2. **Sets** (taken from the v3 build, unchanged): `P` = protected lower-case words (titles, roles, kinship, the ambiguity blocklist, stop words, honorific words and articles) plus common lower-case words (5 or more standalone lower-case occurrences); `L` = the casefolded capitalised name tokens drawn from entity labels, aliases and mention texts (v3 vocabulary). `Q` = the words of `P` with at least 4 letters.
3. **Renaming a letter run** `w` (maximal `[A-Za-z]+`): if `w.casefold()` is in `P`, or not in `L`, or is a pronoun, leave it unchanged. Otherwise scan `w` left to right for the longest case-insensitive occurrences of words of `Q`, non-overlapping, and leave those substrings unchanged; apply sigma to every other letter. Lower-case, upper-case and mixed-case forms of a name token are renamed alike (casefold membership).
4. Offsets do not change (length-preserving), so no offset map is needed (the identity map is used where the runner expects one).
5. Not an exact inverse in general (preserved substrings), so the v1 round-trip property is replaced by G4 below.

## 2. Gate (all hard; run before any resolver call)

- **G1, G2, G3**: exactly as in v2/v3 (display-label commutation, comparison-key class bijection, whole-token containment) on the real vocabulary surfaces.
- **G4 injectivity**: distinct casefolded members of `L` map to distinct renamed strings.
- **G5 no real-word collision**: no renamed member of `L` equals (casefolded) a lower-case token that already occurs in the corpus text or a member of `P`.
- The gate passes only if every violation count is 0. **There is no revision after a failure.** A failure is reported with the violation classes (engine / renamer / gate, by the diagnosis script's rules).

## 3. If the gate passes: runs and decision (as v2 section 4, with one substitution)

Conditions O1 (original), O2 (original again, determinism), I (identity renaming), R (pi_v4), and N' (negative control: pi_v4 except that every run whose casefold contains "yuan" is renamed with a **second, independent** permutation, which breaks containment and family structure on purpose; replaces v3's N). Per-mention agreement by label under pi, the classification of changed mentions, Wilson intervals and the PASS/FAIL/INCONCLUSIVE rule are exactly those of v2 section 4 and 3. N' must show a clear drop in agreement (the v2 rule for the negative control) or the whole test is INCONCLUSIVE (insensitive).

## 4. What this would and would not establish

If PASS: the repository's deterministic resolver is invariant to this renaming on this novel, i.e. the renaming control does not damage what the engine reads; that licences a renaming control **for the engine**. It does not show an LLM is unaffected (that needs an empirical check such as L1's R1 and the unseen-text control). If the gate fails again: report violation classes; no v5.

## 5. Deviations log

None at freeze.
