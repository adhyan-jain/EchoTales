# Pre-registration: a synthetic volume with exactly known truth

Written 2026-10-16 **before the generator or any result exists**. Status: NOT RUN. Label provenance: SYNTHETIC, ground truth set by construction (no annotator, no model call, $0).

## What this can and cannot show

It can: (1) test, on a system where the true gender and the reader-visible evidence are known exactly, that the stamp-versus-evidence leak is produced by the mechanism the audit names and removed by the horizon repair (annotator-free, so it cannot be circular with the labels of `PREREG_LABELS.md`); (2) map where the anchored cue fails (how misleading pronouns degrade its precision), which the real data covers with a single failure; (3) show how the safety/availability trade-off moves with the evidence density. It cannot: show that any of this holds on real text. The generator writes the own-pronoun cue exactly where the anchored cue looks for it, so a high recovered fraction at the base configuration is partly true by construction; the informative part is the failure map and the independence from annotators, not the headline number. Reported that way.

## Generator (fixed now)

Per seed: 40 chapters, 80 characters, gender i.i.d. 50/50, first chapter uniform on 1..28, active from then on. Each chapter, each active character appears with probability 0.6, with `1 + Poisson(0.7)` paragraphs in which it is the subject of the first sentence. A paragraph has 1 to 3 further sentences (each with probability 0.5 per slot) whose subject is another random active character (that is a mention of it too), so a paragraph carries other characters' pronouns, the noise the paragraph rule's floor of 6 exists to absorb. Every sentence starts with the character's unique invented name (the only capitalised word in it) and carries one of: an **own cue** (probability `p_anchor`; a pronoun of the subject's true gender, as ", her cloak trailing" or " and she left"), a **misleading cue** (probability `p_adv`; a pronoun of a random gender about an unnamed third party, as " beside the stranger, his coat dripping" or " beside the stranger and he frowned"), or nothing. Each paragraph is one block and one narration span.

Reference reader (annotator-free): a character is *determinable* at cut `k` if any own-cue sentence for it lies in a chapter at or before `k`. Cuts: 4, 8, 12, 16, 20, 28.

## Configurations and builds

Base: `p_anchor = 0.35`, `p_adv = 0.05`. Sweep: `p_anchor` in {0.10, 0.35, 0.70} times `p_adv` in {0, 0.05, 0.15} (nine configurations including the base), 5 seeds each. Builds compared at every cut, each as a full build against a build over the truncated volume with the same extractor: status quo (single first-sighting stamp), plain horizon repair, horizon repair with the anchored cue at `(min_obs, majority) = (1, 0.8)` (the setting chosen on the real data, not tuned here; `(2, 0.8)` and `(1, 1.0)` also reported).

## Hypotheses (declared now)

- **S1 mechanism.** At the base configuration the status quo has stamp divergence above 0 and premature disclosures above 0 (its served value known where the character is not yet determinable), while the plain repair and the anchored repair have divergence exactly 0. Falsified by a non-zero divergence for either repair (that would be a bug in the repair, reported as such) or by no divergence at all for the status quo (then the real-data defect has some other cause).
- **S2 cue.** At the base configuration the anchored repair recovers at least 50% of the correct values the plain repair loses relative to the status quo, with a wrong-value rate at or below 3.0%.
- **S3 failure map.** Report, for each configuration, the wrong-value rate of the anchored repair, and name the configurations where it exceeds 3.0%. No pass or fail.

## Limits declared now

Synthetic English with invented names; one gender attribute; the generator's cue structure is the cue's own assumption (see above); co-mention noise is modelled by other characters' sentences only, not by titles, kinship terms or pronouns for groups; 5 seeds per configuration, so intervals are across seeds, not across novels.
