# Kill analysis

Every candidate attacked with five questions: Why is this not just another
paper about X? What is the strongest prior art? Is it an obvious combination?
Does a classical method already solve it? What experiment kills it now?

## Rejected outright (9)

| ID | One-line reason it dies |
|---|---|
| C08 | Long-context multi-voice TTS is owned by Audiobook-CC, Deep Dubbing and MOSS-TTSD; EchoTales trains nothing |
| C09 | Description-to-voice casting is owned by Deep Dubbing TTT and S-VoCAL; it also sits next to the firewall |
| C10 | A timbre-consistency metric exists (SwanBench, TTSD-eval) |
| C13 | Hedged interpolation: predicted dead by categorical perception, and **killed by H-HEDGE** (82% of the identity change happens at the discrete switch) |
| C17 | Theory reduces to "distinct outputs are more distinguishable" |
| C18 | A learned commitment controller is CAP plus learning-to-defer |
| C19 | Flagging uncertainty to users is Berke 2017, Kim FAccT 2024 and VSUP; it is anti-immersive |
| C31 | Edit-based preference learning is PRELUDE; firewall risk; n too small |
| C07 | Marker-vs-sentiment conflict would be a LibriQuote re-analysis; Chatterbox has no instruction input. Moved here from LOW |

## Parked (6)

C21, C24, C26, C28, C29, C30. The reasons are in `RESEARCH_THEMES.md` (T3, T4)
and the opportunity map. The common thread: either they drift back into the
killed interface/truncation direction, or the data to test them does not exist.

## Attacked and kept

### C01 + C02 + C11 (H-COST): perceptual error cost and the crossover

- **"Just selective prediction?"** No. Selective Abstraction App. I explicitly leaves subjective, ground-truth-free risk open. In every ladder paper (SA, CLC, HSC, Mohri) the cost of an error does not depend on the form emitted.
- **"Just error propagation?"** The claim is not that errors propagate. It is that the *rendering decision* sets how much an error costs, and that this cost is measurable and can reverse the full-cast advantage.
- **Strongest threat.** Xu et al. (IJHCS 2025) already show non-monotone utility of hedging in text decision support. So the claim must be the perceptual-media mechanism (salience depends on distinctiveness and form), not non-monotonicity per se.
- **Incremental failure mode.** If listeners simply hate errors linearly and never prefer the narrator, the result is "errors are bad". Not a paper.
- **Kill now.** The listening pilot: 12 passages, about 24 listeners, cluster bootstrap on the difference-in-differences. Power at an assumed −0.15 effect is about 57%, so 40-50 listeners are needed to be decisive.
- **Confidence:** MEDIUM.

### C20 (H-SELECT): which moments to illustrate

- **"Just visualness or salience?"** Measured: the cheap scorers barely overlap (best top-k Jaccard 0.22 against a 0.16 random floor). A zero-shot LLM tracks the visualness proxy (Jaccard 0.33, floor 0.11) and not drama. So the notions are distinct; whether readers agree with any of them is open.
- **Strongest threat.** KathaTrace's recoverability-driven bridge scenes, and the subjectivity of the target.
- **Kill now.** Pairwise annotation by 5 people on 3 chapters. If overlap agreement is too low, the target is unlearnable.
- **Confidence:** MEDIUM.

### C22 (H-VABST): visual rendering-level abstention

- **Threat.** Firewall perception, if the uncertainty source is the identity resolver. Frame it as generic attribute specificity.
- **Kill.** 40 beats × {committed default, committed alternative, silhouette}, with reader judgments after reading the passage.
- **Confidence:** MEDIUM.

### C15: joint cross-modal commitment

An interesting interaction, but it doubles study cost. Run only after H-COST shows a main effect. **Confidence:** MEDIUM-LOW.

### C03 + C33: perceptually weighted attribution metric

- Supported by measurement: 52% of real errors are addressee capture, and a vocative inside the quote predicts an error 82% of the time.
- **Kill.** In the H-COST data, the error types cost the same.
- **Confidence:** MEDIUM. It rides on H-COST.

### C05 (H-JUDGE-A): audio-LLM judge validity on misattribution

- Cheap once H-COST stimuli exist. The budget question is API cost.
- **Kill.** The judge matches humans on vocal-only swaps.
- **Confidence:** MEDIUM. Short-paper ceiling alone.

### C27: interventional metric validation

- **Threat.** Causal-ML evaluation literature not fully searched.
- **Kill.** Upstream interventions add nothing over input perturbation.
- **Confidence:** MEDIUM-LOW novelty, HIGH utility as infrastructure.

### C04: rendering policy

- **Measured cap.** H-GATE shows current confidence closes only 16-18% of the random-to-oracle gap in salient-error mass.
- Any policy paper needs a better posterior, which drifts toward attribution and the firewall.
- **Confidence:** LOW as a core; it stays as an ablation inside H-COST.

### C32: confidence calibration on independent gold

A required infrastructure result (H-CAL killed the "constants are a posterior" assumption). Not a paper.

### C12: risk control

A component. Certification is likely vacuous under shift between novels (2606.29054).

## Shortlist (10), ranked on research criteria only

| Rank | Candidate(s) | Why it ranks here |
|---|---|---|
| 1 | C01+C02+C11 (H-COST) | Deepest and most general; its absence is confirmed by three independent searches; decisive human test ready |
| 2 | C20 (+C23) (H-SELECT) | Clean new problem plus a releasable dataset; precondition met |
| 3 | C22 (H-VABST) | Visual arm of #1; gives generality across modalities |
| 4 | C15 | Cross-modal interaction; unique to a two-modality system |
| 5 | C03+C33 | Turns #1 into an evaluation tool the attribution community can use |
| 6 | C05 (H-JUDGE-A) | Judge validity; cheap rider on #1 |
| 7 | C27 | Methodology the whole program needs |
| 8 | C04 | Policy, capped by posterior quality |
| 9 | C26 | Only if synthetic fault injection escapes the truncation explanation |
| 10 | C12 | Component |
