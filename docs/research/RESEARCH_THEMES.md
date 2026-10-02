# Research themes

The 33 candidates reduce to six mechanisms. Status reflects
`DECISION_LOG.md` at the time of writing.

## T1: Perceptual cost of upstream errors, and commitment under uncertainty (primary)

**Candidates:** C01, C02, C03, C04, C11, C12, C13, C14, C15, C16, C22, C32, C33.

**Central mechanism.** A generator consumes an uncertain upstream inference (who speaks, who appears, gender). How much the output *commits* to that inference (a distinct character voice or a specific drawn figure, versus a narrator or a silhouette) determines how salient an upstream error is. The cost of an error is therefore a property of the rendering, not only of the inference.

**Common assumption in prior work.**
- Selective prediction and abstention treat the cost of an error as independent of the emitted form, and measure correctness, not perception.
- Audiobook and story systems assume upstream analysis is correct.

**What appears to break.**
- Real attribution is wrong at rates where this matters: H-CAL measures 13-36% error by tier on human gold, and about 54% honest coverage on web novels.
- More distinctive rendering leaves fewer errors masked (H-GATE: 22% → 2% masked).

**Benchmark.** PDNC passages with errors injected by measured type (addressee, cross-gender, same-gender), crossed with cast distinctiveness and rendering rung.

**Method.** A loss table L(rung, correct/wrong) estimated from listeners, then the Bayes rung per line given a posterior. Risk control is a component, not the claim.

**Theory.** Signal detection: the discriminability of a wrong rendering grows with rendering distinctiveness. Keep it only if it predicts something non-tautological, such as where the crossover sits as a function of posterior calibration.

**Human study.** H-COST (listening, built), and H-VABST (visual, to build).

**Multimodal extension.** C15, joint audio-visual commitment.

## T2: Content selection under a depiction budget

**Candidates:** C20, C23.

**Mechanism.** A long text affords only k pictures. Which moments readers want depicted is a preference target distinct from visualness, from narrative salience, and from what a zero-shot LLM picks.

**Assumption broken.** Story visualization draws every line; selection is left to LLM shot planners.

**Benchmark.** Pairwise beat preferences on public-domain chapters, plus a recoverability-vs-k evaluation.

**Method.** A preference-learned selector compared against the heuristic, visualness, LLM and random baselines.

**Human study.** Built (`moment_annotation.html`).

**Multimodal extension.** Selection for cutaway motion clips, which the product already budgets at two per chapter.

## T3: Causal propagation and correction allocation in multi-stage generation (parked)

**Candidates:** C21, C26, C29.

**Mechanism.** Seeded generation gives common random numbers, so the effect of one intermediate change on the final output can be measured.

**Why parked.**
- It is closest to the killed interface/truncation direction.
- The real-correction data (34 usable) cannot support an allocation policy.

**Revive only if** synthetic fault injection shows stage-dependent transmission that is *not* explained by the 77-token budget.

## T4: Label-free cross-modal error detection (parked)

**Candidates:** C28.

Precision is killed by legitimate non-correspondence (off-panel speakers), and there are no labels. It may come back as a feature of T1's posterior.

## T5: Evaluation validity for generated narrative media (supporting)

**Candidates:** C05, C25, C27, C30.

Audio-LLM and VLM judges, and upstream-interventional metric checks. Not a core on its own, but T1 and T2 need validated automatic proxies at scale. C05 is cheap on H-COST stimuli.

## T6: Generator-side identity stability (engineering)

**Candidates:** C06, C10.

Characterisation work. It joins T1 only if acoustic misattribution turns out to cost the same as textual misattribution.
