# Novelty report support material: prior art, register notes, work plan, spend ledger, gate diagnosis

> Merged on 2026-10-22 from 17 separate documents to keep the docs tree small. Each section below is one original file, text unchanged; its old path is in the section heading. The originals are in git history.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/GATE_FAILURE_DIAGNOSIS.md -->
## Source: `docs/research/NOVELTY_REPORT/GATE_FAILURE_DIAGNOSIS.md`

# Gate failures: is the gate wrong, or the thing it tests? (diagnosis, 2026-10-15)

Standing rule from the owner: when something fails to get past a gate, check whether the fault is an engineering issue in the **gate** or in the **core engine** of the thing being tested, before treating the failure as a finding. Source for the numbers: `data/eval/chimera/gate_failure_diagnosis.json` (`scripts/chimera/gate_failure_diagnosis.py`, CPU only, no model, no spend; counts only). Label provenance: the T4 part has no labels (system-internal); the M1 part uses silver labels.

| Gate that failed or looked suspicious | Verdict | Evidence | What it means |
|---|---|---|---|
| **T4 renaming commutation gate** (v3: G1 = 2, G2 = 9, G3 = 0 on 335 surfaces) | **Engine** (the repo's character-level normaliser), not the gate | All 11 violations classify as `engine`: each violating class is 2 to 4 distinct surfaces that the repo's normaliser keeps as one key because they differ only by spacing, case or a trailing plural (for example a three-token name and its two-token spelling). A token-level renamer cannot map such a class to a single renamed class | The gate flags genuine non-commutation. "A token-level renaming cannot commute with this engine" is a true, specific statement about the engine (backlog B12), not evidence that renaming is unworkable. A character-level cipher that fixes the characters the normaliser strips (the earlier-proposed v4) is the principled fix; it was not tried because the owner closed T4 |
| **L1 / L1b evidence gate** (v1 over-rejected; v2 passes mostly via a shortcut) | **Mostly the gate**, not the model | Of 16 items the v2 gate rejected although the model gave a letter, 12 were silver-correct answers. In 8 of those 12 the full claimed name appears in the prefix window (2 rejected for spans not matching verbatim, 6 judged not entailed); only 4 had just part of the name in the window (the clan-head "Gu Yue" without "Bo") and those rejections are correct | The model usually answered as the silver label did; the gate's span matching and its masked entailment call reject answers that the visible text supports. Why the entailment call rejects (prompt strictness, masking that hides apposition and anaphora, or the model citing the wrong spans) is **not yet separated**: the cited spans were not stored by design, and the next run should keep masked inputs in the scratchpad for inspection |
| **SIO v1 "M2 = 0"** | **Engine** | The shipped resolver never uses reveal sentences (M3: 0 of 872 omniscient and reader-view links; it over-commits on every alias) | A true engine limitation; M3 shows the metric is sensitive once a reveal-aware layer exists |
| **Reveal detection in M3** (repo patterns find 80/80 on one template, 0/80 on three) | **Engine** (the detector's brittleness), not the evaluation | The oracle detector scores perfectly on all four templates, so the evaluation is sound | Rule-based reveal detection is the weak component |
| **L1 closed-book probe (14 of 15 abstentions)** | **Neither a gate nor an engine fault** | It is a probe with no positive control | Cannot support a conclusion about memory either way |

## What follows

1. Do not report "T4 failed" as "renaming does not work": report it as "this engine's normaliser is not compositional at the token level", and keep the character-level fix as the principled next step if the owner reopens T4.
2. Do not report the gate v2 pass as evidence for evidence-gated linking: the mechanism that is supposed to carry the claim (entailment of cited prefix spans) mostly rejected answers the visible text supports. A gate v3 must first separate the three possible causes of those rejections, using masked inputs kept for inspection and, ideally, the owner's human labels.
3. M3 and the SIO notes keep the engine-side limitation (no reveal handling) explicit.

## Correction after the T4 v4 attempt (2026-10-15)

The first diagnosis above classified all 11 v3 violations as "engine" using a coarse rule (the violating class is a set of surfaces the normaliser merges because they differ only by spacing, case or plural). That rule identifies the *precondition* (the engine does merge these variants) but not *where the fix belongs*. T4 v4 (`PREREG_T4_renaming_validity_v4.md`, a single pre-registered attempt with a letter cipher) failed its gate: G1 = 2, G2 = 4, G3 = 0, G4 = 1, G5 = 7 (`data/eval/chimera/t4_v4_results.json`, status `GATE_FAILED_NO_RUN`; no resolver run). Reading the members of the six remaining violating classes and their renamed forms showed one mechanism in all six:

- **Asymmetric protection.** The renamer leaves a token unchanged when its exact word form is a protected or common word, and ciphers it otherwise. So in one variant a token is protected and in the other (glued, singular, or plural form) it is not: `Gu` is unchanged standalone but ciphered inside the glued `GuMaster`; the plural `Contributions` and `Thunderwings` are protected but the singulars are not. The engine then keys the two variants differently after renaming.
- **Verdict: renamer design gap, not an engine property.** Protection must be decided per comparison-key class (a token is protected if any member of its class is), including inflections, not per word form. The v3 diagnosis's "engine" label was too coarse; the engine's character-level merging is what makes the requirement strict, but the missing step is in the renamer.
- **G4 and G5 are also renamer issues.** Renaming only name tokens leaves other words unchanged, so a ciphered short name can collide with an existing word or token (7 collisions, for example a two-letter name mapping onto a two-letter real token; one injectivity collision).

**Status.** T4 is closed by the pre-registered stop rule (no v5). A v5 with class-level protection and collision-aware short-token mapping is mechanistically motivated rather than tuned, but writing it would break the stop rule that I froze, so it needs the owner's explicit lift. L1's renaming validity remains the empirical check (R1 30/30 on controls), and the unseen-text control (spend request pending) is the direct test for renaming damage on LLM arms.

## T4 v5 outcome and a second correction (2026-10-15)

The owner lifted the no-v5 rule. v5 (`PREREG_T4_renaming_validity_v5.md`: class-level protection, CamelCase piece splitting, collision closure) **passed its gate**: G1 = G2 = G3 = G4 = G5 = 0 on the same 335 surfaces, 135 of 378 vocabulary tokens still renamed (v4: 147), closure stable in 2 passes. The resolver conditions ran once (`t4_v5_results.json`): determinism (O2) and identity (I) at exactly 100% of 11,174 mentions; renamed run R at 11,170 of 11,174 (99.96%, Wilson lower bound 0.9991, 4 changed mentions, all `evidence_loss`).

**Second correction (a defect in the negative control, found by the same gate-versus-engine check).** The v5 runner's negative control N' scored exactly as R, which under the pre-registered rule would make T4 inconclusive. Reading why showed N' used a second *consistent* cipher, a function of the token alone that cannot break containment, so it did not implement the pre-registered definition (rename "Yuan" differently after "Fang " than alone). That is an implementation bug in the control, not an engine or renamer fault (`PREREG_T4_v5_addendum_1.md`). Re-run as defined (`t4_v5_negative_control.py`): N at 11,169 of 11,174 (99.955%).

**Verdict by the letter of the v2 rule: PASS** (R at least 0.98, Wilson lower bound at least 0.97, O1 = O2 = I at 100%, N below R, interval not straddling 0.98). **Caveat that must travel with it:** N is below R by one mention. About 90% of this resolver's links are exact-surface gazetteer matches, so aggregate agreement cannot detect damage to the rarer containment-based evidence; the test shows the renaming leaves the engine's decisions 99.96% unchanged, not that it would detect subtle damage. A validated renaming control for the deterministic resolver now exists; it says nothing about an LLM (see L2U).

## Cross-novel replication (2026-10-16, `PREREG_T4_v5_addendum_2_crossnovel.md`): a third correction

The v5 rules, applied unchanged to scratch copies of LOTM (126 surfaces) and ORV (68 surfaces) (both 40-chapter databases), **passed the gate** (G1 to G5 = 0; 100 of 149 and 67 of 100 vocabulary tokens renamed) and the renamed resolver run agrees with the original on **100.0% of mentions** (2,402 and 2,267; Wilson lower bounds 0.9984 and 0.9983; O2 and I also 100%). The negative control N is not defined for these novels, so this is **not a full T4 PASS** (see the addendum).

**What it corrects.** The **v3 token-level renamer also passes the gate on both novels** (G1 = G2 = G3 = 0). So the T4 v3 failure on RI was **specific to RI's vocabulary** (glued and plural variants such as "GuMaster" and "Thunderwings"), not a property of token-level renaming against this engine. The statements above that "this engine's normaliser is not token-compositional" and "renaming fails" are too general; the correct statement is: the commutation gate is **discriminating** (it fails a naive renamer on a corpus with glued and inflected name variants and passes it on corpora without them), and the class-protected cipher passes on all three. Gate-versus-engine attribution, third version: the failure is a **corpus x renamer interaction**, not the engine alone and not the gate.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/INTEGRATION_REGISTER.md -->
## Source: `docs/research/NOVELTY_REPORT/INTEGRATION_REGISTER.md`

# Integration Register (M0), 2026-10-15

Scope: plan v3 section 16. Six donor families, 43 donors read by six reading passes (notes: `register_notes_F1.md` to `register_notes_F6.md`, which hold the full per-donor fields: verified source, method and experiment sections read, licence, EchoTales component, cost, limits, test). This file is the consolidated decision table.

**Rules applied.** Merging a technique is Track S (engineering) and never a paper contribution. "Paper value" is only novelty, ablation baseline, or none. No row is `adopt` on an abstract: every row below was read in its method and experiment sections (`[PUB]`) except where marked. Nothing here was run on EchoTales data (no measurement), so no donor is a plain `adopt`; each `adapt` waits for the test named. Label provenance: any EchoTales number quoted here is silver or system-internal, and says so.

Tags: `[PUB]` method and experiment sections read in the paper itself; `[README]` repo README only; `[LEAD]` snippet or abstract; `UNVERIFIED`; `INACCESSIBLE`. Licences come from a fetched LICENSE file or model card unless marked UNVERIFIED (some from the GitHub API field).

## 1. Decision table

### F1 Mention detection and coreference (`register_notes_F1.md`)

| Donor | Tag | Touches | Product value | Paper value | Form | Licence | Decision | Test that justifies it |
|---|---|---|---|---|---|---|---|---|
| Maverick (ACL 2024) | `[PUB]` | mention detection, title spans | Proposes title and relational spans the gazetteer misses (58/88 silver hard cases undetected) | ablation baseline | research-only adapter | **CC BY-NC-SA 4.0**: blocks product use | adapt (research only) | Precision on added mentions against human-verified hard cases at a bar the owner sets |
| BookCoref (ACL 2025, arXiv 2507.12075) | `[PUB]` | LLM yes/no verifier on non-gazetteer mentions | Reported link precision 88.6 to 93.8 in their ablation | **overlaps C1b**: precision-first LLM-verified linking is theirs | config switch | repo README says NC, HF card says CC BY-SA 4.0 (conflict) | adapt the verifier; baseline-only for gold; reject window expansion (omniscient by construction) | Verifier under renaming (their App. C concedes parametric-memory answers) |
| LlmLink (COLING 2025) | `[PUB]` | linking with character memory | none cheap (needs paid APO, large model) | baseline | baseline-only | GPL-3.0 | baseline-only | Repo's Baseline B must be labelled "LLMLINK-style, reduced" |
| KoCoNovel (arXiv 2404.01140) | `[PUB]` | annotation protocol for the reader-view item set | Template for human labelling (sequential reading, change log, kinship/title rules) | none (dual labels already exist) | protocol only | data Korean, unusable | adapt protocol; reject data | A 60-item two-annotator pilot |
| FantasyCoref (CRAC 2021) | `[PUB]` | taxonomy checklist | disguise / asymmetry categories | none | baseline-only | no licence file | baseline-only | none |
| LitBank coref, BookNLP | `[PUB]` / `[README]` | already integrated (LitBank adapter) | none new | baseline | baseline | LitBank data CC BY 4.0, BookNLP MIT | baseline-only | identical exact-span scoring rows |

### F2 Time, knowledge and state (`register_notes_F2.md`)

| Donor | Tag | Touches | Product value | Paper value | Form | Licence | Decision | Test |
|---|---|---|---|---|---|---|---|---|
| TAC-KBP temporal slot filling | `[PUB]` | `title_holders.tenures`, `FuzzyInterval` | 4-tuple [T1 T2 T3 T4] and gap-aware closed tenures; Q-style scoring | **covers the planned title-holder model directly** (per:title and org:top_employees are its slots) | representation + metric | public task docs | adapt | Tenure score against human tenure labels (none exist yet) |
| TimeChara | `[PUB]` | none | premise only | baseline (RAG-cutoff) | baseline-only | code MIT; data CC-BY-NC; paid GPT-4 judge | baseline-only | none |
| Narrative World Model | `[PUB]` | state policy | idea: write and read cutoffs | overlap on reveal order vs event order | baseline-only | nothing released | baseline-only | none |
| NarraWorld | `[PUB]` | state policy | idea: admissible view before retrieval | overlap on "not disclosed prematurely" aim | baseline-only | code "upon publication" | baseline-only | none |
| E2RAG / ChronoQA | `[PUB]` | none | "never merge" = floor for premature resolution | baseline | baseline-only | data cc-by-nc-sa | baseline-only | none |
| EvolvTrip (arXiv 2506.13641) | `[PUB]` | none | literary-character theory-of-mind temporal graph (in field, not a trip paper) | related work | cite | none found | baseline-only | none |
| Zep / Graphiti | `[PUB]` | none | LLM entity merging and interval-end invalidation conflict with non-negotiables 1, 5, 9 | none | reject as a store | Apache-2.0 | baseline-only | none |

### F3 Leakage and memorisation controls (`register_notes_F3.md`)

| Donor | Tag | Touches | Paper value | Decision | Test |
|---|---|---|---|---|---|
| Jiang & Ferraro (2412.14368) | `[PUB]` | renaming control, gist-prompt arm | **closest prior art for the control**; leakage-as-gap is theirs | adapt (leak audit, gist arm, dose-response); keep renaming as baseline | gist arm on pilot items |
| SynthWorlds (2510.24427) | `[PUB]` | renamer | **leakage = real-minus-synthetic gap is their "knowledge advantage gap"** | adapt (substring-closure renamer) | Re-implement `pi` with closure and pass the existing G1-G3 gate (G1=G2=G3=0) on 335 surfaces |
| SagaScale | `[PUB]` | closed-book stratifier | baseline | baseline-only (filtering deletes the very items the metric needs) | count how many pre-reveal items a closed-book filter would delete |
| Glasserman & Lin; Wu et al. (finance, out of field, method only) | `[PUB]` | analysis rule | **the renaming gap is not pure leakage** (distraction, information loss) | adapt: report gap(real text) minus gap(unseen text) | difference-in-differences on SIO items |
| Gao et al. lookahead probe | `[PUB]` | probability readout | none | adapt only if logprobs exist | positive-control book |
| Speak, Memory (Chang et al.) | `[PUB]` | closed-book positive control | none | adapt | positive control must be clearly above floor |
| LifeState-Bench, WhoDunIt, Yu et al. | `[PUB]` | none | none | reject (cite) | none |

### F4 Reliability (`register_notes_F4.md`)

| Donor | Tag | Decision | Reason |
|---|---|---|---|
| Vovk 2013 (conditional / Mondrian) | `[PUB]` | adapt (engineering only) | per-`alias_type` calibration with minimum-cell fallback; the "Mondrian" name does not appear in the PDFs read |
| Geifman & El-Yaniv 2017 | `[PUB]` (NeurIPS venue from memory) | adapt as a reporting rule | the selective-risk bound is what the gate docstring *claims*; needs i.i.d. labels that do not exist |
| Fannjiang et al. 2022 (PNAS) | `[PUB]` | baseline-only | its fixed P(Y given X) premise fails under the gazetteer feedback loop |
| Murphy & Curran 2007 (ALTA) | `[PUB]` | baseline-only | hard class exclusivity conflicts with transferable titles; the PACLING version INACCESSIBLE |
| Angelopoulos & Bates; Conformal Risk Control; Gibbs & Candes (ACI) | `[PUB]` | baseline-only | ACI repo has no licence; needs a label after every step |

### F5 Visual and audio consistency, product only (`register_notes_F5.md`)

| Donor | Tag | Decision | Reason |
|---|---|---|---|
| Jularr PR #451 (Juloc/Jularr, merged 2026-09-27) | `[PUB]` | adapt (reimplement the idea, no code; repo has no licence) | **dated prior art for a prompt-level spoiler guard**: pre-chapter state plus a second lexical check on the finished prompt |
| StoryDiffusion (Consistent Self-Attention) | `[PUB]` | adapt, conditional | needs a causal batch window; authors tested 24 GB only; 8 GB unproven; Apache-2.0 |
| ViStoryBench (CIDS/CSD) | `[PUB]` | baseline-only | identity-drift regression metric, never evidence of reveal-faithfulness; code Apache-2.0, dataset image rights UNVERIFIED |
| CANVAS, VideoMemory | `[PUB]` | baseline-only | plan from the whole script (not reveal-aware); paid or large models; VideoMemory CC BY-NC-SA |
| Story2Board | `[PUB]` | reject as integration | FLUX.1-dev non-commercial, conflicts with the NoobAI-only rule |
| VinaBench | `[PUB]` | baseline-only | judge needs agreement with a human label set first; data CC BY-NC |
| Gen4AVC poster (Singh et al.) | **INACCESSIBLE** | unknown | OpenReview returns an anti-bot challenge; same group as Narrative World Model; **owner should open it in a browser** |

### F6 Information-flow control for LLM context (`register_notes_F6.md`)

| Donor | Tag | Decision |
|---|---|---|
| FIDES (2505.23643) | `[PUB]` | baseline-only (idea adapted: label every context item, refuse items above the position) |
| Siddiqui et al. (2410.03055), RTBAS (2502.08966) | `[PUB]` | baseline-only (licence UNVERIFIED) |
| CaMeL (2503.18813) | `[PUB]` | reject (idea covered; prompt-injection is out of field) |
| Progent (2504.11703) | `[PUB]` (policy sections skimmed) | reject, out of field |

## 2. What this changes about earlier statements (corrections)

1. **The Mondrian gate is not built.** `gate.py` is a pooled one-sided rule; `docs/HANDOFF.md:884` says Mondrian by `alias_type` is "not started" (verified). `CHIMERA_PLAN.md` section 2 still says it exists, and the gate docstring claims "at most alpha of auto-linked decisions are wrong", which a high quantile of *incorrect* scores does not give: it bounds the false-positive rate, not link precision. FORCE_LINK and BLOCK return before the threshold, so no coverage statement applies to any real link.
2. **The L1 leakage reading must be softened.** Two finance papers show the renamed arm can differ for reasons other than memory (distraction, information loss), and our renamer failed its own commutation gate (T4 v3). So the +9.7 point A-minus-B gap and the three clan-head renamed failures are **not established as leakage**; they may be renaming damage. The report's "directional signal" wording should say this until an unseen-text control (difference-in-differences on SIO items) exists. The closed-book probe also has no positive control.
3. **SynthWorlds has no measured rename-leak audit.** `PRIOR_ART.md` called "Tokyo to Torioka" a rename-leak audit; the source (appendix design rules) gives it as an illustrative example. Leakage-as-gap is SynthWorlds' "knowledge advantage gap". Our novelty in the metric is only the prefix and entitlement framing.
4. **Jiang & Ferraro's human validation is weaker than I wrote**: unpaid volunteers on 100 items (verified in the PDF), with reported maximum changes that vary across tables.
5. **LlmLink is not prefix-like**: its algorithm rewinds the document (maxRewind = 2). `PRIOR_ART.md` lists it as chunked processing.
6. **LitBank data is CC BY 4.0**; the "CC-BY-NC" in `prior_art_notes_B.md` is the proceedings licence.
7. **KoCoNovel**: venue "LREC-COLING 2024" is UNVERIFIED (arXiv `@misc`); its reader view is derived in post-processing for 5 of 50 works and never evaluated.
8. **EvolvTrip** is a literary-character theory-of-mind graph (in field), not a retrieval or trip work. **Zep's "bi-temporal"** means event time vs ingestion time, not reader-disclosure time. ChronoQA's Hugging Face card says 1,028 QA over 18 stories, not the paper's 497 over 9.
9. **New verified defect:** `FuzzyInterval` has four fields and no `last_evidence`; the closed-tenure call in `title_holders.py` passes `last_evidence=`, which Pydantic silently drops (verified by running the constructor). Numbered **B13** here because B10 to B12 already exist in the backlog; not added to that file (no edits to existing files).
10. **The first-tenure-starts-at-chapter-1 rule** (which I described as a by-design backward extension) is a stronger claim than evidence supports and would be penalised by a TAC-KBP-style score.
11. **NoobAI-XL 1.1's README prohibits commercialisation of generated products**, which constrains any product claim.

## 3. Overlaps with the claimed novelty (disclosed, not hidden)

| Claim part | Overlapping work | What remains different |
|---|---|---|
| Renaming as leakage control, leakage as real-minus-renamed gap | Jiang & Ferraro, SynthWorlds (KA gap), Speak Memory | prefix / entitlement framing; an UNDETERMINED reveal-chapter oracle on web serials |
| LLM verifies a link | BookCoref step 2 | the constraint that a cited **in-prefix span must entail** the link, names masked (v1 over-rejected) |
| Reader vs omniscient views | KoCoNovel, LitBank 4.2.5, FantasyCoref 2.2 | chapter-indexed use as a leakage test; translated web serial |
| Disclosure-aware state | Narrative World Model, NarraWorld | measured premature-resolution count |
| Title-holder temporal model | TAC-KBP `per:title`, `org:top_employees` | little; likely Track S |
| Prompt-level spoiler guard | Jularr PR #451 | observer policy, asset lineage, graph state |
| Calibrated abstention | Vovk, Geifman, ACI | only a precision bound per alias type that stays honest under the pipeline's own feedback, with a synthetic test |

No donor measures premature resolution, a prefix cutoff with a renaming control, or a reveal-chapter oracle for aliases (keyword sweeps plus the read sections; figures not inspected; Chinese and Korean venues not searched).

## 4. Track P ranking after M0 (re-ranked on evidence)

1. **Measurement design** (premature-resolution metric with prefix framing). Survives, with required additions the donors expose: a validity gate that passes on hard items (not only 30 plain controls), an unseen-text control, a positive-control closed-book probe, and the gist-prompt arm as an alternative baseline. Difference from donors stated in section 3.
2. **Prefix-entailment gate.** Survives only as a v2 that must be defined against BookCoref step 2; v1 failed (controls 46.7%).
3. **Title-holder temporal model.** TAC-KBP covers it; unless M3 shows an effect beyond the TAC-KBP representation it moves to the system section.
4. **Calibrated abstention: not a defensible contribution as stated.** Narrow candidate only (a precision bound per alias type with windowed re-estimation, falsified on a synthetic stream); optional, not claimed.
5. C5 (failure audit) stays as grounding.

## 5. Track S (product) adoptions, no novelty claimed

1. Prompt-boundary invariant: a `PromptItem(text, ref, learned_at_pos, observer_scope)` builder that refuses items beyond the position and derives `conditioned_on` from what was actually serialised (fixes B3; plus wire in the existing `EpistemicLeakageValidator`, which has no production caller, and make `world/context.py::story_context` use `state_of`).
2. Pass `is_address` through `mentions/runner.py` and measure it (B6); then a title and relational span proposer test (Maverick research-only), then the BookCoref-style verifier switch.
3. Dated wiki canon via `learned_at_pos`; fix the dropped `last_evidence` (B13); a Jularr-style independent guard on the finished image prompt; StoryDiffusion only as a causal-batch config switch after a VRAM proof.
4. Fix B1 to B9 from `CHIMERA_DEFECT_BACKLOG.md` only on a branch the owner authorises at CP-G.

## 6. Read in full vs lead

All rows above are `[PUB]` unless marked. Not read in full: Progent's policy-language sections (skimmed); TAC-KBP 2011 pilot overview; Vovk's book; Murphy-Curran-Scholz PACLING version (INACCESSIBLE); Gen4AVC poster (INACCESSIBLE); TEMPO (2605.18843), TimeSPEC (2602.17234), El Lahib et al. (ACL 2026), PASC (2605.18812), Fellegi-Sunter two-cutoff linkage: `[LEAD]`, abstracts or snippets only, and cannot be adopted.

## 7. Public exposure (information only, no action)

The public branch exposes short gold-text excerpts and review files (mean 74.8 characters, max 145). New IP-relevant material in this step: none created; no novel text is in any file from this step.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/PAPER_SKELETON.md -->
## Source: `docs/research/NOVELTY_REPORT/PAPER_SKELETON.md`

# Paper skeleton v1 and claim-to-evidence matrix (CP-I), 2026-10-15

Status: **skeleton only; no manuscript prose.** Every number is silver, synthetic or system-internal and is tagged as such; no human label exists yet (arrives with the owner's weekend labels). At most three Track P contributions plus a system section. Track P and Track S are kept in separate sections.

## 1. Working title and one-sentence claim

*Reading in order: measuring premature identity resolution in long serials.* We define a **premature-resolution rate** for alias-to-identity linking under a chapter prefix, with a reader-warranted oracle that allows UNDETERMINED, and show on controlled synthetic worlds that it separates resolvers that respect disclosure from those that do not; we also audit a real pipeline against it.

## 2. Track P contributions after the evidence (re-ranked)

| # | Contribution | Survives? | Evidence (provenance) | Closest work and exact difference | Falsifier (stated) |
|---|---|---|---|---|---|
| P1 | **The measurement design**: premature-resolution rate against a reader-warranted oracle with an UNDETERMINED label, reported with reader-view and omniscient-view accuracy (the metric needs both) | **Yes, narrowly.** Construct validity shown on synthetic worlds; real-novel use not yet shown | M3: 160 synthetic worlds, 872 pre-reveal aliases: retroactive system 872/872 premature and 100% omniscient, reader-observer 0/872 premature and 100% reader view, do-nothing floor 49.7%, shipped resolver 0 on both accuracy views (`m3_results.json`, SYNTHETIC) | SynthWorlds' knowledge-advantage gap (real minus renamed) is the leakage definition; Jiang & Ferraro for renaming; KoCoNovel and LitBank 4.2.5 for the two views. Difference: prefix/entitlement framing, a reveal-position oracle and the joint reporting rule | The metric fails to separate the designed systems (it did not fail) |
| P2 | **A pre-registered synthetic suite plus an engine audit showing that rule-based reveal detection does not generalise** | **Yes, as a diagnostic result** | M3 R4: repo `REVEAL_PATTERNS` recall 80/80 on one phrasing, 0/80 on three; patterns written for two phrasings 0/80 on two held-out phrasings (SYNTHETIC) | None found that measures reveal-detector generalisation for serials | Detection recall on real serials is high (unmeasured; needs labels) |
| P3 | **The failure audit (C5)** of an identity-resolution pipeline on a real serial | **Yes, as grounding** | 58/88 silver hard cases never detected; scorer reaches 0.550 vs 0.80 (0 of 880 links scored); 5 of 11,122 links stamped before the reader's binding (5 of 547 briefs); LitBank CoNLL F1 15.95 / 42.44 (human-keyed external) | Audit papers exist for coreference tools (BookCoref evaluates BookNLP); none on a bitemporal story graph | Defects fixed and numbers move (planned via the branch) |
| — | Evidence-gated linking (C1b) | **No** | Gate v1 over-rejected (14/30 vs 29/30); v2 passes only via a surface-identity shortcut (19 of 20 accepted hard items) and a lexical visibility rule explains the primary-item blocks; entailment rejected 9 of 10 uses (SILVER) | BookCoref step 2 overlaps (precision-first LLM verification) | Moves to the system section or a negative-result paragraph |
| — | Leakage under renaming (C1a) | **Not established** | L1: +9.7 points A-minus-B over 62 items, sign test p = 0.031, 6 vs 0 discordant (SILVER, one model); renaming control validated against the deterministic resolver in T4 v5 (99.96% agreement; v3 and v4 failed first) but not for an LLM; unseen-text control L2U run (Luna) and repeated on Qwen (difference-in-differences +6.5 [-3.2, +17.7], inconclusive): synthetic renaming-damage gap +3.2 points [0.0, 8.1], difference-in-differences +6.5 [-1.6, +14.5], inconclusive by the pre-registered rule | J&F, SynthWorlds, finance-domain work show the gap includes renaming damage | The gap equals the gap on unseen synthetic text (run: synthetic gap +3.2 of the real +9.7; difference not distinguishable from 0) |
| — | Title-holder temporal model | **No (system)** | M3b: bitemporal stamp serves both views (SYNTHETIC); TAC-KBP covers tenure intervals | TAC-KBP temporal slot filling | n/a |

**Rating against the novelty gate** (formal task; one novelty sentence; closest work and difference; strongest baseline; falsifier): P1 meets the first four on paper and has a stated falsifier, but its strongest evidence is synthetic and it has **no human-labelled real-novel result**; the strongest baseline for the central question (a renaming-only or gist-prompt control) is defined, not yet run. Verdict today: **a workshop-level measurement-and-audit paper with a pilot, not a main-track method paper.** It becomes stronger if the weekend human labels support P1 on real text and the unseen-text control separates leakage from renaming damage.

## 2b. Track S status (system section, no novelty claimed)

Scope-A adapters are implemented and tested on the local branch `chimera/system-adapters` (B1, B2, B3, B4, B13, A7, A1/A2; see `NOVELTY_REPORT.md` 5.12): honest counters, prefix resolve, causal title option, reader-entitled briefs, honest conditioning, dated wiki canon. Defaults change only for the two counter fixes.

## 3. Proposed sections

1. Introduction: why identity timing matters in serials; the gap (reader view vs final truth) and what exists (KoCoNovel, LitBank, SynthWorlds).
2. Task and metric: the oracle, UNDETERMINED, the three reported numbers, leakage as the renaming gap (credited to SynthWorlds/J&F), power.
3. Synthetic suite (SIO v1, M3, M3b): construction, systems, results, what is by construction and what is not.
4. A real-serial pilot: the 72-item sheet, silver and (when available) human labels, model-versus-human agreement, the closed-book probe and its limits.
5. Pipeline audit (C5) and gate analyses, with the gate-versus-engine diagnosis as a methodological note.
6. System (Track S, separate section): bitemporal graph, reader-observer `state_of`, the integration register adopted/adapted components, defects fixed on the authorised branch.
7. Limitations; ethics and data (no novel text distributed; public-exposure note); related work (from `PRIOR_ART.md` and the register).

## 4. Tables and figures to build (each traced to a file)

| Item | Source | Status |
|---|---|---|
| T1 metric definitions and oracle | `PREREG_M3`, `sio_synthetic_oracle.py` | ready |
| T2 M3 pooled system-by-detector table | `m3_results.json` | ready |
| F1 reader vs omniscient accuracy plane per system | `m3_results.json` | to draw |
| T3 detector recall by template | `m3_results.json` | ready |
| T4 pilot sheet composition and (later) human-label agreement | `pilot_manifest.json`, `human_pilot_analysis.py` | waits for labels |
| T5 L1 and L1b arm results (silver) | `l1_analysis.json`, `l1b_analysis.json` | ready |
| T6 audit table (C5) | `silver_pilot_results.json`, `prompt_invariant_ri.json`, repo files | ready |
| T7 gate diagnosis | `gate_failure_diagnosis.json` | ready |

## 5. What a reviewer would attack, and the prepared answer

1. **"The leakage claim is renaming damage."** True and conceded: the gap is not established as leakage. The unseen-text control (run, $0.0095) found a synthetic renaming-damage gap of +3.2 points and an inconclusive difference-in-differences (+6.5, CI [-1.6, +14.5]); a validated renaming control exists for the deterministic engine (T4 v5). The paper does not claim leakage.
2. **"Silver labels from a model that may share the resolver's memory."** Conceded and disclosed everywhere; the weekend human labels test model-versus-human agreement; M2 on a same-family model does not resolve it, a third-family run would.
3. **"The synthetic results are by construction."** Partly: the sensitivity of the metric is the claim, not any system's merit; the non-by-construction finding is detector brittleness.
4. **"n is tiny on the real novel."** Yes: 4 primary items with repo-derived reveal chapters; up to 23 with human labels; the paper states the smallest detectable effect.
5. **"Renaming and dual labels already exist."** Yes, and they are credited; the contribution is the prefix/entitlement metric and its validity checks.
6. **"The gate result is a shortcut."** Conceded; reported as a negative result with the gate-versus-engine diagnosis.

## 6. Claim-to-evidence matrix

Every sentence that will carry a number in the paper maps to a file and a command in `NOVELTY_REPORT.md` section 10 and `INTEGRATION_REGISTER.md`; no number is used that is not in a results file produced by a logged command.

## 7. Public exposure (information only)

No novel text is in any file created for this skeleton; the standing public-exposure issue stays with the owner.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/PRIOR_ART.md -->
## Source: `docs/research/NOVELTY_REPORT/PRIOR_ART.md`

# Prior art, verified (2026-10-15)

Claim under test: **disclosure-faithful identity resolution under parametric leakage** for long translated web serials. Sources: PDFs downloaded with `curl` and read as extracted text (`pdftotext -layout`), not page summaries. Detailed per-paper notes: `prior_art_notes_A.md` (disclosure-aware memory, leakage, time-aware RAG) and `prior_art_notes_B.md` (datasets, coreference, 19 logged search queries). Two subagents did the reading; **I re-checked in the raw text** the claims marked `RECHECKED` below.

Tags: `[PUB]` read in the paper's own text; `[LEAD]` snippet or abstract only (venue and page details of some papers); `[SUMM]` page read through a summarising fetch tool, not verbatim; `UNVERIFIED`; `INACCESSIBLE`. A statement that a paper "does not cover X" means: I (or the agent) read the named sections and a keyword sweep of the extracted full text found nothing. It is not proof about figures or unread parts.

## 1. What each close paper does, and the exact difference

| Work | What it is | Overlap with the EchoTales claim | Exact difference | Tag |
|---|---|---|---|---|
| **Jiang & Ferraro**, arXiv 2412.14368 v6 (24 Apr 2026) | Name replacement (masking, cross-cultural, same-cultural) as a memorisation intervention on six character-understanding benchmarks, including a character-coreference task; reports up to a 45.2% accuracy drop; human validation that replacement preserves gold | **Renaming as a leakage control is theirs.** Closest prior art for the control in C1a | Replaces main-character names only (Table 7 caption); no chapter-prefix, no disclosure time, no premature-resolution metric | `[PUB]` `RECHECKED` |
| **SynthWorlds**, arXiv 2510.24427, ICLR 2026 | Parallel real-mapped vs synthetic-mapped Wikidata worlds; "knowledge advantage gap"; rename-leak audit (Tokyo to Torioka still leaks) | Methodological source for renaming as a leakage control with a leak audit | Encyclopedic multi-hop QA, not fiction; no disclosure or alias task | `[PUB]` |
| **TimeChara**, arXiv 2405.18027 (Findings of ACL 2024, venue from snippet) | Point-in-time character hallucination in role-play; RAG-cutoff baseline; all baselines at or below 51% on future-type questions | Best premise: LLMs hold the books in parametric memory (Sec. 3: "store knowledge of these series well in their parametric memories") and the context-cutoff baseline does not stop leakage | Role-play event knowledge, not alias-to-identity linking; leakage is exploited, not controlled | `[PUB]` `RECHECKED` (quote); venue `[LEAD]` |
| **NarraWorld** ("Shared Worlds, Private Minds"), arXiv 2609.32401 (26 Sep 2026, no venue) | Structured memory for long-form writing; validity-interval store; alias-linking stage | Sec. 2.4: "the culprit's identity should not be disclosed prematurely"; App. A.1 alias linking in a validity-interval store, architecturally near EchoTales | Premature disclosure is a design aim, never measured; alias linking not evaluated or gated on reveal time; no leakage control; task is writing quality | `[PUB]` `RECHECKED` |
| **Narrative World Model**, arXiv 2607.05577 (PocketFM, 6 Jul 2026, under review) | Typed temporal-state memory, chapter-safe evidence, reveal order vs event order as a first-class axis | Disclosure time vs story time and chapter cutoff are modelled | No alias or identity task; no leakage control; scores QA accuracy of memory | `[PUB]` |
| **E2RAG / ChronoQA**, arXiv 2506.05939 (EACL 2026 from snippet) | Entity-event graph RAG, 497 QA pairs over 9 Gutenberg stories | "Revealed later" motivating example | Opposite design: "we never merge mentions" (Hermione, Miss Granger kept apart); no resolution evaluation, no leakage control | `[PUB]` `RECHECKED` |
| **NstAgent**, arXiv 2609.35759 | Story generation with narrative-state tracking | None substantive | Generation-side consistency only | `[PUB]` |
| **KoCoNovel**, arXiv 2404.01140 (LREC-COLING 2024) | 50 modern Korean novels (Wikisource, public domain), 178K tokens, three annotators (MUC IAA 94.53) | **Reader-view and omniscient-view coreference annotations already exist.** The views differ in only 5 of 50 works (App. C, Table 12) | Models tested on the omniscient version only; no LLM, no leakage control, no chapter-indexed disclosure; Korean, not translated, not web serials | `[PUB]` `RECHECKED` |
| **LitBank coreference** (Bamman et al., LREC 2020) | 100 English works | Sec. 4.2.5 "Revelation of identity" | Annotates "the perspective of the textual reality, rather than from the reader's state of knowledge at the moment of encountering the mention": omniscient only | `[PUB]` `RECHECKED` |
| **FantasyCoref** (Han et al., CRAC 2021) | 211 Grimm tales + 3 fantasy works | Disguise and plot-twist cases discussed | "we follow the omniscient writer's point of view"; no leakage control | `[PUB]` |
| **GenWebNovel** (Zhao et al., COLING 2025) | Nested NER for Chinese web novels: 400 chapters, 1,214,283 tokens, PER/LOC/ORG | Web-novel annotation resource | NER only, coreference is "future" work (p. 3843); **each of 40 novels contributes only its first 10 chapters**, so later reveals are structurally absent; original Chinese; text not redistributable (DUA); not used here | `[PUB]` `RECHECKED`; repo terms `[SUMM]`/DUA read |
| **Song & Liu 2024** (LREC-COLING) | Character resolution (zero and non-zero anaphora) in one Chinese print novel | Hidden identity listed as an open challenge | One qualitative sentence in Sec. 5.2 ("Fifthly, character-resolution for plots about hidden identity ... can hardly demonstrate good performance without manual assistance"); no metric, no LLM, no leakage setup | `[PUB]` `RECHECKED` |
| **BookCoref** (ACL 2025) | Book-scale coreference, silver 50 books / gold 3; BookNLP CoNLL-F1 42.2 on gold | Evaluates BookNLP on whole books | Whole-book omniscient labels; canonical Gutenberg books; admits web availability (Sec. 7), does not control it | `[PUB]` |
| **SagaScale** (arXiv 2601.09723) | Long-context QA on 103 novels (77 EN, 26 ZH) | Contamination control by closed-book filtering | QA not resolution; filters items rather than renaming; no prefix | `[PUB]` |
| **LlmLink**, **Maverick**, **IdentifyMe**, **TLDM**, **WhoDunIt**, **Speak, Memory** | Chunked LLM coref; SOTA encoder coref; MCQ mention resolution; state at "windows of interest"; name swaps on mystery novels; name cloze | Each touches one ingredient (prefix windows, renaming, memorisation probe) | None combines prefix context + renaming control + reader/omniscient labels for aliases | `[PUB]` abstract/method skims plus grep |
| **TAC-KBP temporal slot filling** (KBP2013 overview) | Validity-interval 4-tuples for relations, scored 1/(1+abs(ti-gi)) in years; ran 2011, 2013 | Overlaps only the "when was this true" half of a bitemporal state | No disclosure time, no identity merge, no leakage | `[PUB]` |
| **BookNLP** | Character clustering, coreference, speaker attribution | Baseline family | README wording read via summariser; no reader-view or leakage notion found | `[SUMM]` |

## 2. Search negatives (auditable)

Nothing found that (a) evaluates BookNLP or a modern coreference system on translated web novels, or (b) measures spoiler or future-knowledge leakage in character resolution with a prefix-of-book setup. 19 queries are listed in `prior_art_notes_B.md`. **Bounds:** the engine is US-only; CNKI, KCI, Naver Academic and Baidu Scholar were not searched directly (INACCESSIBLE); the Chinese and Korean queries returned nothing relevant. Absence of evidence in this search is not evidence of absence in those venues.

## 3. Corrections to earlier statements

- **KoCoNovel** is 50 modern Korean *novels*, not "50 short stories" as in the plan; reader and omniscient views differ in only 5 works.
- **Renaming as a leakage control is established** (Jiang & Ferraro, SynthWorlds, WhoDunIt, Speak Memory). The contribution cannot be renaming. Jiang & Ferraro v6 also covers a character-coreference task.
- **"Reader-view versus omniscient-view labels" is not new in itself** (KoCoNovel). What remains is use as a chapter-indexed disclosure test for LLM leakage on translated serials, and that is a design, not a result here.
- **"The combination of components is new"** (an earlier claim) is not repeated: NarraWorld (premature-disclosure aim, alias stage) and Narrative World Model (reveal order, chapter-safe cutoff) overlap on disclosure-aware state, TAC-KBP on valid-time tracking.
- GenWebNovel's "400 chapters" is 40 novels times a 10-chapter prefix, not 400 chapters of full novels.

## 4. What remains open after this review

No paper found defines (1) a *premature-resolution rate* for alias-to-identity linking under a chapter prefix, (2) leakage as the change of that rate under consistent renaming, (3) an evidence-gated linking rule that must cite prefix spans entailing the link, or (4) reader/omniscient labels on translated web-serial text with chapter-indexed reveals. Each ingredient has precedent. Whether the assembly is useful is **untested** in this work.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/PRIOR_ART_E0.md -->
## Source: `docs/research/NOVELTY_REPORT/PRIOR_ART_E0.md`

# E0 prior-art check for the confirmatory study (2026-10-16)

Scope (from the goal): (a) name anonymisation or pseudonymisation used to reduce memorisation or contamination in LLM evaluation; (b) spoiler or premature-reveal leakage by LLMs in narrative tasks. Method: web searches (US-only engine, standard mode, 9 queries), then the PDFs of the closest papers downloaded to `data/raw/papers/` (git-ignored) and **read directly by me**; sections read are given per row. Tags: `[PUB]` I read the paper's own pages; `[SUMM]` a fetch tool summarised the page, so treat as a lead; `[LEAD]` seen in a search snippet only; `INACCESSIBLE` the source refused automated access (403/525); I did not work around it. A "does not do X" claim is made only for the sections named.

## 1. Closest papers and what they already do

| Paper | Tag, pages read | What it does (own sections) | What it does not do (for those sections) |
|---|---|---|---|
| Jiang & Ferraro, arXiv 2412.14368 v6 (24 Apr 2026), "Beyond Math: Stories as a Testbed for Memorization-Constrained Reasoning in LLMs" | `[PUB]` pp. 1-7 (abstract, 1-5, start of 6) | Two-tier framework; **name replacement is the core of the Restrictive Setting**: masking (P0, P1), **cross-cultural replacement keeping gender**, same-cultural replacement (5.1); human validation of 100 items (App. G); CharScript source-identification as a memorisation probe (3.2, 5.1); GPT-4o, Llama-3.3-70B, DeepSeek-V3, 3 runs each (3.3); up to 45.2% accuracy drop (abstract); gist and verbatim prompts as prompt-level memorisation steering (4.2) | No chapter prefix, no reveal time, no alias-to-identity task, no oracle derived from a reveal sentence; names renamed for main characters only (Table 7 caption per fetch summary `[SUMM]`); no decomposition of the drop into memory versus lost name cues; no mitigation framed for deployment |
| Chang, Cramer, Soni, Bamman, arXiv 2305.00118 (EMNLP 2023), "Speak, Memory" | `[PUB]` pp. 1-6 | Name cloze probe of 571 works; GPT-4 and ChatGPT memorise a wide set of books; **memorisation correlates with web duplication** (Table 3: Spearman 0.74 for pre-1928 books against Google hit counts); memorised books do better on downstream tasks (year, narrative time, character-name generation); names from memorised books bleed into other contexts (6.1) | No renaming control on a downstream task, no prefix or reveal setting; the fame dose-response is for name cloze accuracy, not for premature disclosure |
| "On the Impact of Anonymization on the Performance of LLMs", arXiv 2609.11335 v2 (Sep 2026) | `[PUB]` pp. 3-6 (3.1-4.1) | **Pseudonymisation pipeline with category-plus-unique-ID placeholders (`<LOC>-1`), model run on anonymised prompts, then placeholders mapped back to the originals before scoring** (3.1 steps 2-5, 3.4.1); eleven benchmarks, five models (7B to 72B), plus generalisation, masking, randomisation and redaction on GPT-4o-mini (3.4.2); explicit "this prompt is anonymized" prefixes tested (3.4.3); utility loss largest for retrieval-style tasks (RGB), pseudonymisation best | Framed as privacy-utility trade-off, not as a memorisation or leakage control: no test that anonymisation removes memorised knowledge, no narrative task, no reveal oracle (4.1 reports memorisation only as an untested hypothesis for TruthfulQA); NER recall about 91% limits it (3.4.1) |
| TimeChara, Ahn et al., ACL Findings 2024 (arXiv 2405.18027) | `[PUB]` pp. 1-5 | Point-in-time role-play hallucination; **spoiler avoidance is a stated motivation** (1); "unawareness of the future" instances over 4 series (3.1); LLM-judge with spatiotemporal labels (3.3); Narrative-Experts decomposition as a mitigation | Leakage is defined as contradiction with the timeline, not attributed to memory; no renaming or anonymisation control; no alias-reveal item |
| Fu et al., arXiv 2603.09981 (Feb 2026), "Reading or Remembering" | `[PUB]` pp. 1-5 | 25 well-known books; summaries from internal knowledge versus the full text, judged by LLMs (3.1-3.5); full text usually better but internal can win for some books | No reader-position cutoff, no spoiler measure, no renaming |
| Ma et al., arXiv 2608.08160 (Aug 2026), long-horizon consistency in interactive narratives | `[SUMM]` (HTML summarised, 100,000 of 136,982 characters) | **"Premature information disclosure"** defined as a failure (5.3: the narrator discloses plot-critical information before the story supplies it); 100 movie synopses; six narrator models | No separate metric in the sections read, no memory or renaming test, "future-sight isolation" concerns in-story knowledge (3.2) |
| RAT-Bench, arXiv 2602.12806 | `[SUMM]` | Text anonymisation benchmark for privacy; NER, perturbation and LLM-based anonymisers | Pseudonymisation not evaluated; memorisation only as motivation; no mapping back |
| Others seen in snippets only | `[LEAD]` | LiveFact (entity-swap contamination test, 2604.04815); Named Entity Swapping (2505.21128); Wang et al. 2023 and Luo et al. 2026 (cited by the external reviewer; **not located**, treat as unverified) | not read |

Spoiler-side search (3 queries): spoiler detection in reviews (Nishi and Suzuki 2025; Tran et al. 2023) and clickbait spoilers are different tasks `[LEAD]`. **I found no benchmark that truncates a book at a reader position, asks for recaps or character profiles, and measures disclosure of later identity**, and none that ties spoiler leakage to parametric memory by renaming. The search is bounded (US-only engine; nine queries; the 2026 arXiv corpus is large), so this is "not found", not "does not exist".

## 2. What this changes for the planned study

1. **The mitigation (E4) is not a contribution.** Consistent pseudonymisation with back-mapping of the answer is an existing pipeline (2609.11335, 3.1) and name replacement with gender-preserving cross-cultural names is an existing evaluation device (2412.14368, 5.1). In this study both are **baselines and instruments**, and plain "use only the passage" prompting is the prompt baseline (compare their gist prompt, 4.2). What can still be claimed, if the pre-registered result holds: the first measurement of such a mitigation on **premature identity disclosure** with a text-derived reveal oracle, together with its **utility cost on post-reveal answers**. That is an evaluation result, not a new method.
2. **The cue-preserving arm B3 is not novel as a device** (Jiang & Ferraro have gender-preserving replacement). The novel part is using it to **decompose** the original-versus-renamed gap into name-keyed memory and lost name cues (the recovered fraction), in a reveal setting.
3. **The fame dose-response direction is expected** (Chang et al. Table 3 already ties memorisation to web frequency). The new part is measuring it on premature disclosure, with an objective fame variable fixed in advance.
4. **E5 (recap spoilers) has no direct precedent found**; closest are TimeChara (role-play, timeline contradiction) and the premature-disclosure failure category of Ma et al. (no memory test). It is the strongest candidate for a distinct contribution, and the one a reviewer is most likely to challenge on novelty if a paper I did not find exists.
5. **Renaming as a memorisation control is established** (Jiang & Ferraro, plus the entity-swap contamination tests). The paper's claim must be about the reveal-time setting, the decomposition, the fame dose-response, the harm task and the mitigation's utility trade-off, not about renaming itself.

## 3. Remaining gaps in this check (not closed)

Wang et al. 2023 and Luo et al. 2026 not located; Chinese and Korean venues not searched; the premature-disclosure paper's appendix F.2 not read; a systematic search of ACL Anthology for "spoiler" in narrative LLM work not done; all dates are as shown in PDF metadata.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/PRIOR_ART_UPDATE_2026-10-16.md -->
## Source: `docs/research/NOVELTY_REPORT/PRIOR_ART_UPDATE_2026-10-16.md`

# Prior-art update, 2026-10-16 (owner message at about 17:58 IST) and the re-ranked contribution claims

Tags: **[VERIFIED-ABS]** = the arXiv abstract page was fetched and read on 2026-10-16 (not the full text); **[LEAD]** = the owner's summary, not verified by me; **[READ]** = read in the earlier notes (`PRIOR_ART.md`, `PRIOR_ART_E0.md`). Nothing below was read in full today.

| Work | What the owner's note says | What I verified | Consequence for our claims |
|---|---|---|---|
| Chang, Cramer, Soni, Bamman 2023, "Speak, Memory" (EMNLP) | memorisation tracks web frequency; downstream accuracy higher on memorised books | [READ] in `PRIOR_ART_E0.md` (Spearman 0.74 for pre-1928 books against web hits, Table 3) | our fame dose-response is a **confirmation**, not a contribution |
| Jiang and Ferraro, arXiv 2412.14368 | "v5", name replacement exposes memorisation; proposes a cue-preserving mitigation | [VERIFIED-ABS] the current page is **v6** (24 Apr 2026; v1 18 Dec 2024); the abstract says "We introduce a simple yet effective method to mitigate mechanized memorization in character understanding evaluations" and says it keeps the implicit cues needed for comprehension | our pseudonym test (B3) and the E4 mitigation are **replications and baselines** of theirs, not new methods |
| WhoDunIt, arXiv 2502.07747 | name swaps on Gutenberg mysteries, full-story only; closest prior work | [VERIFIED-ABS] Kshitij Gupta, 11 Feb 2025, "WHODUNIT: Evaluation benchmark for culprit detection in mystery stories"; tests original names, name swaps and substitutions with well-known real or fictional entities on GPT-4o, GPT-4-turbo, GPT-4o-mini; accuracy drops under some substitutions, "particularly those with wide recognition". The abstract does **not** say Gutenberg, truncation or memorisation | Gutenberg source and "full-story only" stay **[LEAD]** until the full text is read; our stated difference is pre-reveal truncation with an entitlement oracle |
| DatedGPT, arXiv 2603.11838 | look-ahead-bias literature; parent concept | [VERIFIED-ABS] Yan, Tang, Gao, Jiang, Lu, 12 Mar 2026 (v2 23 Jul 2026), "Preventing Lookahead Bias in Large Language Models with Time-Aware Pretraining": twelve 1.3B models with annual data cutoffs, financial forecasting; the abstract does not use "point-in-time correctness" (that framing is an interpretation) | cite as the **parent concept** (look-ahead bias); reader-faithfulness is the reader-position analogue |
| SurrealDB "Spectron" spoiler-safe narrative memory | product precedent for story-time stamping | [LEAD] not fetched | our difference: **derived** attributes, not stamped events |

## Re-ranked claimed contributions (owner, 17:58 IST)
1. **Premature-resolution construct under prefix truncation**, with a text-derived oracle (entitlement, not truth of the full story).
2. **Renaming validity checks are themselves memory-assisted** (plain controls on famous books are easier with original names; the memory-free gate).
3. **Derived-attribute horizon leakage and its repair** (Channel 2, the prefix-faithfulness session's results).
4. **OLMo training-data link, if it works** (exploratory, addendum 3).
5. **E5 recap harm** (spoiler rate in a realistic reader task).
Not claimed as contributions: the fame dose-response (confirms Chang et al.), the pseudonym test and the E4 mitigation (replications and baselines of Jiang and Ferraro).

---

<!-- merged-from: docs/research/NOVELTY_REPORT/SIO_IMPLEMENTATION_NOTES.md -->
## Source: `docs/research/NOVELTY_REPORT/SIO_IMPLEMENTATION_NOTES.md`

# SIO implementation notes and results (synthetic; not real-novel evidence)

Pre-registration: `docs/research/preregistrations/PREREG_SIO_synthetic_identity_oracle.md` v1, sha256 `df93ef3a4f219c9225641632558dc622606b0acd5d6d4b20801dfa7ad0a5a121`, re-hashed before the run and equal to `MANIFEST.json` `[REPO]`. Frozen files were not edited.

Runner: `scripts/chimera/sio_synthetic_oracle.py` (sha256 `3b87daa9...`). Results: `data/eval/chimera/sio_results.json` (sha256 `dd7534ae...`). Tests: `packages/pipeline/tests/test_sio_generator.py` (5 passed). Command: `python scripts/chimera/sio_synthetic_oracle.py --out data/eval/chimera/sio_results.json` (8 s, CPU, no LLM, no network, no key). Seeds 0..39, no selection, one run of record. A 2-world debug smoke was run first to the scratchpad only, to catch bugs; it was not used for any number.

Label provenance: every label here is **by construction from the world spec** (synthetic). No model labelled anything. No novel text is used.

## Interpretations I made where the frozen prereg is ambiguous (not edits to it)

1. "Retroactive half" of the title worlds = even seeds: the bare title is mentioned in ch1-2 before the holder is named (named + declared in ch3-4). Odd seeds: holder declared first, then mentioned. Chapter-level, not sentence-level.
2. The resolver's co-presence is chapter-wide (`runner.py:902`, `reference_mode.is_physically_present`). So every alias chapter holds exactly one PRESENT named mention (Z). Holder-introduction mentions inside alias chapters carry `NARRATOR_REFERENCE`. This is a deviation from "reference mode PRESENT" for those mentions only.
3. Layout: reveal 0 has a=3, r in 5..7 (distance 2..4 by seed%3); reveal 1 has a=9, r in 11..12 (distance 2..3). Title declarations: H1 ch1-2 (odd seeds) or ch3-4 (even), H2 ch5-6; M1 cuts include 4 and 5 as specified.
4. M1 compares the canonical label of the target (or None) per mention between F and each prefix P_c, pooled over (mention, cut) pairs; the pooled count is not independent, so a world-level count is also reported.

## Known generator flaw (found after the run; results not re-tuned)

The H2-tenure title mention is in ch8. When reveal 0 has distance 4 (seed%3==2, 13 of 40 worlds) ch8 is a post-reveal chapter with a sole PRESENT named mention, so the sole-co-present rule links the title to that person. Exploratory row `title_in_H2_tenure_linked_to_H2_F` (27/40) is therefore confounded and must not be read as a title-holder failure. Pre-registered M1-M4 do not use ch8 mentions. Verified by inspecting seeds 2 and 5 (method `RELATIONAL_COPRESENCE`).

## Results (Wilson 95%)

| Metric | k/n | rate | 95% CI |
|---|---|---|---|
| M1 prefix-invariance violations, pooled (mention, cut) pairs | 0/3741 | 0.000 | [0.000, 0.001] |
| M1 worlds with any violation | 0/40 | 0.000 | [0.000, 0.088] |
| M2 premature resolution to Y, full run F | 0/218 | 0.000 | [0.000, 0.017] |
| M2 premature resolution to Y, prefix run before reveal | 0/218 | 0.000 | [0.000, 0.017] |
| M2 by distance 2 / 3 / 4 (F) | 0/70, 0/96, 0/52 | 0 | upper 0.052 / 0.038 / 0.069 |
| M3 post-reveal alias NOT linked to Y (F) | 221/221 | 1.000 | [0.983, 1.000] |
| M4 retroactive title link (title precedes naming, F) | 40/40 | 1.000 | [0.912, 1.000] |
| control: title after naming linked to holder (F) | 40/40 | 1.000 | [0.912, 1.000] |

Exploratory, not pre-registered:

| Quantity | k/n |
|---|---|
| pre-reveal alias linked to ANY entity (F and prefix) | 218/218 |
| pre-reveal alias linked to the co-present Z, a different person than Y (F) | 218/218 |
| post-reveal alias linked to any entity (F) | 221/221 (all to Z, none to Y by M3) |
| plain PRESENT named controls resolved to their own label (F) | 702/702 |
| title LINK events whose `cause_pos` chapter is earlier than the holder binding's `learned_at_pos` | 40/107 |
| frozen reveal sentence matches the repo's `REVEAL_PATTERNS` | 0/80 |
| repo stock phrases ("This was none other than X.") match `REVEAL_PATTERNS` (regex only, 2 hand-written strings) | 2/2 |

## What this shows and does not show

- Pre-registered decision rule: M1 = 0 and M2(F) = 0, so "the resolver's `mention.target_id` is prefix-causal on these structures" holds. M4 > 0 in the retroactive half as pre-declared. M4 is the by-design backward extension documented in `title_holders.py` (first holder's tenure is extended to chapter 1).
- **The M2 = 0 is vacuous as evidence of disclosure-faithfulness.** The resolver never uses the reveal sentence at all (M3 = 100%): it links every alias, before and after the reveal, to the sole co-present character, who is the wrong person under both the reader view and the omniscient view (218/218 and 221/221). That is a different failure: over-commitment on a deictic alias. Its size depends on this generator's design of exactly one co-present name per alias chapter, and does not transfer to real text.
- Reveals are not meant to rewrite `mention.target_id`: `detect_reveals` logs reader-observer events separately `[INSPECT]`. This test therefore does not test the reveal pipeline end to end, only the mention layer.
- `state_of` gates on `binding.learned_at_pos` and does not reference events or `cause_pos` `[INSPECT: grep of packages/core/src/echotales/core/state.py]`. So the early event stamp (40/107) is a log inconsistency, not shown to leak through `state_of`. Other consumers of `mention.target_id` were not traced: UNVERIFIED.
- **No comparison of "plain resolver vs whole-input renaming vs evidence-gated linking" was possible.** The deterministic resolver has no parametric memory, so renaming and gating cannot change its output, and T4 closed with the renaming control unvalidated. C1b (gating) and C1a (leakage under renaming) are therefore **untested** by SIO. They need an LLM resolver; none was run.
- Power: cannot detect violation rates below about 0.1% pooled or 9% by world.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/SPEND_LEDGER.md -->
## Source: `docs/research/NOVELTY_REPORT/SPEND_LEDGER.md`

# Spend ledger (CHIMERA programme)

Rules (plan sections 7 and 18): nothing is spent without the owner approving an exact verified estimate; the API key is never displayed, printed or copied; owner cap for the OpenAI model is about $0.10 to $0.20 per request; GPU budget is $10 in total and nothing is rented without a separate approved request. Free local inference needs the owner to confirm model tag and hardware.

| Date | Purpose | Model id | Calls | Input tokens | Output tokens | Actual cost (USD) | Approved cap | Running total (USD) | Source |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-15 | L1: LLM leakage and evidence-gated linking, 72-item pilot, silver labels | `gpt-5.6-luna` | 281 (A 70, B 70, C 30, D1 70, D2 41) | 110,905 | 3,800 | 0.0267 | 0.10 | **0.0267** | `data/eval/chimera/l1_results.json` (`log`); cost recomputed 2026-10-15 from token counts at $0.20 / $1.20 per 1M tokens = $0.0267, matches the file's `spent_usd` |
| 2026-10-15 | M1 / L1b: evidence gate v2, 70 items, silver labels | `gpt-5.6-luna` | 80 (D1 70, entailment 10) | 38,082 | 2,701 | 0.0109 | 0.05 | **0.0376** | `data/eval/chimera/l1b_results.json` (`log`); recomputed from token counts at $0.20 / $1.20 per 1M tokens |
| 2026-10-15 | L2U: unseen-text control, 62 synthetic items x arms A and B | `gpt-5.6-luna` | 124 | 43,321 | 656 | 0.0095 | 0.04 | **0.0471** | `data/eval/chimera/l2u_results.json` (`log`); recomputed from token counts at $0.20 / $1.20 per 1M; owner cumulative cap $0.10 |
| 2026-10-16 | PD: public-domain reveal benchmark, 72 real items x arms A and B + 7 closed-book events x 2 + 62 synthetic x 2 | `gpt-5.6-luna` | 282 | 117,136 | 1,636 | 0.0254 | 0.04 | **0.0725** | `data/eval/chimera/pd/run_gpt-5.6-luna.json` (`spent_usd` 0.02539); recomputed from token counts at $0.20 / $1.20 per 1M; owner cumulative cap $0.10 |
| 2026-10-16 | PD v2: all frozen v2 items, arms A, B, B2 + closed book x3 + 62 synthetic x2 | `gpt-5.6-luna` | 1132 | 539,820 | 11,015 | 0.1212 | 0.15 (owner: run if below 0.15; exact estimate 0.1195 expected, 0.1986 theoretical worst case) | **0.1937** | `data/eval/chimera/pd_v2/run_gpt-5.6-luna.json` (`spent_usd`); the owner raised the cumulative cap for this run only |
| 2026-10-16 | PD v3: frozen v3 items (12 fresh books), arms A, B, B2 + closed book x3 + 62 synthetic x2 | `gpt-5.6-luna` | 808 | 375,420 | 7,940 | 0.0846 | 0.14 guard (owner approved the exact estimate $0.0836 expected / $0.139 worst case) | **0.2783** | `data/eval/chimera/pd_v3/run_gpt-5.6-luna.json` (`spent_usd`) |
| 2026-10-16 | PD v4: title-assisted memory probe M2, 31 events x 3 arms | `gpt-5.6-luna` | 93 | 14,924 | 964 | 0.0041 | 0.01 guard (owner approved the exact estimate $0.0038 expected / $0.0074 worst case) | **0.2824** | `data/eval/chimera/pd_v4/run_gpt-5.6-luna.json` (`spent_usd`) |
| 2026-10-16 | PD v7: Luna run **interrupted by the owner's instruction "dont continue with open ai"** (started 14:16:05, process killed about 14:21; no results file written; calls not counted by the harness) | `gpt-5.6-luna` | about 200 to 300 (estimate from elapsed time at roughly 1 call per second; actual UNKNOWN) | unknown | unknown | **about 0.02 to 0.03 estimated; upper bound 0.10 (the run's hard guard); actual spend must be read from the provider dashboard** | 0.10 guard (owner-approved) | **about 0.42 to 0.43 (upper bound 0.50)** | none; partial calls discarded |
| 2026-10-16 | PD label audit: Luna reads each reveal passage (31 events) | `gpt-5.6-luna` | 31 | 5,579 | 279 | 0.0015 | extra budget $0.20 granted by owner for unattended work (2026-10-16); guard 0.01 | **0.2839** | `data/eval/chimera/pd_label_audit.json` |
| 2026-10-16 | PD v5: cue-preserving arm B3, 533 items | `gpt-5.6-luna` | 533 | 260,823 | 5,286 | 0.0585 | guard 0.10 (owner extra budget $0.20, unattended) | **0.3424** | `data/eval/chimera/pd_v5/run_gpt-5.6-luna.json` |
| 2026-10-16 | PD v6: 7 fresh books, arms A/B/B2/B3 + closed book + M2 | `gpt-5.6-luna` | 538 | 251,709 | 5,387 | 0.0568 | guard 0.095 (owner extra budget, unattended) | **0.3992** | `data/eval/chimera/pd_v6/run_gpt-5.6-luna.json` |

Prices used: $0.20 per 1M input and $1.20 per 1M output tokens (Standard, short context), from OpenAI's pricing and model pages read through a summarising fetch tool on 2026-10-15 (tag `[SUMM]`, not verbatim).

GPU spend so far: $0 of the $10 budget. Nothing rented.

Requests, status as of CP-H:

| Request | Model | Calls | Expected cost | Worst case | Notes |
|---|---|---|---|---|---|
| M2 replication of arms A and B on Claude Haiku 5.5 via Claude Code subagents | `haiku` alias (snapshot UNVERIFIED) | 124 spawns | $0 API (subscription quota; measured from completion notices) | $0 API | owner approved the Haiku route, then ("approved for all") the plan was to prefer the free local Qwen run; the Haiku run was NOT run (about 50,800 tokens per spawn, about 6.3M for 124); same family as the silver labeller, so the shared-memory confound is NOT resolved; a third-family run (local Qwen) is still planned |

Remaining under the owner's cumulative $0.10 cap after L2U: $0.0529; **after PD: $0.0275** (running total $0.0725). Further paid runs need a new exact estimate and approval.

After PD v2 on Luna: running total **0.1937** USD, above the original $0.10 cap by the owner's explicit approval of this run ("run luna, if it is below 0.15 then run it"). Any further paid run needs a new exact estimate and approval.

After PD v3 on Luna: running total **0.2783** USD (owner-approved exact estimates for both Luna runs above the original $0.10 cap). Any further paid run needs a new exact estimate and approval.

After PD v4 M2 on Luna: running total **0.2824** USD (owner-approved exact estimates). Any further paid run needs a new exact estimate and approval.

Owner granted an extra $0.20 (beyond the $0.2824 spent) for unattended work on 2026-10-16 with no further approvals; hard ceiling therefore $0.4824. After the label audit: running total **0.2839** USD.

After the unattended window runs: running total **0.3992** USD against a ceiling of $0.4824 (original caps plus the owner's extra $0.20); remaining headroom 0.0832. Any further paid run needs a new exact estimate and approval unless the owner grants more.

Owner instruction 2026-10-16 (late): no further OpenAI use; the confirmatory study runs on open-weight models on RunPod plus Claude Sonnet 5.5 through the owner's Claude subscription. The PD v7 Luna run was interrupted as described above and its results do not exist; PD v7 is reported with the five local models only (exploratory).

## RunPod (owner-created pod, one L40S 48 GB, USD 1.13 per hour all-in: GPU 1.09 + disks 0.04) and Claude subscription

Owner instruction 2026-10-16 (goal text): "hard ceiling of 10 USD total GPU (RunPod) plus the Claude subscription. No OpenAI calls. Log every spend". Earlier the owner set USD 15 in total for RunPod; the tighter 10 USD ceiling governs from the goal text. Stop rule: no new run starts if the projected total exceeds 9.50.

| When (IST) | What | Basis | Estimated USD | Running total |
|---|---|---|---|---|
| 2026-10-16 to 17:45 | pod up 7,349 s (read from `ps -o etimes -p 1` on the pod at about 17:38 IST): exploratory vLLM runs of qwen32b, olmo32b, mistral24 on PD v2/v3/v6/v7, model downloads and swaps | 7,349 s x 1.13 / 3600 | 2.31 | 2.31 |
| 2026-10-16 17:45 to 19:11 | confirmatory run: E1 (3 models x 2,220 calls), E4, E5, E5 judges, E2 stories E1, OLMo corpus check, model swaps; Claude arm on subscription quota (stopped at 211 of 1,218 answers) | 86 min x 1.13 / 3600 per second of uptime = 5,160 s x 1.13 / 3600 | 1.62 | 3.93 |
| 2026-10-16 19:11 to 22:00 (estimate) | pod idle until the owner stopped it (about 19:30), stopped-disk billing, restart at about 20:55 for RF-E2E addendum 8 (qwen32b and mistral24 cards and fix, olmo32b second judge), idle to about 22:00 | about 0.3 h + 1.1 h running x 1.13, plus about 1.4 h stopped x 0.069 | about 1.7 | about 5.6 |

The figure is an **estimate from pod uptime**, not the RunPod billing page; the owner should compare it with the console balance. Claude subscription calls (E2 stories, Claude E1 arm) use quota, not dollars; they are not priced here.

No new run starts after the 20:45 freeze. If the pod stays up until 21:25 the running total reaches about 6.3 USD; the pod bills until the owner terminates it (about 0.069 USD per hour if only stopped), so the owner should terminate it after reading this and compare the total with the RunPod console. Under the 10 USD ceiling and the 9.50 stop rule at every point.

RF-E2E small-model runs and the qwen3:8b judge ran on the local GPU at no cost. The owner should stop or terminate the pod now and compare the running total (about 5.6 USD, an estimate from uptime) with the RunPod console.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/SYSTEM_WORK_PLAN.md -->
## Source: `docs/research/NOVELTY_REPORT/SYSTEM_WORK_PLAN.md`

# System work plan (CP-G), 2026-10-15

Track S (product) only, plus the Track P pieces that need code. **Nothing here has been done.** No existing file has been touched; code changes beyond new files wait for your authorisation of a branch (section 1). Merging a component is engineering and is never claimed as paper novelty. Defect numbers refer to `CHIMERA_DEFECT_BACKLOG.md` (B1 to B12, A1 to A14) plus **B13**, a new defect found in M0: `FuzzyInterval` has no `last_evidence` field, so the argument passed in the closed-tenure call in `resolve/title_holders.py` is silently dropped (verified by running the constructor).

## 1. What I need from you

- **Authorise one local branch**, for example `chimera/system-adapters`, created from the current HEAD (`6c7e2c2`). Not pushed, no commits unless you say so (the standing "no commits" rule stays). Today's branch is the public `validation/evidence-pass-2026-09-24`; I recommend not editing on it.
- **Choose a scope** (section 4): A (recommended), B or C.
- Decide whether a changed default may alter existing numbers (several fixes change how earlier results read; each is flagged below).

## 2. What can be done with NEW FILES ONLY, no branch needed

| Item | New file | Track | Notes |
|---|---|---|---|
| M3a reveal-aware synthetic resolver wrapper | `scripts/chimera/reveal_aware_resolver.py` | P | Wraps `resolve_novel` output with a reader-observer reveal pass on the SIO worlds, so the SIO result stops being vacuous; no repo file edited |
| M3b title-holder temporal model (holder, title, organisation, story time) with TAC-KBP 4-tuple scoring | `scripts/chimera/title_tenure_model.py` | P and S | Evaluated on SIO oracle truth and on the 5 of 22 early-stamped RI events; if it only reproduces TAC-KBP it moves to the system section |
| Prompt-boundary invariant checker (what enters a prompt vs `state_of`) | `scripts/chimera/prompt_invariant_check.py` plus a test | S | Audits `story_context` output for later-chapter items without changing it; produces a measured leak count |
| M1 evidence gate v2, M2 cross-family replication | `PREREG_L1_v2_*.md`, prompts file, runner | P | Spend requests follow at CP-H |
| Diagnostic scripts for B1, B2, B13 | `scripts/chimera/diag_*.py` | S | Reproduce each defect with an executed command so the fix has a before-number |

## 3. Adapters proposed (each isolated, disable-able, with its own tests and, where measurable, an ablation)

All need a branch because they edit existing files. Order is by value per risk.

| # | Adapter or fix | Defects | Existing files touched | What changes for the product | What changes in existing numbers | Test and ablation |
|---|---|---|---|---|---|---|
| 1 | **Honest counters**: `retry_deferred` writes a link or stops counting "recovered"; `conditioned_on` derived from the request actually sent | B1, B3 | `resolve/runner.py`, `render/panels.py` | Reports stop overstating resolution and conditioning | **Yes**: `recovered_from_deferral` and `by_method[DEFERRED_RERESOLVED]` drop; `conditioned_on` loses sheet labels that did not condition | Unit tests on synthetic deferrals; assert `conditioned_on` equals the serialised refs |
| 2 | **Prefix resolve**: make `resolve --chapters` real (`max_chapter` parameter) | B2 | `pipeline/cli.py`, `commands.py`, `resolve/runner.py` | Lets any "resolve up to chapter c" run work | None for default runs | Test: results for chapters up to c equal a run on a truncated copy; needed for real-novel prefix experiments |
| 3 | **Prompt-boundary state policy**: a `PromptItem(text, ref, learned_at_pos, observer_scope)` builder that refuses items beyond the position; `story_context` and `appearance_of` read through `state_of`; wire in the existing `EpistemicLeakageValidator` | A1, A2, B3 | `world/context.py`, `persona/reference_gen.py`, render call sites | One state policy for panel, voice and wiki paths; auditable invariant | **Yes**: briefs and appearance attributes may lose later-chapter facts | Invariant test (plant a chapter-20 fact, assert refusal at position 9); ablation: policy on vs off, leak count from the checker in section 2 |
| 4 | **Dated wiki canon**: stamp canon with `learned_at_pos` and apply it inside the state digest | B4 | `persona/wiki_canon.py`, `persona/canon.py`, `render/panels.py`, `world/context.py` | Later canon stops leaking into earlier panels | **Yes**: panel prompts and digests change; cached panels invalidate | Test with a fixture canon fact dated after the position |
| 5 | **Title-holder repair**: fix the dropped `last_evidence`; gate the chapter-1 backward extension behind a `--causal` flag | B13, A7 | `resolve/title_holders.py`, possibly `core/interval.py` | Closed tenures keep their evidence; causal mode available | None by default; causal mode changes titles linked before the holder is declared | Compare on SIO and RI events; ablation switch is the flag |
| 6 | **Mention detection**: pass `is_address` from the dialogue path and measure; later a proposer test (Maverick, research-only because of its non-commercial licence) and a BookCoref-style verifier switch | B6, A9 | `mentions/runner.py`, `mentions/alias_type.py` | Targets the 58/88 undetected hard cases | **Yes**: mention counts change | Detection recall on the silver hard cases now, on human-verified ones after your labels |
| 7 | **Retraction writer**: give `retract_alias_bindings` a caller | B5 | `resolve/contradiction.py`, `resolve/runner.py` | The retraction axis becomes exercisable on real data | Possibly none until a retraction fires | Synthetic retraction fixture |
| 8 | **Reference guard**: an independent leak check on the finished image prompt, and re-wired reveal-aware reference selection behind a flag; StoryDiffusion only after a VRAM proof | B7, A3, Jularr-style guard | `render/panels.py`, `render/contract.py`, `persona/reference_gen.py` | Fewer spoiler leaks into panels; references conditioned honestly | Panel digests change if references are re-wired | Seeded-leak recall and false-block rate; image inspection by you (text-only tests do not prove visual correctness) |
| 9 | **Smaller**: data-hygiene notes (B8, B9, B11), alias-bucketing rule (A12), NER roster truncation and cache key (A11) | various | gold docs, `runner.py`, `ner.py` | Hygiene | Small | Each with a unit test |

Not proposed: a repository rewrite, new modalities, replacing the resolver with any donor (Graphiti, LlmLink), calibrated-abstention work as a claim, FLUX or other models outside the NoobAI-only rule.

## 4. Scope options

- **A (recommended, about 4 to 6 days of work):** adapters 1, 2, 3, 4, 5. They are what Track P experiments need (B2 prefix runs, B3 and the invariant for honest provenance, B13 and A7 for the title-holder model) and they fix the verified High-severity defects B1 to B4. Every numeric change is flagged and documented in the report.
- **B (A plus detection and retraction, about 2 more days):** adds 6 and 7.
- **C (everything in section 3, about 2 weeks):** adds 8 and 9; image-side work needs your inspection and a confirmed GPU.

## 5. Guardrails for the branch work

- Every adapter is a config switch or isolated module, off by default if it changes numbers; defaults only change when you say so.
- No silent loss of confidence, evidence, temporal, observer or provenance metadata.
- Tests first for each fix; the existing 1,277-test suite must still pass (the CLAUDE.md count) before anything is called done.
- `docs/EVOLUTION.md` and `docs/HANDOFF.md` get entries through the docs-sync agent only after you approve edits to existing docs.
- Source novels and any novel text stay out of every file; nothing is pushed.

## 6. Public exposure (information only)

Nothing new created here carries novel text. The standing public-exposure issue stays with you.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/prior_art_notes_A.md -->
## Source: `docs/research/NOVELTY_REPORT/prior_art_notes_A.md`

# Prior-art notes A (verification pass, 2026-10-15)

Claim under test: "disclosure-faithful identity resolution under parametric leakage" (chapter-filtering context does
not stop an LLM linking an alias to a later-revealed identity because it remembers the novel). Candidate
contributions: C1 premature-resolution metric via renaming controls; C2 evidence-gated linking rule; C3 small
reader-view / omniscient-view item set.

Method: each PDF fetched from arxiv.org/pdf/<id>, `pdftotext -layout`, relevant sections read (intro, method,
benchmark construction, eval protocol, limitations, data appendices) plus keyword sweeps (alias, coreference, identity,
leak, memoriz, parametric, renam, pretrain, spoiler, disclos, reveal, translat, serial, contamin). "No hits" = sweep of
the full extracted text returned nothing; figures were not inspected visually. Tags: [PUB] = read in the paper's own
text; [LEAD] = search snippet only; UNVERIFIED. Quotes verbatim. Section refs are the papers' own.

## 1. Narrative World Model: Narratology-Grounded Writer Memory for Long-Form Fiction  [PUB]
- Saifullah, Kornmaier, Kazi, Sharma, Kanade, Yadav (PocketFM). arXiv 2607.05577v1 [cs.AI], 6 Jul 2026. "Preprint.
  Under review." (no venue).
- Task/data: writer-memory QA; typed temporal-state graph + hybrid retrieval vs Graphiti/Zep, GraphRAG, RAG, all
  read through a held-constant Opus 4.8 reader over "chapter-safe" evidence (Fig. 1; s3.1 "chapters > n hidden").
  s4.1: 12 Project Gutenberg books (576 Qs; 110 multi-hop) + private "five production-style serialized books of 50
  chapters each" (not redistributable, de-identified Books A-E).
- (a) disclosure vs story time: YES, central. s2: "knowledge boundaries, reveal order ... focalized observer" are
  "first-class"; s3.2 scene records carry "event order, reveal order"; question families "focalization/epistemic (who
  knows what, and when they learned it)" and "reveal-order-versus-event-order" (s4.1).
- (b) alias/identity/coref: NO. Sweep hits "alias" only inside a Table 6 story example ("courts the same woman under an
  alias"). Schema (s3.2) has no entity-linking record; no "is mention X person Y" task.
- (c) leakage/memorisation control: NONE. No hits for leak/parametric/memoriz/contamin/pretrain. Chapter filtering is
  the only control. s8: the no-memory row "is an evidence-free abstention control, not a closed-book recall probe".
  Pseudonymised names in private corpus are for confidentiality (App. B), not leakage control. Gutenberg corpus is
  likely memorised by the reader; not discussed.
- (d) web serials/translated: "serialized books" only; origin/language not stated. UNVERIFIED.
- Closest overlap with EchoTales: chapter-safe cutoff plus reveal-order vs event-order as a modelled axis (supports C3's
  reader/omniscient split in spirit).
- Exact difference: no identity linking, no premature-resolution metric, no renaming/leakage control; scores QA
  accuracy of memory representations.

## 2. Shared Worlds, Private Minds: Structured Memory for Long-Form Writing as World Creation (system: NarraWorld)  [PUB]
- Tian, Gu, Su, Chao, Yin, Guo, Zhang, Shen, Luo, Kong, Xia, Liu* (Southeast Univ., Beijing Zhongguancun Academy,
  ZhuiWen Technology, others). arXiv 2609.32401v1 [cs.CL], 26 Sep 2026. No venue in the text read.
- Task/data (s3.1): long-form writing memory. ConStory-Bench (200 stories), TMAS (168 continuation checkpoints), LSGC
  (5 starters x 14 chapters); transfer to RMTBench role-play and LoCoMo. Baselines Mem0, Graphiti, Hindsight, AriGraph,
  StructMem. Metrics: writing quality / consistency error density.
- (a) disclosure vs story time: PARTIAL, as a design principle. s2.4: "Relevant memory and usable memory differ by
  story time, disclosure state, focalization, and branch. For example, in a mystery, the detective may not yet know
  the truth, while the culprit's identity should not be disclosed prematurely." Admissible view V_q filters
  "temporal, disclosure, and branch scope"; per-character belief view B[c] can hold "a false belief" (App. A.2).
  Never measured as a disclosure-faithfulness metric.
- (b) alias/identity: YES, internal pipeline stage only. App. A.1: "links aliases to existing entities when the
  evidence supports the match and creates a new entity otherwise". Not evaluated; not gated on reveal time.
- (c) leakage/memorisation control: NONE (no hits for leak/parametric/memoriz/contamin/renam). s3.1: conditions
  "exclude future text and evaluator-only references" (context filtering only).
- (d) web serials/translated: not addressed; English benchmarks.
- Closest overlap: explicit "identity should not be disclosed prematurely" + alias-linking stage + append-only store
  where "A state change closes the previous validity interval" (App. A.1), architecturally near EchoTales' graph.
- Exact difference: premature disclosure is a design aim, unmeasured; alias linking unevaluated and unconditioned on
  reveal time; no leakage/renaming control; downstream task is writing quality.

## 3. Scaling Long-Form Story Generation via Narrative State Tracking (NstAgent)  [PUB]
- Zhennan Wan, Jianfei Chen (Tsinghua). arXiv 2609.35759v1 [cs.CL], 28 Sep 2026. "Preprint."
- Task/data (s3-4): generate 10K-100K-word stories; typed state (character states, past events, future requirements);
  revised ConStory-Bench windowed Consistency Error Density + WritingBench. Stories are LLM-generated from prompts.
- (a) disclosure vs story time: NO. State is "retrospective ... as well as ... prospective" (s4.1); "knowledge" is
  only a field inside character state; the "scope marker" (s3) is a judge-window device.
- (b) alias/identity: NO. Only identity-related text is a failure case: the agent "names the same character Bishop
  Armitage in Chapter 0 and Bishop Haldane from Chapter 4 onward"; "Nothing in the loop compares a new entry against
  the earlier text" (own-generation name drift, not resolution).
- (c) leakage control: NO (no hits). (d) web serials/translated: NO; synthetic stories.
- Closest overlap: none substantive (chapter t prompt "contains no earlier chapter text").
- Exact difference: generation-side consistency; no identity, disclosure or leakage dimension. Cite only as generic
  narrative-state related work, not competing prior art.

## 4. TimeChara: Evaluating Point-in-Time Character Hallucination of Role-Playing LLMs  [PUB]
- Ahn, Lee, Lim, Kim, Yun, Lee, Kim (SNU, NAVER AI). arXiv 2405.18027, 28 May 2024; Findings of ACL 2024, pp.
  3291-3325 [LEAD for venue/pages, from search result; PDF is the arXiv version].
- Task/data (s1, s3, s5): 10,895 interview-style instances; 14 characters from Harry Potter, LotR, Twilight, Hunger
  Games; 219 time points; types future / past-absence / past-presence / past-only; GPT-4 judge with spatiotemporal
  labels. Baselines: zero-shot, CoT, RAG, "RAG-cutoff" ("limit its retrieval exclusively to the events prior to a defined
  character period"), and Narrative-Experts.
- (a) disclosure vs story time: YES in role-play form: "avoiding spoilers" is a stated rationale; metric is
  future-type accuracy ("All baselines ... accuracies at 51% or below", s5.4). Character-knowledge boundary, not
  reader-knowledge boundary.
- (b) alias/identity/coref: NO (sweep: none; questions are scene-event interview prompts).
- (c) leakage: ACKNOWLEDGED AND EXPLOITED, not controlled. s3: LLMs "store knowledge of these series well in their
  parametric memories ..., facilitating tests"; s1: "despite LLMs memorizing extensive knowledge from books ... they
  still struggle". No renaming/anonymised control. RAG-cutoff is context filtering only.
- (d) web serials/translated: NO; Limitations: "Sourced only from English books".
- Closest overlap: best direct precedent that LLMs leak future-plot knowledge of famous novels despite being told not
  to; RAG-cutoff = the chapter-filter baseline.
- Exact difference: role-play event knowledge, not alias->identity linking; leakage is the phenomenon but never
  isolated by renaming; no evidence-gated rule; no leakage metric of the proposed kind. Supports the premise only.

## 5. SynthWorlds: Controlled Parallel Worlds for Disentangling Reasoning and Knowledge in Language Models  [PUB]
- Ken Gu, Advait Bhat, Mike A. Merrill, Robert West, Xin Liu, Daniel McDuff, Tim Althoff (UW, Stanford, EPFL,
  Google). arXiv 2510.24427 (v1 28 Oct 2025); ICLR 2026 (PDF header: "Published as a conference paper at ICLR 2026").
- Task/data (s3-4, App. B): parallel Wikidata-derived corpora, real-mapped (RM) vs synthetic-mapped (SM) with identical
  structure; multi-hop QA and page navigation; metric "knowledge advantage gap" (RM minus SM).
- (a) disclosure vs story time: NO. Timestamps shifted by fixed offset only "to prevent timestamps from trivially
  revealing real-world identities" (App. B); no narrative or disclosure axis.
- (b) alias/identity: NO as a task. Only name-derivation consistency ("Vancouver -> Metronis, then George Vancouver ->
  Altheon Metronis").
- (c) leakage control: YES, the whole paper; strongest precedent for C1's method. s1: synthetic data built from
  "existing content directly (e.g., novels)" "results in parametric knowledge leakage". App. B: "Simple renaming risks
  (a) factual leakage ... (e.g., Tokyo -> Torioka, which continues to suggest Japanese origins)". Leak audit: an LM is
  asked to guess the real entity behind each synthetic page and leaked pages are removed. s6: idea "generalizes to any
  knowledge graph".
- (d) web serials/translated: NO.
- Closest overlap: renaming as leakage control, a performance gap metric, and a rename-leak audit.
- Exact difference: encyclopedic multi-hop QA, not fiction; no disclosure-time or premature-resolution notion. Any
  EchoTales renaming control must cite SynthWorlds as the method source; novelty of C1 can only lie in the narrative /
  disclosure-cutoff metric, not in renaming itself.

## 6. E2RAG / ChronoQA: Respecting Temporal-Causal Consistency: Entity-Event Knowledge Graphs for RAG  [PUB]
- Ze Yu Zhang, Zitao Li, Yaliang Li, Bolin Ding, Bryan Kian Hsiang Low (NUS, Alibaba). arXiv 2506.05939v1 [cs.IR],
  6 Jun 2025; EACL 2026 Long Papers [LEAD, from search result].
- Task/data (s3, Tables 1-2): ChronoQA, 497 QA pairs over 9 stories (Oz, Sherlock Holmes x4, Phantom of the Opera,
  Harry Potter 1 and 2, Les Miserables), all stated as Project Gutenberg; 8 facets (Character Consistency 229, Causal
  96, ...); questions auto-generated by o1-pro / Claude-3.7 with passage offsets.
- (a) disclosure vs story time: PARTIAL. Query 1: naive RAG "overlooks crucial information revealed later" (Quirrell vs
  Snape); questions hinge on temporal facets ("after the troll incident"). That is retrieval of the right chronological
  passage; no reader-time cutoff protocol found.
- (b) alias/identity: OPPOSITE DESIGN. s4: "We therefore keep each mention ... distinct"; "Hermione in Chapter 9 versus
  Miss Granger in Chapter 16" are separate nodes; no merging; no resolution evaluation.
- (c) leakage control: NONE (no hits for leak/memoriz/parametric/contamin/renam); heavily-read books used without a
  closed-book or renamed baseline.
- (d) web serials/translated: NO.
- Closest overlap: time-aware KG over novels with a "revealed later" example; mention-level entity nodes.
- Exact difference: retrieval QA quality, not identity linking; avoids premature merging by never merging, rather than
  gating merges on evidence/disclosure; no leakage control.

## Cross-paper takeaways
1. None of the six defines a premature-resolution metric, an evidence-gated alias->identity rule, or a reader-view vs
   omniscient-view item set (absence from read sections and keyword sweeps; not proof for unread figures).
2. Renaming as leakage control: precedent SynthWorlds (Wikidata, not fiction). Leakage-in-novels motivation: TimeChara.
   Neither combines them with alias resolution under a disclosure cutoff.
3. Closest on disclosure-aware memory: NWM (reveal order, chapter-safe cutoff) and NarraWorld ("identity should not be
   disclosed prematurely"; alias stage). Neither evaluates leakage or premature linking.
4. Unverified: venues for TimeChara (Findings of ACL 2024) and E2RAG (EACL 2026) come from search snippets; NWM's
   private "serialized books" provenance (web serial or not) is UNVERIFIED. No paper here covers web serials or
   translated novels.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/prior_art_notes_B.md -->
## Source: `docs/research/NOVELTY_REPORT/prior_art_notes_B.md`

# Prior-art notes B (dataset / coreference / leakage-control side)

Date: 2026-10-15. Scope: verify prior art against the claim "disclosure-faithful identity resolution under
parametric leakage" (prefix-of-book context; premature-resolution metric via renaming controls;
evidence-gated linking rule; small reader-view / omniscient-view item set).
Tags: [PUB] = I read the relevant sections of the paper text (PDF via pdftotext) | [LEAD] = snippet/abstract only |
[REPO] = file read from the project repository | [SUMM] = web page read through a summarising fetch tool, wording not verbatim |
UNVERIFIED | INACCESSIBLE. Downloads were kept in the scratchpad and never executed. Qidian was not accessed.
Limit on negatives: "no X in paper" below means I read the sections named AND grepped the full extracted text for
contamin|leak|memoriz|spoil (0 hits unless stated). Absence is bounded by that; it is not proof about unread parts.

## 1. GenWebNovel (Zhao et al., COLING 2025, pp. 3836-3849) [PUB]
- Task/data: nested NER in Chinese web novels. 400 chapters, 1,214,283 tokens, two genres (XuanHuan, History)
  (Abstract). Types: PER, LOC, ORG only (Sec 3.2; Limitations: "our annotations only involve three basic entity types").
- Source: 40 novels crawled from Qidian; "Each selected work includes its first 10 chapters (open for access)" (Sec 3.1).
  So every text is a 10-chapter prefix of a novel; later-chapter reveals are structurally absent.
- Language: original Chinese (Table 1 "Language: Chinese"); not translated text. Agreement: mean Cohen kappa 0.8332 (annotation-quality paragraph, Sec 3).
- Split: novel-level 8:1:1 = 32/4/4 novels (Sec 5.2.1). Model use: GPT/Llama in-context retrieval; no memorisation/leakage control.
- Coreference: NOT covered. Conclusion: "In the future, our work will involve continued annotation for coreference
  resolution and entity relationships on this corpus" (p. 3843). Introduction only cites coref as a downstream use.
- Licence / terms: paper has a "Statement" citing Art. 24 PRC Copyright Law (research use, no broad redistribution).
  Repo (github.com/hjzhao73/GenWebNovel): README says raw text and entity strings are NOT released; only URLs, offsets,
  labels, checksums; users rebuild text locally [SUMM, plus raw README fetched with curl, "does not directly release raw
  novel text"]. DATA_USE_AGREEMENT.md [REPO-style raw read]: "Locally reconstructed full-text data must not be
  redistributed without permission from the relevant rights holders." No OSS licence file seen in repo listing [SUMM].
  Reconstruction script fetches Qidian pages; this is not a route we should use (instruction: do not access Qidian).
- Consequence: usable only as annotation offsets; cannot supply translated text or reveal-bearing later chapters.

## 2. Song & Liu 2024 (LREC-COLING 2024, 2024.lrec-main.125, pp. 1408-1421) [PUB]
- Authors are Li Song and Ying Liu. Task: character-representation resolution (zero + non-zero anaphora) in Chinese novels;
  adapts CHEN-Model (ARMCC) + BERT speaker extraction (SECN); tested on one print novel, White Deer Plain (Sec 5).
  Reported 70.62 F1 non-zero coref, 32.25 F1 zero-pronoun (Conclusion).
- Hidden identity listed as an open challenge (Sec 5.2 "Overall Analysis", fifth point, p. ~1415-1416). Quote:
  "Fifthly, character-resolution for plots about hidden identity, including recognizing the pretenders, tracing the
  criminals, distinguishing the substitute and the real one ... can hardly demonstrate good performance without manual
  assistance." Example: Lu San possessed by the ghost of Tian Xiao'e.
- Caveats: this is a qualitative observation from one novel, no hidden-identity test set or metric, no LLM, no
  leakage/prefix setup, no web-novel or translated text. Fair wording: "listed as an unsolved challenge", not "measured".

## 3. One line each
- LlmLink (Zhu, Wang, He; COLING 2025, pp. 11334-11347) [PUB]: dual-LLM NER+coref over *chunked* narratives with a
  character memory; data = coref-annotated LitBank (90/10 docs) and WhoLink (401 character questions from NarrativeQA)
  (Sec 4.1). Chunked left-to-right processing is prefix-like, but "memorisation" = an explicit memory module, not
  parametric recall. No reader-view/omniscient-view split, no contamination/leakage check (0 grep hits); both datasets
  are public-domain / widely circulated texts. Limitations section silent on LLM prior exposure.
- BookCoref (Martinelli et al., ACL 2025, 2025.acl-long.1197) [PUB]: book-scale character coref; silver 50 books/10.8M
  tokens, gold 3 books (Animal Farm, Pride and Prejudice, Siddhartha) (Table 1/Sec 4). English, Project Gutenberg.
  Annotation is whole-book (no reader-view split). Limitations (Sec 7): "our test set is composed of canonical texts, i.e.,
  books that have been studied extensively and are readily available on the Internet" -> acknowledges, does not control.
  Table 3: off-the-shelf BookNLP CoNLL-F1 42.2 on gold, 50.6 on split-gold (so BookNLP evaluated on full books; no prefix setup).
- FantasyCoref (Han et al., CRAC 2021, 2021.crac-1.3, pp. 24-35) [PUB]: 211 Grimm tales + 3 fantasy works, English,
  coref annotated from the "omniscient writer's point of view (OWV)". Sec 2.2 "Asymmetry of Knowledge" (deception,
  disguise, mistaken identity, secret, plot-twist): "In these cases, we follow the omniscient writer's point of view."
  So omniscient-only; reader view is not annotated. Intro example (evil queen disguised as old woman) shows the authors saw
  the reader/omniscient gap. No leakage control (0 hits). Short fairy tales, so a famous-story memorisation risk is unaddressed.
- Maverick (Martinelli, Barba, Navigli; ACL 2024, 2024.acl-long.722) [PUB, Abstract/Sec 4-5 skimmed + grep]: encoder coref
  model, SOTA on OntoNotes, also LitBank and PreCo; "long-document and out-of-domain" claims. No reader-view data, no
  contamination or prefix evaluation (0 grep hits for contamin|leak|memoriz; "memory" there means GPU memory).
- SagaScale (Du et al., arXiv 2601.09723, Dec 2025) [PUB]: long-context QA over 103 full novels (77 EN, 26 ZH; copyrighted
  + Gutenberg). NOT coreference. HAS a contamination control: closed-book filtering with GPT-4.1, DeepSeek-R1,
  Claude-Opus-4, Gemini-2.5-Pro, "If any of these models can answer a question correctly, we remove that question"
  (Contamination Filtering); closed-book accuracy max 11.7% (Table 4). Whole-novel input; no prefix/reader-view axis.
  This is the nearest prior art for the *idea* of testing parametric knowledge, via filtering rather than renaming.
- LitBank coref (Bamman, Lewke, Mansoor; LREC 2020, pp. 44-54) [PUB]: 100 English works, 210,532 tokens, 29,103 mentions,
  ~2,100-word excerpts. Sec 4.2.5 "Revelation of identity" annotates "from the perspective of the textual reality, rather
  than from the reader's state of knowledge at the moment of encountering the mention" i.e. omniscient/whole-text; the
  text also says "reader's point of view ... scoped over the entirety of the text". No reader-at-time-t labels, no leakage
  control (0 hits). Corpus licence line on page 1: CC-BY-NC.
- LitBank entities (Bamman, Popat, Shen; NAACL 2019) [PUB, abstract+grep only]: ACE-category entity NER on 100 English
  texts; no coref/identity tracking in this paper; no leakage control (0 hits).
- BookNLP [SUMM]: README (github.com/booknlp/booknlp) describes NER, coref, character name clustering, speaker
  attribution, events; English only; trained on LitBank (+PreCo for coref); README: "Accurate coreference at the scale
  of a book-length document is still an open research problem" and full coref "tends to erroneously conflate multiple
  distinct entities". Wording is via a summariser, so UNVERIFIED verbatim. No reader-view or leakage notion found there.
- Closest additional find, NOT in your list: KoCoNovel (Kim, Lee, Lee; arXiv 2404.01140, LREC-COLING 2024) [PUB]:
  178K tokens, 50 Korean novels from Wikisource public domain. "offers annotations from the perspectives of both the
  omniscient author and readers" (Introduction); Table 3 example: "Taehoon" and "Kyung-suk" are separate entities in the Reader
  version, one entity in the Omniscient version. Appendix C Table 12 lists only five works (IDs 0,13,16,36,49) where the
  views differ ("the distinction ... appears only in select works"). Experiments (Sec 6) use only "Omniscient & Separate"
  with BERT-style models; no LLM, no leakage control (0 hits), not translated, not web serials. This PRE-EMPTS a claim that
  a reader-view/omniscient-view annotation is new in itself; what remains open is its use as a time-indexed, LLM-leakage test.
- Also relevant: IdentifyMe (Manikantan et al., arXiv 2411.07466) [PUB, abstract/Limitations/Sec 2 skimmed]: MCQ mention
  resolution on LitBank-derived long narratives; Limitations: "preliminary investigations suggest limited contamination
  risk, as none of our evaluated LLMs could accurately reproduce the original CoNLL annotations ... we acknowledge the
  potential possibility of data contamination". Probe, not a control; no prefix; no reader-view labels.

## 4. TAC-KBP temporal slot filling (primary: KBP2013 English & Temporal SF overview, tac.nist.gov) [PUB]
- Sec 2.2: "Its goal is to add temporal validity information to selected slots in the regular SF output." Seven slots
  (per:spouse, per:title, per:employee_or_member_of, residences, org:top_employees/members). Input = (entity, filler, relation
  provenance); output a 4-tuple [T1 T2 T3 T4] "indicating that the relation is true for a period beginning at some time
  between T1 and T2 and ending ... between T3 and T4"; score Q(S) = mean of 1/(1+|ti-gi|), unit years. Runs only in 2011 (pilot) and 2013.
- Overlap risk: it is valid-time tracking of relations in news/web text. It has no belief/disclosure time, no
  reader-visible prefix, no identity merge, no leakage. Overlaps only with the "when was this state true" half of
  a bitemporal state; it does not model "when did the reader learn it".

## 5. Search for BookNLP / modern coref on translated web novels, and for spoiler / future-knowledge leakage in coref
Result: NOTHING found that does either. Negative result is bounded by the engine (WebSearch, US-only, 19 queries) and by
not having searched CNKI / KCI / Naver Academic / Baidu Scholar directly (INACCESSIBLE by this tool).
Queries run (standard unless noted):
 1. "GenWebNovel web novel named entity recognition dataset COLING 2025"
 2. "Song Liu 2024 LREC-COLING character resolution novel hidden identity"
 3. "LlmLink dual LLMs coreference long narrative"
 4. "BookCoref coreference resolution book-scale ACL 2025"
 5. "FantasyCoref coreference resolution fantasy fiction Han 2021 CRAC CODI"
 6. "Maverick coreference resolution efficient accurate Martinelli ACL 2024"
 7. "SagaScale long-context novel dataset entity coreference benchmark"
 8. "TAC-KBP temporal slot filling task definition 2011 2013 temporal slot filling evaluation"
 9. (extended) "coreference resolution LLM spoiler future knowledge leakage narrative prefix of book character identity"
10. "BookNLP evaluation machine-translated web novels character coreference"
11. "LLM memorization of novels entity renaming control character name substitution evaluation reading comprehension"
12. "temporal leakage story understanding incremental reading LLM only text up to chapter ..."
13. Chinese: "小说 人物指代消解 网络小说 身份揭示 马甲 别名 人物共指 数据集"
14. Korean: "웹소설 인물 지칭 상호참조 해결 대규모 언어모델 번역 소설 데이터셋"
15. "reader's point of view versus omniscient coreference annotation hidden identity revealed later ..." (found KoCoNovel)
16. "incremental online coreference ... memorised novel pretraining entity linking evaluation fiction"
17. "'Speak, Memory' ... name cloze" (no useful hit; I downloaded arXiv 2305.00118 directly instead)
18. "spoiler-aware question answering novels LLM reading up to chapter k ..."
19. "web novel dataset machine translated Korean Chinese English character mention alias linking LLM benchmark 2025 2026"
Adjacent work found (renaming / memorisation controls exist outside coref-on-prefix):
- Speak, Memory (Chang et al., arXiv 2305.00118) [PUB abstract]: name-cloze shows GPT-4 memorised many books; "contaminating
  test data". Measures memorisation; does not propose a reading-progress identity metric.
- Jiang & Ferraro, "Beyond Math: Stories as a Testbed for Memorization-Constrained Reasoning" (arXiv 2412.14368 v6) [PUB
  abstract + method skim]: name replacement (placeholder / cross-cultural / same-culture) on six character-centric tasks
  incl. screenplay character coreference; "up to a 45.2% accuracy drop". Renaming as a memorisation control is therefore
  NOT novel; its application to disclosure timing / premature merges is not in this paper.
- WhoDunIt (Gupta, arXiv 2502.07747) [PUB abstract + method]: character-name swaps / celebrity-name substitutions on
  mystery novels; accuracy falls with famous names. Same point: renaming control exists; culprit detection, not identity resolution.
- TLDM (Hamilton et al., arXiv 2505.14925) [PUB, Sec 3]: asks for state "up to a given point" using "windows of interest"
  of the first 25/50/75/100% of chapters, full text in context; T1 (title+author only) "tests for text memorization".
  Prefix is requested by instruction; no premature-identity or leakage measurement (0 hits for leak/contamin). NovelQA [LEAD].
- Evaluations of BookNLP on non-translated text [LEAD, snippets only]: Portrayal (arXiv 2308.04056), Dutchcoref vs BookNLP,
  fanfiction pipeline (NUSE 2021). None on translated web novels. BookCoref Table 3 (above) is the only BookNLP number I read.

## Closest overlap with EchoTales claim / exact difference (one line each)
- GenWebNovel: closest = Chinese web-novel entity annotation; differs: NER only (coref is "future" work), first-10-chapter prefixes, original Chinese, text not redistributable.
- Song & Liu 2024: closest = names hidden identity as a failure class; differs: one sentence in a qualitative analysis, one print novel, no metric, no LLM, no leakage.
- LlmLink: closest = chunk-sequential LLM linking with memory; differs: no parametric-leakage test, LitBank/NarrativeQA public texts, no reveal-time labels.
- BookCoref: closest = book-scale character coref, tests BookNLP; differs: whole-book omniscient labels, canon Gutenberg books, admits (does not control) web availability.
- FantasyCoref: closest = disguise/plot-twist coref guideline; differs: omniscient-only annotation, short tales, no time index, no LLM leakage.
- Maverick: closest = SOTA coref baseline; differs: no narrative-time or leakage notion.
- SagaScale: closest = closed-book contamination filter on novels (EN+ZH); differs: QA not identity resolution, filters items rather than renaming, no prefix.
- LitBank / BookNLP: closest = literary coref data and tool; differs: LitBank Sec 4.2.5 explicitly annotates textual-reality (omniscient) view; no reader-at-time-t labels.
- KoCoNovel (extra): closest = actual reader-view vs omniscient-view labels (5 of 50 works, Korean public domain); differs: models tested on omniscient only, no LLM, no leakage, no chapter-indexed disclosure, not translated.
- TAC-KBP TSF: closest = valid-time intervals for relations; differs: news slot values, no disclosure/belief time, no identity merges.
- Renaming controls (Chang 2023 / Jiang 2024 / WhoDunIt): closest = rename-to-break-memorisation; differs: applied to QA/guessing, not as a premature-resolution rate for aliases under a prefix.
- Net: no paper found combining prefix context + renaming control + reader/omniscient labels for identity resolution; each part has precedent, so novelty should be argued as the combination and the metric, not any single part.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/register_notes_F1.md -->
## Source: `docs/research/NOVELTY_REPORT/register_notes_F1.md`

# Integration Register, family F1: mention detection and coreference (notes, 2026-10-15)

Method. Each PDF fetched with curl into a scratch dir, read with `pdftotext` (never executed), method + experiment + limitation sections read by me, plus a keyword sweep (leak|memoriz|contamin|spoil|renam|parametric) over the full text. Licences were fetched from the repo LICENSE file or the HF model/dataset card API. Repo files in EchoTales were read, not changed. Nothing was run on EchoTales data, so every "would it help" line is a plan, not a result. Tags: [PUB] method+experiment sections read; [README] first-party README only; UNVERIFIED. Decision values: adopt / adapt / baseline-only / reject. No donor reaches "adopt": each needs a measurement on EchoTales data first.

Repo facts used (read, not assumed). Mention detection = `mentions/runner.py::detect_mentions_in_chapter`: gazetteer layer first, then `MentionDetector.detect(text) -> list[NerSpan]` (`mentions/ner.py`, qwen2.5:7b in 6,000-char windows), then `classify_alias_type` (`mentions/alias_type.py`, 23-entry `_TRANSFERABLE_TITLE_NOUNS`, `is_address` never passed at runner.py:207 = defect B6), then the whole-volume commonness filter. Resolution = `resolve/runner.py` (FORCE_LINK pre-filters, conformal gate `resolve/gate.py`, DEFER queue). Titles = `resolve/title_holders.py` (volume-first, links backwards to chapter 1 by design = A7). Already in repo: a LitBank person-key adapter with results (`docs/results/EXPERIMENT_RESULTS.md`: CoNLL F1 15.9 full key / 42.4 proper names, standard scoring; B3 precision 99.7, recall limited at detection: 887 of 2,665 proper-name key mentions produced with exact span) and `eval/baseline_b.py` = a loose "LLMLINK-style" baseline (qwen2.5:7b, per-mention linker, flat 60-entry memory; no rewind, no prompt optimisation, no cache/memo split). Hard-case set: `data/eval/hardcase_taxonomy.json`, banner "SILVER -- LLM-derived reference set (Claude), not human gold; no IAA"; 58 undetected = relational 25 (15 relational + 10 address-term), title_transfer 16 (11 definite-title + 5 address-term), body_change 8, reveal 7 (incl. 2 gold-span defects), disguise 1, control 1; so at most 55 real losses (ERRATA E3). Dev GPU: nvidia-smi on this host shows RTX 4060 Laptop, 8188 MiB (CONFIRMED here, not only from docs).

---
## 1. Maverick
- **Source**: "Maverick: Efficient and Accurate Coreference Resolution Defying Recent Trends", Giuliano Martinelli, Edoardo Barba, Roberto Navigli (Sapienza). arXiv 2407.21489v1, 31 Jul 2024; ACL 2024 long, aclanthology 2024.acl-long.722 (venue/id from the repo README link; the PDF read is the arXiv version). [PUB]
- **Contributes** (Secs 3.1-3.3, 5.1-5.5, Limitations): encoder-only DeBERTa-v3 coref. Mention extraction = start-token probability then end-token probability per start (EOS regularisation, prunes candidates ~9x/18x vs Coarse-to-Fine, Table 1); three clusterers (s2e, mes with 6 category scorers, incr = shift-reduce with a small transformer over cluster mentions). Reported: OntoNotes CoNLL-F1 83.6 (mes, large, 504M params); LitBank 78.3 (incr; LitBank train/test per-document, docs ~2,105 tokens); PreCo 88.0 but seq2seq is higher (88.5) because Maverick's extractor "favors precision rather than recall" (Sec 5.2); OOD with gold mentions up to +10.1 on LitBank_ns over LingMess (Table 5). Inference 4.0 GiB peak (large, OntoNotes dev, RTX 4090).
- **Artifact and licence**: github.com/SapienzaNLP/maverick-coref, `LICENSE.txt` = "Attribution-NonCommercial-ShareAlike 4.0 International". HF `sapienzanlp/maverick-mes-litbank` and `-ontonotes`: card licence `cc-by-nc-sa-4.0`. Weights are English-only (card tag `en`).
- **Touches**: a new `MentionDetector` subclass beside `QwenNerDetector` in `mentions/ner.py` (the ABC already exists), feeding `NerSpan`s into the layer-1 loop of `mentions/runner.py`; output still passes `classify_alias_type` and the commonness filter. It must NOT touch `resolve/runner.py` or write links.
- **Product value**: candidate-span recall for the nominal/title mentions that EchoTales loses at detection (relational_deictic 25 + title_transfer 16 = 41 of the 58 silver losses by category, if they are real). A coref model proposes NOM person mentions ("the clan head", "his master") that the qwen window prompt and the 23-entry title list miss. Detection is not resolution: title spans still need `title_holders.py`, and relational deictics need a resolver rule that does not exist yet.
- **Paper value**: ablation baseline (strongest public encoder coref next to BookNLP, and the model BookCoref itself uses). Not novelty: using a coref model's spans as proposals is engineering.
- **Integration form**: isolated adapter behind a config switch, default off; research mode only.
- **Cost**: GPU fits (4.0 GiB peak large model) but not alongside qwen2.5:7b on 8 GB, so run as a separate pass (house rule: check GPU free first, no CPU offload). Windows of about 1,500 words (BookCoref's setting; Maverick trained on short docs). 3-5 engineering days (sentence splitting for EOS, offset mapping, B10 off-by-one offsets). Annotation: precision on the ADDED mentions, 2 annotators x ~150 items, about 2 days. Compute: minutes per volume.
- **Evidence needed and available**: needed = per-category recall of the human-verified hard cases (not the silver 88) and precision on added mentions after `classify_alias_type`; zero-shot LitBank person key vs the repo's 42.4/15.9 (note Maverick-LitBank is in-domain on LitBank, so use the OntoNotes checkpoint for the fair out-of-domain row). Available = paper numbers above, all English, news/Gutenberg-fiction, none on translated web fiction.
- **Limits**: authors: single RTX 4090, larger encoders and multilingual untested ("did not test our formulation on multiple languages"). Mine: NC licence blocks a commercial product; LitBank checkpoint types include LOC/FAC/GPE/ORG (needs a person filter); pronoun and generic NOM spans conflict with non-negotiable 4 unless filtered; no calibration, so it cannot feed the conformal gate; added false mentions propagate to `state_of`; translated-xianxia domain mismatch (names fused with epithets) unmeasured.
- **Decision**: adapt (research-only proposer). Product use blocked until licence is resolved (retrain on own labels or owner accepts NC).
- **Test**: on the human-verified hard cases, proposer adds at least X% of the real undetected spans AND precision on added mentions after the alias-type filter is at least a pre-registered bar (suggest 0.90, to match non-negotiable 9; owner to set) with a bootstrap CI; otherwise baseline-only.

## 2. BookCoref (benchmark and silver pipeline)
- **Source**: "BOOKCOREF: Coreference Resolution at Book Scale", Giuliano Martinelli, Tommaso Bonomo, Pere-Lluis Huguet Cabot, Roberto Navigli. ACL 2025 Main, pp. 24526-24544 (aclanthology 2025.acl-long.1197); arXiv 2507.12075 (v1 16 Jul 2025; the arXiv id was not in the brief). [PUB]
- **Contributes** (Secs 3.1-3.5, 4-5, App. A-D, Limitations): pipeline given a book and a closed character-name list C(b): (1) Character Linking = ReLiK entity linker fine-tuned on LitBank person clusters (named by hand, pronouns removed; held-out F1 83.1, App. B); (2) Cluster Refinement = Qwen2-7B-Instruct yes/no "does [mention] correspond to the character?" (App. C prompt); (3) Cluster Expansion = Maverick on 1,500-word windows, then on groups of G=10 windows (Maverick_xl). Table 2 on the 3 gold books: link precision 88.6 -> 93.8 with the LLM filter; final CoNLL-F1 74.7 without vs 80.5 with LLM filter + grouping. Gold = Animal Farm, Pride and Prejudice, Siddhartha (229k tokens; 120 h; MUC IAA 96.1 on a 2,000-word subset by three expert annotators who are the authors). Silver = 50 Gutenberg books, 10.8M tokens. Table 3: off-the-shelf BookNLP CoNLL-F1 42.2 (full books; CEAF-phi4 only 2.4) and 50.6 on 1,500-token splits.
- **Artifact and licence**: github.com/sapienzanlp/bookcoref contains `evaluate.py`, `download_data.py`, `src/metrics.py`, predictions; NO pipeline/annotation script is in the listing and no BookCoref model is under `sapienzanlp` on HF (searched "book", "character"): so the pipeline is re-implementable from the paper, not downloadable [UNVERIFIED that none exists elsewhere]. Licence conflict: repo README "License ... Creative Commons Attribution-NonCommercial-ShareAlike 4.0" (badge says CC BY-NC 4.0); HF dataset card metadata `cc-by-sa-4.0`. Treat as NC until the authors clarify. Paper App. A: ReLiK and Maverick are CC BY-NC-SA; Qwen2 Apache 2.0; LitBank CC BY 4.0.
- **Touches**: (a) the gold set -> `eval/` adapter beside `eval/litbank.py` (external number); (b) the Cluster-Refinement idea -> a yes/no verifier on mentions ADDED by any non-gazetteer layer (inside `detect_mentions_in_chapter` before `_make_mention`), using the existing qwen2.5:7b client. (c) NOT the expansion step: it fuses mentions across ~15,000-word windows with no disclosure time, i.e. omniscient by construction; it would contradict `state_of` and the reader-observer axis.
- **Product value**: moderate for (b): it is the only published measurement that a cheap local LLM verifier lifts link precision (+5.2 on their data). Low for (a): gold is 3 canonical Gutenberg books, English.
- **Paper value**: (a) ablation baseline / external anchor; (b) none (engineering). Overlap flag: "precision-first, LLM-verified linking from a known character list" is stated in Sec 3.2.2 ("We place a strong emphasis on the precision of our initial cluster formation: false positives ... can easily propagate"), so C2 (evidence-gated linking) cannot be argued as "an LLM checks the link"; only the prefix-entailment constraint (a cited in-prefix span must entail the link) is outside BookCoref.
- **Integration form**: (a) baseline-only; (b) config switch around an existing detector layer.
- **Cost**: (b) one qwen call per added mention, minutes per volume on the 4060; 1-2 days. (a) 1-2 days adapter plus scope decision: EchoTales never proposes pronouns/nominals, so a full-key score is low by design (same as LitBank P1 15.9); a restricted named-mention protocol must be pre-declared.
- **Evidence needed and available**: needed = verifier precision/recall on the 55 human-verified real losses plus a random sample of existing NER mentions; available = their Table 2 (3 gold books; verifier tested only on explicit mentions, 42.7% of which exactly match the character name, App. C).
- **Limits**: authors (Sec 7): silver pipeline "may contain errors"; characters only; "our test set is composed of canonical texts, i.e., books that have been studied extensively and are readily available on the Internet"; English only. Mine, new: App. C says the verifier may answer "correctly because of its parametric memory", i.e. the authors saw that the LLM filter can lean on memorised books and did not test it. For EchoTales this is the exact leakage channel: a Qwen verifier on a famous novel is not a clean precision estimate; renaming control needed. Expansion is non-causal. Gold annotators are the authors.
- **Decision**: adapt the verifier (b) behind a switch; baseline-only for the gold set (a); reject the expansion step.
- **Test**: verifier precision on added mentions with and without letterwise renaming of names in the context (B12: renaming must be letterwise); adopt only if precision gain survives renaming.

## 3. LlmLink
- **Source**: "LLMLINK: Dual LLMs for Dynamic Entity Linking on Long Narratives with Collaborative Memorisation and Prompt Optimisation", Lixing Zhu, Jun Wang, Yulan He. COLING 2025, pp. 11334-11347, Abu Dhabi (aclanthology 2025.coling-main.751). No arXiv id found: a search engine associated arXiv 2407.04020 with it; I fetched that page and it is a different paper (LLMAEL), so do not cite it. [PUB]
- **Contributes** (Secs 3.1-3.3, 4-5): lower LLM tags entities per chapter/8,192-token chunk; upper LLM links them to a memory, carried as a "Prompt Cache" (JSON cluster dict) or "Conversation Memo" (history). Algorithm 1 REWINDS the document (maxRewind=2) so a pronoun met before its proper noun can be re-linked on the second scan, "inherits the memory of the previous scan". APO (AutoPrompt) tunes prompts against labels with GPT-4 Turbo as ranker. Table 2 (LitBank 90/10 docs; WhoLink = 401 NarrativeQA "who" questions): LitBank NER 98.4, coref 81.5 vs Mixtral-8x7B 77.4, GPT-3.5 75.3, LCA-LLM 80.2; WhoLink coref 78.2. Ablation (Table 3): cache +2.4, memo +1.6, APO about +1.0 on LitBank; without the LLM ranker 79.3.
- **Artifact and licence**: github.com/somethingx1202/LlmLink, `LICENSE` = "GNU GENERAL PUBLIC LICENSE Version 3". README describes "small utilities" and a wrapper that calls the OpenAI API (needs a key); no weights. Original model Mixtral-8x7B (does not fit 8 GB without offload).
- **Touches**: only `eval/baseline_b.py` (already a loose reimplementation). Not the product path.
- **Product value**: none directly: EchoTales' gazetteer + evidence resolver is already a memory with 0 resolution calls (FINAL_EVIDENCE_TABLE C6: B3 recall 78.9% vs 4.6% for the LLMLINK-style baseline, silver, surface-trivial range). GPL-3.0 makes code reuse in a closed product a problem; reimplementing from the paper is fine. APO and GPT-4 Turbo are paid: rejected under the no-paid-services rule.
- **Paper value**: ablation baseline. A faithful variant gives one clean experiment: rewind ON vs OFF under the renaming control, i.e. how much of the "gain" is future information. That is a use of the donor as the foil for the premature-resolution metric, not a novelty claim.
- **Integration form**: baseline-only.
- **Cost**: 1-2 days to add rewind + descriptions + cache/memo switch to `baseline_b.py`; compute is O(mentions) calls (existing run: 43 extractor + 134 linker calls, 434 s for ch1-10 on qwen2.5:7b).
- **Evidence needed and available**: needed = fidelity audit of Baseline B vs the paper (list in Limits) so the table does not call it LlmLink unqualified. Available = paper numbers on public-domain/widely read texts (case studies are Treasure Island and Tom Sawyer); metric is their own NER/coref F1, not CoNLL ("MUC, B3, CEAF ... will result in low precision"), so NOT comparable with EchoTales' CoNLL numbers.
- **Limits**: authors: extra tokens, prompt engineering, lower layer gets no signal from the upper layer, rewind timing preset. Mine: Correction to prior notes: it is not prefix-only, rewind is built in; memory is explicit, not a leakage control; no check for LLM prior exposure on the very famous books used (0 sweep hits); 10 test documents; Baseline B differs from LlmLink in per-mention linking, no rewind, no APO, 7B model.
- **Decision**: baseline-only. Label current Baseline B "LLMLINK-style, reduced" everywhere.
- **Test**: rewind ON/OFF x renamed/unrenamed contexts on the reader-view items; a large ON-OFF gap shows memory-based linking uses future information.

## 4. KoCoNovel
- **Source**: "KoCoNovel: Annotated Dataset of Character Coreference in Korean Novels", Kyuhee Kim, Surin Lee, Sangah Lee (Seoul National Univ.). arXiv 2404.01140 (v1 1 Apr 2024, v2 11 Apr 2024, comment "12 pages"). Venue: UNVERIFIED; the arXiv page lists no journal-ref and the repo's BibTeX is `@misc` arXiv-only. Earlier notes say LREC-COLING 2024; I could not confirm it. [PUB]
- **Contributes** (Secs 2.1, 3, 4, 5.4, 6, App. C): 50 Korean works (Wikisource, public domain), 178,928 tokens, 19,030 mentions, 19 annotators (3 per work). Annotators "reviewed coreference relations sequentially ... instructed to record any changes ... resulting from developments within the story"; post-processing then split the data into Reader and Omniscient versions (x Separate/Overlapped). The two views differ only in 5 works (App. C Table 12: IDs 0, 13, 16, 36, 49; reveals such as "the protagonist's father is Director Jo"). 24% of mentions are single common nouns, kinship 9.2% and titles 3.1% (Table 9): same phenomenon as EchoTales' relational deictics. IAA: average MUC 94.53. Experiments (Sec 6, Table 11): BERT-base coref on the Omniscient & Separate version only; KoCoNovel-trained beats NIKL-trained.
- **Artifact and licence**: github.com/storidient/KoCoNovel, `LICENSE` and README = "Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)"; data in CoNLL and JSONL; README (2025-02) adds speaker annotations. No model weights.
- **Touches**: no code. The annotation protocol (sequential reading, change log, two views, kinship/title guideline, Sec 4.3 generic vs specific) informs the human item set for `data/gold/` and the hard-case relabelling (W1). Data itself is Korean and unusable for the English-translated RI/LOTM.
- **Product value**: none. **Paper value**: it PRE-EMPTS "reader-view vs omniscient-view labels" as a novelty (related work, cite it). Its reader view is not chapter-indexed and nobody tested a model on it.
- **Integration form**: baseline-only for data (not usable); protocol reuse is annotation process.
- **Cost**: protocol reuse costs only annotator time. Pilot of 60 items x 2 humans, about 2-3 days; IAA reported against their 94.53 MUC for context only.
- **Evidence needed and available**: needed = whether reader labels at chapter t differ from omniscient on EchoTales' own items (they differ in 5/50 works here; unknown for xianxia). Available = Korean public-domain data only.
- **Limits**: authors state none in a Limitations section (none found); mine: non-expert annotators; reader view derived in post-processing, the sequence of reveal points is not reported as data in the paper (UNVERIFIED in the released files); no leakage control (0 hits); different language and register; "novels" vs "short stories" wording is inconsistent inside the paper (Sec 5.2 says "50 full-length Korean short stories").
- **Decision**: adapt (annotation protocol only); reject the data.
- **Test**: the pilot above shows reader != omniscient on at least some EchoTales hard cases; if never, C3 (reader-view item set) is not worth building.

## 5. FantasyCoref
- **Source**: "FantasyCoref: Coreference Resolution on Fantasy Literature Through Omniscient Writer's Point of View", Sooyoun Han, Sumin Seo, Minji Kang, Jongin Kim, Nayoung Choi, Min Song, Jinho D. Choi. CRAC 2021 (4th Workshop on Computational Models of Reference, Anaphora and Coreference), pp. 24-35, Punta Cana, 10-11 Nov 2021; aclanthology 2021.crac-1.3. [PUB]
- **Contributes** (Secs 2.2, 3.2, 4.4, 5, App. A): 211 Grimm tales + 3 fantasy texts (Aladdin, Ali Baba, first chapters of Alice), 367,891 tokens, all Gutenberg. Four guideline categories: Asymmetry of Knowledge (deception/disguise, mistaking, secret, plot-twist; "In these cases, we follow the omniscient writer's point of view"), Changes in Entities (a transformed entity "retains identity" if same identity through the story), Foretelling/Wishes, Lexical Variations. 36.4% of Grimm stories have an asymmetry case vs 2.0% in OntoNotes samples. IAA 87% averaged F1. SpanBERT fine-tuning: +2.59 / +3.06 Avg-F1 over the OntoNotes model (71.27 -> 73.86; 73.82 -> 76.88); genre-specific errors 12.5% of errors before fine-tuning.
- **Artifact and licence**: github.com/emorynlp/FantasyCoref (default branch `master`): README and `data/` only, NO LICENSE file; GitHub reports no licence. Source texts are Project Gutenberg; annotation licence UNVERIFIED (treat as all-rights-reserved until stated).
- **Touches**: no code. Guidelines inform the disguise/body-change categories of the hard-case set (body_change 8, disguise 1, reveal 7) and the identity-continuity rule (`persona`, `Self` vs persona, non-negotiable 3). Note Changes in Entities (one entity through transformation) is the opposite of EchoTales' Self/Persona split for body changes: annotation conventions must be mapped, not copied.
- **Product value**: none. **Paper value**: none for novelty; cite for "the reader/omniscient gap is a known annotation problem" (Intro Snow White example, Sec 2.2, App. A "King Thrushbeard": annotated "with the knowledge after reading through all the text").
- **Integration form**: baseline-only (reference); no adapter.
- **Cost**: reading only; 0.5 day to map its four categories onto the EchoTales taxonomy.
- **Evidence needed and available**: none needed for adoption. Their numbers: coref on short fairy tales, OntoNotes-trained SpanBERT, not comparable.
- **Limits**: authors: best result 76.88%, "room for improvement"; EE higher-order inference memory-limited on long docs. Mine: omniscient-only labels so a system scored on it is rewarded for premature resolution; famous short tales (memorisation risk) with no control (0 sweep hits); fairy-tale register far from serial web novels.
- **Decision**: baseline-only (guideline reference).
- **Test**: n/a; usable as a checklist: every hard-case category must say which view (reader or omniscient) its gold follows.

## 6. LitBank coreference
- **Source**: "An Annotated Dataset of Coreference in English Literature", David Bamman, Olivia Lewke, Anya Mansoor. LREC 2020, pp. 44-54, Marseille 11-16 May 2020 (aclanthology 2020.lrec-1.6; README cites arXiv 1912.01140). [PUB]
- **Contributes** (Secs 4.2.5, 5, 6): 100 works, 210,532 tokens, 29,103 mentions, ACE types incl. PER/FAC/LOC/GPE/ORG/VEH, singletons annotated, ~2,100-word excerpts. Sec 4.2.5 "Revelation of identity": annotated "from the perspective of the textual reality, rather than from the reader's state of knowledge at the moment of encountering the mention", i.e. whole-text view (convict = Pip's benefactor). Table 3 gold-mention 10-fold: LitBank-trained 79.3 vs OntoNotes-trained 72.9; with predicted mentions about 68.1 (Sec 6.2.2).
- **Artifact and licence**: github.com/dbamman/litbank README: "LitBank is licensed under a Creative Commons Attribution 4.0 International License" (so CC BY 4.0). Correction: the "CC-BY-NC" on page 1 of the PDF is the proceedings' (ELRA) licence, not the dataset's.
- **Touches**: already integrated: `eval/litbank.py`, `scripts/eval/litbank_eval.py`, results `data/eval/litbank_results.json`.
- **Product value**: the only human-keyed anchor in the repo. **Paper value**: ablation baseline / external anchor (exists). **Integration form**: baseline-only.
- **Cost**: done; re-running per new system is minutes. **Evidence needed and available**: add Maverick-OntoNotes, BookNLP on the same person key and scoring so the table has comparators; currently only EchoTales' own row exists.
- **Limits**: authors' view is omniscient; includes NOM person mentions ("his room" style), a schema EchoTales excludes by design (89% of person key mentions are NOM/PRON). Mine: Gutenberg classics, plausibly memorised by qwen; excerpts are ~2k tokens so no long-range test.
- **Decision**: baseline-only (keep). **Test**: add comparator rows under identical exact-span scoring.

## 7. BookNLP
- **Source**: github.com/booknlp/booknlp (David Bamman and collaborators). No paper read; first-party README fetched in full. [README]
- **Contributes**: English pipeline: entity tagging, character name clustering ("Tom", "Tom Sawyer", "Mr. Sawyer" -> one id), coreference (trained on LitBank and PreCo), quote attribution, events. README table: coreference Avg F1 76.4 small / 79.0 big. README: "Accurate coreference at the scale of a book-length document is still an open research problem ... tends to erroneously conflate multiple distinct entities into one"; by default common entities may not corefer to named entities (`pronominalCorefOnly`). Gender priors from ~15K Gutenberg works. The prior notes' wording is now verified from the raw README.
- **Artifact and licence**: GitHub licence API: MIT License (code). Model-weight licence UNVERIFIED. Big model targets GPU; BookCoref reports 6.9 GB peak on a 4090.
- **Touches**: eval only. **Product value**: none (English-only, name clustering is exactly the clustering non-negotiable 1 forbids). **Paper value**: ablation baseline (the reviewer-expected tool; BookCoref gives its whole-book CoNLL 42.2 on 3 canonical books).
- **Integration form**: baseline-only. **Cost**: 1-2 days to run on RI/LOTM chapters and LitBank with a name-level scorer; 6.9 GB peak is tight beside other GPU jobs on 8 GB.
- **Evidence needed and available**: needed = BookNLP on the LitBank person key and on the human-verified hard cases (no published number on translated web fiction: confirmed negative in earlier searches, bounded).
- **Limits**: English, trained on LitBank/PreCo; cannot be retrained on new data (BookCoref footnote 10); clustering-based. **Decision**: baseline-only. **Test**: report its name-level F1 and hard-case recall next to EchoTales; it should score near zero on title transfer.

---
## Corrections to the brief and to earlier notes
1. LlmLink is not prefix-only: Algorithm 1 rewinds at least once and the second pass inherits the whole first-pass memory. Notes B called its chunked processing "prefix-like": retracted. Also its Baseline B stand-in in this repo lacks rewind.
2. LitBank dataset licence is CC BY 4.0 (repo README); notes B quoted "CC-BY-NC" from the PDF page, which is the proceedings licence: retracted.
3. KoCoNovel venue "LREC-COLING 2024" is UNVERIFIED (arXiv-only citation); "reader view" exists for 5 of 50 works and was derived in post-processing of sequential annotation, never evaluated.
4. BookCoref: arXiv id is 2507.12075; the released repo has evaluation code only (no pipeline script found); licence is inconsistent between repo README (NC) and HF card (CC BY-SA 4.0). New: App. C concedes the LLM filter may answer from "parametric memory".
5. Maverick is not SOTA on every set: PreCo seq2seq is higher (88.5 vs 88.0). Brief's "SOTA also LitBank" holds only for the incremental variant (78.3).
6. Search-engine association of arXiv 2407.04020 with LlmLink is wrong (it is LLMAEL).

## Summary (10 lines)
1. Best adoption 1 (adapt): Maverick-LitBank as a research-only `MentionDetector` proposer for title and relational spans; NC licence blocks product use; gate on precision of added mentions.
2. Best adoption 2 (adapt): BookCoref's LLM yes/no mention verifier (+5.2 link precision, +5.8 CoNLL-F1 downstream in their ablation) on mentions added by non-gazetteer layers, tested under renaming because its own App. C admits parametric-memory answers.
3. Best adoption 3 (adapt): KoCoNovel's sequential-reading, change-log, two-view protocol and kinship/title guideline for the human reader-view item set; FantasyCoref's asymmetry-of-knowledge categories as a taxonomy checklist.
4. Baseline-only: LlmLink (GPL-3.0, paid APO, Mixtral; faithful rewind ON/OFF variant is the useful experiment), BookNLP (MIT code), LitBank (CC BY 4.0, already integrated), BookCoref gold, FantasyCoref (no licence stated). Reject: BookCoref window-expansion (omniscient), LlmLink APO, BookNLP clustering.
5. Overlap with EchoTales' claimed novelty: KoCoNovel pre-empts dual-view labels; BookCoref step 2 pre-empts "an LLM verifies the link" as C2, so C2 must be defined by the prefix-entailment constraint; LitBank 4.2.5, FantasyCoref 2.2 and KoCoNovel all document the reader/omniscient gap, so naming the problem is not novel.
6. No donor measures premature resolution, renaming-based leakage, or a prefix cutoff: all six papers returned 0 hits on leak/contamin/spoil/renam (BookCoref has one parametric-memory clause), so C1 survives this family, bounded by keyword sweeps and unread figures.
7. Detection is the binding constraint (58 of 88 silver cases, at most 55 real); no donor was run on EchoTales data, so none is adopted; the test for each is stated above.
8. Hardware: 8 GB 4060 confirmed; Maverick-large (~4 GB) and BookNLP (6.9 GB) must run as separate GPU passes, never beside qwen2.5:7b.
9. Retracted or corrected from earlier notes: LlmLink "prefix-like"; LitBank "CC-BY-NC"; KoCoNovel venue; BookCoref "no code" nuance and licence conflict (see section above).
10. Recommended order of work: fix `is_address` and measure (B6, no donor needed), then the Maverick-proposer test on human-verified hard cases, then the verifier, then the 60-item reader-view pilot.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/register_notes_F2.md -->
## Source: `docs/research/NOVELTY_REPORT/register_notes_F2.md`

# Integration Register, family F2: time, knowledge and state (2026-10-15)

Scope: seven donors, each judged adopt / adapt / baseline-only / reject for EchoTales. Merging a technique is engineering and never counts as paper novelty. Paper value is one of: novelty, ablation baseline, none.
Tags: [PUB] method and experiment sections read in the paper's own text (pdftotext, no code executed); [LEAD] abstract or snippet only (cannot be "adopt"); UNVERIFIED; INACCESSIBLE. [INSPECT] = I read the repo file; nothing was run. Downloads are in the scratchpad (`regF2`, `paA`, `paB`, `pa`).
Boundary: this file reports what I read. Nothing here is a measurement on EchoTales data. Every "Cost" figure is [INFER].

## Repo facts the decisions depend on [INSPECT]
- `interval.py::FuzzyInterval` has `from_lb/from_ub/to_lb/to_ub`; `contains()` returns CERTAIN/PLAUSIBLE/EXCLUDED. This is the TAC-KBP 4-tuple [T1 T2 T3 T4] with T1=from_lb, T2=from_ub, T3=to_lb, T4=to_ub. `open_ended()` is the "Chairman Smith" pattern [- t t -]. `since_before()` is the shape a late reveal takes.
- `state.py::StateResolver.state_of` composes story-time containment, `_visible_to_observer` (knowledge time, truth status, positional retraction) and timeline scoping, and returns Certainty. It does not return provenance.
- `title_holders.py::tenures` forces the first holder's start to 1.0 ("retroactive"). A closed holder's interval is stored crisp (`to_lb == to_ub == last_declared`) and the same call passes `last_evidence=` to `FuzzyInterval`, which has no such field (pydantic default ignores extras, so it is dropped silently; not run). Mentions in a handover gap are skipped by the linker, but the stored interval says EXCLUDED immediately after `last_declared`, so state_of and the linker disagree about the gap.
- Defect backlog items touched here: B4 wiki canon undated and applied after `state_of`; B5 `retract_alias_bindings` has no callers; B2 `resolve --chapters` ignored; A1/A2/A4 attribute, context and voice paths bypass `state_of`.

---
## 1. TAC-KBP temporal slot filling
- **Source:** (a) "Proposed Task Description for Knowledge-Base Population at TAC 2011", version 05/15/2011, TAC/NIST, no author line in the extracted text (the final pilot overview, Ji, Grishman, Dang 2011, was NOT read; cited only through the 2013 paper). (b) Mihai Surdeanu, "Overview of the TAC2013 Knowledge Base Population Evaluation: English Slot Filling and Temporal Slot Filling", TAC 2013; PDFs from `tsf11`/`tsf13` in `paB`. [PUB] for both documents as far as they go.
- **Contributes:** Sec. 3.4 (2011) and Sec. 2.2 (2013): a slot value gets a 4-tuple [T1 T2 T3 T4] = starts between T1 and T2, ends between T3 and T4; a hyphen is -inf/+inf. Examples from Table 2 (2011): "Chairman Smith" is [- d d -]; "named chairman two years ago" is [d-2y d-2y d-2y -]. Scoring: 2011 draft S = 1/4 sum c/(c+d_i) with separate constants for over-constraining and for vagueness (both tentatively 1 year); 2013 Q = 1/4 sum 1/(1+|t_i-g_i|), years. Slots include per:title and org:top_employees/members. Aggregation of per-sentence tuples: max of T1,T3 and min of T2,T4 (2011, Sec. 3.4.4). Stated non-representable: durations with no endpoint, disjoint multiple intervals.
- **Artifact and licence:** No code needed (metric is two formulas). Source collection and annotations are LDC (2013 text names LDC2013E45); LDC licence terms UNVERIFIED. Not usable as training data for fiction anyway.
- **Touches:** `core/interval.py` (mapping only); `resolve/title_holders.py::tenures` and the AliasBinding intervals it writes; a new scorer under `eval/` (pipeline), no core change.
- **Product value:** Medium for one concrete fix: store closed tenures as T1=previous holder's last declaration, T2=this holder's first declaration, T3=this holder's last declaration, T4=next holder's first declaration, so the handover gap is PLAUSIBLE rather than EXCLUDED. Also drop the dead `last_evidence=` argument.
- **Paper value:** Ablation baseline only. The metric is prior art. The 2013 baseline DCT-WITHIN ("valid at the document date", <-inf, d, d, +inf>) is the natural trivial baseline for tenure inference ("valid at each declaration chapter").
- **Integration form:** Isolated adapter (a scorer plus a tuple import/export), not a core change.
- **Cost:** [INFER] 2-3 engineering days for scorer and gap fix; annotation is the real cost: no human tenure gold exists, and the tenure count per novel is small (tens), so one annotator pass is hours.
- **Evidence needed/available:** Needed: human tenure tuples for title holders on RI (and ideally one more novel), then Q for current `tenures` vs the gap-aware version vs DCT-WITHIN. Authors' numbers (2013, news text, 201 scored queries): best system MS MLI 33.15, DCT-WITHIN baseline 19.10, LDC annotators 68.84 (Table 7); only 2 of 5 systems beat the baseline (3 of 4 in 2011); residence slots harder than employment slots.
- **Limits:** Authors: several relations are not expressible (see above); 2011 draft says durations are read "literally exact". Mine: scoring in years is meaningless without a unit change (chapters are not uniform time); both infinities have undefined distance, so Q needs a rule for -inf vs -inf; news-wire domain, no disclosure axis, no identity merge. EchoTales' "since chapter 1" choice is a stronger commitment than the tuple evidence ([- first_decl ... -]) supports and would be penalised as over-constraining.
- **Decision: ADAPT** (representation and metric only).
- **Test:** On a human-labelled tenure set, gap-aware tuples score higher Q than the current crisp intervals and than DCT-WITHIN, with the retroactive-start rule evaluated separately as its own ablation. Failing that, keep the current form.

## 2. TimeChara
- **Source:** Jaewoo Ahn, Taehyun Lee, Junyoung Lim, Jin-Hwa Kim, Sangdoo Yun, Hwaran Lee, Gunhee Kim, "TimeChara: Evaluating Point-in-Time Character Hallucination of Role-Playing Large Language Models", arXiv 2405.18027v1, 28 May 2024; Findings of ACL 2024 (venue confirmed by the repo README, which says "ACL 2024 Findings"). [PUB] Secs. 3, 4, 5, App. H.
- **Contributes:** Sec. 3: 14 characters from 4 English series, 219 time points, 10,895 interview-style instances in four types (future, past-absence, past-presence, past-only) plus fake-based questions; GPT-4 Turbo judge given spatiotemporal labels. Sec. 4 Narrative-Experts: a Temporal Expert (LLM names the scene's book and chapter, labels the question past or future) and a Spatial Expert (was the character present), each injecting a hint into the role-play prompt. Sec. 5: baselines include RAG and RAG-cutoff (retrieval limited to events before the character's time point). Table 5 (600 sampled instances), GPT-4 Turbo, future-type column as I read it from the text "all baselines at 51% or below": zero-shot 46.5, RAG-cutoff 50.0, Narrative-Experts 92.5, Narrative-Experts+RAG-cutoff 93.0.
- **Artifact and licence:** Code https://github.com/ahnjaewoo/timechara, GitHub API licence MIT. Data https://huggingface.co/datasets/ahnpersie/timechara, licence tag cc-by-nc-4.0; README: "TimeChara should only be used for non-commercial research". Only the Harry Potter creation path is released; needs OpenAI API (paid).
- **Touches:** Nothing in product. At most a leakage probe in `scripts/eval/` (premature-resolution experiment from C1).
- **Product value:** None. Role-play hallucination, not alias linking; no state to compile.
- **Paper value:** Ablation baseline / motivating premise only. Direct evidence (Sec. 3, 5.4) that LLMs hold famous books parametrically and that cutting off retrieval does not stop leakage (RAG-cutoff 50.0 on future type). Also App. H.5: the Temporal Expert's past/future call itself "rely[s] on parametric memories", which is useless on a novel the model does not know and redundant when the chapter position is an input.
- **Integration form:** Baseline-only (a prompt-level temporal-expert condition in a future leakage probe).
- **Cost:** [INFER] 0.5-1 day prompt port; paid judge calls are excluded by the no-paid-service rule; a local judge is unvalidated.
- **Evidence needed/available:** Authors' numbers are on 4 famous English series with GPT-4-class models and a GPT-4 judge. None on translated serials or on identity.
- **Limits:** Authors: English only; judge cost; Narrative-Experts latency/cost (Limitations). Mine: judge is an LLM (no human agreement quoted in the sections I read); leakage is exploited, never isolated by renaming; characters are famous.
- **Decision: BASELINE-ONLY.**
- **Test:** In the C1 leakage probe, a Temporal-Expert-style "is this alias linkable at chapter c" prompt as one arm; it justifies nothing unless it reduces premature links versus plain chapter filtering on renamed text.

## 3. Narrative World Model (NWM)
- **Source:** Mohammad Saifullah, Thomas Kornmaier, Taaha Kazi, Vasu Sharma, Aditya Sanjiv Kanade, Aanand Kumar Yadav (PocketFM), "Narrative World Model: Narratology-Grounded Writer Memory for Long-Form Fiction", arXiv 2607.05577v1, 6 Jul 2026, "Preprint. Under review". [PUB] Secs. 3, 4.1, 5, 8, App.
- **Contributes:** Sec. 3.1 causal publish flow: M_n = Publish(C_n, M_{n-1}), retrieval only uses updates through chapter n; republishing an edited chapter invalidates downstream edges. Sec. 3.2 typed records stamped with source chapter and evidence span; scene records hold event order and reveal order as separate fields; "focalized observer" and "reader knowledge" slots. Sec. 3.3 edges carry validity interval; "as of chapter n" selects the latest valid edge. Sec. 3.5 retrieval restricted to source chapter <= n, BM25+dense RRF, one-hop expansion. Sec. 5: private multi-hop (176 items) NWM Graph Retrieval 0.898 vs Graphiti 0.574 (McNemar 64 to 7); public 576 items 0.625 vs 0.516, public multi-hop 0.709 vs 0.582 with p = 0.054 (underpowered).
- **Artifact and licence:** No repo. "Code and Data Availability": public harness reproducible on Gutenberg; the private corpus, benchmark and "production Narrative World Model backend are proprietary and are withheld". Licence: none (nothing released).
- **Touches:** Concepts map to `Store` (event/reveal order = story/discourse axes), `state_of`, `world/context.py::story_context`. The chapter-edit invalidation idea would map to the missing retraction writer (B5).
- **Product value:** Low. EchoTales already has separate story/discourse axes. The only transferable idea is dependency-based invalidation on a corrected chapter, which the repo lacks; I read one paragraph on it, not an algorithm.
- **Paper value:** Ablation baseline (reported gain of a reveal-aware typed memory over Graphiti on QA). Not a novelty source, and it overlaps the claimed disclosure-aware state.
- **Integration form:** Baseline-only (design reference). Reimplementing needs unreleased components.
- **Cost:** [INFER] reimplementation of the baseline arm: multi-day plus paid extraction (they used Sonnet 4.5 and an Opus 4.8 answerer).
- **Evidence needed/available:** Authors' numbers are QA accuracy of writer memory on Gutenberg and private books, token-coverage scorer. Nothing on identity.
- **Limits:** Authors (Sec. 8): within-NWM controls show stripping the type labels, and re-embedding the graph untyped, leave accuracy unchanged (App. H), so "narratological typing" is not shown to be the lever; the lever is decomposition plus query-conditioned retrieval; the benchmark is "narratology-tilted by design"; automatic token-coverage scoring. Mine: no leakage or memorisation control (checked in prior notes and my greps); no alias task; closed-source.
- **Decision: BASELINE-ONLY.**
- **Test:** None for adoption. If cited as a baseline, state that the comparison is QA, not identity.

## 4. NarraWorld ("Shared Worlds, Private Minds")
- **Source:** Qiuyu Tian, Haojie Yin et al. (Southeast Univ., Beijing Zhongguancun Academy, ZhuiWen Technology and others), arXiv 2609.32401v1, 26 Sep 2026; no venue in the text. [PUB] Secs. 2.1-2.4, 3, App. A.1-A.2; the Appendix G limitations body did not survive text extraction and is not quoted.
- **Contributes:** Sec. 2.1 four views projected from one evidence-grounded graph: W (world), B[c] (per-character belief), D (developments: open/advanced/blocked/resolved), H (hypothetical branches). Sec. 2.2 update: link entities, add events and state changes with validity periods preserved, record each character's access (observation, communication, inference), update developments. App. A.1: an alias stage "links aliases to existing entities when the evidence supports the match", append-only store, "a state change closes the previous validity interval". Sec. 2.4 admissible view first (time, disclosure, branch), then retrieval. Results (Table 1) ConStory-Bench CED 0.185 vs Graphiti 0.385; LoCoMo: exposing H lowers Overall Main 0.614 to 0.570 (task-conditioned view).
- **Artifact and licence:** Code "will be released in anonymized form for review and made publicly available upon publication" (Ethics/reproducibility paragraph). No repo, no licence: UNVERIFIED/not released.
- **Touches:** `world/context.py::story_context` (filter by `state_of` first, retrieve second; matrix row 7), `core/readset.py` provenance, observer observations (EVOLUTION 4.80).
- **Product value:** Low-medium as a design confirmation: "admissible view, then retrieve" is already what A2 asks for; EchoTales needs wiring, not this paper. The belief view B[c] is the same idea as EchoTales' observer observations.
- **Paper value:** None for a novelty claim (it states the premature-disclosure aim and has an alias stage). Not a useful baseline either: its tasks are writing quality and role-play.
- **Integration form:** Baseline-only / design reference.
- **Cost:** [INFER] nothing to integrate; reimplementation not justified.
- **Evidence needed/available:** Authors' numbers are writing-consistency measures on English benchmarks; no identity or disclosure metric.
- **Limits:** Premature disclosure is a design aim, never measured (Sec. 2.4 example only); alias linking unevaluated and not conditioned on reveal time; no leakage or renaming control; code unreleased; LLM-generated stories and LLM judges in parts of the evaluation (details not fully read).
- **Decision: BASELINE-ONLY** (cite as related work).
- **Test:** The `story_context`-through-`state_of` fix is justified by a fixture where an observer must not see a fact (matrix row 7), not by this paper.

## 5. E2RAG / ChronoQA
- **Source:** Ze Yu Zhang, Zitao Li, Yaliang Li, Bolin Ding, Bryan Kian Hsiang Low (NUS, Alibaba), "Respecting Temporal-Causal Consistency: Entity-Event Knowledge Graphs for Retrieval-Augmented Generation", arXiv 2506.05939v1, 6 Jun 2025; EACL 2026 per a search snippet [LEAD for venue]. [PUB] method, Sec. 5, limitations.
- **Contributes:** Method: keep every entity mention as its own node ("Hermione in Chapter 9 versus Miss Granger in Chapter 16" are distinct), separate entity and event vertex sets joined by a bipartite edge when the entity name occurs in the event description; query-time cue extraction, seed retrieval, one-hop expansion, re-rank. Evaluation: ChronoQA 497 QA over 9 stories (paper), three LLM judges, 1-10 rubric. Table 3: E2RAG (comb. extraction) 7.126, LightRAG hybrid 6.880, GraphRAG local 6.800, vanilla RAG 6.602, RQ-RAG 3.514.
- **Artifact and licence:** Dataset https://huggingface.co/datasets/zy113/ChronoQA, README licence cc-by-nc-sa-4.0; the card now says 1,028 QA over 18 public-domain stories, which differs from the 497/9 in the paper I read (version drift; I used the paper's numbers). I found no code link in the paper text (grep for release/GitHub): UNVERIFIED.
- **Touches:** Conceptually the no-merge arm of identity resolution (`resolve/`); `world/context.py` retrieval.
- **Product value:** None as an adoption. Never merging gives zero premature merges by construction and no coreference.
- **Paper value:** Ablation baseline: a "mention-level graph, no resolution" arm brackets the premature-resolution/recall trade-off from the safe end.
- **Integration form:** Baseline-only.
- **Cost:** [INFER] 1 day to emit a mention-level arm; no LLM needed for the arm itself.
- **Evidence needed/available:** Needed: the same reader-view items scored for recall under no-merge. Available: authors' score differences between the top E2RAG variant and LightRAG hybrid are 0.25 on a 10-point LLM-judge scale; I found no significance test, interval or seed variance in the text.
- **Limits:** Authors: gains limited to documents with temporal/causal structure. Mine: LLM-generated questions and LLM judges; Gutenberg books heavily memorised, no closed-book or renamed control; retrieval QA, not identity; the chronological facet is passage order, not reader disclosure.
- **Decision: BASELINE-ONLY.**
- **Test:** In the human-labelled item set, report premature-resolution rate and recall for (no-merge, current resolver, evidence-gated); no-merge is the floor on one and the ceiling on the other.

## 6. EvolvTrip (verified: NOT a trip or retrieval work)
- **Lead correction:** "EvolvTrip" is a character theory-of-mind paper. It is in the character-knowledge field, not out of field. The repo's own `docs/paper/RELATED_WORK_FINAL.md` already cites it as "EvolvTrip / LitCharToM (Yang et al.; arXiv 2506.13641)".
- **Source:** Bohao Yang, Hainiu Xu, Jinhua Du, Ze Li, Yulan He, Chenghua Lin, "EvolvTrip: Enhancing Literary Character Understanding with Temporal Theory-of-Mind Graphs", arXiv 2506.13641v1 [cs.CL], 16 Jun 2025; no venue in the text. [PUB] Secs. 3.3, 3.4, 4, 5.1-5.3, Limitations.
- **Contributes:** LitCharToM: 2,539 multiple-choice questions on belief, emotion, intention, desire from 20 Gutenberg books (CoSER). GPT-4o extracts perspective-aware triples (BelievesAbout, DesiresFor, FeelsTowards, IntendsTo) per plot segment, restricted to what the character could observe; each triple is tagged with the plot number, carrying earlier mental states forward and updating on contradiction; 40% of triples human-verified. Adding triples to the prompt improves accuracy, e.g. extended context DS-R1-Distill-Qwen-14B 56.25 to 61.08 and InternLM3-8B 53.21 to 57.38; fine-tuning on 5 held-out books gives Qwen3-8B 54.25 to 58.12.
- **Artifact and licence:** https://github.com/Bernard-Yang/EvolvTrip (GitHub API: no licence file, contents are README and assets only); data on HF `yangbh217/EvolvTrip`, no licence tag returned. Licence UNVERIFIED (treat as unlicensed).
- **Touches:** Observer facts: `state.py::_visible_to_observer` and the observations table (EVOLUTION 4.80). It models mental states, not identity.
- **Product value:** None (GPT-4o extraction, mental-state triples, no identity facts).
- **Paper value:** None to ablation baseline. It is already in the repo's related-work table; EchoTales' difference stands as identity facts per observer.
- **Integration form:** Baseline-only.
- **Cost:** [INFER] none worth spending.
- **Evidence needed/available:** Authors' gains are modest (2-5 points) on multiple choice built from LLM-written questions.
- **Limits:** Authors (Limitations): GPT-4o extraction bias; four dimensions only, no recursive beliefs; the triple format simplifies ambiguity. Mine: time is a plot index, no intervals, no discourse-vs-story separation; no leakage or memorisation control found (keyword grep on leak/memoriz/contamin/pretrain returned nothing relevant); no identity or alias.
- **Decision: BASELINE-ONLY** (cite only).
- **Test:** None.

## 7. Zep / Graphiti
- **Source:** Preston Rasmussen, Pavlo Paliychuk, Travis Beauvais, Jack Ryan, Daniel Chalef (Zep AI), "Zep: A Temporal Knowledge Graph Architecture for Agent Memory", arXiv 2501.13956v1 [cs.CL], 20 Jan 2025; no venue. Title confirmed against the PDF. [PUB] Secs. 2.1-2.2.3, 4.2-4.3, 5.
- **Contributes:** Sec. 2.1 "bi-temporal": T (event chronology) and T' (transactional order of ingestion). Sec. 2.2.1 entity resolution: embed name, cosine plus full-text search for candidates, then an LLM duplicate decision. Sec. 2.2.3: four timestamps per edge (t'_created, t'_expired, t_valid, t_invalid); an LLM compares a new edge against related edges and sets the old edge's t_invalid to the new edge's t_valid; "Graphiti consistently prioritizes new information". Results: DMR 94.8% vs MemGPT 93.4% (gpt-4-turbo; the paper's own full-conversation baseline gets 94.4%); LongMemEval gpt-4o 71.2% vs 60.2% full context, temporal-reasoning 62.4% vs 45.1%, single-session-assistant 17.7% worse.
- **Artifact and licence:** https://github.com/getzep/graphiti, GitHub API licence Apache-2.0 (LICENSE file, "Apache License"); README lists Neo4j 5.26, FalkorDB, Neptune backends and Kuzu "deprecated". Repo active (last push 2026-10-15).
- **Touches:** Would replace nothing. As a baseline: a scratch DB copy fed chapter episodes (cf. NWM Sec. 3.6, which did exactly this) compared on prefix-of-book queries.
- **Product value:** Reject as a store. It would swap the SQLite bitemporal store and the deterministic resolver for LLM merges, contradicting non-negotiables 1 and 9 and the "preserve existing architecture" charter. Two ideas are already in the repo.
- **Paper value:** Ablation baseline. Also a correction to wording: Zep's second axis (T') is database ingestion time, not reader-disclosure time. If chapters are ingested in order the two coincide, which is a degenerate disclosure axis, not an observer-indexed one. EchoTales' "bitemporal" claim must say what its second axis means (reader or observer knowledge position) and not rely on the shared word.
- **Integration form:** Baseline-only.
- **Cost:** [INFER] LLM extraction over the chapters plus a graph database; local-model extraction quality unknown (NWM reports a cheaper extractor gave a sparser graph, 3,600 to 2,226 edges, with unchanged accuracy).
- **Evidence needed/available:** Authors' numbers are conversation memory, not novels; the DMR baseline already scores 94.4%.
- **Limits:** Authors: DMR is small and weak; assistant-side questions got worse; they say future work. Mine: invalidation is interval-end (set t_invalid), not retraction, so a later correction cannot keep the earlier belief visible, the exact distinction non-negotiable 5 protects; "prioritize new information" is a recency rule with no reader-view notion.
- **Decision: BASELINE-ONLY.**
- **Test:** On the same prefix queries, Graphiti arm vs `state_of`; Graphiti loses on any item where an earlier belief must stay visible after a later retraction.

---
## Product angle: shared narrative-state policy and dated wiki canon
No donor supplies this. It is engineering (B4, A1, A2, A4), and the existing primitives suffice: a wiki trait grounded at chapter g becomes a fact with `learned_at_pos = g` and `FuzzyInterval.since_before(g)`; `canon_for` should then go through `state_of`, and the wiki file hash should enter the state digest. Nearest conceptual support: NarraWorld Sec. 2.4 and NWM Sec. 3.5, both "restrict to the admissible view, then retrieve". No paper value.

## Summary (10 lines)
1. Best adoption 1: TAC-KBP 4-tuple and gap-aware tenure intervals for `title_holders.tenures` (adapt, cheap, closes a handover-gap inconsistency and a dead `last_evidence=` argument).
2. Best adoption 2: the "admissible view first, then retrieve" principle (NarraWorld Sec. 2.4, NWM Sec. 3.5) as an integration rule for `story_context` and all render paths; engineering, not a paper claim.
3. Best adoption 3: the DCT-WITHIN trivial baseline plus Q-style scoring for any tenure or state evaluation (ablation baseline, no code to import).
4. Everything else is baseline-only: TimeChara (MIT code, CC-BY-NC data, paid judge), NWM (proprietary, nothing released), NarraWorld (code unreleased), E2RAG/ChronoQA (cc-by-nc-sa, no-merge floor), EvolvTrip (no licence), Zep/Graphiti (Apache-2.0, but LLM merges contradict precision-first resolution).
5. Overlaps with the planned title-holder temporal model: TAC-KBP covers it directly (per:title and org:top_employees are its slots; the repo's first-tenure-from-chapter-1 rule is stronger than the tuple evidence allows). Graphiti covers edge-validity invalidation.
6. Overlaps with claimed novelty: NWM (reveal vs event order, chapter-safe cutoff), NarraWorld (premature-disclosure aim, alias stage, validity intervals), EvolvTrip (per-character temporal mental states). None measures premature alias resolution.
7. Correction to the brief: EvolvTrip is a literary-character theory-of-mind graph (arXiv 2506.13641), in field and already cited in `RELATED_WORK_FINAL.md`; it is not a trip or retrieval work.
8. Correction to earlier prior-art wording: "bitemporal" in Zep is ingestion time (T') versus event time (T); EchoTales' disclosure axis is reader knowledge position, so shared vocabulary must not be read as shared design. Also ChronoQA on the Hugging Face card now has 1,028 QA/18 stories, not the 497/9 in the paper, and TimeChara's venue is now confirmed by the repo README.
9. No earlier prior-art claim is retracted. One softening: "NarraWorld alias linking is unevaluated" rests on App. A.1 and the results I read; its Appendix G limitations text was not extractable. NWM's own controls (Sec. 8) say its type labels are not the lever, which weakens it as a "typing helps" precedent.
10. Nothing here is a measurement on EchoTales data; every adoption waits on human tenure labels (none exist) and the reader-view item set.

---

<!-- merged-from: docs/research/NOVELTY_REPORT/register_notes_F3.md -->
## Source: `docs/research/NOVELTY_REPORT/register_notes_F3.md`

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

---

<!-- merged-from: docs/research/NOVELTY_REPORT/register_notes_F4.md -->
## Source: `docs/research/NOVELTY_REPORT/register_notes_F4.md`

# Integration Register notes, family F4 (reliability of links)

Scope: selective prediction, calibration, abstention, bootstrapping drift. Date 2026-10-15. Nothing in the repo was modified; no code from any download was run. Papers were fetched as PDFs to `scratchpad/regF4` and read with `pdftotext` only. Tags: [PUB] method + experiment sections of the paper itself read; [LEAD] snippet only; [REPO] read in this repo; [INFER] my deduction, not stated by a source. Merging a technique is engineering, never paper novelty.

## 0. What the repo actually does (read first, because it changes every verdict)

- **R1 [REPO] The "Mondrian gate" is a standard one-sided gate, not Mondrian.** `resolve/gate.py::ConformalGate.calibrate` takes one pooled list of `(probability, is_correct)` and sets `link_threshold = incorrect[int(alpha*n)]` (incorrect probabilities sorted descending). No `alias_type` appears in `gate.py`. `docs/HANDOFF.md:884` says "Mondrian/class-conditional conformal by alias_type: not started"; `docs/private/IP/invention_disclosure.md:345` says "No Mondrian conformal calibration ... not built". `docs/design/architecture.md` Section 6 describes it as design. `CHIMERA_PLAN.md:15` still says "conformal gate (Mondrian by alias type)", which is wrong against the code.
- **R2 [REPO+INFER] What the gate bounds is a false-positive rate, not link precision.** Thresholding at a high quantile of the scores of *incorrect* pairs bounds P(score >= threshold | pair is incorrect) near alpha. The docstring claims "at most alpha of auto-linked decisions are wrong", which is P(incorrect | linked), a different quantity (selective risk). With base rate pi of correct pairs and recall TPR, precision = pi*TPR / (pi*TPR + (1-pi)*alpha) [INFER, Bayes], so it moves with pi even when the FPR is held fixed.
- **R3 [REPO] The gate does not govern the links that exist.** `gate.decide` returns on FORCE_LINK / BLOCK before the threshold is consulted. `SCORER_DIAGNOSIS.md` Sec. 3: gold candidates are 101 FORCE_LINK, 2 BLOCK, 0 SCORE; Sec. 2: max reachable scorer probability 0.550 vs 0.80. So any conformal guarantee covers only the scorer region, which has zero labelled examples and links nothing today. Pre-filter links (the real ones) carry no coverage statement at all.
- **R4 [REPO] Calibration pairs are not independent.** `eval/calibrate.py` records every `(mention, candidate)` pair; 15,796 cached pairs vs 103 silver mentions with a retrievable gold candidate (SCORER_DIAGNOSIS Sec. 1). Pairs sharing a mention are dependent. Labels are SILVER (LLM-derived, no IAA). `held_out_coverage` already does a chronological calibrate-early / test-late split, a ready-made probe for drift.
- **R5 [REPO] Feedback loop.** `runner.py::resolve_novel` runs `sweep_contradictions` then `retry_deferred` every `window_size` chapters. Links add gazetteer surfaces that later force-link (docstring of `sweep_contradictions`: "The gazetteer compounds wrong decisions as readily as right ones"). `retry_deferred` re-scores queued cases against grown profiles with the same gate, and (defect B1, `CHIMERA_DEFECT_BACKLOG.md`) counts a case "recovered" without calling `_apply_link`. The sweep only returns entities to the queue ("the detector proposes").
- **R6 [REPO] Exchangeability violations, enumerated.** (a) Time/compounding: `architecture.md` states the violation outright and says it is "stated as a limitation". (b) Feedback: earlier links change `profiles`, the gazetteer and retrieval, hence later evidence vectors, and wrong earlier links change P(correct | evidence) itself (a gazetteer hit is evidence only if the earlier link was right). That breaks the "P(Y|X) unchanged" premise of feedback covariate shift, not just the covariate premise [INFER]. (c) Within-mention dependence of pairs (R4). (d) Calibration set mixes pre-filter-decided pairs with the (empty) scorer region (R3). (e) `retry_deferred` cases are selected because they were uncertain.

## 1. Fannjiang et al. 2022 (feedback covariate shift)
- **Source**: Fannjiang, Bates, Angelopoulos, Listgarten, Jordan, "Conformal prediction under feedback covariate shift for biomolecular design", PNAS 119(43):e2204569119, Oct 2022 (venue/date from search result, not from the PDF); arXiv:2202.03613 (v1 8 Feb 2022; v5 3 Apr 2025 read). Title of v1 was "Conformal prediction for the design problem" (search result). [PUB]
- **What it contributes** (Sec. 2.1-2.5, Sec. 3 read): defines FCS: training data i.i.d.; the test input is drawn from a distribution induced by the training data; P(Y|X) unchanged. Full-conformal set with weights = normalised likelihood ratios v(X;D)=p~_{X;D}(X)/p_X(X), recomputed per leave-one-out dataset and candidate label (Eq. 3-4); Theorem 1 gives >= 1-alpha under absolute continuity. Split-conformal variant (Sec. 2.5): freeze the model on a training split, then it is ordinary covariate shift. Experiments (Sec. 3.1): ridge regression on 8,192-sequence fluorescence data, n in {96,192,384}, T=2000 trials, empirical coverage <= 0.924 vs the 0.9 target; standard-covariate-shift weights over-cover.
- **Artifact and licence**: github.com/clarafy/conformal-for-design; GitHub licence API returned "MIT License" (file `LICENSE`, "Copyright (c) 2022 Clara Wong-Fannjiang"). Code not run.
- **Touches**: nothing today. Conceptually `gate.py::ConformalGate.calibrate` and the window loop in `runner.py::resolve_novel` (snapshot of scorer+gazetteer per window).
- **Product value**: low now. Needs a known test-input density ratio; EchoTales' "test distribution" is generated by retrieval over a mutating gazetteer, with no tractable density.
- **Paper value**: none as a method (borrowing). Its formalisation of feedback gives *language* for the limitation, nothing more.
- **Integration form**: baseline-only (a reviewer-facing citation; optionally the split-conformal reading as a design rule: freeze per window, calibrate on that window's labels, apply to the next).
- **Cost**: full conformal needs (n+1) refits per test point (Sec. 2.4); split variant is cheap. Implementation of split variant: ~1 engineer-day. [INFER]
- **Evidence needed / available**: needs labels in the scorer region (none, R3) and per-window labels (silver only).
- **Limits (stated)**: needs P(Y|X) fixed and densities known or estimable; the guarantee is marginal, not conditional (Sec. 1.1); covers regression sets, not an abstain/link decision. **(Found)** EchoTales violates the fixed-P(Y|X) premise through R6(b); the theorem therefore does not transfer.
- **Decision: baseline-only.** Cite as the closest formal treatment of feedback. Do not implement.
- **Test that would justify upgrading**: show on RI chapters that the labelled error rate among scored pairs, for a gate frozen at window w, differs between window w+1 and a window-w holdout by more than a bootstrap CI; only then is a shift correction worth building.

## 2. Murphy & Curran 2007 / Curran, Murphy & Scholz 2007 (mutual exclusion bootstrapping)
- **Source**: (A) Murphy, Curran, "Experiments in Mutual Exclusion Bootstrapping", Proc. Australasian Language Technology Workshop (ALTA) 2007, pp. 66-74, aclanthology U07-1011. [PUB] (B) Curran, Murphy, Scholz, "Minimising semantic drift with mutual exclusion bootstrapping", Proc. PACLING 2007, pp. 172-180 (bibliographic data only from (A)'s reference list). **(B) INACCESSIBLE**: no PDF found; everything about it is second-hand via (A). The brief's "Murphy & Curran 2007" is (A).
- **What it contributes** (Sec. 2, Algorithm 1, Sec. 4-6 of A read): run one bootstrapping loop per semantic class in parallel; any term or context claimed by more than one class in an iteration is discarded (hard mutual exclusion); optional "stop classes" to bound drift. Experiments on Google Web 1T 5-grams, BBN entity types (unigram/bigram) and WordNet lexical files: MEB robust to class order (10 permutations, mean 75, sd 3.0), stop classes help, accuracy collapses when left context is cut (about 30 points), best at 5-20 contexts per iteration, more seeds help; poor on diffuse classes ("cognition").
- **Artifact and licence**: no code in the paper. Text licence per ACL Anthology: pre-2016 materials CC BY-NC-SA 3.0 (page states it). Data: Web 1T, LDC2006T13, proprietary; not used.
- **Touches**: `mentions/induce.py` (lexicon induction, `min_support`), gazetteer admission and `gazetteer.py::AMBIGUITY_BLOCKLIST`, `resolve/contradiction.py`. Idea: a surface form (alias) claimed by two entities in the same window is not admitted to the exact-match automaton for either.
- **Product value**: plausible and cheap: a "one alias, one entity" admission rule is a precision-first guard on the compounding gazetteer (non-negotiables 8 and 9). But EchoTales deliberately has legitimately shared surfaces (titles, "master", transferable titles); a hard exclusion would delete exactly the hard phenomenon (architecture.md "Lexicon confidence tiers" makes this argument for single-sample terms) [INFER].
- **Paper value**: none for novelty; a possible ablation baseline for a "gazetteer admission guard" only. It gives no reliability statement about links.
- **Integration form**: config switch behind an off-by-default flag, or baseline-only. Not adapter.
- **Cost**: small code (<~100 lines) [INFER]; a measurement needs labels for admitted aliases.
- **Evidence needed / available**: none on EchoTales. `CHIMERA_DEFECT_BACKLOG.md` A9 already flags unmeasured blocklist effects. No human-labelled alias-admission set exists.
- **Limits (stated by authors)**: the exclusivity assumption "is clearly false" and "far from realistic"; discards many viable contexts, "a significant problem" when classes overlap or data are small; order-sensitive (sd 3.0). **(Found)** their setting is unlabelled corpus-scale (Web 1T); EchoTales is one volume, labelled by silver, so drift cannot be measured there without labels. The paper measures precision-at-n of lists, not per-link correctness.
- **Decision: baseline-only** (admission-guard ablation arm, not adopted).
- **Test**: on RI chapters 1-50 vs 51-100 with the silver set, count gazetteer-admitted surfaces that link to two or more distinct gold identities, then run the resolver with the guard on/off and compare false-link counts (silver, labelled as such). Falsifier: guard changes false links by less than its CI, or removes any hard-case title link (hardcases n=88: 23 correct links must survive).

## 3. Vovk 2013, conditional / label-conditional inductive conformal predictors (the "Mondrian" construction)
- **Source**: Vovk, "Conditional validity of inductive conformal predictors", Machine Learning 92:349-376, 2013 (venue from search result); arXiv:1209.2673 (v2, 24 Sep 2012). [PUB: Sec. 2-4, Sec. 6-8 read]. The name "Mondrian" does not occur in this text (grep count 0); the original Mondrian-named sources (Vovk et al. 2003/2005 book) were **not read** [LEAD/UNVERIFIED]; here the construction is the "conditional ICP with an m-taxonomy".
- **What it contributes** (Sec. 4 Eq. 10, Prop. 3; Sec. 7): p-values are computed only against calibration examples of the same category kappa (Eq. 10); Prop. 3: if examples are exchangeable, P(error | category) <= epsilon for every category. "Label conditional ICP" = taxonomy K(.,(x,y)) := y. Sec. 7: the spam example, "classify x as spam iff f(x) exceeds the k-th largest of the calibration scores of true email, k = floor((n0+1)eps)", bounds P(mistaking email for spam) <= eps. Sec. 5: object-conditional validity is impossible in a non-trivial way. Experiments (Sec. 6): UCI spam, split 2602/999/1000.
- **Artifact and licence**: R programs at alrw.net referenced in the paper, **UNVERIFIED** (not fetched, licence unknown).
- **Touches**: `gate.py::ConformalGate.calibrate` (would take a `category` key = `alias_type` from `mentions/alias_type.py`: RIGID_NAME / TRANSFERABLE_TITLE / EPITHET / RELATIONAL_DEICTIC), `eval/calibrate.py::held_out_coverage`.
- **Product value**: the existing `calibrate` is already Vovk's one-sided label-conditional rule with the "incorrect" label as the class [INFER from R1 + Sec. 7]; this block says what it does and does not guarantee (FPR given incorrect, not precision). Per-category thresholds are a genuine, cheap change. Category sizes are the risk: Vovk's conclusion advises categories not below about 100 examples; alias-type cells will be far smaller on one volume.
- **Paper value**: none (standard). A *measured* per-alias-type coverage table on real hard cases would be a result, not a method.
- **Integration form**: config switch (per-category thresholds with fallback to pooled when a cell is below a minimum size).
- **Cost**: ~100-150 lines (project's own estimate, invention_disclosure.md:345); blocked on labels.
- **Evidence needed / available**: labelled scorer-region pairs per alias type; available: 0 (R3).
- **Limits (stated)**: needs exchangeability within category; object-conditional validity unattainable; guarantee is unconditional on the calibration draw unless the PAC form (Prop. 2a/2b) is used. **(Found)** violated by R6(a)-(e).
- **Decision: adapt** (engineering: implement per-`alias_type` calibration with a minimum-cell fallback and an honest note that it bounds FPR). Not novelty.
- **Test**: with silver labels, chronological split (calibrate chapters <= k, test > k): per-alias-type false-link rate among incorrect pairs vs alpha. Falsifier: in-cell empirical rate exceeds alpha by more than a Clopper-Pearson interval in at least one cell with n >= 30. Report cells with n < 30 as not evaluable.

## 4. Angelopoulos & Bates, "A gentle introduction to conformal prediction and distribution-free uncertainty quantification"
- **Source**: arXiv:2107.07511, Angelopoulos, Bates (PDF dated 8 Dec 2022). Tutorial; publication venue not stated in text read (a Foundations and Trends monograph per my memory, UNVERIFIED). [PUB: Sec. 1-2 (Thm 1), 3 (marginal vs conditional), 4.1, 4.2, 4.5, 4.6, 5.3 read]
- **What it contributes**: Thm 1: i.i.d. calibration + test point gives P(Y in C) >= 1-alpha, marginally, for any score. Sec. 4.1-4.2 give group-/class-balanced coverage by calibrating per group/class (attributed to Vovk). Sec. 4.5: weighted conformal under covariate shift needs the known likelihood ratio, test independent of calibration. Sec. 4.6, Thm 4: with discounting weights, P(cover) >= 1-alpha - 2*sum(w~_i * TV_i), where TV_i is the total-variation distance of point i from the test point. Sec. 5.3: sliding-window weights restore coverage on temperature time series (unweighted under-covers before a change point).
- **Artifact and licence**: github.com/aangelopoulos/conformal-prediction, GitHub licence API "MIT License". Not run.
- **Touches**: `gate.py` (design reference); Sec. 4.6 weights are a candidate "recent windows weigh more" calibration for the gate.
- **Product value**: a recency-weighted calibration quantile is a cheap mitigation of R6(a); the TV_i term is never known, so no formal guarantee [authors' own caveat, Sec. 4.6].
- **Paper value**: none (reference/ablation arm: pooled vs per-type vs recency-weighted).
- **Integration form**: config switch (weights = 1{window >= w-K}); baseline-only otherwise.
- **Cost**: ~30 lines for weighted quantile [INFER].
- **Evidence needed / available**: labelled early/late windows; silver only.
- **Limits (stated)**: marginal not conditional; i.i.d./exchangeable required; Thm 4 needs TV_i. **(Found)** TV_i between EchoTales windows is unobservable; the feedback effect (R6b) is not slow drift, so Sec. 4.6 does not cover it.
- **Decision: baseline-only** (cited as the exchangeability statement and the recency-weighting ablation).
- **Test**: weighted vs unweighted calibration on the chronological split; falsifier: no difference in late-window false-link rate beyond CI.

## 5. Geifman & El-Yaniv 2017 (selective classification with guaranteed risk)
- **Source**: "Selective Classification for Deep Neural Networks", arXiv:1705.08500v2 (1 Jun 2017). NeurIPS 2017 is my memory, not stated in the text read: UNVERIFIED venue. [PUB: Sec. 2-3 incl. Alg. 1 SGR, Lemma 3.1, Thm 3.2; Sec. 5 tables read]
- **What it contributes**: defines coverage phi(f,g)=E[g] and selective risk R(f,g)=E[loss*g]/phi (Eq. 1), the error *among accepted examples*. SGR: sort a labelled i.i.d. sample by confidence, binary search the threshold, bound the true selective risk with the exact binomial tail bound B*(r_hat, delta/k, accepted) (Lemma 3.1, Gascuel-Caraux); Thm 3.2: with prob >= 1-delta over the sample, R(f,g) <= the bound, uniformly over the log2(m) iterations. Experiments: VGG on CIFAR-10/100/ImageNet with softmax-response confidence; e.g. a 2% top-5 ImageNet error guaranteed with prob 99.9% at about 60% coverage (abstract).
- **Artifact and licence**: **UNVERIFIED** (no repository linked in the text I read; not searched).
- **Touches**: `gate.py::ConformalGate` (threshold selection), `eval/calibrate.py`.
- **Product value**: this is the guarantee the gate's docstring *claims* ("at most alpha of auto-linked decisions are wrong"): a PAC bound on precision of the accepted set. Directly relevant to R2. It also gives an honest way to report "link precision >= 1-r* with prob 1-delta" for the scorer region once labels exist.
- **Paper value**: ablation baseline (SGR is the standard comparator for any abstention-at-target-precision rule). Not novelty.
- **Integration form**: isolated adapter (an offline threshold-selection function applied to labelled `(probability, is_correct)`), config switch to use it instead of the quantile rule.
- **Cost**: ~40 lines plus a binomial tail solve [INFER].
- **Evidence needed / available**: m i.i.d. labelled scorer-region pairs; none exist (R3). Bound is vacuous at small m: with m=30 even zero errors gives a loose bound [INFER from Eq. 4].
- **Limits (stated)**: requires i.i.d. sample; footnote 1: if the confidence function is badly skewed the achieved risk can be far from target (loose, not wrong). **(Found)** i.i.d. violated by R4 and R6; the scorer's confidence is bounded at 0.550 so any threshold is vacuous today.
- **Decision: adapt** as the *reporting and selection* rule for a future labelled scorer region, as an isolated adapter; baseline for any claim.
- **Test**: on silver pairs split by chapter, compute SGR bound at target r*=0.05, delta=0.1 on the early split; measure realised selective risk on the late split. Falsifier: realised risk above the bound in the late split (that would quantify the drift violation).

## 6. Angelopoulos, Bates, Fisch, Lei, Schuster, "Conformal Risk Control"
- **Source**: arXiv:2208.02814 (v4, 13 Jun 2025 read). Venue (ICLR 2024) from memory, UNVERIFIED. [PUB: Sec. 1-2 (Thm 1, 2), 3.1 FNR, 4.1 read]
- **What it contributes**: for any non-increasing bounded loss L_i(lambda) on exchangeable data, lambda_hat = inf{lambda : n/(n+1) R_n(lambda) + B/(n+1) <= alpha} gives E[L_{n+1}(lambda_hat)] <= alpha (Thm 1); a lower bound alpha - 2B/(n+1) when i.i.d. (Thm 2). Non-monotone losses are not controlled (Prop. 1). Sec. 4.1: known bounded likelihood-ratio weights extend this to covariate shift. Experiments: FNR in tumour segmentation, graph distance, token F1.
- **Artifact and licence**: github.com/aangelopoulos/conformal-risk, GitHub licence API "MIT License". Not run.
- **Touches**: `gate.py::decide`. The loss 1{linked and wrong} is non-increasing in a stricter threshold, so Thm 1 applies as a *per-mention* expected false-link bound [INFER]. It is not selective risk (not conditioned on linking), so it is weaker than Geifman for "precision of links" but is finite-sample, expectation-based and needs no PAC slack.
- **Product value**: a clean way to set the threshold for a stated per-mention false-link budget; also lets a DEFER cost be explicit. Moot until the scorer region has labels.
- **Paper value**: none; ablation arm.
- **Integration form**: isolated adapter (same shape as Sec. 5) or baseline-only.
- **Cost**: ~20 lines [INFER].
- **Evidence needed / available**: as Sec. 5; none.
- **Limits (stated)**: exchangeability; monotone bounded loss; shift extension needs a known bounded weight. **(Found)** same R6 violations; 1{linked and wrong} counts only the scorer region unless pre-filter links are scored through the same loss.
- **Decision: baseline-only.**
- **Test**: as Sec. 5 with realised false-link-per-mention on the late split vs alpha.

## 7. Gibbs & Candes, "Adaptive Conformal Inference Under Distribution Shift"
- **Source**: arXiv:2106.00170v3 (28 Oct 2021, "Preprint. Under review"). NeurIPS 2021 from memory, UNVERIFIED. [PUB: Sec. 1-2.1, 2.2, 4.1 (Prop. 4.1), 7 read]
- **What it contributes**: online update alpha_{t+1} = alpha_t + gamma(alpha - err_t) (Eq. 2), err_t = 1{Y_t not in C_t(alpha_t)}. Prop. 4.1: for all T, |(1/T) sum err_t - alpha| <= (max(alpha_1,1-alpha_1)+gamma)/(T*gamma), with probability one, **with no assumption on the data process**. Experiments: market volatility on 12 stocks, plus a second domain; the non-adaptive method under-covers after shifts.
- **Artifact and licence**: github.com/isgibbs/AdaptiveConformal exists; licence endpoint returned 404 "Not Found" (no LICENSE file detected). **UNVERIFIED / treat as unlicensed.**
- **Touches**: `runner.py::resolve_group` window loop and `gate.alpha`: per-window nudge of the target level from audited outcomes.
- **Product value**: the only donor here that survives non-exchangeability *in the long-run average* sense. But it needs Y_t revealed after every step (authors' Sec. 7: "specific to cases where Y_t is revealed at each time point"), which EchoTales does not have; labels arrive only from review/audit.
- **Paper value**: possible *component* of a Track P candidate (Sec. 8) if driven by randomly audited auto-links; as a standalone it is prior art.
- **Integration form**: isolated adapter, fed by `corrections.py` confirmations or a random audit sample.
- **Cost**: ~10 lines of update + the audit labels (the real cost: human minutes).
- **Evidence needed / available**: a stream of audited link outcomes in chapter order; none.
- **Limits (stated)**: needs per-step feedback; theory in 4.2 limited to a fixed quantile function and one data model; gamma choice open; guarantee is time-average, not per-window or per-type. **(Found)** error events from delayed or sparse audits make the telescoping bound loose by the missing steps [INFER]; and it bounds average miscoverage, not link precision.
- **Decision: baseline-only** now; **adapt** only inside the Sec. 8 candidate.
- **Test**: simulate (SYNTHETIC) a stream whose error rate steps up at chapter 100 and audit 10% of links; compare static-alpha vs ACI time-average false-link rate. Falsifier: no gain at 10% audit rate.

## 8. Could a calibrated-abstention link rule be a Track P contribution?
Honest answer: **not as stated**. Per-type conformal calibration (Sec. 3), selective-risk bounds (Sec. 5), risk control (Sec. 6) and online adaptation (Sec. 7) all exist; Fellegi-Sunter-style two-cutoff match / possible-match / non-match rules driven by error-rate bounds are classical record linkage [LEAD: search snippet only, not read]. A search for conformal methods in entity resolution/coreference found nothing directly, but that is a snippet-level negative; PASC (arXiv:2605.18812, multi-stage NLP pipelines) appeared and was **not read** [LEAD]. Novelty is unverified until it is.
Only a narrow difference is conceivable: **a link-precision (selective-risk) bound that stays honest under the pipeline's own feedback**, i.e. (i) bound precision per alias type over the *whole* decision stack including pre-filter links, not only scorer outputs; (ii) re-estimate it each window from a random audit of auto-links (ACI-style, because plain conformal is invalid under R6b); (iii) evaluate it with a disclosure-time-faithful sequential protocol so the guarantee is checked in the order a reader meets the text. The donors give none of (i)-(iii) for a self-referential gazetteer.
**Test with baseline and falsifier** (silver or synthetic, labelled so): *Synthetic stream* with a known entity table, a gazetteer that grows from the system's own links, and an injected wrong-link rate (SYNTHETIC; no real-novel claim). Arms: A pooled static gate (current), B per-type static (Sec. 3), C SGR once on early windows (Sec. 5), D windowed re-estimate from a 10% audit (Sec. 8). Metric: per-window, per-type precision of auto-links and abstention rate. Falsifier: D is not better than B in late-window precision at equal abstention by more than a bootstrap CI, or B/C already hold within CI (then no contribution). Silver replication on RI chapters 1-100 only to check direction, not to claim accuracy; real claims need human labels (CHIMERA adjudication package).

## 9. Summary (10 lines)
1. The current gate is a one-sided label-conditional rule (Vovk 2013 Sec. 7): it bounds FPR given an incorrect pair, not precision of links; the "Mondrian by alias_type" gate is not implemented (HANDOFF:884).
2. Real links are FORCE_LINK; the gate never sees them, and the scorer region has 0 labels, so no coverage statement applies to any actual link today.
3. Fannjiang (MIT code): baseline-only; its premise (P(Y|X) fixed) fails in EchoTales because earlier links change what evidence means.
4. Murphy & Curran ALTA 2007 [PUB]: baseline-only; the PACLING paper is INACCESSIBLE. Hard exclusivity conflicts with transferable titles; no code, no EchoTales evidence.
5. Vovk 2013: adapt (per-alias-type calibration with a min-cell fallback), engineering only; cell sizes will be small.
6. Geifman and El-Yaniv: adapt as an isolated threshold/reporting adapter; it is the guarantee the docstring claims (selective risk), but needs i.i.d. labels that do not exist. Artifact UNVERIFIED.
7. A&B tutorial and Conformal Risk Control (both MIT): baseline-only; Gibbs & Candes ACI: baseline-only now (no licence file; needs per-step labels).
8. Exchangeability is violated five ways (time, feedback, pair dependence, mixed pre-filter/scorer calibration, selected retry cases), so every guarantee here is nominal.
9. A calibrated-abstention rule is defensible as Track P only in the narrow form of Sec. 8 (precision over the whole stack, audit-fed re-estimation, sequential protocol), and only if it beats per-type static calibration on a synthetic stream and survives a prior-art read of PASC and Fellegi-Sunter literature.
10. A reviewer would attack: "this is Vovk plus ACI", silver labels, n of the scorer region = 0, the Mondrian claim (R1) shipped ahead of code, and `retry_deferred` counting un-written "recoveries" (B1).

---

<!-- merged-from: docs/research/NOVELTY_REPORT/register_notes_F5.md -->
## Source: `docs/research/NOVELTY_REPORT/register_notes_F5.md`

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

---

<!-- merged-from: docs/research/NOVELTY_REPORT/register_notes_F6.md -->
## Source: `docs/research/NOVELTY_REPORT/register_notes_F6.md`

# Integration Register notes, family F6: information-flow control (IFC) for LLM context (2026-10-15)

Scope rule: only "what enters each LLM prompt, with provenance and labels, and blocking disallowed flows" is in scope. General agent security
(prompt-injection defence, tool-call authorisation, exfiltration through egress tools) is OUT-OF-FIELD for EchoTales and is named as such below.
Track S (product-leaning): merging any of this is ENGINEERING and carries no paper novelty unless stated.
Method: PDFs fetched from arxiv.org/pdf/<id> into a scratch dir, `pdftotext -layout` only, nothing executed. Licences quoted from the GitHub API
`license` field (repo metadata, not a LICENSE file read). Tags: [PUB] method and experiment sections read in the paper text; [LEAD] snippet or abstract only.

## 0. What EchoTales already does (do not reinvent)

- `core/state.py::_visible_to_observer` is a per-fact visibility test on a (learned_at_pos, observer, retracted_at, truth_status) label: a fact is
  visible iff `learned_at_pos <= knowledge_pos` (or the observer's own `witnessed_at` for a character observer), not retracted before that position,
  and not FALSE. `observer_scope` gives characters no inheritance of reader knowledge. This IS a position/observer label check, at the graph read.
- `core/state.py::GenerationState` carries `allowed_facts`, `forbidden_facts`, `provenance_refs` (audit, not hashed) and `read_set` (hashed into the
  cache key). `core/readset.py::ReadSetRecorder`/`fact_ref` give stable string refs per fact.
- `core/disclosure.py::compile_minimal_disclosure` only NARROWS the `state_of` candidate set per `TaskSpec`; its stated invariant (tested in
  `core/tests/test_disclosure.py`) is `allowed_facts` is a subset of what `compile_generation_state` yields. Its only non-test caller is the
  experiment-only `render/plan_builder.py` (`use_mdc=True`).
- `core/readset.py::EpistemicLeakageValidator.validate(gen_state, text)` is a post-hoc casefold-substring scan of finished prompt text for
  `forbidden_facts`. Tested in `core/tests/test_state.py::TestGenerationStateAndValidator`. grep over `packages/` finds NO production caller.
- `pipeline/world/context.py::story_context` (director brief) filters `_facts_as_of` by chapter number only: `attr.learned_at_pos.chapter > chapter`.
  It does not go through `state_of`, so it has no observer axis, no retraction handling, no truth_status test (also CHIMERA_COMPONENT_MATRIX s.8).
- `conditioned_on` is a free `list[str]` on `PanelImage` (`render/panels.py:1027`), set from a pre-selection `conditioned` list while
  `engine.generate` runs with `reference_images=[]` (`panels.py:2808-2864`); CHIMERA_DEFECT_BACKLOG B3 records it still over-claims.

What an IFC-style check ADDS: (a) a label on every item at the point it is placed into a prompt, not only at graph read; (b) a refusal at the
prompt-builder boundary, so the guarantee covers paths that bypass `state_of` (story_context, wiki canon, free-text director context); (c) an
auditable invariant per generated artifact: "no context item with learned_at > position, or observer not in scope, was placed in this prompt", plus
a `conditioned_on` that is derived from the labelled items actually serialised, not asserted by the caller.
What it does NOT add: a defence against parametric leakage (the model remembering the novel); no label can stop that (see NOVELTY_REPORT prior-art A).

## Donor 1: FIDES, "Securing AI Agents with Information-Flow Control"

- **Source**: Costa, Koepf, Kolluri, Paverd, Russinovich, Salem, Tople, Wutschitz, Zanella-Beguelin (Microsoft). arXiv:2505.23643v2 [cs.CR], 3 Sep 2025
  (v1 29 May 2025). Brief's lead confirmed. No venue found. [PUB]
- **What it contributes** (s.4.1-4.3, s.5, s.7-8): labels from a lattice (confidentiality as authorised-reader sets, integrity trusted/untrusted;
  join = least upper bound) attached to every node of a tool result and to every message. Planning loop (Alg. 5-6) propagates labels
  conservatively: a model response gets the join of all labels in its context ("signifying the inability to precisely propagate labels through
  LLMs"). Policy check before a tool call: label of tool and each argument must be at or below a static policy label. s.5.1 `HIDE` swaps any node
  whose label exceeds the current context label for an opaque variable, so the prompt's label does not rise. s.8 on AgentDojo (949 attacks, gpt-4o):
  successful injections Basic 163 (156), FIDES 24 (23), FIDES with policy 1 (0); Task Completion Rate reported as "modest loss".
- **Artifact and licence**: github.com/microsoft/fides (tutorial per abstract); GitHub API: "MIT License", spdx MIT, last push 2025-05-30. Paper's
  eval code release UNVERIFIED (only the tutorial is claimed).
- **EchoTales component**: none today. Idea would land as a thin wrapper in the prompt-assembly path of `render/panels.py` (director call near
  `story_context`, `panels.py:2370`) and `world/context.py::StoryContext` items; label type reuses `fact_ref` + `DiscoursePosition`.
- **Product value**: low-moderate. The reusable part is the shape: label every context node, `HIDE` (drop and keep a reference) when the label exceeds
  the context level, and a pre-call policy `label <= bound`. EchoTales' lattice would be a total order on `DiscoursePosition` times observer scope,
  which is far simpler than FIDES' product lattice.
- **Paper value**: none for novelty (IFC labels on context are the donor's idea; position-as-label is a trivial instance). Possible ablation baseline:
  "conservative join" label propagation vs per-item label, relevant to the `conditioned_on` over-approximation.
- **Integration form**: baseline-only for the library; the idea itself becomes an isolated adapter (a `PromptItem(label, text)` builder). No dependency.
- **Cost**: reading cost only for the donor; adapter ~1-2 days with tests, no GPU, no API spend.
- **Evidence needed and available**: need a fixture graph with facts at chapters 3/9/20 and a position of 9; available in `core/tests` helpers
  (`make_self`, `bind_alias`). No EchoTales-side measurement needed to adopt the idea; none exists of leak rate through `story_context`.
- **Limits**: stated: policies enforced on tool calls only, so text-to-text attacks pass (s.8.1); labels must be supplied by trusted wrappers
  ("security guarantees ... only as good as the labels"); implicit flows not prevented. Found: the guarantee is about the labelled channel; it says
  nothing about what the model memorised, which is EchoTales' main leak (see prior-art A). Tool-call, egress and prompt-injection parts are OUT-OF-FIELD.
- **Decision**: baseline-only (the code); adapt the idea (see summary item 3). Not "adopt" because nothing is imported.
- **Test that would justify it**: on a fixture graph, assert for N random (position, observer) pairs that every item in the serialised director
  brief satisfies `label <= (position, observer)`, and that a deliberately planted chapter-20 fact is refused at position 9.

## Donor 2: Permissive Information-Flow Analysis for Large Language Models

- **Source**: Siddiqui, Gaonkar, Koepf, Krueger, Paverd, Salem, Tople, Wutschitz, Xia, Zanella-Beguelin. arXiv:2410.03055v3 [cs.LG], 14 Jan 2026;
  TMLR 10/2025. Not in the brief; found via FIDES s.9 (ref [29]). [PUB]
- **What it contributes** (s.2.2, s.3.1-3.2, Alg. 1, s.4-6): naive taint takes the join of all context labels as the output label. They instead
  search for the least-restrictive label L' whose sub-context `C|L'` yields an output with utility (negative perplexity) within lambda of the
  full-context output (Definition 1, "lambda-similar"), via a DAG search over labels below the full-context label; two propagators
  (prompt-based retrieval augmentation, kNN-LM) vs an introspection baseline. Results: more permissive label than baseline in >85% of cases
  (synthetic key-value and news-article datasets, s.5). Cost: extra LLM calls (s.3.5, s.6.2).
- **Artifact and licence**: no code link found in the paper text (keyword sweep for github/licen returns only LangChain). UNVERIFIED.
- **EchoTales component**: `render/panels.py` `conditioned_on` / `PanelImage`, `GenerationState.read_set` vs `provenance_refs`. The defect B3
  (provenance lists items that did not condition the generation) is the same over-approximation problem, in the opposite direction: here the
  list is too LARGE because it joins everything in scope, not because the model used it.
- **Product value**: low. Needs repeated LLM calls per panel to find the minimal sub-context; EchoTales' cheaper route is deterministic: provenance
  = exactly the items serialised into the prompt (what `compile_minimal_disclosure` already narrows to).
- **Paper value**: closest conceptual cousin of "minimal sufficient evidence"; relevant to the disclosure-minimisation claim as RELATED WORK, and its
  lambda-similar test is a possible ablation (does dropping an item change the output?). Not novel for EchoTales to adopt.
- **Integration form**: baseline-only (cited, not run).
- **Cost**: re-implementation ~1 week plus many LLM calls; not justified.
- **Evidence needed and available**: would need a utility metric for panels/director output; none defined. Unavailable.
- **Limits**: stated: more LLM calls; adversary can add distractors so the label never improves (s.6.2). Found: utility is perplexity of a fixed
  reference completion, which does not transfer to image prompts.
- **Decision**: baseline-only (cite as related work for `conditioned_on` semantics).
- **Test**: none to run; the deterministic alternative is tested under Donor 1.

## Donor 3: CaMeL, "Defeating Prompt Injections by Design"

- **Source**: Debenedetti, Shumailov, Fan, Hayes, Carlini, Fabian, Kern, Shi, Terzis, Tramer (Google, DeepMind, ETH). arXiv:2503.18813v2 [cs.CR],
  24 Jun 2025. Brief's lead confirmed. [PUB]
- **What it contributes** (s.3.1, s.5.2-5.4, s.6, s.7): a Privileged LLM writes restricted Python from the trusted query; a custom interpreter
  runs it, a Quarantined LLM parses untrusted data. Each value carries a capability tag (provenance: User, CaMeL, or a tool plus inner source; set of
  allowed readers). The interpreter keeps a dependency graph per variable (STRICT mode adds control-flow dependencies) and checks Python-function
  policies (Allowed/Denied with reason, Fig. 6) before each tool call. s.6: 77% of AgentDojo tasks solved with provable security vs 84% undefended.
  s.7 documents side channels (exceptions, timing, external resource).
- **Artifact and licence**: github.com/google-research/camel-prompt-injection; GitHub API: "Apache License 2.0", spdx Apache-2.0, last push 2025-06-20.
- **EchoTales component**: none; the transferable idea is per-value provenance tags plus a recorded dependency graph, i.e. what
  `ReadSetRecorder`/`fact_ref` already are for graph facts, and the "origin of displayed content can be traced" property (s.3.1 non-goals).
- **Product value**: low. The interpreter architecture (code-writing planner) is a different system; EchoTales' prompt assembly is deterministic
  code already, so the dual-LLM split buys nothing.
- **Paper value**: none for novelty. Ablation baseline: no.
- **Integration form**: reject as a dependency; cite for the capability/provenance vocabulary.
- **Cost**: adopting the interpreter is weeks and a redesign of render; not warranted.
- **Evidence needed and available**: n/a.
- **Limits**: stated: text-to-text attacks that do not change data flow are out of scope; "Data requires action" failure (s.6.1.2) where the planner
  cannot read data it must act on; side channels (s.7). Found: security is defined per tool call, not per prompt content.
- **Decision**: reject (as code); the provenance-tag idea is already covered by Donor 1's adapter. Prompt-injection and exfiltration defence is OUT-OF-FIELD.
- **Test**: none.

## Donor 4: RTBAS, "Defending LLM Agents Against Prompt Injection and Privacy Leakage"

- **Source**: Zhong, Chen, Wang, McCall, Titzer, Miller, Gibbons (CMU, Two Sigma). arXiv:2502.08966v2 [cs.CR], 14 Feb 2025. Not in the brief; named in
  FIDES s.9. [PUB for s.7-8 sections read; the lattice/proof parts skimmed]
- **What it contributes** (s.7, s.8): regions of the history carry integrity and confidentiality labels; a "dependency screener" decides which
  regions the next output depends on, so only those labels propagate (and unused regions are redacted). Two screeners: LM-as-judge on
  `<REGION_N>` markers, and an attention-feature LSTM (85% train, 81% test on 40 AgentDojo cases, Phi-3-Mini). Baselines Naive Tainting, Redact All,
  Tool Filter. Results (GPT-4o, AgentDojo, 629 security cases): blocks all attacks violating the policy; <1% (LM-judge) and 3% (attention) utility
  loss under attack, 7.4-10% without attack; Slack suite utility falls to 22-33%.
- **Artifact and licence**: no repository found (GitHub search for "rtbas" returned unrelated repos; paper text has no code link). UNVERIFIED.
- **EchoTales component**: same as Donor 2 (`conditioned_on` over-approximation). The "redact unused regions" step corresponds to
  `compile_minimal_disclosure` dropping unneeded facts.
- **Product value**: low; a judge/attention screener per panel is costly and unneeded when the prompt text is built by deterministic code from known
  items.
- **Paper value**: related work only.
- **Integration form**: baseline-only (cited).
- **Cost**: high (extra model passes, a trained classifier); no.
- **Evidence needed and available**: none.
- **Limits**: stated: "security guarantees ... only as good as the labels provided and the policies enforced"; one workspace case missed because
  user text labelled trusted contained an injection. Found: the screener is itself a probabilistic component, so the guarantee becomes
  probabilistic wherever it is used to drop a label.
- **Decision**: baseline-only.
- **Test**: none.

## Donor 5: Progent, "Securing AI Agents with Privilege Control"

- **Source**: Shi, He, Wang, Li, Wu, Guo, Song (UC Berkeley and others). arXiv:2504.11703v3 [cs.CR], 14 May 2026. Brief's lead confirmed. [PUB for
  abstract, s.8.1, s.9; policy-language sections skimmed only]
- **What it contributes**: a symbolic allow/forbid policy over tool names and arguments, LLM-generated from the task and updated at runtime; an SMT
  solver classifies each update as narrowing (auto) or expansion (needs approval), giving monotonic confinement. AgentDojo ASR 39.9% -> 1.0% (gpt-4o).
- **Artifact and licence**: github.com/sunblaze-ucb/progent; GitHub API: "MIT License", last push 2026-09-24.
- **EchoTales component**: none. It controls which ACTIONS an agent may take, not what content enters a prompt; EchoTales has no tool-calling agent in
  the render path.
- **Product value**: none for this field. **Paper value**: none.
- **Integration form**: reject (OUT-OF-FIELD: general agent security / privilege control).
- **Cost**: n/a. **Evidence needed**: n/a.
- **Limits**: stated: does not address text-to-text attacks (s.9 "Defense Scope"); text only, no multimodal.
- **Decision**: reject, out-of-field. **Test**: none.

## Novelty threats (position / time visibility labels for narratives)

- No IFC paper read here labels context by story position or reader knowledge. FIDES/CaMeL use trust and reader-set lattices; Siddiqui et al. mention
  timestamps only as an example of an infinite lattice (s.3.2). A narrative-specific position-and-observer label check is not pre-empted by these donors.
- Adjacent, LEAD only (abstracts read on arxiv.org/abs, methods not read): TEMPO arXiv:2605.18843 (Zhang, Stadie, 13 May 2026) and TimeSPEC
  arXiv:2602.17234 (Zhang, Chen, Stadie, 19 Feb 2026) enforce a pre-cutoff evidence rule for LLM backtesting (temporally filtered retrieval plus
  claim-level supervision / trained temporal discipline). This is the nearest "position-based visibility" prior art, in forecasting, not narrative. A
  search snippet also reports date-filtered retrieval alone still leaks (El Lahib et al., ACL 2026; UNVERIFIED, not opened). Treat "time-cutoff
  evidence filtering for LLM prompts" as NOT novel in general; EchoTales' narrower claim (observer-conditioned bitemporal `state_of` with retraction
  and witnessed-at) is not shown by any of these.
- StoRM (Guiding Neural Story Generation with Reader Models, Findings EMNLP 2022) [LEAD, snippet]: models the reader's beliefs as a graph, for
  planning, not for blocking prompt content.

## Summary (10 lines)

1. Worth building: one `PromptItem(text, ref, learned_at_pos, observer_scope)` builder that REFUSES any item whose label exceeds `(position, observer)` and
   returns `conditioned_on` as the refs of items actually serialised. Engineering, not a contribution.
2. Invariant test: for any (position, observer), `max(item.learned_at_pos for item in prompt_items) <= knowledge_pos` and every item is in
   `state_of(...).allowed_facts`; plant a chapter-20 fact and assert refusal at position 9 on a fixture graph; assert `conditioned_on == serialised refs`.
3. Overlap: `_visible_to_observer`, `GenerationState.allowed/forbidden/read_set` and `compile_minimal_disclosure` already enforce the label rule AT GRAPH READ;
   the new part is enforcement at the prompt boundary.
4. Gap it closes: `world/context.py::story_context` filters by chapter number only (no observer, retraction or truth_status) and bypasses `state_of`.
5. `EpistemicLeakageValidator` is a substring post-check with no production caller in `packages/`; wiring it is cheaper than any donor.
6. `conditioned_on` defect (B3): FIDES-style conservative join over-approximates; Siddiqui et al. confirm the problem but fix it with extra LLM calls. Fix it
   deterministically instead.
7. Decisions: FIDES baseline-only (idea adapted); Siddiqui baseline-only; CaMeL reject (idea covered); RTBAS baseline-only; Progent reject, out-of-field.
8. No donor labels by story position or reader knowledge; nearest prior art is LEAD-only: TEMPO 2605.18843 and TimeSPEC 2602.17234 (forecasting cutoff).
9. Corrections to the brief: FIDES id and authors confirmed (v2, 3 Sep 2025, MIT); CaMeL and Progent exist (Apache-2.0, MIT); Siddiqui (2410.03055) and RTBAS
   (2502.08966) are the better-fitting additions, the latter two have no verified code.
10. No label stops parametric leakage (model memory of the novel); this family cannot support any claim about that.
