# PD CONFIRM v2, addendum 2: halved scope to finish the same day (written before any event is mined)

Written 2026-10-16 (evening IST), before any model has read any candidate sentence and before any event exists. Owner instruction (verbatim): "half the dataset you are trying to work on, we need to get this completed soon". It changes only the size and scope below; every rule, hypothesis, estimator and threshold of `PREREG_PD_CONFIRM_v2_L40S.md` and addendum 1 stays.

| Item | Before | Now |
|---|---|---|
| Event target | 150 (acceptable 100 to 200) | **75 (acceptable 60 to 100)**; selection stops at 75 events, books taken in mining order, at most 5 per book |
| Book rounds (addendum 1) | up to 3 rounds | all drawn books are mined (cheap); selection still takes events in mining order and stops at 75, so later rounds are used only if earlier ones fall short |
| Power | 80% power for 9.0 points with 120 test events | with about 60 test events the minimum detectable gap is about 12.7 points at Holm 0.0125 (same SD 0.295, scaled by sqrt(120/60)); H1's +10 threshold is **below** the minimum detectable gap, so a null on H1 is not evidence of absence |
| Stages | E1+M2, E4, E5, E2 | **E1 + M2 (H1, H2, H3) and E4 (H5) only.** E5 (H6, recap spoilers) and E2 (H4, LLM-authored unseen stories) are **not run**; they are reported as "not run", never as passed or failed |
| Claude arm | test split, A/B/B3 + M2 | unchanged in design; scope may be cut to the first 300 test items if throttled; any cut is reported |

Provenance unchanged: text-derived oracle, model-selected events, no human verification.
