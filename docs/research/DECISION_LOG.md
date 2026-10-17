# Decision log

Append-only. Each entry: hypothesis, pre-registered kill criterion, result
with numbers, verdict, artifact. The machine-checked status lives in
`packages/research/src/echotales/research/hypotheses.toml`.

## 2026-10-02: first pass

### H-CAL: pipeline attribution confidence is a usable posterior. **KILLED**

- **Kill criterion:** AUROC < 0.6 or tier accuracy not monotone in confidence.
- **Method:** the product's speaker ladder (`attribute_span`, tiers 1-3; the LLM tier excluded for reproducibility) run on all 28 PDNC novels, 36,991 gold quotes. Scored strict (the surface name denotes exactly the gold speaker) and lenient (the gold speaker is among the surface's owners).
- **Results:**
  - Coverage 9.9% of quotes.
  - Accuracy on resolved quotes: 74.8% strict, 84.0% lenient.
  - EXPLICIT tier states 0.95, measures 86.7% lenient [Wilson strict 76.4-79.3%]; n = 3,214.
  - PROXIMAL tier states 0.75, measures 63.8% lenient; n = 431.
  - ECE 0.179. AUROC 0.573 strict / 0.590 lenient (below 0.6). Tiers are monotone.
  - **Errors:** 52.3% addressee capture; 41.5% cross-gender. When the predicted name is a vocative inside the quote, accuracy is 18.2% (n = 44), against 84.8% otherwise.
- **Verdict:** the constants are not a usable posterior, so any confidence-conditioned policy needs a recalibrated or learned posterior.
- **What it teaches:** addressee capture, seen in the web novels (EVOLUTION 4.87/4.88), is the dominant error class on independent human gold too.
- **Artifact:** `data/eval/research/H-CAL/real-a5524f970cf9ab0f/results.json`.
- **Bug found and fixed during the run:** an alias index mapped the pronoun "She" to a descriptive PDNC character name; gold "Unknowable" quotes were being scored. Both fixed before the reported numbers.

### H-GATE: gating beats random; distinctiveness unmasks errors. **SURVIVING (weak on the policy half)**

- **Kill criterion:** masked share equal across casts, or the paired-bootstrap CI of the AURC difference includes 0.
- **Method:** real errors from the ladder on PDNC (3,424 resolved lines with cast voices; 362 errors). Each novel's characters cast onto 22 native-English EARS voices, either homogeneous (centroid-nearest pool) or diverse (farthest-point). Salience proxy: Chatterbox speaker-embedding cosine distance between the wrong and right voice.
- **Masking results:**
  - Homogeneous cast: 22.4% of errors land on the same voice; mean error distance 0.095.
  - Diverse cast: 2.2% on the same voice; mean error distance 0.186.
  - About 43% of errors are gender flips under both.
- **Gating results:**
  - Tier confidence beats random. Diverse: Δ AURC 0.0015 [0.0008, 0.0027]. Homogeneous: 0.0007 [0.0003, 0.0014].
  - But it closes only **17.8%** (diverse) and **15.5%** (homogeneous) of the random-to-oracle gap. The vocative penalty helps a little.
- **Verdict:** the objective precondition for the distinctiveness × accuracy crossover holds. A commitment *policy* is capped by posterior quality, so the perceptual science (H-COST) must not depend on the posterior.
- **Caveat:** embedding distance is not perception (categorical identity perception), so this is a stimulus-design variable, not a result about listeners.
- **Artifact:** `data/eval/research/H-GATE/real-9f0a4af1ffd3116a/results.json`.

### H-COST: rendering-dependent perceptual error cost. **OPEN (study ready, needs listeners)**

- **Built:**
  - 12 PDNC passages (6-10 quotes, mixed-gender casts, ≥2 implicit quotes). 336 condition scripts (rate {0, .15, .35} × type {addressee, cross_gender, same_gender} × cast {homogeneous, diverse} × policy {full_cast, narrator_only}). 24 comprehension probes on implicit quotes, never corrupted themselves.
  - Latin-square listening page, cluster-bootstrap analysis, power simulation.
- **Pilot audio:** passage 0, 4 conditions, 26 Chatterbox calls in 98 s.
- **Manipulation check:** 10/10 rendered quote lines (including all 4 injected ones) are nearest to their intended voice in speaker-embedding space (cosine 0.79-0.92).
- **Design issues found:**
  - Same-gender errors realise at about half the requested rate, because many passages have one speaker per gender. Either select passages with ≥2 speakers per gender or report realised rates.
  - Narrator-only renders run about 30% longer (60 s vs 46 s), so duration is a confound for enjoyment. Control it (time-normalise, or add duration as a covariate).
- **Power:** at an assumed −0.15 probe-accuracy interaction, 12 / 24 / 40 listeners give 38% / 57% / 75%. A decisive run needs about 50 listeners or more probes per passage.
- **Artifact:** `data/eval/research/H-COST/real-14034e3f106cb8ff/results.json`.

### H-HEDGE: posterior-weighted voice interpolation is a graded hedge. **KILLED (machine level)**

- **Kill criterion:** identity change concentrated (>60%) at the discrete prompt switch for every pair.
- **Method:** interpolate Chatterbox's continuous conditioning (T3 speaker embedding, S3Gen x-vector) between two voices, α ∈ {0, .25, .5, .75, 1}. The discrete speech-token prompt and reference mel switch at α = 0.5. Two pairs, two sentences each. Identity measured as relative similarity to A and B.
- **Results:** step share 0.823 and 0.827. Moving α from 0 to 0.25 changes identity by 0.005 and 0.021.
- **Verdict:** the generator cannot express a graded hedge, which agrees with the categorical-perception literature.
- **Caveat:** single-sentence nearest-voice identification is noisy (a "third identity" in 2/4 of the *endpoint* clips), so no phantom-speaker claim is made. A listener test would only add a human confirmation of an already-dead method.
- **Artifact:** `data/eval/research/H-HEDGE/real-4796b27b4fa9dfbb/results.json`.

### H-SELECT: moment selection is not settled by cheap notions. **OPEN (precondition met)**

- **Kill criterion (precondition part):** max non-random pair Jaccard ≥ random floor + 0.15.
- **Results:**
  - 13 public-domain chapters, 671 beats, budget 20%: best pair (drama vs visual lexicon) Jaccard 0.22 against a random floor of 0.16. Precondition met.
  - With a local LLM on 3 chapters / 217 beats: the LLM agrees with the visual-lexicon proxy (Jaccard 0.33, floor 0.11) but not with the drama heuristic (0.15) or dialogue density (0.03).
- **Next:** the pairwise annotation study (built).
- **Artifacts:** `data/eval/research/H-SELECT/real-0b1915448bceb49f/results.json`, `data/eval/research/H-SELECT/real-llm-4x1/results.json`.

### Parked without running

- **H-XMOD:** no labels. The human correction log has 34 speaker corrections, most with stale span IDs.
- **H-CRN:** same data limit, and it overlaps the killed interface direction.

### Prior-art outcomes

- 9 candidates rejected outright, 6 parked (the kill analysis doc was removed 2026-10-03; these verdicts are its record).
- No mechanism qualifies as PATENT-CANDIDATE. The one concrete mechanism (hedged rendering) is dead.

## 2026-10-02: mutation lab, wave 1

The catalog, prior-art and kill-matrix docs were removed on 2026-10-03 once the
convergence pass superseded them; the verdicts below are their record. All kill criteria
below were registered in `hypotheses.toml` before the experiment code
existed. Every number is model- or machine-level unless it says otherwise:
no human data exists yet.

### H-JUDGE-A: audio-LLM judges miss voice-only misattribution. **KILLED (prior art, not run)**

- SpeakerSleuth (arXiv 2601.04029): 12 audio LMs prioritise text over
  acoustics and miss even gender switches in multi-turn dialogue. HEAR
  (2608.29120) shows the same for speaker attribution. No experiment could
  add more than a domain transfer.

### H-IOL: an ideal-observer listener predicts non-uniform, spillover costs. **SURVIVING (model level)**

- **Kill criterion:** spillover < 0.25 x direct cost at the default
  listener, or the sign of P1, P2 or P3 flips anywhere in the 24-setting grid.
- **Method:** a Bayesian listener (`models/listener.py`) that learns
  voice -> character from tagged lines.
  - **Passages:** 90 PDNC windows of 60 quotes from 24 novels.
  - **Casts:** EARS voices, diverse or homogeneous.
  - **Errors:** injected by measured type at 10-60%, plus fixed-count
    placement (tagged vs implicit) and position (early vs late).
  - **Robustness:** a 24-setting grid over confusability tau, anaphora
    reliability, turn prior and self-training.
- **Results (default listener):**
  - **P1 spillover:** 0.106 comprehension per error is lost on *correctly
    rendered* lines, against 0.142 on the corrupted lines themselves. Ratio
    0.744, novel-cluster bootstrap CI [0.714, 0.784]. Holds in 24/24
    settings (ratio 0.69-0.81).
  - **P2 tag poisoning:**
    - An error on a tagged line costs 0.014 directly but 0.413 in spillover.
    - An implicit-line error costs 0.369 directly but 0.089 in spillover.
    - Tagged minus implicit spillover is +0.32 (CI [0.24, 0.42]).
    - Holds in 24/24 settings.
  - **P3 crossover:** **not supported.**
    - Full cast never falls to the narrator within 60% errors in 22/24
      settings. The listener learns that voices are unreliable and falls back
      to the turn prior.
    - Where a crossover exists (tau 0.12, no turn prior), it sits at
      0.48-0.57 error, and the *diverse* cast is more robust, opposite to the
      salience account. No sign flips.
  - **P4 late casting:** 0.068 spillover per error against 0.106 for
    full casting; 24/24 settings.
  - **Other:** early errors cost 1.41x late ones. By type, addressee capture
    costs most (0.281 per error), then cross-gender (0.260), then same-gender
    (0.203).
- **Verdict:** survives as a *model*. It becomes a result about people only
  through H-COST v2, which now tests its numbers.
- **What it changes:**
  - The crossover question becomes a test of listener rationality: a
    crossover would mean people over-trust voice cues.
  - C03's premise that a spoken tag repairs an error is inverted.
- **Artifact:** `data/eval/research/H-IOL/real-d531b1c1f6b0b632/results.json`.

### H-CCAST: confusion-aware casting beats globally reduced distinctiveness. **KILLED**

- **Kill criterion:** the novel-level bootstrap CI of the hypervolume gain
  (aware over blind) includes 0.
- **Method:**
  - Pair confusion predicted by Poisson regression on the other fold (14/14
    novels, 2-fold), from addressee co-occurrence, gender and line counts.
  - Local-search casting over EARS voices, with a lambda sweep.
  - Evaluated on the held-out novels' *real* ladder errors.
- **Result:** gain -0.0022, CI [-0.120, 0.154]. Predicted confusion correlates
  **0.96** with the need for distinctness.
- **Verdict:** killed, for the reason recorded before the run. The pairs the
  attributor confuses are the pairs that talk to each other. Masking their
  errors and keeping their correct lines distinct are the same knob.
- **Artifact:** `data/eval/research/H-CCAST/real-92d76d7efdf5c4d2/results.json`.

### H-LEVER: spend corrections by listener leverage, not upstream uncertainty. **SURVIVING by the letter; method dominated**

- **Kill criterion:**
  - leverage minus lowest-confidence gain CI includes 0 (AUROC 0.6, budget 10%,
    *mismatched* evaluation listener); or
  - leverage overlaps first-appearance by > 80%.
- **v1, as pre-registered:**
  - **Result:** killed by an implementation defect. Signed leverage, measured
    against the already-wrong rendering, is negative for 52% of wrong lines,
    so the policy avoided errors: 0.46 errors fixed, against 1.46 for random.
  - **Artifact:** `.../H-LEVER/real-1fe08f4d8dce5a86/`.
- **v2 (|leverage|; disclosed post-hoc deviation, same criterion):**
  - **Result at the primary cell:** +0.0026 over lowest-confidence, CI
    [0.0008, 0.0046]. Jaccard with first-appearance 0.10. Passes.
  - **But first-appearance itself does better:** 0.0117, against 0.0082 for
    leverage and 0.0056 for lowest-confidence.
  - **At AUROC 0.8:** lowest-confidence wins.
  - **Headroom:** the oracle reaches 0.043.
  - **Artifact:** `.../H-LEVER/real-8640c77f8f03e9ed/`.
- **Verdict:** the leverage *method* is not the contribution. The mechanism
  is: lines that teach the voice map matter most. That is registered as
  **H-FIRST**.

### H-FIRST: with a weak error score, review first appearances first. **OPEN (registered)**

- Observation from H-LEVER v2, registered before its own test.
- **Test:** the product ladder's real confidences and errors. This needs the
  full product ladder including the LLM tier, because the rule tiers alone
  resolve only 9.9% of PDNC lines.

### H-COMPL: audio-ambiguity complementarity is a distinct selection notion. **SURVIVING (L1)**

- **Kill criterion:** top-k Jaccard with any existing scorer >= the random
  floor + 0.15.
- **Result:** max Jaccard 0.169 (with dialogue density), against a random floor
  of 0.164 (13 chapters, 671 beats, budget 20%). Ties are not the driver:
  only 12.5% of beats score 0.
- **Verdict:** distinct at L1. Whether readers or listeners value it is the
  human study.
- **Artifact:** `data/eval/research/H-COMPL/real-1d333db3be4c0145/results.json`.

### H-COST v2: stimulus set rebuilt with pre-registered model predictions. **OPEN (Level 3 built)**

- **Fixes:**
  - at least 2 speakers per gender, so same-gender errors now realise at
    0.19-0.25, against about half the requested rate in v1;
  - a tagged/implicit placement factor;
  - a duration covariate (spoken characters).
- **Pre-registered H-IOL predictions on the exact scripts (probe accuracy):**
  - **Clean:** full cast 0.565 (diverse) and 0.523 (homogeneous), against
    0.414 for the narrator.
  - **Errors on tagged lines (30%):** 0.43-0.48 (diverse).
  - **Errors on implicit lines (30%):** 0.54-0.55 (diverse).
- **Artifact:** `data/eval/research/H-COST/real-v2-iol/results.json`.
- **Not yet done:** audio synthesis and listeners.

## 2026-10-03: visual arm (GPU batch)

### H-VRUNG: can the engine withhold attributes? **SURVIVING (weak)**

- **Kill criterion:** a withholding rung leaks gender AND hair at > 70%, or
  the committed rung recovers < 80%.
- **Method:**
  - 20 balanced beats, 5 rungs, 2 variants: the attribute in the prompt, or
    attribute-free.
  - NoobAI-XL with prompts from the product's own `build_image_prompt`, at a
    fixed seed (200 images).
  - Probes: CLIP-L zero-shot and llava:7b.
- **Run 1, invalid instrument:** read KILL (committed 0.55/0.70), but llava
  answered "unknown" on 85% of committed panels. Artifact
  `real-bd79f777dc64f3a9`, kept.
- **Probe fix, validated before re-scoring:**
  - forced-choice gender: 15/16;
  - open hair colour word: 15/16, on the committed panels that visibly
    contain a person.
- **Run 2:**
  - **Committed:** 0.93 gender, 0.88 hair. It commits.
  - **Back view:** leaks both (0.93 / 1.00).
  - **Silhouette and crop:** leak gender (0.875 / 0.875) but hide hair
    (0.65 / 0.65).
  - **Distant:** hides gender (0.575) but leaks hair (0.725). The person is
    visible in only 35% of these panels.
  - **Result:** passes by the registered rule, which counts a rung as leaking
    only if *both* attributes leak. No rung hides both.
  - **Attribute-free prompts** mostly draw *no person* (llava: person
    visible in 0-30% of panels). When a figure appears, CLIP reads it as
    male (majority 0.6-1.0).
- **Verdict:** a weak survivor. The engine cannot withhold gender while
  still drawing a legible figure. H-VABST (the reader study) is only worth
  running with "silhouette" for hair-uncertain and "distant" for
  gender-uncertain beats.
- **Artifact:** `data/eval/research/H-VRUNG/real-a89a29764cb7eea2/results.json`.

### H-JUDGE-V: where upstream errors are lost, and do judges see them? **SURVIVING**

- **Kill criterion:** either
  - every judge reaches AUROC > 0.9 given that the error survived and was
    rendered, or
  - P(rendered | survives) > 0.9 for every error type.
- **Method:**
  - One attribute error per panel (gender, hair or setting), injected above
    the product's prompt assembly.
  - Rendered at the same seed as the correct panel (60 interventions).
  - Probes: the validated v2 probes.
- **Stage decomposition:**

  | Error | Survives budget | Rendered, given survives |
  |---|---|---|
  | gender | 1.00 | 0.80 |
  | hair | 1.00 | 0.80 |
  | setting | 0.80 | **0.125** |

  The setting is lost in the *generator*, not the token budget. The style
  anchor overpowers the locale. This is the T3 revival condition: loss not
  explained by the 77-token budget.
- **Judges:**
  - **CLIPScore against the intended description**, on 29 pairs with a
    compliant base and a verified rendered error: AUROC **0.52**
    [0.35, 0.69]. Chance. It cannot tell the wrong-gender or wrong-hair
    panel from the right one.
  - **llava-7b holistic judge: invalid instrument.** It answers "1" to any
    1-10 prompt, even for "a red sports car". As yes/no it says "no" to
    every description, the correct one included. This is reported as an
    instrument failure, not as a judge result.
- **Base compliance:** 0.85 gender, 0.80 hair, 0.20 setting. The correct
  panels themselves miss the setting 80% of the time.
- **Caveats:**
  - n is small (20 beats).
  - One engine and one style. The ink-painting style anchor is strong.
  - The probes that define "rendered" are automatic, though validated.
- **Verdict:** survives. The decomposition is the contribution.
  - In this product style, the generator, not the budget, is the dominant
    loss stage for scene errors.
  - A standard CLIPScore check would pass a panel with the wrong character
    gender as often as the right one.
- **Artifact:** `data/eval/research/H-JUDGE-V/real-7d9f5d39a811c34b/results.json`.

### H-XDIS: ladder-vs-LLM disagreement as an error score. **PASSES (product infrastructure)**

- **Kill criterion:** AUROC(disagreement, ladder error) < 0.7. Pre-declared
  product-only.
- **Method:**
  - 1,000 random PDNC quotes that the product ladder resolves (tiers 1-3).
  - qwen2.5:7b (local) is given the passage of ±600 characters and a
    candidate list (speakers and addressees within 20 quotes, plus the
    ladder's owners).
- **Results:**

  | Measure | Value |
  |---|---|
  | Ladder error rate | 0.160 |
  | LLM accuracy | 0.763 |
  | Disagreement rate | 0.263 |
  | **AUROC, disagreement** | **0.889** |
  | AUROC, tier confidence | 0.612 (H-CAL measured 0.59 on all quotes) |
  | P(error given disagree) | 0.517 |
  | P(error given agree) | 0.033 |

- **Verdict:** passes.
  - This is the posterior a confidence-gated voice policy was missing.
    H-GATE showed tier confidence closes only 16-18% of the oracle gap.
  - Agreement alone certifies about three quarters of resolved lines at 3%
    error.
  - Not a research claim.
- **Next:** rerun H-GATE's gating curve with disagreement as the score
  (CPU only, from these trials), and propose the product hook.
- **Artifact:** `data/eval/research/H-XDIS/real-6f97e4d14f536dfe/results.json`.

### H-GATE-XDIS: does disagreement give a better selective-intervention frontier? **CONDITIONAL**

- **Registered:** 2026-10-03, before the analysis code.
- **Method:** CPU only, from H-XDIS's saved 1,000 trials. No new LLM calls.
  - Missing fields re-derived from the same ladder probe, behind an exact-match
    gate (1000/1000 rows matched).
  - Exact expected-value tie handling.
  - Novel-cluster paired bootstrap (2000 resamples).
- **Results, all 1,000 quotes (160 ladder errors):**

  | Errors caught at | Confidence (P1) | Disagreement (P2a) | Disagreement then confidence (P3) |
  |---|---|---|---|
  | 10% review | 24.9% | 32.3% | 38.8% |
  | 20% review | 37.2% | 64.6% | 67.1% |

  - P3 minus P1: +0.139 [0.074, 0.217] at 10% (below the 0.15 bar), and
    +0.299 [0.143, 0.462] at 20% (passes).
  - Residual error at 20%: 10.1% (P1) vs 5.3% (P3).
  - Shortlist-random control: *worse* than confidence (-0.16 / -0.19), so
    there is no shortlist artifact.
  - Strata at 20% support addressee capture, cross-gender and
    same-gender errors.
  - **Key mechanism:** 110/160 errors are EXPLICIT-tier (0.95 confidence).
    Confidence catches 0% of them at 10% review; disagreement catches 34%.
  - **Narrator fallback:** P3 closes 0.84 of the random-to-oracle
    salient-error gap, against 0.29 for confidence.
- **Found during the run:**
  - 58/1000 PDNC gold labels are name variants absent from the character
    keys. The ladder is scored wrong on all 58, and the LLM returns
    "unparsed" on 39 of them.
  - **Disclosed robustness run without them** (n = 942, 102 errors): P3 at
    10% is +0.169 [0.094, 0.275], which meets every criterion. This is post
    hoc and does not overturn the verdict.
- **Verdict:**
  - CONDITIONAL by the pre-registered map.
  - XDIS finds the confidently wrong lines that native confidence cannot
    rank.
  - No research branch yet. Open:
    - the gold-derived shortlist given to qwen;
    - the PDNC alias scoring;
    - pretraining contamination.
- **Artifacts:**
  - `docs/research/experiments/H-GATE-XDIS/` (CONFIG, RESULTS.json, CURVES.csv)
  - `data/eval/research/H-GATE-XDIS/real-c25db0ede3291c7b` (pre-registered)
  - `real-7d44fa32eac9c062` (canonical, identical numbers)
  - `real-28ceee8f12417e15` (robustness)

## 2026-10-03: convergence pass (C1-C3). **Convergence thesis: KILL**

Everything is in `CONVERGENCE.md`: the 13 answers (part 1), analysis (part 2),
protocols frozen before any result plus results (part 3), and prior art (part 4).

### H-XDIS-ALIAS: XDIS under PDNC alias-corrected gold. **CONDITIONAL (unchanged)**

- **Rule (frozen):** main name; else a unique exact alias match; else a
  unique `comparison_key` match; else excluded.
- **Labels:** all 58 name-variant golds resolved; 54 false ladder errors
  removed, leaving 106 errors.
- **Results:**
  - P3 vs P1 errors caught: 0.424 vs 0.284 at 10% (+0.140 [0.079, 0.213],
    below the 0.15 bar), and 0.691 vs 0.414 at 20%.
  - AUROC: P3 0.877 vs P1 0.631.
- **Artifact:** `data/eval/research/H-XDIS-ALIAS/real-4fe36b54f7f8328b`.

### H-XDIS-PS: XDIS with a product-built candidate list. **GREENLIGHT (no collapse)**

- **List:** text surfaces in ±2,000 characters (HeuristicDetector,
  plausible_name, commonness test, capitalisation consistency) plus the
  ladder surface, capped at 12. No PDNC gold.
- **Disagreement:** computed product-side by surface comparison.
- **Results:**
  - Gold recall 0.972. qwen accuracy 0.919, against 0.76 with the gold list.
  - P3 caught 0.620 at 10% (+0.336 [0.233, 0.486]) and 0.928 at 20%,
    against 0.284 and 0.414 for P1.
  - AUROC 0.943; P(err | agree) 0.014; the control is at chance.
- **Diagnosed afterwards:** the gold list's PDNC main names had caused 137 of
  the original 149 "unparsed" answers. qwen had answered with the name form
  the text uses. This is a parser artifact in H-XDIS (ENGINEERING_NOTES 23).
- **Open:**
  - the ladder's `known_names` still come from PDNC (sensitivity run not done);
  - contamination is untested;
  - PDNC only.
- **Artifact:** `data/eval/research/H-XDIS-PS/real-2745361d4136dce5`.

### H-ACT: action counterfactual (same error, different rendering). **KILLED (DEFINITIONAL)**

- **Design:**
  - 60 PDNC lines, each with an injected error (20 cross-gender, 20
    same-gender, 20 addressee).
  - Narrator, generic (the product's unconfirmed rule) and specific voices.
  - 415 Chatterbox renders at fixed seeds.
  - Measured with WavLM-SV, whisper-small and F0.
- **Manipulation check:** 0.90, exactly at the threshold.
- **Error manifestation Δ (specific / generic / narrator):**

  | Error type | Specific | Generic | Narrator |
  |---|---|---|---|
  | cross-gender | 0.87 | 0.42 | 0 |
  | same-gender | 0.35 | 0.01 | 0 |
  | addressee | 0.74 | 0.18 | 0 |

  The causal effect is real.
- **Triviality control:** reference-clip geometry predicts the realised
  margins with **R² 0.95** and the same ordering. The generic voice's
  wrong-gender carry-over (0.53) is as predicted (0.55). The status is
  therefore DEFINITIONAL, and the "beyond the cast table" claim is killed.
- **Product findings:**
  - The unconfirmed voice keeps the predicted gender, so it removes only
    about half of a cross-gender error.
  - The price of masking on correct lines is 0.21-0.25 for the generic
    voice and 0.22-0.51 for the narrator.
- **Policy layer:** at a 20% narrator budget, P3 leaves 0.08 of the
  manifested error mass against 0.58 for P1, at a lower identity price.
  This is selective prediction times a cost table.
- **Image arm (H-VRUNG reread):** attribute-selective masking by framing,
  also by design.
- **Artifacts:**
  - `data/eval/research/H-ACT/real-b01eac13f33ad227` (audio);
  - `real-226129dbf767bac9` (policy);
  - `real-7ec275bc84d41144` (image).

### S1: ladder name-inventory sensitivity. **PASSES**

- The ladder's `known_names` were rebuilt from the product detector instead of PDNC's list.
- Only 2 predictions changed; 48 units became unresolved and were excluded.
- P3 caught 0.929 of errors at 20% vs 0.424 for P1. AUROC 0.943 vs 0.637.
- XDIS-PS therefore does not rest on PDNC's name inventory.
- All 952 answers are real qwen calls; the 2 changed units were asked live.
- **Artifact:** `data/eval/research/H-XDIS-PS/real-255962a04945d31a`.

### Convergence verdict: **KILL**

- **Layer 1:** holds strongly, but is prior art (cross-model disagreement for
  confidently-wrong outputs, ICLR 2026).
- **Layer 2:** definitional (R² 0.95) and published in text pipelines
  (arXiv 2608.14588).
- **Layer 3:** hedging / hierarchical selective classification (Deng 2012;
  Goren et al. 2024).
- **Layer 4:** does not rescue layer 2.
- **H-SELECT:** PRODUCT-ONLY.
- **Kept:** XDIS as product infrastructure. A gender-disputed line should
  route to the narrator, not to the same-gender unconfirmed voice.
- **Next:** the CPU ladder-inventory sensitivity, then a product hook behind
  a flag.
- **Only remaining research question:** whether listener cost is
  non-linear in voice distance. It needs humans.

## 2026-10-17: reader-faithfulness addenda (pointer entry)

This log tracks the research arena. The reader-faithfulness study keeps its
own record in `docs/research/PREFIX_FAITHFULNESS/` (pre-registrations, `REPORT.md`,
`FORMAL.md`) and `docs/research/PAPER/READER_FAITHFULNESS.md`; this entry
only records the three results of 2026-10-17 so the state of record is not
silent about them. Full numbers: EVOLUTION 4.103. All local models, $0, no
human labels.

### Addendum 12, suffix canaries. **SUPPORTED (H12.1-H12.3)**

- **Provenance:** text-derived (string match on tokens planted after the cut); events model-selected.
- **Results:** whole-volume card 22.8% [14.2, 31.5] of 54 events vs 0 for the versioned card; long-context positional instruction 40.6% [29.7, 51.4] of 46 events vs 0 truncated; 3 of 3 models positive; 0 hits in any prefix-only cell.
- **Post hoc (not pre-registered):** a judge says 76% (card) and 88% (long-context) of hits equate the alias with the planted identity.
- **Artifacts:** `data/eval/chimera/rf_e2e/canary_analysis.json`, `posthoc_canary_judge.json`.

### Addendum 13, selection leak. **SUPPORTED (H13.1, H13.2)**

- **Provenance:** judge-labelled (qwen3:8b); resolver qwen2.5:7b; events model-selected.
- **Result:** over 24 resolver-merged events, merged-entity card 19.4% vs prefix-built 1.4%, +18.1 [4.2, 33.3]; a canary is blind to this class by construction.
- **Artifact:** `data/eval/chimera/rf_e2e/selection_analysis.json`.

### Counterfactual suffix on the persona stage. **SUPPORTED (H14.1-H14.4)**

- **Provenance:** system-internal, no labels, deterministic path only, one intervention (pronoun swap).
- **Result:** 47 of 289 gender cuts depend on the suffix vs 23 that diverge under truncate-and-rebuild (all 23 also flip); 0 of 47 outside the exposure window; 0 of 296 move with the `prefix_causal` repair.
- **Artifact:** `data/eval/prefix_audit/counterfactual_suffix.json`.
