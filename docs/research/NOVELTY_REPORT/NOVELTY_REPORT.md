# EchoTales Novelty Report

**Status: DRAFT v1.8 (adds section 5.24, RF-E2E: a whole-volume LLM character card leaks the reveal through the input and a versioned card fixes it, both channels measured on one system; v1.7 added section 5.23, the pre-registered confirmatory run PD CONFIRM v2 on 68 events from 65 mostly obscure public-domain books with three open models: no gap on obscure books, fame contrast underpowered and not passed, E4/E5/E2/OLMo-link results; v1.6 added section 5.22, a post hoc dose-response over all 38 events: the leakage gap rises with how well the book is recognised; v1.5 added PD v6, the final pre-registered test on 7 fresh books: NOT SUPPORTED for the valid local models, replicated for Luna, with a pooled event-level view of all data in section 5.21; v1.4 added PD v5, the pre-registered cue-preserving rename test of the reviewer's main objection, verdict MEMORY SURVIVES (strong), section 5.20; v1.3 added section 5.19, a response to an external adversarial review: event-cluster intervals replace item-level intervals as the honest reading, the claim wording is narrowed, and the cue-loss objection is recorded as the main open risk; v1.2 added PD v4: a memory-free validity gate and a title-assisted memory probe, with a pre-registered re-evaluation of v2 and v3 giving SUPPORTED on both; v1.1 added PD v3, a pre-registered confirmatory test with verdict PARTIALLY SUPPORTED; v1.0 added PD v2 (repaired re-run, verdict INCONCLUSIVE), the engineering probes E1-E6 and a ranked novelty table 8b; v0.9 added the PD public-domain reveal benchmark and a novelty-points section; v0.8 added cross-novel replication of the audit and the renaming gate, the Track S adapters on branch `chimera/system-adapters`, the local Qwen replication M2Q, T4 v5 renaming validity, L2U unseen-text control, a gate-versus-engine diagnosis, M1 gate v2, M3, M3b and a prompt-boundary audit; L1 wording softened after the M0 reading), 2026-10-15. L1 (first LLM test of C1a and C1b) has run. Human verification of the real-novel labels is still pending, so every real-novel number, including every L1 number, is SILVER.**

**Label provenance, stated once and applying to every real-novel number below.** The reference labels for the real novel (Reverend Insanity, "RI") are **silver: drafted by a model, not verified by any human** (`data/gold/reverend-insanity-hardcases.jsonl`, `provenance: model`, `confirmed: false` on all 89 records). No human label exists yet. The only human-keyed number in this work is LitBank (an external dataset). The author's single-annotator human labels for the 72-item pilot arrive after this report is submitted; when they do, the pilot tables are re-run and model-versus-human agreement is reported as a finding (section 9). Every table is tagged **SILVER**, **SYNTHETIC (by construction)** or **NO LABELS (system-internal)**. Nothing here measures reader-view correctness.

Evidence tags: `[REPO]` read in the repository, `[INSPECT]` read by me in code, `[RAN]` produced by a command run this session, `[PUB]` read in the publication itself, `[LEAD]` seen only in a search snippet or abstract, `UNVERIFIED`.

---

## 0. Bottom line

**Novelty, redefined (2026-10-16 night; supersedes the ranking in 8a and 8b).** The paper is a methods-and-measurement paper on **reader-faithfulness**: the output of a position-aware reading assistant at chapter c may depend only on chapters up to c.
1. **Definition and guarantees.** A two-part contract (input channel, parameter channel), the observation that they compose and that passing one audit does not certify the other, and elementary, property-tested guarantees for the repairs (versioning by evidence horizon has zero divergence for any prefix-only derivation; hiding beats doing nothing only when fewer in-window prefixes already hold the final value; prefix-decided gates remove prominence leaks).
2. **Derivation look-ahead is a design defect, found and fixed on two systems (strongest).** On the deployed narrative graph: 6.0% of 685 character-cuts diverge, the versioned repair gives 0, naive hiding is worse (82 vs 23). On the generic whole-volume LLM character card (pre-registered, 54 reveal events): the card names the hidden identity before the reveal in 18.5% of events for 7 to 8B models and 23.1% for 24 to 32B models **under cipher names no model has seen**, against 1.2% and 1.9% for the versioned card (strict text rule: 24.6% and 21.1% vs 0%); every one of five models is positive; a second judge agrees on 97.8% of labels (kappa 0.88).
3. **Input and memory leaks separated on one system with one oracle.** At the reveal cut the memory-only leak is +2.5 points (7 to 8B) and +0.0 points (24 to 32B) while the build leak is about 20 points: for these books the pipeline, not the model, is the main risk.
4. **Premature resolution under prefix truncation (parameter channel).** A text-derived entitlement oracle, a renaming probe with a memory-free validity gate, and the finding that plain renaming validity checks are memory-assisted on famous books; the effect is large on famous books (exploratory, +26.0 points for a reference model) and bounded below about 5 points on obscure books (pre-registered, three 24 to 32B models).
**Not claimed:** fame dependence of memorisation (Chang et al. 2023), name replacement and pseudonymisation (Jiang and Ferraro), point-in-time correctness (feature stores), look-ahead bias as a concept (finance LLM work). Prior-art search was bounded; "to our knowledge" applies.


1. **What is shown.** A failure audit of the identity-resolution pipeline on a real novel, and a mechanism-level test on synthetic worlds. The audit findings are verified in the repository (sections 5 and 6).
2. **What is shown about the central idea, with its limits.** L1 (one model, `gpt-5.6-luna`, one serial, silver labels) gives a *weak, confounded* signal for C1a (the renaming gap may include renaming damage, not only memory; see section 5.4 caveat): on the 4 items with a repo-derived reveal chapter the model names the silver final identity from the prefix 4 of 4 times under original names and 0 of 4 under renamed names, and the renaming control is valid (30 of 30 agreement on plain controls). That primary comparison is **pre-registered as inconclusive** (n = 4). C1b as implemented **over-rejects**: it blocks all 4 premature answers but also drops control accuracy from 96.7% to 46.7%. A closed-book memorisation probe found **no** evidence of memory for this model (14 of 15 abstentions).
3. **Net novelty claim.** Still narrow: a precisely specified measurement design (reader-warranted versus final-truth identity, with leakage defined as the change under consistent renaming) for long translated web serials, now with a first pilot signal on one model and a reproducible audit. It is a pilot signal, not a demonstrated result. Section 8 rates it against the gate and the closest prior work.
4. **Public-domain benchmark (PD, section 5.14).** Pre-registered leakage test on seven famous public-domain novels with a text-derived oracle, a closed-book positive control and an unseen-text control: **verdict NOT SUPPORTED** (only `gpt-5.6-luna` passes the renaming-validity gate; gap +7.0 pts, CI [0.0, 16.3]). Positive results: the closed-book control shows memory in 4 of 5 models and renaming removes it (0 of 7); renaming validity itself fails for 4 of 5 models on real prose. The novelty points, with their evidence tier and weak spots, are in section 8a.
12. **Confirmatory run (5.23, pre-registered, 2026-10-16).** On 68 events from 65 Gutenberg books (32 EXPLICIT test events form the primary set; 78% low-fame) three open 24B to 32B models show **no premature-naming gap**: pooled A-B +0.1 points [-5.0, +5.2] (H1 not passed), A-B3 +5.7 [-1.3, +12.6] (H2 not passed), the closed-book control recovers the identity in only 2 of 68 events, so the sample holds little memory. The fame contrast (primary P1) is +7.6 [-1.4, +18.3], p = 0.060, not passed, minimum detectable 12.8 points; H3 Spearman +0.30 (raw p 0.041, Holm 0.145, not confirmed). Pseudonymisation halves premature naming (5.0% to 2.6%) at a 6.7 to 15.6 point accuracy cost (H5 not met). E5 recap spoilers: 0 detected (floor), E2 unseen stories: gaps about 0 (n = 17), OLMo training-data link: Spearman +0.13, p = 0.41 (null). The Claude arm stopped at 211 of 1,218 answers and is excluded. Net: the effect is established only as an exploratory result on famous books; the confirmatory run bounds it on obscure books.
13. **Second system, found and fixed (5.24, pre-registered).** RF-E2E (pre-registered, addenda 6 and 7, written before any card was read): on 54 confirmatory reveal events, a whole-volume LLM character card stamped at first mention names the hidden identity before the reveal in 18.5% of events under cipher names no model has seen (judge rule; strict text rule 24.6% of 19), against 1.2% for the versioned (prefix-built) card. Input-channel RF1 SUPPORTED on the primary text rule (+24.6 [+8.8, +42.1]) and SUPPORTED on the judge rule (+17.3 [+9.3, +26.5]); memory-only leak +2.5 [+0.0, +5.6]. Pseudonymise-and-map-back: prefix-card leak 3.7% to 3.1% (RF5 not evaluated: no memory leak to fix). Models: llama3.1:8b, mistral:7b-instruct, qwen2.5:7b; not run: none. Larger open models (mistral24, qwen32b, addendum 8): W-ren 23.1% vs P-ren 1.9%; memory-only leak +0.0 points.
11. **Dose-response (5.22, post hoc).** The per-event leakage gap rises with how many local models recognise the book: Luna's gap vs recognition Spearman +0.37 (p = 0.024, cross-family), the valid-local pool's +0.59 (p = 0.00015); the small models' gap is about zero below three recognising models and +40.9 points when all five recognise, which explains the PD v6 null.
10. **PD v6 final test and pooled view (5.21).** On 7 fresh books the pre-registered verdict is NOT SUPPORTED for the valid local models (gap -5.9 points [-14.8, 1.0]) but the reference model replicates (+16.7 [5.4, 28.6]); pooled over all 38 events the valid-local gap is +11.5 [4.5, 19.0] and Luna's is +26.0 [16.8, 36.0] (22 events positive against 1). The claim is narrowed to the strongest model and well-known books; the cross-model wording is withdrawn.
9. **Cue-preserving test (5.20).** Natural, gender- and name-type-matched pseudonyms for the cast and alias names restore plain-control accuracy to the original-text level but do not restore premature naming: gap original minus pseudonym +16.1 points [8.2, 25.0], recovered fraction -0.11 [-0.36, 0.06], pre-registered verdict MEMORY SURVIVES (strong). This answers the main open risk from the adversarial review.
8. **External adversarial review (5.19).** Item-level intervals were too narrow (items within an event are not independent). With the event as the unit: all 31 events, G2-valid pool, +14.6 points [6.6, 22.7], 21 positive and 6 negative, sign test p = 0.006; Luna alone +28.1 [17.0, 39.6], 18 against 1; each dataset alone is borderline (v3 alone: lower bound 1.3). The main open risk is that renaming removes name-borne cues, not only memory; a cue-preserving pseudonym condition has not been run. Claim wording narrowed.
7. **PD v4 (re-evaluation).** With a memory-free validity gate (B-versus-B2 at least 90% on real controls, A-versus-B at least 80% on unseen text) and a title-assisted memory probe (all six models meet the memory rule; 0 to 6 of 31 events under renaming), the pre-registered re-evaluation of v2 and v3 gives SUPPORTED on both: pooled gap +15.4 [10.6, 20.5] and +13.4 [7.2, 19.9], unseen-text gap 0.0, event-level correlation with memory 0.73 and 0.66 (section 5.18). It is a re-evaluation of seen gaps, not a new confirmation.
5. **PD v3 (confirmatory).** On 12 books no earlier version used, with the validity bar fixed at 80% in advance, the pre-registered verdict is PARTIALLY SUPPORTED (unchanged with Luna in the pool): pooled real-book gap +12.7 points [6.8, 19.0] for the five local models (+13.6 [7.9, 19.6] with Luna; Luna alone +18.2 [10.9, 26.6]), unseen-text gap 0.0, the gap tracks how well-known the book is (Spearman 0.80); the memory-count condition fails because the closed-book probe under-detects (section 5.17).
6. **v1.0 additions.** PD v2 (19 books, 5 local models plus Luna, repaired controls): verdict INCONCLUSIVE; no model reaches the 95% renaming-validity gate; all six show a positive real-book gap (Luna +35.2 points) and a 0.0 gap on unseen text, descriptive only, concentrated in the most famous books; plain controls on famous books appear memory-assisted (section 5.15). Engineering probes: the resolver is exactly prefix-causal but the persona stage is not (8.0% of character-cuts), and the resolver behaves as a string lookup plus about 3% to 5% alias merging (section 5.16). Ranked novelty points are in section 8b.

---

## 1. Problem

A web-novel reader meets "the masked guest" or "the clan head" long before the text says who that is. A system that links such aliases must answer *what is the reader entitled to believe at chapter c*, not *who is it in the end*. Two things make this hard for long serials. First, identity is revealed late, and mid-book linking that uses the later reveal is premature. Second, an LLM may already remember the novel, so truncating the context to chapters up to c does not stop it from linking to the answer it remembers (parametric leakage). EchoTales builds a bitemporal graph with separate discourse, story and knowledge time and a reader-observer query, `state_of(target, timeline, position, observer=READER)` `[REPO]`, so the question is testable.

## 2. Claims, one falsifiable sentence each, with status

| ID | Claim | What would falsify it | Status |
|---|---|---|---|
| C1a | On items whose reader-warranted identity at chapter c differs from the final-truth identity, a *premature-resolution rate*, with leakage defined as the change between original and consistently renamed text, separates systems that use later information from systems that do not. | Rate equal across systems; or the renaming control changes the answer for reasons other than memory. | **Pilot signal, inconclusive by pre-registration.** Renaming control valid (R1: 30/30). On the 4 items with a repo-derived reveal chapter: original names 4/4 name the silver final identity, renamed 0/4 (section 5.4). Silver labels; one model. |
| C1b | A link rule that must cite spans inside the prefix that entail it, with names masked, lowers the premature-resolution rate relative to plain whole-input renaming. | No difference from whole-input renaming on the same items. | **Not supported as implemented.** The gate rejected all 4 premature answers but also cut control accuracy from 96.7% to 46.7% (section 5.4). Pre-registered prompts were not tuned. |
| C2-pilot | A 72-item reader-view / omniscient-view sheet for web-serial hard cases is constructible and can be annotated by one person. | Unconstructible, or too few items where the two views differ. | **Constructed, not yet labelled by a human.** 23 pre-reveal candidates. |
| C5 | The pipeline's real-novel failures are located at mention detection and in a scorer that links nothing, not at linking decisions. | Detection loss small, or the scorer linking a material share. | **Supported** by repository measurements (silver and system-internal; section 5). |

**Ranking after the evidence.** C5 is the surviving floor. C2-pilot is a construction result. C1a and C1b are retained as the research question but have no supporting number.

## 3. Closest prior art and the exact difference

Full table with evidence tags: `PRIOR_ART.md`. I read the papers' own text (not summaries) for every row below; where a venue comes from a search snippet it is marked `[LEAD]` there.

| Closest work | What it already does | Exact difference from EchoTales |
|---|---|---|
| Jiang & Ferraro, arXiv 2412.14368 | Name replacement as a memorisation control on six character-story tasks, including coreference; human check that gold survives renaming `[PUB]` | Renaming a control is **theirs**. They have no chapter-prefix, no disclosure time, no premature-resolution rate; they rename main characters only |
| SynthWorlds, ICLR 2026 | Renaming plus a rename-leak audit as the way to separate knowledge from reasoning `[PUB]` | Encyclopedic QA, not fiction; no alias task |
| TimeChara, Findings of ACL 2024 | Shows LLMs hold novel plots in parametric memory and that a context-cutoff baseline does not stop future leakage `[PUB]` | Role-play event knowledge, not alias-to-identity linking; leakage exploited, not controlled |
| KoCoNovel, LREC-COLING 2024 | **Reader-view and omniscient-view coreference labels** on 50 public-domain Korean novels; views differ in 5 works `[PUB]` | Omniscient-only experiments, no LLM, no leakage control, no chapter-indexed disclosure, not translated serials. *Dual labels are not new in themselves.* |
| NarraWorld, arXiv 2609.32401 | States "the culprit's identity should not be disclosed prematurely" and has an alias-linking stage in a validity-interval store `[PUB]` | Disclosure is a design aim, never measured; alias linking not evaluated or gated on reveal time |
| Narrative World Model, arXiv 2607.05577 | Chapter-safe evidence and reveal order vs event order as modelled axes `[PUB]` | No identity task, no leakage control |
| E2RAG / ChronoQA | Time-aware graph over novels; "we never merge mentions" `[PUB]` | Avoids premature merging by never merging; no leakage control |
| GenWebNovel, COLING 2025 | Chinese web-novel NER, first 10 chapters of 40 novels; coreference listed as future work `[PUB]` | NER only; later reveals structurally absent; not used here (access terms) |
| Song & Liu 2024 | Lists hidden-identity plots as an unsolved challenge in one print novel `[PUB]` | One qualitative sentence; no metric, no LLM, no prefix setup |
| LitBank, FantasyCoref, BookCoref, LlmLink, Maverick, BookNLP | Literary coreference data and systems | Omniscient labels; no leakage control; none on translated web serials |
| TAC-KBP temporal slot filling | Valid-time intervals for relations `[PUB]` | No disclosure time, no identity merge |

**Search negative, bounded.** No work was found that evaluates BookNLP or a modern coreference system on translated web novels, or that measures future-knowledge leakage in character resolution with a prefix-of-book setup (19 logged queries; US-only engine; CNKI, KCI and Baidu Scholar not searched). I do not claim the combination of components is new: each ingredient has precedent and two papers overlap on disclosure-aware state.

## 4. Method

**4.1 Metric (C1a).** For an item (mention m at chapter c) with oracle `reader(m)` and `omniscient(m)`: *premature resolution* means a system links m to `omniscient(m)` when `reader(m) = UNDETERMINED`. *Leakage* is `rate(original text) - rate(consistently renamed text)`, using a bijective, type-preserving renaming of names so that a memory-free system is unaffected. Wilson 95% intervals; paired bootstrap for system differences once more than one system exists.

**4.2 Renaming control.** Pre-registered in three frozen versions (`docs/research/preregistrations/`). The control must commute with the repository's own normalisers before any result is read. It did not (section 6).

**4.3 Evidence-gated linking (C1b).** A link is permitted only if spans within chapters up to c, with names masked, entail it. Not run as an LLM experiment.

**4.4 Oracles.** SIO: ground truth from a synthetic world specification; the oracle never reads the system's store. Pilot: silver labels from the model-drafted gold now, and the author's human labels later.

## 5. Results

### 5.1 SIO, synthetic worlds (labels by construction)  `SYNTHETIC`

Source: `data/eval/chimera/sio_results.json` `[RAN]`, runner `scripts/chimera/sio_synthetic_oracle.py`, detail in `SIO_IMPLEMENTATION_NOTES.md`. 40 worlds, seeds 0-39, one run, CPU, no LLM, deterministic resolver. These are properties of the resolver's mention layer on templated text and **do not transfer to real text**.

| Metric | k/n | 95% CI |
|---|---|---|
| M1 prefix-invariance violations, pooled (mention, cut) pairs | 0/3741 | [0, 0.001] |
| M1, worlds with any violation | 0/40 | [0, 0.088] |
| M2 premature link to the revealed identity (full run) | 0/218 | [0, 0.017] |
| M3 post-reveal alias **not** linked to the revealed identity | 221/221 | [0.983, 1] |
| M4 title linked backwards to a holder named later | 40/40 | [0.912, 1] |

Reading. The M2 = 0 is **vacuous**: the resolver ignores the reveal sentence and links every alias, before and after the reveal, to the one co-present named character (218/218 and 221/221), the wrong person under both views. That is over-commitment on a deictic alias, driven by this generator's one-name-per-chapter design. M4 is the documented backward extension of the first title holder (`title_holders.py`). The per-mention title link events are stamped at the mention's chapter while the holder binding is stamped at the declaration chapter (40 of 107 events); `state_of` reads only the binding `[INSPECT]`, so no leak through `state_of` is shown. A generator flaw affects one exploratory row (13 of 40 worlds; documented).

### 5.2 Real novel (RI), 72-item pilot sheet, silver  `SILVER`

Source: `data/eval/chimera/silver_pilot_results.json` `[RAN]`, script `scripts/chimera/silver_pilot_analysis.py`. **Reference labels: model-drafted gold, unconfirmed. There are no reader-view labels and no human labels.** Items are *chosen*, not sampled (23 pre-reveal candidates, 17 other hard cases, 32 controls).

| Gold-sourced hard items (37) | n | not detected as a mention | detected, unresolved | linked, matches silver label | linked, differs from silver label |
|---|---|---|---|---|---|
| Tier P (disclosure-flagged) | 20 | 8 | 0 | 12 | 0 |
| Tier H (other hard cases) | 17 | 11 | 0 | 3 | 3 |
| All | 37 | 19 (51%) | 0 | 15 | 3 |

- **Detection is the bottleneck on this slice too**: 19 of 37 silver-labelled hard items never become a mention, consistent with the repository's earlier 58/88 finding (`data/eval/hardcase_resolution.json`, overlap alignment; `CHIMERA_ERRATA.md` E3) `[REPO]`. By category, every one of the 7 relational-deictic and 4 title-transfer items is undetected.
- **Sheet integrity (no labels involved)**: all 33 system-sourced items (3 clan-head, 30 plain controls) recover the same mention from the sheet's offsets, 33/33.
- **Real-data counterpart of the SIO event-stamp finding (no labels involved)**: 5 of 22 title-holder link events in the shipped RI database are stamped at chapter 1 while the holder binding is learned at chapter 6 (Wilson 95% [0.10, 0.43]).
- **Eligibility for a premature-resolution count**: of 23 pre-reveal candidates, 12 gold-sourced ones are linked by the system at all; those are the only items on which a premature rate can be non-zero once a human marks the reader view. With 0 events in 12 the exact one-sided 95% upper bound is 22%; in 23 it is 12%. **The pilot cannot detect a premature-resolution rate below roughly 12-22%.**

Nothing in this subsection is an accuracy, a reader-view result, or evidence that a model label equals a human label.

### 5.3 Repository audit findings, verified in files  `[REPO]`

| Finding | Source |
|---|---|
| The learned scorer links nothing: best reachable probability 0.550 against a 0.80 threshold; 0 of 880 real links are SCORED | `docs/results/SCORER_DIAGNOSIS.md:50`; `docs/status/STATUS.md:77,79` |
| All 103 labelled gold candidates are decided by pre-filters (FORCE_LINK / BLOCK) before the scorer | `docs/status/STATUS.md:79` |
| Hard cases are lost at detection: 58 of 88 never become a mention (overlap alignment; 67 by exact span) | `data/eval/hardcase_resolution.json`; `CHIMERA_ERRATA.md` E3 |
| External anchor (human-keyed): LitBank CoNLL F1 15.95 on the full person key, 42.44 on proper names only | `data/eval/litbank_results.json` |
| Real data is thin: 3 reveals in the observer ablation | `data/eval/observer_ablation.json` |
| Verified defects B1-B9 (for example `retract_alias_bindings` has no callers) | `docs/research/CHIMERA_DEFECT_BACKLOG.md` |

### 5.4 L1: first LLM test of C1a and C1b, silver  `SILVER`

Source: `data/eval/chimera/l1_results.json` and `l1_analysis.json` `[RAN]`; pre-registration `PREREG_L1_llm_leakage.md` v1 and hashes in `MANIFEST_L1.json`; runner `scripts/chimera/l1_llm_leakage.py`; analysis `scripts/chimera/l1_analyze.py` (written before the run). Model `gpt-5.6-luna` (OpenAI). **Reference labels: silver (model-drafted gold; the pipeline's own link for system-sourced items). Reveal chapters: repository structured data only.** Run once per arm, 281 calls, 110,905 input and 3,800 output tokens, **actual cost $0.0267** (approved cap $0.10; pre-run estimate $0.037). The key was never printed or stored; the results file holds letters, hashes and offsets only.

| Pre-registered measure | Result | Reading |
|---|---|---|
| R1 renaming validity: original vs renamed prompts give the same letter on the 30 plain controls | 30/30 [0.89, 1.00] | **Valid.** Renaming did not break reading on determinate items |
| Control accuracy vs silver (n = 30) | A 29/30; B 29/30; D 14/30 | Always-most-frequent-candidate baseline 18/30 (60%); uniform chance about 9% |
| R2 primary, 4 items (CP-001/002/003 clan head, reveal ch 6 from the title-holder binding; CP-017, reveal ch 166 from an observation row) | names the silver final identity: A 4/4, B 0/4, D 0/4 | **Inconclusive by pre-registration.** Directionally what C1a and C1b predict |
| Leakage, A minus B on 62 items with a silver label | +9.7 points, 95% CI [3.2, 17.7] | Renaming lowers accuracy on hard items; 6 items differ, all A correct and B wrong |
| R3 closed-book, 15 non-string-trivial items | original 1/15, renamed 0/15; 14/15 abstained each | **No evidence of memorisation for this model**; chance about 0.10, exact p = 0.79; baseline 7/15 |
| R4 gating cost | controls D minus A = -50 points; D abstained on 4/4 primary items | **Not within 5 points: the gate over-rejects** |

**Post-hoc checks (not pre-registered; labelled as such).**
- *Clan-head items are not textually entailed.* For CP-001, CP-002 and CP-003 the full name "Gu Yue Bo" does **not** appear in the 1,200-character prefix window (the family tokens do). In arm D the model cited two verbatim spans for the same answer and the gate auto-rejected all three because the claimed name is not in the cited spans. That is the C1b mechanism working as designed on these items. Under renaming (arm B) the same inference failed 3 of 3, which a text-only inference would not predict: this is the leakage-consistent part.
- *CP-017 is ambiguous.* The full name "Bai Ning Bing" is present in its window, so the answer may be legitimate; the gate marked it not entailed.
- *Sign test on A vs B.* 6 discordant items, all in one direction: exact two-sided p = 0.031 (post-hoc).
- *Why gating over-rejects on controls.* 7 of 30 controls had cited spans that were not verbatim substrings (the model paraphrased), 7 more were judged not entailed even though the raw answer was right, and one was rejected for a name-absence rule. Per pre-registration rule R5 nothing was tuned or rerun; a fixed gate would be a new version.
- *Closed-book abstention.* The model abstained on 14 of 15 closed-book items in both conditions, so the closed-book result says the model declines, not that it has no memory.

**Caveat added after the M0 literature reading (2026-10-15).** Finance-domain work (Glasserman & Lin; Wu et al., method only) shows the renamed arm can differ for reasons other than memory (distraction, information loss), and our renamer failed its own commutation gate in T4 v3. The A-minus-B gap (+9.7 points) and the three clan-head renamed failures are therefore **not established as parametric leakage**. Leakage-as-real-minus-renamed gap is also SynthWorlds' "knowledge advantage gap", so what is ours is only the prefix and entitlement framing. An unseen-text control (difference-in-differences on synthetic-world items) and a positive-control closed-book probe are required before any leakage claim; the closed-book probe here has no positive control.

**What this does and does not support.** It supports: prompt-only renaming is a valid control on this model and serial, and renaming changes answers on exactly the hard alias items where a prefix cannot decide, in one direction. It does **not** support a premature-resolution rate (n = 4, pre-registered inconclusive), reader-view correctness (no human labels), generalisation beyond one model, or an effective evidence-gated rule. A follow-up (L1-H) on the human-labelled pre-reveal items would give up to 23 primary items.


### 5.5 TRACK P. M3: does the premature-resolution metric separate systems? (synthetic)  `SYNTHETIC`

Source: `data/eval/chimera/m3_results.json` `[RAN]`; pre-registration `PREREG_M3_reveal_aware_synthetic.md` (frozen before the code existed); script `scripts/chimera/m3_reveal_aware.py`; 160 worlds (40 seeds x 4 reveal-sentence templates), 320 reveals, 1,756 alias mentions, 872 pre-reveal. Labels by construction from the world spec; no model, no human, no spend. **Does not describe real-text performance.** The shipped resolver is run unchanged; the reveal-aware systems are wrappers over its output.

| System (detector) | Premature (pre-reveal alias linked to the revealed identity) | Reader-view accuracy | Omniscient accuracy | Over-commit (linked to a wrong person) |
|---|---|---|---|---|
| S0 shipped resolver | 0/872 | 0/1756 | 0/1756 | 1756/1756 |
| S_abstain (never links aliases) | 0/872 | 872/1756 (49.7%) | 0/1756 | 0 |
| S_retro volume-first (oracle detector) | **872/872** | 884/1756 (50.3%) | 1756/1756 | 0 |
| S_causal reader-observer (oracle detector) | **0/872** | **1756/1756** | 884/1756 (50.3%) | 0 |
| S_retro (D_plus detector) | 436/872 | 442/1756 | 878/1756 | 878/1756 |
| S_causal (D_plus detector) | 0/872 | 878/1756 | 442/1756 | 878/1756 |
| S_retro / S_causal (repo `REVEAL_PATTERNS` detector) | 218/872 / 0/872 | 221/1756 / 439/1756 | 439/1756 / 221/1756 | 1317/1756 each |

- **What it shows (construct validity).** The metric separates the four designed systems: a system tuned for the final truth (retroactive) scores best on the omniscient view and is premature on every pre-reveal alias; a reader-observer system is never premature and scores best on the reader view; the shipped resolver's earlier "0 premature" (SIO v1) was vacuous because it also gets 0 on both accuracy views and over-commits on every alias. A do-nothing floor scores 49.7% on the reader view, so the metric needs both terms. The outcomes for the designed systems under the oracle detector hold **by construction**; that is the point of a sensitivity check, not a result about any real system.
- **What it shows that is not by construction: rule-based reveal detection is brittle.** Detection recall over 80 reveals per template: the repository's own `REVEAL_PATTERNS` find 80/80 on the one template that contains "none other than" and 0/80 on the other three; patterns added for two templates find 80/80 on those and **0/80 on two held-out phrasings**. When detection fails, both reveal-aware systems degrade to the shipped resolver's behaviour. A reader-view evaluation on real serials therefore depends on a reveal detector whose recall is unmeasured on real text.
- **Not claimed:** that any system is faithful on real text; that the added patterns are a good detector (they are fitted to two templates by design).

### 5.6 TRACK P. M3b: title-holder tenure under both views (synthetic)  `SYNTHETIC`

Source: `data/eval/chimera/m3b_results.json`; `PREREG_M3b_title_tenure.md`; `scripts/chimera/title_tenure_model.py`; 40 SIO worlds, 120 title mentions. Labels by construction.

| System | Reader-view accuracy | Omniscient accuracy | Premature on pre-declaration titles |
|---|---|---|---|
| V volume-first (shipped behaviour) | 80/120 | 120/120 | 40/40 |
| C causal-only | 120/120 | 80/120 | 0/40 |
| B bitemporal (story-time interval plus a `learned_at` stamp on the link) | 120/120 | 120/120 | 0/40 |
| shipped resolver's own title links | 67/120 | 107/120 | 40/40 |

The shipped resolver agrees with V on 107 of 120 links; the 13 disagreements are all the documented chapter-8 co-presence collision of the SIO generator. **This is Track S in substance:** the repository's alias *binding* is already bitemporal, and the defect is that the per-mention link and its event carry no `learned_at` stamp, so a consumer reading `mention.target_id` gets the volume-first answer. A TAC-KBP-style tenure score does not separate the models (0.833 each), because the bounds are the same and only the view differs. Tenure intervals themselves are covered by TAC-KBP (see section 3), so no novelty is claimed.

### 5.7 TRACK S. Prompt-boundary audit on the real database (no labels)  `NO LABELS`

Source: `data/eval/chimera/prompt_invariant_ri.json`; `scripts/chimera/prompt_invariant_check.py` (read-only; no existing code changed). System-internal consistency, not accuracy. In the shipped RI database **5 of 11,122 linked mentions** are linked before the reader's alias binding is learned (Wilson 95% [0.02%, 0.11%]); all 5 are title-holder links ("the clan head" at chapter 1, binding learned at chapter 6). Running the real `story_context` over 21 sampled chapters, **5 of 547 briefs** name that entity early; they are the same chapter-1 briefs. So the leak through mention links is narrow on this novel. The audit does not cover wiki canon, appearance reads or reference images (backlog B4, A1, A3).

### 5.8 TRACK P. M1: evidence gate v2 (silver)  `SILVER`

Source: `data/eval/chimera/l1b_results.json`, `l1b_analysis.json` `[RAN]`; pre-registration `PREREG_L1b_gate_v2.md` (frozen before the run; the designer had already seen all v1 outcomes, so the dev/test split is **not blind** to the v1 failure categories, as the prereg states); runner `scripts/chimera/l1b_gate_v2.py`. Model `gpt-5.6-luna`; 80 calls, 38,082 input and 2,701 output tokens, **actual cost $0.0109** (approved cap $0.05; running total $0.0376). Labels: **silver**; reveal chapters from repository data. The v1 result (controls 29/30 ungated vs 14/30 gated) is unchanged and still reported in section 5.4.

| Pre-registered measure (test split, n = 37 items) | Result |
|---|---|
| P1: gated accuracy on test-split controls vs ungated arm A | 15/16 vs 15/16 (within 5 points) |
| P2: primary items accepted as the silver final identity (of 4) | 0 of 4 blocked (3 by the name-absence rule, 1 not entailed) |
| Decision | **PASS** as pre-registered, descriptive only |
| Same controls, dev half / all | 14/14 vs 14/14; 29/30 vs 29/30 |

**Interpretation guard (decisive, and why this is not a positive result).** Every one of the 29 correctly accepted controls was accepted by the surface-identity rule (the mention itself names the candidate), and **the entailment path handled zero controls**, so P1 says nothing about whether the entailment check is sound. **Post-hoc, not pre-registered:** on the 40 non-control items the gate accepted 20, **19 of them by surface identity and 1 by entailment**; the entailment call rejected 9 of its 10 uses, so v2 repeats v1's over-strict entailment and the pass comes from a shortcut. The four primary items were blocked mostly because the claimed name is not in the prefix at all, which a trivial lexical rule ("link only to a name that appears in the visible text") would also do. So the supportable statement is only: **v2 no longer over-rejects trivial links, and it blocks the four premature answers, but the evidence-entailment mechanism itself is not shown to add anything beyond a lexical visibility check.** This weakens C1b further.

**Gate-versus-engine diagnosis (added after the owner's instruction; see `GATE_FAILURE_DIAGNOSIS.md`, which includes a correction after T4 v4).** *Correction first:* a second, pre-registered T4 attempt (v4, letter cipher) also failed its gate (G1 = 2, G2 = 4, G4 = 1, G5 = 7, no resolver run), and reading the violating classes showed the cause is **asymmetric protection inside the renamer** (a token protected in one spelling and ciphered in another), so the T4 failure is a renamer design gap, not purely an engine property as first written below; the engine's character-level merging only makes the requirement strict. Before treating a failed gate as a finding, each was attributed. The T4 renaming gate's 11 violations are all caused by the repo's character-level normaliser merging spacing, case and plural variants, which no token-level renamer can map one-to-one: an **engine** property, so T4 is better stated as "this engine is not token-compositional" than "renaming fails". For the evidence gate, 8 of the 12 silver-correct answers it rejected had the full claimed name in the prefix, so most of the over-rejection is the **gate's** span matching and entailment logic; why the entailment call rejects is not yet separated. This further weakens the claim that the v2 pass supports evidence-gated linking.

### 5.9 TRACK P. T4 v5: renaming control validated against the deterministic resolver (no labels)  `NO LABELS`

Source: `data/eval/chimera/t4_v5_results.json`, `t4_v5_negative_control.json`; `PREREG_T4_renaming_validity_v5.md` (frozen before the code; single attempt) and `PREREG_T4_v5_addendum_1.md` (disclosed fix of a negative-control bug); scripts `t4_renaming_v5.py`, `t4_v5_negative_control.py`. System-internal; CPU only; no model; no spend. v3 and v4 failed their commutation gates (renamer asymmetric protection and short-name collisions, see `GATE_FAILURE_DIAGNOSIS.md`); **v5 passed**: G1 = G2 = G3 = G4 = G5 = 0 on 335 surfaces, 135 of 378 name tokens renamed. Resolver on the original and the renamed database (11,174 mentions): determinism O2 and identity I at 100%; renamed run **99.96% agreement** (11,170; Wilson lower bound 0.9991; entity-clustered interval [0.9987, 0.9999]); negative control (context-dependent renaming of "Yuan") 99.955% (11,169). **By the pre-registered rule: PASS.** Caveat: the negative control is below the renamed run by one mention, because about 90% of links are exact-surface matches, so the comparison cannot detect damage to rarer containment evidence; the claim is that renaming leaves this engine's decisions 99.96% unchanged. It does not show an LLM is unaffected.

### 5.10 TRACK P. L2U: unseen-text control for the renaming gap (synthetic and silver)  `SYNTHETIC / SILVER`

Source: `data/eval/chimera/l2u_results.json`, `l2u_analysis.json`; `PREREG_L2U_unseen_text_control.md` (frozen before the runner); `scripts/chimera/l2u_unseen_text.py`. Model `gpt-5.6-luna`; 124 calls, 43,321 input and 656 output tokens, **actual cost $0.0095** (running total $0.0471 of the owner's $0.10 cap). On synthetic text with invented names no memory is possible, so an A-minus-B gap measures renaming damage alone. Renamer: the T4 v5 cipher.

| Measure | Result |
|---|---|
| U1 renaming validity on synthetic plain items | A = B on 20/20 |
| Synthetic accuracy (n = 62: 21 pre-reveal alias, 21 post-reveal alias, 20 plain) | A 62/62 (100%); B 60/62 (96.8%) |
| **Synthetic gap (renaming damage alone)** | **+3.2 points, 95% CI [0.0, 8.1]**; both misses are pre-reveal items where B named a person instead of abstaining |
| Real-text gap from L1 (silver) | +9.7 points |
| **Difference-in-differences** (real minus synthetic) | **+6.5 points, 95% CI [-1.6, +14.5]** |
| Pre-registered reading | **(c) inconclusive**; ceiling guard applies (both synthetic arms at least 95%) |

So renaming damage on easy synthetic text is small but not zero (+3.2), about a third of the real gap; the residual +6.5 on real text has an interval that includes 0. **The leakage claim (C1a) remains unestablished.** The synthetic items are easy (ceiling), so they cannot show damage of the kind that may occur on hard real items; this is a weakly informative control with one model and silver labels on the real side.

### 5.11 TRACK P. M2Q: replication on a different family, local Qwen2.5-7B (silver and synthetic)  `SILVER / SYNTHETIC`

Source: `data/eval/chimera/m2q_results.json`, `m2q_analysis.json`; `PREREG_M2Q_qwen_local.md` (frozen before any study-item call); `scripts/chimera/m2q_qwen_local.py`. Model `qwen2.5:7b` via ollama on the owner's GPU (verified 100% in VRAM, no CPU offload), deterministic (temperature 0, seed 20261016), 278 calls, **no API cost**. A different family from the silver labeller (Claude) and from Luna (OpenAI); it replaces the Haiku-subagent plan, which was not run (about 6.3M tokens of quota and the labeller's family). Real items silver; synthetic items by construction.

| Pre-registered measure | Result | Reading |
|---|---|---|
| R1 renaming validity, A = B on 30 plain controls | **29/30** | **Not valid** (needs 30/30): the real-text gap is not interpreted |
| Real-text accuracy vs silver (62 items), A / B | 51 (82%) / 48 (77%); gap **+4.8** [0.0, 11.3]; 3 discordant A-right versus 0 | Below the +5 threshold and uninterpretable by R1 |
| Primary items (n = 4), A / B | 0 / 0 | Inconclusive by design |
| R4 closed book (15 items), original / renamed | **0 / 0**, all 15 abstained | No evidence of memory for this model; no positive control |
| R5 unseen text (synthetic, 62 items): A / B | 72.6% / 74.2%; gap **-1.6** [-11.3, +8.1]; plain A = B on 20/20 | Renaming damage on synthetic text is not detectable for this model |
| R5 difference-in-differences | **+6.5** [-3.2, +17.7] | **(c) inconclusive** |

**What this adds.** A second, different-family model shows no memory signal (closed book 0 of 15) and a real-text renaming gap that does not meet the replication threshold and whose control is not valid; its synthetic gap is about zero. Nothing here supports leakage; nothing rules it out for stronger models (a 7B model abstains on every closed-book item). Together with L1 and L2U, the honest summary is: **a renaming gap of +5 to +10 points appears on real text for two models, a synthetic renaming-damage gap of about 0 to +3 on invented names, and the difference-in-differences intervals include 0 for both.**

### 5.12 TRACK S (system, engineering). Scope-A adapters on branch `chimera/system-adapters`  `NO LABELS`

Integration or defect fixes, **not novelty**. Branch `chimera/system-adapters` from HEAD `6c7e2c2`, uncommitted (the standing no-commit rule); 6 existing source files changed (+161/-31 lines) and 6 new test files (22 tests); the full suite of 1,320 tests passes (exit 0) after the changes. Every behaviour change is a switch that is off by default except B1 and B3, which correct counters. Measured on a scratch copy of the real RI database, counts only (`data/eval/chimera/adapters_before_after.json`, `scripts/chimera/adapters_before_after.py`; system-internal, no labels):

| Fix | Change | Measured effect on RI |
|---|---|---|
| **B1** honest deferral counters (`resolve/runner.py`) | A re-gated LINK on a deferred case no longer counts as "recovered" unless a link is written; new counter `regated_link_not_applied`; `apply_deferred_links=True` writes it | The old code would have reported **107 "recovered"** and a nonsensical **-57 unresolved**; the honest default reports 0 recovered, 107 not applied, **50 unresolved**. With the link actually written only **1** of 107 applies (105 not applicable: their mentions were already resolved by other means) |
| **B2** prefix resolve (`resolve --chapters`) | The flag was accepted and ignored; it now selects the chapters, and the non-causal volume passes are skipped in prefix mode | `chapters=1-20`: links in chapters up to **20 only** (733 links, 114 groups) instead of the whole volume |
| **A7 / B13** title holders (`resolve/title_holders.py`) | `causal=True` starts the first tenure at its first declaration; `fuzzy_handover=True` bounds a closed tenure by the next declaration; the call that passed a field `FuzzyInterval` does not have (silently dropped) is fixed | `causal_titles=True`: links before the reader's binding **5 -> 0** (title-holder links 30 -> 25) |
| **A1/A2** prompt boundary (`world/context.py`) | `story_context(reader_entitled=True)` drops a mention linked before the reader was told | Closes the 5-of-547 early-naming briefs found by the audit in 5.7 when enabled |
| **B3** honest `conditioned_on` (`render/panels.py`) | The manifest and the conditioned-panel counter derive from the reference images actually sent (none), not from sheets that exist | Panels no longer claim conditioning; test asserts `conditioned_on == []` when a sheet exists |
| **B4** wiki canon dating (`persona/canon.py`) | `apply_canon(position=, first_appearance=)` drops the undated wiki tier before the character first appears | Hand-authored canon unaffected; the wiki's body-blindness stays open |

Not done (scope B and C): `is_address` (B6), the retraction writer (B5), reference-image re-wiring and the reference guard (B7, A3), and body-aware wiki traits.

### 5.13 TRACK P. Cross-novel replication: audit, reveal detector, renaming gate (system-internal)  `NO LABELS`

Source: `data/eval/chimera/xn_audit_*.json`, `xn_t4_*.json`; `scripts/chimera/cross_novel_replication.py`; `PREREG_T4_v5_addendum_2_crossnovel.md` (frozen before the script). Scratch copies of the three serials' databases, re-resolved with the **current** code. LOTM and ORV databases cover **40 chapters each** (partial volumes); RI covers all 199. No reference labels; counts only. CPU only, no spend.

| Measure | RI (199 ch) | LOTM (40 ch) | ORV (40 ch) |
|---|---|---|---|
| Mentions / linked | 11,174 / 11,122 | 2,402 / 2,334 | 2,267 / 2,262 |
| Link groups tagged `SCORED` | 10 | 16 | 8 |
| ...of which **link to an existing entity** | **0** | **0** | **0** |
| ...of which found a new entity | 10 | 16 | 8 |
| Links before the reader's alias binding | 5 | 0 | 0 |
| Raw `REVEAL_PATTERNS` matches in narration (resolving to a known character) | 4 (3) | 3 (1) | 0 (0) |
| Renaming gate, token-level (v3 design) | fails (G1 = 2, G2 = 9) | **passes** | **passes** |
| Renaming gate, class-protected cipher (v5) | **passes** | **passes** | **passes** |
| Resolver agreement under v5 renaming | 99.96% | 100.0% | 100.0% |

- **"The scorer links nothing" replicates on all three serials with the correct measure.** An earlier draft column mislabelled the `SCORED` tag as "scorer share"; that tag is the gate's default for every path that reaches the scorer, **including minting a new entity** (975 mentions over 266 of RI's 267 entities carry it). Counting groups instead, every `SCORED` group in all three novels founds a new entity; none links to an entity that already existed.
- **The repository's reveal detector almost never fires on real serials:** 7 raw matches in 279 chapters across three novels, 4 of them resolving to a known character. RI's silver hard-case file lists 30 reveal and disguise cases (17 + 13); at most 3 resolved matches could correspond to them, an **upper bound of about 10% recall against silver labels** (silver, and matches are not aligned to cases). This is the real-text counterpart of the synthetic brittleness result in 5.5.
- **The token-level renaming failure is not general.** The v3 design passes the gate on LOTM and ORV; its failure on RI came from that corpus's glued and plural name variants. The T4 verdict for LOTM and ORV is partial (no negative control defined).

### 5.14 TRACK P. PD: text-derived reveal benchmark on famous public-domain novels, four local models plus `gpt-5.6-luna`  `TEXT-DERIVED / SYNTHETIC`

Source: `data/eval/chimera/pd/run_*.json`, `analysis.json`, `r0_diagnosis_exploratory.json`; `scripts/chimera/pd_reveal_benchmark.py`; `PREREG_PD_reveal_benchmark.md`, `PD_events_v1.json`, `PD_prompts_v1.json` (frozen before the builder existed; hashes in `MANIFEST_PD.json`). **Label provenance:** the reveal oracle is **text-derived** (the book's own explicit reveal sentence, found by exact search; cutoff = a conservative position before it). The *selection* of the 7 events, reveal sentences and cast lists was made by the model-drafter and is **not yet verified by the owner**; nothing is human-verified. Seven events from seven public-domain books (Phantom of the Opera, The Scarlet Pimpernel, Great Expectations, The Case of Identity, A Study in Scarlet, Jane Eyre, The Red-Headed League). 72 items: 43 pre-reveal alias items (truth for a careful reader: UNDETERMINED), 8 post-reveal, 21 plain controls; each shown to each model with original names (A) and with every proper noun renamed by the T4 v5 cipher (B); 7 closed-book events (C). Synthetic unseen-text control: the 62 L2U items. Local models at temperature 0, seed 20261016, GPU only; `gpt-5.6-luna` spent $0.0254 (282 calls; ledger). `gemma2:9b` was **not run** (it did not fit fully in VRAM and CPU offload was forbidden).

Pre-registered primary result (R0 = A and B give the same letter on at least 95% of plain controls):

| Model | R0 agreement (plain controls) | R0 | Premature A | Premature B | Gap A-B | Sign test p | Synthetic gap | Closed-book: C_orig names identity (of 7) | C_ren |
|---|---|---|---|---|---|---|---|---|---|
| `gpt-5.6-luna` | 20/21 (95.2%) | **pass** | 3/43 (7.0%) | 0/43 | +7.0 pts, CI [0.0, 16.3] | 0.25 | 0.0 | 3 (memory present) | 0 |
| `qwen2.5:7b` | 14/21 (66.7%) | fail | 19/43 (44.2%) | 0/43 | +44.2 pts, CI [30.2, 58.1] | 3.8e-6 | +4.8 | 3 (memory present) | 0 |
| `llama3.1:8b` | 12/21 (57.1%) | fail | 8/43 (18.6%) | 1/43 | +16.3 pts, CI [4.7, 30.2] | 0.039 | +14.3 | 3 (memory present) | 0 |
| `mistral:7b-instruct` | 18/21 (85.7%) | fail | 16/43 (37.2%) | 2/43 | +32.6 pts, CI [18.6, 46.5] | 5.2e-4 | 0.0 | 3 (memory present) | 0 |
| `phi4-mini` | 15/21 (71.4%) | fail | 6/43 (14.0%) | 2/43 | +9.3 pts, CI [-2.3, 23.3] | 0.29 | -9.5 | 0 | 0 |

**Pre-registered verdict: LEAKAGE NOT SUPPORTED.** Only one model passes R0, so the pooled statistic is that model alone: gap +7.0 pts, 95% CI [0.0, 16.3] (condition i needs at least +10 pts with the interval above 0: fails); difference-in-differences +7.0 (CI [0.0, 16.3], does not exclude 0: fails); `memory_present` among R0-passing models: 1 (needs 3: fails).

What this does and does not show:

- **The closed-book positive control works.** Four of five models (Luna, Qwen, Llama, Mistral) name the revealed identity from the alias and candidate list alone for 3 of 7 events (chance about 1 in 9; exact one-sided probability below 0.04 per model), and **0 of 7 once the names are renamed**, for every model. This is the first evidence in this programme that the renaming control removes real memory of a text, and it contrasts with the real-serial probe, where memory was not demonstrable (14 of 15 abstentions, section 5.4). The 3 events were not tabulated per model here; see `analysis.json` and the runs.
- **Four of five models fail the renaming-validity gate on real prose.** Their answers change under consistent renaming on 14% to 43% of plain controls, against 5% for Luna. This is a finding about renaming controls, not a bug in the gate (see the diagnosis below), and it means those four models' gaps are **not interpretable as memory leakage**: the gap includes renaming damage. They are reported separately, as pre-registered.
- **Descriptive only, not part of the verdict:** the four failing models show gaps of +9 to +44 points, significant for Qwen, Llama and Mistral. Their synthetic (unseen-text) gaps are small (Qwen +4.8, Mistral 0.0; Llama +14.3 is the exception), so unseen-text damage does not explain Qwen's and Mistral's gaps, but real-prose renaming damage on plain controls (Qwen 100% accurate on A, 67% on B) could. This cannot be separated with the present design.
- **Luna's gap is small and not significant** (+7.0 pts, 3 premature answers in A, none in B; 32 of 43 abstentions in A and 39 in B, i.e. it mostly answers UNDETERMINED as the prompt asks). With 43 items the interval is wide (0.0 to 16.3).

**Gate-versus-engine diagnosis (owner rule), exploratory and post hoc (`r0_diagnosis_exploratory.json`).** Is R0 failing because the gate is wrong, or because the engine (renaming on real prose) damages these models? The same cipher yields A = B on 40 of 41 synthetic items that are not pre-reveal for Qwen and 41 of 41 for Luna, so the renaming code itself is not breaking text. On the real controls the disagreements for Qwen are 5 different letters and 2 invalid outputs; for Llama 4 different letters, 2 invalid, 3 cases where A was wrong; for Mistral 2 and 1. So the failure is the models misreading long ciphered classic prose, plus answer-format noise (over real and synthetic items Mistral gave 35 invalid answers and Llama 10). The gate (95% agreement) stays: loosening it after seeing the results would be changing the rule post hoc. A fairer follow-up needs a larger control set (21 controls give one-item resolution of 4.8 points) and a prompt that constrains the output format; both are new pre-registrations.

**Limits (stated in advance, plus what the run adds).** Event and cast selection is the model-drafter's, owner spot-check pending; one conservative-cutoff convention; hints before the explicit sentence may let a careful reader infer an identity early; 7 events from 7 books; candidate lists anchor; the "always the most-mentioned candidate" baseline in the prereg was **not computed** (the analysis script does not implement it), so a premature answer may sometimes be "name the protagonist" rather than memory; models that never abstain (Mistral 0 of 43) will name some candidate on every pre-reveal item. Each cell was run once. These are results about LLM behaviour on famous novels, not about the EchoTales pipeline or web serials.

### 5.15 TRACK P. PD v2: repaired re-run on 19 public-domain novels, five local models plus `gpt-5.6-luna`  `TEXT-DERIVED / SYNTHETIC`

Source: `data/eval/chimera/pd_v2/run_*.json`, `analysis.json`, `r0_asymmetry_exploratory.json`; `scripts/chimera/pd_v2.py`; `PREREG_PD_v2.md`, `PD_events_v2_additions.json`, `PD_prompts_v2.json` (frozen before any v2 call; hashes in `MANIFEST_PD_v2.json`). **Label provenance:** text-derived reveal oracle; the 19 events (7 from v1, 12 new from 12 more books) were *selected* by model-drafters and are **not owner-verified** (weakest oracles: MC, DL, SA; `PD_EVENTS_V2_NOTES.md`). Nothing is human-labelled. v2 repairs the three causes the v1 diagnosis named: answer-format noise (ollama JSON-schema constrained output), 21 controls (now 152) and a one-cipher artefact (a second independent cipher arm B2); it also computes the "most-mentioned candidate" baseline v1 listed but never computed. Local models at temperature 0, seed 20261016, GPU only. **Deviation, logged:** the frozen prereg said no paid model in v2; after the result the owner approved a Luna run on the same frozen items and prompts ("run luna, if it is below 0.15 then run it"; expected cost $0.1195, actual $0.1212, 1,132 calls). Luna received the same prompts as plain chat (no schema-constrained decoding available) and its JSON answer was parsed; 5 answers were INVALID. 317 real items (135 pre-reveal, 30 post-reveal, 152 plain controls), 19 closed-book events, the same 62 synthetic items.

| Model | R0: A = B on 152 controls | B = B2 | Gap A minus mean(B, B2), 135 items | Damage-adjusted gap | Premature A (baseline 14.8%) | Synthetic gap | Closed book: names identity (of 19; 6 needed) | Renamed C / C2 | Invalid |
|---|---|---|---|---|---|---|---|---|---|
| `gpt-5.6-luna` (reference) | 85.5% | 89.5% | **+35.2 pts [27.0, 43.0]** | +20.7 | 36.3% | 0.0 | 11 | 0 / 0 | 5 |
| `mistral:7b-instruct` | 88.2% | 92.1% | +24.1 pts [15.9, 32.2] | +12.2 | 31.9% | 0.0 | 8 | 0 / 1 | 0 |
| `qwen2.5:7b` | 80.3% | 80.9% | +22.2 [15.2, 29.6] | +2.5 | 31.1% | 0.0 | 6 | 1 / 0 | 0 |
| `llama3.1:8b` | 80.9% | 90.8% | +14.1 [6.3, 21.9] | -5.0 | 21.5% | 0.0 | 8 | 3 / 4 | 0 |
| `gemma2:9b` | 84.2% | 97.4% | +13.0 [7.0, 19.3] | -2.8 | 20.0% | 0.0 | 6 | 0 / 0 | 0 |
| `phi4-mini` | 87.5% | 93.4% | +10.4 [4.4, 16.7] | -2.1 | 16.3% | 0.0 | 2 | 1 / 0 | 0 |

**Pre-registered verdict: INCONCLUSIVE (validity-limited).** No model of the six reaches the 95% renaming-validity gate (best 88.2%; Luna 85.5%), so the pooled statistic is undefined and no leakage verdict is issued. (The v1 rule would have returned NOT SUPPORTED here; v2 declared before the run that fewer than 3 passing models is INCONCLUSIVE, because the outcome would otherwise reflect missing power.) `gemma2:9b` ran this time (smaller context, fully in VRAM).

What v2 does and does not show:

- **Luna, the reference comparator, shows the largest gap, and it is concentrated.** With original names it names the hidden identity on 36.3% of pre-reveal items (49 of 135) against 1.1% with renamed names; on unseen synthetic text the gap is 0.0; closed book it names the identity for 11 of 19 events and for 0 of 19 once renamed. On the seven v1 events the result is identical to v1 (3 of 43 premature, 0 renamed), so the changed prompt did not move it; the difference from v1's +7 comes from the 12 new events, where Luna is premature on 46 of 92 items with original names (Les Misérables 7 of 8, Villette 7 of 8, The Woman in White 7 of 8, The Three Musketeers 6 of 8, Ivanhoe 5 of 8, Monte Cristo 4 of 8; The Secret Adversary 0 of 8). The effect is strongly event-dependent, largest for the most famous books. The 1,200-character window cannot hold a book's earlier hints, which is why a premature answer that vanishes under renaming reads as recall of the book rather than inference from the passage; this is an interpretation, not a test. The same asymmetry that weakens the gate is present for Luna (21 plain controls right only with original names, 1 only with renamed, p = 1e-5), so Luna's own gap carries the same caveat as the others.
- **The format repair worked; the gate failure was not format noise.** Invalid answers fell to 0 for every model (v1: up to 35). R0 rose from 57-86% to 80-88%, but stays below 95% for every model.
- **Descriptive, not verdict-bearing: all five models show a positive gap on real books (+10 to +24 points, every interval above 0) and a gap of exactly 0.0 on unseen synthetic text.** The ordering follows closed-book memory: the one model without closed-book memory (phi4-mini, 2 of 19) has the smallest gap. Premature rates in the original arm (16% to 32%) exceed the 14.8% most-mentioned-candidate baseline, and renamed-arm rates (6% to 9%) fall below it. Because no model passed the gate, this is a direction, not a result; the gap includes any renaming damage.
- **Closed-book positive control, replicated at larger n.** Four of five models name the revealed identity from the alias alone for 6 to 8 of 19 events (chance 1 in 8 would give 2.4; 6 is the pre-registered threshold), and fall to 0-4 when renamed. Llama still names it 3 to 4 times under renaming, so its cipher arms are not fully memory-free.
- **Gate-versus-engine diagnosis (owner rule), exploratory and post hoc (`r0_asymmetry_exploratory.json`).** The R0 gate itself appears **contaminated by memory on famous books**. On the plain controls the A-versus-B disagreements are asymmetric toward the original-names arm for gemma2 (23 items right only in A, 1 only in B; sign test p = 3e-6), mistral (15 vs 1; p = 5e-4) and qwen (26 vs 3; p = 2e-5), not for llama (16 vs 9) or phi4-mini (12 vs 6), while B versus B2 disagreements are symmetric for every model (all p above 0.14). A cipher that merely injects noise would hurt both arms alike; instead the original arm is more accurate on *plain* controls, as expected if the model also recognises the book's characters. The alternative reading is that original names carry surface cues (nationality, gender) that the cipher removes. Either way, plain controls on a famous book are not a clean test of renaming validity. On unseen synthetic text, where memory is impossible, the same cipher gives A = B on 41/41 (phi4-mini), 40/41 (qwen), 38/41 (gemma2), 35/41 (llama) and 34/41 (mistral) non-reveal items; so phi4-mini and qwen look cipher-valid there, gemma2 is borderline (92.7%), and mistral and llama do not. The gate threshold was not loosened: any redefinition (for example validity measured on unseen text) is a new pre-registration with fresh items, not a re-reading of these.
- **Threshold sensitivity (post hoc, `threshold_sensitivity_posthoc.json`; the frozen verdict above is unchanged).** The 95% bar was an arbitrary conventional choice, so the pooled statistic is shown at other bars. At R0 of at least 90%: no model passes. At 88%: 1 model (mistral), gap +24.1 [16.3, 32.2], inconclusive. At 85%: 3 models (Luna, mistral, phi4-mini), pooled gap +23.2 [18.9, 27.8], synthetic gap 0.0, closed-book memory in 2 of them, so the decision rule reads PARTIALLY SUPPORTED. At 80%: all 6 models, pooled gap **+19.8 points [15.7, 24.1]**, synthetic gap 0.0, difference-in-differences +19.8 [15.7, 24.1], closed-book memory in 5 models; the pre-registered decision rule read at this bar would return SUPPORTED. This reading cannot be reported as the verdict: 80% was found after the data and happens to be the lowest bar that admits all five models, and the asymmetry analysis above shows the A-versus-B disagreement on plain controls is partly memory, so a lenient gate partly measures the effect it is meant to exclude. What it does show is that the direction (positive real-book gap, zero unseen-text gap, memory present) holds across every bar that admits at least one model. A threshold for v3 should be fixed before new items are run.
- **Limits.** Event selection and cast lists are the model-drafter's; several new events have implied or spoken reveals or a cutoff close to the reveal; six of 19 books are translations; constrained decoding makes v2 gaps not directly comparable with v1 gaps; local 7B to 9B models only; one run per cell; no human label anywhere.

### 5.16 TRACK S/P. Engineering probes E1-E6: invariants of the graph and resolver tested on three serials  `NO LABELS / SYNTHETIC`

Source: `docs/research/ENGINEERING_NOVELTY_PROBE/` (notes, `SUMMARY.md`), `scripts/chimera/eng_probe_*.py`, `data/eval/chimera/eng_probe_E*.json`. Run by a delegated subagent on scratch copies of the databases, CPU only, no LLM, each probe with a hypothesis and falsifier written before its confirmatory run. **I re-checked one headline number only** (E6: 23 of 288 character-cuts, summed from the stored per-novel JSON files; E5: string-identity baseline and ARI 0.971 for RI read from the stored JSON); the other numbers are the subagent's, not independently re-run. No human labels; correctness of the resolver or personas is not measured.

| Probe | Invariant tested | Result | Reading |
|---|---|---|---|
| E1 resolver prefix causality | decisions at chapter c depend only on chapters up to c | **holds**: 0 of 28,165 mention-cut pairs differ (14 cuts, 3 serials); by-design volume passes re-target up to 39% of early LOTM mentions | positive property; the volume passes are sized |
| E6 persona-stage prefix causality | state_of(READER, k) equals the graph built from chapters up to k | **violated**: 23 of 288 character-cuts (8.0%) differ; 46% of the cast after LOTM chapter 5 (Wilson [23, 71]); 21 of 23 are gender (and the derived archetype) unknown in the prefix and set in the full graph from later pronoun evidence; 2 go the other way; body splits use a whole-volume "life after" rule; age band, register, big five differ in 0 | a measured look-ahead in the reader view; whether gender-from-later-evidence is a defect or a convention is the owner's call |
| PD v3 pre-registered confirmatory test (12 unused books, 5 local models, 80% bar fixed in advance) | That the v2 direction (positive real-book gap, zero unseen-text gap) fails on fresh books | **PARTIALLY SUPPORTED:** pooled gap +12.7 points [6.8, 19.0], difference-in-differences +12.7, conditions (i) and (ii) hold; condition (iii) (memory in at least 3 valid models by the closed-book probe) fails (1 of 5; probe under-detects). Robust to dropping weak-oracle events (+12.0 to +19.0). |
| PD v4 pre-registered re-evaluation (memory-free gate G2, title-assisted probe M2) | That the leakage effect disappears once the validity gate is memory-free and memory is measured with a stronger probe | **SUPPORTED on both datasets:** v2 pooled gap +15.4 [10.6, 20.5], v3 +13.4 [7.2, 19.9], synthetic gap 0.0, memory by M2 in 4 and 3 valid models; event-level correlation 0.73 and 0.66. Re-evaluation of seen gaps, not a new confirmation; condition (iii) is easy to meet with the title given. |
| PD v5 pre-registered cue-preserving test (B3 pseudonyms, 31 events, five local models) | That the original-versus-renamed gap is cue loss, not name-keyed memory | **MEMORY SURVIVES (strong):** gap A-B3 +16.1 [8.2, 25.0] (cipher gap +14.6), recovered fraction -0.11 [-0.36, 0.06]; B3 restores plain-control accuracy to the original level (cue loss was real on controls) but does not restore premature naming. |
| PD v6 pre-registered final test (7 fresh books, all instruments fixed in advance) | That the leakage effect fails to replicate on books nothing has touched | **NOT SUPPORTED for the valid local pool** (gap -5.9 [-14.8, 1.0], 1 event positive against 4); **replicates for Luna** (+16.7 [5.4, 28.6]; fresh books pooled +17.7 [8.0, 28.3], 9 positive against 1). Small models recognise these less-famous books poorly (M2 1 to 3 of 7). |
| Dose-response (post hoc, 38 events) | That the gap does not depend on how well the book is known | **Not falsified:** gap rises with recognition (Luna vs local recognition Spearman +0.37, p = 0.024; valid-local pool +0.59, p = 0.00015, about zero below three recognising models and +40.9 when all five recognise). Post hoc; the local-pool version shares models with its predictor. |
| E5 resolver versus string lookup | the gazetteer compounds; the resolver adds more than normalisation | exact-match groups equal groups whose surface was seen before (0 exceptions on 1,809); real curve within a chapter-shuffle null on LOTM and ORV; surface-key partition agrees with the resolver at ARI 0.971 to 0.985 (RI 0.971); 4.7% of RI mentions are in a non-dominant surface of their entity; surface keys held by more than one entity: 0 (RI), 0 (ORV), 1 (LOTM) | on these serials the resolver behaves as an order-invariant normalised-string lookup plus about 3% to 5% alias merging; the "compounding" is memoisation; precision is unmeasured |
| E2 order and batching | incremental resolution is stable | re-run exact; window size inert; ARI at least 0.995 under 10% chapter swaps, at least 0.984 under full reversal; entity ids are order-dependent (gate artefact: ids hash first surface and position) | supports E5 |
| E3 `state_of` invariants (synthetic spec oracle) | bitemporal filters, retraction is not interval end, observer scope | filters hold (0 of 4,800 prefix queries violate); gaps: persona bindings ignore truth status and have no retraction; **retraction is observer-global** (a character who never learned a claim was false stops believing it when the reader is told); off the main timeline the default knowledge position is omniscient; voiding a main-timeline segment empties the graph; equal-position attribute ties depend on insertion order | no real-data instance (zero retractions, zero conflicting attributes in the three serials); the observer-global retraction is a modelling point |
| E4 discourse positions | `DiscoursePosition(chapter, offset)` is a total order | **violated**: offsets are block-relative; within a chapter the order agrees with true text order for only 46.5% to 58.2% of pairs (random is 50%); writers use three different units | engineering integrity defect; no downstream error today because queries are chapter-level |

### 5.17 TRACK P. PD v3: confirmatory test on 12 books no earlier version used, validity bar 80% fixed in advance, five local models plus `gpt-5.6-luna`  `TEXT-DERIVED / SYNTHETIC`

Source: `data/eval/chimera/pd_v3/run_*.json`, `analysis.json`, `sensitivity_secondary.json`; `scripts/chimera/pd_v3.py` (generated from the frozen `pd_v2.py`: event file, paths, R0 bar and a per-event secondary only); `PREREG_PD_v3.md`, `PD_events_v3_additions.json`, `MANIFEST_PD_v3.json` (frozen before any v3 call). **Label provenance:** text-derived reveal oracle; the 12 events (12 books, 12 authors, 2 translations: Father Goriot and The Mystery of the Yellow Room) were selected by a model-drafter and are **not owner-verified**; weak oracles listed in `PD_EVENTS_V3_NOTES.md` (BR, LA, YR, EL, CO, IM, PG). The renaming-validity bar is **80%** (owner convention, fixed before the run and not tuned on v3 data); everything else is as PD v2. 216 items (96 pre-reveal, 24 post-reveal, 96 plain controls), 12 closed-book events, the same 62 synthetic items. The prereg made Luna an optional reference comparator subject to an owner-approved exact estimate; the owner approved $0.0836 expected / $0.139 worst case and Luna ran on the same frozen items and prompts (808 calls, actual $0.0846, plain chat with the JSON answer parsed, 4 INVALID). The local-only analysis (the pre-registered five-model pool) is kept in `analysis_local_only.json`; `analysis.json` includes Luna.

| Model | R0 (A = B, 96 controls) | Gap A minus mean(B, B2), 96 pre items | Premature A / baseline | Synthetic gap | Closed book: names identity (of 12; 5 needed) | Renamed C / C2 |
|---|---|---|---|---|---|---|
| `gpt-5.6-luna` (reference) | 91.7% | **+18.2 pts [10.9, 26.6]** | 18.8% / 8.3% | 0.0 | 4 (just below the 5 needed) | 0 / 0 |
| `gemma2:9b` | 90.6% | **+25.0 pts [15.6, 34.9]** | 33.3% / 8.3% | 0.0 | 3 | 0 / 0 |
| `llama3.1:8b` | 93.8% | +14.6 [6.8, 22.9] | 25.0% | 0.0 | 7 (memory) | 2 / 2 |
| `mistral:7b-instruct` | 95.8% (strict 95% pass) | +9.9 [0.5, 19.3] | 22.9% | 0.0 | 2 | 1 / 1 |
| `qwen2.5:7b` | 80.2% (just above the bar) | +9.9 [0.5, 19.3] | 19.8% | 0.0 | 3 | 1 / 0 |
| `phi4-mini` | 93.8% | +4.2 [-2.6, 11.5] | 12.5% | 0.0 | 3 | 0 / 0 |

**Pre-registered verdict (five local models): PARTIALLY SUPPORTED.** All five models pass the 80% bar. Pooled over them: gap **+12.7 points [6.8, 19.0]** (condition i: at least +10 with the interval above 0: **holds**); synthetic gap 0.0, difference-in-differences **+12.7 [6.8, 19.0]** (condition ii: **holds**); closed-book `memory_present` in only 1 of the 5 valid models (condition iii needs 3: **fails**). On unseen books, models name a hidden identity more often with the original names than with consistently renamed names, and the same renaming changes nothing on unseen synthetic text. At the strict 95% bar only mistral passes, so the 95% reading is INCONCLUSIVE again. **With Luna added to the pool (six models): pooled gap +13.6 points [7.9, 19.6], synthetic gap 0.0, difference-in-differences +13.6 [7.9, 19.6], memory in 1 of 6 valid models by the closed-book rule; verdict unchanged, PARTIALLY SUPPORTED.** Luna alone: R0 91.7%, premature 18.8% (18 of 96) with original names against 0.5% with renamed names, plain controls 100% accurate with original names and 91.7% renamed, abstains on 76 of 96 pre-reveal items, names the identity closed book for 4 of 12 events (one short of the memory rule) and for 0 once renamed. The per-event premature counts pooled over all six models (table below) pick out the same books: Gatsby, Invisible Man, Father Goriot and Riders of the Purple Sage are highest, with Spearman 0.75 against closed-book recognition.

- **Robust to the weakest oracles (secondary, `sensitivity_secondary.json`).** Dropping BR: +13.5 [7.1, 20.0]; dropping all seven flagged weak events (40 items left): +12.0 [1.0, 23.3]; dropping the three events with an alias-and-identity sentence in the prefix (VW, EL, LA): +19.0 [12.4, 25.8]. Every interval is above 0.
- **Concentrated where books are best known.** Premature rates with original names, pooled over the five local models (40 items per event): The Great Gatsby 30, Invisible Man 19, Father Goriot 18, Riders of the Purple Sage 16, the rest 0 to 7 (with Luna in the pool, 48 items per event: Gatsby 35, Invisible Man 22, Goriot 22, Riders 21, the rest 0 to 7). Spearman correlation between an event's premature rate and the number of models that name its identity closed book: **0.80** for the five local models (0.75 with Luna; 12 events; descriptive). Both findings match the v2 result for Luna (Les Misérables, Villette, The Woman in White high; The Secret Adversary zero).
- **Why condition (iii) fails, and what it does not mean.** The closed-book probe gives only the alias and the candidate list, so it works for famous aliases (Gatsby, Goriot, the Invisible Man) and fails for descriptors and minor names; the threshold needs 5 of 12 events per model and most models name 2 to 3. Memory is therefore under-detected by this probe, so the failed condition is a power limit of the probe, not evidence that the gap is not memory; the correlation above is the more informative signal.
- **Limits.** The gap is still read through a lenient gate: damage-adjusted gaps (gap minus the plain-control disagreement) are positive for gemma2 (+15.6), llama (+8.3) and mistral (+5.7) and negative for phi4-mini and qwen, and the plain-control disagreement is partly memory (5.15), so part of the gap is the same phenomenon measured twice. Event selection is not owner-verified; 12 events; the synthetic control is not fresh; one run per cell; local 7B to 9B models plus one API model.

### 5.18 TRACK P. PD v4: memory-free validity gate and a title-assisted memory probe, pre-registered re-evaluation of v2 and v3  `TEXT-DERIVED / SYNTHETIC`

Source: `data/eval/chimera/pd_memory_free_validity.json` (post-hoc table that motivated the gate), `data/eval/chimera/pd_v4/run_*.json`, `analysis.json`; `scripts/chimera/pd_memory_free_validity.py`, `scripts/chimera/pd_v4_memory.py`; `PREREG_PD_v4.md`, `PD_prompts_v4.json`, `MANIFEST_PD_v4.json` (frozen before any probe call). Answers the two weaknesses left by v3. **What is new data and what is not:** the probe calls are new; the v2 and v3 leakage runs and gaps were already seen, so this is a pre-registered *re-evaluation* under rules fixed beforehand, not a new confirmation. Labels: text-derived oracle, model-drafter selection, not owner-verified, no human labels. Spend: Luna probe $0.0041 (93 calls, owner-approved estimate $0.0038); local models free.

**G2, a memory-free validity gate.** A model is valid in a dataset if (a) B-versus-B2 agreement on real plain controls is at least **90%** (two renamed arms, no original names, so memory cannot affect it; inside the owner's 88-95% range) and (b) A-versus-B agreement on unseen synthetic non-reveal items is at least **80%** (memory impossible). Four of six models pass in both v2 and v3 (gemma2, llama, mistral, phi4-mini); Luna (B-versus-B2 89.5% in v2, 85.4% in v3) and qwen (80.9%, 83.3%) fall below the 90% bar. The renaming control is also robust across ciphers: the gap computed against each cipher separately (A-B and A-B2) is positive for all six models in v2 (every interval above 0) and the B-versus-B2 difference in premature naming is 7 points or less in every model and dataset (post hoc, `pd_memory_free_validity.json`).

**M2, a title-assisted closed-book memory probe** (31 events, no passage: the novel's title, the alias and the cast list; renamed arms rename the alias and candidates but keep the title). Names the revealed identity (of 31; 8 needed by the pre-registered binomial rule), original names versus the two ciphers: `gpt-5.6-luna` 25 vs 0 and 0; `llama3.1:8b` 17 vs 4 and 6; `gemma2:9b` 16 vs 3 and 2; `phi4-mini` 16 vs 5 and 3; `mistral:7b-instruct` 11 vs 2 and 2; `qwen2.5:7b` 10 vs 2 and 1. All six models meet the memory rule on the 31 events, and all fall to 0-6 under renaming. (Alias-only probe, for comparison: 2-11 of 19 events.)

**Pre-registered re-evaluation (valid models by G2, pooled gap A minus mean of B and B2, M2 memory among valid models):**

| Dataset | Valid models | Pooled gap | Difference-in-differences (synthetic gap 0.0) | Memory by M2 among valid (need 3) | Verdict |
|---|---|---|---|---|---|
| v2 (19 events) | gemma2, llama, mistral, phi4-mini | **+15.4 pts [10.6, 20.5]** | +15.4 [10.6, 20.5] | 4 | **SUPPORTED** |
| v3 (12 fresh events) | gemma2, llama, mistral, phi4-mini | **+13.4 pts [7.2, 19.9]** | +13.4 [7.2, 19.9] | 3 (gemma2, llama, phi4-mini) | **SUPPORTED** |

The per-event premature rate (original names, valid models) correlates with the number of models that name the event's identity under M2 at Spearman **0.73** (v2) and **0.66** (v3).

**How strong is this, honestly.** (1) It is a re-evaluation: the gaps were seen first, the G2 bars (90% and 80%) were set from the owner's stated range before any probe call but after the gap data, and the v3 books are the only fresh part of the gap evidence (v3 alone, confirmatory under the 80% A-versus-B bar, was PARTIALLY SUPPORTED). (2) Condition (iii) is now easy to meet: the title-assisted probe is satisfied by all six models, including phi4-mini whose own v3 gap is only +2 points, so it shows memory is widespread, not that it explains each model's gap; the event-level correlation is the more informative number. (3) The probe gives the title, which for some books contains a cast name; renamed arms keep the title, and phi4-mini and llama name the identity 4 to 6 times under renaming, so the probe is not perfectly memory-specific. (4) Luna, the reference model, has the largest memory score (25 of 31) and the largest gap, but misses G2 at 90%, so it is outside the pooled estimate; its own v2 and v3 gaps (+35.2 and +18.2) are reported in 5.15 and 5.17. (5) Events are model-selected and not owner-verified; local 7B to 9B models plus one API model; no human labels.

### 5.19 TRACK P. Response to an external adversarial review of the PD claims (post hoc, no new model calls)  `TEXT-DERIVED / SYNTHETIC`

Source: `data/eval/chimera/pd_adversarial_checks.json`, `scripts/chimera/pd_adversarial_checks.py`. An external language model, prompted to be hostile, reviewed the claims; its objections are answered below. Literature it cited (Wang et al. 2023, Luo et al. 2026, Ahn et al. 2024 TimeChara) is **cited by the reviewer, not verified by me**. The checks below are POST HOC and descriptive. Labels remain text-derived, model-selected and not owner-verified.

**A real error found: item-level intervals were too narrow.** Every interval in 5.14-5.18 resampled *items*, but the 8 items of an event share one book, one reveal and one cast, so they are not independent. With the event as the resampling unit:

| Reading | Pooled gap | Event-cluster 95% interval | Events positive / negative / zero | Event sign test |
|---|---|---|---|---|
| v2, G2-valid pool (4 models) | +15.4 | [5.7, 25.7] | 13 / 4 / 2 | p = 0.049 |
| v3, G2-valid pool (4 models) | +13.4 | [1.3, 26.2] | 8 / 2 / 2 | p = 0.11 |
| **All 31 events, G2-valid pool** | **+14.6** | **[6.6, 22.7]** | **21 / 6 / 4** | **p = 0.006** |
| All 31 events, Luna alone | **+28.1** | [17.0, 39.6] | 18 / 1 / 12 | p = 8e-5 |
| All 31 events, every model with G2a at least 80% | +17.2 | [9.8, 24.9] | 23 / 6 / 2 | p = 0.002 |

The pre-registered v2, v3 and v4 verdicts were defined with the item bootstrap and **stand as pre-registered**, but they are now known to rest on a flawed interval; the cluster-corrected reading is that the effect is clearly positive across all 31 events and **borderline within each dataset alone** (v3 alone: lower bound 1.3 points, sign test not significant). The event sign test treats the pooled models as one observation per event, so it is conservative. Per model (event-cluster): Luna +35.2 [20.2, 50.7] in v2 (13 of 13 non-zero events positive), mistral +24.1 in v2, qwen +22.2 in v2; the v3 per-model intervals mostly include 0 (phi4-mini +4.2, mistral +9.9, qwen +9.9).

**Sensitivity to the gate bar (G2a from 70% to 95%, G2b fixed at 80%, event-cluster):** the pooled gap is +19.8 to +19.3 in v2 for bars 70-85% (6 and 5 models), +15.4 at 90% (4 models), +13.0 at 95% (1 model; interval [1.8, 25.3]); in v3 it is +13.4 to +14.6 across all bars. The point estimate is stable, the intervals are wide, and the conclusion does not depend on the particular bar once the cluster interval is used.

**Competence floor (cue-loss partial check).** Keeping only model-event pairs where the model answers that event's plain controls correctly at least 75% of the time in all three arms: v2 all models +17.5 [10.1, 25.9] (92 of 114 pairs, 14 of 17 non-zero events positive, p = 0.013); v2 G2-valid +12.0 [4.0, 21.6] (62 of 76 pairs, p = 0.077); v3 all models +12.2 [0.8, 24.4] (67 of 72 pairs); v3 G2-valid +12.4 [0.5, 25.0]. The gap persists where renaming did not degrade comprehension of that book. This does **not** remove cue loss that leaves control accuracy intact.

**Objection-by-objection (12 objections, 1-12 as numbered by the reviewer):**

| # | Reviewer's objection | Response | Status |
|---|---|---|---|
| 1 | Circularity: the answer is inferable from a 1,200-character window plus a candidate list | Window text and candidates are identical across arms A, B and B2, so inference that does not depend on the name identity cancels in A minus B; the renamed-arm rate (0.5% to 10%) is the inference floor. The "most-mentioned candidate" baseline (8% to 15%) is weak, and a human-answerability baseline does not exist | Partly accepted; no human baseline |
| 2 | Renaming destroys cues (gender, nationality, role), so A minus B measures cue loss | **Accepted as the main open risk.** The cipher renames proper nouns only (pronouns and honorifics untouched), and the competence-floor gap persists; but name-borne cues are lost. The decisive test (cue-preserving, gender- and name-type-matched pseudonyms) was then run as PD v5 (section 5.20): pre-registered verdict MEMORY SURVIVES (strong), recovered fraction -0.11 [-0.36, 0.06] | **Addressed by PD v5; residual: heuristic pseudonyms** |
| 3 | The validity gate was chosen after the gaps | Accepted; v4 is a re-evaluation, not a confirmation; sweep above shows the estimate does not depend on the bar | Accepted, partly mitigated |
| 4 | B-versus-B2 agreement is not memory-free validity | Accepted for the wording: it is a cipher-agreement heuristic (renamed arms contain no original names), not a demonstration of memory-free validity | Wording changed |
| 5 | Forking paths, pseudo-replication, pooled estimates | **Accepted; a real error was found and corrected (table above).** Four analysis versions exist; each had one pre-registered verdict, none discarded; pooled estimates are now descriptive | Corrected |
| 6 | M2 is nearly tautological | Accepted: M2 is a familiarity measure (the title is given); the renamed arms fall to 0-6 of 31, so it is not trivially satisfied, but condition (iii) is easy | Reframed as familiarity covariate |
| 7 | LLM-selected labels, unverified | Accepted and unresolved; the weak-oracle subset analysis (v3: +12.0 [1.0, 23.3] on 40 items) shows the result survives dropping the flagged events. No human verification is planned at present (owner decision) | Open limitation |
| 8 | The event-level correlation could reflect difficulty or fame | Accepted; no partial correlation was computed; fame and memory are the same construct here | Open |
| 9 | Novelty overstated; renaming probes exist | Accepted: the renaming control is established (Jiang and Ferraro, already in the prior-art map); the claimed addition is the memory-free validity check, the positive control and the unseen-text control in the alias-reveal setting, not a first renaming probe. A fuller related-work table is still to be written | Claim narrowed |
| 10 | Engineering audit is weak evidence | Accepted as minor: no resolver precision or recall; a separate persona-stamp repair is recorded elsewhere (see memory note on the prefix-faithfulness worktree; not reviewed here) | Minor |
| 11 | Scope overreach (public domain, Western, small models) | Accepted; claims restricted to this corpus and model set | Accepted |
| 12 | No positive control for the leakage metric | Accepted: the closed-book probe shows memory exists and correlates with the gap, but no constructed case with a verified memorised answer proves the metric fires | Open |

**Claim wording after this review (supersedes the wording in 8b where they differ).** Not: "a validity-gated way to measure identity leakage". Instead: "A renaming-controlled test shows that LLM identity answers on famous public-domain novels drop sharply when names are replaced (about +15 points pooled, +28 for the reference model, positive in 21 of 27 non-zero events), the drop is absent on unseen synthetic text and tracks how well-known the book is, and a cipher-agreement check separates renaming noise from the effect; whether the drop is memorisation or name-borne cue loss is not yet separated." Not "memory-free validity gate" but "cipher-agreement heuristic". Not "premature resolution is due to memorised knowledge" but "is associated with book familiarity under a renaming intervention".

### 5.20 TRACK P. PD v5: cue-preserving rename arm (B3), pre-registered test of the main objection from the adversarial review, five local models  `TEXT-DERIVED`

Source: `data/eval/chimera/pd_v5/run_*.json`, `analysis.json`, `pseudonym_map_audit.json`; `scripts/chimera/pd_v5_cuepres.py`; `PREREG_PD_v5.md`, `MANIFEST_PD_v5.json` (frozen before any B3 call). **The objection (5.19, number 2):** the letter cipher turns names into gibberish and destroys gender and name-type cues, so the gap between original and renamed text might measure lost cues, not name-keyed memory. **The test:** arm B3 replaces only the cast and alias name tokens of each event with natural pseudonyms matched in gender (inferred from the pronouns that follow the name in the book) and name type (first name or surname), keeps every other proper noun ciphered (so places and bystanders stay memory-free), and leaves honorifics, pronouns and all other words untouched; 373 name tokens were mapped (168 male first names, 41 female, 27 unknown-gender neutral, 137 surnames). If cue loss explained the gap, B3 would restore the premature rates of the original text; if memory explains it, B3 stays near the cipher arms. The same 533 items of v2 and v3 were rebuilt from re-downloaded texts (0 of 533 ids, kinds, events or distances differ from the stored runs), and only B3 was newly asked. Labels: text-derived oracle, model-selected events, not owner-verified, no human labels.

**Pre-registered verdict (memory-free-gate pool, four local models, 31 events, event-cluster intervals): MEMORY SURVIVES (strong).** Gap original minus B3 **+16.1 points [8.2, 25.0]**, against +14.6 [7.0, 22.7] for the cipher arms; recovered fraction (rate B3 minus rate B over rate A minus rate B) **-0.11 [-0.36, 0.06]**, below the pre-registered 1/3 line; original names beat B3 in 19 events and lost in 8. All five models, all 31 events: gap A-B3 +16.8 [9.2, 25.4], recovered fraction -0.11 [-0.34, 0.03].

| Model | Gap A-B (v2 / v3) | Gap A-B3 (v2 / v3) | Plain-control accuracy A / B / B3 (v2) |
|---|---|---|---|
| `gemma2:9b` | +13.0 / +25.0 | +17.0 / +28.1 | 98.0 / 83.6 / 96.1 |
| `qwen2.5:7b` | +22.2 / +9.9 | +23.0 / +14.6 | 95.4 / 80.3 / 96.7 |
| `mistral:7b-instruct` | +24.1 / +9.9 | +19.3 / +14.6 | 96.7 / 87.5 / 96.1 |
| `llama3.1:8b` | +14.1 / +14.6 | +14.1 / +16.7 | 90.1 / 85.5 / 92.8 |
| `phi4-mini` | +10.4 / +4.2 | +11.8 / +8.3 | 93.4 / 89.5 / 92.8 |

**The informative contrast.** Cue restoration works on the plain controls: accuracy under the cipher (B) falls 5 to 15 points below accuracy with the original names (A), and under cue-preserving pseudonyms (B3) it returns to the original level (for example qwen 80.3 to 96.7, gemma2 83.6 to 96.1, mistral 87.5 to 96.1). So name-borne cues did damage comprehension on controls, which is the reviewer's mechanism. But restoring them does **not** bring back the premature naming of the hidden identity: the recovered fraction is below zero. What the original names carry that gibberish and gender-matched pseudonyms do not is the specific name, which is what memory is keyed on. The gate G2 and the memory probe M2 results (5.18) point the same way.

**Limits.** Gender and name type are heuristic (pronoun counts and position in the name; unknown-gender women can land in the surname pool); only cast and alias names are pseudonymised by name; pseudonyms are English-style, which shifts nationality cues of foreign names; B3 was designed after the PD v2 to v4 results and the review, so it is a pre-registered test but not blind to those results; B3 removes name-keyed memory only, and a null recovery could in principle also arise if pseudonyms trigger a different "not this book" response (the gap A-B3 slightly exceeds A-B, so B3 elicits at least as few premature answers as the cipher); the pool is four local models; events are model-selected; one run per cell; Luna B3 (run later within the owner's extra budget, $0.0585) shows the same: gap original minus pseudonym +35.6 points on v2 and +18.8 on v3, as large as its cipher gap (+35.2 and +18.2).

### 5.21 TRACK P. PD v6: final pre-registered test on 7 fresh books, and the pooled view of all leakage data  `TEXT-DERIVED / SYNTHETIC`

Source: `data/eval/chimera/pd_v6/run_*.json`, `analysis.json`, `data/eval/chimera/pd_final_pooled.json`; `scripts/chimera/pd_v6.py`, `scripts/chimera/pd_final_pooled.py`; `PREREG_PD_v6.md`, `PD_events_v6_additions.json`, `PD_EVENTS_V6_NOTES.md`, `MANIFEST_PD_v6.json` (frozen before any v6 call). Seven books by seven authors that no earlier step had touched (The Great God Pan, The Man Who Was Thursday, Carmilla, The Pioneers, Graustark, 813 in translation, The Mysteries of Udolpho), 124 items (54 pre-reveal, 14 post-reveal, 56 plain controls), arms A, B, B2 and the cue-preserving B3, the alias-only closed book and the title-assisted probe M2; five local models and Luna ($0.0568 of the owner's extra budget). Valid models by G2 (B-versus-B2 on this set's controls at least 90%, synthetic A-versus-B from PD v3 at least 80%). Labels: text-derived, model-selected, not owner-verified; CM weak, GR medium-weak, PN's identity label ambiguous (`PD_EVENTS_V6_NOTES.md`).

**Pre-registered verdict: NOT SUPPORTED.** Valid models: `llama3.1:8b`, `mistral:7b-instruct`, `phi4-mini`. Pooled gap A-B **-5.9 points [-14.8, 1.0]**, gap A-B3 +4.9 [-1.9, 14.3], 1 event positive and 4 negative (sign test p = 0.375); M2 memory present in only 1 of 3 valid models. None of the three conditions holds. **This is a failure to replicate for the small local models, reported as it fell.**

| Model | G2a (this set) | Valid | Gap A-B [event-cluster 95%] | Gap A-B3 | M2: names identity (of 7; 3 needed) | Renamed |
|---|---|---|---|---|---|---|
| `gpt-5.6-luna` | 83.9% | no (below 90%) | **+16.7 [5.4, 28.6]** | +24.1 | **6** | 0 / 1 |
| `gemma2:9b` | 85.7% | no | -12.0 [-29.6, -1.8] | +5.6 | 3 | 0 / 0 |
| `llama3.1:8b` | 96.4% | yes | -15.7 [-40.7, 4.5] | +5.6 | 3 | 1 / 2 |
| `mistral:7b-instruct` | 94.6% | yes | +1.8 [-8.0, 13.0] | +1.8 | 1 | 0 / 1 |
| `phi4-mini` | 91.1% | yes | -3.7 [-14.4, 4.6] | +7.4 | 1 | 0 / 0 |
| `qwen2.5:7b` | 87.5% | no | 0.0 [-16.1, 14.3] | +18.5 | 1 | 1 / 1 |

**Pooled, event-cluster view of all leakage data (v2, v3, v6; `pd_final_pooled.json`).**

| Pool | Events | Gap A-B [95%] | Events positive / negative | Sign test |
|---|---|---|---|---|
| Valid local models, v2 | 19 | +15.4 [5.9, 26.3] | 13 / 4 | 0.049 |
| Valid local models, v3 | 12 | +13.4 [1.2, 26.3] | 8 / 2 | 0.11 |
| Valid local models, **v6** | 7 | **-5.9 [-14.8, 1.0]** | 1 / 4 | 0.375 |
| Valid local models, fresh books (v3 + v6) | 19 | +7.7 [-2.0, 18.2] | 9 / 6 | 0.61 |
| Valid local models, all three sets | 38 | +11.5 [4.5, 19.0] (cue-preserving +14.5 [7.3, 22.2]) | 22 / 10 | 0.050 |
| All models with G2a at least 80%, all three sets | 38 | +13.6 [7.0, 20.5] | 26 / 8 | 0.003 |
| **Luna alone, v2** | 19 | **+35.2 [20.2, 50.0]** | 13 / 0 | 0.0002 |
| **Luna alone, v3** | 12 | +18.2 [4.2, 33.9] | 5 / 1 | 0.22 |
| **Luna alone, v6** | 7 | **+16.7 [5.4, 28.6]** | 4 / 0 | 0.125 |
| **Luna alone, fresh books (v3 + v6)** | 19 | **+17.7 [8.0, 28.3]** (cue-preserving +20.7 [9.5, 32.9]) | 9 / 1 | 0.021 |
| **Luna alone, all three sets** | 38 | **+26.0 [16.8, 36.0]** (cue-preserving +27.7 [18.6, 37.9]) | 22 / 1 | 1e-5 |

**Reading, honestly.** (1) The effect is **strong and consistent for the reference model**: Luna's gap is positive in all three datasets, survives on the fresh books (+17.7 [8.0, 28.3], 9 events positive against 1), and its cue-preserving gap is as large as its cipher gap (Luna B3, run on v2 and v3 at $0.0585: +35.6 and +18.8 points). (2) It is **weaker and inconsistent for the four small local models**: positive on v2 and v3, absent on v6 (pre-registered NOT SUPPORTED), and +11.5 pooled over all 38 events with a sign test at the 0.05 line. (3) The v6 books are **less famous**, and the small models recognise them poorly: M2 names 1 to 3 of 7 events for the local models against 6 for Luna, whereas the v2/v3 sets gave the local models 10 to 17 of 31; the pattern (effect where the model knows the book, none where it does not) fits the memory reading and is also what a weak, noisy effect would look like, so it does not by itself confirm it. (4) The pre-registered v6 pool excluded Luna because Luna misses the 90% gate by 6 points (83.9%); under the 80% bar the owner set earlier for v3, Luna is valid. (5) With 7 events the test has low power (stated in advance); a null for small models here is not proof of absence, but it is not support either.

**Consequence for the claim.** The supportable statement is now: *identity naming that depends on the original names is clearly present for the strongest model tested and across the full 38-event set, and is weaker and not reliably replicated for small local models on less-famous books.* The earlier wording that the effect holds across models is withdrawn.

### 5.22 TRACK P. Dose-response across all 38 events: the leakage gap rises with how well the book is recognised (post hoc, no new model calls)  `TEXT-DERIVED`

Source: `data/eval/chimera/pd_dose_response.json`, `scripts/chimera/pd_dose_response.py`. **Predictor ("recognition"):** how many of the five local models name the revealed identity under the title-assisted probe M2 with the original names (0 to 5), from the PD v4 and v6 runs. **Outcomes:** (a) Luna's per-event gap (original minus renamed), a different model family from the predictor; (b) the memory-free-gate local pool's per-event gap (same family as the predictor, so not independent). Spearman correlation across the 38 events with a 20,000-shuffle permutation p-value. Post hoc and descriptive; events are model-selected and not owner-verified.

| Recognition count (local models naming the identity) | Events | Mean gap, Luna | Mean gap, valid local pool |
|---|---|---|---|
| 0 | 10 | +8.8 | +0.3 |
| 1 | 10 | +20.6 | +1.0 |
| 2 | 4 | +37.5 | +1.8 |
| 3 | 2 | +31.3 | -4.7 |
| 4 | 5 | +47.5 | +15.6 |
| 5 | 7 | +29.5 | **+40.9** |
| **Spearman (permutation p)** | 38 | **+0.37 (0.024)**; without v2 +0.42, without v3 +0.23, without v6 +0.39 | **+0.59 (0.00015)**; without v2 +0.35, without v3 +0.56, without v6 +0.70 |

**Reading.** The leakage gap behaves like a dose-response to book familiarity. For the small local models it is about zero (-5 to +2 points) on books that at most two of them recognise and large (+41 points) on books all five recognise, which also explains the PD v6 result: the seven v6 books are poorly recognised by the small models (1 to 3 of 7 events), so a near-zero gap there is what the pattern predicts, not a contradiction. The cross-family version (Luna's gap against the local models' recognition) is weaker but positive and survives dropping any one dataset (+0.23 to +0.42). **Caveats:** post hoc; the local-pool correlation shares models with its predictor, so only the Luna version is a cross-family check; recognition is measured with the title given, and for some books the title contains a cast name; cells with 2 to 5 events are noisy (the mean of Luna's gap is not monotone: +47.5 at four, +29.5 at five); correlation is moderate; a familiarity confound with other book properties (length, prose style, quote density) is not excluded; this is evidence consistent with memory, not a demonstration of the mechanism.

### 5.23 TRACK P. PD CONFIRM v2: pre-registered confirmatory run on 68 events from 65 books, three open models (CONFIRMATORY; E2, E4, E5 and the OLMo check EXPLORATORY-small)  `TEXT-DERIVED`

**Design.** `PREREG_PD_CONFIRM_v2_L40S.md` with addenda 1 to 5 (frozen by SHA-256 manifests before mining; addendum 4 enlarged the book rounds after yield 8 events from 326 books; addendum 5, written before any model saw an event, made the fame contrast P1 the primary hypothesis and H1 to H3, H5 secondary). Books: 3,523 eligible Gutenberg books in fame bands by Wikidata sitelinks (high W >= 20, mid 3 to 19, low < 3). Events: mined by `qwen32b` with frozen cues and deterministic verification, audited by `mistral24` (42 EXPLICIT, 21 IMPLIED, 5 NOT_SUPPORTED); 68 events from 65 books (53 test, 15 development); primary set 32 EXPLICIT test events (25 low, 6 mid, 1 high fame). Models: Qwen2.5-32B (AWQ), OLMo-2-32B (fp8), Mistral-Small-3.2-24B (fp8) by vLLM on one L40S at temperature 0; 2,220 E1 calls per model. Provenance: text-derived oracle, model-selected and model-audited events (the selector and the auditor are evaluated models), no human labels.

**Results (primary set; percentage points; 95% event-bootstrap intervals).**

| Model | Gap A-B | CI | Gap A-B3 | Events +/- |
|---|---|---|---|---|
| mistral24 | +4.4 | [-2.3, +12.0] | +9.9 | 4/2 |
| olmo32b | +0.0 | [-4.4, +4.9] | +5.5 | 2/3 |
| qwen32b | -0.8 | [-4.7, +2.3] | +3.4 | 1/1 |

| Test | Estimate | One-sided p | Verdict |
|---|---|---|---|
| P1 (primary): gap high+mid minus low fame | +7.6 [-1.4, +18.3]; 7 against 25 events; minimum detectable 12.8 | 0.060 | not passed |
| H1: pooled A-B | +0.1 [-5.0, +5.2] | 0.468 | not passed (3 of the 4 required models only) |
| H2: pooled A-B3 | +5.7 [-1.3, +12.6] | 0.036 | not passed |
| H3: Spearman fame vs gap | +0.30 (32 events, 31 books) | 0.041 raw, 0.145 Holm | raw rule met, not confirmed after Holm |
| H5: pseudonymisation (P2) | pre-reveal premature naming 5.0% to 2.6%; post-reveal accuracy -6.7 [-13.3, -2.2]; control accuracy -15.6 [-22.9, -8.9] | 0.037 | not met (utility outside the 5-point margin) |

Closed-book recovery of the identity: 2 of 68 events for each model. E5 (24 events, 3 models, 144 outputs per condition): 0 spoilers detected in every condition; second-model faithfulness check 90.0% to 90.9% supported. E2 (17 verified LLM-authored stories): gaps +0.0, +1.5 [0.0, +4.4], -1.5 [-4.4, 0.0] (Mistral, OLMo, Qwen). OLMo training-data check (infini-gram on the OLMo-2 1124 corpus, 62 books, 50 with a gap): Spearman +0.13, permutation p = 0.41; mean gap +2.9 for books present against +1.0 absent. Claude Sonnet 5.5 arm: stopped by the subscription session limit after 211 of 1,218 answers (8 events), excluded from all pooled tests (`PD_CONFIRM_deviations.md`).

**Reading.** The confirmatory run does not detect the effect on a sample dominated by obscure books and does not resolve the fame contrast. It is consistent with the exploratory dose-response (no memory to leak when the books are not recognised) and it does not contradict the famous-book results; it bounds the pooled gap on obscure books at about 5 points. Nothing in it shows that the effect is absent on famous books; the high band was exhausted with 2 events. E5 and the OLMo link are nulls under narrow detectors. Source: `data/eval/chimera/confirm/{main,e2}/analysis.json`, `olmo_corpus_check.json`; tables by `python scripts/chimera/gen_ch1_tables.py`.

### 5.24 TRACK P. RF-E2E: a whole-volume LLM character card leaks the reveal; the versioned card fixes it (pre-registered, addenda 6 and 7)  `TEXT-DERIVED / MODEL-JUDGED`

**Design.** Same 68 frozen events and cuts as 5.23. Card for the aliased character (at most 80 words, one fixed prompt) from up to 12 passages around alias mentions: W = whole volume, P = prefix only (clipped at the cut; equals the versioned build). Arms: original names and the frozen letter cipher. Leak rule A (text-derived, primary): the card contains an identity token never seen in the prefix (19 events). Rule B (secondary): judge `qwen3:8b` (not a generator) says the card identifies alias with identity (54 events). Fix 2: prefix card from E4-P2 pseudonyms, mapped back. Local ollama models at temperature 0, $0.


#### Small local models (7 to 8B; addenda 6 and 7)
Models finished: ['llama3.1:8b', 'mistral:7b-instruct', 'qwen2.5:7b'] not run: [] judged: ['llama3.1:8b', 'mistral:7b-instruct', 'qwen2.5:7b']

**Rule A (text-derived), primary set: 19 events.** Leak rate (% of events) per cell; input channel = W-ren minus P-ren; memory channel = P-orig minus P-ren.

| Model | W-orig | W-ren | P-orig | P-ren | Input channel [95% CI] | Events W-ren > P-ren / < | Memory channel [95% CI] |
|---|---|---|---|---|---|---|---|
| Llama-3.1-8B | 36.8 | 31.6 | 0.0 | 0.0 | +31.6 [+10.5, +52.6] | 6 / 0 (p = 0.0156) | +0.0 [+0.0, +0.0] |
| Mistral-7B | 31.6 | 21.1 | 0.0 | 0.0 | +21.1 [+5.3, +42.1] | 4 / 0 (p = 0.0625) | +0.0 [+0.0, +0.0] |
| Qwen2.5-7B | 26.3 | 21.1 | 0.0 | 0.0 | +21.1 [+5.3, +42.1] | 4 / 0 (p = 0.0625) | +0.0 [+0.0, +0.0] |
| **Pooled (mean over models)** | 31.6 | 24.6 | 0.0 | 0.0 | +24.6 [+8.8, +42.1] | 3 of 3 models positive | +0.0 [+0.0, +0.0] |

RF1 SUPPORTED; RF2 validity P-ren rate 0.0% (valid); RF4 W-orig minus P-orig +31.6 [+14.0, +50.9].

**Rule B (judge), EXPLICIT and IMPLIED events: 54 events.** Leak rate (% of events) per cell; input channel = W-ren minus P-ren; memory channel = P-orig minus P-ren.

| Model | W-orig | W-ren | P-orig | P-ren | Input channel [95% CI] | Events W-ren > P-ren / < | Memory channel [95% CI] |
|---|---|---|---|---|---|---|---|
| Llama-3.1-8B | 27.8 | 27.8 | 3.7 | 3.7 | +24.1 [+11.1, +37.0] | 14 / 1 (p = 0.000488) | +0.0 [+0.0, +0.0] |
| Mistral-7B | 13.0 | 11.1 | 5.6 | 0.0 | +11.1 [+3.7, +20.4] | 6 / 0 (p = 0.0156) | +5.6 [+0.0, +13.0] |
| Qwen2.5-7B | 16.7 | 16.7 | 1.9 | 0.0 | +16.7 [+7.4, +27.8] | 9 / 0 (p = 0.00195) | +1.9 [+0.0, +5.6] |
| **Pooled (mean over models)** | 19.1 | 18.5 | 3.7 | 1.2 | +17.3 [+9.3, +26.5] | 3 of 3 models positive | +2.5 [+0.0, +5.6] |

RF1 SUPPORTED; RF2 validity P-ren rate 1.2% (valid); RF4 W-orig minus P-orig +15.4 [+6.8, +25.3].
A_EXPLICIT_only: events 11, input +27.3 [+6.1, +51.5], passes True
B_EXPLICIT_only: events 38, input +20.2 [+10.5, +30.7], passes True

**Fixes.**

| Fix | Rule | Events | Leak before | Leak after | Removed [95% CI] | Content check |
|---|---|---|---|---|---|---|
| Versioned card (fix 1), orig names | A | 19 | 31.6% | 0.0% | +31.6 [+14.0, +50.9] | alias named 86.0% vs 82.5%; 94 vs 86 words |
| Versioned card (fix 1), ren names | A | 19 | 24.6% | 0.0% | +24.6 [+8.8, +42.1] | alias named 86.0% vs 82.5%; 94 vs 86 words |
| Versioned card (fix 1), orig names | B | 54 | 19.1% | 3.7% | +15.4 [+6.8, +25.3] | alias named 85.2% vs 82.7%; 93 vs 89 words |
| Versioned card (fix 1), ren names | B | 54 | 18.5% | 1.2% | +17.3 [+9.3, +26.5] | alias named 85.2% vs 82.7%; 93 vs 89 words |
| Pseudonymise and map back (fix 2) | A | 19 | 0.0% | 0.0% | +0.0 [+0.0, +0.0] | alias named 82.5% vs 87.7%; RF5 evaluated False, passes None |
| Pseudonymise and map back (fix 2) | B | 54 | 3.7% | 3.1% | +0.6 [-1.9, +3.7] | alias named 82.7% vs 87.7%; RF5 evaluated False, passes False |

Second judge (OLMo-2-32B, addendum 9, robustness only): W-ren 19.1% vs P-ren 1.9%, input channel +17.3 [+8.6, +27.2] over 54 events. Agreement with the first judge: 97.8% identical labels, kappa 0.88 (684 labels).

#### Larger open models (24 to 32B on the pod; addendum 8, separate stratum)
Models finished: ['mistral24', 'qwen32b'] not run: [] judged: ['mistral24', 'qwen32b']

**Rule A (text-derived), primary set: 19 events.** Leak rate (% of events) per cell; input channel = W-ren minus P-ren; memory channel = P-orig minus P-ren.

| Model | W-orig | W-ren | P-orig | P-ren | Input channel [95% CI] | Events W-ren > P-ren / < | Memory channel [95% CI] |
|---|---|---|---|---|---|---|---|
| Mistral-Small-3.2-24B | 26.3 | 26.3 | 0.0 | 0.0 | +26.3 [+5.3, +47.4] | 5 / 0 (p = 0.0312) | +0.0 [+0.0, +0.0] |
| Qwen2.5-32B | 15.8 | 15.8 | 0.0 | 0.0 | +15.8 [+0.0, +31.6] | 3 / 0 (p = 0.125) | +0.0 [+0.0, +0.0] |
| **Pooled (mean over models)** | 21.1 | 21.1 | 0.0 | 0.0 | +21.1 [+5.3, +39.5] | 2 of 2 models positive | +0.0 [+0.0, +0.0] |

RF1 SUPPORTED; RF2 validity P-ren rate 0.0% (valid); RF4 W-orig minus P-orig +21.1 [+5.3, +39.5].

**Rule B (judge), EXPLICIT and IMPLIED events: 54 events.** Leak rate (% of events) per cell; input channel = W-ren minus P-ren; memory channel = P-orig minus P-ren.

| Model | W-orig | W-ren | P-orig | P-ren | Input channel [95% CI] | Events W-ren > P-ren / < | Memory channel [95% CI] |
|---|---|---|---|---|---|---|---|
| Mistral-Small-3.2-24B | 27.8 | 31.5 | 1.9 | 3.7 | +27.8 [+16.7, +40.7] | 15 / 0 (p = 3.05e-05) | -1.9 [-9.3, +3.7] |
| Qwen2.5-32B | 14.8 | 14.8 | 1.9 | 0.0 | +14.8 [+5.6, +24.1] | 8 / 0 (p = 0.00391) | +1.9 [+0.0, +5.6] |
| **Pooled (mean over models)** | 21.3 | 23.1 | 1.9 | 1.9 | +21.3 [+13.0, +30.6] | 2 of 2 models positive | +0.0 [-3.7, +4.6] |

RF1 SUPPORTED; RF2 validity P-ren rate 1.9% (valid); RF4 W-orig minus P-orig +19.4 [+9.3, +30.6].
A_EXPLICIT_only: events 11, input +18.2 [+0.0, +36.4], passes False
B_EXPLICIT_only: events 38, input +25.0 [+14.5, +36.8], passes True

**Fixes.**

| Fix | Rule | Events | Leak before | Leak after | Removed [95% CI] | Content check |
|---|---|---|---|---|---|---|
| Versioned card (fix 1), orig names | A | 19 | 21.1% | 0.0% | +21.1 [+5.3, +39.5] | alias named 84.2% vs 78.9%; 91 vs 81 words |
| Versioned card (fix 1), ren names | A | 19 | 21.1% | 0.0% | +21.1 [+5.3, +39.5] | alias named 84.2% vs 78.9%; 91 vs 81 words |
| Versioned card (fix 1), orig names | B | 54 | 21.3% | 1.9% | +19.4 [+9.3, +30.6] | alias named 84.3% vs 80.6%; 90 vs 82 words |
| Versioned card (fix 1), ren names | B | 54 | 23.1% | 1.9% | +21.3 [+13.0, +30.6] | alias named 84.3% vs 80.6%; 90 vs 82 words |
| Pseudonymise and map back (fix 2) | A | 19 | 0.0% | 0.0% | +0.0 [+0.0, +0.0] | alias named 78.9% vs 81.6%; RF5 evaluated False, passes None |
| Pseudonymise and map back (fix 2) | B | 54 | 1.9% | 2.8% | -0.9 [-4.6, +1.9] | alias named 80.6% vs 84.3%; RF5 evaluated False, passes False |

Second judge (OLMo-2-32B, addendum 9, robustness only): W-ren 22.2% vs P-ren 0.9%, input channel +21.3 [+13.0, +30.6] over 54 events. Agreement with the first judge: 97.8% identical labels, kappa 0.89 (456 labels).


**Measurement checks (post hoc, no model calls).** Judge vs the text-derived rule over 380 card labels: sensitivity 91.7%, false-positive rate 0.9%, kappa 0.92. Exposure: a leaking whole-book card is visible for a median 11.4% of the book before the reveal.

**Robustness (addendum 10, Qwen2.5-7B).** Rule A (text): with the instruction the whole-volume card still leaks in 15.8% (renamed) and 21.1% (original) against 21.1% and 26.3% without it; the remaining gap to the versioned card (+15.8 points) is not significant at 19 events (95% lower limit 0.0); with the second cipher the input channel is +31.6 [+10.5, +52.6], robust to the cipher. Rule B (judge): with the instruction the whole-volume card still leaks in 14.8% (renamed) and 18.5% (original) against 16.7% and 16.7% without it; prompting does not remove the input leak; with the second cipher the input channel is +5.6 [-5.6, +18.5], not shown robust to the cipher (the judge flags 7.4% of second-cipher prefix cards, which cannot contain the identity, above the 5% validity bound of addendum 6, so this judge-rule value is not interpretable and the text rule is the reading for the second cipher).

**Reading.** RF-E2E (pre-registered, addenda 6 and 7, written before any card was read): on 54 confirmatory reveal events, a whole-volume LLM character card stamped at first mention names the hidden identity before the reveal in 18.5% of events under cipher names no model has seen (judge rule; strict text rule 24.6% of 19), against 1.2% for the versioned (prefix-built) card. Input-channel RF1 SUPPORTED on the primary text rule (+24.6 [+8.8, +42.1]) and SUPPORTED on the judge rule (+17.3 [+9.3, +26.5]); memory-only leak +2.5 [+0.0, +5.6]. Pseudonymise-and-map-back: prefix-card leak 3.7% to 3.1% (RF5 not evaluated: no memory leak to fix). Models: llama3.1:8b, mistral:7b-instruct, qwen2.5:7b; not run: none. Larger open models (mistral24, qwen32b, addendum 8): W-ren 23.1% vs P-ren 1.9%; memory-only leak +0.0 points. Limits: one prompt and one reader position per event, small local models, rule B labelled by a model, model-selected events. Source: `data/eval/chimera/rf_e2e/analysis.json`; `python scripts/chimera/pd_rf_e2e.py analyze`.

## 6. What each test could have falsified, and what happened

| Test | Could have falsified | Outcome |
|---|---|---|
| T4 renaming validity (pre-registered v1-v3) | That a token-level renaming control commutes with the repository's normalisers | **Failed its pre-run gate twice** (v2: G1=8, G2=25; v3: G1=2, G2=9, G3=0 on 335 surfaces; `data/eval/chimera/t4_results.json`). The owner decided no v4. Finding: a token-level renaming control cannot be made to commute with the repo's normalisers without further design; **control not validated**. The violation classes (display and class-splitting cases such as "Thunderwings" and compound Gu names) are the finding. |
| SIO prefix-causality | That the resolver's mention layer is not prefix-causal | **Not falsified** on these structures (M1 0/3741); but the test is weak where the resolver ignores reveals (M2 is vacuous). |
| SIO retroactive title link | That titles are linked only from what the prefix contains | **Falsified as pre-declared** (M4 40/40): the first holder is extended back to chapter 1 by design. |
| Silver pilot | That detection is not the bottleneck | **Not falsified**: 51% of silver-labelled hard items undetected. |
| L1 renaming validity (R1) | That prompt-only renaming changes answers on plain controls | **Not falsified: valid.** Original and renamed prompts gave the same letter on 30 of 30 plain controls. |
| L1 primary (R2), n = 4 | That the model names the silver final identity from a prefix that does not entitle it | **Inconclusive by pre-registration.** Original 4/4, renamed 0/4, gated 0/4. Exact upper bound with 0 of 4 is 52.7%. |
| L1 leakage A minus B (62 items) | That renaming does not change accuracy against silver | **Gap present:** +9.7 points, bootstrap 95% CI [3.2, 17.7]; 6 items differ, all in the same direction. Interpretable because R1 is valid; confounded by the silver labels coming from a model (section 7). |
| L1 closed-book (R3) | That the model resolves aliases above chance with no passage | **Not supported for this model.** 1/15 correct (chance about 0.10, exact p = 0.79); 14/15 abstentions in both original and renamed. Narrows the claim to this model and prompt. |
| L1 gating (R4) | That gating removes premature naming without destroying correct links | **Falsified as implemented.** Controls: 14/30 gated vs 29/30 ungated (-50 points). It did block 4/4 premature answers. |
| PD pre-registered leakage test (public-domain novels, 5 models run) | That renaming does not change premature identity naming where memory is demonstrable | **Verdict NOT SUPPORTED as pre-registered:** only `gpt-5.6-luna` passes the renaming-validity gate, with gap +7.0 pts, CI [0.0, 16.3], below the +10 threshold. The closed-book positive control works (4 of 5 models name the identity for 3 of 7 events; 0 of 7 once renamed). The four other models fail renaming validity (57% to 86% agreement), so their larger gaps (+9 to +44 pts) are not attributable to memory. |
| PD v2 pre-registered leakage test (19 books, 5 local models, repaired controls) | That renaming does not change premature identity naming where memory is demonstrable | **INCONCLUSIVE as pre-registered:** no model reaches the 95% renaming-validity gate (best 88.2%); format noise fixed (0 invalid), but plain controls on famous books are themselves memory-assisted (asymmetric A-over-B disagreement for gemma2, mistral, qwen). Descriptive: all five show a positive gap (+10 to +24) and 0.0 on unseen text. |
| E6 persona-stage prefix causality | That the persona stage adds nothing the prefix does not entitle | **Falsified:** 23 of 288 character-cuts differ (8.0%); 46% of the cast after LOTM chapter 5. |

## 7. Limitations

- **Labels.** Silver only for the real novel; no human label exists yet; single annotator when it does; no agreement statistic will be claimed (one annotator, so no kappa).
- **Model-drafted gold elsewhere.** All six repository gold files are model-drafted; the 89 hard cases and the 288-item pre-labelled package are model output.
- **Selection.** Pilot items are chosen, not sampled. Only 3 system-derived pre-reveal mentions exist in the RI database.
- **Power.** n = 23 pre-reveal candidates; effects below about 12-22% are not detectable.
- **Synthetic scope.** SIO is templated English with one name per alias chapter; it shows mechanism properties, not real-world rates. A generator flaw is logged.
- **One LLM, one serial, one phrasing, one run per arm.** L1 used `gpt-5.6-luna` only; temperature and seed were not sent (the model page does not mention them), so determinism is not guaranteed. A null or a gap for one model does not transfer to others.
- **Silver labels and shared memory.** The reference labels were drafted by another model that may share memorised knowledge of this serial, so agreement with them can partly reflect shared memory, not correctness.
- **Candidate lists anchor.** Every list was built to contain the silver answer plus decoys; a choice among about 11 names is easier than open resolution.
- **n = 4 primary items.** Only 4 pre-reveal items have a repo-derived reveal chapter; for one of them (CP-017) the revealed name is already in the prefix window, so it is not clean premature naming.
- **Public exposure.** The public branch exposes short excerpts (mean 74.8 characters, median 35, max 145) of gold-set text and review files. This is the owner's decision and is information only.
- **Source texts** are copyrighted EPUBs held locally and not committed; no novel text appears in any file produced for this report.

## 8. Novelty assessment

**Rating against the gate** (formal task; one novelty sentence; closest work and difference; strongest baseline; falsifiable outcome):

| Gate item | Assessment |
|---|---|
| Formal task | **Met on paper.** Alias-to-identity linking under a chapter prefix, scored by premature-resolution rate against a reader-warranted oracle (section 4.1). |
| One novelty sentence | "A premature-resolution rate for alias-to-identity linking under a chapter prefix, with leakage defined as its change under consistent renaming, and an evidence-gated rule that must cite prefix spans, for translated web serials." **Narrow**, and each ingredient has precedent. |
| Closest work and difference | Jiang & Ferraro (renaming control), KoCoNovel (dual labels), NarraWorld (premature-disclosure aim), TimeChara (leakage premise). The difference is the assembly and the metric, not any ingredient. |
| Strongest baseline | Whole-input renaming alone (Jiang & Ferraro style) and chapter-filtered context (TimeChara's RAG-cutoff). **Defined, not run.** |
| Falsifiable outcome | The gated rule's rate is not lower than renaming-only on the same items. **Specified, not run.** |

**What is new, what is engineering, what overlaps.**

- *Possibly new, unevidenced:* the premature-resolution metric as defined, and its use on reveal-bearing translated serials. No supporting number exists in this work.
- *Engineering:* the bitemporal graph, the reader-observer `state_of`, the pre-filter-driven resolver, the pilot tooling. These are substantial but are not claimed as research novelty.
- *Overlaps prior work:* renaming as a leakage control; reader/omniscient dual labels; disclosure-aware chapter-safe memory; valid-time tracking.
- *Supported by evidence:* the failure audit (C5): detection loss, a scorer that links nothing, and event/binding timestamp inconsistencies, in silver, synthetic and system-internal form.

**Verdict: audit-plus-pilot report with a first pilot signal.** C5 is supported. C1a has a directional, pre-registered-inconclusive signal on one model (valid renaming control; 4/4 vs 0/4 on four items; +9.7 points on 62 items), all silver. C1b as implemented is not supported (over-rejects). The closed-book memorisation probe is null for this model. No contribution yet has an adequately powered, human-labelled result; the report should be read as a precise problem statement, an honest prior-art map, a reproducible audit, a pilot signal and a pilot sheet ready for human labels.

## 8a. Novelty points for the report (status as of 2026-10-16, labels treated as final for now)

Labels from the good models are treated as final for this report (owner decision); the owner will update them at the weekend, and the metrics may change. Each point carries its evidence tier and its closest overlap, so the professor can see what is claimed and what is not.

| # | Point | Evidence tier | What it rests on | Closest prior work and the difference | Weak spot |
|---|---|---|---|---|---|
| 1 | **A reader-warranted-versus-final-truth identity metric, validated for construct validity.** Premature-resolution rate against a reader-entitled oracle, with leakage defined as the change under consistent renaming; the metric separates systems by construction and exposes a resolver whose reveal detector is brittle. | Synthetic (labels by construction) | SIO, M3, M3b (sections 5.1, 5.5, 5.6) | KoCoNovel (dual labels), TimeChara (leakage premise), Jiang and Ferraro (renaming). The assembly and the metric are the contribution, not an ingredient. | Synthetic worlds are templated; no human-labelled real result yet. |
| 2 | **A text-derived reveal oracle with a closed-book positive control and an unseen-text control.** The reveal is an explicit sentence found by exact search, so the oracle needs no model judgement and any reader can re-check it; the closed-book probe shows when a model carries memory of a text, and the renamed arm shows the control removes it. | Text-derived (selection by model-drafter, owner check pending) | PD benchmark (section 5.14): 4 of 5 models name the identity for 3 of 7 events from the alias alone; 0 of 7 once renamed | Renaming controls exist (Jiang and Ferraro); a positive control for memory in a leakage test is the added piece. | 7 events; selection not owner-verified; one run per cell. |
| 3 | **Renaming controls are not free: validity must be measured per model.** On real classic prose, 4 of 5 models changed their answer under consistent renaming on 14% to 43% of plain controls, against 5% for Luna; a leakage gap from such a model mixes memory with renaming damage. A per-model validity gate (R0) and an unseen-text control are therefore necessary. | Text-derived and synthetic | Section 5.14 R0 column; diagnosis in `r0_diagnosis_exploratory.json` | Prior renaming-control work reports the gap; I did not find a per-model validity gate in the papers read (not an exhaustive search). | 21 controls, one-item resolution of 4.8 points; the diagnosis is post hoc. |
| 4 | **A multi-novel audit of a deployed resolver.** The scorer links no mention to an existing entity in any of three serials (0 of 10, 16 and 8 groups); the repository reveal detector recovers at most about 10% of silver reveal cases (real-text counterpart of the synthetic brittleness); the token-level renaming failure was corpus-specific, not engine-wide. | System-internal counts; silver for the recall bound | Sections 5.3, 5.13 | An audit of one system, not a general result. | Silver recall bound; LOTM and ORV are 40-chapter partials. |
| 5 | **Method: gate-versus-engine diagnosis and pre-registered negatives.** Every failed gate was attributed to the gate, the engine or the model before being called a finding; three earlier misattributions were found and corrected in the record. | Process | `GATE_FAILURE_DIAGNOSIS.md`, sections 5.9 to 5.13 | Not a research result; a reproducibility asset. | Process, not evidence. |

**What is not claimed.** No result shows that EchoTales or any web-serial resolver leaks memorised identities; the pre-registered leakage test on public-domain novels came out **not supported** (only one model passed validity, with a gap of +7.0 points, below the threshold). C1b (evidence gate) is not supported as implemented. No point rests on a human label yet. Points 2 and 3 are the strongest candidates for a short methods paper if the weekend labels and a larger control set hold up; point 1 and point 4 are supporting.

### 8b. Ranked novelty points after the engineering probes and PD v2 (v1.0, 2026-10-16)

Supersedes the order of 8a; the rows of 8a stay as the evidence-tier detail. No human annotation is assumed in this report (owner decision, 2026-10-16): labels are text-derived or label-free, and `gpt-5.6-luna` is the reference comparator because it is the only model that passed the pre-registered renaming-validity gate in v1. Metrics may change if the design is revised.

| Rank | Point | Tier | Evidence | Closest prior work (unverified where marked) | Weak spot |
|---|---|---|---|---|---|
| 1 | **Truncate-and-rebuild prefix-causality audit of a narrative knowledge graph, with measured look-ahead.** The resolver is exactly prefix-causal (0 of 28,165 comparisons); by-design volume passes are not (up to 39% of early mentions in LOTM); the persona stage is not (8.0% of character-cuts, 46% of the cast after chapter 5 of LOTM) because gender is stamped from later pronoun evidence. | A: measured, defensible as an audit | E1, E6 (section 5.16); E6 headline re-summed from stored JSON | temporal look-ahead leakage tests; TimeChara (LLM); CALM/monotonicity, metamorphic testing, incremental coreference (from memory, unverified) | truncate-and-rebuild is a standard protocol, so the novelty is the application and the measured size; correctness of the personas is not measured; gender-from-later-evidence may be a design convention |
| 2 | **(v1.2) A renaming-controlled, memory-gated leakage benchmark; the pre-registered re-evaluation with a memory-free validity gate and a title-assisted memory probe is SUPPORTED on v2 (+15.4 [10.6, 20.5]) and v3 (+13.4 [7.2, 19.9]); the earlier, fuller description follows.** A renaming-controlled leakage benchmark on public-domain novels with a closed-book positive control and an unseen-text control; confirmed in direction on 12 fresh books (pre-registered PARTIALLY SUPPORTED, unchanged with the reference model Luna: pooled gap +12.7 points [6.8, 19.0] local, +13.6 with Luna, zero on unseen text, correlated 0.80 with how well-known each book is); on v2 the reference model shows a large, event-dependent gap (Luna +35.2 points [27.0, 43.0]; 46 of 92 premature on the 12 new events, 3 of 43 on the original 7), zero on unseen text; and plain controls on famous books are not a memory-free validity test.** | A: methods contribution with a direction supported at lenient bars | PD v1 and v2 (5.14, 5.15): memory in 5 of 6 models (6 to 11 of 19 events), 0-4 after renaming; synthetic gap 0.0 for all; pre-registered verdict INCONCLUSIVE at 95%, PARTIALLY SUPPORTED at 85% and SUPPORTED at 80% (post hoc); gate failure is asymmetric toward the original-names arm | Jiang and Ferraro (renaming), TimeChara (leakage premise) | pre-registered verdict INCONCLUSIVE; the 80% reading is post hoc; event selection unverified; a confirmation needs a new pre-registration with fresh items (PD v3, 12 unused books, now run: PARTIALLY SUPPORTED, section 5.17) |
| 3 | **On these serials the resolver reduces to a normalised-string lookup plus about 3% to 5% alias merging; the "gazetteer compounds" claim is memoisation.** With the earlier "scorer links nothing" and "reveal detector recovers at most about 10%" findings. | B: descriptive system audit | E5, E2, 5.13 | lexical and most-frequent baselines | no precision labels; system-specific |
| 4 | **Observer-global retraction in the bitemporal model:** one reader-discourse `retracted_at` cannot record that a character never learned a claim was false. | B: model-level point, latent in the data | E3 (synthetic spec oracle) | dynamic epistemic logic with private announcements, belief revision, bitemporal databases (from memory, unverified) | no real-data instance |
| 5 | Construct validity of the premature-resolution metric (synthetic), the multi-novel audit and the gate-versus-engine method. | B/C | 5.1, 5.5, 5.6, 5.13, GATE_FAILURE_DIAGNOSIS | KoCoNovel, SynthWorlds, LitBank | synthetic; process |
| - | Discourse-position order is not a total order (E4). | engineering, not novelty | 5.16 | - | no downstream error today |

**Not claimed.** No evidence that EchoTales or any web-serial resolver leaks memorised identities; the PD leakage verdicts are NOT SUPPORTED (v1) and INCONCLUSIVE (v2). C1b (evidence gate) is not supported as implemented. Every number is text-derived, synthetic or label-free; none is human-labelled. Honest overall rating: a measurement-and-audit paper (workshop level). Ranks 1 and 2 are the candidates to lead with.

## 9. Next steps, and how to update this report when the human labels arrive

Update procedure (all zero-spend, run from the repo root with the venv active):

```
python scripts/chimera/validate_pilot_sheet.py --sheet <returned sheet.csv>          # must print no errors
cp data/db/reverend-insanity.db <scratch>/ri_copy.db                                  # read-only analysis uses a copy
python scripts/chimera/silver_pilot_analysis.py --db <scratch>/ri_copy.db --out data/eval/chimera/silver_pilot_results.json
python scripts/chimera/human_pilot_analysis.py --sheet <returned sheet.csv> --out data/eval/chimera/human_pilot_results.json
```

Then replace the section 5.2 tables' label banner from SILVER to the new `HUMAN (single annotator)` rows, add the counts of pre-reveal items where the reader view differs from the omniscient view, the premature-resolution counts with Wilson intervals, the controls sanity rate, and the **model-versus-human agreement** on the omniscient label as a finding. The script refuses to run on a sheet with a blank or model-named annotator and never edits a label; there is one annotator, so no kappa is reported.


1. Weekend: the author labels the 72-item sheet; run the procedure above.
2. L1-H: rerun the pre-registered L1 prompts on the human-labelled pre-reveal items (human `reveal_chapter` gives up to 23 primary items instead of 4); expected cost about $0.03 at the observed rate, requires the owner's separate approval. A corrected evidence gate (verbatim-span tolerance; identical-surface claims) would be a new pre-registered version, not an edit of v1.
3. If a renaming control is retried, it needs a design that commutes with the normalisers (a new pre-registration, not a v4 tweak of the frozen rule).

## 10. Claim-to-evidence table

| Number or statement | Source file or command |
|---|---|
| SIO M1-M4, exploratory rows | `data/eval/chimera/sio_results.json`; `python scripts/chimera/sio_synthetic_oracle.py --out ...` |
| SIO generator tests pass (5) | `pytest packages/pipeline/tests/test_sio_generator.py` |
| SIO prereg hash | `docs/research/preregistrations/MANIFEST.json`; `sha256sum` of the prereg file |
| Silver pilot table, integrity 33/33, title events 5/22, eligibility 12 | `data/eval/chimera/silver_pilot_results.json`; `python scripts/chimera/silver_pilot_analysis.py --db <scratch copy> ...` |
| T4 gate failure | `data/eval/chimera/t4_results.json`; `docs/research/preregistrations/PREREG_T4_renaming_validity_v3.md` |
| Scorer 0.550, 0 SCORED of 880 | `docs/results/SCORER_DIAGNOSIS.md:50`, `docs/status/STATUS.md:77,79` |
| L1 pre-registration, frozen prompts, runner, dry run | `docs/research/preregistrations/PREREG_L1_llm_leakage.md`, `L1_prompts_v1.json`, `MANIFEST_L1.json`; `scripts/chimera/l1_llm_leakage.py --dry-run` -> `data/eval/chimera/l1_dryrun.json`; `pytest packages/pipeline/tests/test_l1_runner.py` (8 passed) |
| L1 results (281 calls, $0.0267, silver): R1 30/30; controls A 29/30, B 29/30, D 14/30; P* A 4/4, B 0/4, D 0/4; A-B +9.7 pts [3.2, 17.7]; closed-book 1/15 | `data/eval/chimera/l1_results.json`, `data/eval/chimera/l1_analysis.json`; `python scripts/chimera/l1_analyze.py --db <scratch copy> --results data/eval/chimera/l1_results.json --out ...` |
| Hard-case detection 58/88 | `data/eval/hardcase_resolution.json`, `docs/research/CHIMERA_ERRATA.md` E3 |
| LitBank 15.95 / 42.44 | `data/eval/litbank_results.json` |
| 72-item sheet composition | `data/eval/chimera/pilot_manifest.json` |
| Prior-art claims | `docs/research/NOVELTY_REPORT/PRIOR_ART.md`, `prior_art_notes_A.md`, `prior_art_notes_B.md` (PDFs read as extracted text; `RECHECKED` rows verified again by me in the raw text) |
| Human-label analysis tool (not yet run on human labels) | `scripts/chimera/human_pilot_analysis.py` (refuses invalid sheets; smoke-tested on a fixture only) |
| PD benchmark: R0 and gaps per model, verdict NOT SUPPORTED, closed-book 3/7 for four models and 0/7 renamed, Luna spend $0.0254 | `data/eval/chimera/pd/analysis.json`, `run_*.json`, `r0_diagnosis_exploratory.json`; `python scripts/chimera/pd_reveal_benchmark.py analyze`; `docs/research/preregistrations/PREREG_PD_reveal_benchmark.md`, `MANIFEST_PD.json`; `SPEND_LEDGER.md` |
| PD v2: R0 80-88%, gaps +10 to +35 (Luna +35.2), synthetic 0.0, closed book 6-11 of 19 for five models, verdict INCONCLUSIVE; threshold sensitivity; post-hoc asymmetry; Luna spend $0.1212 | `data/eval/chimera/pd_v2/analysis.json`, `run_*.json`, `r0_asymmetry_exploratory.json`; `python scripts/chimera/pd_v2.py analyze`; `PREREG_PD_v2.md`, `MANIFEST_PD_v2.json` |
| Engineering probes E1-E6 (0 of 28,165; 23 of 288; ARI 0.971; E3 gaps; E4 47-58%) | `docs/research/ENGINEERING_NOVELTY_PROBE/SUMMARY.md`, `data/eval/chimera/eng_probe_E*.json`, `scripts/chimera/eng_probe_*.py`, `scripts/chimera/test_eng_probe_e3_state_of.py` (E6 and E5 headlines re-read from stored JSON by me; the rest are the subagent's) |
| PD v3: R0 80-96%, gaps +4 to +25 (Luna +18.2), pooled +12.7 [6.8, 19.0] local / +13.6 [7.9, 19.6] with Luna, synthetic 0.0, condition iii fails, verdict PARTIALLY SUPPORTED; Spearman 0.80; sensitivity | `data/eval/chimera/pd_v3/analysis.json`, `run_*.json`, `sensitivity_secondary.json`; `python scripts/chimera/pd_v3.py analyze`; `PREREG_PD_v3.md`, `MANIFEST_PD_v3.json` |
| PD v4: G2 gate, M2 probe (Luna 25 of 31 vs 0 renamed), re-evaluation SUPPORTED on v2 (+15.4) and v3 (+13.4), Spearman 0.73 / 0.66; Luna probe spend $0.0041 | `data/eval/chimera/pd_v4/analysis.json`, `run_*.json`, `pd_memory_free_validity.json`; `python scripts/chimera/pd_v4_memory.py analyze`; `PREREG_PD_v4.md`, `MANIFEST_PD_v4.json`; `SPEND_LEDGER.md` |
| Event-cluster intervals, gate sweep, competence floor, objection responses | `data/eval/chimera/pd_adversarial_checks.json`; `python scripts/chimera/pd_adversarial_checks.py` |
| PD v5: B3 gap +16.1 [8.2, 25.0], recovered fraction -0.11 [-0.36, 0.06], control accuracy restored, verdict MEMORY SURVIVES (strong) | `data/eval/chimera/pd_v5/analysis.json`, `run_*.json`, `pseudonym_map_audit.json`; `python scripts/chimera/pd_v5_cuepres.py analyze`; `PREREG_PD_v5.md`, `MANIFEST_PD_v5.json` |
| PD v6: valid-local pool -5.9 [-14.8, 1.0] NOT SUPPORTED; Luna +16.7 [5.4, 28.6]; pooled 38 events (valid-local +11.5, Luna +26.0); Luna B3/v6 spend $0.0585/$0.0568 | `data/eval/chimera/pd_v6/analysis.json`, `run_*.json`, `data/eval/chimera/pd_final_pooled.json`; `python scripts/chimera/pd_v6.py analyze`, `python scripts/chimera/pd_final_pooled.py`; `PREREG_PD_v6.md`, `MANIFEST_PD_v6.json`; `SPEND_LEDGER.md` |
| Dose-response: Luna gap vs local recognition +0.37 (p = 0.024); valid-local +0.59 (p = 0.00015); mean gap by recognition count | `data/eval/chimera/pd_dose_response.json`; `python scripts/chimera/pd_dose_response.py` |
| PD CONFIRM v2 (5.23): 68 events, primary 32; pooled A-B +0.1 [-5.0, +5.2]; P1 +7.6 [-1.4, +18.3] p 0.060; H2 +5.7; H3 +0.30 (Holm 0.145); E4 5.0% to 2.6%; E5 0 spoilers; OLMo link +0.13 p 0.41 | `data/eval/chimera/confirm/main/analysis.json`, `e2/analysis.json`, `main/olmo_corpus_check.json`; `python scripts/chimera/pd_confirm_analyze.py`; `scripts/chimera/gen_ch1_tables.py`; `docs/research/preregistrations/PD_CONFIRM_deviations.md` |
| RF-E2E (5.24): W-ren 18.5% vs P-ren 1.2% (rule B, 54 events); rule A 24.6% vs 0.0% (19 events) | `data/eval/chimera/rf_e2e/analysis.json`; `python scripts/chimera/pd_rf_e2e.py analyze`; `PREREG_RF_E2E_addendum_6.md`, `_addendum_7_fix.md` |
