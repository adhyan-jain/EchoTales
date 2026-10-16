# Pre-registration L2U: unseen-text control for the renaming gap (version 1)

Written and frozen **before the L2U runner exists and before any L2U model call**. Repo HEAD `6c7e2c2`, 2026-10-15. Hashes in `MANIFEST_L2U.json`. L1 results are unchanged and are the "real text" side of the comparison.

**Label provenance.** Synthetic items: labels by construction from the world spec (no model, no human). The L1 comparison side is silver (model-drafted gold; the pipeline's own link). Nothing here is human-verified.

## 1. Question

L1 found that accuracy against the silver label is 9.7 points higher with original names than with renamed names (A minus B, 62 items, CI [3.2, 17.7]). The renaming gap could be **memory of the novel** (leakage) or **damage from renaming** (distraction, unusual tokens, information loss). On **synthetic text with invented names, no memory is possible**, so an A-minus-B gap there measures renaming damage alone. The difference-in-differences (real gap minus synthetic gap) is the part attributable to memory, if any.

## 2. Items (frozen rule)

From the 40 SIO v1 worlds (`sio_synthetic_oracle.make_world`, template T0 with the reveal sentence, no new generator; the M3 generator's T0 is identical), 62 items, one mention per world, chosen by position rule, no outcome seen:
- 21 **pre-reveal alias** items: the first pre-reveal alias mention of world seeds 0 to 20; correct answer `UNDETERMINED`.
- 21 **post-reveal alias** items: the alias mention in the chapter after the reveal chapter, worlds 0 to 20; correct answer the revealed identity (derivable from the reveal sentence inside the prefix window).
- 20 **plain named** items: a PRESENT named mention in chapter 5 or later of worlds 20 to 39; correct answer that name.
Candidate list for each item: the six character names of the world plus two unused invented names, order fixed by a seeded shuffle (seed 20261017 plus item index), the same list and order in both arms (names only).

## 3. Arms and prompts

Arm A (original names) and arm B (renamed) use the frozen L1 prefix template (`A_B_prefix` in `L1_prompts_v1.json`, hash in `MANIFEST_L1.json`), a window of at most 1,200 characters ending at the end of the mention's sentence (earlier chapters used when the chapter is shorter; prefix only), model `gpt-5.6-luna`, `reasoning_effort: none`, token cap 150, one run per arm, no temperature or seed. **Renaming for B:** the T4 v5 letter cipher (same seed, same fixed letters `s`, `u`, `i`, same protected word set taken from the real-novel build) applied to every name token in the window, the surface and the candidate names (the aliases such as "the masked guest" are not names and are unchanged).

## 4. Metrics and decision rules (fixed now)

- **U1 renaming validity on synthetic controls:** A and B give the same letter on all 20 plain named items.
- **Synthetic gap** `g_s`: accuracy against the construction truth, A minus B, over the 62 items (pre-reveal items are correct only if the answer is `UNDETERMINED`), with a 95% bootstrap interval (10,000 resamples, seed 20261016); also reported by item type.
- **Difference-in-differences** `D = g_r - g_s` where `g_r = +9.7` points is the L1 real-text gap; the 95% interval of `D` is from independent bootstrap resampling of the two item sets.
- **Readings fixed now.** (a) If `g_s >= +4.8` points (half the real gap) and the interval of `D` includes 0: **the real gap is consistent with renaming damage**; leakage is not supported. (b) If `g_s <= +2` points and the lower bound of the interval of `D` is above 0: **a residual gap on real text beyond renaming damage** (consistent with memory; still silver labels, one model). (c) Otherwise: **inconclusive**.
- **Ceiling guard:** if accuracy in both arms on the synthetic items is at least 95%, the synthetic set is too easy to detect damage of the kind that may occur on hard real items; reading (b) is then reported with that caveat and the result is labelled "weakly informative".

## 5. Power

n = 62 per arm on each side; with accuracy near 95% a gap smaller than about 5 points cannot be distinguished from 0; the interval for `D` will be wide (roughly the real-gap interval plus the synthetic one).

## 6. Spend and safety

Estimated about $0.013 expected and $0.04 worst case (dry-run output `data/eval/chimera/l2u_dryrun.json`); the owner's cumulative cap for the research budget is $0.10 and the running total before this run is $0.0376. The runner needs an explicit `--budget-usd`, reads the key only from the environment, never prints it, stops before any call whose worst case would exceed the budget, and stores letters and counts only. No novel text is involved (synthetic names and text).

## 7. Deviations log

None at freeze.
