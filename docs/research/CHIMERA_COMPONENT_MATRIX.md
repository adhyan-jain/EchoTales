# CHIMERA component matrix (Checkpoint 1)

| Field | Value |
|---|---|
| Commit | `6c7e2c2`, 2026-10-15 |
| Basis | The audit (`CHIMERA_REPOSITORY_AUDIT.md`) for the original methods; `CHIMERA_PRIOR_ART.md` for alternatives. Nothing here was benchmarked. |
| Ran | Nothing. This is a design comparison. Every "cost" is an [INFER] estimate; every "evidence it helps" cell says what I actually have |
| Status of every selection | **Provisional.** Each carries an evaluation plan; none is justified by a measurement yet |

Reading guide. For each component: the **original** method (what the repo does), at least two **alternatives**, then a short answer on the questions the directive requires: failure addressed; direct evidence it helps (here: from the repo or from papers I read, else "none"); cost; assumptions; whether the output can be validated; whether it leaks or propagates error; fit with current code; reproducible within about $10-15 of GPU; whether the benefit survives downstream.

**Precision vs recall rule applied throughout.** The system's own design (non-negotiables 7 and 9) is precision-first. A method that raises mention recall by adding false entities can damage state downstream: a false entity creates alias bindings, appears in `state_of`, and can be drawn or voiced. So every recall-raising option below is scored by precision on the added mentions, not by recall alone, and none is accepted without a human-labelled precision estimate on the *added* items.

---

## 1. Entity recognition (mention detection)

| | Original | Alt A: fine-tuned encoder NER (DiffusionNER-style or BERT tagger) | Alt B: instruction-tuned LLM with retrieved examples (the MetaRetrieval idea) | Alt C: curated-lexicon repair of the existing detector |
|---|---|---|---|---|
| What it is | Gazetteer + qwen2.5:7b NER in 6,000-char windows, then alias-type classification, then whole-volume commonness filter (audit section 6) | Supervised span tagger | In-context examples fetched by similarity (GenWebNovel's mechanism [PUB]) | Fix the traced defects: pass `is_address`, widen the 23-entry title list, review `AMBIGUITY_BLOCKLIST` and the commonness filter for deictics |
| Failure addressed | - | Boundary and type errors | Genre adaptation and recall of unusual surface forms | Hard cases lost at detection: 58 of 88 are undetected, though at most 55 are real losses [INSPECT] |
| Direct evidence it helps | Baseline: LitBank name-level F1 42.4, full key 15.9 [REPO] | GenWebNovel reports DiffusionNER 72.10 F1 on Chinese text [PUB]; none on English translations | GenWebNovel reports 73.74 vs 62.64 for a plain 3-shot Llama [PUB], Chinese only | **No measurement.** The traced defects are real [INSPECT: `is_address` unused; blocklist; 23 titles]; their effect size is unmeasured |
| Cost | existing | Needs training data; **no human gold exists for EchoTales** [INSPECT] so training would use silver labels, which carry model errors | Per-chunk LLM calls; local qwen2.5:7b is already used | Engineer-days, CPU only |
| Assumptions | Names and titles only; generic descriptors excluded (non-negotiable 4) | Labelled spans in the target language and schema | Retrieval pool of correctly labelled examples; GenWebNovel's PER schema **includes** descriptors, conflicting with non-negotiable 4 | Hand lists generalise across novels |
| Validatable? | Only against silver today | Only with human labels | Only with human labels | Yes, by hard-case recall and precision on added mentions, **once** human labels exist |
| Leaks or propagates error | Missed mentions silently vanish | Silver-label errors would be baked in | Retrieved examples can inject wrong labels | Loosened filters add false mentions, which propagate to state |
| Fit with code | - | New dependency, GPU training | Fits `mentions/ner.py` prompt path | Fits directly; smallest diff |
| Reproducible in budget | - | Probably not on this host (no GPU use without approval) | Local model only if the owner approves a run | Yes |
| Survives downstream? | - | Unknown | Unknown | Unknown: depends on whether detected hard cases then resolve correctly; resolution of titles and deictics also has defects (FORCE_LINK ordering, alias absorption) |
| **Provisional choice** | | | | **Alt C first** (cheap, diagnosed), measured on human-verified hard cases. Alt B only as a labelled approximation on GenWebNovel after D3. Evaluation plan: T2 headroom test, then precision on the added mentions with two annotators |

## 2. Mention normalisation (names, titles, translation variants)

| | Original | Alt A: rule-based canonical forms plus translator-variant tables | Alt B: LLM-proposed variant clusters, human-reviewed |
|---|---|---|---|
| Original | `display_label`, `alias_type`, morphology stripping (`ingest/normalize.py`, `mentions/alias_type.py`) | | |
| Failure addressed | Surface variants of one name | Translator-induced variants | Same, at scale |
| Evidence | None quantified for variants | None | None |
| Cost / assumption | existing | Per-novel tables; needs aligned or parallel text to build well (GuoFeng-style aligned data is unopened, licence unknown) | LLM calls plus review time |
| Error propagation | A wrong merge creates a false link that is hard to undo (non-negotiable 1: incremental, no clustering) | Same risk if tables are wrong | Reviewed clusters limit risk but need human time (D5) |
| **Provisional choice** | Keep original; do **not** add Alt B without D5 and a precision estimate | | |

## 3. Entity resolution

| | Original | Alt A: retrieval + learned scorer with calibrated gate | Alt B: LLM adjudication of deferred cases | Alt C: evidence-gated link requiring citeable in-prefix spans (candidate C1 mechanism) |
|---|---|---|---|---|
| Failure addressed | - | The scorer currently links nothing (max probability 0.550 vs 0.80 gate) [REPO, SCORER_DIAGNOSIS]; decisions come from pre-filters (101 FORCE_LINK / 2 BLOCK / 0 SCORE on gold candidates) | `adjudicate_remaining` exists but is unreachable from the CLI and discards its outcome [INSPECT] | Premature or leaked links |
| Evidence it helps | - | Diagnosis says three of five weighted features are constant and temporal fields are never populated [INSPECT: audit 6] | None measured | **None**; hinges on T3 |
| Cost | existing | Needs real feature inputs (`speaker`, `temporal_certainty`, scene scope) wired in | LLM calls on the queue | New module |
| Validatable? | Silver | Needs human labels | Needs human labels | Needs reader-view labels, which do not exist |
| Propagates error? | FORCE_LINK takes the first candidate in retrieval order, so order is load-bearing [agent-reported] | Better features could raise precision or just move errors | A recovered-looking link that is not written would mislead counts (the same defect already exists in `retry_deferred`) | Could cut recall |
| **Provisional choice** | Fix the **instrumentation** first: make `retry_deferred` write or stop reporting "recovered"; wire `speaker`. Candidate C1's gated link only if T3 shows leakage above chance. Plan: paired comparison against the original on human-verified items, reporting precision and recall separately |

## 4. Fact extraction

| | Original: regex detectors + whole-run LLM sampling for appearance | Alt A: per-chapter causal extraction (LLM sees only chapters <= c, stamps at c) | Alt B: span-grounded extraction with verbatim-quote requirement |
|---|---|---|---|
| Failure addressed | Later evidence can shape an earlier-stamped fact [agent-reported: `appearance_extract.py:481-533, 781-811`] | Look-ahead | Hallucinated facts |
| Evidence | None quantified | None | NarraWorld restores exact evidence spans and verifies references before commit [PUB, Appendix A.1] |
| Cost | existing | ~N LLM calls per entity per chapter instead of one sample; local model needs approval | Moderate |
| Validatable? | Silver | Yes against a prefix oracle (deterministic fixtures, Gate 5) | Yes by span containment (mechanical check) |
| **Provisional choice** | Alt B's mechanical grounding check is cheap and testable at $0; Alt A only if a claim about disclosure faithfulness is pursued. Plan: fixture with a fact that is true early but only stated late; assert it is not visible before its disclosure chapter |

## 5. Narrative memory

| | Original: SQLite bitemporal store | Alt A: NWM-style typed temporal-state graph [PUB] | Alt B: NarraWorld four-view memory (world, belief, development, hypothetical) [PUB] |
|---|---|---|---|
| Note | Already has story time, disclosure time, observer, retraction columns [INSPECT] | Reveal order stored separately from event order | Admissible-view projection |
| Evidence | Axes exist and are tested; real data is thin (12 observations, 0 retractions, 0 relations) [INSPECT] | Authors report gains over Graphiti/Zep on their benchmarks [PUB, authors' numbers] | Authors report ablation gains [PUB] |
| Cost to adopt | - | Reimplement (proprietary backend withheld) | Reimplement (code not released) |
| **Provisional choice** | Keep the original. Alt A and B are baselines and design references, not replacements (the repo's own non-negotiables already cover most of their semantics) |

## 6. Temporal reasoning

Original: three-axis model with fuzzy endpoints; `state_of` (core/state.py). Alternatives: (A) TAC-KBP-style bounded temporal slot filling (not read this checkpoint, so [LEAD] from the directive only); (B) pure interval algebra without discourse time (loses the disclosure axis, which is the repo's distinguishing feature). **Provisional choice:** keep the original; its weak point is not the algebra but the **writers** (look-ahead stamps, zero retraction writers, `appearance_of` bypass), which is an integration defect list, not a method choice.

## 7. Retrieval

Original: `CandidateRetriever` over entity profiles; `story_context` for the director. Alternatives: (A) query-conditioned hybrid retrieval over a typed graph (NWM [PUB]); (B) admissible-view-then-retrieve (NarraWorld [PUB]). Failure addressed: the director brief filters only by disclosure chapter and ignores observer and story time [INSPECT]. **Provisional choice:** apply the admissible-view idea (filter first, retrieve second) to `story_context` by routing it through `state_of`, which is an integration fix. Plan: fixture where the observer should not see a fact; check the brief.

## 8. State reconstruction

Original: `state_of` + `compile_generation_state`; but attributes bypass it via `appearance_of`, and four policies coexist (audit section 5). Alternatives: (A) one policy object consumed by every render path (the Gate 7 design); (B) leave as is and document. **Provisional choice:** A, but only as an integration step, because this is wiring, not a research contribution. Success test: the same fixture yields the same visible fact set in image prompt, director brief, voice casting and cache key.

## 9. Provenance

Original: `Attribute` provenance exists in some paths (`resolve_admissible_attributes`), dropped by `state_of`'s return type; `ref_image_candidate` / `ref_image_selection_log` tables exist. Alternatives: (A) NarraWorld-style single provenance chain per record [PUB]; (B) content-addressed lineage with parent-asset checks (the repo's visual-memory design). **Provisional choice:** carry provenance through `state_of`'s result (small API change) before claiming any provenance contribution. Whether a transitive lineage check catches leaks that a simple cutoff filter misses is exactly the open question for C4 and is untested on real data (no retractions, no relations exist).

## 10. Visual reference selection

Original: `reference_images=[]` in production [INSPECT]; the selection code runs but its result is discarded; metadata still says "conditioned". Alternatives: (A) re-enable reference conditioning with the old IP-Adapter path (**permanently removed** per the project's rendering decisions; do not reopen); (B) hosted reference-capable model; (C) the unwired `VisualMemorySelector`. **Provisional choice:** none until the metadata is made honest. Any visual claim must first state that production has no reference conditioning. Selecting references without a generator that uses them cannot be evaluated; note also that text-only tests cannot establish image correctness.

## 11. Generation

Original: gemma2:9b director, NoobAI XL. The image stack is a settled project decision (NoobAI primary, no multi-model per image). **Provisional choice:** no change; generation is demonstration surface, not the contribution.

## 12. Evaluation

| | Original: silver gold + LitBank | Alt A: human adjudication of the existing 288-item package | Alt B: reader-view gold in the KoCoNovel style (Reader and Omniscient labels) | Alt C: LLM-as-judge |
|---|---|---|---|---|
| Evidence it helps | Only LitBank is human-keyed [INSPECT] | The package exists and its tests pass (25/25) [INSPECT] | KoCoNovel is a direct precedent [PUB] | Not a ground truth; labels from models cannot validate models (rule: LLM labels are never ground truth) |
| Cost | existing | Human hours (D5) | Human hours plus a protocol | Cheap but invalid as gold |
| **Provisional choice** | | **A first** (it unblocks T1, T2, T6), then B only if C1 or C2 survive the gate. Alt C only as a triage aid, never as a number reported as accuracy |

---

## Cross-cutting conclusions (INFER)

1. The cheapest, best-diagnosed improvements (Alt C for detection, honest `conditioned_on`, `retry_deferred` instrumentation, `--chapters` flag, wiki canon dating, `story_context` through `state_of`) are **engineering fixes**, not research contributions. They also change how every existing number should be read.
2. No component alternative has a measurement behind it on EchoTales' data. All selections wait on human-verified labels, because the existing gold is model-provenance.
3. Nothing in this matrix supports a novelty claim.
