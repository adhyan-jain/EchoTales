# Pre-registration: an anchored-pronoun cue under the evidence horizon

Written 2026-10-16 **before the cue is implemented and before any result with it exists**. Status: NOT RUN. Labels: MODEL-GENERATED (two annotators, `PREREG_LABELS.md`), no human labels.

## Why

REPORT 4.10 found that the horizon-honest repair (a persona stage that serves, at each cut, exactly what a prefix-only build holds) is safe but withholds about 1 to 4 values the text already supported per premature disclosure it removes. The cause (REPORT 4.9, gate-versus-engine) is not the horizon rule: the gender extractor needs at least 6 third-person pronouns in the whole narration paragraph around every mention (`_PRONOUN_MIN = 6`, 70% majority), and an early prefix often does not reach 6, while a reader sees "Alger Wilson stood on deck, **his** body..." in one sentence. This pre-registration tests whether a stronger cue, used only when the existing rule says `unknown`, recovers most of the lost availability without adding wrong values. If it does, the contribution becomes a method with a measured safety/availability frontier, not only an audit.

## The cue (fixed now, not tuned)

For each mention of the character in the evidence chapters (the same first-12-attested-chapter, up-to-the-cut window as the existing evidence): take the text after the mention inside the same narration or inner-monologue span; cut at the first sentence terminator (`.`, `!`, `?`, a closing quote) or after 160 characters, whichever is first, and cut earlier at the first capitalised word other than "I" (another name intervenes). The first third-person pronoun in what is left (he, him, his, himself, she, her, hers, herself) is one observation for that mention. At most one observation per mention.

Decision: with `n` anchored observations of which a share `s` agree on one gender, call that gender when `n >= min_obs` and `s >= majority`. Used **only** when the existing pronoun rule returns no gender; it outranks the honorific table exactly as the existing pronoun rule does (a pronoun is stronger evidence than a title). Off by default (`anchored_gender=False`); the default path stays byte-identical, which is re-checked by hash.

## Grid and selection (declared now)

Six settings: `min_obs` in {1, 2, 3} times `majority` in {0.8, 1.0}. Selection is leave-one-serial-out so no setting is chosen on the data it is scored on: for each held-out serial, among the six settings choose the one with the highest correct share on the **other two** serials subject to a wrong-value rate of at most 3.0% there (the status quo is 2.0%); apply it to the held-out serial; report the three held-out results pooled. All six settings are also reported on all data, labelled in-sample, as the frontier.

## Hypothesis and success rule (declared now)

**H5.** The horizon repair with the anchored cue (a) has 0 stamp-divergence on every cut (by construction; any non-zero is a bug and is reported as such); (b) recovers at least 50% of the correct values the plain horizon repair loses relative to the status quo, where recovered = (correct_new - correct_plain) / (correct_status_quo - correct_plain), on the cuts where the combined reference label (T*) is male or female; and (c) keeps the wrong-value rate at or below 3.0%. H5 is supported only if all three hold on the held-out pooled result. If (b) holds but (c) fails the result is reported as a trade-off, not a success.

Also reported, not thresholded: over-reading (the build serves a known gender where the second annotator's prefix label is undetermined) on the exposed pairs that carry that label, per setting; and the unknown share served by each build.

## What would count against it

If the anchored cue recovers little (under 50%), the over-conservatism comes from evidence the text states in other ways (titles, kinship, the narrator's naming), not from the pronoun floor, and the repair stays as it is in 4.10. If it recovers a lot but its wrong rate exceeds 3%, then the status-quo extractor's floor of 6 was doing real error-absorbing work and the frontier is the finding.

## Addendum 1 (2026-10-16, written BEFORE the v2 code and before any v2 result): a v2 window after PD3 failed

**What happened.** On the two English originals (`PREREG_PD.md`) the cue's precision on the values it added was 8 of 11 (`(1, 0.8)`), against 34 of 35 on the web novels, and PD3's absolute 3% bar failed (REPORT 4.14). Reading the windows behind the one cue-caused error (Milady) showed two patterns: a pronoun that follows an unnamed third party ("Milady, seeing **the stranger** lay his hand on his sword") and a pronoun after a clause boundary ("Milady; he cast a passing glance"). Both are what the synthetic failure map predicted (REPORT 4.13).

**v2 (fixed now, not tuned).** The v1 window (after the mention, to the sentence end, 160 characters, or the next capitalised word other than "I") is additionally cut (a) at the first `;`, `:` or dash (`--`, an em dash) and (b) before the first occurrence of a determiner (`the`, `a`, `an`) followed by one of these role nouns: stranger, man, woman, young man, young woman, officer, gentleman, lady, girl, boy, fellow, maid, servant, soldier. Nothing else changes; the cue is still used only when the paragraph rule says `unknown`; setting names `(min_obs, majority, "v2")`; off by default; the default path stays byte-identical.

**Data roles (declared now).** The English originals are a **development set**: the failure was diagnosed on them, so their v2 numbers are reported but are not evidence. The **confirmatory** data are the three web-novel serials (never looked at for this change), with the labels of `PREREG_LABELS.md`, the same 24 cuts and the same settings `(1, 0.8)` and `(2, 0.8)`.

**Hypothesis H6 (declared now).** On the web novels, v2 at each setting (a) keeps stamp divergence at exactly 0; (b) has a correct share within 2 points of v1's at the same setting; and (c) has no more wrong values than v1 at the same setting. All three must hold. If (b) fails, the v2 cuts discard real own cues and v1 stays the recommended window. Reported, not thresholded: the English originals' wrong counts under v2.

## Limits declared now

Labels are model-generated, one reference per character (T*) with 31% unknown, so the test runs on about 67 characters; the three serials are the same ones the defect was found on (no independent system); the extractor is English-translation-specific; the grid is small and the 160-character and name-interruption rules are fixed by design choice, not tuned.
