# RF-E2E addendum 12: suffix canaries, a judge-free test of input-channel look-ahead on every event (written 2026-10-17, before any of these cells exists)

**Seen before writing:** all results of addenda 6 to 11 and the post hoc checks in paper Section 7.7. No cell of this addendum has been generated. The events are the 68 frozen confirmatory events (`PD_confirm_events_v1.json`, unchanged); the same 57 measurable events of addendum 6 are used.

## Why

Section 7 has two weaknesses an external reader names first. (1) The primary, judge-free rule A applies to only 19 of 57 events, because in the others the identity's name already occurs in the reader's prefix, so a name match cannot tell disclosure from mention. (2) Every other event needs a model judge. A **suffix canary** removes both: we change the text *after the reader's position only*, writing into it a string that occurs nowhere in the prefix, nowhere else in the book and in no training corpus, and check whether the output at the reader's position contains it. The string can reach the output only through the input suffix. So a hit is input-channel look-ahead with no false positives by construction, no judge, no renaming and no memory explanation, and it applies to every event. It is also the definition of reader-faithfulness applied directly (Section 3.1: two volumes with the same first c chapters must give the same output at c), and it needs only black-box access, so it can be run against a product that accepts an uploaded book.

## Canaries (deterministic, no model)

For each event, on the original text, only in `text[cut:]`:

- **Reveal canary (C-R).** Every capitalised identity name token (length >= 3, not an honorific, not part of any alias string) is replaced, at word boundaries, by a fresh invented token. The narrative is unchanged: the book still reveals that the alias is a person, now under a name nobody has seen. Tokens shared with other characters (a family surname) are replaced too; this is stated, not corrected.
- **Fact canary (C-F).** One sentence `"<Alias> had been born in <Place>."` (alias capitalised as written in the event, `<Place>` a fresh token) is inserted after the end of the sentence of the first alias mention after the reveal sentence. It probes look-ahead of an ordinary, non-spoiler fact and does not depend on the event's reveal being correctly labelled.
- **Fresh tokens.** Built from a fixed syllable list with seed 20261017 plus the event index; capitalised, 6 to 10 letters; rejected if the lower-cased token occurs as a word in the book, in `/usr/share/dict/cracklib-small`, among the event's cast tokens or among tokens already drawn.

## Systems and cells (original names, canaried text, local models)

1. **W_can**: the whole-volume card of addendum 6 (same prompt, K = 12 passages spaced over all alias mentions, same passage windows), built from the canaried text and served from the first mention.
2. **P_can**: the versioned (prefix) card at the cut (same rule as P). The prefix is unchanged by construction, so its canary rate must be exactly 0.
3. **L_can (new design, long-context positional instruction).** The most common way to make a general long-context assistant spoiler-aware is to give it the book and tell it where the reader is. Context = the prefix window (up to 16,000 characters ending at the cut, extended back to include the last pre-cut alias mention, at most 24,000 characters) + the line `[READER POSITION: the reader has read up to here]` + the canaried suffix up to 1,500 characters past the end of the later of the reveal sentence and the fact canary, at most 16,000 characters. Prompt: "You are a reading companion. The reader has read the book only up to the marker [READER POSITION]. Answer the reader's question using only the text before the marker, and do not reveal anything that happens after it.\n\nBook text:\n{CTX}\n\nReader's question: Who is {ALIAS}? Answer in at most 60 words." `num_ctx` 12,288.
4. **L_trunc**: the same prompt with the suffix removed (the context ends at the marker). This is the prefix-faithful version of L; its canary rate must be exactly 0.

Models: `qwen2.5:7b`, `llama3.1:8b`, `mistral:7b-instruct` (the generators of addenda 6 and 7), temperature 0, seed 20261016, one generation per cell; cards with `num_predict` 160, L cells 120.

## Rules (text-derived, no judge)

- `canary_R` = the output contains any reveal-canary token (case-sensitive word match; a case-insensitive count is reported beside it).
- `canary_F` = the output contains the fact-canary place token.
- An event is L-measurable for C-R if the reveal sentence lies inside the L suffix window, and for C-F if the fact sentence does. W exposure (whether any W passage contains a canary token) is recorded per event; the leak is reported overall and conditional on exposure.
- Descriptive only: on the 19 rule-A events, `P_can` and `L_trunc` naming the *real* identity (rule A of addendum 6), i.e. memory or prefix inference with no suffix in the input.

## Hypotheses (event-cluster bootstrap, 10,000 resamples, seed 20261101; pooled per-event value = mean over models)

- **H12.1 (primary).** W_can minus P_can on `canary_R`, over measurable EXPLICIT and IMPLIED events, is at least +10 points with a 95% lower limit above 0, and positive for at least 2 of 3 models.
- **H12.2.** L_can minus L_trunc on `canary_R`, over L-measurable EXPLICIT and IMPLIED events, is at least +10 points with a 95% lower limit above 0, and positive for at least 2 of 3 models.
- **H12.3 (validity, structural).** P_can and L_trunc have `canary_R = canary_F = 0` in every cell. Any hit means the harness is wrong; the analysis then stops and reports the bug instead of a result.
- **Secondary, descriptive.** `canary_F` rates for W and L; per-model rates and sign tests; EXPLICIT-only subset; W leak conditional on exposure; consistency with addendum 6 rule A on the 19 rule-A events (W_can canary_R against W_orig rule A; different text, so not expected to be identical).

## What would count against the claim

H12.1 failing would mean the judge rule of Section 7 over-states the input channel on the events rule A could not score; the paper would say so. H12.2 failing would mean an explicit positional instruction is enough for these models in this setting; the paper would say so and would not generalise Section 7 to that design.

## Order and stopping

qwen2.5:7b first, then llama3.1:8b, then mistral:7b-instruct; a run stops if available RAM falls below 0.8 GiB and resumes per event. Any model not complete when the session ends is reported "not run", and the hypotheses are evaluated on the complete models with the rule "at least 2 of the complete models" stated as a deviation. No earlier verdict changes. Cost $0 (local GPU).
