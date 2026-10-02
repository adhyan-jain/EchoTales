# Research opportunity map

Pass of 2026-10-02. Built from (a) the code, artifacts and history of this
repository and (b) a literature pass run as four parallel searches (audio and
audiobook TTS; story and manga visualization; uncertainty, decision and HCI;
feedback and evaluation methodology), each opening the actual papers where
possible. The raw search notes are not committed. Every prior-art claim below
is cited in `PRIOR_ART_MATRIX.md`.

## Part 1: Asset map

Classes: **A** product, **B** research infrastructure, **C** benchmark/data,
**D** potentially novel research component, **E** baseline/comparator,
**F** obsolete.

| Asset | Where | Class | Role in the research program |
|---|---|---|---|
| Full pipeline: EPUB to spans, cast, director, panels, voice, video | `packages/pipeline` | A | The product. It is also the generator under test. |
| Speaker-attribution ladder with per-tier confidence | `pipeline/speakers/attribution.py` | A, E | The source of real upstream errors. Its constants were measured against human gold for the first time this pass (H-CAL). |
| Voice stack: Chatterbox engine, EARS/CREMA-D/VCTK banks, unconfirmed-voice gate | `pipeline/voice/` | A, B | Stimulus generator for the perceptual studies. The unconfirmed-voice gate is the natural baseline policy. |
| Seeded SDXL-family engines, silhouette fallback, tiered CLIP fit | `pipeline/render/panels.py`, `persona/prompt.py` | A, B | The visual arm (H-VABST). Fixed seeds give matched pairs. |
| Provenance manifests, versioned render directories | `render_artifact.jsonl`, `paths.py::next_version` | B | Reproducibility; the pattern for `research/provenance.py`. |
| Correction log and webview correction UI | `pipeline/corrections.py`, `data/corrections/` | A, B | Too sparse to serve as labels: 34 human speaker corrections, most with stale span IDs. Kept as product UI. |
| Bootstrap statistics | `pipeline/eval/stats.py` | B | Re-exported by `research/stats.py`. |
| LitBank harness; RI/LOTM/ORV silver sets | `scripts/eval/litbank_eval.py`, `data/gold/` | C, E | The silver sets are LLM-drafted and cannot be released (copyrighted text). Not used as research gold. |
| CLIPScore with a shuffled-prompt control | `scripts/eval/clip_score.py` | E | A circular metric (it uses the generator's own encoder against a truncated prompt). Kept only as a foil. |
| Render history v0 to v54, EVOLUTION failure record | `data/novels/RI/panels/ch1/`, `docs/EVOLUTION.md` | C | Hypothesis source only. It is not a controlled intervention series (earlier audits). |
| KG, `state_of`, observer axis, gazetteer, cache read-set | `packages/core`, `pipeline/resolve` | A | Product infrastructure. **Firewalled** as a research contribution. |
| Learned scorer (contributes 0 links), lexical `relevance.py` | `pipeline/resolve`, `render/relevance.py` | F | Inert or circular. |
| **New:** PDNC (28 public-domain novels, human speaker and addressee gold) | `data/cache/research/pdnc` (gitignored) | C | Independent gold for every audio experiment. Licence unclear, so used for research only and not redistributed. |
| **New:** research arena | `packages/research/` | B | Shared infrastructure (see `RESEARCH_ARENA.md`). |

## Part 2: Candidates

Format: **ID — name** (type). RQ / mechanism / gap / EchoTales advantage /
kill test / confidence. Theme assignments are in `RESEARCH_THEMES.md`; the
attack on each candidate is in `KILL_ANALYSIS.md`.

### Audio and audiobook

- **C01 — Perceptual cost function of attribution errors** (phenomenon / human study)
  - **RQ:** how do comprehension, error-noticing and preference change with attribution error *rate* and *type* in a multi-voice chapter?
  - **Gap:** MultiActor-Audiobook's MOS-S never manipulates errors. Deep Dubbing assumes attribution is solved. LibriQuote says wrong delivery "might mislead listeners" but does not measure it. Targeted searches found no study.
  - **Advantage:** attribution is separable from synthesis in this pipeline, the error types are measured on human gold (H-CAL), and re-rendering is cheap.
  - **Kill:** comprehension and noticing flat across 0/15/35% injected error.
  - **Confidence:** MEDIUM-HIGH that the gap is real.
- **C02 — Distinctiveness × accuracy crossover (masking)** (phenomenon)
  - **RQ:** does a more distinctive cast raise the cost of each error, so that homogeneous voices win below some accuracy?
  - **Gap:** no work crosses voice distinctiveness with attribution correctness (Stevenage 2018 covers isolated voices only).
  - **Advantage:** both banks exist, and the objective precondition is now measured (H-GATE: 22% of errors masked under a homogeneous cast vs 2% under a diverse one).
  - **Kill:** no interaction, i.e. parallel lines.
  - **Confidence:** MEDIUM.
- **C03 — Perceptually weighted attribution metric** (evaluation)
  - Weight each attribution error by its expected audible harm (vocative self-address, gender mismatch, confusable voices, a spoken tag repairing the error) instead of counting all errors equally.
  - **Gap:** PDNC and every quote-attribution paper score errors uniformly.
  - **Kill:** in the C01 data, addressee swaps are detected at the same rate as same-gender swaps.
  - **Confidence:** MEDIUM.
- **C04 — Rendering policy under attribution uncertainty** (method)
  - Compare narrator vs unconfirmed voice vs best-guess voice vs best-guess with a forced spoken tag.
  - **Gap:** no audiobook system conditions rendering on attribution confidence.
  - **Kill:** listeners cannot tell the policies apart.
  - **Confidence:** MEDIUM-LOW standalone. Policy value is capped by the posterior: H-GATE shows current confidence closes only 16-18% of the random-to-oracle gap.
- **C05 — Audio-LLM judges and vocal-only misattribution** (evaluation validity)
  - **Gap:** MultiActor, LibriQuote and Dopamine use audio-LLM judges. HEAR shows speech LMs rely on semantic priors over vocal evidence. Nobody validates judges on narrated misattribution.
  - **Kill:** a judge catches vocal-only swaps at human rate.
  - **Confidence:** MEDIUM.
- **C06 — Expressive-control identity drift** (characterisation)
  - Does high exaggeration push a voice across another cast member's identity boundary?
  - **Gap:** SwanBench concedes its timbre metric is not perceptual.
  - **Kill:** no line crosses to another voice under the nearest-voice check.
  - **Confidence:** LOW-MEDIUM; mostly engineering.
- **C07 — Delivery marker vs scene sentiment conflict set** (benchmark)
  - **Gap:** LibriQuote has no conflict subset.
  - **Kill:** a LibriQuote re-analysis already answers it.
  - **Confidence:** LOW. Chatterbox has no instruction input.
- **C08 — Long-context expressive multi-voice TTS** (method). **Rejected:** Audiobook-CC, Deep Dubbing, MOSS-TTSD.
- **C09 — Voice casting from character descriptions** (method). **Rejected:** Deep Dubbing TTT, S-VoCAL; also firewall-adjacent.
- **C10 — Long-form timbre-consistency metric** (evaluation). **Rejected:** SwanBench-Speech, TTSD-eval.

### Decision, uncertainty and HCI

- **C11 — Form-endogenous perceptual error cost over a rendering ladder** (phenomenon + decision framing)
  - Measure L(rung, correct) and L(rung, wrong). An interior optimum exists if L(specific, wrong) − L(neutral) is large relative to L(neutral) − L(specific, correct).
  - **Gap:** Selective Abstraction (2602.11908) App. I names subjective, no-ground-truth risk as open. Conformal Linguistic Calibration excludes the cost of vagueness by design. No paper lets the error cost depend on the emitted form.
  - **Kill:** salience gap near zero, or fewer than about 5% of real lines fall in the band where a policy would change the decision.
  - **Confidence:** MEDIUM-HIGH unclaimed; MEDIUM effect.
  - Merged with C01/C02 as H-COST.
- **C12 — Risk control with form-dependent loss** (method). Learn-Then-Test and joint certificates (2606.08517) already handle non-monotone losses; certification breaks under shift (2606.29054). **Component only.**
- **C13 — Hedged rendering by identity interpolation** (method). Predicted to fail by categorical voice perception (Latinus & Belin 2012) and by INSIDE (interpolation creates new speakers). **KILLED this pass at machine level (H-HEDGE).**
- **C14 — Gender-neutral mid-attribute rung** (method). Watanabe 2210.09916 shows mid-attribute voices are possible. A rung inside C11, not standalone.
- **C15 — Joint cross-modal commitment** (phenomenon)
  - Is a wrong voice over a correctly drawn speaker worse than a wrong voice alone?
  - **Gap:** no joint commitment policy across output modalities. V-CASS only hints at the effect.
  - **Kill:** no interaction in a 2×2.
  - **Confidence:** MEDIUM-LOW. Extends C11.
- **C16 — Perceptual risk-coverage curves** (methodology). Presentation device for C11.
- **C17 — Uncertainty–perception theory for conditioning errors** (theory). Risks the tautology "distinct outputs are more distinguishable". **LOW.**
- **C18 — Learned controller choosing commitment level.** **Rejected:** CAP (ACML 2025), learning-to-defer.
- **C19 — Mark uncertain renderings to the user.** **Rejected:** Berke 2017 (caption confidence markup disliked), Kim FAccT 2024, VSUP.

### Visual and story

- **C20 — Moment selection learned from reader preference** (problem + dataset)
  - Which k of N beats should be illustrated?
  - **Gap:** none found. Visualness work scores single sentences, salience work has no visual side, story visualization draws every line, and KathaTrace uses recoverability rather than preference.
  - **Advantage:** long public prose and a product heuristic baseline. Precondition met: the cheap scorers disagree (H-SELECT).
  - **Kill:** annotator agreement too low, or a zero-shot LLM already at the human ceiling.
  - **Confidence:** MEDIUM-HIGH novelty.
- **C21 — Source-grounded faithfulness at novel scale with per-stage loss** (measurement)
  - KathaTrace owns the general idea; only the long-prose plus per-stage version is new.
  - Overlaps the killed interface direction. **PARKED.**
- **C22 — Rendering-level visual abstention** (phenomenon)
  - Silhouette vs committed figure under attribute uncertainty.
  - **Gap:** none found; text-to-image abstention exists only in evaluators or as asking the user.
  - **Kill:** obscured figures rated worse than wrong commitments.
  - **Confidence:** MEDIUM. The visual arm of C11 (H-VABST).
- **C23 — Recoverability vs depiction budget** (phenomenon). Does selection matter more than rendering? KathaTrace never varies k. **Kill:** random ≈ heuristic within CIs. Folds into C20.
- **C24 — Capability-aware framing** (method). Reads as prompt engineering. **PARKED.**
- **C25 — VLM judge validity for manga vs prose** (evaluation). A support study; no system-level gap if Spearman > 0.8.

### Feedback and evaluation methodology

- **C26 — Counterfactual value of a human correction under common random numbers** (methodology)
  - **Gap:** CAR leaves common random numbers open; Takano leaves propagation as future work.
  - Real-correction data is too sparse (34 usable), and the idea risks reducing to the killed truncation finding. **PARKED.**
- **C27 — Interventional metric validation by seeded re-render** (methodology). Closest: perturbation CheckLists and semantic-invariance tests (they perturb the metric's inputs, not upstream). **Confidence:** MEDIUM-LOW novelty, HIGH utility.
- **C28 — Cross-modal disagreement as an error detector** (method). Legitimate non-correspondence (off-panel speakers) kills precision, and there are no labels. **PARKED.**
- **C29 — Error-transmission coefficients across stages** (measurement). Overlaps the killed interface direction. **PARKED.**
- **C30 — Power for clustered within-work judgments** (statistics). Incremental on Lee and Kim. **LOW.**
- **C31 — Learning from sparse intermediate corrections.** **Rejected:** PRELUDE; firewall risk; data size.

### From this pass's own measurements

- **C32 — Upstream confidence as a rendering input must be calibrated on independent gold** (infrastructure finding)
  - Measured (H-CAL): the "0.95" explicit tier is 86.7% correct on PDNC and the "0.75" proximal tier is 63.8%; AUROC 0.59.
  - Not a paper on its own; it gates C04 and C11's policy half.
- **C33 — Addressee capture is the dominant error class** (finding supporting C03)
  - 52.3% of the ladder's real errors on PDNC put the addressee in the speaker's slot, and 41.5% are cross-gender. Errors when the predicted name is a vocative inside the quote: 82%.

## Summary

33 candidates: 9 rejected outright by prior art, 6 parked, and 18 alive at
some level. After the kill analysis, 10 are on the shortlist
(`KILL_ANALYSIS.md`).
