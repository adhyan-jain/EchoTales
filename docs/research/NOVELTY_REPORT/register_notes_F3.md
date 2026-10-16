# Integration Register notes, family F3: leakage and memorisation controls (2026-10-15)

Claim under test: disclosure-faithful identity resolution under parametric leakage (premature-resolution metric; leakage = change under consistent renaming; evidence-gated link rule). Scope of this file: evaluation methodology only. Merging a technique is ENGINEERING, never paper novelty. Nothing was run, nothing in the repo was edited; downloads are in the session scratchpad (`regF3/`), read with `pdftotext` only. Tags: [PUB] method+experiment sections read in the paper text; [LEAD] snippet/abstract only; UNVERIFIED; INACCESSIBLE. Licence rows quote what I fetched (raw LICENSE file, or Hugging Face API metadata); GitHub API was rate-limited, so a missing LICENSE file means UNVERIFIED, not "none". Costs use the L1 rate card (`PREREG_L1`: $0.20 / 1M input, $1.20 / 1M output) and the L1 actual ($0.0267 for 281 calls).

## What the family says about the EchoTales claim, in five lines
- Renaming as a memorisation control, and "leakage = score on real names minus score on renamed names", are established (J&F; SynthWorlds calls it the knowledge advantage gap KA = P_R - P_S). Not ours.
- Nobody in this family has a chapter-prefix, a disclosure time or a premature-resolution count. Closest: NarraWorld's stated aim (F-other), LifeState-Bench's qualitative "models predict future plot details" remark (block 5).
- Two finance papers show the renaming gap is NOT pure leakage: it also contains distraction and information loss, and the anonymised arm can win. Our +9.7 point A-minus-B gap has the same confound plus a known-defective renamer (T4 v3 gate failed).
- Our closed-book probe has no positive control; SynthWorlds, Speak Memory and Gao et al. each build one.
- Closed-book item filtering (SagaScale) would delete exactly the items our metric needs.

---
## 1. Jiang & Ferraro
- Source: "Beyond Math: Stories as a Testbed for Memorization-Constrained Reasoning in LLMs", Yuxuan Jiang, Francis Ferraro (UMBC); arXiv 2412.14368v6, 24 Apr 2026; no venue stated in the text; [PUB] (Sec. 1-7, App. B-H read; local `paB/jiang.txt`).
- What it contributes: Sec. 4 "Inductive" prompt-only arm (verbatim vs gist prompts; gist = "do not rely on pre-learned entity associations") and Sec. 5 "Restrictive" name replacement (masking P0/P1, cross-cultural, same-cultural) on six tasks incl. character coreference (Screenplay F1, GPT-4o 58.3 original -> 49.6 renamed, Table 3). Sec. 5.1 adds a Source-Identification probe: after replacement, can the model still name the source work (200 segments, 40 works); cross-cultural replacement is the strongest disruptor. Three runs per setting, temperature 0 (App. H), prompt-paraphrase robustness (Table 9).
- Artifact and licence: no code or data URL for this paper in the text (only a Llama model-card link); licence UNVERIFIED. CharBench reuses public datasets; CharScript (200 segments) is described, not linked.
- EchoTales component: renaming control (T4/`pi`), validity gate, baseline arms for C1b.
- Product value: low directly; its audit ideas protect the evaluation, not the pipeline.
- Paper value: ablation baseline. Strongest baseline for C1b is "whole-input renaming" plus their gist prompt ("answer only from the passage, ignore remembered knowledge") as a prompt-only mitigation arm. Exact difference from our claim: they have no prefix, no disclosure time, no premature rate; they rename main characters only (Table 7 caption); their accuracy drop mixes memory with whatever the renamer breaks.
- Integration form: baseline-only (renaming already exists); two small adapters worth copying: (a) source-identification leak audit run on OUR renamed prompts, (b) a gist-prompt arm. Isolated adapter, no pipeline change.
- Cost: audit about 62 prompts x ~400 tokens = ~25k tokens, about $0.005; gist arm about $0.007 (L1 rate). CPU only, no GPU.
- Evidence needed and available: need renamed-prefix source-ID rate (expected near 0 if renaming works) and a blind second-pass gold-preservation check on the hard items; available: L1 prompts, `pi` seed 20261015, 62 hard items; the single annotator can do the blind pass.
- Limits (stated): GPT-4o era models, Western TV/movie sources likely heavily memorised (Limitations), no human study of reasoning. Limits (found): the human validation (App. G) is 3 unpaid volunteers, 100 multiple-choice items, MC TV answers not alias chains; the reported max change is 2.2 pp (Sec. 5.1), 7.2 pp (App. G text) and 2.7 pp implied by Table 8 (Person 2); the headline drop is 45.2% in the abstract, 45.8% in the intro, 46.2 in Table 3. Their own finding 3 (Sec. 6.3) is that removing memory can IMPROVE some tasks, so a drop is not proof of leakage.
- Decision: adapt (take audit + gist arm + dose-response; keep renaming as baseline).
- Test: with `pi`, ask "which novel is this?" on the 62 renamed windows; if the model names the serial on more than a handful, the control leaks and the gap is understated. Gate for the gist arm: its premature rate must be reported next to the evidence-gated arm D; if gist alone matches D, C1b adds nothing over a prompt.

## 2. SynthWorlds
- Source: "SynthWorlds: Controlled Parallel Worlds for Disentangling Reasoning and Knowledge in Language Models", Ken Gu, Advait Bhat, Mike A. Merrill, Robert West, Xin Liu, Daniel McDuff, Tim Althoff; ICLR 2026 (header: "Published as a conference paper at ICLR 2026"); arXiv 2510.24427; [PUB] (Sec. 1, 3, 5, 6, App. A, B.2, B.5, B.6, Table 2, 4, 5; local `paA/2510.24427.txt`).
- What it contributes: parallel real-mapped (RM) and synthetic-mapped (SM) corpora from Wikidata; KA = P_R - P_S (Sec. 3). Renaming rules (App. A): type-consistent names and a name-derivation dependency DAG (u depends on v when v's label is a substring of u's AND a KG relation links them; rename in level-order) so "Vancouver -> Metronis" propagates to "George Vancouver -> Altheon Metronis"; timestamps shifted by a fixed offset. Validation: closed-book SM F1 0.2-1.8 vs RM 17-22 (Table 4) as the "memory is gone" floor; programmatic + LM checks; page removal for einsteinium-style derived names (App. B.6); 798-fact human check (kappa 0.85 on 7 pages, B.5) which validates fact expression, not obfuscation.
- Artifact and licence: github.com/behavioral-data/synthworlds (code; no LICENSE at `main` or `master`, UNVERIFIED); dataset huggingface.co/datasets/kenqgu/synthworlds, HF metadata `license:cc-by-4.0`.
- EchoTales component: `pi` renamer design (T4 v3 failure classes), SIO synthetic worlds, probe calibration.
- Product value: low. Paper value: ablation baseline plus a novelty THREAT to the leakage definition: our "leakage = rate(original) - rate(renamed)" is KA under another name; novelty can only be in the prefix/disclosure framing. Difference: encyclopedic multi-hop QA and page navigation, no fiction, no alias task, no prefix.
- Integration form: adapt (config switch in the renamer: closure over substring-related names). Cost: graph pass is CPU only; name generation can be deterministic (their LLM renaming cost $0.06 for 0.3K calls, Table 2).
- Evidence needed and available: T4 v3 failed on inflected plurals, case variants and common-word names (`PREREG_T4_v3` section 0), the same family as their substring-closure. Available: 335 name surfaces and the G1-G3 gate, runnable on CPU.
- Limits (stated): needs a clean KG; only capitalised entities renamed; literals excluded. Found: the "rename-leak audit" the register previously credited is a design rule and page exclusion; no residual-leak rate is measured. The Tokyo -> Torioka line is an example of naive renaming, not a measurement.
- Decision: adapt. Test: reimplement `pi` with substring-dependency closure and re-run the existing G1-G3 gate on the 335 surfaces; accept only if G1=G2=G3=0. If it passes, the L1-B arm can be re-run (about $0.01 per arm).

## 3. SagaScale
- Source: "SagaScale: A Realistic, Scalable, and High-Quality Long-Context Benchmark Built from Full-Length Novels", Guancheng Du, Yong Hu, Wenqing Wang, Yaming Yang, Jiaheng Gao; arXiv 2601.09723v1 (stamp 27 Dec 2025); no venue stated; [PUB] (Sec. 1, 3.1-3.3, 5, 6, App. prompts, Table 4; local `paB/saga.txt`).
- What it contributes: QA generation from Wikipedia/Baidu Baike segments grounded in book chunks, then three filters; Contamination Filtering (Sec. 3.1): four frontier models (GPT-4.1, DeepSeek-R1, Claude-Opus-4, Gemini-2.5-Pro) answer each question closed-book with the novel NAME given (Fig. 14 prompt); if any is correct the item is dropped. 11,584 generated -> 1,124 kept (9.7%, my arithmetic). Check: closed-book max 11.7% on survivors (Table 4). Authors verified 100 items (95 fully correct); judge kappa 0.92 on 100 samples.
- Artifact and licence: github.com/ducatiqwq/SagaScale `LICENSE` fetched at `master`, first line "MIT License"; HF dataset ducatiqwq/SagaScale metadata `license:apache-2.0` (data licence for copyrighted novels not independently checked).
- EchoTales component: closed-book probe arm C; item selection.
- Product value: none. Paper value: ablation baseline. A reviewer will ask "why not simply filter items the model already knows?". Difference: filtering removes the leak-susceptible items, which are the premature-resolution items; the survivors are by construction those where parametric knowledge fails, so it cannot measure leakage.
- Integration form: baseline-only; use "any of K models answers closed-book" only as a per-item stratifier (leak-susceptible vs not), never as a filter.
- Cost: K=2-3 models x 62 items x ~150 tokens: under $0.02 at the L1 rate; CPU only.
- Evidence needed and available: closed-book answers on all 72 sheet items from at least two models; available: arm C prompts for 15 items, 14/15 abstentions (`l1_analysis.json`).
- Limits (stated): QA only, 1,124 items, English+Chinese, single task; filter keeps few items (Sec. 6). Found: filtering is by-answer-correctness for four named models only, so it certifies nothing about partial or alias-level memory; abstention hides recall (see block 6).
- Decision: baseline-only. Test: show how many of the 23 pre-reveal items a closed-book filter would delete from our set; if it deletes the ones where A names the silver final identity, that is the argument against filtering.

## 4. Glasserman & Lin (look-ahead bias; DOMAIN OUT-OF-FIELD, method relevant)
- Source: "Assessing Look-Ahead Bias in Stock Return Predictions Generated By GPT Sentiment Analysis", Paul Glasserman, Caden Lin (Columbia); arXiv 2309.17322v1, 29 Sep 2023; text shows no venue (Wu et al. cite it as 2024; venue UNVERIFIED); [PUB] (Sec. 1, 2.1-2.4, 3.1-3.2; local `regF3/txt/2309.17322.txt`).
- What it contributes: compare trading-signal quality on original vs anonymised headlines (company name and up to 20 Google-KG products replaced by "Blahblahblah", fuzzy InDel match threshold 80, abbreviations), separately IN-sample and OUT-of-sample relative to the model's training cutoff (GPT-3.5, Sept 2021). Names two effects: look-ahead bias and a "distraction effect" (general knowledge about the entity). Result: anonymised headlines did BETTER in-sample (+5.89 and +4.37 bp/day, p=0.066 and 0.017), so distraction outweighed look-ahead.
- Artifact and licence: none stated in the text; UNVERIFIED.
- EchoTales component: interpretation of the A-minus-B gap; residual-identifier audit.
- Product value: none. Paper value: ablation baseline / reviewer-attack source. Exact difference: no identity task, no prefix, no disclosure time; but it proves that "original minus anonymised" is not signed leakage.
- Integration form: baseline-only (an analysis rule, no code). Cost: zero.
- Evidence needed and available: an estimate of the renaming gap where leakage is impossible (SIO worlds, unseen by any model by construction; or text published after the model's cutoff). Available: SIO generator and results on CPU; cutoff of `gpt-5.6-luna` UNVERIFIED.
- Limits (stated): headlines only, one model; their method misses indirect identifiers (they add product lists after finding iPhone leaks). Found: no human audit of the anonymiser and no residual-identification test in the text; spaCy NER was rejected for missing entities, a warning for any NER-based renamer.
- Decision: adapt as an analysis rule (report gap(real text) minus gap(unseen text), not the raw gap). Test: run arms A and B on SIO items; if the A-minus-B gap there is non-zero, part of the +9.7 points is renaming damage, not memory.

## 5. LifeState-Bench (verified: a lifelong-learning dialogue benchmark; task OUT-OF-FIELD)
- Source: "If an LLM Were a Character, Would It Know Its Own Story? Evaluating Lifelong Learning in LLMs", Siqi Fan, Xiusheng Huang, Yiqun Yao, Xuezhi Fang, Kang Liu, Peng Han, Shuo Shang, Aixin Sun, Yequan Wang; arXiv 2503.23514v2, 13 Apr 2026 ([PUB], Sec. 1, 3, 4.4, 5, 6, 7); venue ACL 2026 long paper 2026.acl-long.1659 from a search snippet only ([LEAD] for the venue). Name is "LIFESTATE-BENCH" in the arXiv text.
- What it contributes: episodic Hamlet (character names replaced) and a Claude-3.5-generated synthetic script set; per-episode fact questions on self-awareness, memory retrieval and relationship shift with answers that evolve over episodes (Fig. 2); context = episodes E1..E_{t-1} (prefix-like) plus parametric (knowledge editing, LoRA) vs non-parametric (concatenation, summaries) memory. Sec. 4.4: "when character names were restored, the model could still generate correct answers without context"; Sec. 6: after replacement "models sometimes predict future plot details"; the synthetic set "avoids such contamination".
- Artifact and licence: none stated in the text; one search found no repository; UNVERIFIED.
- EchoTales component: none directly; one probe idea.
- Product value: none. Paper value: none as a method (no identity task, no premature metric, no CI on the leak remark, qualitative). It is a 1-sentence supporting citation that renaming alone did not stop plot-level leakage on a famous play.
- Integration form: reject as a donor; cite only. Cost: n/a.
- Evidence needed and available: the probe it implies (restore the real names in a closed-book question, see whether the model answers without context) is what arm C does with 15 items.
- Limits (stated): small sample counts, Hamlet may be contaminated. Found: leak remark is anecdotal; time-indexed answers exist but are used to test retention, not to penalise early knowledge.
- Decision: reject (cite). Test: none; revisit only if the authors release per-episode ground truth we could reuse as a disclosure-time oracle.

## 6. Extra donor A: Gao, Jiang, Yan, "Detecting Lookahead Bias in LLM Forecasts" (OUT-OF-FIELD domain)
- Source: Zhenyu Gao, Wenxi Jiang, Yutong Yan (CUHK Business School); arXiv 2512.23847v2, June 2026 (earlier title "A Test of Lookahead Bias in LLM Forecasts"); working paper, no venue; [PUB] (Abstract, Sec. 1, 2.1, data section; proofs skimmed only).
- What it contributes: Lookahead Propensity LAP = P(up)+P(down) read from first-token probabilities of an identifier-only recall query (firm, ticker, date, nothing else) with an explicit "unknown" option; LAP collapses to about zero right after the training cutoff (positive/negative control built into the design); interaction of LAP with the model's forecast tests whether the signal loads on memory. Llama-3.3-70B via logprobs; they note closed APIs work if logprobs are exposed.
- Artifact and licence: "detection procedure specified in a CLAUDE.md instruction file, available for download here" (link not in the extracted text); licence UNVERIFIED.
- EchoTales component: the closed-book arm C (replace argmax answers by probability mass on committing options).
- Product value: none. Paper value: ablation baseline (a stronger memorisation probe than ours). Difference: no text input, no prefix, no identity linking.
- Integration form: isolated adapter, optional. Cost: about 60 short prompts; under $0.01 if the provider returns logprobs, otherwise needs a local open model (qwen2.5:7b is configured; must check GPU is free first, no CPU offload per owner note). `gpt-5.6-luna` logprob support UNVERIFIED.
- Evidence needed and available: 14/15 abstentions under argmax show the probe is uninformative at the answer level but say nothing about probability mass; no logprobs recorded.
- Limits (stated): needs token probabilities; task-specific. Found: a local open model's memory is not the evaluated model's memory.
- Decision: adapt, conditional on logprobs. Test: on a positive-control book the model is known to know (block 8) LAP-style mass must be high, and on the renamed prompt near the chance level; otherwise the probe stays uninformative.

## 7. Extra donor B: Wu, Yang, Ying, Zhou, "Anonymization and Information Loss" (OUT-OF-FIELD domain)
- Source: Ke Wu, Baozhong Yang, Zhenkun Ying, Dexin Zhou; arXiv 2511.15364v2 [q-fin.GN], 5 Sep 2026; conference talks listed, no venue; [PUB] (Abstract, Sec. 1, 2.3, 4.1-4.3; tables skimmed).
- What it contributes: separates look-ahead removal from information loss by evaluating raw vs anonymised text on POST-cutoff data (cutoff Oct 2023, window Nov 2023-Dec 2024) where memorised outcomes cannot exist, then checks the pre-cutoff interaction. "Anonymization gap" = attenuation-adjusted |raw - anonymised| per document, needing no outcome labels. Anonymising loses signal: entity and number masking changes how the rest is read (Shapley split about 41% evidence displacement, 59% interpretive distortion). Tested with spaCy-TRF and LLM-paraphrase anonymisers on GPT-4o-mini/4o/o3-mini.
- Artifact and licence: none for the method; the cutoff-date list it cites is github.com/HaoooWang/llm-knowledge-cutoff-dates (not fetched); UNVERIFIED.
- EchoTales component: interpretation and control of the renaming gap; the per-item gap as a diagnostic.
- Product value: none. Paper value: ablation baseline and the strongest reviewer attack on "leakage = gap under renaming". Difference: finance text, no prefix.
- Integration form: baseline-only (analysis rule) plus a per-item disagreement flag A vs B in the existing runner output. Cost: zero extra calls for the flag; unseen-text control uses SIO (about $0.03).
- Evidence needed and available: renaming gap on unseen text (SIO or post-cutoff chapters). Not available yet for real serials: post-cutoff chapters of the same copyrighted serial are held locally only.
- Limits (stated): scoring tasks in finance; framework assumes a linear projection. Found: the "information loss" our renamer causes in clan-head items (family tokens shared) is the same mechanism.
- Decision: adapt (adopt the unseen-text control as a registered requirement). Test: difference-in-differences = (A-B on real serial) minus (A-B on SIO or post-cutoff text) with a paired bootstrap; leakage is claimed only if the difference's CI excludes 0.

## 8. Extra donor C: Chang, Cramer, Soni, Bamman, "Speak, Memory"
- Source: "Speak, Memory: An Archaeology of Books Known to ChatGPT/GPT-4", EMNLP 2023 (the cited proceedings entry in J&F: pp. 7312-7327); arXiv 2305.00118v2, 20 Oct 2023; [PUB] (Sec. 1-7, Tables 1-5; local `paB/speak.txt`).
- What it contributes: name cloze membership probe: 40-60 token passages with exactly one person name masked, no other named entity, 100 passages per book, model must guess; human baseline 0%, most-frequent-name baseline 0.6%; accuracy tracks web duplication (Spearman 0.70-0.84 on pre-1928 works). Positive controls are free: Alice 0.98, Harry Potter 0.76, GPT-4. Also shows downstream tasks do better on memorised books (publication year MAE 0.6 vs 14.5 years) and that memorised books' names bleed into other contexts (log-odds test).
- Artifact and licence: github.com/bamman-group/gpt4-books (code and data); no LICENSE file at `main`/`master`; UNVERIFIED. Cost reported about $400 for 571 books.
- EchoTales component: replacement for the failed closed-book alias probe (arm C).
- Product value: none. Paper value: ablation baseline / probe validation. Difference: tests memory of passages, not alias-to-identity or disclosure time.
- Integration form: isolated adapter. Cost: 100 passages from our serial, plus 100 from a famous public-domain novel as positive control: about 200 x 150 tokens = 30k input tokens, about $0.01; CPU only. BookNLP is not needed; we already have mention spans.
- Evidence needed and available: need passages with one masked person name from the translated serial; available from the existing chapters (copyrighted, local only). Caveat: translated web serials were probably never memorised at name level, so a floor result is the likely outcome.
- Limits (stated): closed-model archaeology, no training data access. Found: the probe is binary on exact names; a translated serial with unstable name renderings can score zero for non-memory reasons.
- Decision: adapt. Test: positive control must show clearly above-floor accuracy (Alice-class), the serial must be compared to its renamed twin, and the pre-registered statement is only "not detected", never "no memory".

## 9. Extra donor D: Gupta, "WhoDunIt"
- Source: "WhoDunIt: Evaluation benchmark for culprit detection in mystery stories", Kshitij Gupta (BITS Pilani); arXiv 2502.07747v1, 11 Feb 2025; no venue; [PUB] (Sec. 1-6 and appendix; short paper).
- What it contributes: Project Gutenberg mystery stories, culprit labels from CliffsNotes or reading, five name conditions (original, full swap, Harry Potter names, Hollywood names, Bollywood names), four prompt styles, 10 trials with majority vote on GPT-4o, GPT-4-turbo, GPT-4o-mini. Original-name accuracy highest; the full swap drops accuracy; the famous-name conditions rose again (Sec. 5.3). Appendix excerpts "Point of Reveal" passages for two stories.
- Artifact and licence: github.com/kjgpta/WhoDunIt-Evaluation_benchmark_for_culprit_detection_in_mystery_stories; dataset kjgpta/WhoDunIt on HF, metadata `license:apache-2.0`. Dataset card fields: full text, title, author, length, culprit_ids; no reveal-position field, so the task is omniscient culprit detection on the whole story.
- EchoTales component: none beyond a citation. Product value: none. Paper value: none (a reviewer may cite it as prior renaming-on-mysteries).
- Integration form: reject. Cost: n/a.
- Evidence needed and available: n/a. Limits (stated): short and medium stories only. Found: no CI, no human check of the swaps or of the culprit labels in the text read, the figures are bar charts, the famous-name substitution adds a new memory cue, so it is not a neutral control. It does NOT do prefix-before-reveal evaluation; I checked the dataset card for a reveal position and found none (it is not a threat to the premature-resolution idea).
- Decision: reject. Test: none; keep only as the cautionary example that famous replacement names are not a control.

## 10. Extra donor E: Yu et al., "Few-Shot Character Understanding in Movies" (ToM-in-AMC)
- Source: Mo Yu, Qiujing Wang, Shunchi Zhang, Yisi Sang et al.; arXiv 2211.04684v2, 2 Feb 2024; venue not shown in the extracted text, UNVERIFIED; [PUB] (Sec. 4 name perturbation, Sec. 7 results, Fig. 5; other sections skimmed). This is the paper J&F cite as "Yu et al., 2022" for same-cultural replacement.
- What it contributes: test movies' main character names replaced by random English names of the same gender to stop GPT-4 resolving the task from memorised film knowledge; Fig. 5 reports a GPT-4 in-context result on real vs perturbed scenes (the extracted numbers 71.7/63.8 and 73.6/67.8 are printed without a legible mapping, so I do not quote a drop); human accuracy 88.0% on the dev set, annotators had not seen the movies. Also: using mental states generated on non-perturbed scenes only helped slightly (68.2 -> 70.7).
- Artifact and licence: not stated in the text read; UNVERIFIED.
- EchoTales component: none beyond a citation. Product value: none. Paper value: none (earlier example of the same control). Difference: character classification, not alias linking.
- Integration form: reject. Cost: n/a. Evidence/limits: main characters only; no leak audit, no gold-preservation check for the perturbed set in the text read.
- Decision: reject. Test: none.

---
## Reusable method details, with CPU and cost flags (all my reading; none run)
1. Source-identification leak audit on renamed prompts (J&F Sec. 5.1). CPU only; about $0.005. Needed before any A-minus-B claim.
2. Positive-control book for every memory probe (Speak Memory Table 1; SynthWorlds RM closed-book). CPU only; about $0.01. Without it a null is uninterpretable; our R3 (1/15, 14/15 abstentions) has none.
3. Name-closure renaming (SynthWorlds App. A): substring-dependency DAG, level-order. CPU only. Fixes the T4 v3 classes (inflection, case variants, compound names) and is gated by the existing G1-G3.
4. Unseen-text difference-in-differences (Wu et al.; Glasserman & Lin in/out-of-sample; Gao post-cutoff collapse). SIO is unseen by construction: about $0.03 for A and B on the SIO items; CPU for the generator.
5. Probability-mass readout of abstaining probes (Gao LAP). Under $0.01 if logprobs exist; else local model, GPU first.
6. Dose-response across renaming schemes (J&F cross-cultural > same-cultural; SynthWorlds type-consistent). Report gap for at least two schemes; a gap that depends on the scheme is a renamer effect. About $0.01 per extra arm.
7. Blind second-pass gold-preservation check on hard items (J&F App. G): the single annotator re-answers renamed items blind, report agreement; no kappa claimed. Zero API cost.
8. Power (my arithmetic, not from a paper): the exact sign test on discordant A/B items gives p=0.0625 for 5:0, 0.031 for 6:0, 0.0156 for 7:0; the existing 6:0 result sits at the edge. Wilson CI width on a 62-item rate is about +/-12 points at 50%. Pre-reveal n=23 cannot detect rates below 12-22% (report section 5.2).
9. What EchoTales must ADD to be different: (a) the chapter-prefix and reader-warranted oracle (reveal chapter, UNDETERMINED label) which none of the 10 donors has; (b) a renaming validity gate on HARD items (not only 30 plain controls) because a renamer that splits inflections can break text-only inference (the three clan-head renamed failures in the post-hoc check match T4's defect classes); (c) the unseen-text control; (d) the baseline arms: renaming only, gist prompt, closed-book stratifier.

## 10-line summary
1. Novelty threat: no donor does premature resolution or disclosure time. Closest are LifeState-Bench (anecdote that models "predict future plot details" after renaming Hamlet) and NarraWorld (aim only); WhoDunIt has full-text culprit labels with no reveal field (dataset card checked).
2. The leakage definition (score on real minus renamed) is already SynthWorlds' knowledge advantage gap; our novelty is the prefix/entitlement framing only.
3. Strongest reviewer attack: the +9.7 point A-minus-B gap is not leakage; Glasserman & Lin and Wu et al. show the anonymised arm can win and that masking loses information, and our renamer failed its own commutation gate (T4 v3), so the three clan-head failures may be renaming damage.
4. Second attack: the closed-book probe has no positive control and 14/15 abstentions; Speak Memory, SynthWorlds and Gao et al. each include one.
5. Third attack: why not filter known items (SagaScale)? Answer: it deletes the leak-susceptible items that define the metric; use closed-book only as a stratifier.
6. Earlier claims corrected: SynthWorlds has no measured "rename-leak audit" (design rules, page exclusion, closed-book floor); J&F's human validation is 3 volunteers with internally inconsistent figures (2.2 / 7.2 / 2.7 pp, and 45.2 / 45.8 / 46.2 headline), so "human check that gold survives" is weaker than reported.
7. Adopt nothing outright. Adapt: leak audit + gist arm (J&F), name-closure renamer (SynthWorlds), unseen-text control (Wu, Glasserman & Lin), positive-control name cloze (Speak Memory), logprob readout (Gao, conditional). Baseline-only: SagaScale. Reject: LifeState-Bench, WhoDunIt, ToM-in-AMC.
8. Everything here is CPU or under $0.20 in total (estimates about $0.07 for audit, gist arm, SIO arms and name cloze at the L1 rate); only the LAP probe may need logprobs or a local GPU model.
9. Paper value: no donor adds novelty; they supply baselines (renaming-only, gist prompt, closed-book stratifier) and the validity gate that makes the metric believable. Merging any of them is engineering.
10. Not verified: licences for J&F, Gao, Wu, LifeState-Bench, Yu et al., the SynthWorlds/Speak Memory code (UNVERIFIED); LifeState-Bench venue (snippet); `gpt-5.6-luna` logprobs and training cutoff.
