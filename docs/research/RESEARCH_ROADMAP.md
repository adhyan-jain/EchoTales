# Research roadmap

Ordered by what can kill the most at least cost. No paper thesis is selected
yet. The leading theme is T1, but it has not earned commitment: everything
depends on step 1.

## Step 1 (decisive): H-COST listening pilot

1. Fix the two design issues from the pilot:
   - select passages with ≥2 speakers per gender, or report realised rates;
   - control the duration difference between narrator and cast renders.
2. Synthesize the full stimulus set: about 12 passages × 28 conditions, cached; roughly 1-2 GPU-hours on the 4060 with ollama unloaded.
3. Run the manipulation check on every stimulus (`voice_geometry.identify`).
4. Recruit 24 listeners (local, volunteer) as a pilot to estimate effect size and listener variance. Then run a power-based main study of about 50.
5. **Decision:**
   - Kill T1's core if the cluster-bootstrap CI of the probe-accuracy difference-in-differences includes 0 at the powered n **and** enjoyment shows no interaction.
   - Also kill if any crossover sits only at accuracies below about 45%.

Budget note: paid crowd listeners would exceed the $5-10 cloud cap by about two orders of magnitude. Plan on volunteers (the university team) or ask the owner for a separate study budget.

## Step 2 (parallel, no GPU): H-SELECT annotation

- 3 chapters, about 90 within-chapter pairs, 5 annotators, 20 shared overlap pairs.
- **Kill** if overlap agreement is too low (kappa-equivalent below 0.3), or if the LLM ranking already matches the Bradley-Terry human ranking at ceiling.

## Step 3: H-VABST (visual arm of T1), only if Step 1 survives

Build the image stimulus generator: 40 beats × {committed default, committed alternative, silhouette}, using fixed seeds on the existing engines, plus a reader study page.

## Step 4: riders on Step 1 data

- **H-JUDGE-A:** audio-LLM judge vs listeners by error type. Check API cost first.
- **C03:** fit the per-type error-cost model, giving a perceptually weighted attribution metric.

## Step 5: only after a surviving core

- C15, joint cross-modal commitment (a 2×2 on beats with both voice and panel).
- C04 with a learned posterior. This needs care, because a better posterior drifts toward attribution and the firewall.
- Product hooks (opt-in): a casting-policy hook in `voice/runner.py` and a framing-rung hook in `render/panels.py`.

## Kill-or-commit rule

The paper core is chosen only when one hypothesis has:
1. survived its human test;
2. shown generality across both modalities, or across two corpora;
3. a mechanism-level explanation.

Until then, EchoTales is developed as a product, and the arena keeps collecting evidence.
