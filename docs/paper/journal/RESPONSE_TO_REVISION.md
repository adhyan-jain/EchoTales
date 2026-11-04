# Response to Revision 1: point-by-point

Manuscript: *Reader-Faithfulness in LLM-Based Narrative Assistants: Measuring Parametric Memory Leakage and
Future-Information Leakage in Processing Pipelines* (first draft, 26 October 2026).

**Files:**
- `main.tex`: one file, no `\input`, in the Overleaf `sn-jnl` template.
- `references.bib`: 52 entries.
- `figures/fig1-10`: vector PDF, plus 600 dpi PNG.
- `supplementary.tex`: the supplementary material.

**Status key:** **Done** = addressed in the draft.

---

## Journal structure (pages 1-2)
| Request | Status | Where |
|---|---|---|
| Follow the proposed outline: numbered subsections only where the outline numbers them; plain paragraphs elsewhere | Done | The headings are the outline verbatim: 1; 2.1-2.4; 3; 4.1-4.4; 5; 6.1-6.5; 7; 8; 9; then Declarations, References and Supplementary. Sections 1, 3, 5, 7, 8 and 9 have no subsections. The detailed notes' 4.5-4.6 and 6.6-6.8 are folded into the outline's 4.4 and 6.4-6.5 rather than added as headings. |

## Major issues
| # | Issue | Status | What changed |
|---|---|---|---|
| 1 | Rebuild as a research article; numbering of sections, figures and tables | Done | Article order. Sections 1-9 are numbered continuously. Figures 1-10 and Tables 1-12 are numbered in order of first citation, and every float is cited before it appears. There are no sub-numbered tables. |
| 2 | One central contribution | Done | One reader-faithfulness framework (Sect. 3, Definition 1, Fig. 1) with RQ1-RQ3. Three contributions map 1:1 to the RQs, and the protocols of the two tracks are separated (Sect. 4, Fig. 2). |
| 3 | Narrow the parametric-memory claim | Done | +26.0 is stated as exploratory and specific to the reference model and tested books. The confirmatory +0.1 [-5.0, +5.2] is given equal weight in the abstract, 6.1, 7 and 9. Nowhere does the text claim that LLMs in general leak. |
| 4 | Separate divergence from spoilers | Done | Divergent fact, exposed fact and genuine disclosure are defined (Sect. 3). Table 8 reports divergence (41/685) and disclosure (1.7-3.5%) as separate rows with their own denominators. |
| 5 | Human validation of a representative subset | Done | 36 events (18 exploratory, 18 confirmatory primary), each labelled by 2 of 3 author-annotators, blind to model labels (`scripts/review/reveal_validation_app`, scored by `score_reveal_validation.py`, labels in `data/eval/validation/`). Results in 6.1 and Limitations: reveal explicit for both annotators in 34/36 (94.4%, Wilson [81.9, 98.5]); all 28 audit-EXPLICIT events confirmed; identity confidently inferable in 0/36 but suspected by at least one annotator in 17/36; one annotator flagged 6 confirmatory events invalid (the other accepted them). Main estimates on the validated events: reference gap +27.4 [+16.0, +40.3]; confirmatory pooled -1.2 [-6.3, +3.9], and -3.9 [-5.9, -1.9] without the flagged events. The copyrighted serial cuts could not be shared, so their disclosure labels stay model-only (4.3, 8). Supplement S8 lists every disagreement. |

## Claims table (page 4)
Every "claim to avoid" was checked by searching the manuscript for universal phrasing ("all LLMs", "guarantee",
"spoiler-free", "proves", "universal"). The only remaining uses are negations ("not a formal guarantee", "not guaranteed").
Each defensible interpretation is used:
- 6.1 and 7: the reference model on the tested books; the confirmatory study did not establish a general effect.
- 6.3: "the existing implementation is not equivalent to rebuilding from the prefix"; "zero observed divergence in the reported tests".
- 6.4: rates on the tested setup only; a position instruction did not reliably prevent leakage; the alias-merge procedure relative to the prefix-built alternative.
- 6.5: pseudonymisation is a trade-off that failed its margin.

## Section-by-section
| Section | Request | Status / where |
|---|---|---|
| Title | Use the recommended title | Done (verbatim). |
| Abstract | Five compact parts; keep the key results; state model selection, the explicit-sentence oracle and the absence of human labels; no universal claims | Done. Labelled parts: Problem and gap, Objective, Methods and data, Principal results, Limitations. Secondary mitigation rates moved to Results. |
| 1 | Shorten the product narrative; end with RQ1-RQ3; three contributions | Done. One sentence of project history; RQs verbatim; three contributions. |
| 2 | Analytical related work; reveal-time vs recall; renaming method vs our use; name-keyed reading qualified; temporal state vs our question; compact coreference table; omniscient vs reader-position; tools out; remove "2020 or later" | Done. 2.1-2.4; Table 1 replaces the per-corpus paragraphs; tools moved to Sect. 5 and the references; the year-threshold sentence removed. |
| 3 | Formal definition; operational, not correctness; behavioural leakage vs pipeline dependence; leakage gap with its aggregation | Done. Definition 1 (non-interference), the two tests derived from it, Eq. 1 with item-pooled and event-weighted estimators, recovered fraction, term definitions, content vs selection leak, Fig. 1 at the end of the section. |
| 4.1 | Normalisation, chapter boundaries, alias/identity selection, multiple reveal sentences; describe as a text-grounded oracle with model-assisted selection | Done. |
| 4.2 | Exact transformation rules; what is transformed; consistency; mapping back; controls; name-keyed as the most consistent explanation | Done. |
| 4.3 (stats) | Estimand per test; dependence; pooling; random effects | Done in Sect. 5, "Statistical protocol" (the outline puts statistics in Sect. 5). |
| 4.4 (audit) | Define character-cut, divergent, exposed, genuine disclosure; hiding vs status quo; divergence vs correctness | Done (Sect. 3 definitions; 4.3; 6.3). |
| 4.5 | Group the mitigations under one subsection | Done (4.4: one principle, each design described once). |
| 4.6 | Canary placement, hit rule, long-context assembly, alias-merged vs prefix index; judge limitation in Methods and Results | Done (4.4 and 6.4). |
| 5 | Datasets and overlap; models with versions, settings and hardware; positive control kept separate; metrics; statistical protocol; reproducibility; incomplete arm; timings not a benchmark | Done. Table 2 (datasets), Table 3 (models), Table 4 (metrics); the Claude arm is labelled incomplete and excluded. |
| 6.1 | Exploratory and confirmatory as separate blocks; why they do not contradict | Done (Fig. 3, Tables 5-6). Wording: "fits a familiarity-dependent effect". Human validation of the oracle in Fig. 4. |
| 6.2 | Pseudonym result concise; recovered-fraction interval and pre-registered rule; familiarity post hoc with group sizes and CIs | Done (Fig. 5, Table 7, Fig. 6: groups n = 20/6/12 with bootstrap CIs; six-level counts 10/10/4/2/5/7 in the text). |
| 6.3 | Tables 9a-9e consolidated; distinct denominators; zero *observed* divergence; costs visible | Done (Tables 8-9, Figs. 7-8). Resolver diagnostics moved to the supplement (Table S5). |
| 6.4 | Text rule vs judge rule separated; content vs selection in separate paragraphs; which result is deterministic | Done (Table 10, Fig. 9, Table 11, Fig. 10). |
| 6.5 | Synthesis table cites its sources; pseudonymisation is a trade-off; key costs; per-run timings to the supplement | Done (Table 12; Table S9). |
| 7 | Four questions; no repetition of tables; empirical success is not a formal guarantee | Done. |
| 8 | Seven threats, each with its meaning for the conclusions | Done (construct, selection, external, annotation, power, implementation, reproducibility). |
| 9 | Short; no new numbers or references; engineering lesson | Done (no numbers, no citations). |

## Figures
| Old figure | Action |
|---|---|
| Fig. 5 architecture | Redrawn as **Fig. 2**: both tracks and their shared concepts, short labels only. |
| Fig. 6 channels | **Fig. 1**, at the end of Sect. 3. Shows which evaluation detects each channel and where each mitigation acts. |
| Fig. 1 forest | **Fig. 3**: exploratory and confirmatory blocks separated; the +10 line removed; CIs defined in the caption. |
| (new) | **Fig. 4**: human validation of the reveal oracle, answers to four questions over 72 labels with raw agreement. |
| Fig. 2 cue control | **Fig. 5**: one panel with CIs; A, B and B3 defined in the caption. Per-model numbers in Table S1. |
| Fig. 3 dose-response | **Fig. 6**: labelled post hoc, with n per group and CIs; the caption states that the predictor shares models with the outcome. |
| Fig. 4 pooled | Removed. Its content is in Fig. 3. |
| (new) | **Fig. 7**: persona-stage audit, every test on the same 289 cuts with Wilson intervals, plus the synthetic dose-response. |
| (new) | **Fig. 8**: correct / withheld / wrong values served under each build (Table 9 drawn). |
| Fig. 11 cards | **Fig. 9**: Okabe-Ito colours plus distinct marker shapes (readable in greyscale); text rule and judge rule in separate panels. |
| (new) | **Fig. 10**: each leaking assistant design next to its reader-faithful counterpart, with paired-difference intervals and the evidence type labelled. |
| Figs. 7-10 screenshots | Removed. |
| Format | Separate vector PDFs (plus 600 dpi PNGs), one font, consistent line widths, self-contained captions. |

## Tables
| Old | New |
|---|---|
| 1 related work | Table 1 (compact comparison). Long summaries removed. |
| 2 tools | Merged into Sect. 5 and the references. |
| 4 individual contributions | Removed. A CRediT statement is in Declarations. |
| 5 hardware/software | Table 3 (models) and Sect. 5 text. |
| 6 datasets | Table 2 (by track). |
| 7 gap per model | Table 5. Every cell now uses one estimator and seed. The old table mixed two bootstrap runs; see the corrections below. |
| 8 cue control | Table 7 (pooled); per-model rows in Table S1. |
| 9a, 9b, 9c, 9d | Table 8 (divergence, hiding, dependence, disclosure) and Table 9 (correct / withheld / wrong). |
| 9e | Table S5 (resolver), plus a sentence on the statistical correction in Sect. 5. |
| 10 runtime | Table S9; key costs in 6.5. |
| 10a, 10b | Table 6. The incomplete arm is stated as excluded. |
| 10c | Table 10 (rules separated). |
| 10d | Table 12. Each row cites its source table. |
| 10e | Table 11. The deterministic and judge-based rows are labelled. |

## Cross-table consistency checks (page 16)
| Check | Resolution |
|---|---|
| +26.0 vs +35.2 / +18.2 / +16.7 | The pooled value is item-pooled over 285 pre-reveal items (135 / 96 / 54); the item-weighted mean of the three gaps reproduces +26.0. Stated in 6.1; asserted in `scripts/paper/journal_numbers.py`. |
| 2,220 questions | 453 items × 4 arms + 68 × 3 closed-book + 68 × 3 title-assisted = 2,220, over all 68 events. The primary analysis uses only the pre-reveal items of the 32 primary test events. Stated in 6.1. |
| 41/685 vs 23/289 | Separate rows with their denominators in Table 8; the text always names the cut set. |
| 18.5% vs 24.6% | Never merged. Each is given with its rule and event count (54 vs 19). |
| Selection 19.4% vs 1.4% | The CI [+4.2, +33.3] is for the paired event-level difference (stated). The descriptive-phrase exclusion is now a fixed, stored rule: +18.3 [+3.3, +36.7] over 20 events (`scripts/paper/posthoc_descriptive_identity.py`). |

`scripts/paper/journal_numbers.py --check main.tex` recomputes every quoted value from the stored results and confirms that each number in the manifest appears in the manuscript (current result: 0 missing).

## References
- **52 entries, each checked against its live record** (Crossref, arXiv API, doi.org handle, ACL Anthology or the URL). The log is `reference_verification.md`.
- **DOIs.** 39 entries carry a DOI; arXiv papers use `10.48550/arXiv.*`. The 13 without one say why in their `note`: three ACL Anthology papers, which have no DOI; Holm (1979), which has a JSTOR URL; and nine vendor, software or model-card pages.
- **2026 preprints.** All six were re-verified, with the version consulted recorded (Jiang & Ferraro v6; Deußer et al. v2).
- **Placement.** Statistical references are cited where each method is used (Sect. 5). Tools and model checkpoints cite their technical reports, and the exact builds are in Table 3. Vendor pages are cited only as evidence that a design exists.
- **Errors found in the old reference list and corrected:**
  - KoCoNovel was listed as LREC-COLING 2024. It is an arXiv-only preprint; it is not in the LREC-COLING 2024 volume.
  - Jiang & Ferraro's "up to 45.2% drop" is not in the current v6. v6 reports 96% → 72% and up to 18%, which is now used.
  - The Open Fiction changelog cited as product evidence now reads "OpenFiction has retired". The reference was dropped.
  - Unverifiable specifics attributed to Chang et al. (571 works, rho 0.74), KoCoNovel (MUC 94.53; 5 of 50 differ), Ma et al. and NarraWorld were removed. Only claims checkable against each record are kept.

## Remove / merge / move (page 18)
| Item | Status |
|---|---|
| Faculty supplement, individual contributions table, screenshots, setup instructions, video and presentation links, course framing, repeated contribution lists | Removed. |
| Tools merged into Setup | Done. |
| Mitigations grouped | Done (4.4). |
| Ablations combined | Done (Table 12; secondary analyses in Table S4). |
| Moved to supplementary | Done: runtime and API logs (S9), human-validation detail (S8), resolver diagnostics (S5), prompts (S6), event manifest (S7), secondary sensitivity results (S4), PD v7 (S3), incomplete arm (S2). |
| Kept in the main paper | The confirmatory null, the oracle's limitations, the key pipeline findings and the cost of the fixes. |

## Corrections found while preparing the revision
These were found while checking every number against its stored source. Each is fixed in the manuscript.
1. **Persona-stage time.** The course report said "about 50% more". The stored summary gives 6.5 s → 13.8 s, about 2×; the 50% figure came from an earlier 9.1 s timing. 6.5 now reports both as single-run timings.
2. **Reference-model v2 interval.** Table 7 of the course report gave [+20.2, +50.7] from one bootstrap run; the figure gave [+20.2, +50.0] from another. All exploratory cells now use one estimator and seed.
3. **Counterfactual suffix count.** "47" is the count on the 289 cuts shared with truncate-and-rebuild. The file's pooled total of 51 is over 304 compared cuts. The text now says so explicitly, and "0 of 296" for the repair is corrected to "0 of 304".
4. **Unstored selection sensitivity.** The old "+15.9 [+2.9, +30.4] over 23 events" excluded one event by hand and was not stored. It is replaced by a fixed rule with a stored result.
5. **Event quality.** 7 of the 68 confirmatory events (2 of the 32 primary) have a descriptive phrase as their "identity". This is now reported (8, Limitations) with sensitivities: H1 -1.1 [-3.8, +1.6] and selection +18.3 [+3.3, +36.7].
6. **Miner and auditor overlap.** The confirmatory miner (Qwen2.5-32B) and auditor (Mistral-Small-24B) are also evaluated models. The pre-registration had named larger models. This is stated in Limitations.

## Open items before submission
1. **Use-of-AI declaration.** It currently names code and annotation only. Springer Nature also requires disclosure of AI assistance with drafting text; confirm the wording with Dr. Satapathy before submission.
2. **Similarity check.** `scripts/paper/overlap_check.py` found no run of 6 or more identical words shared with the abstracts of the cited works (`overlap_check.md`). That is not an iThenticate or Turnitin report; the journal's own check remains to be run.
3. **Overleaf compile.** Compile in Overleaf with the project's own class file. The local build used a public mirror of `sn-jnl` with a local-only shim (`local_build/`); it compiles with 0 errors, 0 undefined references and 0 overfull boxes.

---

# Response to Revision 2: point-by-point

Source: "Echotales - 2nd revision.pdf" (27 October 2026). No experiment was rerun and no quoted number changed;
`journal_numbers.py --check main.tex` still reports 0 numbers not found, and `overlap_check.py` still finds 0 runs of 8
or more identical words. **Table numbers in this section are the new numbering:** the new arms table is Table 2, so the
Revision 1 numbers shift by +1 from Table 2 onward (datasets 3, models 4, metrics 5, exploratory 6, confirmatory 7,
cue control 8, pipeline 9, repair 10, cards 11, canaries 12, synthesis 13).

**Status key:** Done = addressed in the draft; Deferred = the human-annotation work the owner asked to leave for now.

## Critical technical issues
| Issue | Status | What changed |
|---|---|---|
| 1. Scope of F(B,c); stochastic models; seeds | Done | Sect. 3: F is evaluated for one fixed configuration (weights, prompts, decoding, indexes, caches, persistent state). Equality of single outputs is not a complete criterion for a stochastic model; temperature 0 and fixed seeds make it meaningful here, and residual nondeterminism (GPU kernels, API drift) is stated as uncontrolled. |
| 2. Ideal property vs empirical tests | Done | Sect. 3: the experiments are operational tests (removed suffix, a few counterfactual suffixes, canaries, selection), not proofs of Definition 1 for all books and suffixes. |
| 3. What F includes; components held fixed | Done | Sect. 3 and 4.3: entity resolution is held fixed in truncate-and-rebuild to isolate the persona stage; this cannot see a resolution dependence, so the selection experiment tests the merge decision directly and a prefix-causal resolver check is cited. |
| 4. Behavioural leakage vs pipeline dependence | Done | One sentence in Sect. 3 that an internal change is not itself a spoiler; same wording in the abstract, Fig. 7 and Table 9 captions, 6.3, 8 and 9. |
| 3.2 Reveal oracle; human validation | Done (wording) / Deferred (new work) | Abstract, 4.1, 6.1 and 8 now say the oracle marks the first selected explicit reveal sentence, not the first inferable point, and that 34/36 validates explicitness, not every event's suitability or an unbiased selection; the disagreements are described as ambiguity. **Deferred:** a further annotation round, an annotation rubric with examples and disagreement categories as new supplement material, and human-validated labels for the pipeline disclosures. Supplement S8 is unchanged. |
| Memory result: familiarity unconfirmed | Done | 6.1 and 6.2: familiarity is a plausible interpretation, not a demonstrated moderator or the explanation of the failed replication; P1 was inconclusive; the exploratory association is not causal evidence; the cue-preserving arm is consistent with name-specific memory but not a mechanism; the incomplete Claude arm stays out of pooled estimates; the confirmatory null leads the abstract and the +26.0 is labelled exploratory. |
| Pipeline audit and model labels | Done | 6.3: 41/685 kept apart from 1.7-3.5%; disclosure labels are model-produced and one annotator implemented the repair (bias source stated in the main text, not only Sect. 8); the hiding result (23 to 82) and counterfactual-suffix result (47 vs 23) are kept; zero divergence is called zero *observed* divergence, not a guarantee; the 289- and 685-cut denominators are never merged; Sect. 8 states the Wilson intervals are optimistic for nested cuts from three serials. |
| Generic-assistant experiments | Done | 6.4: text rule and judge rule kept separate; versioned-card rates bounded to the tested prompts and generators; the long-context design (24,000 / 16,000 characters, marker line, 46 events, exact-match rule) is stated beside the 40.6%; zero-hit controls are described as validating the tested controls and harness; alias-merged retrieval stays preliminary because the judge is least validated there; content and selection leakage stay separate. |
| Mitigation claims bounded | Done | Abstract: "zero observed leakage under the reported prefix-built or truncated controls"; 6.5 and 7 unchanged in substance (pseudonymisation a measured trade-off; repairs succeed in the tested configurations only); Sect. 9 no longer repeats rates. |

## Section by section
| Section | Status | What changed |
|---|---|---|
| Abstract | Done | Confirmatory null first, +26.0 labelled exploratory; divergence-is-not-disclosure; 34/36 caveat; "zero observed leakage" wording. The structured labels stay; convert to one paragraph if the journal requires an unstructured abstract. |
| 1 Introduction | No change needed | Three RQs and three contributions kept, no project-history subsection (red note in the review). The RQs are now answered one by one in Sect. 9. |
| 2 Related work | Done | 2.3 states, for each closest system, what it enforces (reader-visible evidence horizon, story time, consistency, belief views); Table 1 cells the documentation does not support are "Not stated" and the caption says entries follow published descriptions; 2.4 says vendor documentation shows a design exists, not that it was evaluated. No tools subsection, no 2020 cut-off. |
| 3 Formulation | Done | Definition stays in the main text; plain-language gloss added; item-pooled vs event-weighted kept; "leakage gap" is defined once as the original minus the mean of the two ciphers and other contrasts are named; recovered fraction flagged unstable near a zero gap; Definition 1 not presented as a theorem. No extra subsection. |
| 4.1 | Done | Deterministic matching verifies after model proposal; unique-reveal rule and fallback cutoff stated; descriptive identities handled by a stated fixed rule (identity starts with an article or pronoun), re-applicable from the manifest and `posthoc_descriptive_identity.py`. |
| 4.2 | Done | New Table 2 (arms A, B/B2, B3: transformation, cues kept, role); the validity gate is described per model and dataset (v2 and v3: Gemma-2-9B, Llama-3.1-8B, Mistral-7B and Phi-4-mini pass; Qwen2.5-7B and the reference model fall below 90% cipher agreement and are kept out of the gated pool only). |
| 4.3 | Done | Reason for fixing resolution; nested cuts and optimistic intervals; the English check is a limited transfer check; model labels kept apart from deterministic divergence. |
| 4.4 | Done | Duplicated judge-limitation text replaced by a pointer to 6.4; full prompts remain in the supplement. |
| 5 | Done | Table 3 caption: reuse of confirmatory events is not independent replication. Models: ollama image IDs added, read from the installed models on 27 Oct 2026 (not recorded at run time); the vLLM checkpoints have no stored revision hash and the commercial model no snapshot identifier, and the text says so. The statistical protocol lists which analyses use item-pooled, event-weighted and random-effects estimates. **Holm verified:** the registration's final addendum (`PREREG_PD_CONFIRM_v2_addendum_5.md`) makes H1, H2, H3, H5 the Holm family and tests P1 alone at 0.05; the manuscript already matched, and now states that P1 is outside the family and labels raw vs adjusted p-values in Table 7 and the text. The reproducibility paragraph says only what the scripts can do. |
| 6.1-6.5 | Done | See the rows above. |
| 7 Discussion | Done | "Across systems" became "within the implementations we tested"; the memory pattern is "conditional ... not confirmed in the primary analysis"; the engineering principle names derived state and selection decisions. No new subsection, no new numbers. |
| 8 Limitations | Done | Event ambiguity might affect the between-arm difference (the arms-equal argument is plausible, not guaranteed); disclosure rates are provisional and the human check does not extend to the pipeline audit; nested cuts scope the audit to these serials. |
| 9 Conclusion | Done | RQ1-RQ3 answered explicitly; the final lesson keeps "markers and timestamp filters are insufficient when upstream processing has already used future information" and "does not establish universal spoiler-free behaviour". The future-work human item is stated as a larger independent sample recording both explicitness and prefix inferability, with human-validated disclosure labels on shareable or synthetic text. |

## Review round 3 (third review comments)
Status key: **Text** = addressed by wording or restructuring in `main.tex`; **Pending** = needs new evidence or an owner action (see the open list below); none remain except the Overleaf layout compile.

| Comment | Status | Where / what changed |
|---|---|---|
| Abstract: zero-leakage sentence names the tested controls | Text | "Prefix-built representations and physically truncated inputs produced zero observed leakage in the reported tests." |
| Abstract: 34/36 is an explicitness check only | Text | Limitations sentence says it is not validation of the whole corpus and not proof the identity was unknowable. |
| Abstract: keep four findings, move secondary percentages | Text | Kept confirmatory null, +26.0 exploratory, 41/685, and one selection result (19.4% vs 1.4%); card range removed. |
| Keywords | Text | Added Non-interference and Information-flow control; dropped "Information leakage" and "Large language models" to stay at six. |
| Sec 1: project mention to one sentence | Text | Done. |
| Sec 2.3 critical comparison; 2.4 vendor docs not evidence | Text | Added the story-time/belief/consistency versus enforced evidence-horizon distinction; product documentation stated not to be evidence of effectiveness. No tools subsection added. |
| Sec 3: fixed configuration versus book-derived state | Text | Definition rewritten as configuration plus state-construction process; all book-derived state is rebuilt for $B'$; the held-fixed entity assignment in truncate-and-rebuild is named as a deliberate departure. |
| Sec 3: stochastic systems | Text | Temperature 0 and seeds give operational reproducibility, not distributional equality; tests are sampled operational checks, not verification. |
| Sec 4.1 rubric and examples | Text | Rubric summary in 4.1; supplement table of representative events (explicit, implied, already inferable, two invalid), checked against the stored labels. |
| Sec 4.2 pseudonym caveat | Text | One sentence added. |
| Sec 4.3 evaluator bias; raw pairs primary; adjudication as sensitivity | Text | Stated; the 36-event and 48-cut checks are kept distinct in 4.3 and 8. |
| Sec 5 Table 4 / model reproducibility / identifier | Text | Model name stated as sent to the API, reasoning effort none (verified in `scripts/chimera/pd_v2_luna.py`, `pd_v3_luna.py`, `l1_llm_leakage.py`, `scripts/prefix_audit/luna_labels.py`), no snapshot or returned model string recorded; runs not described as exactly reproducible. |
| Sec 5 nested cuts | Text, new analysis | Statistical unit stated; intervals descriptive; `scripts/paper/serial_level_sensitivity.py` gives per-serial divergence (10/179, 7/122, 24/384; 5.6 to 6.2%) and leave-one-serial-out (5.6 to 6.1%); three serials support no population inference. |
| Sec 5 independence of replications | Text | Card, canary and selection experiments described as complementary tests. |
| Sec 5 repository tag | Done | Tag `journal-rev3-2026-10-31` (commit 77dd0e9) pushed; the availability statement names it and lists the 48-cut labels, the third reader's labels, the scoring script, the event manifests and the number registry; the old disclaimer is removed. |
| Sec 6.1 disagreement table | Text | Table added (raw agreement and events with a disagreement per question). |
| Sec 6.2 familiarity | Text | Group sizes, estimate, interval and inconclusive status reported together; not a moderator. |
| Sec 6.3 anchored cue | Text | Non-transfer made explicit as a limit on generality. |
| Sec 6.4 judge validation, versioned cards, Fig. 10, negative controls | Text, new evidence | Judge-rule result called not fully model-independent; cards described as tested configurations; Fig. 10 caption states the metrics differ. The known-truth judge test is done: 120 synthetic cards, paper's judge finds 30/30 explicit and 19/30 implied identifications and rejects 59/60 negatives, so it is conservative and judge-rule leak rates are more likely understated (supplement table; `scripts/paper/judge_known_truth.py`). |
| Sec 6.5 runtime | Text | Timings described as indicative; per-run values left to the supplement. |
| Sec 7, 8, 9 repetition | Text | Numbers removed from the Discussion; Limitations rewritten by effect on conclusions with the two human checks separated; Conclusion shortened to RQ1-RQ3. |
| Evidence-strength labels, terminology, faithfulness versus utility | Text | Four labels defined in Sec 5; terminology paragraph in Sec 3; utility stated as an evaluation principle in Sec 3. |
| Independent human annotation round; model-judge known-truth test | Known-truth test done; human round partly | Judge test as above. For the 48-cut disclosure check the first author's labels were found to be partly name-based and now lose every split; an independent third reader (not an author, had read none of the books) labelled the 11 earlier-ruled cases from the passages alone on 2026-10-31 and settled the 3 gender and 2 of the 3 support splits; the headline numbers did not move. |

## Open after this revision
1. **Human annotation:** partly done on 2026-10-30. The supplement now gives the reveal-check rubric, an example and four disagreement categories, and a 48-case human check of the disclosure labels was run and reported (main text and supplement). On 2026-10-31 the first author's labels were found to be partly name-based (0 'undetermined' in 32 cases against 7 and 8; knew the plot in 22 of 32), so on every split the other annotator now stands and the original first-author rule is reported beside it (S1 model-judged disclosures not supported: 9 of 10 against 2 of 10; served value not supported 11 of 34 against 4 of 35). The third reader's labels (all 11 earlier-ruled cases, none of the books known) settled the 3 gender splits and 2 of the 3 support splits and reproduce the model passages-only reading in 11 of 11 cases; the remaining support split (C020) was not in the set that reader received and stays out of the served-value counts. Still open: human-validated labels on shareable or synthetic text.
2. **Not recorded, so not claimable:** vLLM checkpoint revisions, the commercial-model snapshot, and ollama IDs at run time. Sect. 5 says so; recording them in the next run would remove the caveat.
3. **Repository pointer:** closed. Tag `journal-rev3-2026-10-31` (commit 77dd0e9) is pushed and named in the availability statement.
4. **v6 validity gate:** closed. The result is stored in `data/eval/chimera/pd_v6/analysis.json` (per-model `G2a`, with `G2b` taken from each model's v3 run) and `data/eval/chimera/pd_final_pooled.json` (`per_dataset_valid_models`). Llama-3.1-8B, Mistral-7B and Phi-4-mini pass on v6; Gemma-2-9B (0.857), Qwen2.5-7B (0.875) and the reference model (0.839) fail the 0.90 criterion. Sect. 4.2 now says so and notes that the v6 local pool is three models.
5. **Abstract style:** the abstract is about 281 words in five labelled parts. The target journal's word limit is not recorded in the repository, so it has to be checked against the journal's author guidelines before submission; shorten if the limit is 250 or less.
6. **Still open, needs the owner:** the C020 support split (never shown to the third reader), and human-validated labels on shareable or synthetic text.

---

# Response to Review Round 4 (final): point-by-point

Source: "Echotales Review 4 Final.pdf" (4 November 2026). Table and figure numbers below are those of the submitted
manuscript. Figure 8 of the previous draft (repair outcomes) was removed as an exact duplicate of Table 12, so the card
figure is now Fig. 8 and the leak-by-design figure Fig. 9; table numbers are unchanged (1-15).
`journal_numbers.py --check main.tex` reports 0 numbers not found after every change.

## Critical abstract and conclusion consistency issue
| Comment | Status | What changed |
|---|---|---|
| "Prefix-built representations and physically truncated inputs produced zero observed leakage" is too broad | Done | Abstract Results now follow the suggested replacement: 41/685 deterministic divergence in a *component-level* audit; zero observed divergence under evidence-horizon versioning in the tested configurations; whole-volume content leakage; 19.4% *model-judged* disclosure for future-informed merging against 1.4% for the prefix-causal index; zero observed suffix-canary hits for physical truncation in the tested long-context configuration. Limitations: model-selected events, model-judged disclosure labels with limited independent human validation, three nested serials cannot support population-level estimates. |
| Same issue in the conclusion and elsewhere | Done | Sect. 9 RQ2 rewritten per control (versioning, truncation, prefix cards with the judge-rule residue stated); Sect. 6.5 no longer says prefix rebuilds "removed the observed leak" and gives deterministic and model-judged results separately (prefix cards 1.2% judge, prefix index 1.4%); Sect. 8 "zero-hit" sentence corrected to name only the zero results that exist; Sect. 6.4 states the prefix-card 1.2% judge-rule rate and why it cannot be suffix leakage without rounding it to zero. |

## Priority 1
| Item | Status | Where |
|---|---|---|
| Correct overbroad abstract statement | Done | Abstract; see above. |
| 19.4% vs 1.4% identified as model-judged, not human-validated | Done | Abstract ("model-judged"), Sect. 6.4 ("Both rates ... are model-judged; no person labelled these cards"), Table 15 evidence column (M), Sect. 8, Sect. 9. |
| Verify "gpt-5.6-luna" against request logs and the official identifier | Done | Sect. 5 and Table 4. Request bodies in `scripts/chimera/l1_llm_leakage.py::call_model` and `scripts/prefix_audit/luna_labels.py` send exactly `gpt-5.6-luna` to `https://api.openai.com/v1/chat/completions` with `reasoning_effort: none`; scripts exit on any non-200, so every stored answer came from an accepted request, and every stored run file records the model string and the API-returned token usage. The vendor model page (developers.openai.com/api/docs/models/gpt-5.6-luna, checked 4 Nov 2026) lists `gpt-5.6-luna` as the model ID and its only snapshot, with chat completions, reasoning effort `none`, and the $0.20/$1.20 per 1M prices used in our ledger. Not verifiable and stated: the response `model` string and `system_fingerprint` were not stored. |
| Persona-stage experiment is component-level, not end-to-end | Done | Sect. 3 (third qualification), 4.3, opening of 6.3, abstract, Sect. 9. |
| Preserve raw 48-cut pairs and original-vs-revised sensitivity | Done | Table 11 keeps the raw pairs and both rules; the supplement now lists every case-level label under both rules; the scorer runs from a committed passage-free case key (`data/eval/validation/disclosure_cases_key.json`). |
| Keep six-of-18 validity disagreements prominent | Done | Sect. 4.1 examples, 6.1 text and Table 8, Sect. 8 (unchanged in substance). |
| Three nested serials cannot support population-level estimates | Done | Abstract Limitations, Sect. 5 statistical protocol, 6.3, Sect. 8. |
| Final repository tag contains labels, scoring script, manifests, outputs, analysis files | Done | Tag `journal-rev4-2026-11-04`; the supplementary reproducibility map is generated by a script that asserts every listed path exists and marks gitignored (copyrighted) inputs as local-only. |

## Priority 2
| Item | Status | Where |
|---|---|---|
| Short examples for all four reveal-validation categories in 4.1 | Done | Sect. 4.1: explicit (Oliver Twist, Monks -> Edward Leeford), implied (The Red-Headed League), already inferable (King Solomon's Mines), invalid (Dracula's Guest; the first-person "I" event), each with the annotators' labels. |
| Independent human-validated or known-truth test for the selection-leak judge | Done (known truth) | New `scripts/paper/judge_known_truth_selection.py`, output `data/eval/judge_known_truth_selection.json`: 120 synthetic card-length texts on cipher-like invented names, shaped like merged-retrieval cards (both names present). Paper's judge: 0/60 false positives on two-name negatives (Wilson upper 6.0%), 30/30 explicit, 14/30 implied; second family agrees 111/120. So judge false positives cannot produce the 19.4% merged rate, and the rate is more likely understated. Sect. 6.4 and supplement. Human labels on the real selection cards were not collected; stated. |
| Exact API request metadata, recoverable checkpoint and tokenizer hashes | Done | Supplement "Model and request manifest": request body, per-run calls and tokens; ollama GGUF blob SHA-256 (the GGUF embeds the tokenizer) with manifest dates preceding all runs; vLLM repository revisions recovered from the Hub (each last modified before the October runs). Sect. 5 says these were recovered after the fact, not logged. |
| Statistical interpretation of random effects with three models | Done | Sect. 5: DL tau^2 = 0, so the pooled point estimate is the precision-weighted average of the three models; Hartung-Knapp uses t with 2 df; H1 is a summary of these three models, not a population mean; per-model estimates are primary. |
| Evidence-strength comparison, or integrate into Table 15 | Done | Table 15 rebuilt with Cost and Evidence (D/M/H/P) columns. |
| Observable system boundary and equality criterion in Sect. 3 | Done | New paragraph "Observable boundary and equality" in Sect. 3, with the equality rule per component type. |

## Priority 3
| Item | Status | Where |
|---|---|---|
| Reduce duplicated numbers across figures and tables | Done | Old Fig. 8 removed (duplicate of Table 12); 6.3 text points to Table 10 instead of repeating its rows; 48-cut model-reader consistency details moved to the supplement. |
| Figure 9 readability; simplify Table 15 | Done | Card figure redrawn (stacked panels, horizontal 8.5 pt labels, labelled size separator, legend outside data); leak-by-design figure: no negative axis, zero-rate bars labelled, legend clear of intervals. Table 15 simplified to one line per channel with ragged columns. |
| Shorten the contribution paragraph | Done | Sect. 1: three numbered contributions in four sentences. |
| Move low-level details and prompts to supplement | Done | Prompts already in the supplement; 48-cut secondary agreement and model-reader checks moved. |
| Rename "What the limitations do not touch" | Done | Now "Scope of the limitations". |
| Reformat in the Elsevier template | Not applied | The manuscript targets a Springer Nature journal and is in the current `sn-jnl` template; switching to Elsevier would only be right if the target journal changes. Flagged to the authors. |

## Supplementary arrangement
Followed the reviewer's placement table. No appendix was created; everything is in Supplementary sections and tables.

## Additional changes from a final internal referee pass
- Table 8 (reveal disagreements) is now cited in the text; tables and figures are numbered in order of first citation (checked by script).
- Figure files renamed to their printed numbers: `fig8_cards.pdf` (was `fig9_cards`) and `fig9_leak_by_design.pdf` (was `fig10_leak_by_design`); `fig8_repair_outcomes` removed. Fig. 8 no longer carries a duplicate outer y-axis label.
- Ethics statement now names the external volunteer reader; "further"/"third" reader unified as "external reader"; "Consent for publication" and "Code availability" declarations added.
- Abstract: the exploratory commercial-model gap is described as not reproduced with the open models (the reference model was not in the confirmatory study); the truncation result is stated beside the 40.6% long-context leak it controls for. Abstract length 231 words.
- Wording tightened where a claim outran the evidence: "will leak" -> "can diverge from a prefix build"; "the resolver is prefix-causal" -> "no entity change in this check"; "certify cuts as safe" -> "mark cuts at which the code allows no divergence"; "The repairs that worked" -> "that reduced leakage"; naive repairs "left substantial leakage", with the text-rule spoiler-instruction interval reaching zero stated.
- Second judges named (OLMo-2-32B for the 684-label agreement; Gemma-2-9B in both known-truth tests, added to Table 4); the two 120-card known-truth sets are distinguished.
- Table 10 caption and 6.3 give the counterfactual denominator (304 cuts, status quo 51, of which 47 on the 289 truncation cuts). Table 14 gives the selection paired difference. Birthplace canary denominators stated. Recap check labelled model-judged.
- Number registry gains `judge_kt_selection`; four 48-cut detail keys moved to the supplement are listed as not quoted in the main text. `journal_numbers.py --check`: 0 missing. `overlap_check.py`: 0 sentences with an 8-word run shared with a cited abstract. Local build: main 41 pages, supplement 17 pages, 0 errors, 0 overfull boxes, 0 undefined references.

## Open after this revision (for the authors, not the reviewer)
1. Target journal and template: the reviewer's last item names an Elsevier template; the manuscript is in Springer Nature `sn-jnl`. Keep as is unless the target journal changes.
2. Abstract word limit of the chosen journal (now 231 words).
3. Human labels on the real selection-leak cards were not collected; the known-truth test bounds the judge instead, and the text says so.
