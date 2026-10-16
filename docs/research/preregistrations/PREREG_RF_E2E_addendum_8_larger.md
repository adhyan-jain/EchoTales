# RF-E2E addendum 8: the same experiment and fixes on two larger open models (written before any larger-model card exists)

Written 2026-10-16 at 20:50 IST. **What had been seen first:** the interim analysis of `qwen2.5:7b` alone (rule A: W-ren 21.1% vs P-ren 0.0% over 19 events; rule B: 16.7% vs 0.0% over 54 events; memory channel about 2 points). Nothing of `llama3.1:8b` or `mistral:7b-instruct` had been read. Owner instruction of the same day: "if you think it is better to use higher ones then i can run up the runpod pod". Owner budget: RunPod total at most 10 USD (about 3.9 USD used).

**Why.** Two questions the small models cannot answer: whether the input-channel leak holds for larger models, and whether there is a memory-channel leak for fix 2 to remove (memory grows with model size, Section 6).

**Models.** `qwen32b` (Qwen2.5-32B-Instruct, AWQ) and `mistral24` (Mistral-Small-3.2-24B, fp8) through the existing pod router (vLLM, temperature 0, seed 20261016, 160 new tokens); `olmo32b` only if both finish before 22:30 IST. Everything else is exactly addenda 6 and 7: events, cut, passages, prompt, arms, rules A and B, the judge (`qwen3:8b`, local), fix 1 and fix 2, bootstrap and decision rules.

**Analysis.** The larger models form a **separate, pre-registered stratum**: RF1 and RF5 are evaluated on the pooled larger models with the same thresholds, and reported beside (not pooled with) the three small models, whose verdicts stay as addenda 6 and 7 define them. A card that comes back empty (an endpoint error) is counted and reported; if more than 5% of a model's cards are empty, that model is reported as not interpretable. A model that does not finish by 22:45 IST is reported "not run".
