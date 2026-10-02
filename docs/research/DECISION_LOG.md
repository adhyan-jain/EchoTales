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

- 9 candidates rejected outright, 6 parked (`KILL_ANALYSIS.md`).
- No mechanism qualifies as PATENT-CANDIDATE. The one concrete mechanism (hedged rendering) is dead.
