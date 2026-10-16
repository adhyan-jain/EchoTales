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
