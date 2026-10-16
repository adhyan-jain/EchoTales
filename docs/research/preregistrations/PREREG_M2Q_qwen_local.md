# Pre-registration M2Q: arms A, B and closed-book on local Qwen2.5-7B, with the unseen-text control (version 1)

Written and frozen **before the M2Q runner exists and before any Qwen call**. Repo HEAD `6c7e2c2`, 2026-10-15. Hashes in `MANIFEST_M2Q.json`. L1 and L2U results are unchanged and are the comparison. Replaces the Haiku-subagent M2 (not run: 6.3M tokens of quota, same family as the silver labeller).

**Label provenance (every number).** Real-text items: silver (model-drafted gold; the pipeline's own link). Synthetic items: by construction. No human label. Reveal chapters from repository data only.

## 1. Why this model

`qwen2.5:7b` (ollama) is a different family from the silver labeller (Claude) and from Luna (OpenAI), runs free on the owner's GPU, is deterministic (temperature 0, fixed seed), and is trained on substantial Chinese web-novel text, so it is the most informative cheap test of whether the L1 renaming gap reflects memory. **Hardware verified by the agent before the run:** RTX 4060 Laptop GPU, 8,188 MiB, 7,874 MiB free, ollama serving `qwen2.5:7b`; GPU only, no CPU offload; system RAM monitored. A null from a 7B model narrows the claim to this model; it does not kill it for larger models.

## 2. Items, arms, prompts

- **Real items:** the 62 pilot items with a silver truth letter (the L1 leakage set), arms **A** and **B** built exactly as in L1 (same windows, same candidate lists, same T4 v3 token renaming for B, same frozen `A_B_prefix` template), 124 calls.
- **Closed book:** the 15 non-string-trivial items, arms **C_orig** and **C_ren** (frozen `C_closed_book` template), 30 calls.
- **Synthetic unseen-text control:** the 62 items and prompts of `PREREG_L2U_unseen_text_control.md`, arms A and B (renamed with the T4 v5 cipher), 124 calls.
- Settings for every call: `temperature 0`, `seed 20261016`, `num_predict 8`, `num_ctx 4096`, one run per cell, no retries. An answer must start with a candidate letter or the word `UNDETERMINED` after stripping punctuation; otherwise `INVALID` (a non-answer).

## 3. Metrics and decision rules (fixed now; same as M2 and L2U)

- **R1 renaming validity for this model:** A and B give the same letter on all 30 plain controls. If not, the real-text A-minus-B gap is not interpreted.
- **R2 replication:** if R1 holds, paired bootstrap (10,000 resamples, seed 20261016) of accuracy-against-silver A minus B over the 62 items; **replicates** if the mean difference is at least +5 points and the 95% interval excludes 0.
- **R3 primary items (n = 4):** counts under A and B; inconclusive by design.
- **R4 closed book:** **memory-consistent** if C_orig has at least 4 of 15 correct (exact one-sided binomial p < 0.05 against the mean chance 1/(candidates)) and the Wilson lower bound exceeds chance; else no evidence of memory **for this model**. C_ren reported beside it; chance and always-most-frequent-candidate baselines reported.
- **R5 unseen-text control (this model):** the L2U readings (a), (b), (c) applied with this model's real-text gap `g_r` (not Luna's) and this model's synthetic gap `g_s`; ceiling guard as in L2U.
- Reading guard: all real-text results are silver, one model, small n; a gap that replicates is not evidence of leakage unless R5 reading (b) also holds.

## 4. Power

As M2 and L2U; closed-book n = 15 (4 correct needed); the sign test on 62 pairs needs at least 5 discordant pairs in one direction with none the other way.

## 5. Cost and safety

No API key, no spend. Local GPU only; if free VRAM falls below 3 GiB or available system RAM below 1 GiB the run stops. Prompts contain novel text but are built in memory and sent only to `127.0.0.1`; the repository receives letters and counts only.

## 6. Deviations log

None at freeze.
