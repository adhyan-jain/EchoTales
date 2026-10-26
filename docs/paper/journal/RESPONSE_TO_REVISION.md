# Response to Revision 1: point-by-point

Manuscript: *Reader-Faithfulness in LLM-Based Narrative Assistants: Measuring Parametric Memory Leakage and
Future-Information Leakage in Processing Pipelines* (first draft, 26 October 2026).

**Files:**
- `main.tex`: one file, no `\input`, in the Overleaf `sn-jnl` template.
- `references.bib`: 52 entries.
- `figures/fig1-6`: vector PDF, plus 600 dpi PNG.
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
| 1 | Rebuild as a research article; numbering of sections, figures and tables | Done | Article order. Sections 1-9 are numbered continuously. Figures 1-6 and Tables 1-12 are numbered in order of first citation, and every float is cited before it appears. There are no sub-numbered tables. |
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
| 6.1 | Exploratory and confirmatory as separate blocks; why they do not contradict | Done (Fig. 3, Tables 5-6). Wording: "consistent with a familiarity-dependent effect". |
| 6.2 | Pseudonym result concise; recovered-fraction interval and pre-registered rule; familiarity post hoc with group sizes and CIs | Done (Fig. 4, Table 7, Fig. 5: groups n = 20/6/12 with bootstrap CIs; six-level counts 10/10/4/2/5/7 in the text). |
| 6.3 | Tables 9a-9e consolidated; distinct denominators; zero *observed* divergence; costs visible | Done (Tables 8-9). Resolver diagnostics moved to the supplement (Table S5). |
| 6.4 | Text rule vs judge rule separated; content vs selection in separate paragraphs; which result is deterministic | Done (Table 10, Fig. 6, Table 11). |
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
| Fig. 2 cue control | **Fig. 4**: one panel with CIs; A, B and B3 defined in the caption. Per-model numbers in Table S1. |
| Fig. 3 dose-response | **Fig. 5**: labelled post hoc, with n per group and CIs; the caption states that the predictor shares models with the outcome. |
| Fig. 4 pooled | Removed. Its content is in Fig. 3. |
| Fig. 11 cards | **Fig. 6**: Okabe-Ito colours plus distinct marker shapes (readable in greyscale); text rule and judge rule in separate panels. |
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
1. **Author emails.** The three student emails are placeholders in `main.tex`.
2. **Use-of-AI declaration.** Confirm the statement on Claude Code with Dr. Satapathy (Springer Nature requires such disclosure).
3. **Overleaf compile.** Compile in Overleaf with the project's own class file. The local build used a public mirror of `sn-jnl` with a local-only shim (`local_build/`); it compiles with 0 errors, 0 undefined references and 0 overfull boxes.
