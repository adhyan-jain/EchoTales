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

## RF-E2E run notes (addenda 6 to 9, 2026-10-16 20:20 to 21:55 IST)
- Order of the local GPU queue was changed during the run so that the larger models' judging came before the small-model fix 2; in the end every pre-registered cell ran (no cell was skipped).
- The pod router came back after the owner restarted the pod without the inner-port setting, so the first qwen32b card run exited before writing anything; the router was restarted with the inner port 18001 and the run was started again from nothing. No card was written twice.
- Zero empty cards for every model; RF1 decisions as pre-registered; fix 2 (RF5) not evaluated in either stratum because the memory channel had no lower limit above 0, as addendum 7 specifies.
- Addendum 9 (second judge olmo32b) ran because the time condition was met (finished 21:43).
- Addendum 10: qwen2.5:7b finished (22:17); llama3.1:8b had started as the addendum allowed but was stopped part-way at about 22:20 to meet the owner's submission time, and its partial files were removed; it is reported "not run (time)". The judge flags 7.4% of second-cipher prefix cards as leaks, above the 5% validity bound of addendum 6, so the judge-rule second-cipher value is reported as not interpretable and the text rule is the reading.
