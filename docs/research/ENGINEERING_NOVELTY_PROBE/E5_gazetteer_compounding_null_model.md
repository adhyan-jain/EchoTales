# E5. Does the gazetteer "compound"? Null model and an error-side proxy on three serials

Status: PRE-DECLARATION written 2026-10-16 BEFORE the confirmatory run. Label provenance: SYSTEM-INTERNAL (no labels) plus an ambiguity proxy.

## Claim (non-negotiable 8; architecture.md "The compounding gazetteer")
"The system gets cheaper and more accurate as it reads." EVOLUTION 4.77 measured the cheaper half on RI only: the GAZETTEER_EXACT share of
links rose 81% -> 93% over the first two 40-chapter windows then plateaued, with no null model and no accuracy-side measurement.

## Design
Per serial, resolver loop only (stored mentions fixed): per 10-chapter bucket (and per 40-chapter window) compute
(1) exact-match share of link groups and scorer-reached share (cost), with bootstrap-over-groups intervals;
(2) NULL MODEL: the exact-match share expected from repetition alone = share of groups whose normalised surface was already seen in an earlier
group, under the real order and under 20 random chapter permutations; if the real curve is not above the permuted curve at matched
vocabulary depth, "compounding" is memoisation, not a property of reading order;
(3) ERROR-SIDE PROXY: among exact-match links, the share whose normalised surface is held by >= 2 distinct entities in the final graph
(a force-link on an ambiguous surface can only be right for one of them), by depth.
## Hypotheses and falsifiers (pre-declared)
H_E5a: exact-match share rises with depth (Spearman across buckets > 0 with CI excluding 0) on every serial.
H_E5b: the real-order curve exceeds the permuted-order null by more than the permutation 95% band (i.e. narrative order matters).
H_E5c: the ambiguous-surface share of exact-match links does not increase with depth (accuracy side does not degrade).
Falsifier for the "cheaper AND more accurate" claim: H_E5a fails, or H_E5b fails (curve explained by repetition alone), or H_E5c fails.
Prior expectation: H_E5a holds on RI and fails or is weak on 40-chapter LOTM/ORV; H_E5b likely fails (repetition explains most);
H_E5c unknown. Reported either way.

---
## RESULTS (run 2026-10-16; `scripts/chimera/eng_probe_e5_gazetteer_compounding.py`; data `data/eval/chimera/eng_probe_E5_<novel>.json`)

Label provenance: SYSTEM-INTERNAL. Unit = a link group (chapter, local group), 372 to 1,603 per serial; five equal-sized bins in reading order.

| | LOTM (453 groups) | ORV (372) | RI (1,603) |
|---|---|---|---|
| GAZETTEER_EXACT share by fifth | .44 .56 .61 .75 .66 | .62 .81 .85 .91 .88 | .68 .79 .80 .76 .81 |
| scorer-reached share by fifth | .37 .27 .12 .14 .12 | .34 .18 .12 .05 .11 | .21 .14 .15 .19 .14 |
| Spearman(exact, reading position), bootstrap 95% | 0.19 [0.11, 0.29] | 0.22 [0.12, 0.33] | 0.07 [0.02, 0.12] |
| share of groups whose surface was linked earlier ("seen before") by fifth | .46 .56 .61 .79 .66 | .62 .81 .85 .91 .88 | .69 .79 .80 .76 .81 |
| exact-match groups whose surface was NOT seen before | **0 of 274** | **0 of 303** | **0 of 1,232** |
| seen-before groups that were exact matches | 274 / 279 | 303 / 303 | 1,232 / 1,238 |
| fifths where the real "seen-before" share lies outside the 200-permutation chapter-shuffle 95% band | none | none | fifth 1 (higher than null) and fifth 4 (lower) |
| exact-match links whose surface is held by >= 2 entities in the final graph | 5 of 274 (fifths 2 and 3) | 0 | 0 |

### Reading (gate-vs-engine)
- **GAZETTEER_EXACT is identical to "this normalised surface was linked before"** (zero exceptions on one side, 5 to 6 on the other, all three serials). So the "cheaper as it reads" curve is a memo-table hit rate. It rises because names repeat; H_E5a holds (positive trend on all three, weak on RI because it plateaus after the first 50 chapters, as EVOLUTION 4.77 found), but H_E5b is not supported: on LOTM and ORV the real curve is indistinguishable from the same groups with chapters shuffled, and on RI the real order is *flatter* than shuffled (higher early, lower late), i.e. reading order adds nothing and, on RI, slightly hurts after the first third.
- The accuracy side: no evidence of deterioration (H_E5c holds: ambiguity proxy 0 of 1,232 on RI, 0 of 303 on ORV, 5 of 274 on LOTM), but this proxy cannot detect a wrong link on an unambiguous surface, and there are no labels. "More accurate with depth" is untested, not supported.

### String-identity baseline (id-free, no labels)
Partition of the resolver's linked mentions versus the partition by the repo's own `comparison_key(text)`:

| | LOTM | ORV | RI |
|---|---|---|---|
| linked mentions | 2,334 | 2,262 | 11,092 |
| distinct normalised surfaces / entities | 106 / 93 | 64 / 59 | 289 / 266 |
| surfaces held by more than one entity | **1** | **0** | **0** |
| mentions in a non-dominant surface of their entity (alias-merged) | 106 (4.5%) | 63 (2.8%) | 522 (4.7%) |
| ARI vs surface-key partition | 0.985 | 0.971 | 0.971 |

So 95 to 97% of mention-to-entity assignments are exactly "same normalised string, same entity", the resolver never splits a surface across entities except 1 surface (4 of 2,334 mentions) in LOTM, and everything that is not a string lookup is the 3 to 5% of mentions that join an alias to an entity. The architecture's motivating case, "two mentions may be character-identical yet denote different people" (architecture.md Section 2), is realised 0, 0 and 1 times in the output graphs. No claim about correctness: if the serials contain homonymous characters the resolver collapses them (precision is not measured), and if they do not, the case is vacuous on these data.
