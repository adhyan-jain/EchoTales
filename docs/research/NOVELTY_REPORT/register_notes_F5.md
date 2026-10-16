# Integration Register notes, family F5: visual and audio narrative consistency (Track S, product-only)

Verification pass 2026-10-15. Merging any donor here is engineering, not paper novelty. Paper value is "ablation baseline" or "none".
Method: PDFs fetched from arxiv.org/pdf/<id>, `pdftotext -layout`, method/experiment/limitation sections read plus keyword sweeps
(licen, GPU/VRAM, limitation, reveal, spoiler, github). Licences quoted from the repos' LICENSE files / Hugging Face API metadata fetched today.
No code run, no GPU used, nothing executed from downloads. Tags: [PUB] method+experiment read in the source itself; [LEAD] snippet only;
[PRIMARY] a non-paper primary source read in full (PR body and code). Nothing here is a visual-correctness claim: every judgement below is from text.
Local grounding (read-only): `render/panels.py:2740` `reference_images=[]`; `CHIMERA_DEFECT_BACKLOG.md` B3/B4/B7/A3/A4;
`core/visual_memory.py` (commit 6c7e2c2, 2026-10-13); `render/plan_builder.py` (`visual_registry`, `discourse_cutoff`, `disclosure_policy` optional args, default None).

## 0. Gen4AVC poster (read first)
- Source: "Grounding the Visual Axis of a Narrative World Model: Consistency-Aware Reference Generation for Long-Form Stories", Divyajot Singh,
  Imon Banerjee, Shourya Gupta, Aaryaman Jain, Shreyash Mishra, Vasu Sharma. 2nd Gen4AVC workshop, ECCV 2026 (8 Sep 2026), regular poster #2
  (gen4avc.github.io/eccv2026). The page states "The workshop will be non-archival." Tag: **INACCESSIBLE** (title/authors/venue only, [LEAD]).
- What I tried: (1) workshop page lists only title, authors, PDF link `openreview.net/attachment?id=KQuK4YCiLP&name=pdf`; no abstract, no forum link, no code link.
  (2) curl and WebFetch of that PDF and of `/forum?id=KQuK4YCiLP`, `/pdf?id=...`, `api2.openreview.net/notes?id=...`: HTTP 403 "Verifying your browser"
  challenge page (HTML saved, no PDF). I did not try to defeat the bot check. (3) arXiv API queries for the title and for "Consistency-Aware Reference
  Generation": 0 results; only one arXiv hit for "narrative world model" (2607.05577). (4) Web search on exact title, author names, "Gen4AVC": nothing beyond the workshop page.
  (5) Semantic Scholar API rate-limited (429). (6) LinkedIn page of NWM first author: HTTP 999.
- Related, read [PUB]: Narrative World Model (arXiv 2607.05577v1, Saifullah, Kornmaier, Kazi, Sharma, Kanade, Yadav, PocketFM; 23 pp, "Preprint. Under review";
  accepted at COLM 2026 workshops per a LinkedIn snippet [LEAD]). It is text-only. Its Discussion ends: "NWM-conditioned generation is future work." Vasu Sharma is on both
  author lists, so the poster is very probably the group's first visual follow-up (INFERENCE, not verified).
- Overlap assessment: **cannot be ruled in or out.** The title says "reference generation" and "consistency-aware", which is the same object as EchoTales'
  character reference sheets and `VisualMemorySelector`. Whether it is reveal-aware (reference admissibility by reader position) is UNKNOWN. Treat as an open novelty threat; owner can open the PDF in a normal browser.
  Action: have the owner download the PDF in a browser and give it to a reader; do not cite or dismiss it until read.

## 1. CANVAS (Continuity-Aware Narratives via Visual Agentic Storyboarding)
- Source: Mondal, Song, Parmar, Goyal, Boyd-Graber, Pfister, Song (UMD, Google). arXiv 2604.13452v1 [cs.CL], 15 Apr 2026. No venue stated. [PUB]
- Contributes: Sections 3.1-3.2 and Algorithm 1. An LLM planner reads ALL shot descriptions first and emits a global plan P=(C,L,O): per-shot character
  appearance state C(c,t), location ids L, object states O(o,t). Then per shot: retrieve anchors (previous frame, character anchor, location anchor) from a
  visual memory M=(Mc,Ml,Mf), generate N candidates, pick by VLM question-answering against the plan, update memory. Experiments (Sec 5-6, Tables 2-3):
  ViStoryBench-Lite, ST-Bench, own HardContinuityBench (small); VLM judge Gemini-2.5-Flash; claims +21.6% background, +9.6% character, +7.6% props over best baseline (Gemini-CT).
  Table 1 marks "Future Cond" as a CANVAS feature: the plan is conditioned on future shots by design.
- Artifact and licence: code "coming soon" on the project page (checked) ; benchmark/data not released; weights none. Licence: UNVERIFIED (nothing published).
  Backbone is Gemini-3-pro-image (Sec 4 "Baselines and Implementation"), a hosted paid API; App A.3 "all methods ... on standard CPU-only machines".
- Touches: `render/panels.py` (reference selection ~2127-2232), `render/plan_builder.py`, `persona/scoped_reference.py`; conceptually a replacement for the whole panel loop.
- Product value: low as code; medium as ideas (object-state tracking, location anchors, QA-based candidate selection). Paper value: none (EchoTales' contribution is the opposite: reader-bounded state).
- Integration form: baseline-only / idea mining. Cost: not runnable locally (API); App A.3 call count 1 + C + S(1+3K) per story; at S=30 panels, K=3 about 300 calls per chapter, price UNVERIFIED and likely to eat the $5-10 cloud budget.
- Evidence needed: released code and a licence; a reveal-bounded variant of its plan. Available: paper only.
- Limits (stated): "relies on large image generation models, making generation computationally expensive"; HardContinuityBench small; assumes entities "can be reliably extracted from text".
  Found: plan sees the whole script, so a later identity or outfit change can flow back into earlier shots (anti-reveal-aware); no identity-change-with-same-name handling beyond a state label; no manga multi-panel layout.
- **Decision: baseline-only** (conceptual comparator in related work; reject as dependency: paid hosted model conflicts with local-first and the $5-10 budget, and "no multi-model per image"). LEAD-grade features cannot be adopted anyway.
- Test: none to run now. If code appears, run it on one RI chapter with reveal-position audit (does shot k's anchor set contain any asset first disclosed after k?). Expected to fail by construction.

## 2. VideoMemory
- Source: Zhou, Du, Xu, Wang, Zhuang, Zhang, Li, Hu, Su, Chen (HKUST-GZ, ByteDance). "VideoMemory: Toward Consistent Video Generation via Memory Integration", arXiv 2601.03655v1 [cs.CV], 7 Jan 2026. No venue stated. [PUB]
- Contributes: Sec 3.3 Dynamic Memory Bank with character/prop/background banks; entry m=(e,a,Iref) keyed by entity + attribute vector ("Anna 1985"); retrieve-or-update:
  if no sufficiently similar entry, generate a new reference conditioned on past images of the same entity (Anna at 20 then 60). Sec 3.4 keyframe (Gemini 2.5 Flash-Image) then Wan 2.2 I2V-14B.
  Sec 4 (54-case own benchmark; DINOv2 character/prop/background similarity; Table 3 ablation: removing the bank drops background consistency 0.72 to 0.28). Fig 4 caption: it "plans all scenes and shots without any visual input", i.e. whole script up front.
- Artifact and licence: code github.com/EnVision-Research/VideoMemory; LICENSE file is Creative Commons "Attribution-NonCommercial-ShareAlike 4.0 International", README: "licensed under the CC BY-NC-SA 4.0". GitHub API reports NOASSERTION. Data/weights: none released (repo needs OPENAI and REPLICATE API keys in env.example).
- Touches: `persona/reference_gen.py` (per-body sheets), `persona/scoped_reference.py`, `visual_memory.py` (the bank is a flat, position-blind analogue of `VisualAssetRegistry`).
- Product value: low; EchoTales already has body-epoch sheets keyed by persona and a registry with lineage. Paper value: baseline only ("flat entity memory, no cutoff"). Integration form: baseline-only.
- Cost: Wan 2.2 14B and Gemini keyframes are not 8GB-VRAM class (VRAM not stated in paper; UNVERIFIED); NC-SA licence is share-alike and non-commercial, which contaminates any copied code.
- Limits (stated): no limitations section found in the extracted text (sweep). Found: retrieval by text-similarity of attribute strings, so a later-state entry could be retrieved for an earlier shot if the planner labels it; no observer or disclosure axis; video-oriented.
- **Decision: baseline-only** (ideas already present in EchoTales; do not copy NC-SA code). Test: a flat-bank ablation arm in the leakage test (Section 9): same assets, retrieve ignoring position; count leaked references.

## 3. StoryDiffusion (Consistent Self-Attention)
- Source: Zhou (Yupeng), Zhou (Daquan), Cheng, Feng, Hou (Nankai, ByteDance). "StoryDiffusion: Consistent Self-Attention for Long-Range Image and Video Generation", arXiv 2405.01434v1 [cs.CV], 2 May 2024. Venue NeurIPS 2024 Spotlight per the GitHub repo description [LEAD for venue]. [PUB] for method (Sec 3.1, Alg. 1, Sec 4.1-4.2, App C).
  Verified that "Zhou et al. 2024" in CANVAS refers to this paper.
- Contributes: training-free replacement of U-Net self-attention; for image i in a batch it appends randomly sampled tokens from all OTHER images (Eq. 2: I_1..I_{i-1}, I_{i+1}..I_B) to the K/V (sampling rate 0.5 default, tile/sliding window for memory). Compared on SDXL against IP-Adapter and PhotoMaker with 20 character prompts x 100 activities (GPT-4 generated), 50-step DDIM. Semantic Motion Predictor for video (SD1.5, trained on WebVid10M; not relevant here).
- Artifact and licence: code HVision-NKU/StoryDiffusion, LICENSE "Apache License Version 2.0, January 2004". Weights: the repo ships code and uses third-party base checkpoints; Motion Predictor weights licence UNVERIFIED. Effective licence of outputs = base model: NoobAI-XL 1.1 is "license: other / fair-ai-public-license-1.0-sd" and its README adds "II. Commercial Prohibition ... We prohibit any form of commercialization, including ... model-generated products." (Hugging Face card, fetched today).
- Touches: the image engine call at `render/panels.py:2738-2742` (ComfyUI/diffusers worker), not the narrative layer.
- Product value: medium for within-chapter identity drift WITHOUT references (IP-Adapter is permanently removed; this needs no reference image). Paper value: ablation baseline ("attention-level consistency, no state"). Integration form: isolated adapter / config switch (batch of one chapter's panels).
- Cost: README: "low GPU Memory cost version ... tested on a machine with 24GB GPU-memory (Tesla A10) and 30GB RAM, and expected to work well with >20 G GPU-memory". 8GB is therefore UNSUPPORTED by the authors; memory grows with batch x tokens. Engineering 3-5 days (diffusers attention processor on NoobAI SDXL, ComfyUI nodes if used), plus an ablation run.
- Limits (stated, App C): "inconsistencies in some minor clothing details, such as ties"; not designed for very long sequences ("absence of global information exchange"). Found: **cross-batch symmetry**: tokens are sampled from every other image in the batch, so a panel batch that includes later-chapter panels lets later appearance (disguise reveal, aged body) flow BACK into earlier panels. This violates reveal-aware rendering unless batches are causal (panel k sees only panels <= k) or per-epoch. Consistency is within a batch only, not across chapters. Also tied to SD-U-Net attention; a conflict check with `STYLE_ANCHOR` first is not needed (prompt-level), but untested.
- **Decision: adapt (conditional)**: only as a config switch with a causal-batch rule, and only after the reference-less baseline is measured. Not adopt: 8GB unproven, no reveal safety by default, and the project forbids multi-model per image (this is single-model, so no conflict).
- Test: on one RI chapter, same seeds, 3 arms (baseline, CSA full-batch, CSA causal-window); VRAM peak logged; identity-drift via face-embedding similarity on a human-checked sample; leak probe: add one later-reveal panel to the batch and measure whether an earlier panel's character features move toward it (embedding distance shift). Image inspection by a human is required; text tests cannot show visual correctness.

## 4. Story2Board
- Source: Dinkevich, Levy, Avrahami, Samuel, Lischinski. "Story2Board: A Training-Free Approach for Expressive Storyboard Generation", arXiv 2508.09983v1 [cs.CV], 13 Aug 2025. No venue stated. [PUB]
- Contributes: Sec 3: Latent Panel Anchoring (a reference sub-panel and a target sub-panel are denoised jointly in one stacked canvas; the reference is cropped away) and Reciprocal Attention Value Mixing (blends values of token pairs with strong reciprocal attention). Sec 4: Rich Storyboard Benchmark, 100 stories x 7 scene prompts; VQAScore (prompt alignment), DreamSim (character consistency), a new Scene Diversity metric; AMT user study. An LLM (GPT-4o) decomposes the story into a shared reference prompt plus scene prompts.
- Artifact and licence: code DavidDinkevich/Story2Board, LICENSE "MIT License, Copyright (c) 2025 David Dinkevich". Base weights FLUX.1-dev, whose card says license "flux-1-dev-non-commercial-license". Benchmark data release: UNVERIFIED.
- Touches: image engine only. Product value: low (FLUX/DiT, not SDXL). Paper value: none/baseline. Integration form: baseline-only.
- Cost: FLUX.1-dev 12B is not an 8GB native model (paper reports no VRAM; UNVERIFIED); would be a second model beside NoobAI, violating the "NoobAI primary, one model per image" rule.
- Limits (stated, Sec 4.6): inherits attention entanglement of the base model. Found: the shared reference prompt is a single text "anchor" built from the full story, so no per-epoch (disguised/aged) reference; explicit LPA doubles tokens per panel.
- **Decision: reject as an integration** (model-stack conflict + licence); keep as a related-work baseline. Test: none; citing only.

## 5. VinaBench
- Source: Gao, Mathew, Mi, Mamooler, Zhao, Wakaki, Mitsufuji, Montariol, Bosselut (EPFL, Sony). arXiv 2503.20871v3 [cs.CV], 3 Apr 2025; CVPR 2025 (arXiv comment). [PUB]
- Contributes: Sec 3 annotates existing visual-narrative datasets (VWP, StorySalon, Storyboard20K) with commonsense links and discourse constraints (global: character profile, appearance style; per scene: characters, time of day, location), produced by Llama3.1-70B and VLMs; expert check of 100 samples (Table 1, acceptance 84.5-95.5%). Sec 4: VQA-based metrics (LLaVA-OneVision-72B): alignment ranking, fine-grained alignment, and Style / Character / Location consistency. Sec 5-6: ARLDM, StoryGen, MM-Interleaved with constraints improve results.
- Artifact and licence: code Silin159/VinaBench "Apache-2.0"; data on HF Silin1590/VinaBench, card license "cc-by-nc-4.0" (source images from VWP etc. carry their own terms: UNVERIFIED).
- Touches: eval only (`scripts/eval/`); its Character and Location consistency metrics could audit EchoTales panels. Product value: low-medium (a ready VLM-judged consistency metric). Paper value: ablation/eval baseline at most. Form: baseline-only (metric reference).
- Cost: a 72B VLM judge does not fit 8GB; a small VLM substitute would void comparability. 2-3 days to port the metric idea.
- Limits: LLM/VLM-annotated constraints (not human gold); no disclosure or time-of-knowledge axis; English kids' stories and cartoons, not web novels. Judge hallucination (VLM) is a threat; no human audit of judge on manga.
- **Decision: baseline-only.** Test: ask whether its Character-consistency judge agrees with a 50-panel human label set on RI before using it for any number.

## 6. ViStoryBench
- Source: Zhuang, Huang, Hu, Wu, Cheng, Liao, Wang, Liao, Cai, Xu, Zhang, Zeng, Huang, Yu, Zhang (ShanghaiTech, StepFun, AIGC Research). arXiv 2505.24862v5 [cs.CV], 29 Mar 2026; "Accepted by CVPR 2026" (arXiv comment). [PUB]
- Contributes: Sec 3: 80 stories, 1,317 shots, 344 characters, 509 reference images, 10 styles; per-shot scripts (setting, onstage characters, perspective, actions). Metrics: CSD style similarity, Character Identification Similarity (CIDS, detected-box matching), prompt alignment via Gemini-3-Pro (Qwen3-VL for reproducibility), onstage character count, copy-paste rate, Inception, Aesthetic score. 25 methods evaluated, Copy-Paste baseline included.
- Artifact and licence: code ViStoryBench/vistorybench "Apache License 2.0"; dataset HF ViStoryBench/ViStoryBench card "license: mit"; but the 509 character reference images were "manually collect[ed] ... from the Internet" (Sec 3), so image rights are UNVERIFIED despite the MIT tag.
- Touches: eval harness only; CIDS needs a reference image per character, which EchoTales does not feed the generator (B7), though sheets exist for scoring. Product value: medium for regression-testing identity drift; paper value: ablation/eval baseline. Form: baseline-only (metric).
- Cost: CIDS/CSD run locally (small models); Gemini-3-Pro judge is paid, Qwen3-VL is the reproducible local option (size vs 8GB: UNVERIFIED). 2-4 days.
- Limits (stated, Sec 4.2 / App): "does not support accurate evaluation of comic-style or manga generation tasks that involve multi-panel layouts within a single image"; no background-reference evaluation; VLM hallucination; Chinese/English language variance. Found: no time-of-knowledge axis, so it cannot measure leakage.
- **Decision: baseline-only** (identity-drift sanity metric); never use it as evidence of reveal-faithfulness. Test: run CIDS between a character's sheet and its panels across one chapter before/after any change; report as drift not correctness.

## 7. "Jularr" pull request #451
- Source: repository **Juloc/Jularr** (public, C#/.NET book and light-novel reader, created 2026-09-22), PR #451 "feat(chapter-artwork): spoiler-safe generated chapter artwork", author Juloc, opened 2026-09-27T12:45Z, merged 2026-09-27T16:43Z, +3,581/-0, 31 files, closes #407, builds on #412 (shared story context; #412 not retrievable by API, 404). Tag: [PRIMARY] (PR body, file list, `ChapterArtworkPrompt.cs` at merge commit 9ac10b9 read; 14 tests described but not run). Not peer reviewed. Found by search, so not INACCESSIBLE.
- Contributes: the prompt for chapter N is built only from `StoryContextQuery.Before(N)` (entities first seen before N, facts recorded before N; entities with unknown first chapter excluded; aliases excluded). Chapter 1 gets a neutral image from title/genre/style. Scenes: "a known setting plus up to two figures whose look is already established (small, from a distance, no faces/names)". Second independent check `ChapterArtworkSpoilerGuard`: forbidden-name list (names/aliases/terms first seen at or after N, or unplaced; hidden chapter titles) + 5-word/8-character shingle overlap with chapter N, N+1 and later text; failure falls back to a neutral prompt, else generation fails. Image via OpenAI-compatible /images/generations (hosted provider, owner-configured image model). No reference-image conditioning at all.
- Artifact and licence: the repo has NO LICENSE file in the root listing and the GitHub API returns `license: null` (404 on /license); README has no licence line. Default = all rights reserved; code cannot be reused. UNVERIFIED beyond that. Data/weights: none.
- Touches (as a design pattern only): `render/panels.py` prompt assembly and a post-assembly leakage guard; `world/context.py` (A2) and `persona/reference_gen.py` (A1/A3) are where EchoTales lets later state in. In a skim I found no final-prompt string guard in `render/` (UNVERIFIED; grep hits on "leak" were not inspected).
- Product value: **high** as a pattern: (a) single "Before(N)" query as the only source for the image prompt; (b) an independent lexical guard on the finished prompt. Paper value: **NOT none** — it is dated prior art (27 Sep 2026) for the generic claim "spoiler-safe generated images from pre-chapter state with a second leakage check". Differences that remain for EchoTales: reference-asset admissibility with transitive lineage, observer policy (reader/character/omniscient), retraction-aware facts, and an evaluation. Jularr tests are unit tests with fakes, and the guard is name- and passage-based (misses visual leaks, e.g. a described scar or hair colour revealed later).
- Integration form: isolated adapter (a post-prompt guard + a "Before(N) only" policy check in the render path). Cost: 2-3 days, CPU only.
- Limits: lexical only; "Aliases have no chapter" so all aliases are blanket-forbidden (over-blocks); no visual verification of the produced image; owner-hosted paid image API.
- **Decision: adapt** (reimplement the idea; do not copy code, no licence). Flag as novelty threat (Section 10).
- Test: seeded-leak test on RI: take panels whose prompts we know contain a later-revealed name, alias or appearance clause; guard must catch it (recall on seeded leaks) and must not block clean panels (false-block rate on a human-checked sample). Report both. Text-only, so it supports "prompt hygiene", not visual correctness.

## 8. Cross-donor product synthesis (EchoTales defects)
- B3 honest `conditioned_on`: none of the donors helps; fix is local (derive from the request actually sent). CANVAS/VideoMemory both log retrieved anchors per shot, which is the right shape.
- B4 undated wiki canon: Jularr excludes "unknown first chapter" entities outright, a simple fail-closed rule worth copying for canon traits with no dating.
- Single narrative-state policy (A4): Jularr's one `Before(N)` query feeding image prompts is a concrete example; extend it to voice by sharing the same `GenerationState`.
- Reveal-aware reference selection is already implemented in `core/visual_memory.py` but optional and default-off in `plan_builder.py`; `panels.py` still passes `reference_images=[]`. No donor supplies a reference-leakage test.

## 9. Proposed reference-leakage test (EchoTales-side, no donor provides it)
Definition: for panel at (p, k, observer), a reference asset R is leaking if any fact in its provenance closure (including parents it was conditioned on) has disclosure > k, or if R was generated from whole-novel `appearance_of` (A1/A3). Count over a chapter: leaked references / selected references, per arm (legacy flat read, `VisualMemorySelector`, flat-bank VideoMemory-style). Seeded positives: sheets built from post-reveal appearance. This tests provenance only; it does not show the pixels cannot depict the leak (as `visual_memory.py` itself states).

## 10. Summary (10 lines)
1. Best 3 product adoptions: (i) Jularr-style independent final-prompt leakage guard + single Before(N) source (adapt, 2-3 days, CPU); (ii) causal-window Consistent Self-Attention from StoryDiffusion as an opt-in config switch (adapt, conditional on VRAM proof; authors tested only 24GB); (iii) ViStoryBench CIDS/CSD as a drift-regression metric (baseline-only, not a correctness claim).
2. Overlap/novelty threats: Jularr PR #451 (merged 27 Sep 2026, no licence) is prior art for "spoiler-safe image generation from pre-chapter state with a second check" (prompt level, no reference lineage, no observer). The Gen4AVC poster "Grounding the Visual Axis of a Narrative World Model: Consistency-Aware Reference Generation" is **INACCESSIBLE** (OpenReview 403 challenge); same group as the Narrative World Model paper, whose last line says "NWM-conditioned generation is future work"; overlap with reveal-aware reference selection is UNKNOWN and should be read by the owner.
3. CANVAS and VideoMemory plan from the whole script ("Future Cond", "plans all scenes and shots") and use hosted Gemini image models; both are structurally non-reveal-aware and out of budget: baseline-only.
4. Story2Board runs on FLUX.1-dev (non-commercial licence) and conflicts with the NoobAI-only rule: reject as integration.
5. StoryDiffusion Eq. 2 samples tokens from all other batch images: later panels can influence earlier ones, a reveal leak unless the batch is causal (inference from the method text, untested).
6. Licences: VideoMemory CC BY-NC-SA 4.0; Jularr none (all rights reserved); VinaBench data CC BY-NC 4.0; ViStoryBench dataset MIT but reference images scraped from the Internet; StoryDiffusion Apache-2.0; Story2Board MIT; CANVAS nothing released.
7. Corrections: the poster is not unreadable by location (it is listed, poster #2, PDF on OpenReview) but still inaccessible to automated fetch; NoobAI-XL 1.1's own card (README line "II. Commercial Prohibition") bars commercial use of model-generated products, which constrains any "product" claim; StoryDiffusion needs about 20GB+ per its README, so "fits 8GB" is unsupported; 8GB GPU itself remains unconfirmed.
8. No LEAD-only row was marked adopt; all adapt decisions are conditional on a measured test (seeded-leak recall and false-block rate; 3-arm CSA run with VRAM log and human image inspection).
9. None of the donors fixes B3/B4/B7; those are local code changes (derive `conditioned_on` from the sent request; date wiki canon).
10. Paper value across F5: baseline/ablation only; Jularr is the single item that lowers claimed novelty and must be cited.
