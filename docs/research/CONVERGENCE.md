# Convergence pass (2026-10-03): disagreement → action selection → error manifestation

One file, four parts. Final status: **KILL** of the converged thesis; XDIS kept as product infrastructure.

- [Part 1: Decision](#part-1-decision)
- [Part 2: Analysis](#part-2-analysis)
- [Part 3: Experiments](#part-3-experiments-frozen-protocols-and-results)
- [Part 4: Prior-art recheck](#part-4-prior-art-recheck)

---

# Part 1: Decision


### Final status: **KILL** (of the converged research thesis)

XDIS is kept as strong product infrastructure, with two product actions attached.

### The four-layer test

| Layer | Claim | Holds empirically? | Novel? | Verdict |
|---|---|---|---|---|
| 1. Phenomenon | Independent disagreement finds errors native confidence misses | **Yes, strongly** (C2: AUROC 0.943 vs 0.631; 0.928 vs 0.414 of errors caught at 20%) | No: cross-model disagreement for confidently-wrong outputs (ICLR 2026); disagreement-targeted review (2026) | Holds; prior art |
| 2. Causal effect | The downstream action changes how the same upstream error manifests | **Yes, but definitional** (C3: R² 0.95 against cast-table geometry; same ordering; no unpredicted leakage) | No: representation-dependent detectability under injection (Hallucination Snowball, 2026) | Killed as a phenomenon |
| 3. Method | Disagreement selects a safer action | Yes (P3 dominates P1: 8% vs 58% residual manifested mass at 20%, at lower identity price) | No: hedging, hierarchical selective classification, cost-sensitive deferral | Application, not method |
| 4. Generalisation | Works in another modality | Same structure in image (H-VRUNG reread), also by design | — | Does not rescue layer 2 |

The pre-registered kill conditions (section 12 of the brief) that fire:
- **A straightforward existing selective-prediction method explains all gains.** The policy result is the layer-1 capture curve times the layer-2 cost table.
- **Literature shows the mechanism already exists.** Layer 1 is ICLR 2026. Layer 3 is Deng 2012 and Goren 2024. Layer 2 is published in text pipelines.
- **Partly: "changing the rendering action does not materially change downstream error".** It does change it materially, but only by the amount the action's definition dictates. That is the same failure in a different form.

The kill conditions that did *not* fire:
- XDIS kept its advantage after alias correction and with a product-built list. It got stronger.
- The effect does not depend on gold candidate information.

### Answers

**1. Does XDIS survive principled PDNC alias correction?**
Yes.
- The tiered alias rule resolved all 58 name-variant golds, and 54 false ladder errors disappeared, leaving 106.
- P3 still beats confidence: 0.424 vs 0.284 caught at 10% review, 0.691 vs 0.414 at 20%.
- The 10% gain, +0.140 [0.079, 0.213], misses the pre-registered 0.15 bar, so the verdict stays CONDITIONAL. That was the original verdict.

**2. Does XDIS survive a genuinely product-built shortlist?**
Yes, and it improves. The list came from text surfaces only.
- Gold recall 0.972; 10.5 names on average.
- qwen accuracy rose from 0.76 to 0.92. The gold list of PDNC main names had caused 149 parse failures, so the original run under-measured qwen.
- **GREENLIGHT** by the frozen map:
  - P3 catches 0.620 of errors at 10% (+0.336 [0.233, 0.486]) and 0.928 at 20%;
  - P(error | agree) = 0.014;
  - the random-pick control is at chance.

**3. Does disagreement still outperform native confidence?**
Yes, by a wide margin:
- AUROC 0.913 (P2a) and 0.943 (P3) vs 0.631;
- selective risk at 20% review: 0.009 vs 0.078;
- the gap comes almost entirely from the ladder's EXPLICIT tier, 0.95 confidence: 93% vs 9% of those errors caught at a 20% budget.

**4. Does a downstream action causally change the manifestation of the same upstream error?**
Yes. Holding the text and the injected error fixed:

| Error type | Specific | Generic | Narrator |
|---|---|---|---|
| cross-gender | 0.87 | 0.42 | 0 |
| same-gender | 0.35 | 0.01 | 0 |
| addressee | 0.74 | 0.18 | 0 |

These are speaker-verification margins toward the gold voice. All the specific-voice CIs exclude 0.

**5. Is there an action-conditioned amplification/masking phenomenon?**
No, beyond the definition.
- Reference-clip geometry predicts the realised audio margins with R² 0.95, slope 0.90, and the same order in every error type.
- The generic voice's wrong-gender carry-over is exactly what the geometry predicts: 0.53 vs 0.55.
- The image arm's attribute-selective masking is likewise by design.

**6. Which parts are already covered by prior art?**
All four layers, in general form (Part 4):
- **Disagreement for confidently-wrong outputs and selective prediction:** ICLR 2026; arXiv 2603.25450; 2609.26926.
- **Downstream representation changes error detectability under injection, with gating:** arXiv 2608.14588.
- **Coarser output under uncertainty:** Deng et al. 2012, also patented (US 9,779,291); Goren et al., NeurIPS 2024.
- **Cost-sensitive multi-action deferral:** Mao et al. 2024; DeCCaF.

**7. What exact scientific gap remains, if any?**
One gap, which machine evaluation cannot close: whether *listener* cost tracks speaker-embedding distance or is categorical and non-linear. That is the H-HEDGE / H-IOL / H-COST line.
- Machine verifiers in the output space reproduce the action's own geometry by construction. C3 measured this directly: R² 0.95.
- A second gap is application-only: no audiobook or dubbing system measures or acts on attribution uncertainty. That is a product gap, not a scientific one.

**8. Can the main evidence be machine-only?**
For layers 1 and 3, yes, and it now is. For layer 2, machine-only evidence can show only the definitional effect. Any non-trivial claim about masking or amplification needs human perception.

**9. Is a small human sanity check useful?**
Not for this thesis.
- 8-12 listeners cannot support a paper claim about non-linear perceived cost. They could give a direction (does narrator fallback sound less wrong than a wrong character voice?) to calibrate the product's price-of-masking trade-off.
- Worth running only as product calibration, after the product hook ships, using the existing H-COST stimuli.

**10. Does H-SELECT converge into the same mechanism?**
No. The "limited commitment budget" framing reduces to the C3 policy layer, which is selective prediction. "Which moment to illustrate" contains no upstream error. Classification: **PRODUCT-ONLY**.

**11. What is the single strongest paper formulation?**
None at research-paper strength. The most defensible write-up is a short application or negative-results note:

> In a full-cast audiobook pipeline, rule-vs-LLM disagreement catches 93% of
> speaker errors at a 20% gating budget where confidence catches 41%
> (PDNC, product-built candidates). Rendering-action counterfactuals show
> that the error's audible manifestation under narrator, generic and
> character voices is fully predicted by voice geometry (R² 0.95). So the
> lever is the risk signal, not the rendering action.

Its honest contributions are measurements:
- the product-faithful protocol;
- the gold-list parse artifact (a methodological caution for LLM attribution evaluations on PDNC);
- the triviality control.

It is not a new mechanism.

**12. What is the single strongest patent-relevant technical mechanism, if any?**
A weak candidate, at best:
- per-line voice-commitment gating driven by *product-side* surface agreement between a deterministic attribution ladder and an independent LLM over a text-derived candidate list;
- with routing of gender-disputed lines to a non-gendered (narrator) voice rather than a same-gender "unconfirmed" voice;
- and a measured action-cost table.

The prior art is close: Deng's patented hedging, cross-model disagreement, and diarization confidence (US20140029757A1). The inventive step looks thin. Not recommended for filing without a professional search.

**13. What is the next experiment?**
A product step, not a research experiment:
- Wire XDIS into `voice/runner.py`'s choice of action, behind a config flag. Disagreement plus low confidence routes to narrator; disagreement alone routes to the unconfirmed voice, and a gender-disputed line routes to narrator.
- Measure on the RI novel what fraction of lines change voice, and the GPU cost of the second view.

S1 (the ladder name-inventory check) is done and passes (part 3). It was:
- the H-XDIS-PS ladder sensitivity, with the ladder's `known_names` rebuilt from the product detector instead of PDNC's list;
- if P3's 20% capture drops below about 0.7, the product claim weakens.

The research track should return to the open perception questions (H-COST / H-IOL) only if human listeners become available.

### What is kept, and where

| Finding | Status | Home |
|---|---|---|
| XDIS as a gating signal (P3) | Strong product infrastructure | H-XDIS-PS; product hook proposed (answer 13) |
| Gold-list parse artifact | Methodological note | ENGINEERING_NOTES 23; H-XDIS-PS note |
| The unconfirmed voice leaks cross-gender errors (floor 0.24 under oracle) | Product defect, measured | H-ACT note; `voice/runner.py:334-347` rule |
| Price of masking on correct lines | Product calibration number | H-ACT |
| Action-conditioned manifestation | Definitional; killed as research | H-ACT KILLED |
| H-SELECT | PRODUCT-ONLY | — |

---

# Part 2: Analysis


**Date:** 2026-10-03.

**Inputs:** every surviving artifact (H-XDIS, H-GATE-XDIS, H-GATE, H-CAL, H-HEDGE, H-VRUNG, H-COST, H-IOL, H-JUDGE-V/A, H-SELECT) and the product voice path (`pipeline/voice/runner.py`).

**New evidence:** three pre-registered experiments (Part 3) and a prior-art recheck (Part 4).

**Decision:** Part 1.

### 1. What the product actually does

`voice/runner.py` already implements three rendering actions for a dialogue line:
- **Character-specific:** the cast voice. Used when the attribution confidence is at least `min_character_confidence`.
- **"Unconfirmed":** a voice of the *predicted* character's gender, never their own. Used when confidence is lower.
- **Narrator:** used when the line is unresolved.

The only risk signal driving the choice is the ladder's tier confidence. H-CAL showed that signal barely ranks errors (AUROC 0.59-0.63). Two consequences follow:
- **Engineering, not a research question:** whether a better signal should drive the choice.
- **Possibly research:** whether the choice changes what an error costs.

### 2. Layer 1: XDIS as a control signal

Read the three runs in order, because each removes one confound.

| Run | Labels | qwen's list | Errors | AUROC P3 | Caught @10% / @20%, P3 vs P1 |
|---|---|---|---|---|---|
| H-GATE-XDIS (original) | raw PDNC | gold-derived, main names | 160 | — | 0.388 / 0.671 vs 0.249 / 0.372 |
| C1 (H-XDIS-ALIAS) | alias-corrected | same gold list | 106 | 0.877 | 0.424 / 0.691 vs 0.284 / 0.414 |
| C2 (H-XDIS-PS) | alias-corrected | **product-built, from text** | 106 | **0.943** | **0.620 / 0.928** vs 0.284 / 0.414 |

**The alias correction removed an artifact that hurt *both* signals.**
- 54 false ladder "errors" were really PDNC name variants. Disagreement had partly been "detecting" them through the shared name-format mechanism.
- After correction, XDIS still beats confidence by the same margin.

**The product list was expected to weaken XDIS. It strengthened it.** The reason is mundane (ENGINEERING_NOTES 23):
- The gold list held PDNC main names. qwen answered with the names the passage uses, and the parser could not match them: 149 unparsed answers, 137 of them this case.
- So the original experiment had under-measured the second view.

As a selective-risk control signal on PDNC, XDIS is therefore strong:
- At a 20% intervention budget, ladder error falls from 10.6% to 0.9% under P3, against 7.8% under P1.
- "Agree" certifies 85% of lines at 1.4% error.
- The mechanism is complementarity. The ladder's EXPLICIT tier states 0.95 confidence on 68 of the 106 errors. Confidence cannot rank those errors at all; disagreement catches 93% of them at a 20% budget.

**What it is not.**
- It is not a new result: cross-model disagreement exposing confidently-wrong outputs was published at ICLR 2026 (Part 4).
- It is not free of gold: the research ladder's name inventory is still PDNC's.
- It is not tested on the product's own web novels: no speaker gold exists there.

### 3. Layer 2: does the action causally change how an error manifests?

**The causal structure is X → Z → A → Y.**
- Intervene on Z: gold, or an injected wrong speaker.
- Intervene on A: narrator, generic or specific.
- Hold X and the renderer fixed.

**The answer is yes, and trivially so:**
- The specific voice manifests the error strongly: Δ = 0.87 / 0.35 / 0.74 for cross-gender, same-gender and addressee errors.
- The generic voice manifests it partly: 0.42 / 0.01 / 0.18.
- The narrator does not manifest it at all, by construction.

**The pre-registered triviality control decides what this means.**
- The voice geometry of the reference clips, with no audio at all, predicts the realised speaker-verification margins with R² = 0.95.
- It also predicts the same action order in every error type.
- Even the one effect that looked like a candidate phenomenon is predicted. The generic voice carrying the wrong *gender* on cross-gender errors (Γ = 0.53) matches the geometry's 0.55.
- That effect is the product rule's own definition (keep the predicted gender), not something the renderer adds.

**So "action-conditioned error amplification" exists, but as a definition.** The manifestation of an error under action a is, to within a 10% shrinkage, the embedding distance between the voice a selects under the error and the voice it selects under gold.

**This does not license a named quantity.**
- Δ_a is `d(voice_a(err), voice_a(gold))` in a speaker space.
- Calling it a new phenomenon would restate the cast table.

**The image arm (the H-VRUNG reread) shows the same shape for the same reason.**
- A framing hides the attribute it removes: distant hides gender, silhouette hides hair.
- It keeps the attribute it retains.
- Whether a *wrong* attribute shows depends on the rung *by design*.

**The non-definitional content left is small but real, and product-relevant:**
1. **The product's "unconfirmed" voice is a weak mask for cross-gender errors.** It removes only about 52% of their identity manifestation (0.42 of 0.87), because it keeps the disputed attribute. When disagreement is about *gender*, the rule should drop to the narrator or to a gender-neutral choice.
2. **Masking has a measured price on correct lines.** Identity margin falls by 0.21-0.25 for the generic voice and 0.22-0.51 for the narrator. A policy has to pay for false alarms, which is why a sharper signal matters.
3. **The narrator path showed the only fidelity anomaly.** One runaway render ran over 30 s, giving WER 0.145 vs 0.086. That is one event; it is not an effect of the action.

### 4. Layer 3: does disagreement select a safer action?

With the C3 cost table applied to the C2 rows (`action_policy`), the answer is yes:
- At a 20% budget routed to the narrator, P3 leaves 8% of the manifested error mass, against 58% for P1.
- It does so while paying *less* identity price (0.036 vs 0.055 per line), because it gates fewer correct lines.
- The generic action floors at 24% even under an oracle. That is point 1 above.

This is the selective-prediction frontier of layer 1, multiplied by the cost table of layer 2. The action choice is *coarsening under uncertainty*: specific → gender → root. That is the hedging / hierarchical selective classification policy family (Deng et al. 2012; Goren et al., NeurIPS 2024). Nothing in it is new mechanism.

### 5. Generalisation

The same causal structure exists in two modalities here:
- audio: voice commitment;
- image: framing commitment.

In both, the action-conditioned manifestation is what the action specification says it is. Dubbing and multi-speaker TTS share the structure on paper. No data for them was found, and the outcome would plausibly be the same definitional result.

A second domain does not rescue layer 2, because the issue is not domain-specific. It is that machine verifiers in the output space measure the action's own definition.

### 6. Where a genuine phenomenon could still live

Only in the observer: whether *perceived* cost tracks the geometry.
- H-HEDGE found the generator's identity is categorical.
- The categorical-perception literature (Latinus & Belin 2012) predicts listener cost is *not* linear in embedding distance.
- H-IOL's ideal-observer model predicts spillover costs on neighbouring lines.

These are claims about listeners. Machine verifiers cannot test them by construction, which is exactly what C3's R² = 0.95 shows. The no-large-study constraint therefore removes the only place the "masking/amplification" story could be non-trivial. A tiny 8-12 listener check could at most give a direction, not a paper result.

### 7. H-SELECT

It does not converge.
- "Limited rendering budget → choose where to commit" is the C3 policy layer, which is selective prediction with a cost table. XDIS already supplies the selection signal.
- "Which moments to illustrate" (H-SELECT's actual question) is a preference question with no error in it.
- Classification: **PRODUCT-ONLY**.

---

# Part 3: Experiments: frozen protocols and results


**Status of this file.** The three *protocol* sections below were written and
frozen on 2026-10-03, before any corrected or new number existed. The kill
criteria are copied verbatim into `hypotheses.toml`. The results sections at
the end were appended afterwards.

**What was seen before freezing.** One input count, and no result metric:
- Of the 1,000 H-XDIS gold labels, 942 are PDNC main names.
- Of the other 58:
  - a one-step rule (exact lowercase *or* `comparison_key`) resolves 54 uniquely and leaves 4 ambiguous;
  - those 4 are all honorific collisions created by `comparison_key` stripping titles ("Miss Tendril" vs "Mr Tendril", "Mr. Inglethorp" vs "Mrs. Inglethorp");
  - the tiered rule below resolves all 58 uniquely.

The tier order was chosen *because of* that count (exact match before
normalised match). That is a disclosed rule choice made on inputs, not on any
AUROC or capture number.

---

### C1: H-XDIS-ALIAS, PDNC gold-alias correction (CPU, saved trials only)

**Source.** `data/eval/research/H-XDIS/real-6f97e4d14f536dfe/trials.jsonl` (1,000 rows). It is never modified.

**Canonicalisation rule `canon(g)`, for a raw PDNC gold speaker string `g`, frozen:**
1. If `g` is a key of the novel's character list (a "Main Name"), return `g`.
2. Otherwise, collect the characters with `g.lower()` equal to the lowercase main name or any listed alias. If exactly one, return it.
3. If tier 2 is empty, collect the characters with `comparison_key(g)` equal to `comparison_key` of the main name or any alias. If exactly one, return it.
4. Otherwise, mark the row UNSCORABLE. It is excluded and counted, never guessed.

No token-subset, fuzzy, or edit-distance matching.

**Rescoring:**
- `ladder_err = canon(g) not in ladder_owners`;
- `llm_correct = (llm == canon(g))`;
- disagreement is unchanged, because the LLM outputs are fixed;
- `gold_in_shortlist` is recomputed against `canon(g)`.

**Gate.** Before canonicalising, the re-derived rows must reproduce the saved
`ladder_error`, confidence and owners exactly (the `gate_xdis._rederive`
gate). Otherwise the run aborts.

**Analysis.** `gate_xdis`'s functions, unchanged:
- policies P1, P2a, P2b, P2c, P3, C_shortlist_random and oracle;
- rates 5-30%;
- novel-cluster paired bootstrap, 2,000 resamples;
- the same strata.

**Change log.** Every row whose `ladder_err` or `llm_correct` changed, with
the raw gold, the canonical name, the owners and the reason, goes to
`changed_rows.jsonl` in the run directory.

**Kill and status map.** The H-GATE-XDIS map, applied to corrected labels:
- **KILL** if the best XDIS policy's errors-caught gain over P1 is < 0.15, or its CI includes 0, at both 10% and 20%.
- **CONDITIONAL** if it passes at exactly one rate.
- **PRODUCT-INFRA** if it passes at both rates but one of these holds:
  - the shortlist control reaches >= 80% of P2a's gain;
  - fewer than 2 strata support it;
  - capture at 10% is < 40%.
- **GREENLIGHT** otherwise.

---

### C2: H-XDIS-PS, product-built shortlist qwen rerun (the GPU gate)

**Sample.** The identical 1,000 quotes. They are re-derived with the H-XDIS
sampling code (same seed), and the unit ids must equal the saved trials'
or the run aborts.

**Candidate list, frozen.** Built by `product_shortlist(novel_text, q.start, q.end, ladder_raw, profile)`. Its signature takes no gold object.
1. **Window.** `text[q.start-2000 : q.start] + text[q.end : q.end+2000]`. The quote's own text is excluded.
2. **Detection.** Surfaces from the product's offline detector `mentions/ner.py::HeuristicDetector`.
3. **Keep a surface only if all of these hold:**
   - `mentions/chapter_ner.py::plausible_name` is true;
   - `comparison_key(surface)` is non-empty, which drops bare honorifics such as "Mr";
   - it is not a common noun by the product's corpus grammar test `mentions/commonness.py` (determiner/plural rate), with the profile built over the *whole novel text*. Volume-first processing, non-negotiable 6, makes the whole volume product-available;
   - it is capitalisation-consistent: across the whole novel, its case-sensitive occurrences are at least half its case-insensitive ones. This is the product's "names are capitalised consistently" assumption.
4. **Ladder surface.** Add `ladder_raw`, the surface the product's ladder emitted.
5. **Deduplicate and rank.**
   - Deduplicate by `comparison_key`, keeping the most frequent surface form.
   - Rank by in-window count (descending), then whole-novel count (descending), then alphabetically.
   - Keep the top 12. `ladder_raw` is always kept; if it ranked below 12th, it replaces the 12th.
6. **Order in the prompt.** Alphabetical, the same format as H-XDIS.

The procedure never uses PDNC's character list, aliases, gold speakers or
addressees, or gold windows.

**Prompt and model.** Byte-identical template to H-XDIS, except the list:
- qwen2.5:7b via ollama;
- temperature 0, seed 0, `num_predict` 16, `keep_alive` 30s;
- ±600-character passage.

**Answer parse.** As in H-XDIS: the longest candidate found
case-insensitively in the response, else unparsed.

**Product-side disagreement.** No alias index, since the product has none.
The answers agree if, after `comparison_key`:
- the keys are equal; or
- the non-empty token set of one is a subset of the other's.

An unparsed answer counts as disagree for P2a and P3. P2c keeps it as its own middle tier and remains exploratory.

**Scoring side.** Gold may be used here, and only here.
- The LLM surface maps to PDNC characters through `attribution_probe.alias_index`.
- `llm_correct_lenient = canon(g) in owners(llm)`.
- **Shortlist gold recall** = P(some candidate's owners contain `canon(g)`).
- The ladder error uses C1's `canon`.
- A secondary *alias-space* disagreement (`owners(llm)` and `owners(ladder)` are disjoint) is reported for comparison with H-XDIS only. It is not the primary measure, because the product cannot compute it.

**Controls:**
- **C_product_random:** the expected disagreement of a uniform pick from the same product list, `1 - |{c : comparison-agree(c, ladder_raw)}| / |list|`.
- **P1:** ladder confidence.

**Report:**
- qwen accuracy, overall and conditional on gold being reachable;
- AUROCs;
- P(err | agree) and P(err | disagree);
- curves for P1, P2a, P2c, P3, the control and the oracle;
- the H-GATE-XDIS operating metrics: errors caught, residual error, selective risk and capture efficiency;
- strata;
- bootstrap CIs;
- a side-by-side with C1, which uses the same alias-corrected labels and so isolates the shortlist effect.

**Kill.**
- **Primary:** the H-GATE-XDIS status map on this run.
- **COLLAPSE** (KILL of XDIS as a control signal) if either holds:
  - the primary fails at both 10% and 20%;
  - AUROC(P2a) − AUROC(P1) < 0.05.
- **Leakage:** C_product_random must not reach >= 80% of P2a's gain.

**Disclosed and not fixed:**
- The research adapter's ladder (`attribution_probe.probe`) builds its `known_names` from PDNC's character list. The user barred changing the ladder.
- An optional CPU sensitivity run (ladder `known_names` from the same product detector) is reported if run. It is never mixed into the primary.
- Pretraining contamination of qwen on Gutenberg text and PDNC cannot be tested from saved data.

---

### C3: H-ACT, action counterfactual (same error, different rendering)

**Causal structure.** X (source text) → Z (speaker inference) → A (rendering action) → Y (audio).
- We intervene on Z, setting it to gold or to an injected error.
- We intervene on A, setting it to narrator, generic or specific.
- X and every renderer setting are held fixed.

**Units:** 60 PDNC quotes, 20 per error type.

*Eligibility:*
- 40-220 characters;
- gold speaker is a main name with gender M or F.

*Wrong speaker,* drawn by `transforms/error_injection.inject` over the quote's local cast (the speakers and addressees within ±20 quotes, gold-derived; this is error *design*, not inference):
- **cross_gender:** a local-cast character of the other gender;
- **same_gender:** a local-cast character of the same gender;
- **addressee:** one of the quote's own gold addressees.

*Sampling:*
- Seeded order, round-robin over novels.
- A unit is kept only if gold and wrong speaker get distinct cast voices.

**Voices:**
- **Bank:** the 22 EARS voices.
- **Narrator:** the bank voice nearest the Chatterbox-VE centroid, the same rule as H-COST (`error_cost_stimuli`).
- **Casting:** per novel, `controllers/casting.cast(mode="diverse")` over the bank *minus the narrator*, in prominence order, with the H-GATE seed scheme.

**Actions:**
- **A narrator:** the narrator voice.
- **B generic:** replicates `pipeline/voice/runner.py:334-347`, the unconfirmed-speaker rule. It is a voice of the *predicted* speaker's gender, excluding:
  - the predicted speaker's own cast voice;
  - the narrator;
  - every voice cast in the novel's local cast window (the product excludes voices already used in the chapter).

  The pick is deterministic: `derive_seed(base, unit, "generic", predicted)`. If the pool is empty, fall back to the same-gender bank minus own and narrator.
- **C specific:** the predicted speaker's cast voice.

**Renders per unit.** Z = err is predicted = wrong; Z = gold is predicted = gold.
- specific: under err and under gold (2 renders);
- generic: under err and under gold (2 renders);
- narrator: 1 render, used for both Z values because the narrator output does not depend on Z;
- second seed, specific under err and under gold: 2 renders, to estimate render noise.

**TTS settings:**
- Chatterbox through the product engine (`pipeline/voice/engine.py`), default `exaggeration` and `cfg_weight`;
- `torch`, `random` and `numpy` seeded with `derive_seed(base, unit, voice, seed_idx)` immediately before each call;
- reference clip = the EARS neutral clip.

**Measurements.** Run after TTS is released from the GPU.
- **Speaker identity.** `microsoft/wavlm-base-plus-sv` x-vectors, independent of the generator.
  - `sim(Y, ref_v)` = cosine to the reference clip of voice v.
  - identity margin `m(Y) = sim(Y, ref_gold_voice) − sim(Y, ref_wrong_voice)`, where the gold and wrong voices are the cast voices of the gold and injected-wrong speakers.
- **Gender cue.**
  - `g(Y) = cos(Y, centroid_F) − cos(Y, centroid_M)` over the WavLM embeddings of the reference clips;
  - F0 median from librosa `pyin`.
- **Transcript fidelity.** whisper-small (English, greedy decoding), then WER against the quote text after lowercasing, stripping punctuation and collapsing whitespace.
- **Cost.** Duration and wall-clock synthesis time.
- **Secondary only.** Chatterbox VoiceEncoder similarity. It is the generator's own space, so it is circular.

**Manifestation.**
- The Z-contrast under action a is `Δ_a = m(Y | Z=gold, a) − m(Y | Z=err, a)`. Higher means the error shows more.
- Narrator: Δ = 0 by construction, because the render is identical. This is stated, not tested.
- Gender-manifestation contrast: `Γ_a = |g(Y|Z=err,a) − g(Y|Z=gold,a)|`.

**Questions, frozen:**
- **Q1.** Is Δ_specific − Δ_narrator > 0 per error type, by a paired bootstrap 95% CI over units?
- **Q2.** On cross-gender errors, is Γ_generic > 0 (generic masks identity but leaks the wrong gender)? And is Δ_generic < Δ_specific?
- **Q3, price of masking.** On correct lines, how much smaller is m(Y | Z=gold) under narrator and under generic than under specific?
- **Triviality control.**
  - Predict every render's m(Y) from reference-clip geometry alone: `m̂ = cos(ref_rendered_voice, ref_gold) − cos(ref_rendered_voice, ref_wrong)` in WavLM space, with no audio.
  - DEFINITIONAL if R²(m, m̂) >= 0.9 and the action ordering of mean Δ is the same as predicted, in every error type.
  - PHENOMENON requires Q1 and a systematic residual: R² < 0.9, an ordering reversal, or unpredicted gender leakage.
- **Manipulation check, a precondition.** `voice_geometry.identify` (Chatterbox VE nearest bank voice) on the Z = gold specific renders must return the cast voice for at least 90% of units. Otherwise the run is INVALID.

**Policy layer (CPU, after C2 and C3).**
- Map each real ladder error in the C2 rows (by gold vs predicted gender: cross or same) to the C3 mean Δ_a for its type.
- Map each correct line to the C3 Q3 price of masking.
- For budgets k, gate the top-k lines by each signal (P1, P2a, P3, random, oracle) to generic, or to narrator, and leave the rest specific.
- Report the frontier: manifested error mass against identity price paid.
- This is descriptive. A risk signal "selects a safer action" only if the frontier under P3 dominates P1's.

**Image arm (CPU reanalysis, no renders).**
- In H-VRUNG run `real-a89a29764cb7eea2`, the "in" variant's prompted gender and hair stand in for an upstream attribute that may be wrong.
- Per rung, the manifestation is the probe recovery rate of the prompted attribute (llava forced choice, CLIP argmax), with Wilson CIs.
- The gender × hair interaction is reported alongside: which rung masks which attribute.

---

### Results (appended 2026-10-03, after the runs)

#### C1: H-XDIS-ALIAS. **CONDITIONAL; the advantage survives, the verdict is unchanged**

Run `data/eval/research/H-XDIS-ALIAS/real-4fe36b54f7f8328b`.
- **Exact-match gate:** 1000/1000.
- **Labels:**
  - The tiered rule resolved all 58 name-variant gold labels. None were UNSCORABLE.
  - 54 rows flipped from ladder error to correct; none flipped the other way.
  - 9 LLM answers flipped from wrong to right.
  - Ladder errors fell from 160 to **106**.
  - The full change log is in `results.json → summary.changed_rows`.
  - Largest groups:

    | Gold name | Rows | PDNC alias of |
    |---|---|---|
    | "Kemp" | 12 | "The Doctor" |
    | "Lucy" | 12 | "Miss Honeychurch" |
    | "Dorian Gray" | 12 | "Prince Charming" |
    | "Ellen Olenska" | 5 | — |
    | "Cecil" | 3 | — |

  - One row ("Josie Pye" → "Aunt Josephine") follows PDNC's own alias list, which looks wrong there. It was kept by rule.

**Gating results:**

| Policy | AUROC | Caught @10% | Caught @20% | Selective risk @20% |
|---|---|---|---|---|
| P1 confidence | 0.631 | 0.284 | 0.414 | 0.078 |
| P2a disagreement | 0.833 | 0.326 | 0.653 | 0.046 |
| P3 disagree→conf | 0.877 | **0.424** | **0.691** | 0.041 |
| shortlist-random control | 0.473 | 0.107 | 0.197 | 0.106 |

**P3 − P1** (novel-cluster CI):
- +0.140 [0.079, 0.213] at 10%, below the 0.15 bar;
- +0.277 [0.132, 0.431] at 20%.

So the verdict is **CONDITIONAL**, the same as before the correction.
- The EXPLICIT-tier errors (68) are still the mechanism. P1 catches 0.00 of them at 10% review and P3 catches 0.22; at 20%, 0.09 vs 0.64.
- Narrator-fallback gap closed: P3 0.76 vs P1 0.26.

#### C2: H-XDIS-PS. **GREENLIGHT by the frozen map; no collapse**

Run `data/eval/research/H-XDIS-PS/real-2745361d4136dce5`. Same 1,000 units (id gate passed), alias-corrected labels (106 errors).
- **Product list:** gold recall 0.972; mean 10.5 names.
- **qwen accuracy:** 0.919 overall and 0.946 when the gold speaker is reachable. The gold-shortlist run, alias-corrected, had 0.76. Only 9 answers were unparsed, against 149 before.
- **Disagreement:**
  - rate 0.148;
  - P(err | disagree) = 0.635;
  - P(err | agree) = **0.014**.

| Policy | AUROC | Caught @5% | @10% | @20% | @30% | Selective risk @20% |
|---|---|---|---|---|---|---|
| P1 confidence | 0.631 | 0.142 | 0.284 | 0.414 | 0.487 | 0.078 |
| P2a disagreement | 0.913 | 0.300 | 0.599 | 0.894 | 0.907 | 0.014 |
| P3 disagree→conf | **0.943** | 0.342 | **0.620** | **0.928** | 0.957 | **0.009** |
| C_product_random | 0.515 | 0.051 | 0.103 | 0.206 | 0.309 | 0.105 |
| oracle | 1 | 0.472 | 0.943 | 1 | 1 | 0 |

- **P3 − P1:** +0.336 [0.233, 0.486] at 10%, and about +0.51 at 20%, CI [0.411, 0.631].
- **Control:** below P1. Its ratio to P2a's gain is negative, so there is no list artifact.
- **Strata at 20%:**

  | Stratum | P3 | P1 |
  |---|---|---|
  | addressee capture | 0.93 | 0.43 |
  | cross-gender | 0.90 | 0.42 |
  | same/unknown gender | 0.94 | 0.41 |
  | EXPLICIT tier | 0.93 | 0.09 |

- **Narrator-fallback gap closed:** P3 0.88 vs P1 0.26.
- **Alias-space disagreement** (secondary, not product-computable): AUROC 0.919.

**Why the product list did *better* than the gold list (diagnosed after the run).**
- 137 of the 149 H-XDIS unparsed answers were qwen naming the form the passage uses ("Syme", "Pooh", "Miss Howard").
- The gold list held PDNC main names ("Gabriel Syme", "Winnie-the-pooh").
- So the original run under-measured qwen and inflated "disagreement" with parse failures.
- The product list is drawn from the text, so it does not have this problem (ENGINEERING_NOTES 23).

**Remaining gold dependence and caveats:**
- The research ladder's `known_names` still come from PDNC's character list. The optional sensitivity run was **not run**.
- qwen pretraining contamination is untested.
- PDNC only: public-domain 19th- and 20th-century English, not the product's web novels.

#### C3: H-ACT audio arm. **DEFINITIONAL; the causal effect is real, the phenomenon claim is killed**

Run `data/eval/research/H-ACT/real-b01eac13f33ad227`. 60 units (20 per type), 415 Chatterbox renders, narrator `earsp033`.

**Preconditions:**
- Manipulation check: **0.90**. It passes exactly at the threshold, so 6 of 60 Z = gold specific renders were nearest a different bank voice.
- Seed noise in the specific-voice margin: 0.035 [0.027, 0.045].

**Manifestation Δ** (WavLM-SV margin toward the gold voice, gold render minus error render), with geometry-predicted values in parentheses:

| Error type | Δ specific | Δ generic | Δ narrator | Specific − generic |
|---|---|---|---|---|
| cross-gender | 0.873 [0.754, 0.977] (0.997) | 0.416 [0.317, 0.519] (0.465) | 0 | 0.456 [0.340, 0.579] |
| same-gender | 0.350 [0.279, 0.423] (0.442) | 0.013 [−0.022, 0.057] (0.021) | 0 | 0.338 [0.274, 0.403] |
| addressee | 0.738 [0.617, 0.860] (0.823) | 0.185 [0.042, 0.324] (0.203) | 0 | 0.553 [0.448, 0.661] |

- **Q1:** passes in every type. The action changes the error's manifestation, causally.
- **Q2, gender carry-over:**
  - The generic voice still carries the wrong *gender* on cross-gender errors: Γ = 0.531 [0.460, 0.598].
  - The geometry predicts 0.547. The excess is −0.016 [−0.049, 0.016]: **no unpredicted leakage**.
  - The carry-over is the product rule's own design: the unconfirmed voice keeps the *predicted* gender.
- **Q3, price of masking on correct lines:**

  | Error type | Generic | Narrator |
  |---|---|---|
  | cross-gender | 0.245 | 0.507 |
  | same-gender | 0.213 | 0.219 |
  | addressee | 0.248 | 0.324 |

- **Triviality control:**
  - Realised margin against reference-clip geometry: **R² = 0.95**, slope 0.90, intercept −0.001.
  - The action order is the same as predicted in every type.
  - The audio adds only a uniform shrinkage of about 10%.
  - The status is therefore **DEFINITIONAL**: choosing a voice changes which voice is heard, in the amount the cast table says.
- **Fidelity and cost on correct lines:**
  - WER: specific 0.086, generic 0.086, narrator 0.145 [0.053, 0.314]. One runaway render ran over 30 s (ENGINEERING_NOTES 25).
  - Duration: 6.7-7.3 s.
  - There is no fidelity effect of the action apart from that runaway render.

#### C3 policy layer (`action_policy`)

Run `data/eval/research/H-ACT/real-226129dbf767bac9`.
- **Inputs:** the C2 rows joined with the C3 cost table.
- **Measure:** the share of all-specific manifested error mass left in the output. Identity price per line is in parentheses.

| Budget | Gate to | P1 | P3 | Oracle |
|---|---|---|---|---|
| 10% | narrator | 0.711 (0.024) | 0.385 (0.012) | 0.057 |
| 20% | narrator | 0.583 (0.055) | **0.080** (0.036) | 0 |
| 20% | generic | 0.684 (0.037) | 0.296 (0.024) | **0.239** |

- P3 **dominates** P1 on both axes: less error left *and* less identity spent, because it gates fewer correct lines.
- The product's generic "unconfirmed" voice has a floor of 0.24 even under an oracle, because it keeps the predicted gender on cross-gender errors.
- This is H-GATE-XDIS's capture curve weighted by a cost table. It adds no mechanism beyond selective prediction.

#### C3 image arm (`vrung_manifestation`)

A reread of H-VRUNG `real-a89a29764cb7eea2`, CPU only.
- **Committed framing:** shows the prompted, possibly wrong, gender/hair at 0.95/0.85 (CLIP); llava gives 0.90/0.90.
- **Masking relative to committed (CLIP):**

  | Framing | Gender | Hair |
  |---|---|---|
  | distant | −0.40 | −0.20 |
  | silhouette | −0.05 | −0.25 |
  | crop | −0.10 | −0.15 |
  | back view | 0.00 | +0.15 |

- **Selectivity:**
  - silhouette hides hair but not gender;
  - distant hides gender, and the person is visible in only 35% of those panels.
- The same structure as the audio Q2: an action masks the attribute its rendering removes and keeps the one it retains.
- It is also *by design*, and confounded by "nobody drawn".
- 20 beats, attribute probes only.

---

### S1: ladder name-inventory sensitivity (protocol frozen 2026-10-03, before running)

**The last gold dependence in C2.** The research adapter hands the ladder
`known_names` built from PDNC's character list and aliases
(`attribution_probe.probe`). The product would build that inventory from its
own mention detection.

**Product inventory, frozen.** Per novel, over the whole text (volume-first):
1. `HeuristicDetector` surfaces.
2. Kept only if all of these hold:
   - they pass `plausible_name`;
   - `comparison_key` is non-empty;
   - they are not a common noun (`commonness`, whole novel);
   - case-sensitive occurrences are at least half of case-insensitive ones;
   - **the whole-novel case-sensitive count is at least 3.** The product's gazetteer also needs repeated support.
3. `known_names` = each kept surface, its lowercase form and its `comparison_key`, plus each capitalised token longer than 2 characters of a multi-token surface that is not in the probe's `_NOT_NAME_TOKENS`. This mirrors the token expansion `alias_index` applies to PDNC names.

**Run.**
- Same 1,000 units, same product shortlist procedure, same prompt and model.
- The cached qwen answers are reused wherever the candidate list is unchanged. A changed ladder surface can change the list, and those units are re-asked.

**Scoring.**
- Unchanged: alias-corrected gold, and owners of the ladder surface through PDNC's `alias_index`. The scoring side may use gold.
- A unit the ladder now leaves **unresolved** is excluded from the gating analysis and counted. The product renders it with the narrator already, so it is not a committed error.

**Reported:**
- units changed, newly unresolved and newly wrong;
- the new ladder error rate;
- the full H-GATE-XDIS operating table on the still-resolved units.

**Decision rule** (from Part 1 answer 13): the product claim **weakens** if P3's capture at 20% review falls below 0.70. If it stays at 0.70 or above, the XDIS-PS result is independent of PDNC's name inventory.

### S1 result: **PASSES; XDIS-PS does not depend on PDNC's name inventory**

Run `data/eval/research/H-XDIS-PS/real-255962a04945d31a`.
- **Inventory:** about 285 entries per novel.
- **Ladder changes:**
  - 48 of the 1,000 units become unresolved. They are excluded, and the product renders them with the narrator.
  - Only **2** predictions change.
  - 952 units remain, with 95 errors.
- **Results:**

  | Policy | AUROC | Caught @10% | Caught @20% |
  |---|---|---|---|
  | P1 confidence | 0.637 | 0.424 | 0.424 |
  | P2a disagreement | 0.913 | 0.627 | 0.892 |
  | P3 disagree→conf | **0.943** | 0.651 | **0.929** |
  | control | 0.531 | 0.107 | 0.215 |

  - P3 − P1 CI: [0.244, 0.523] at 10%, [0.376, 0.639] at 20%.
  - qwen accuracy 0.924; P(err | agree) 0.013.
- **qwen calls:** cached answers were reused for 950 units. The 2 units whose candidate list changed were asked live.
  - Their first live answers came back as empty strings. Re-asked directly, qwen gave "Adye" (gold: Colonel Adye), so the empty strings were transient (ENGINEERING_NOTES 26).
  - The empty answers were dropped from the cache and the run repeated. The final answers are "May's" and "Adye".
  - A provisional CPU-only run that counted those 2 units as disagree gave 0.931 at 20%, inside its stated ±0.02 bound.

---

# Part 4: Prior-art recheck


**The claim checked:**

> Independent disagreement finds upstream errors that native confidence
> misses. The downstream rendering action changes how those errors manifest.
> Disagreement can select a safer action, and this generalises across
> modalities.

**Method.**
- Adversarial web search on 2024-2026 work, one query per layer, listed below.
- The two closest hits were read directly.
- This is not a systematic review. A miss here is a reason to search more, not evidence of novelty.

**Queries:**
- model disagreement for selective prediction;
- the hedging / accuracy-specificity trade-off and hierarchical selective classification;
- learning to defer and multi-class abstention;
- uncertainty-aware generation and image generation;
- error propagation in cascaded speech pipelines and dubbing;
- causal and counterfactual error propagation in multi-stage generative pipelines;
- speaker attribution with multi-speaker TTS and audiobooks;
- quotation attribution on PDNC;
- patents on narrator fallback under attribution uncertainty.

### Layer by layer

| Layer | Closest work | What it already does | What it does not do | Verdict |
|---|---|---|---|---|
| **1. Disagreement finds the errors confidence misses** | "Complementing Self-Consistency with Cross-Model Disagreement for Uncertainty Quantification" (ICLR 2026) | Black-box cross-family disagreement as an epistemic term. The "confidently wrong" framing: in the low-self-uncertainty group, incorrect answers have higher cross-model disagreement. AUROC +0.13 to +0.15; AURC improved by 15% in selective prediction. | It does not use disagreement for anything but answer/abstain. Its signals are LLM vs LLM, not a rule system vs an LLM. | **Covered.** H-XDIS's "EXPLICIT-tier 0.95 lines: confidence catches 0%, disagreement catches most" is this paper's finding in a new domain. |
| | Cross-Model Disagreement as a Label-Free Correctness Signal (arXiv 2603.25450); Multi-LLM Disagreement as a Detector of Human Annotation Errors (medRxiv 2026); Experts Rise Where LLMs Disagree (arXiv 2609.26926) | Disagreement for routing, error flagging, and targeting expert effort under budget. | No downstream rendering. | Covered (review-budget targeting). |
| | Query-by-committee and ensembles (classical) | Committee disagreement for selection. | — | Covered; already pre-declared in H-XDIS. |
| **2. The downstream representation changes how an upstream error manifests** | "The Hallucination Snowball" (Singh & Pawar, arXiv 2608.14588) | Injects false facts after stage 1 of a 4-agent text pipeline. Detection falls from 72% to 51% as the error is *transformed*: fact, then computation, then prose, then conclusion. "The pipeline, not the hallucination itself" creates invisibility. Escape probabilities are measured per transition. Proposes verification gates at handoffs. | Text agents only. Varies the *stage*, not a chosen rendering action. No modality, no voice or image. | **Largely covered** as a phenomenon: representation-dependent detectability under error injection. |
| | CausalFlow (arXiv 2605.25338); EDGE error-dependency graphs (2609.01360); causal failure attribution in agentic RAG (2608.20627) | Step-level counterfactual interventions that re-execute downstream steps and label errors disappeared, weakened, strengthened or emerged. | Agent traces, not media rendering. | Covered as *methodology* (counterfactual intervention on pipeline stages). |
| | Cascaded speech translation error propagation (e.g. arXiv 2502.00377) | ASR errors compound through MT. | No action choice that changes cost. | Adjacent. |
| **3. A risk signal selects a safer (less specific) action** | "Hedging Your Bets" (Deng et al., CVPR 2012; also a granted US patent, 9,779,291) | Under uncertainty, predict a coarser node of a hierarchy ("mammal", not the species) to trade specificity for accuracy. | — | **Covered.** The generic voice is "predict the gender node instead of the character leaf". The narrator is "predict the root". |
| | Hierarchical Selective Classification (Goren, Galil & El-Yaniv, NeurIPS 2024) | Hierarchical risk-coverage curves; inference rules that climb the hierarchy under uncertainty; accuracy guarantees. | No downstream rendering cost. The hierarchy's cost is semantic, not measured from generated output. | **Covered** (the policy family and its evaluation curves). |
| | Learning to defer / predictor-rejector multi-class abstention (Mao et al. 2024; DeCCaF, arXiv 2403.06906) | Cost-sensitive abstention and deferral with instance- and label-dependent costs and capacity constraints. | — | Covered (cost-sensitive multi-action selection under budget). |
| **4. Uncertainty-aware generation in TTS or image** | Risk-Aware Image Generation (Perez et al., ICML-W 2023); Ctrl-U (arXiv 2410.11236) | Propagate input/latent uncertainty to output regions; use uncertainty in reward models. | Uncertainty is about the generator, not an upstream semantic decision. No choice of a less committal render. | Adjacent; does not cover. |
| | MultiActor-Audiobook (arXiv 2505.13082); Audiobook-CC (arXiv 2509.17516); open-source LLM-attributed audiobook tools | LLM speaker attribution feeding multi-voice TTS. | No attribution uncertainty, and no fallback policy that is measured. | Does not cover, but these show the problem is real and current. |
| | PDNC quotation attribution SOTA: 94.5% (arXiv 2608.02359); Llama-3 evaluation (NAACL 2025) | Strong attributors. The Llama-3 paper argues memorisation does not explain its gains. | Attribution only. | Context: a 7B LLM as the second "view" is far from SOTA. Contamination risk is acknowledged in the field. |
| | Dubbing: industry write-ups say speaker *confusion* errors are the most damaging. Patent US20140029757A1 gives a confidence measure for diarization. | — | No rendering-policy study. No machine-measured action-conditioned cost. | Gap (thin). |

### What remains

**1. Layers 1 and 3 are not novel.**
- Disagreement exposing confidently-wrong errors is published, ICLR 2026.
- Backing off to a coarser output under uncertainty is published: Deng 2012, and Goren et al. 2024 with risk-coverage machinery.
- Cost-sensitive deferral covers budgeted multi-action selection.
- An EchoTales paper whose contribution is "use disagreement to pick a coarser voice" would be an *application* of these. Reviewers would say so.

**2. Layer 2 is covered as a phenomenon in text pipelines** by "Hallucination Snowball": the downstream stage changes detectability. The specific variant not found is narrower:
- the *chosen output action* of a media renderer (narrator, generic or specific voice; committed or hidden framing) as the intervention;
- with the *same* upstream error held fixed;
- measured by independent machine verifiers in the output modality.

**3. Whether that narrow gap is science or bookkeeping depends on C3.**
- If the realised effect is the cast geometry restated (choose a voice, hear that voice), the gap is filled by a definition, not a finding.
- It survives as research only if something *not* predicted by the action's specification shows up in the output, for example:
  - a generic voice that still carries gender;
  - an image framing that hides hair but not gender;
  - a TTS that fails to realise the distinction.

**4. Patents.**
- Deng et al.'s hedging method is itself patented (US 9,779,291). A claim of "choose a coarser output class under uncertainty" therefore has direct prior art.
- No patent was found on attribution-uncertainty-gated voice fallback for audiobooks. That is weak evidence, from a non-exhaustive search.
- A mechanism would need to be specific: cross-system disagreement between a deterministic rule ladder and an independent model, gating per-line voice commitment, with a measured action-conditioned cost table. Even then, the inventive step over Deng combined with a disagreement detector looks thin.

### Sources

- [Complementing Self-Consistency with Cross-Model Disagreement for Uncertainty Quantification (ICLR 2026 notes)](https://en.papernotes.org/ICLR2026/llm_evaluation/complementing_self-consistency_with_cross-model_disagreement_for_uncertainty_qua/)
- [Cross-Model Disagreement as a Label-Free Correctness Signal](https://arxiv.org/pdf/2603.25450)
- [Multi-LLM Disagreement as a Scalable Detector of Human Annotation Errors](https://www.medrxiv.org/content/10.64898/2026.05.04.26352392v1.full)
- [Experts Rise Where LLMs Disagree](https://arxiv.org/abs/2609.26926v1)
- [The Hallucination Snowball](https://arxiv.org/html/2608.14588v1)
- [CausalFlow](https://arxiv.org/pdf/2605.25338)
- [EDGE: Error Dependency Graph-Guided Multi-Error Attribution](https://arxiv.org/pdf/2609.01360)
- [When Failures Propagate: Causal Failure Attribution in Agentic RAG](https://arxiv.org/pdf/2608.20627)
- [When End-to-End is Overkill: Rethinking Cascaded Speech-to-Text Translation](https://arxiv.org/html/2502.00377)
- [Hedging Your Bets (Deng et al., CVPR 2012)](http://vision.stanford.edu/pdf/DengKrauseBergFei-Fei_CVPR2012.pdf)
- [US patent 9,779,291: optimizing accuracy-specificity trade-offs](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9779291)
- [Hierarchical Selective Classification (NeurIPS 2024)](https://proceedings.neurips.cc/paper_files/paper/2024/file/c8b100b376a7b338c84801b699935098-Paper-Conference.pdf)
- [Predictor-Rejector Multi-Class Abstention](https://arxiv.org/pdf/2310.14772)
- [Cost-Sensitive Learning to Defer to Multiple Experts (DeCCaF)](https://arxiv.org/pdf/2403.06906)
- [Risk-Aware Image Generation by Estimating and Propagating Uncertainty](https://openreview.net/pdf/b87c4b3ea2a93b7598f7755da2b72341fb7175f0.pdf)
- [Ctrl-U](https://arxiv.org/pdf/2410.11236)
- [MultiActor-Audiobook](https://arxiv.org/pdf/2505.13082)
- [Audiobook-CC](https://arxiv.org/pdf/2509.17516)
- [Fast and Accurate Quotation Attribution in Literary Texts](https://arxiv.org/html/2608.02359v1)
- [Evaluating LLMs for Quotation Attribution in Literary Texts (NAACL 2025)](https://aclanthology.org/2025.naacl-short.62.pdf)
- [Speaker diarization for AI dubbing (pyannoteAI)](https://www.pyannote.ai/blog/speaker-diarization-for-ai-dubbing-and-localization)
- [US20140029757A1: confidence measure for speaker diarization](https://patents.google.com/patent/US20140029757)
