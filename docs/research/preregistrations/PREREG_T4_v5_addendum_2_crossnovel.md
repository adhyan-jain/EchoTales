# Addendum 2 to PREREG_T4_renaming_validity_v5.md: the frozen v5 rules applied to two more serials

Written and frozen **before the cross-novel script exists or runs**. Repo HEAD `6c7e2c2` (working tree on branch `chimera/system-adapters`), 2026-10-16. Hash in `MANIFEST_T4_v5.json` (key `addendum_2_sha256`). The frozen v5 prereg and addendum 1 are unchanged. CPU only, no model, no spend, no novel text in any output.

## 1. Question

The v5 letter-cipher renamer was validated on one novel (RI). Is the commutation-gate result a property of the design or of that novel's vocabulary? And is the earlier failure of a naive token-level renamer (the v3 design) general?

## 2. Scope and rules (nothing new is designed)

- Novels: `lord-of-the-mysteries` (LOTM) and `omniscient-readers-viewpoint` (ORV), local databases, **scratch copies only**. Both databases hold **40 chapters** (partial volumes), which is stated wherever a number is reported.
- The renamers are built exactly as in v5 (same seed 20261015, same code, same protected-word sources, same 10-pass closure) from each novel's own vocabulary. The v3 token-level renamer (`t4_renaming.build_pi`) is built the same way from the same vocabulary and run through the same gate.
- **Gate:** G1 to G5 exactly as in v5. **If the gate fails for a novel there is no resolver run for it** and the violation classes are reported. Single attempt per novel, no iteration, no seed search.
- If the gate passes: conditions O1 (original), O2 (original again), I (identity renaming), R (v5 renaming) on the current code with a fresh `resolve_novel` on each scratch copy, with the v2 comparison and classification. **The negative control N is not run**: the pre-registered N is specific to RI ("Fang Yuan" and "Yuan") and has no registered analogue for these novels; defining one now would still be a new design choice. So the T4 verdict for these novels is **partial**: the v2 rule requires N below R, and without N the verdict is reported as "gate passed, O2 = I = 100%, R agreement X, N not run: not a full PASS".

## 3. What may be claimed

If the v5 gate passes on both novels and the v3 design fails on both: "the failure of token-level renaming against a character-level normaliser, and the validity of a class-protected letter cipher, replicate across three serials at the gate level". Not claimed: that the renaming control is validated for any LLM; a full T4 PASS on LOTM or ORV (no N).

## 4. Deviations log

None at freeze.
