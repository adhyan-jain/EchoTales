# PD CONFIRM v2: deviations log (written as they occur, before the affected analysis is read)

| Time (IST) | Deviation | Effect |
|---|---|---|
| 18:32 | **Claude Sonnet 5.5 arm stopped by the subscription session limit** ("You've hit your session limit, resets 9:50pm IST") after 211 of 1,218 planned answers (8 events, no M2 answers). The reset is after the 20:45 freeze, so the arm cannot be completed. | The Claude file is reported as a **partial, descriptive** arm (8 events) and is **excluded from the pooled H1, H2, H3 and P1** (the analysis script is run with the file moved out of the pooled set). H1's "at least 3 of 4 core models" criterion is therefore evaluated over three models and cannot pass as written; it is reported as "not evaluable (3 models)". |
| 18:00 | Events: 68 (53 test, 32 test events in the primary EXPLICIT set), far below the 150 first planned and the 75 of addendum 2. Mining stopped when all 3,523 drawn books were processed (before the 19:45 stop). | Minimum detectable effects reported with each result; nulls are not evidence of absence. |
| 18:09 | The shared helper `pd_reveal_benchmark.spaced` divides by zero for k = 1; `pd_confirm_run.spaced` handles it (1 post-reveal item from the middle of the mentions). No result had been produced. | none |

## Analysis-time notes (19:05 IST, after all three open-model arms finished)
- **Claude arm excluded from every pooled test.** The partial file (211 of 1,218 answers, 8 events, no M2) was moved to `data/eval/chimera/confirm/partial/` before the analysis run. H1's criterion "at least 3 of 4 core models" cannot be met with 3 models (`criterion_needs_4_models`), so H1 is reported as not passed by construction as well as by its estimate.
- **Bootstrap guard.** `boot_events` crashed when the recovered fraction was undefined in every resample (OLMo A-B3 baseline near zero). It now returns NaN limits in that case. No other statistic is affected; the analysis script was otherwise unchanged after the results were seen.
- **H3 reading.** The pre-registered pass rule in code is rho >= 0.20 and raw p < 0.05, which is met (rho +0.30, p 0.041). The Holm-adjusted p (family H1, H2, H3, H5) is 0.145 and addendum 2 sets the Holm level at 0.0125, so H3 is **not** reported as confirmed; the raw criterion is reported beside the adjusted p.
