# Pre-registration: model-generated labels for the prefix audit

Written 2026-10-16 **before any passage was read for labelling**. The sheets exist (`data/eval/prefix_audit/labels/sheet_*.txt`); no label does. The owner cannot provide human annotation before the deadline and told me to generate labels myself.

## Provenance, stated up front

**MODEL-GENERATED, single annotator (Claude, this session), no human review.** This is weaker than human gold: it shares failure modes with the system under test (both are language models reading translated prose), the annotator is one rater (no inter-annotator agreement), and passages are samples. Every result below that uses these labels is tagged `LABELS: MODEL-GENERATED`. A human spot-check sheet is prepared for the weekend (see "Human check") so the claim can be upgraded or retracted afterwards.

## Two labels

1. **Truth** (`labels/truth_<novel>.json`): one label per character (117), from passages spread over the character's whole chapter range: `male | female | unknown | non-person`, plus `confidence` in {high, medium, low}. `unknown` means the passages do not determine it, and is never guessed.
2. **Prefix** (`labels/prefix.json`): for 46 (character, cut) items, from passages up to the cut only: `male | female | undetermined`. The items are all 23 diverging gender cuts plus 23 non-diverging exposed cuts drawn at random, shuffled, with the diverge flag hidden on the sheet and kept in `prefix_key.json`.

## Blinding and anti-circularity rules

- Sheets print name, aliases and passages only. They contain **no value the system served** (full or prefix build, either stage). I will not open the audit rows for these characters before all labels are written to disk.
- Passages are sampled evenly over the character's chapters, not selected for pronouns, so the sheets do not inherit the deterministic extractor's heuristic. A low-confidence or `unknown` label is the correct output when the sample is not enough; I will not search outside the sheet to resolve it, so a label can be `unknown` where more text would settle it. That biases scores toward "system wrong or leaking" in no direction in particular, and is stated as a limit.
- Labels are written once and frozen (file hash recorded in the report). Disagreements found later are reported, not edited away.

## What will be computed (declared now)

Let T be the truth label, P the prefix label, S_full the status-quo served value at cut k, S_pre the value a prefix-only build serves, S_rep the value served with the repair on.

- **A. Justification of the leak.** Among the 23 diverging cuts: how many have P = undetermined (the text up to k does not settle it, yet the status quo served a value: a *premature disclosure*) versus P = the served value (the value was already derivable, so the stamp was early but the information was not a spoiler) versus P ≠ served value.
- **B. Correctness.** For S_full, S_pre and S_rep at the exposed cuts: share equal to T, share `unknown` (withheld), share wrong (a known value that differs from T, with T in male/female). Reported with Wilson 95% intervals. Cuts where T is `unknown` or `non-person` are excluded from "wrong" and counted separately.
- **C. Does the repair buy correctness or only safety?** Compare wrong-rate of S_full and S_rep. Declared expectation: the repair mostly trades correct-but-premature values for `unknown`, so it changes wrong-rate little and raises withheld-rate; if instead S_full is wrong more often than S_rep, that is a corruption finding, not only a spoiler finding. Either outcome is reported.
- **D. Label sanity.** The share of the 117 truth labels that are `unknown`, and the agreement between P and T on cuts late enough to show the whole range (reported, as a check that the labeller is not drifting between the two sheets).

## Falsifiers and limits

- If more than 25% of truth labels are `unknown`, B and C are reported on the labelled subset only and flagged as under-powered.
- If P disagrees with T on cuts where the passages already show the full chapter range, the labelling is unreliable and the labelled results are withdrawn.
- 23 diverging cuts come from about a dozen characters and are not independent. Intervals are reported per cut and per character.
- One annotator, one model family: this cannot establish ground truth, only check the audit against an independent reader.

## Record of what happened (2026-10-16, after scoring)

- **Frozen:** `labels/LABELS.sha256` was written after the last label file and before any audit value was opened; `score_labels.py` refuses to run if a label file changed.
- **Deviation 1 (declared before scoring, after reading both sheets):** the prefix label uses any passage at or before the cut from either sheet, not only the sampled ones (the text up to a cut is all of it; Melissa's ch3 line is in the text up to cut 10 whichever sheet shows it). This was the right reading of "what the text up to the cut determines", but it was decided after seeing the sheets, so it is a deviation from the order stated above.
- **Deviation 2:** the repair-on audit files predated the stored served values, so `audit.py --repair on` was rerun for the three serials (CPU only, $0). It reproduced the earlier flags exactly (0 gender divergences; 2, 0 and 5 non-gender rows).
- **Falsifier fired:** 40 of 117 truth labels (34.2%) are `unknown` or `non-person`, above the 25% limit. B and C are therefore reported on the labelled subset (118 exposed cuts, 53 characters) and flagged as under-powered, as declared.
- **Label sanity (D):** 0 clashes between a prefix label and the truth label of the same character.
- Results and their limits are in `REPORT.md` section 4.9.

## Addendum 2 (2026-10-16, written BEFORE any Luna call): second annotator, uniform protocol, more cuts

The owner supplied an OpenAI key and told me to use Luna (`gpt-5.6-luna`, the project's reference comparator) to label the `unknown` characters and to fix the other two limits of 4.9. I read "the other two" as: (a) the post-hoc rule and sampled passages behind my prefix labels (Deviation 1), and (b) the very small number of premature-disclosure cases. Limit (c), one annotator, is addressed as a by-product. Limit (d), independence, cannot be fixed without a fourth serial and is not claimed fixed.

**Annotator 2 and protocol (fixed now).** `gpt-5.6-luna`, `reasoning_effort: none`, one call per item, no repeats, `max_completion_tokens` 120, OpenAI chat completions. One fixed prompt (hash recorded in the output) for every item: the passages are shown with their chapter numbers; the model must use only those passages and must return JSON `{"gender": male|female|undetermined|non-person, "passage": <number>, "quote": <verbatim words, at most 15>}`. Accepted cues: a gendered pronoun that refers to the character, a gendered title or kinship term (Mr, Lady, uncle, granddaughter), or an explicit statement. Passages: up to 24 per item, chosen by evenly spaced chapters among those that mention the character (first mention in each chosen chapter), not selected for pronouns, 150 characters before and 350 after the mention. No outside knowledge is allowed in the prompt; to catch it anyway, a male/female answer whose quote is not found verbatim (whitespace and case normalised) in the cited passage is recorded as `unverified` and counts as `undetermined`.

**Items.**
- Truth: all 117 characters, with passages from their whole chapter range.
- Prefix: every *exposed* (character, cut) pair, at the 13 original cuts (139 pairs) and at 11 added cuts (LOTM 15, 25, 35; ORV 15, 25, 35; RI 30, 60, 100, 140, 160), with passages up to the cut only. Only exposed pairs are labelled because H1 found no divergence outside the exposure window. Added cuts are written to separate files (`audit_dense-*`) and do not touch the original results; they add cut positions, not independent characters.

**Reference labels (declared now).**
- T*: male/female if at least one annotator has a verified male/female label and the other does not give the opposite; `disputed` if they give opposite labels (excluded from correctness, counted); otherwise `unknown`/`non-person`.
- P* (what the text up to the cut determines): Luna's label is primary for **every** exposed pair, because it is one uniform protocol with no post-hoc rule (this replaces Deviation 1 as the basis of the headline). My 46 labels are a cross-check; agreement is reported as Cohen's kappa and raw agreement, with the caveat that the two annotators saw different passage sets.
- Sensitivity: the headline rates are also reported with my labels only and with Luna's only, so the choice of reference cannot decide the verdict.

**Metrics (declared now).** (A') over all exposed pairs: the share that are premature disclosures (status quo serves a known value, the prefix-only build does not, P* undetermined), with Wilson 95% and a count of distinct characters; plus the shares justified-by-text and reverse, separately for the original and the added cuts. (B') correctness of the three builds against T* on pairs where T* is male/female, and the new unknown share of T*. (D') kappa on the 117 truth labels and on the 46 prefix labels.

**Addendum 2a (written after a 3-call smoke test, $0.00055, before the full run).** The smoke test showed that the strict verbatim rule rejects a correct, near-verbatim quote that only appended a stray word ("...mine...he"). The primary verification is therefore: at least 80% of the quote's words appear, in order, in the cited passage (copying from the provided text is still required). The strict substring result is stored as `verified_strict` and reported as a sensitivity analysis. The 3 smoke records are discarded and rerun. This is a change to the verification rule made after seeing three outputs; it does not look at any outcome of interest, and it is recorded here rather than silently applied.

**Falsifiers.** If Luna's label contradicts mine (male vs female) on more than 5% of the commonly labelled characters, the labelling procedure is unreliable and I report both sets without a reference. If more than 25% of T* is still `unknown`, B' stays flagged under-powered.

**Budget.** Prices $0.20 per million input tokens and $1.20 per million output tokens (the earlier Luna scripts). The script prints an exact estimate before any call, takes a hard `--budget-usd`, stops before any call that could exceed it, and reads the key from the environment file in-process without printing it. I will use a cap of 1.5 times the printed expected cost and will not exceed $0.30 in total; if the estimate is higher I shrink the scope instead. Earlier spend on this project (CHIMERA session) is $0.2824 and is separate. Passages (short, from the three source novels) are sent to the API under the owner's explicit instruction; nothing else is sent, and the owner's email is not.

## Record of Addendum 2 (2026-10-16, after the run)

- **Run once, as declared:** 419 calls (142 truth, 277 prefix), `gpt-5.6-luna`, prompt hash `b3986b1ada7ecf1d`, $0.0524 spent against the $0.075 estimate and a $0.12 cap (CHIMERA-session spend of $0.2824 is separate; project total about $0.335). `luna_labels.jsonl` sha256 is recorded in `labels_summary_v2.json`. The 3-call smoke test was discarded and rerun after Addendum 2a.
- **Falsifiers:** male-versus-female contradictions 0 of 61 (limit 5%): passed. Unknown share of T* 31.0%: above 25%, so correctness stays flagged as a subset result.
- **Deviation from the declared order:** none beyond Addendum 2a. The added cuts were audited before the estimate (CPU only), which the addendum describes.
- Results: `REPORT.md` section 4.10. The two annotators are nested (all 5 of my premature cases are among Luna's 10 on the original cuts), so the premature rate is reported as a range, not a point.

## Addendum 3 (2026-10-16, written BEFORE the call): a permissive reading by the same model

The owner granted an extra $0.20 with no approval step. The weakest point of REPORT 4.10 is that the premature-disclosure rate is bracketed from one side by a model (Luna's strict prompt) and from the other by me. This addendum brackets it from the permissive side with Luna too, so the range no longer depends on my labels.

- **Same model, same passages, same JSON and the same 80% quote check; only the instruction changes.** The strict sentence "Accepted evidence: ... If the passages do not support an answer, say undetermined." is replaced by "Answer male or female whenever a reasonable reader would infer it from any passage: a single gendered pronoun, title, kinship term, form of address or description is enough. Answer undetermined only if no passage points either way." Prompt hash recorded.
- **Items:** the 277 prefix pairs (exposed (character, cut) pairs of the 24 cuts), not the truth labels. Output `labels/luna_labels_permissive.jsonl`.
- **Budget:** the strict run cost $0.0524 for 419 calls, so 277 calls are expected near $0.035. Hard cap $0.06 for this step.
- **Declared output:** premature-disclosure rate and the justified/premature split of the diverging pairs under the permissive reading, next to strict-Luna and mine. The report states the resulting range with the three readers. Nothing is thresholded; if the permissive reading calls (almost) every diverging pair justified, then the premature rate approaches the zero bound and the spoiler claim shrinks to the lower end of the range, which is reported as such.

## Human check (weekend, not required for today)

`labels/human_check.csv` will list 30 characters sampled at random with a blank column for a human label and no model label shown; agreement with the model label will be added to the report when done. Until then the labelled results stay tagged MODEL-GENERATED.
