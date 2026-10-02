# Prior-art matrix

The strongest prior art for each live theme, and the exact difference. Tags:
**[read]** means the method/limitations sections were read; **[abs]** means
abstract or snippet only. Absence claims ("no study found") rest on targeted
web searches, not a full ACM DL / ISCA / PsycINFO search, and must be
re-checked before any claim of novelty goes into a paper.

## T1: Perceptual cost of upstream errors and commitment under uncertainty

| Prior work | What it solves | What it leaves open (cited) | Our difference | Kind |
|---|---|---|---|---|
| Selective Abstraction, Goren et al., [arXiv 2602.11908](https://arxiv.org/abs/2602.11908) [read] | A ladder of specificity for long-form text; low-confidence atoms replaced by abstractions; AURC; risk guarantee | App. I: non-factual settings need "task-appropriate definitions of risk and coverage when ground truth is unavailable or inherently subjective"; the error cost does not depend on which form is emitted | Neutral rungs (narrator, silhouette) assert nothing; the cost is perceptual salience that **depends on the rendering**; measured by humans in audio and image | scientific |
| Conformal Linguistic Calibration, [arXiv 2502.19110](https://arxiv.org/abs/2502.19110) [partial] | Hedging as soft abstention with conformal factuality | Uses "factuality metrics that do not penalize generality", so the cost of vagueness is excluded | Vagueness cost (lost immersion) is a measured term | scientific |
| CAP, [arXiv 2502.06884](https://arxiv.org/abs/2502.06884) [partial] | RL policy over point / set / abstain for LLMs and VLMs | Hand-set reward, not perceptual | Loss table from listeners | method |
| Hierarchical selective classification, [arXiv 2405.11533](https://arxiv.org/abs/2405.11533); conformal factuality, [arXiv 2402.10978](https://arxiv.org/abs/2402.10978) [abs] | Back-off ladders with guarantees | Correctness-of-emitted-form loss | Form-dependent loss | — |
| MultiActor-Audiobook, [arXiv 2505.13082](https://arxiv.org/abs/2505.13082) [read] | Zero-shot multi-voice audiobooks; MOS-S (speaker identifiability) | Errors are never manipulated, so there is no cost function | Attribution error as the independent variable | scientific |
| Deep Dubbing, [arXiv 2509.15845](https://arxiv.org/abs/2509.15845); Audiobook-CC, [arXiv 2509.17516](https://arxiv.org/abs/2509.17516); MOSS-TTSD, [arXiv 2603.19739](https://arxiv.org/abs/2603.19739) [read] | Multi-cast long-context TTS; TTSD-eval checks rendering against the *given* tags | Deep Dubbing assumes script analysis is "high accuracy"; none studies wrong tags | What happens to listeners when the tags are wrong | scientific |
| LibriQuote, [arXiv 2506.21619](https://arxiv.org/abs/2506.21619) [read] | Delivery-cue pseudo-labels for expressive TTS | Wrong delivery "might mislead listeners", not measured | Measures it, for speaker identity | — |
| HEAR, [arXiv 2608.29120](https://arxiv.org/abs/2608.29120) [read] | Speech LMs rely on semantic priors over vocal evidence for speaker attribution | Machine listeners and conversation only | Human listeners and narrated fiction (also motivates T5) | — |
| Stevenage 2018 ([PMC6175009](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6175009/)); Van Berkum 2008; Choi & Perrachione 2019 | Distinctive voices are recognised better; speaker-message mismatch is detected neurally; talker-switch cost | Isolated sentences or words; no narrative; no synthetic cast | Distinctiveness × error rate in narrative audiobooks | scientific |
| Xu et al., IJHCS 2025 (verbalized uncertainty); Dhuliawala et al., EMNLP 2023 [abs] | Medium hedging beats both extremes in text decision support; confidently-wrong outputs cost more trust | Text decision support, not perceptual rendering | Do **not** claim non-monotonicity in general, only its perceptual-rendering form and mechanism | — |
| Latinus & Belin 2012; INSIDE, [arXiv 2508.19210](https://arxiv.org/abs/2508.19210); Blau & Michaeli, [arXiv 1711.06077](https://arxiv.org/abs/1711.06077) | Categorical voice-identity perception; interpolation creates new speakers; averaging degrades perception | — | Predicted the H-HEDGE kill, which the machine-level test confirmed | — |
| IMPLICIT-Bench, [arXiv 2609.24228](https://arxiv.org/abs/2609.24228); default images, [arXiv 2505.09166](https://arxiv.org/abs/2505.09166) [read] | Text-to-image models default or stereotype under unspecified attributes | "By design, TTI models always yield an output": abstention is never considered | Deliberate visual abstention (H-VABST) | scientific |

## T2: Content selection under a depiction budget

| Prior work | Solves | Leaves open | Our difference |
|---|---|---|---|
| ViStoryBench, [arXiv 2505.24862](https://arxiv.org/abs/2505.24862) [read] | Story-visualization benchmark; script-grounded | One frame per storyboard line; "pacing" left to future work | Which k of N beats, from reader preference |
| LLMs Behind the Scenes, [arXiv 2509.22940](https://arxiv.org/abs/2509.22940) [read] | LLM-directed illustration preferred by humans | Illustrates every fragment; "complex narratives" not assessed | Budgeted selection on long prose |
| KathaTrace, [arXiv 2607.01312](https://arxiv.org/abs/2607.01312) [read] | Source-grounded recoverability; adds bridge scenes | Five-scene fables; long-range recovery is future work; selection is not preference-based | Preference-learned selection; budget axis |
| Visualness, [arXiv 2305.10434](https://arxiv.org/abs/2305.10434) [read] | Per-sentence visualness | No budget, no narrative weight | A foil and a feature, not the target |
| MangaFlow, [arXiv 2605.28173](https://arxiv.org/abs/2605.28173); VinaBench, [arXiv 2503.20871](https://arxiv.org/abs/2503.20871) | Agentic story-to-manga; faithful narratives | Use LLM shot planners or crowd-written narratives | Natural long prose; human choice of moments |

## T3: Causal propagation and correction allocation (parked)

| Prior work | Solves | Leaves open | Our difference |
|---|---|---|---|
| CAR, [arXiv 2606.08275](https://arxiv.org/abs/2606.08275); AgenTracer, [arXiv 2509.03312](https://arxiv.org/abs/2509.03312) | Intervene-and-replay failure attribution for agents | Common random numbers "left as a refinement"; judge outcomes noisy | Seeded generation gives common random numbers; perceptual outcomes |
| Takano, [arXiv 2608.26171](https://arxiv.org/html/2608.26171v1) | One human checkpoint in a text pipeline | Propagation through later stages is future work | Where to place corrections |
| Urman et al., [arXiv 2609.11532](https://arxiv.org/abs/2609.11532) | Causal ablation of an intermediate prompt-rewrite stage | Two conditions; VQA proxy confound | Many interventions, a SHAM control, multiple seeds |

## T5: Evaluation validity for generated narrative media

| Prior work | Solves | Leaves open | Our difference |
|---|---|---|---|
| CheckList-style metric perturbation ([EMNLP 2021](https://aclanthology.org/2021.emnlp-main.575/)) | Perturbs a metric's *inputs* | Never intervenes upstream through the generator | Upstream intervention through a real generator |
| Speech-DRAME, [arXiv 2511.01261](https://arxiv.org/abs/2511.01261); CEAEval (ACL 2026); EmergentTTS-Eval, [arXiv 2505.23009](https://arxiv.org/abs/2505.23009) | Audio-LLM judges for expressiveness | No misattribution validation | Judge vs human by error type on H-COST stimuli |

## Licences of data the program touches

| Resource | Licence (as found) | Consequence |
|---|---|---|
| PDNC | No licence file in either repo (paper reportedly says CC BY-NC-ND); texts are Gutenberg PD | Research use only; regenerate derived sets from code; per-line trials not committed |
| EARS | CC BY-NC 4.0 | Stimuli are fine for research; **a commercial product needs another bank** |
| CREMA-D | ODbL / DbCL | Product-usable with attribution |
| LitBank | CC BY 4.0 | Free |
| LibriQuote | Code CC BY-NC 4.0; audio LibriVox PD | Research |
