# Spend ledger (CHIMERA programme)

Rules (plan sections 7 and 18): nothing is spent without the owner approving an exact verified estimate; the API key is never displayed, printed or copied; owner cap for the OpenAI model is about $0.10 to $0.20 per request; GPU budget is $10 in total and nothing is rented without a separate approved request. Free local inference needs the owner to confirm model tag and hardware.

| Date | Purpose | Model id | Calls | Input tokens | Output tokens | Actual cost (USD) | Approved cap | Running total (USD) | Source |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-15 | L1: LLM leakage and evidence-gated linking, 72-item pilot, silver labels | `gpt-5.6-luna` | 281 (A 70, B 70, C 30, D1 70, D2 41) | 110,905 | 3,800 | 0.0267 | 0.10 | **0.0267** | `data/eval/chimera/l1_results.json` (`log`); cost recomputed 2026-10-15 from token counts at $0.20 / $1.20 per 1M tokens = $0.0267, matches the file's `spent_usd` |
| 2026-10-15 | M1 / L1b: evidence gate v2, 70 items, silver labels | `gpt-5.6-luna` | 80 (D1 70, entailment 10) | 38,082 | 2,701 | 0.0109 | 0.05 | **0.0376** | `data/eval/chimera/l1b_results.json` (`log`); recomputed from token counts at $0.20 / $1.20 per 1M tokens |
| 2026-10-15 | L2U: unseen-text control, 62 synthetic items x arms A and B | `gpt-5.6-luna` | 124 | 43,321 | 656 | 0.0095 | 0.04 | **0.0471** | `data/eval/chimera/l2u_results.json` (`log`); recomputed from token counts at $0.20 / $1.20 per 1M; owner cumulative cap $0.10 |
| 2026-10-16 | PD: public-domain reveal benchmark, 72 real items x arms A and B + 7 closed-book events x 2 + 62 synthetic x 2 | `gpt-5.6-luna` | 282 | 117,136 | 1,636 | 0.0254 | 0.04 | **0.0725** | `data/eval/chimera/pd/run_gpt-5.6-luna.json` (`spent_usd` 0.02539); recomputed from token counts at $0.20 / $1.20 per 1M; owner cumulative cap $0.10 |
| 2026-10-16 | PD v2: all frozen v2 items, arms A, B, B2 + closed book x3 + 62 synthetic x2 | `gpt-5.6-luna` | 1132 | 539,820 | 11,015 | 0.1212 | 0.15 (owner: run if below 0.15; exact estimate 0.1195 expected, 0.1986 theoretical worst case) | **0.1937** | `data/eval/chimera/pd_v2/run_gpt-5.6-luna.json` (`spent_usd`); the owner raised the cumulative cap for this run only |
| 2026-10-16 | PD v3: frozen v3 items (12 fresh books), arms A, B, B2 + closed book x3 + 62 synthetic x2 | `gpt-5.6-luna` | 808 | 375,420 | 7,940 | 0.0846 | 0.14 guard (owner approved the exact estimate $0.0836 expected / $0.139 worst case) | **0.2783** | `data/eval/chimera/pd_v3/run_gpt-5.6-luna.json` (`spent_usd`) |
| 2026-10-16 | PD v4: title-assisted memory probe M2, 31 events x 3 arms | `gpt-5.6-luna` | 93 | 14,924 | 964 | 0.0041 | 0.01 guard (owner approved the exact estimate $0.0038 expected / $0.0074 worst case) | **0.2824** | `data/eval/chimera/pd_v4/run_gpt-5.6-luna.json` (`spent_usd`) |
| 2026-10-16 | PD v7: Luna run **interrupted by the owner's instruction "dont continue with open ai"** (started 14:16:05, process killed about 14:21; no results file written; calls not counted by the harness) | `gpt-5.6-luna` | about 200 to 300 (estimate from elapsed time at roughly 1 call per second; actual UNKNOWN) | unknown | unknown | **about 0.02 to 0.03 estimated; upper bound 0.10 (the run's hard guard); actual spend must be read from the provider dashboard** | 0.10 guard (owner-approved) | **about 0.42 to 0.43 (upper bound 0.50)** | none; partial calls discarded |
| 2026-10-16 | PD label audit: Luna reads each reveal passage (31 events) | `gpt-5.6-luna` | 31 | 5,579 | 279 | 0.0015 | extra budget $0.20 granted by owner for unattended work (2026-10-16); guard 0.01 | **0.2839** | `data/eval/chimera/pd_label_audit.json` |
| 2026-10-16 | PD v5: cue-preserving arm B3, 533 items | `gpt-5.6-luna` | 533 | 260,823 | 5,286 | 0.0585 | guard 0.10 (owner extra budget $0.20, unattended) | **0.3424** | `data/eval/chimera/pd_v5/run_gpt-5.6-luna.json` |
| 2026-10-16 | PD v6: 7 fresh books, arms A/B/B2/B3 + closed book + M2 | `gpt-5.6-luna` | 538 | 251,709 | 5,387 | 0.0568 | guard 0.095 (owner extra budget, unattended) | **0.3992** | `data/eval/chimera/pd_v6/run_gpt-5.6-luna.json` |

Prices used: $0.20 per 1M input and $1.20 per 1M output tokens (Standard, short context), from OpenAI's pricing and model pages read through a summarising fetch tool on 2026-10-15 (tag `[SUMM]`, not verbatim).

GPU spend so far: $0 of the $10 budget. Nothing rented.

Requests, status as of CP-H:

| Request | Model | Calls | Expected cost | Worst case | Notes |
|---|---|---|---|---|---|
| M2 replication of arms A and B on Claude Haiku 5.5 via Claude Code subagents | `haiku` alias (snapshot UNVERIFIED) | 124 spawns | $0 API (subscription quota; measured from completion notices) | $0 API | owner approved the Haiku route, then ("approved for all") the plan was to prefer the free local Qwen run; the Haiku run was NOT run (about 50,800 tokens per spawn, about 6.3M for 124); same family as the silver labeller, so the shared-memory confound is NOT resolved; a third-family run (local Qwen) is still planned |

Remaining under the owner's cumulative $0.10 cap after L2U: $0.0529; **after PD: $0.0275** (running total $0.0725). Further paid runs need a new exact estimate and approval.

After PD v2 on Luna: running total **0.1937** USD, above the original $0.10 cap by the owner's explicit approval of this run ("run luna, if it is below 0.15 then run it"). Any further paid run needs a new exact estimate and approval.

After PD v3 on Luna: running total **0.2783** USD (owner-approved exact estimates for both Luna runs above the original $0.10 cap). Any further paid run needs a new exact estimate and approval.

After PD v4 M2 on Luna: running total **0.2824** USD (owner-approved exact estimates). Any further paid run needs a new exact estimate and approval.

Owner granted an extra $0.20 (beyond the $0.2824 spent) for unattended work on 2026-10-16 with no further approvals; hard ceiling therefore $0.4824. After the label audit: running total **0.2839** USD.

After the unattended window runs: running total **0.3992** USD against a ceiling of $0.4824 (original caps plus the owner's extra $0.20); remaining headroom 0.0832. Any further paid run needs a new exact estimate and approval unless the owner grants more.

Owner instruction 2026-10-16 (late): no further OpenAI use; the confirmatory study runs on open-weight models on RunPod plus Claude Sonnet 5.5 through the owner's Claude subscription. The PD v7 Luna run was interrupted as described above and its results do not exist; PD v7 is reported with the five local models only (exploratory).

## RunPod (owner-created pod, one L40S 48 GB, USD 1.13 per hour all-in: GPU 1.09 + disks 0.04) and Claude subscription

Owner instruction 2026-10-16 (goal text): "hard ceiling of 10 USD total GPU (RunPod) plus the Claude subscription. No OpenAI calls. Log every spend". Earlier the owner set USD 15 in total for RunPod; the tighter 10 USD ceiling governs from the goal text. Stop rule: no new run starts if the projected total exceeds 9.50.

| When (IST) | What | Basis | Estimated USD | Running total |
|---|---|---|---|---|
| 2026-10-16 to 17:45 | pod up 7,349 s (read from `ps -o etimes -p 1` on the pod at about 17:38 IST): exploratory vLLM runs of qwen32b, olmo32b, mistral24 on PD v2/v3/v6/v7, model downloads and swaps | 7,349 s x 1.13 / 3600 | 2.31 | 2.31 |

The figure is an **estimate from pod uptime**, not the RunPod billing page; the owner should compare it with the console balance. Claude subscription calls (E2 stories, Claude E1 arm) use quota, not dollars; they are not priced here.
