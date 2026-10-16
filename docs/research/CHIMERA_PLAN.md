# CHIMERA PLAN — EchoTales novelty report

Owner: AJ. Written 2026-10-15. This file is the single source of context for the coding agent. Read all of it before acting. Where it conflicts with older directives (Checkpoint 1, Checkpoint 2, ECHOTALES_NOVELTY_REPORT_PROMPT.md), this file wins.

---

## 1. Goal and deadline

Produce a complete **Novelty Report** on EchoTales that AJ submits online to his programme. It is a report, **not a journal paper**. The report is due **tomorrow (2026-10-16)**. AJ's presentation is about a week out. The novelty section must be finished first.

A good report states a precise novelty claim, shows the closest prior art with exact differences, presents a pilot experiment with real numbers, and says plainly what it does not show. An honest narrow claim beats an inflated one. AJ prefers a collaborator who argues back and does not agree unless something fully makes sense. You are that collaborator: independent, skeptical, and direct. Do the thinking and the coding yourself. AJ will do exactly one thing: label the pilot sheet.

## 2. The project in one paragraph

EchoTales (repo `adhyan-jain/EchoTales`, local at `~/Desktop/EchoTales`, branch `validation/evidence-pass-2026-09-24`, HEAD `6c7e2c2`) builds a bitemporal narrative knowledge graph from web-novel volumes. The query is `state_of(target, timeline, position, observer=READER)`. It has three time axes (discourse, story, knowledge), a Self-vs-Persona split, retractions that are not interval ends, fuzzy three-valued containment (CERTAIN / PLAUSIBLE / EXCLUDED), a compounding gazetteer, hard pre-filters (FORCE_LINK / BLOCK), a conformal gate (Mondrian by alias type), and an escalation ladder. Test corpus: Reverend Insanity (RI), Lord of the Mysteries (LOTM), Omniscient Reader's Viewpoint (ORV), as local EPUBs (copyrighted, not committed).

## 3. The novelty claim under test

**Disclosure-faithful identity resolution under parametric leakage, for long translated web serials.** Filtering the context to chapters ≤ c does not stop a model from linking an alias to an identity revealed later, because it remembers the novel. Candidate contributions, in order. Re-rank them yourself, and drop any that fails its evidence:

1. **C1a. A premature-resolution metric.** It is measured on items whose reader-warranted identity at chapter c differs from the final-truth identity. Leakage is the change between original and consistently renamed text (the renaming control of Jiang & Ferraro, arXiv 2412.14368, and SynthWorlds).
2. **C1b. An evidence-gated linking rule.** A link must cite spans inside the prefix that entail it with names masked. The decisive comparison is against plain whole-input renaming.
3. **C2-pilot. A small reader-view / omniscient-view item set** for web-serial hard cases, single annotator, flagged as a pilot. It is not a benchmark.
4. **C5. A failure audit** of the pipeline, as grounding (detection loss, a scorer that links nothing, defects in the backlog). This is the always-alive floor.

Do not equate an under-explored domain with a novel algorithm.

## 4. Verified facts you may rely on (re-verify before citing as your own finding)

- **No human gold exists.** All six gold files are model-drafted (`confirmed:false` or a bulk "glancing over" approval). The 89 hard cases are model drafts. LitBank is the only human-keyed number: CoNLL F1 15.9 on the full person key, 42.4 on proper names only.
- **Scorer links nothing.** Max reachable probability 0.550 against a 0.80 gate. Every labelled decision is taken by hard pre-filters (101 FORCE_LINK, 2 BLOCK, 0 SCORE).
- **Hard cases are lost at detection, not linking.** 58 of 88 never become a mention (see `CHIMERA_ERRATA.md` for the 58/88 vs 59/89 reconciliation: the evaluated n is 88 because one `not_an_entity` record is dropped).
- **Real data is thin.** Three reveals, 12 observation rows, 0 retractions in the shipped RI database.
- **Defects** (`CHIMERA_DEFECT_BACKLOG.md`: B1–B9 verified, A1–A14 leads): `retract_alias_bindings` has no callers; `retry_deferred` counts "recovered" without linking; `resolve --chapters` is ignored; `reference_images=[]` in production panels; character-sheet labels still counted in `conditioned_on`; wiki canon is undated.
- **T4 (renaming validity) failed its pre-run commutation gate twice** (v2: G1=8, G2=25; v3: G1=2, G2=9, G3=0). The frozen rule says no v4 unless the owner asks. **The owner has decided: no v4.** Report T4 as "a token-level renaming control cannot be made to commute with the repo's normalisers without further design; control not validated", with the violation classes as the finding.
- **Pilot sheet is built:** 72 items (23 pre-reveal, 17 hard, 32 controls), `data/eval/human_review_chimera_pilot.csv`, answer key in `data/eval/human_review_chimera_pilot_key.csv` (blind: the owner must not open it). Both are local only and gitignored. Manifest: `data/eval/chimera/pilot_manifest.json`.
- Pre-registrations live in `docs/research/preregistrations/` (T4 v1–v3, SIO synthetic identity oracle, T3 draft) with hashed manifests. A change after freezing is a new file, never an edit.
- The public repo and branch are public, exposing IPR review files and short excerpts (mean 74.8 characters, median 35, max 145) of the gold text. This is the owner's decision. Do not touch it. Information only.

## 5. Prior art (verification status: mostly `[LEAD]`; Task 2 must upgrade or retract)

- **GenWebNovel** (COLING 2025): NER only (PER/LOC/ORG), 400 chapters, 40 Qidian novels, annotations only, DUA bars anti-bot workarounds. Coreference is listed as future work. Chinese text, so **do not** evaluate English title detection against it. Parked; it needs Qidian access the owner has not authorised.
- **Song & Liu 2024** (LREC-COLING): character resolution in a print novel; hidden-identity plots listed as unsolved.
- **KoCoNovel** (arXiv 2404.01140): reader and omniscient annotation views, 50 short stories. Direct precedent for any reader-view gold; the pilot must cite it and say what it adds.
- **Jiang & Ferraro** (2412.14368), **SynthWorlds**: renaming as a leakage control. Closest prior art to C1a.
- **TimeChara** (ACL Findings 2024), **Narrative World Model** (arXiv 2607.05577), **NarraWorld** (2609.32401), **TAC-KBP temporal slot filling**, **E²RAG/ChronoQA**: overlap risk on time-aware state and disclosure. My earlier "the combination is new" claim was too strong. Do not repeat it.
- Others to read: LlmLink, BookCoref, FantasyCoref, Maverick, SagaScale, "Scaling Long-Form Story Generation via Narrative State Tracking" (2609.35759, unread). No work evaluating BookNLP or a modern coreference system on translated web novels was found; Chinese and Korean venues were not searched.
- A page summarised by a fetch tool is `[LEAD]`, never `[PUB]`. Never infer that a paper lacks a feature because its abstract omits it. Cite the section you read for every "X does not cover Y" claim.

## 6. Hard rules

- No commits, pushes, merges, resets, stashes, branch switches, deletions, or visibility changes. New files only (`docs/research/NOVELTY_REPORT/`, `scripts/chimera/`, `data/eval/chimera/`, new tests). Never edit existing files, including the `CHIMERA_*` files. Use `git --no-optional-locks`. Run experiments in a scratch copy where possible. Preserve all untracked files.
- No fabrication. Every number comes from a command you ran, every prior-art claim from a source you opened. Evidence tags: `[REPO]` `[INSPECT]` `[PUB]` `[LEAD]` `[INFER]` `UNVERIFIED` `INACCESSIBLE`. Never say a test ran or passed unless you ran it.
- Model-drafted gold is never human truth. Only rows labelled by AJ may be called `HUMAN (single annotator)`. Never fill, adjudicate, or "fix" a human label. Never compute or claim κ (there is one annotator).
- Never state that results support real-world performance when they come from synthetic worlds. Report synthetic and real results separately.
- A null result from a small local model narrows the claim to that configuration. It does not kill it for larger models.
- Before publishing, check that nothing you create carries novel text into a tracked or shared location.
- **Provenance disclosure is mandatory (owner decision 2026-10-15, v2 of this plan).** The report must state, for every real-novel number, what the reference labels are: model-drafted (silver) or human. Never omit, soften, or relabel provenance, and never write wording that lets a reader assume human verification. The owner asked to leave this out; it stays in. A report that hides its label source is not defensible and would fail the first question a reviewer asks. Stating it costs the novelty claim nothing, because the claim rests on the gap, the design and the synthetic-oracle evidence, not on the quality of the real-novel labels.

## 6b. Silver labels for the pilot (owner decision, v2)

AJ will do human labelling on the weekend, after the report is submitted. For the report, the real-novel pilot uses **silver labels**: the existing model-drafted labels already in the repo (89 hard cases, the 288-item model pre-labelled package, the pilot key's repo-derived final-truth labels), and optionally a fresh model-labelled pass. Rules:

1. **Zero-cost first.** Use the labels that already exist. No new call is needed to analyse the 72-item sheet against repo-derived final truth.
2. **Reader-warranted labels cannot come from an LLM that may remember the novel.** That is the exact leakage the claim studies, so labelling the reader view with Luna 5.6 or any model is circular. A model's reader-view label is silver-of-silver and must be reported as "model-labelled; contaminated by the effect under test; not evidence of reader-warranted truth". If AJ approves a model pass anyway, run it twice: on the original text and on the renamed text, and report the gap as a leakage measurement, never as ground truth.
3. Any model labelling pass needs approval first, with the §7 cost estimate. Do not assume a price. Verify it. As a guide only: 72 items at roughly 1–2k input tokens each is about 70–150k tokens, which is small, but the dollar figure must come from verified prices.
4. Claims allowed from silver: that the metric is computable, that the pipeline and baselines can be compared on it, descriptive counts, and the audit findings. Claims not allowed from silver: accuracy, reader-view correctness, any statement that Luna or another model "is as good as a human". There is no evidence for that comparison here, and none will be created without human labels. The weekend human labels are what will test it.
5. Label every table "silver (model-labelled), human verification pending". When AJ's human labels arrive, rerun the analysis, report model-vs-human agreement as a finding, and update the report.

## 7. Spending and approvals (strict)

AJ has **$10 spare for GPU compute** and may allow an **OpenAI model ("Luna 5.6") only if the cost is about $0.10–0.20 or less**. Rules:

1. **Default is no spend and no key use.** Never read, print, log, copy, or transmit any API key. Use one only through existing tooling, only after AJ approves, and only for the approved call.
2. **Before any spend, stop and ask AJ.** Your message must contain: what the run is for; the exact model id and provider; the number of calls and expected input and output tokens; unit prices with the source and date you took them from; the **total estimated cost** with a safety margin (state the worst case); what we learn that we can't learn free; and the free fallback if AJ says no.
3. The model name "Luna 5.6" is the owner's wording. Verify the exact model id and current price from the provider's documentation before estimating. If you cannot verify them, say so and mark the estimate `UNVERIFIED`. Do not guess a price.
4. For GPU time: give the provider, the GPU, the hourly price, the expected hours with margin, and the total. Stay under $10 including retries. Do not rent anything yourself.
5. Free local inference (ollama on AJ's machine) needs AJ to confirm the model tag and hardware before each use. The repo docs say `qwen2.5:7b` on an RTX 4060 8 GB. This is unconfirmed.
6. Never exceed an approved amount. If a run is likely to, stop and ask again.

## 8. Work plan and status

| ID | Task | Status |
|---|---|---|
| W0 | Re-baseline, errata, defect backlog | **Done** (`CHIMERA_ERRATA.md`, `CHIMERA_DEFECT_BACKLOG.md`) |
| W1 | Pilot sheet, annotation guide, validator | **Done**, waiting for AJ's labels |
| W2 | Pre-registrations (T4 v1–v3, SIO, T3 draft) | **Done**; T3 needs finalising |
| T4 | Renaming validity | **Gate failed ×2; closed as a finding** |
| SIO | Synthetic identity oracle test (CPU) | **Next.** Run exactly as frozen |
| T3 | Closed-book memorisation probe (local model) | Blocked until AJ confirms model and hardware. Optional |
| P | Prior-art verification (`NOVELTY_REPORT/PRIOR_ART.md`) | Next, in parallel with SIO |
| R | `NOVELTY_REPORT/NOVELTY_REPORT.md` (+ .docx or PDF copy) | Draft now with placeholders; finish when labels return |
| L | Pilot analysis on silver labels (§6b), flagged as such | Start after SIO; no human labels needed for the report |
| L2 | Re-run on AJ's human labels | Weekend, after submission; report model-vs-human agreement |

**SIO details.** Generate small serial worlds from a specification where true identity, reveal chapter, and reader-warranted identity are known by construction. Measure the premature-resolution rate at controlled reveal distances for (a) the plain resolver, (b) whole-input renaming, (c) evidence-gated linking, with Wilson intervals and paired bootstrap for differences. The oracle reads only the world spec, never the system's store. If the three conditions don't differ, say so and narrow the claim.

**Pilot-label analysis.** When the sheet returns: run the validator (rejects blank or model-named annotators); report how many pre-reveal items AJ marked as having reader label ≠ omniscient label; premature-resolution counts for each system on those items with Wilson intervals; the controls as sanity checks. State that n is small (23 pre-reveal candidates) and the power consequence, i.e. the smallest effect that n can detect.

## 9. The report (`NOVELTY_REPORT.md`) must contain

1. Problem and why it matters. 2. The claim, one falsifiable sentence per contribution. 3. Closest prior art, with the exact difference from each. 4. Method: metric, renaming control, gated linking rule. 5. Pilot setup and results with intervals. 6. What each test could have falsified and what happened (including T4's failure). 7. Limitations, plainly: single annotator, no agreement statistic, model-drafted gold elsewhere, small or no local-model test, synthetic scope, small n, public exposure. 8. An honest novelty assessment: what is new, what is engineering, what overlaps, with a rating against the gate (formal task, one novelty sentence, closest work and difference, strongest baseline, falsifiable outcome). 9. Next steps. Include a **claim-to-evidence table** tracing every number to a file or command.

If no contribution survives the gate, say so and make the report an audit-plus-pilot report. Do not inflate.

## 10. Checkpoints: stop, audit, and ask AJ to continue

Work continuously and fast between checkpoints. At each one, **stop and send AJ an audit**, then wait for him to say continue. Do not move past a checkpoint on your own.

- **CP-A: SIO result.** After the synthetic oracle test: what ran, the numbers with intervals, what it does and doesn't show, whether C1b survives, the recommended next action.
- **CP-B: Prior-art and draft report.** After `PRIOR_ART.md` and a full draft with placeholders: which claims survived verification, which were retracted, the closest-overlap assessment, and the remaining gaps.
- **CP-C: Spend request,** only if you think T3 or any paid or higher-compute run is worth it. Use the §7 format.
- **CP-D: Silver pilot analysis (and later, human labels).** After the silver analysis (and again when AJ's human labels arrive): the pilot numbers, the report's final novelty rating, and any claim that must be dropped.
- **CP-E: Final.** The finished report and a short list of what AJ should say if his programme asks about the weak points.

**Audit format at every checkpoint:** work completed; files created (state that no existing file was modified); commands run and results; tests run; sources opened with tags; findings that contradict earlier reports or this plan; cost so far (zero unless approved); open questions; recommendation (continue / narrow / stop); the exact next action; what AJ must do before you continue. Keep it concise.

## 11. Traps already hit. Don't repeat them

- Claiming the combination of components is novel (TAC-KBP and NWM overlap).
- Evaluating English title detection on GenWebNovel (Chinese text, generic-descriptor PER labels).
- Treating the sandbox VM's 2 CPUs and 3 GB as the host. The reported host is 16 CPUs and 15 GB. Confirm before relying on it.
- Reading `conditioned_on` as a pure tag count or as fixed. It is partly fixed. Check the specific path.
- Treating LLM pre-labels (the 288-item package, the 89 hard cases) as truth.
- Letting renaming-gate iteration become open-ended tuning. T4 is closed.

## 12. Venue facts (re-check before relying on them)

ACL 2027 ARR deadline 2027-01-04 (per the official site, via a summarising tool, so `[LEAD]`). The October 2026 ARR cycle has passed. No 2027 WNU call found. None of this matters for the tomorrow report. It matters only if AJ later pursues a paper, which is outside this plan.

---

## 14. v3: Two tracks, one programme (owner decision 2026-10-15, late)

**What changed.** Until now this plan produced a novelty report on one narrow idea. The owner wants CHIMERA to be what its name says: study many papers, take the useful parts of each, merge them into the EchoTales product, add EchoTales' own novelty on top, and grow the paper as far as the evidence allows without leaving the field. The product is a web-novel adaptation pipeline built on a bitemporal narrative knowledge graph with reveal-aware state. The end goal is still **a paper with strong, defensible novelty**.

**Owner statement to respect:** a component may be merged for product value even if it adds no novelty. **Constraint added by the collaborator (non-negotiable): merging a component never counts as a paper contribution.** Connecting existing methods is not novelty, and a prior ledger entry already killed it as a standalone claim. So the programme runs on two tracks.

| | Track P (paper) | Track S (system / product) |
|---|---|---|
| Purpose | Defensible novelty and evidence | A better, more consistent product |
| What goes in | Only claims with a test, a baseline, intervals and a falsifier | Any well-fitting technique from the literature that helps the product |
| How it is described | As a contribution, with a claim-to-evidence row | In a "system" section as engineering, tagged as integration, never as novelty |
| Gate | Novelty gate (formal task, one novelty sentence, closest work and difference, strongest baseline, falsifier) | Fit, licence, isolation, test; ablation where measurable |

A merged component earns paper space only if (a) an ablation shows it moves a measured number and (b) its difference from the donor paper is stated exactly. Otherwise it stays in Track S. Do not pad the paper with Track S material to look bigger. A reviewer discounts claims they cannot test, and bloat hides the one result that matters.

**Owner clarification (same day): merge for product value only, make no novelty claim for it, and omit anything that harms novelty.** Adopted, with one rule on what "omit" means:

- **Harms novelty by overlapping the claim** (a donor already does the thing): do not hide it. It goes into related work as the closest prior art and into the experiments as a baseline. Omit it from the *claimed* contribution, never from the disclosure.
- **Harms novelty by confounding the experiment** (a merged component changes the numbers being measured): keep it out of the evaluated configuration, or evaluate with it switched off and on. Any component that was active in a reported run is named in the report's system description.
- **Product-only, no effect on the claim:** merge freely, record it in the Integration Register as Track S, and describe it as engineering.

So the system the paper evaluates is always exactly the one described in the paper, with the product-only extras either disabled or listed.

## 15. Field boundary

In scope: identity and alias resolution, mention detection, narrative time and disclosure, character knowledge, retraction and correction, leakage/memorisation controls, reliability of links, and the visual and audio consistency of adaptations **only through the narrative state the pipeline already feeds them**. Out of scope: new modalities, new genres or corpora unrelated to web serials, general-purpose agent memory, and anything that needs a rewrite of the repository. When in doubt, ask. Do not go out of the field.

## 16. Integration Register (the core of the "chimera" work)

Build `docs/research/NOVELTY_REPORT/INTEGRATION_REGISTER.md`: one row per candidate technique. Columns: source paper (verified title, authors, venue, date, evidence tag); what it contributes; artifact and licence (code, data, models; can we legally reuse); the EchoTales component it touches; product value; paper value (novelty, ablation baseline, or none); integration form (isolated adapter, config switch, or baseline-only); cost (compute, annotation, engineering days); evidence needed and available; risks (error propagation, leakage, precision loss); **decision: adopt / adapt / baseline-only / reject**; and the test that would justify the decision. No row is accepted on an abstract. Papers read only as snippets stay `[LEAD]` and cannot be adopted until read in full.

**Donor families to evaluate** (all prior-art claims below are leads until read in full; correct any that are wrong):

1. **Mention detection and coreference.** Maverick (ACL 2024); the BookCoref pipeline (ACL 2025); LlmLink's dual-LLM linking with a character memory (COLING 2025); KoCoNovel's reader and omniscient annotation protocol (arXiv 2404.01140); FantasyCoref's disguise and transformation annotation; LitBank and BookNLP as baselines. Product angle: title-aware mention detection, which Checkpoint 1 found is where the hard cases are lost (58 of 88 not detected).
2. **Time, knowledge and state.** TAC-KBP temporal slot filling (bounded intervals, maps onto the repo's fuzzy endpoints); TimeChara (point-in-time character hallucination); Narrative World Model (arXiv 2607.05577: chapter-safe write and read cutoffs, reveal order separate from event order); NarraWorld (arXiv 2609.32401: per-character beliefs, open developments); E²RAG/ChronoQA and EvolvTrip (entity-event and temporal retrieval); bitemporal graph-memory systems (Graphiti/Zep and similar). Product angle: one shared state policy for all render paths, with dated wiki canon.
3. **Leakage and memorisation controls.** Jiang & Ferraro (arXiv 2412.14368), SynthWorlds, SagaScale's closed-book filtering, look-ahead bias work (Glasserman & Lin), LifeState-Bench. Paper angle: the evaluation methodology.
4. **Reliability.** Selective prediction and conformal methods (Fannjiang et al. 2022), semantic drift in bootstrapping (Murphy & Curran 2007). Product angle: calibrated abstention in the link rule.
5. **Visual and audio narrative consistency (product only).** CANVAS (arXiv 2604.13452), VideoMemory, StoryDiffusion-style consistent references, VinaBench, ViStoryBench, Story2Board, Jularr PR #451, the Gen4AVC poster "Grounding the Visual Axis of a Narrative World Model" (unreadable so far; read it first, it may overlap the reveal-aware reference idea). Product angle: reveal-aware reference selection, with the leakage test applied to references. Do not claim visual correctness from text-only tests.
6. **Information-flow control for LLM context** (FIDES and similar; ids unverified). Product angle: a cheap provenance-and-label check on what enters each prompt.

Search for more donors inside these families, not outside them. For each donor, read the method and experiment sections, note the limits the authors state and the ones you find, and record the reproduce-or-adapt decision.

## 17. Workstreams for v3

State carried forward from the L1 run (agent-reported, re-verify in `l1_results.json` and `l1_analysis.json` before citing; all numbers are silver, model-labelled, no human check): cost $0.0267 for 281 calls on `gpt-5.6-luna`; renaming control valid on controls (30 of 30 identical); primary test inconclusive (4 pre-reveal items; naming the revealed identity 4/4 with original names, 0/4 renamed, 0/4 gated); accuracy 9.7 points higher with original names across 62 items (95% CI [3.2, 17.7]; post-hoc sign test p = 0.031; may partly reflect shared memory between the resolver and the model that drafted the silver labels); the evidence gate over-rejects (control accuracy 96.7% to 46.7%); closed-book probe uninformative (abstention on 14 of 15). Cumulative paid spend so far: $0.0267.

| ID | Workstream | Track | Notes |
|---|---|---|---|
| M0 | Integration Register (read-only research, §16) | P and S | Do first. No spend. |
| M1 | Evidence gate v2: redesign the over-rejecting gate as a **new pre-registered version**. Split the 72 items into dev and test by seed before looking at outcomes; design on dev, run once on test. | P | Needs cost approval (about $0.03 scale). Report v1 failure unchanged. |
| M2 | Replicate arms A and B on a model from another family, same items, to test the shared-memory confound. | P | Needs cost approval. |
| M3 | Make the synthetic-world resolver reveal-aware so that the SIO result stops being vacuous; add a title-holder temporal model (holder, title, organisation, story time) evaluated on synthetic worlds with oracle truth and on the real RI link events stamped before the holder binding is learned (5 of 22 at chapter 1 vs learned at chapter 6). | P and S | CPU, no spend. Compare against the register's temporal donors. |
| M4 | Product adapters: a single narrative-state policy shared by every render path; dated wiki canon; honest `conditioned_on`; reveal-aware reference selection. Fix verified defects B1–B9 from `CHIMERA_DEFECT_BACKLOG.md` **only on an authorised branch**. | S | Needs the owner to authorise a branch (A3). Ask at CP-G. |
| M5 | Translation-vs-narrative decomposition (E2). | P | Only if a GuoFeng-style aligned corpus is legally and practically available. Otherwise drop it and say so. |
| M6 | Paper skeleton v1: structure, tables, figure list, claim-to-evidence matrix. Manuscript prose only after the gates. | P | After CP-H. |
| M7 | Owner's human labels (weekend): L2 analysis, L1-H, model-versus-human agreement. | P | Owner labels; agent analyses. |

**Paper scope guard.** At most three Track P contributions in the first version, plus a system section. The likely order, to be re-ranked on evidence: (1) the disclosure-faithfulness measurement design (the premature-resolution metric with the renaming-based leakage control; its difference from Jiang & Ferraro is the prefix and disclosure-time framing), (2) the evidence-gated or calibrated link rule if v2 survives, (3) the title-holder temporal model if M3 shows an effect, with the failure audit (C5) as grounding throughout. A new contribution is added only if it passes the novelty gate; otherwise it goes to the system section.

## 18. Spending (unchanged rules, plus a ledger)

Keep `docs/research/NOVELTY_REPORT/SPEND_LEDGER.md`: date, purpose, model id, calls, tokens, actual cost, running total. Same protocol as §7: nothing is spent without the owner approving an exact verified estimate; the key is never displayed or copied; the owner's cap for the OpenAI model is about $0.10 to $0.20 per request; the GPU budget is $10 in total and nothing is rented without a separate approved request. Free local inference needs the owner to confirm the model tag and hardware.

## 19. Checkpoints for v3 (stop, audit, wait for "continue")

- **CP-F: Integration Register.** Rows, decisions, what was read in full vs lead, overlaps found, any claim from earlier sessions that the new reading retracts.
- **CP-G: Plan for system work.** Which adapters you propose, the defects to fix, the branch you need, and what each would change for the product. Wait for authorisation before touching code beyond new files.
- **CP-H: M1, M2, M3 results,** each preceded by a spend request where it needs one. Report nulls as nulls.
- **CP-I: Paper skeleton and claim-to-evidence matrix.** Which contributions survived, which moved to the system section, the novelty rating against the gate, and a candid statement of what a reviewer would attack.
- **CP-J: Human labels in.** L2 and L1-H, model-versus-human agreement, the final novelty assessment, and what must be dropped.

Audit format at every checkpoint is §10's format, plus the running spend total.

## 20. Standing guardrails for the merging work

- Each adopted technique is an **isolated, disable-able adapter** with its own tests and an ablation where the benefit is measurable. No silent loss of confidence, evidence, temporal, observer or provenance metadata. No repository rewrite.
- A donor's code or data is reused only if its licence allows it, and the source is cited. Do not copy text or code from papers.
- Never describe a merged component as novel. Never describe a result from synthetic worlds or silver labels as real-world performance. Label provenance in every table.
- Keep the public-exposure issue (IPR files and gold excerpts in the public repo) in front of the owner at every checkpoint where new IP-relevant material is created. Do not act on it.
- Track P claims and Track S claims are kept in separate sections of every document you write.

## 21. The /goal prompt for v3 (paste this to start; it supersedes §13)

```
/goal Read docs/research/CHIMERA_PLAN.md (v3, sections 14 to 21) and
docs/research/NOVELTY_REPORT/NOVELTY_REPORT.md (v0.2) in full. The programme is
now two tracks: Track P builds a defensible-novelty paper, Track S merges the
useful parts of published work into the EchoTales product. Merging counts as
engineering, never as paper novelty. Work in order: M0 (Integration Register,
read-only, no spend) first, then stop at CP-F with the audit format from the
plan. Then continue through the workstreams in section 17, stopping at each
checkpoint (CP-F to CP-J) and waiting for me to say continue. Read every donor
paper's method and experiment sections before adopting anything; snippets stay
LEAD. Stay inside the field (section 15). Keep the paper to at most three
contributions plus a system section. Before any paid or higher-compute run, or
any use of the OpenAI key, stop and give me the exact verified cost estimate;
log every spend in SPEND_LEDGER.md; never display or copy the key. No commits,
pushes, deletions or edits to existing files; code changes beyond new files
only on a branch I authorise at CP-G. Silver labels are labelled silver
everywhere; never hide label provenance.
```

## 13 (superseded by §21). The old /goal prompt (kept for the record)

```
/goal Read docs/research/CHIMERA_PLAN.md in full and execute it. Produce the
EchoTales Novelty Report (NOVELTY_REPORT.md plus a .docx or PDF copy) as fast
as possible, honestly and with evidence only. The plan lists the state of the
work, hard rules, spending rules and checkpoints. Next: run the SIO synthetic
oracle test and write PRIOR_ART.md in parallel, then draft the report with
placeholders for pilot-label results. Stop at each checkpoint (CP-A to CP-E)
with the audit format in section 10 and wait for me to say continue. Before any
paid or higher-compute run or any OpenAI-key use, stop and tell me the exact
cost estimate (section 7); never spend without my approval, never touch the
key otherwise. No commits, pushes, deletions or edits to existing files.
```
