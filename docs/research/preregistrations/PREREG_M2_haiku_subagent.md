# Pre-registration M2: replication of arms A and B on Claude Haiku 5.5 via subagents (version 1)

Written and frozen **before any M2 spawn**. Repo HEAD `6c7e2c2`, 2026-10-15. Hashes in `MANIFEST_M2.json`. L1 results are unchanged and used as the comparison.

**Label provenance (every number).** Reference labels are **silver** (model-drafted gold; the pipeline's own link for system-sourced items). Reveal chapters from repository data only. No human label.

## 1. Question and the confound this does NOT resolve

Does the L1 finding (answers agree more with the silver final identity under original names than under renamed names) replicate on a second model? **The silver gold labels were drafted by a Claude model (`claude-sonnet-5-gold-hardcases`) and the resolver here is a Claude model**, so a gap that appears may reflect shared memory *between the resolver and the labeller* rather than memorisation of the novel. M2 therefore tests replication on a second model, **not** the shared-memory confound. The confound needs a resolver from a third family (planned: local Qwen, owner confirmation pending).

## 2. Method

- **Resolver:** Claude Haiku 5.5, called as a Claude Code subagent (`model: haiku`, general-purpose agent), at no per-token API charge to the research budget; usage is subscription quota, measured from the completion notices. That the `haiku` alias resolves to Haiku 5.5 is **UNVERIFIED** (the harness documents the alias, not the snapshot).
- **Items:** the 62 pilot items that have a silver truth letter (the L1 leakage set), arms **A** (original names) and **B** (the T4 v3 token renaming applied to the window, the mention surface and the candidate names), **124 spawns, one item and one arm per spawn** (several items in one prompt would show later-chapter text to an earlier-chapter question, breaking the prefix rule).
- **Prompts:** exactly the L1 prefix template (`A_B_prefix` in `L1_prompts_v1.json`, hash in `MANIFEST_L1.json`), built by `scripts/chimera/m2_haiku_prepare.py` into per-item files in the session scratchpad (never in the repo: they contain novel text).
- **Spawn instruction (frozen wrapper):** "Read the file <path>. It contains a reading-comprehension question; answer it exactly as the file instructs. Then use the Write tool to write ONLY your answer token (one letter, or the word UNDETERMINED) to the file <outpath>, and reply done. Use no other tool, read no other file, and do not search for anything." Wrapper hash in the manifest.
- **Tool-use rule:** a valid spawn uses **exactly two tool calls** (one Read, one Write), read from the completion notice. A spawn with any other count is **invalid**, its answer is discarded, and it is **re-run once** in a fresh spawn; a second invalid result is recorded as `INVALID`. No other re-runs. No prompt is edited after freezing.
- **Parse:** the written token must be a listed candidate letter or `UNDETERMINED`; anything else is `INVALID` (a non-answer).
- Temperature and seed cannot be set. Each (item, arm) is run once.

## 3. Metrics and decision rules (fixed now)

- **M2-R1 renaming validity for this model:** A and B give the same letter on **all 30 plain controls** (the same 98% rule as L1, which means 30 of 30). If not, the A-minus-B gap is **not interpreted**.
- **M2-R2 replication:** if R1 holds, paired bootstrap (10,000 resamples, seed 20261016) of accuracy-against-silver A minus B over the 62 items; **replicates** if the mean difference is at least +5 points and the 95% interval excludes 0; **does not replicate** if the interval includes 0 or the difference is below +5 points; the sign-test counts (A right and B wrong versus B right and A wrong) are reported.
- **M2-R3 primary items (n = 4):** counts of naming the silver final identity under A and under B; **inconclusive by design** (n = 4), reported as counts.
- Baselines: uniform chance and always-most-frequent-candidate on the controls, as in L1.
- **Reading guard:** any pass is "the gap appears on a second model from the labeller's family"; it is not evidence of parametric leakage, because of the confound in section 1 and because the renamer failed its commutation gate in T4 v3.

## 4. Power

62 paired items; a one-sided sign test at 0.05 needs at least 5 discordant pairs in one direction with none the other way. Primary n = 4. Controls n = 30.

## 5. Cost and safety

No API key and no paid call. Cost is subscription quota, reported from the completion notices (subagent token counts). A pilot of 2 spawns on non-novel dummy text measures the per-spawn overhead before the 124 are launched. Prompt files and answer files stay in the scratchpad; only letters, hashes and counts reach the repository. Novel text goes to Anthropic through this session (the provider already serving it); the owner approved the Haiku-subagent route.

## 6. Deviations log

None at freeze.
