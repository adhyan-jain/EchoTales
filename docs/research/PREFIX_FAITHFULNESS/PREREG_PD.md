# Pre-registration: a second text domain (public-domain English originals)

Written 2026-10-16 **before the volumes are built and before any result exists**. Status: NOT RUN. Labels: MODEL-GENERATED (one annotator, `gpt-5.6-luna`, strict prompt of `PREREG_LABELS.md` Addendum 2); no human labels.

## Why

Every real result so far comes from three translated web novels, so "one system, three serials" also means one translation idiom. The project holds public-domain Gutenberg texts locally (CHIMERA's benchmark). Two third-person English originals, *Oliver Twist* (pg730, 53 chapters) and *The Three Musketeers* (pg1257, 67 chapters), give a different narration style, genre and register through the same persona stage. This tests whether the stamp-versus-evidence defect, the horizon repair and the anchored cue reproduce outside the original serials.

## What is built, and what is not the system under test

The persona stage (`build_personas`) is the system under test and runs unchanged. Its inputs here are built by a script, not by EchoTales' resolver: chapters from the Gutenberg headings, one block per paragraph, narration and dialogue spans from the quotation marks, and mention-to-character assignments from a name gazetteer (case-sensitive whole-word patterns for the main named characters, chosen from the most frequent capitalised words of each text; ambiguous bare surnames such as "Bonacieux" or "Maylie" are left out). This is the same fixed-resolution design as `PREREG.md` Amendment 1 (the audit never re-resolves), but the mention layer is much cleaner than the real one, which flatters the extractor; stated as a limit, not corrected.

## Fixed beforehand

Cuts: *Oliver Twist* 5, 10, 15, 20, 30, 40; *The Three Musketeers* 10, 20, 30, 40, 50. Builds, each as a full build against a build over the truncated volume with the same extractor: status quo, plain horizon repair, horizon repair with the anchored cue at `(min_obs, majority) = (1, 0.8)` (the setting chosen on the web-novel serials in `PREREG_ANCHORED.md`; **not re-tuned here**) and at `(2, 0.8)` for robustness. Reference: `gpt-5.6-luna` strict prompt, a truth label per character (all passages) and a prefix label for each exposed (character, cut) pair (passages up to the cut), exactly the protocol and the 80% quote check of `PREREG_LABELS.md`. Budget for the labelling: expected under $0.03, hard cap $0.08 of the extra $0.20.

## Hypotheses (declared now)

- **PD1 the defect reproduces.** The status quo has stamp divergence above 0 in gender at these cuts. Falsified by 0 divergences on both books (then the defect is specific to the web-novel idiom or to the cuts).
- **PD2 the repair holds.** Plain and anchored repairs have exactly 0 stamp divergence on every cut. Any non-zero is a bug and is reported as such.
- **PD3 the cue transfers.** With the setting fixed beforehand, on the pairs whose reference gender is male or female, the anchored build is within 5 points of the status quo's correct share and has a wrong rate of at most 3.0%. Reported alongside: premature and justified counts of the diverging pairs under the strict reader, and the plain repair's correct share (its price).

## Limits declared now

One annotator (Luna) and no human labels; two books; third-person English only; a gazetteer mention layer that is cleaner than the real resolver; character names chosen after looking at the frequency lists but before building or running anything; the persona stage's other keys (age band, register, Big Five) are not scored here.
