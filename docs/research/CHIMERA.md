# CHIMERA program: plan, gate, prior art, data plan, annotation guide, defects and errata

> Merged on 2026-10-22 from 9 separate documents to keep the docs tree small. Each section below is one original file, text unchanged; its old path is in the section heading. The originals are in git history.

---

<!-- merged-from: docs/research/CHIMERA_ANNOTATION_GUIDE.md -->
## Source: `docs/research/CHIMERA_ANNOTATION_GUIDE.md`

# CHIMERA pilot annotation guide (single annotator)

For: the owner, one sitting-day. Sheet: `data/eval/human_review_chimera_pilot.csv` (72 items, local only, gitignored). Do not share the sheet or the key; both contain excerpts of the novel.

This is a **single-annotator pilot**. There is no second annotator, so there is no agreement statistic. Results will be reported as counts with Wilson intervals only, labelled "single-annotator pilot".

## 1. What you are labelling

Each row marks one mention in the novel with `[[double brackets]]` inside a source window of about 400 characters. For each mention you give **two** answers:

1. **`reader_warranted`**: who a careful first-time reader of the book is warranted in taking this mention to refer to, **at that point in the text**, using only what has been read so far.
2. **`omniscient_id`**: who the mention actually refers to, using the whole book.

These two are often the same. They differ when the text withholds, disguises or later changes an identity. The comparison between them is the whole point of the pilot, so **do not make them agree out of habit**.

## 2. The cut point (what "so far" means)

The reader has read: every chapter before the mention's chapter, **and** the mention's chapter up to the **end of the sentence that contains the `[[mention]]`**. Nothing after that sentence. The mention's own sentence counts, because a reader reads the whole sentence before moving on (a name given in apposition, such as "his uncle Gu Yue Dong Tu", is therefore known).

If you remember the book or know a spoiler, ignore it for `reader_warranted`. Use the window and the earlier text. When you cannot tell what you would have believed, say `UNDETERMINED` rather than guessing.

## 3. Allowed answers

For both `reader_warranted` and `omniscient_id`:

| Answer | When |
|---|---|
| a candidate **letter** (`A`, `B`, ...) from the `candidates` column | the entity is in the list |
| **free text** (a name) | the entity is real but not in the list |
| `NEW` | a person or thing not yet introduced that the reader cannot name yet |
| `UNDETERMINED` | the reader (or, for omniscient, the book) does not settle it |
| `NOT_AN_ENTITY` | the highlighted words do not refer to an individual (a ritual, an event, a generic noun) |

The candidate list is a shortlist built the same way for every item. It always contains some entities and some decoys, and the correct answer may not be on it. **Never choose a letter just because it is there.**

**Misdirection.** If the text deliberately leads the reader to a cover identity (someone disguised, or the narrator misleading), the reader-warranted answer is the cover identity, and the omniscient answer is the real one. Say so in `notes`.

**Title and relational words** ("the clan head", "his uncle", "junior brother"): the reader-warranted answer is whoever holds the title or relation *at that point as far as the reader has been told*. If the text has not yet said who, answer `NEW` or `UNDETERMINED`.

## 4. The other columns

| Column | What to write |
|---|---|
| `reader_evidence` | the chapter and a short quote (or character offset) that supports your reader answer, or the last place the information was missing |
| `omniscient_evidence` | the chapter and a short quote that settles the true identity |
| `reveal_chapter` | the chapter where a reader first gets enough to know the true identity. **Leave blank if the reader already knew** (both answers agree and nothing was withheld) |
| `confidence_1to3` | 1 = unsure, 2 = fairly sure, 3 = certain |
| `minutes_spent` | honest wall-clock minutes for this item (used to plan the next batch) |
| `notes` | anything odd: wrong highlight, misdirection, you used an outside spoiler, etc. |
| `annotator` | your name, on **every** row you label |
| `provenance` | the word `HUMAN` on every row you label |

Leave items you cannot judge **blank** and say why in `notes`. Do not fill a row with a placeholder.

## 5. Order and pacing

The sheet is ordered with the **pre-reveal candidates first**: batch 1 (items CP-001 to CP-024) is almost entirely those. If time runs short, finish batch 1 before the rest, because those are the items the pilot most needs. Batches 2 and 3 are mixed. Estimate: 5-10 minutes per item; 72 items is roughly 6-12 hours. Fewer than 72 is fine; the first 24 matter most.

Do not use any model, search a summary, or look at a machine's answer. The sheet carries no machine suggestion; the separate key file stays untouched.

## 6. Worked examples from the repo's own cases

These are illustrations of the rules, **not answers for the sheet**:

- *Reveal at the mention.* "It was actually his older brother Fang Yuan who had grasped his collar" (ch 6). Before this sentence the reader does not know who pulled him up. At the end of this sentence the mention "Fang Yuan" refers to Fang Yuan (both answers agree, reveal chapter = 6 if you are labelling an earlier unnamed reference).
- *Manufactured doubt.* "Who told you I was Gu Yue Fang Yuan?" (ch 32). The speaker tries to make the listener doubt his identity. For `reader_warranted`, decide what a reader who has followed the story believes; for `omniscient_id`, the true person. If the text leaves the reader unsure, `UNDETERMINED`.
- *Not an entity.* "the Awakening Ceremony" is an event, so `NOT_AN_ENTITY`.

## 7. What the pilot can and cannot say

It reports how many of the 72 items have `reader_warranted` different from `omniscient_id`, with Wilson intervals, and gives the first honest count of pre-reveal items in the book. It cannot give an agreement statistic, cannot represent the whole novel (the items are chosen, not sampled), and cannot support any claim about other novels. It is evidence for the novelty report's "what could be measured and how big the effect set is", not a benchmark.

## 8. Reference

The reader and omniscient views follow the idea in KoCoNovel (Kim, Lee, Lee, arXiv 2404.01140): in the Reader version, entities that the text keeps separate until a reveal stay separate; in the Omniscient version they are merged (the paper's Table 3: "Taehoon", "Kyungsuk" and "Ms. B" are separate for the reader and one entity for the omniscient author) [PUB, read]. I read the paper's introduction and Table 3; I did not read its full annotation guidelines section, so this guide is **not** a reproduction of their protocol.

---

<!-- merged-from: docs/research/CHIMERA_COMPONENT_MATRIX.md -->
## Source: `docs/research/CHIMERA_COMPONENT_MATRIX.md`

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

---

<!-- merged-from: docs/research/CHIMERA_DATA_AND_BENCHMARK_PLAN.md -->
## Source: `docs/research/CHIMERA_DATA_AND_BENCHMARK_PLAN.md`

# CHIMERA data and benchmark plan (Checkpoint 1, Gate 3)

| Field | Value |
|---|---|
| Commit | `6c7e2c2` (branch `validation/evidence-pass-2026-09-24`), 2026-10-15 |
| Read | GenWebNovel paper PDF (all 9 pages), README, `DATA_USE_AGREEMENT.md`, `scripts/reconstruct_from_qidian.py` (all full text); KoCoNovel arXiv 2404.01140 (text); repo gold files and `data/eval/hardcase_taxonomy.json`; `docs/results/{GOLD_DATASET_README,EXTERNAL_BENCHMARK,FINAL_EVIDENCE_TABLE}.md` |
| Ran | Read-only grep/count on `data/gold/*.jsonl`; read-only SQLite counts on a scratch copy of the RI database. **Nothing from GenWebNovel was executed. D3 not granted.** |
| Not opened | BookCoref, FantasyCoref, GuoFeng, Qidian-Webnovel, WebNovelBench, LitBank corpus itself (rows below say so) |
| Evidence tags used | see directive section 0 |

Scope: this file inventories data and says what each set can and cannot support. No dataset is universal ground truth. Nothing here is a result.

---

## 1. Findings that change the plan

1. **No human-verified gold exists for any EchoTales novel.** [INSPECT] `grep -c '"confirmed": *true'` returns 0 for all six `data/gold/*.jsonl` files and `"provenance": "human"` returns 0. In `reverend-insanity.jsonl` (7,879 records), 3,457 records carry a `confirmed_by` name but `confirmed` is false, so the code correctly refuses to count them. The only human-keyed number in the repo is LitBank (15.9 full person key / 42.4 proper names only [REPO: `EXTERNAL_BENCHMARK.md:36,38`]).
2. **The hard-case count is 58 undetected of 88, not 59 of 89.** [INSPECT] `data/eval/hardcase_taxonomy.json` sums to 58 (annotation-control 1, gold-span-defect 2, pronoun 10, relational 15, address-term 16, definite-title 11, possessive-np 1, rigid-name 2). It includes one not-entity control and two gold-span defects, so at most 55 are real detection losses. All 89 hard-case records are model drafts (`confirmed_true=0`).
3. **GenWebNovel is Chinese-language text. EchoTales' mention layer targets English translations.** [INSPECT] The pipeline's NER and coref prompts are written for "translated Chinese and Korean web-novel prose" (`mentions/ner.py:151`, `anaphora/coref.py:242`), and I found no Chinese tokenizer or Chinese NER path (grep for `jieba`, `zh_core`, `spacy.load`: no hits). So "EchoTales' current mention layer" cannot be a like-for-like baseline on GenWebNovel without building a Chinese path. Any such path is new work, not a measurement of the current system.
4. **GenWebNovel's PER schema annotates generic descriptors, which EchoTales forbids.** [PUB: paper section 3.2.1, Table 2] PER includes common nouns for relationships ("the Senior Brother"), descriptive noun phrases ("a woman wearing a green dress") and nested names. EchoTales non-negotiable 4 says generic descriptors never enter the graph. The public release labels are only `PER/LOC/ORG` with no named-vs-nominal flag [INSPECT: README annotation format], so a "names only" slice would need a heuristic filter and would be an approximation.
5. **Scratch-copy caveat.** The 9 failures I first saw in `test_adjudication_package.py` were caused by gitignored inputs missing from `git archive`, not by a defect. With those inputs copied in, the two untracked test files pass (25/25). [INSPECT]

---

## 2. GenWebNovel protocol (steps in the directive's order, stopping at the first blocker)

| Step | Result | Tag |
|---|---|---|
| 1. Read paper, README, DUA, script in full | Done. Facts below. | [PUB]/[INSPECT] |
| 1. Check Qidian terms | **INACCESSIBLE.** `https://www.qidian.com/about/terms` and `/robots.txt` both returned empty content through the fetch tool. No workaround attempted. Terms of use are therefore unverified. | INACCESSIBLE |
| 1. Reconstruction permitted? | The DUA places responsibility for source-site terms on the user and bars redistribution of reconstructed text. It does not itself grant permission to scrape. Because Qidian's terms could not be read, permission is **UNVERIFIED**. | [INSPECT] + UNVERIFIED |
| 1. Practical from here? | Not tested. Script needs `bs4`+`lxml`, issues unauthenticated GETs to `m.qidian.com` with an iPhone user-agent string at 0.2 s delay. The DUA says no login/cookies/paid chapters/CAPTCHA/proxy/anti-bot support. If Qidian serves a challenge page, the script fails and the stated rule is to stop. **Do not run until D3.** | [INSPECT] |
| 2. Split | **Not shipped.** The paper states a novel-level 8:1:1 split (32 train / 4 dev / 4 test novels) following Bamman et al. 2019 and gives sentence/entity counts (Table 3: train 19,762 sentences, dev 2,222, test 1,822; test PER 3,142, LOC 626, ORG 286). It does not name which novels are in each fold. The README lists no splits. [PUB]/[INSPECT] The split cannot be reproduced exactly. Only the 4 test novels named in Figure 6 are known (Perfect World, Jiang Ye, Qing Yu Nian, Zhui Xu); the other 36 are not identified. **Action: ask the authors (corresponding author listed in the paper header). Do not invent a split.** | [PUB] |
| 3. MetaRetrieval code/checkpoint | The abstract says "code, dataset, and model are available" at the repo. The README layout and the repo tree (tree via a summarising fetch [LEAD]) contain only `qidian_annotations.jsonl`, `reconstruct_from_qidian.py`, `validate_public_release.py`, `requirements.txt`, the DUA and README. **No model, retrieval code or checkpoint was found.** Any implementation by us is a labelled approximation of "MetaRetrieval-Llama", never a reproduction. | [INSPECT] README; tree [LEAD] |
| 4. Matched baselines | Plan below. | plan only |
| 5. Blocker rule | Two blockers exist already: (a) no split, (b) Qidian terms unreadable. **Status: BLOCKED pending D3 and an author reply on the split.** | |

Other verified GenWebNovel facts [PUB]: COLING 2025, pp. 3836-3849; 400 chapters, 40 Qidian novels (XuanHuan and History, first 10 chapters each), 1,214,283 tokens; annotated by five web-novel readers in Label Studio over three months; average Cohen's kappa 0.8332; PER 39,862 entities (Figure 2), nested outer 1,250 / inner 549; the README says about 49K entities. Reported F1 (Table 4): MetaRetrieval-Llama 73.74, DiffusionNER 72.10, Llama 3-shot 62.64, Baichuan 3-shot 60.89, ChatGPT 0-shot 21.90. Cross-genre transfer (Table 6): 50.19 and 52.24 off-diagonal. All of this matches the directive's figures.

Two observations on the release script [INSPECT]: (1) any single entity checksum mismatch raises and drops the **whole chapter**, so yield under page drift could be much lower than 400 chapters; (2) it normalises punctuation to Chinese forms before hashing, so a changed page layout will silently fail hashing rather than partly match.

**Planned matched baselines (not run).** Where each would run:
- Fine-tuned encoder NER (DiffusionNER-style) on the 32 training novels: needs GPU, so **not** on this host; a Gate 4 item requiring D4 approval. DiffusionNER code availability: not checked.
- Instruction-tuned LLM with the paper's prompt and retrieved examples: needs local inference or paid API (D4).
- EchoTales mention layer: requires a Chinese path first (finding 3); cannot be a baseline as-is.
- Metrics: span-level exact-match P/R/F1 with nested spans scored as separate spans, per genre and per type, plus the paper's overall micro-F1 for comparison. A GenWebNovel result supports mention-recognition claims only.

---

## 3. Dataset and annotation-set inventory

"LLM memorisation" risk applies to any popular published or widely mirrored text.

| Dataset | Task / schema | Language, genre | Size | Licence and access | Splits / scripts | Contamination | Can evaluate | Cannot support | Status |
|---|---|---|---|---|---|---|---|---|---|
| **RI gold** `data/gold/reverend-insanity.jsonl` | Mention-to-entity, silver | English translation of a Chinese novel | 7,879 records (3,457 `confirmed_by` set, 0 confirmed) | Local; derived from a copyrighted EPUB, never committed [REPO CLAUDE.md] | none; `echotales eval` | High: model-drafted, 4,422 circular (drafted by the system's own builder) | Regression tracking of the pipeline against itself | Any accuracy claim | [INSPECT] |
| **LOTM gold** | same | English translation | 6,756 (0 confirmed) | Local, copyrighted source | none | High, circular | same | same | [INSPECT] |
| **ORV gold** | same | English translation, Korean origin | 4,836 (0 confirmed) | Local | none | High, circular | same | same | [INSPECT] |
| **Hard cases** `reverend-insanity-hardcases.jsonl` | Hard mention subset | same | 89 records; taxonomy covers 88 with 58 undetected | Local | `hardcase_taxonomy.py` | Model drafts | Detection-loss analysis (silver) | Resolution accuracy; includes 1 control and 2 span defects | [INSPECT] |
| **288-mention adjudication package** `data/eval/adjudication/`, `human_review_*.csv` | Review sheets pre-labelled by `gpt-5.6-luna` | RI | 200 + 88 sheets | Local, gitignored CSVs | `validate_adjudication_package.py` (tests pass 25/25 in scratch) | Labels are model output; per `ANNOTATION_RESULTS_REPORT.md` and the provisional metrics file, `human_adjudicated` is false [REPO; spot-check recommended] | Becomes human gold only after a person adjudicates | Anything until adjudicated | [INSPECT] sheets exist; adjudication is the owner's job |
| **LitBank** (Bamman et al. 2019) | Entities, coref, events, 100 English literary works | English, public-domain literature | ~210K tokens (as cited by KoCoNovel Table 2; paper not read here) | Public | CoNLL-style; repo script `scripts/eval/litbank_eval.py` | Public-domain classics are likely in pretraining | Mention/coref in English literary prose | Web fiction, translation artefacts, reveals | Corpus not opened here; repo result 15.9 / 42.4 [REPO] |
| **GenWebNovel** | Nested PER/LOC/ORG recognition | Chinese web fiction (XuanHuan, History) | 400 ch., 1.21M tokens | Annotation-only release; DUA; reconstruction from Qidian | Novel-level 8:1:1 described, **not shipped**; no eval script | Medium: mainstream novels (the README example is Douluo Dalu II) are likely in pretraining [INFER] | Mention recognition in Chinese | Coref, identity, temporal state, spoiler safety, visual consistency, English text | [PUB] |
| **KoCoNovel** | Character coreference, four versions incl. **Reader** and **Omniscient** views | Korean modern/contemporary stories | 50 works, 178K tokens, 19K mentions, 1.4K entities, 3,578 tokens/doc | Texts public domain from Wikisource [PUB]; dataset licence not checked | splits not checked; code at `github.com/storidient/KoCoNovel` | Low-medium | The only reader-vs-omniscient gold precedent; design reference for any reader-view gold | Long serialised fiction (docs are short), English, web-novel reveals | [PUB] partial read |
| **BookCoref** (ACL 2025) | Book-scale coref, silver train + gold test | English books | per a search snippet: silver 50 books, gold 3 novels [LEAD] | released on GitHub per snippet [LEAD] | not read | High (classic books) | Long-document coref scaling | Alias/reveal semantics | [LEAD] |
| **FantasyCoref** (CRAC 2021) | Coref from omniscient writer's POV | English fantasy; 211 Grimm tales + 3 works [LEAD] | n/k | n/k | not read | High | Omniscient-view coref | Reader-view | [LEAD] |
| **GuoFeng Webnovel** | zh-en aligned web novel translation | zh+en | not verified | Registration-gated, redistribution prohibited (per directive) | not read | n/k | Possible zh-en alias decomposition (C2 angle) subject to licence | Anything until opened | UNVERIFIED, not opened |
| **Qidian-Webnovel corpus** | not verified | Chinese | not verified | not verified | not read | n/k | n/k | n/k | UNVERIFIED, not opened |
| **WebNovelBench** (EACL Findings 2026) | LLM story-generation benchmark over 4,000+ Chinese web novels per directive | Chinese | n/k | n/k | not read | n/k | **Not an entity benchmark; do not use as one** | Entity, coref | LEAD from directive; not opened |
| **TimeChara** | Point-in-time character hallucination, 10,895 instances / 219 time points [LEAD snippet] | English | | | | | Role-play knowledge cutoffs | Alias/identity resolution in novels | [LEAD] |

### Memorisation and leakage notes
- Every EchoTales novel (RI, LOTM, ORV) is popular and widely mirrored. A pretrained model may "know" a reveal. [INFER] This is the risk candidate C1 targets, and it also means every LLM-assisted label (the existing `claude-*` and `gpt-5.6-luna` drafts) can be contaminated by parametric knowledge of the ending.
- The one clean control I read in the literature is name replacement (arXiv 2412.14368; v6 is titled "Beyond Math: Stories as a Testbed for Memorization-Constrained Reasoning in LLMs" and contains "Name Masking" and "Cross-Cultural Name Replacement" settings [PUB: section 5.1 text]). It reports roughly a 10% drop under replacement and concludes this does not fully remove reliance on memorisation. The directive describes this id as a name-replacement paper; the title has changed since, so cite the version.

---

## 4. Minimal baseline reproduction plan (plan only; nothing run)

Order: reproduce on the original protocol first, then adapt.

1. **LitBank, Maverick and BookNLP on LitBank itself** (their home protocol). Purpose: confirm our harness reproduces published numbers before trusting any web-novel delta. Record paper, commit, dataset version, preprocessing, checkpoint, seeds, hardware, runtime, metric definition, reported vs reproduced numbers, deviations. Maverick's licence per a search snippet is CC BY-NC 4.0 [LEAD]; check at its repo. CPU only if the model fits in RAM (15 GB total, about 2 GB free when checked); otherwise ask.
2. **GenWebNovel** only after D3 and an author reply on the split (section 2).
3. Not before 1 and 2 pass: any run on RI/LOTM/ORV.

## 5. Pre-registered falsification tests (designed now, **not run**)

All $0. No test runs without owner approval of its venue. Host: 16 CPUs / 15 GB RAM with about 2 GB free; no GPU runs.

| ID | Question | Items | Baselines | Metric | Rejection rule | Runs where |
|---|---|---|---|---|---|---|
| T1 | Do existing English tools fail on web novels in general? | Human-verified RI chapters (needs adjudication first, D5) | BookNLP, Maverick | CoNLL F1 on easy slice vs published English numbers | Within ~5 F1 of published English numbers on the easy slice: the general claim is false | CPU if models fit, else ask |
| T2 | Does the hard slice have headroom? | Verified hard cases vs easy slice | all baselines | F1 gap | Gap under 15 points for every baseline: no headroom | CPU |
| T3 | Is there parametric leakage of reveals? | Pre-reveal items whose post-reveal identity differs | Local model, closed-book "who is X really" | Recall vs chance over candidate set | Not above chance: **C1 dies** | Owner's GPU via ollama only if asked each time (D4) |
| T4 | Is renaming evidence-preserving? | Items the deterministic resolver decides | pure rename function | Decision agreement before/after rename | Under 98%: renaming destroys evidence; drop it as a control | CPU, deterministic |
| T5 | Is translation a material share of hard alias pairs? | zh-en aligned hard alias pairs | none | share introduced by translation | Under 10%: drop the C2 translation angle | Needs GuoFeng licence check first |
| T6 | Can humans agree on hard labels? | Hard cases in reader and omniscient views, second annotator on 20% | n/a | Cohen's kappa | Under 0.7 in either view: labels unusable for claims | Human time (D5) |

Pre-registration files for each test are to be written as separate new files before any run.

---

<!-- merged-from: docs/research/CHIMERA_DEFECT_BACKLOG.md -->
## Source: `docs/research/CHIMERA_DEFECT_BACKLOG.md`

# CHIMERA defect backlog (Checkpoint 2, W0)

Nothing here is fixed. Fixing is out of scope until the owner decides. Corrections to Checkpoint 1 are in `CHIMERA_ERRATA.md`.

How to read the table. **Verified** means I read the code at the cited lines in this checkpoint ([INSPECT]). **Agent-reported** means a Checkpoint 1 subagent traced it and I have not re-read it; treat it as a lead. **Repro** entries are *static traces*: no command below was run, because A8 (host CPU experiments) was left blank, which means no. Where a repro needs a database it says so. Several would be destructive on a real database (for example `resolve` deletes bindings), so any real repro belongs in a scratch copy.

Severity is for a research or evidence claim, not for a user of the product: **High** = invalidates or changes how an existing number or claim should be read; **Med** = silently wrong behaviour or a counter that misleads; **Low** = documentation or latent.

Already recorded by the repo: marked **recorded**. Everything else is not recorded as open in `HANDOFF.md`, `EVOLUTION.md` or `STATUS.md` as far as my greps found (E7 in the errata).

---

## Confirmed (verified by me)

| ID | Defect | Sev | Where | Minimal repro (static) | Proposed fix | Recorded? |
|---|---|---|---|---|---|---|
| B1 | **`retry_deferred` reports cases "recovered" without writing a link.** It removes the case from the queue and increments `recovered_from_deferral` and `by_method[DEFERRED_RERESOLVED]`; no `_apply_link`, no store write | **High** (any figure built on that counter overstates resolution) | `resolve/runner.py:646-682` | Read the body: the `Decision.LINK` branch contains only `queue.remove`, two counters and `recovered += 1`. A scratch DB resolve followed by `SELECT COUNT(*) FROM resolution_event WHERE method='DEFERRED_RERESOLVED'` should show 0 despite a non-zero report counter (not run) | Either call `_apply_link` for the winning candidate (and append a `resolution_event`) or rename the counters to `dequeued_after_retry` and stop reporting them as recoveries. Add a test that a recovered case changes `mention.target_id` | no |
| B2 | **`echotales resolve --chapters` is accepted and ignored.** Silent no-op | **High** for any "prefix" experiment (blocks disclosure-faithful claims) | parser `cli.py:101`; call `commands.py:728-737` | `echotales --db <scratch.db> resolve --novel X --chapters 1-10`: the call passes no chapter argument, so all chapters resolve (static trace) | Add a `chapters` (or `max_chapter`) parameter to `resolve_novel` and the stage loop, make `cmd_resolve` pass it, and fail loudly when a flag is parsed but unused. Note upstream stages (commonness profile, lexicon induction) are still whole-volume, so a flag alone does not give a causal prefix | no |
| B3 | **`conditioned_on` and `conditioned_panels` still claim conditioning for character sheets** while generation is called with `reference_images=[]`. The earlier fix covered only the `curated` tag | **High** for the observer-conditioned visual claim; Med for the product report | `render/panels.py:2127-2128, 2143, 2165, 2232, 2740-2741, 2850-2855, 2864` | Render any panel with a present character that has a sheet on a scratch DB: `report.conditioned_panels > 0` while the engine request has `reference_images == []` (static trace) | Populate `conditioned_on` from `_panel_request.reference_images` (the thing actually sent), not from the pre-selection `conditioned` list; or delete the field until conditioning is re-wired. Add a panel-level test asserting `conditioned_on` is empty when references are empty (none exists today per Checkpoint 1) | partly (`EVOLUTION.md:6168`, curated only) |
| B4 | **Wiki canon is undated, position-blind and body-blind, and is applied after `state_of`**, outside the digest. The module docstring promises first-appearance dating that does not exist | **High** (later state leaks into earlier panels; one measured instance already recorded) | `persona/wiki_canon.py:26-28`; `persona/canon.py:49-60, 165-209`; applied at `render/panels.py:1398`, `world/context.py:248`, `persona/reference_gen.py:670` | In `canon_for(label, ...)` any wiki-covered character returns the same traits at chapter 1 and chapter 199 (static trace of `base = load_wiki_canon(...)` then `.update(...)`) | Store `{label: {trait: {value, first_chapter}}}` with the chapter at which the wiki section is grounded in the novel (dated by an extraction check, as `appearance_extract` does), filter by position in `canon_for`, and include the wiki file hash in `state_digest`/the cache key | partly (the Fang Yuan regression is recorded in `canon.py`; the general class is not) |
| B5 | **Retraction has no writer.** `retract_alias_bindings` has zero callers, including tests; `store.retract_alias` is called only from that function and from tests; there is no `retract_attribute` or `retract_relation` | Med for product, **High** for any research claim about retractions (the axis cannot be exercised on real data) | `resolve/contradiction.py:277-304`; `core/store.py` | `grep -rn retract_alias_bindings packages` returns only the definition | Decide whether retraction is in scope; if so, wire the contradiction sweep to call it behind a flag and add store methods for attributes and relations | **recorded** (`STATUS.md:227`, `VALIDATION_BASELINE.md:59`) |
| B6 | **`is_address` is never passed**, so address-form relational deictics are never classified as such | Med (explains part of the 25/29 relational-deictic losses; effect size unmeasured) | `mentions/alias_type.py:76, 116` | `grep -rn is_address packages/pipeline/src` finds only the definition, docstring and a recursive call | Pass `is_address` from the dialogue-span path in `mentions/runner.py`, then measure on human-verified hard cases (needs W1 labels) | no |
| B7 | **`reference_images=[]` is hard-coded in production generation** while reference selection still runs and `CharacterRenderSpec.reference_paths` is not part of `plan_digest` | Med now, latent if references are re-wired (cache key would not change when the selected path changes) | `render/panels.py:2740-2741`; `render/contract.py` (digest fields) | Read `PanelImageRequest(...)` at 2738-2742 | Out of scope to re-wire (IP-Adapter removal is a settled project decision); if re-wired, hash selected reference content, not path | partly (`panels.py:2808-2823` comment, `EVOLUTION` 4.47) |
| B8 | **The hard-case evaluation set carries known non-evaluable records**: 1 not-entity control inside n=88, 2 gold-span defects, and the doc layer mixes 59/89 with 58/88 | Med (data hygiene; changes the headline from 58 to at most 55 real losses) | `data/gold/reverend-insanity-hardcases.jsonl`; `data/eval/hardcase_taxonomy.json`; `docs/EVOLUTION.md:7682`; `docs/archive/STORYTRACE_TRANSFER.md:33` | Recompute from the JSON files as in `CHIMERA_ERRATA.md` E3 | Mark controls and span defects in the gold file, report n explicitly, and update the stale doc figures to say 58/88 (overlap alignment), not 59/89 | partly (58/88 in `FINAL_EVIDENCE_TABLE.md`) |
| B9 | **3,457 RI gold records carry `confirmed_by` but `confirmed: false`** | Med (the code correctly refuses to count them; a reader of the file may not) | `data/gold/reverend-insanity.jsonl`; `eval/gold.py:178-198` | `grep -c '"confirmed_by": *"[^"]'` vs `grep -c '"confirmed": *true'` | Either complete per-record confirmation or clear `confirmed_by` so the field does not suggest review | **recorded** (`GOLD_DATASET_README.md`, bulk approval note) |
| B10 | **`Mention.offset` is sometimes one character early inside a block**, so `block start + offset` does not index `Chapter.story_text` (the translation `_block_starts` is correct; the stored offset is not). Measured by execution 2026-10-15: 6 of 44 chapter-1 mentions, and 9 of 35 system-derived mentions sampled for the pilot sheet were one character early (e.g. "the clan head" at block 78 offset 84, block 68 offset 219) | Med (every offset-keyed join against gold or text silently misses these; the scorer's overlap alignment hides it) | `mentions/runner.py` (offset = span start + hit start); `eval/coref_score.py::_block_starts` | In a scratch DB: for every mention compare `story_text[starts[block_index]+offset : +len(text)]` with `text`; count mismatches | Find where `Span.start` and the gazetteer/NER hit offset disagree by one (a stripped leading character is the likely cause; unverified), store chapter-absolute offsets, add an invariant test that `story_text` at the stored offset equals the mention text | no |
| B11 | **The RI lexicon named in `data/sources.toml` does not exist locally**, so `load_or_seed` silently falls back to the generic `_seed.toml` for the whole resolve stage | Med (any claim about the "induced lexicon" or per-novel declarations rests on a file the run of record may not have used; unclear whether the file is gitignored and simply absent here) | `data/sources.toml:17`; `mentions/induce.py::load_or_seed` | `ls data/lexicons/reverend-insanity.toml` -> missing; `load_or_seed` falls through to the seed | Make `load_or_seed` warn loudly (or fail under a flag) when a configured lexicon path is missing; record in `EVOLUTION` which lexicon the canonical run used | no |
| B12 (observation) | **The repo's name normaliser is character-level and spacing/case/plural-insensitive** (`normalize_romanization` strips all spaces; `strip_morphology` folds a trailing "s"), so real surface variants ("Bai Ning Bing" / "Bai Ningbing", "MoonlightGu", "JIao San", "Iceblade Gu") share a comparison key but not a token sequence | Informational; it constrains any renaming or masking control | `ingest/normalize.py:123-215` | Run the T4 commutation gate (`scripts/chimera/t4_renaming.py`): 335 surfaces, a token-level renaming fails G1/G2 (8/25 under v2, 2/9 under v3) | Not a defect to fix. It means a leakage-control renaming must be **letterwise** (a type-preserving substitution cipher fixing "s", "u", "i"), not token-wise | no |

---

## Agent-reported (Checkpoint 1; not re-read by me in this checkpoint)

| ID | Defect | Sev | Where (as reported) | Fix idea |
|---|---|---|---|---|
| A1 | `appearance_of` filters only `interval.from_lb > position`, ignoring observer, `learned_at_pos`, timeline, retraction; it is the real attribute source for panels, so `state_of` only chooses the persona id | High | `persona/reference_gen.py:208` | Route attribute reads through `state_of` or `resolve_admissible_attributes` |
| A2 | `story_context` / `_facts_as_of` filter on disclosure chapter only; no observer, no story time; brief built for READER even under `--observer` | Med-High | `world/context.py:124-149, 160-218` | Pass the resolver and observer in; compile through `state_of` |
| A3 | `reference_path_for` and reference sheets ignore position and observer; sheets are generated from whole-novel `appearance_of` plus wiki canon | Med | `persona/reference_gen.py:657-665, 788-801` | Position-scoped sheets (the unwired `emit_scoped_reference` exists) |
| A4 | Audio and video use no narrative state; `voice` has no `--observer`; panel and voice manifests can silently mismatch | Med | `voice/runner.py:199-207`; `render/runner.py:82-200` | Share one state-policy object; record the observer in each manifest and check it at join |
| A5 | Panel prompt cache key is DB mtime + size + beat text; ignores observer, director model, template | Med | `render/panels.py:~2347, 1695-1703` | Key on the state digest and a template/model version |
| A6 | Whole-novel trait profiles are written to every body epoch with `learned_at_pos = first_attested_pos`; `write_epochs` stamps `learned_at` from story position | Med-High | `persona/build.py:~270-290`; `persona/split.py:~855-866` | Stamp `learned_at` from the disclosure position of the supporting evidence |
| A7 | `link_title_holders` forces tenure start to chapter 1 and links earlier title mentions backward; `merge_transmigrations` rewrites mention targets across all chapters | Design (volume-first by design); High for any causal claim | `resolve/title_holders.py:287, 301`; `resolve/transmigration.py:104-114` | Gate behind a `--causal` mode that disables both |
| A8 | `adjudicate_remaining` unreachable from CLI and discards its outcome | Low-Med | `resolve/runner.py:684-714`; `commands.py:728-737` | Wire or remove |
| A9 | `AMBIGUITY_BLOCKLIST` drops seeded relational deictics that are exactly "master", "elder", "uncle"; the 23-entry title list and the commonness filter (determiner-rate threshold 0.08) may drop others | Med (effect unmeasured) | `mentions/gazetteer.py:37-62, 129-130`; `mentions/alias_type.py:49-56`; `mentions/commonness.py:102-120` | Measure on human-verified hard cases before changing |
| A10 | `temporal_certainty`, `concurrent_personas`, `scene_scope`, `known_scopes` and `speaker` are never populated, so the temporal BLOCK and speech-partner features never fire | Med | `resolve/evidence.py:380-384`; `resolve/runner.py:449, 907` | Populate or remove from the feature set (the scorer already has three constant features per `SCORER_DIAGNOSIS.md`) |
| A11 | NER roster passed to the model is alphabetically truncated to 120 names; NER cache key omits the roster | Low-Med | `mentions/ner.py:249`; `mentions/chapter_ner.py:~170` | Truncate by frequency or recency; include a roster hash in the key |
| A12 | Window bucket index inconsistent (`int(head.chapter // window_size)` vs enumeration `i // window_size`) | Low | `resolve/runner.py:622` vs `:920` | Use one bucketing rule |
| A13 | `Mention.segment_id` always `segments[0]`; `Mention.position` truncates fractional chapters | Low-Med | `mentions/runner.py:350-351`; `core/models.py:396-398` | Carry the real segment and a fractional position |
| A14 | Dead or unused: `coref.resolve_span_pronouns`, `world/extract.py::extract_world` | Low | `anaphora/coref.py:337`; `world/extract.py` | Remove or document as research-only |

---

## Not code defects, but owner decisions that interact with the backlog

- **Public exposure (A2 in the directive).** The repo and the branch `validation/evidence-pass-2026-09-24` are public and carry `packages/ecrdt/IPR_REVIEW*.md`, `docs/archive/STORYTRACE_TRANSFER.md` and gold JSONL with source excerpts (mean 74.8 characters). Information only; no action taken (see `CHIMERA_ERRATA.md` E1 for the corrected size).
- **Local-only label sheets.** Two `.gitignore` patterns were added at the owner's request for the pilot and blind adjudication sheets. The W1 sheets will also carry excerpts and must be ignored the same way (W1 step 5 will verify).

## Suggested order if the owner wants fixes (INFER)

B1 and B3 first (counters that mislead, one line each of risk), then B2 (silent no-op), then B4 (dated canon plus digest), then A1/A2 (route reads through `state_of`). Each fix changes how existing numbers read, so regenerate the affected artifacts and note it in `EVOLUTION.md`.

---

<!-- merged-from: docs/research/CHIMERA_ERRATA.md -->
## Source: `docs/research/CHIMERA_ERRATA.md`

# CHIMERA errata (Checkpoint 2, W0)

Append-only. Each entry quotes the Checkpoint 1 text, gives the correction, and says how I know. The five Checkpoint 1 files (`CHIMERA_REPOSITORY_AUDIT.md`, `CHIMERA_PRIOR_ART.md`, `CHIMERA_COMPONENT_MATRIX.md`, `CHIMERA_DATA_AND_BENCHMARK_PLAN.md`, `CHIMERA_NOVELTY_GATE.md`) are **not edited**; where they conflict with this file, this file wins from 2026-10-15.

## Re-baseline (W0 step 1)

| Item | Value | Tag |
|---|---|---|
| HEAD / branch | `6c7e2c2` / `validation/evidence-pass-2026-09-24` | [INSPECT] |
| `.git/index.lock` | absent | [INSPECT] |
| Tracked modifications | **1: `.gitignore`**, modified after Checkpoint 1 **at the owner's request** (two ignore patterns for the pilot and blind adjudication sheets that carry `source_text`). Checkpoint 1 itself left no tracked change | [INSPECT] |
| Untracked paths | 27 `??` entries: the owner's 22 remaining original paths + the 5 CHIMERA files. The original 23 became 22 because `data/eval/pilot_review_10.csv` is now ignored | [INSPECT] |
| Commits since Checkpoint 1 | none (a commit and a push were attempted at the owner's request and refused by the permission classifier; nothing ran) | [INSPECT] |
| Authorisation block A1-A8 | left unfilled in the Checkpoint 2 directive, which says blank means NO. So: no branch, no local inference, no paid API, no GenWebNovel, no host CPU experiments. Read-only tracing and `--collect-only` were treated as outside A8 | owner's directive |

---

## E1. Size of the public text excerpts

Checkpoint 1 audit, section 1 ("What the public branch exposes"): "each record has a `context` field of about 130 characters of source-novel text, so roughly 20k short excerpts of copyrighted novels are public". Data plan finding is consistent with it.

**Correction.** About 130 was the maximum I sampled from one file, not the typical length. Measured on `data/gold/reverend-insanity.jsonl` (7,879 records): `context` length mean **74.8**, median **35**, max **145** characters. The hard-case file's first record was 129. The total record count across the six public gold JSONL files (about 20k) stands, but "about 130 characters each" should read "mean about 75, up to about 145". The owner's figure of about 75 is right. The exposure finding itself is unchanged. [INSPECT]

## E2. "1,277 vs 1,252 test count unexplained"

Checkpoint 1 audit, section 1: "The docs claim 1,277 tests; I collected 1,252 in the same two suites. The 25-test difference is unexplained", and defect-list rank 10.

**Correction: explained, not a discrepancy.** I collected tests at the commit where CLAUDE.md dates the figure, `e34a628` (2026-10-02), in a scratch checkout: core + pipeline **1,206**, research **16**, ecrdt **55**, total **1,277**. The docs' figure counts four suites; I compared it against two. Today: core + pipeline 1,252 (the 46 more are the owner's tests added since, including the 25 in the two new untracked files), research 29, ecrdt 55 (unchanged), so 1,336 across four suites. Remove defect rank 10's first clause. [INSPECT, `--collect-only`]

## E3. "58 of 88, not 59 of 89"

Checkpoint 1 data plan finding 2: "The hard-case count is 58 undetected of 88, not 59 of 89", and the audit's "at most 55 are real".

**Correction: both numbers are real, from different runs, and the "89" was never the evaluated denominator.**
- The evaluation script reads the gold file through `read_gold(...).silver_only.entities_only` (`scripts/eval/hardcase_resolution.py:~68`, `eval/gold.py:314-315`). `entities_only` drops records whose kind is not an entity. The gold file has 89 records; exactly one (`3.0/7926 "the Awakening Ceremony"`, kind `not_an_entity`) is dropped, so **n = 88** in every version of the output. [INSPECT]
- The "59" is from the **first, non-canonical** run: `git show 6facc1e:data/eval/hardcase_resolution.json` gives overlap alignment not-detected **59**, correct **23**, n **88**. After canonical promotion (`7c0432f`) it is not-detected **58**, correct **24**, n **88**. [INSPECT]
- `docs/EVOLUTION.md:7682` ("59 of 89") and `docs/archive/STORYTRACE_TRANSFER.md:33` therefore mix the stale count (59) with the gold-file size (89). The current artifacts (`FINAL_EVIDENCE_TABLE.md`, `PAPER_CLAIM_BOUNDARIES.md`, `STATUS.md`) say 58/88.
- Exact alignment (not overlap) gives 67 not-detected (canonical). Which alignment a doc cites matters and none of the "58" statements say "overlap alignment" except `FINAL_EVIDENCE_TABLE.md:46`.
- **"At most 55 are real" holds only under the repo's own taxonomy labels.** `hardcase_taxonomy.json` (58 records) labels one `annotation-control` (`105/3604 "the Spring Autumn Cicada"`, kind `item`, category `not_entity_control`) and two `gold-span-defect` (`54/10645 "his identity"`, `86/6554 "he turned out to be C grade"`, both category `reveal`). 58 - 1 - 2 = 55. I did not independently judge whether those two spans are defects; the label is the script's. [INSPECT counts; label unverified]
- Note the control that remains in n=88 is the item-kind one; the dropped one is the entity-kind-excluded one, so "1 control inside the 58" is correct.

## E4. Retraction writer: "I did not exhaustively grep"; "no non-test callers"

Checkpoint 1 audit, component 8: "`retract_alias_bindings` (`contradiction.py:277`) has **no non-test callers (V)**"; defect rank 8 treated this as a finding; the audit closed by saying it did not grep HANDOFF/EVOLUTION for already-recorded items.

**Corrections.**
1. It has **no callers at all, tests included**. My grep over `packages` found only the definition (`resolve/contradiction.py:277`). The only `store.retract_alias(` callers are the line inside that unused function (`contradiction.py:301`) and tests in `core/tests/test_state.py`. "No non-test callers" understated it. [INSPECT]
2. It is **already recorded**: `docs/status/STATUS.md:227` ("`retract_alias_bindings` has zero callers; `retracted_chapter IS NOT NULL` returns 0 rows in every database") and `docs/archive/VALIDATION_BASELINE.md:59` ("Retraction **writer** | **MISSING** ... 0 rows across all 27 DBs"). It is not new. [INSPECT]

## E5. `conditioned_on` overstating conditioning

Checkpoint 1 audit, section 5 and defect rank 3: reference-selection code runs but its result is discarded, yet "`conditioned_on` metadata and `report.conditioned_panels` are still populated"; the headline "reference-conditioned 5/5" "counts a manifest tag".

**Qualification (the owner's re-check was right that it is partly fixed).**
- A comment at `render/panels.py:2808-2823` ("Section 4.4: `conditioned_on` must not claim conditioning that never happens") records a fix for the **curated** tag specifically. `EVOLUTION.md:6168` also discusses the field. [INSPECT]
- What remains: character-sheet labels are still appended to `conditioned` at `panels.py:2127-2128` (after the curated override at 2118-2123, so both sheet kinds are appended), at `2232`, and carried forward at `2143` and `2165`. `conditioned` is cleared only in the crowd/no-prompt branch (`2656-2657`) and for chunk-mob panels that are not close-ups (`2793-2794`). Then `engine.generate(_panel_request)` is called with `reference_images=[]` (`2740-2741`, `2850`), `report.conditioned_panels` increments whenever `conditioned` is non-empty (`2854-2855`), and `PanelImage.conditioned_on=conditioned` is stored (`2864`). [INSPECT: read each site]
- **Verdict:** confirmed for normal panels. The pre-existing partial fix does not cover character sheets.
- **Still INFERRED:** that the "reader 5/5, non-reader 0/5" figure in `OBSERVER_CONTRAST_VALIDATION.md` is a manifest-tag count. I did not open that run's manifest. The code path makes it likely; it is not demonstrated.

## E6. Items the owner marked qualified that I now resolve

| Claim in Checkpoint 1 | Verdict | Evidence |
|---|---|---|
| `retry_deferred` counts "recovered" without writing a link | **Confirmed.** On `Decision.LINK` it calls `queue.remove`, increments `recovered_from_deferral` and `by_method[DEFERRED_RERESOLVED]`, and returns; no `_apply_link`, no store write (`resolve/runner.py:646-682`, body read in full) | [INSPECT] |
| `cmd_resolve` does not read `--chapters` | **Confirmed.** The parser accepts it (`cli.py:101`); `cmd_resolve` builds its `resolve_novel(...)` call from `args.novel`, `lexicon`, `strict_kind_check`, `force_rewipe`, `capture_evidence`, `evidence_run_tag` only (`commands.py:728-737`). `args.chapters` is read at `commands.py:112, 686, 756, 957, 1005`, none of them in the resolve call. (`--chapters` on `voice`, `render` and `appearance` is consumed.) Static trace; not executed | [INSPECT] |
| `is_address` never passed | **Confirmed.** Only the definition, its docstring and a recursive call inside `classify_alias_type` reference it | [INSPECT] |
| Wiki canon undated | **Confirmed.** `persona/wiki_canon.py:26-28` promises first-appearance dating; the saved structure is `{label: {trait: value}}` with no chapter or position, and `persona/canon.py:49-60` records a measured regression from it | [INSPECT] |

## E7. Defects 3 and 6 "may not be recorded"

Audit section 8 said: "I did not exhaustively grep `docs/HANDOFF.md` or `EVOLUTION.md`, so I cannot say whether defects 3 and 6 are already recorded".

**Now checked.** `retry_deferred` appears in `docs/EVOLUTION.md:7006` only in a note about threading arguments, not as a no-write defect; `recovered_from_deferral` appears in no doc I grepped (HANDOFF, EVOLUTION, STATUS). `conditioned_on` is discussed in `EVOLUTION.md:4387, 6168` (the curated fix) but not as the remaining character-sheet overstatement. So defect 6 (`retry_deferred`) and the remainder of defect 3 are **not recorded as open**. [INSPECT, grep]

## E8. Not errors, but statements that need a qualifier

- Audit section 4.1 says no test asserts prefix invariance, citing an agent's grep. Still **agent-reported**; I did not re-grep every test file.
- Audit section 4.2 says there are no 30-50 chapter LLM windows. Re-confirmed in code only for `window_size = 40`'s uses as reported; the stale gazetteer docstring at `mentions/gazetteer.py:3-4` is what the directive's phrase came from. Still agent-reported for line numbers beyond those I opened.
- Prior-art row 1.2 says NWM's public corpus is "12 books per the directive; I did not re-count". Unchanged.

## Not corrected (checked, stands)

- 0 confirmed gold records in all six gold files; 3,457 RI records with `confirmed_by` set but `confirmed: false`. [INSPECT again this session]
- `reference_images=[]` at `panels.py:2740-2741`. [INSPECT]
- RI database: 0 retracted rows, 0 relation rows, 12 observation rows. [INSPECT, scratch copy without the `-wal`]

---

<!-- merged-from: docs/research/CHIMERA_NOVELTY_GATE.md -->
## Source: `docs/research/CHIMERA_NOVELTY_GATE.md`

# CHIMERA novelty gate (Checkpoint 1, Gate 4 preparation)

| Field | Value |
|---|---|
| Commit | `6c7e2c2`, 2026-10-15 |
| Inputs | `CHIMERA_REPOSITORY_AUDIT.md`, `CHIMERA_PRIOR_ART.md`, `CHIMERA_COMPONENT_MATRIX.md`, `CHIMERA_DATA_AND_BENCHMARK_PLAN.md`; the existing ledger `ECHOTALES_NOVELTY_LEDGER.md` (not contradicted, only extended) |
| Ran | Nothing new. No experiment, no model, no paid call |
| Verdict | **No candidate passes the gate today.** None is killed either. Reason in section 1 |

## 0. The gate

A candidate passes only if all six hold: (1) the closest work lacks the substantive mechanism; (2) it is more than connecting components; (3) it addresses a meaningful failure; (4) a strong baseline is implementable; (5) a plausible result could falsify it; (6) it fits the repo, data and budget. "Passes" means the evidence needed to *start* building exists. It does not mean the idea is novel in the field.

## 1. Why nothing passes yet (the shared blocker)

- **There is no human-verified label for any EchoTales item.** 0 confirmed records across all six gold files; the 288-item package is model pre-labelled and unadjudicated. [INSPECT, see data plan] So criterion 5 (falsifiability on real data) cannot currently be met for C1, C2 or C3; the tests that would meet it (T1-T6) are designed and not run.
- The closest published systems (NWM, NarraWorld) already implement chapter-safe or admissible-view reads, observer/belief views and provenance, so the architecture alone is not a contribution. [PUB, prior-art rows 1.2, 1.3]
- The real data cannot exercise the interesting axes: the RI database has 0 retracted rows, 0 relations, and 12 observation rows. [INSPECT]

## 2. Re-ranking (my ranking; it differs from the seed order)

| Rank | Candidate | Why this position | Gate status |
|---|---|---|---|
| 1 | **C5** floor: systems/findings paper with negative results | Evidence already exists in the repo and is partly strengthened by this audit (e.g. no human gold, silver-only numbers, scorer links nothing, `retry_deferred` counts, reference conditioning off). Needs no new labels to be honest | Always alive (floor) |
| 2 | **C3** title-aware detection (engineering) | Diagnosed causes in code; $0 CPU; measurable target. But it is **not** a contribution on identity, and its evaluation needs human-verified hard cases | Not a novelty candidate; a workstream. Blocked on labels; GenWebNovel is Chinese text and cannot test the English mention layer |
| 3 | **C1** disclosure-faithful identity under parametric leakage | The only candidate with a cheap, decisive kill test (T3) and a meaningful failure. Prior art overlaps on each ingredient (renaming control 2412.14368; admissible views NarraWorld/NWM; reader vs omniscient KoCoNovel). The combination on identity over long serials is not shown covered, **but I only did partial reads** | Pending T3, T4, T6; needs reader-view labels |
| 4 | **C2** long-span identity benchmark | KoCoNovel precedes the reader/omniscient design, though its documents are short. The translation-share angle needs GuoFeng, whose licence and contents I did not open. Annotation cost is the real constraint | Pending D5, licence check, T5, T6 |
| 5 | **C4** progression-aware disclosure-safe state for multimodal adaptation | Overlaps NWM and NarraWorld on the state side; the visual-lineage side overlaps CANVAS and an unlocated "VividWorld", neither read. Production has no reference conditioning, so a visual claim has no downstream effect to measure. Real data has no retractions or relations, so a leak class beyond "cutoff filter + short label check" cannot be shown | **Fails today.** Reopen only if a named leak class is found that the cutoff filter cannot catch, shown on real data |

I disagree with the seed order in one place: C3 ranks above C1 as a *workstream* because it is actionable now, but it does not compete as a *paper* candidate.

---

## 3. Candidate sheets

### C1. Disclosure-faithful identity resolution under parametric leakage

| Field | Content |
|---|---|
| Formal task | Given a text prefix of chapters 1..c, a mention m at position <= c and a candidate set of entities, output the entity the **reader at c** is warranted in linking m to, or abstain. Distinguish the reader-warranted label from the final-truth label on items where they differ (hidden identities, title transfers, disguises, body changes) |
| Input / output | Prefix text, mention span, candidates -> link or abstain plus the citing spans |
| Falsifiable novelty sentence | "On identity items where reader-warranted and final-truth labels differ, an LLM-based resolver links prematurely at a rate that exceeds chance because of parametric knowledge of the novel, and an evidence-gated link rule (a link must cite in-prefix spans that entail it, names masked) lowers that rate below what whole-input renaming achieves." Each clause is testable |
| Closest prior art and exact difference | **2412.14368**: renaming as a memorisation control for character reasoning (does not address linking against a reader-warranted label, per the sections I read). **NarraWorld / NWM**: admissible-view and chapter-safe reads (memory-level filtering; no leakage control found by keyword search). **KoCoNovel**: reader vs omniscient labels (short stories, coreference, no leakage measurement). **TimeChara** [LEAD]: point-in-time hallucination in role-play, not identity linking. Exact difference to establish: the premature-resolution metric on long serials, and mechanism vs plain renaming |
| Minimal mechanism | A link is accepted only if a deterministic check finds, inside the prefix, spans that entail it with names masked |
| Strongest simple baseline | Renaming the whole input consistently (pure function) plus the existing deterministic resolver |
| Strongest published baseline | Prefix-only memory systems (NWM-style chapter-safe packet) with an LLM resolver |
| Datasets | RI/LOTM/ORV as local; hard-case slice; KoCoNovel only as a protocol reference |
| Required annotation | Reader-view and omniscient-view labels on the hard cases, two annotators on at least 20% (D5, T6). **Does not exist** |
| Metrics | Premature-resolution rate; leakage = change between original and renamed text; abstention rate; precision and recall on non-hidden items to show no collapse |
| Ablations | Remove masking; remove gating; renaming vs gating vs both |
| Failure modes | Renaming destroys evidence (T4); leakage not above chance (T3); labels cannot reach kappa 0.7 (T6); gating cuts recall excessively |
| Cost | $0 for T4; T3 needs local-model inference approved per run (D4); annotation human time |
| **Rejection criteria (pre-registered)** | T3 recall not above chance -> C1 dies. T4 agreement under 98% -> renaming control invalid, redesign. T6 kappa under 0.7 in either view -> labels unusable. Mechanism not better than renaming in a paired test -> no mechanism contribution |

### C2. Long-span identity benchmark for translated web serials

| Field | Content |
|---|---|
| Formal task | Resolve alias-to-identity links over long reveal distances in English translations, scored under reader and omniscient views |
| Falsifiable novelty sentence | "A benchmark of translated web-serial identity items with reader and omniscient labels and reveal distances above N chapters has at least a 15-point headroom gap between easy and hard slices for existing tools, and at least 10% of hard alias pairs are introduced by translation." |
| Closest prior art | KoCoNovel [PUB]: reader/omniscient versions, 50 short Korean stories. FantasyCoref and BookCoref [LEAD]. GenWebNovel [PUB]: Chinese mention recognition only. Difference to establish: reveal distance, serials, translation decomposition |
| Baselines | BookNLP, Maverick, existing mention layer (T1, T2) |
| Annotation | Large; two annotators on 20%; D5 open |
| Rejection | T2 gap under 15 points; T5 share under 10% (drop the translation angle); T6 kappa under 0.7; GuoFeng not licensed for the decomposition |
| Cost | Mostly human time. Dataset release is also constrained by D2 and copyright (the source texts cannot be redistributed; only offsets and checksums, as GenWebNovel does) |

### C3. Title-aware mention detection (workstream, not a paper claim)

| Field | Content |
|---|---|
| Task | Raise detection of transferable-title and relational-deictic mentions without adding false entities |
| Mechanism | Pass `is_address`; widen or learn the title list; revisit `AMBIGUITY_BLOCKLIST` and the commonness filter for deictics |
| Baseline | Current detector (58 of 88 hard cases undetected on silver; at most 55 real) |
| Evaluation | Recall on **human-verified** hard cases and precision on the *added* mentions; GenWebNovel is not applicable to the English layer without a Chinese path (data plan finding 3) |
| Rejection | Added-mention precision below the precision of the current detector, or no downstream resolution gain |
| Note | Any gain is engineering. It also changes how existing numbers read, so it should be done after human labels exist, or silver numbers will move without meaning |

### C4. Progression-aware, disclosure-safe state reconstruction for multimodal adaptation

| Field | Content |
|---|---|
| Task | Reconstruct state for story position p, disclosure cutoff k, observer o, with retractions and asset lineage, for rendering |
| Prior art | NWM [PUB] (chapter-safe reads, reveal order, observer); NarraWorld [PUB] (admissible views, beliefs, validity intervals, provenance); CANVAS, FilmWorld, "VividWorld" not read or not found |
| Why it fails the gate today | (a) the repo ledger already reduces it to snapshot reads plus an information-flow check; (b) production has `reference_images=[]`, so visual lineage has no effect to measure; (c) the real database has no retractions or relations; (d) no leak class beyond a cutoff filter has been named |
| Reopen condition | A concrete leak that "cutoff filter + short transitive label check" misses, shown on real data. The audit surfaced real, *integration-level* leaks (wiki canon, `appearance_of`, audio, brief) but those are bugs fixed by routing through `state_of`, not a new mechanism |

### C5. Floor: systems/findings paper

| Field | Content |
|---|---|
| Claim set | Only what the repo can support: pipeline description; the finding that gold is model-provenance; the scorer diagnosis; hard cases are lost at detection (with the corrected 58/88 and the control and span-defect caveats); the measured failure of existing baselines on a surface-trivial subset reported as cost and failure shape; the integration defects found in this audit |
| Needs | No new labels to be honest; benefits strongly from the 288-item adjudication |
| Venue | The repo's own analysis (2026-09-25) names WNU 2027, ACL 2027 System Demonstrations and the January 2027 ARR cycle; I did not re-verify those dates. The October 2026 ARR deadline (2026-10-12) has passed (per the directive) |
| Risk | The public repo is already visible (audit section 1). That affects D2 timing, and a reviewer can already see the branch |

---

## 4. Cheap falsification tests (status)

All designed in the data plan; **none run**. T3 and T4 are the highest-value, because they decide C1 at $0 to small cost.

| Test | Decides | Needs before running |
|---|---|---|
| T4 renaming validity | C1 control validity | Nothing but approval to run in a scratch copy (CPU, deterministic) |
| T3 memorisation probe | C1 | D4 (local model, owner's GPU, asked each time) |
| T6 agreement | C1, C2 | D5 and an annotation protocol |
| T1, T2 | C2, C3 headroom | Human-verified chapters; BookNLP/Maverick runs; check their licences |
| T5 | C2 translation angle | GuoFeng licence and contents |

## 5. Recommendation for this gate

**INSUFFICIENT EVIDENCE** to pass any candidate. Not NO-GO, because C1 has a cheap decisive test and C5 is intact; not CONDITIONAL GO, because every candidate that matters needs human labels that do not yet exist and the closest prior art for the state-and-memory side (C4) is already substantial.

---

<!-- merged-from: docs/research/CHIMERA_PLAN.md -->
## Source: `docs/research/CHIMERA_PLAN.md`

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

Build `docs/research/NOVELTY_SUPPORT.md`: one row per candidate technique. Columns: source paper (verified title, authors, venue, date, evidence tag); what it contributes; artifact and licence (code, data, models; can we legally reuse); the EchoTales component it touches; product value; paper value (novelty, ablation baseline, or none); integration form (isolated adapter, config switch, or baseline-only); cost (compute, annotation, engineering days); evidence needed and available; risks (error propagation, leakage, precision loss); **decision: adopt / adapt / baseline-only / reject**; and the test that would justify the decision. No row is accepted on an abstract. Papers read only as snippets stay `[LEAD]` and cannot be adopted until read in full.

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

Keep `docs/research/NOVELTY_SUPPORT.md`: date, purpose, model id, calls, tokens, actual cost, running total. Same protocol as §7: nothing is spent without the owner approving an exact verified estimate; the key is never displayed or copied; the owner's cap for the OpenAI model is about $0.10 to $0.20 per request; the GPU budget is $10 in total and nothing is rented without a separate approved request. Free local inference needs the owner to confirm the model tag and hardware.

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

---

<!-- merged-from: docs/research/CHIMERA_PRIOR_ART.md -->
## Source: `docs/research/CHIMERA_PRIOR_ART.md`

# CHIMERA prior art (Checkpoint 1, Gate 2)

| Field | Value |
|---|---|
| Commit | `6c7e2c2`, 2026-10-15 |
| Read in full or in part ([PUB]) | GenWebNovel (COLING 2025; all 9 pages, README, DUA, script); Narrative World Model arXiv 2607.05577 (PDF text, keyword search of the full text plus abstract, intro, system and limitation passages); NarraWorld arXiv 2609.32401 (PDF text; abstract, section on admissible views, Appendix A on extraction and views); arXiv 2609.35759 (PDF text; abstract and keyword search only); KoCoNovel arXiv 2404.01140 (PDF text; abstract, Tables 2-3, annotation guidelines); arXiv 2412.14368 v6 (PDF text; abstract, section 5.1) |
| Downloaded but **not** read beyond the title | SagaScale arXiv 2601.09723 |
| Seen only as search snippet or summarising fetch ([LEAD]) | TimeChara, BookCoref, Maverick, FantasyCoref, Song & Liu (LREC-COLING 2024), Narrative Weaver (CVPR 2026) |
| Not downloaded (size) | CANVAS arXiv 2604.13452 (18 MB), FilmWorld arXiv 2607.19038 (50 MB) -> [LEAD] at best; need owner approval to fetch |
| Not located | "VividWorld" / "Grounding the Visual Axis of a Narrative World Model" (standard and extended search, nothing found; Gen4AVC not found); Jularr PR #451 (search found nothing) |
| Not searched this checkpoint | ChronoQA/Entity-Event RAG, EvolvTrip, Graphiti/Zep paper itself, TAC-KBP slot filling, FIDES/APPA/SPA, SynthWorlds, LifeState-Bench, Glasserman & Lin, Lookahead Propensity, "Speak, Memory", OWL, Story2Board, ViStoryBench, VideoMemory, StoryDiffusion, IdentityStory, LogiStory, NGP, VinaBench, DOI 10.1111/cgf.70319, Qidian-Webnovel, GuoFeng, WebNovelBench; CCL/JCIP and Korean-venue searches (one mixed-language web search returned no BookNLP-on-Chinese-web-novel paper, which is **not** evidence of absence) |

Coverage is incomplete by design of this checkpoint's budget. Rows below carry only what I actually read. Where a field says "not read", no claim is made.

Rule applied: "X is not covered by paper Y" appears only with the section or passage I read; a keyword search of a PDF's extracted text is stated as such and is weaker than a read.

---

## 1. Works read ([PUB], full or partial)

### 1.1 GenWebNovel (Zhao, Yan, Zhu, Liu, Jia, Zan, Peng; COLING 2025, pp. 3836-3849)
| Field | Content |
|---|---|
| Status | Peer-reviewed main conference |
| Task and assumptions | Nested entity **recognition** (PER/LOC/ORG) in Chinese web novels. PER includes common nouns, descriptive phrases and nested names (section 3.2.1) |
| Data | 400 chapters, 40 Qidian novels (20 XuanHuan, 20 History; first 10 chapters each), 1,214,283 tokens; annotated by five readers over three months; average Cohen's kappa 0.8332 |
| Splits and metrics | Novel-level 8:1:1 (32/4/4) per section 5.2.1; P/R/F1 overall and per type |
| Mechanism | Metadata-augmented BERT pretraining ("Novel-BERT"), FAISS retrieval of similar training sentences as in-context examples, fine-tuned Llama 3.1-8B ("Novel-Llama"), reported as MetaRetrieval-Llama |
| Reported results (authors') | F1: MetaRetrieval-Llama 73.74, DiffusionNER 72.10, Llama 3-shot 62.64, Baichuan 3-shot 60.89, ChatGPT 0-shot 21.90 (Table 4); cross-genre 50.19 / 52.24 (Table 6) |
| Authors' limitations | Only two genres and three entity types (Limitations section). The conclusion lists coreference and relation annotation as future work, so **no coreference is annotated** |
| Limitations found by inspection | Split fold membership not released; no evaluation script; no model code in the repo (README); reconstruction depends on Qidian pages and drops any chapter with one checksum mismatch |
| Artifact | Annotations only, plus a reconstruction script. Reconstructed text must not be redistributed (DUA) |
| Relevance | Evidence for mention recognition on Chinese web fiction only. Not for identity, time, spoilers or visuals |
| Reproduce / adapt / reject | **Blocked** pending D3 and an author reply on the split. If reproduced, MetaRetrieval would be a labelled approximation |
| Overlap with candidates | C3 only (detection). None with C1, C2, C4 |

### 1.2 Narrative World Model (Saifullah et al., PocketFM; arXiv 2607.05577 v1, 6 Jul 2026, "Preprint. Under review")
| Field | Content |
|---|---|
| Status | Preprint, industry authors |
| Task and assumptions | Writer-facing memory for long-form fiction: multi-hop questions about evolving story state (who knows a secret and when, whether an event preceded the narration that revealed it, setup/payoff, relationship deltas) |
| Data | Public corpus from Project Gutenberg (12 books per the directive; I did not re-count), plus a private corpus of five 50-chapter production-style serialised books, de-identified as Books A-E and not redistributable. Multi-hop benchmark: 272 private questions (176 validated multi-hop) |
| Mechanism | Typed temporal-state graph with first-class focalised observer, **reveal order stored separately from event order**, epistemic knowledge/unknowns, promise/payoff, dramatic function; query-conditioned hybrid retrieval returning a **chapter-safe evidence packet** from chapters up to the checkpoint; a held-constant Opus 4.8 reader across systems |
| Reported results (authors') | Private multi-hop 0.574 with paired McNemar 64-7, p < 1e-5; public set 0.625 vs 0.516, n=576, p=0.0001; outperforms Graphiti/Zep, GraphRAG and flat retrieval; advantage survives rebuilding the baseline with NWM's extractor |
| Authors' limitations | Section 8: benchmark is narratology-tilted by design; private corpus not redistributable; backend proprietary and withheld |
| Limitations found by inspection | **Keyword search of the extracted full text found no mention of alias linking, disguise, memorisation, contamination or leakage control.** I did not read sections 3-5 line by line, so this is "not found by search", not "not covered" |
| Artifact | Evaluation harness public; production backend proprietary and withheld |
| Relevance | Closest published match to a chapter-safe, reveal-ordered, observer-scoped memory. Materially overlaps N1/N3/C4 |
| Reproduce / adapt / reject | Adapt as the baseline for any state-memory claim; cannot reproduce the backend |
| Overlap | C4: **high** (chapter-safe read and write, reveal order, observer). C1: partial (disclosure semantics yes; parametric leakage not found). C2: none |

### 1.3 NarraWorld, "Shared Worlds, Private Minds" (arXiv 2609.32401; anonymised review submission)
| Field | Content |
|---|---|
| Status | Preprint under review; code stated as "will be released in anonymized form" |
| Task and assumptions | Structured memory for long-form writing: world facts (W), per-character beliefs (B), open developments (D), hypothetical branches (H) |
| Mechanism (read: main text on admissible views, Appendix A.1-A.3) | Admissible view V_q = projection of the committed memory under the request's temporal, **disclosure** and branch scope; belief views indexed by character; entity mentions grounded against the committed entity index, **aliases linked to existing entities when evidence supports** and a new entity created otherwise; append-only store, state change closes the old validity interval and opens a new record; one provenance chain per record |
| Evaluation | ConStory-Bench, LSGC (14-chapter continuations), RMTBench role-play, LoCoMo; GPT-5-mini for memory calls and GPT-5 for generation. Ablations: removing character beliefs (86.04), possible worlds, developments |
| Limitations found by inspection | Evaluated on generation benchmarks, not on identity resolution or on a reader-vs-omniscient gold. Keyword search found no memorisation or leakage control; not a full read |
| Relevance | Overlaps the bitemporal/observer/provenance architecture of N1/N3/C4 (admissible-view projection, belief holders, append-only validity intervals) |
| Overlap | C4: **high**. C1: partial (premature disclosure is named as a goal in the text). C2: none |

### 1.4 arXiv 2609.35759, "Scaling Long-Form Story Generation via Narrative State Tracking" (NstAgent)
Read: abstract and keyword search only. Training-free agentic framework for long story generation; code at `github.com/zhennan1/NstAgent` (stated in its abstract). Reports a state snapshot dated "pre-cutoff" in an appendix example. **Not read for method details; no claim of overlap or difference beyond "story generation via state tracking, not identity resolution".** Status: [PUB] partial.

### 1.5 KoCoNovel (Kim, Lee, Lee; arXiv 2404.01140; publication venue not verified)
| Field | Content |
|---|---|
| Task and assumptions | Character coreference in Korean novels with **four versions: Reader or Omniscient perspective, crossed with separate or overlapping entities** (abstract, Table 3 and section 4) |
| Data | 50 modern and contemporary novels from public-domain Wikisource, 178K tokens, 19K character mentions, 1.4K entities, mean 3,578 tokens per document; 24% of mentions are single (abstract) |
| Mechanism | Dataset and guidelines; trains BERT-based coreference models |
| Limitations found by inspection | Short stories, not long serials; Korean; whether reader/omniscient labels differ on hidden-identity cases at scale was not measured by me. Agreement scores exist in Table 6 (not read) |
| Relevance | **Direct precedent for any reader-view gold.** Any claim that "reader vs omniscient annotation" is new would be false |
| Overlap | C2: **high** (reader/omniscient views). C1: partial (labels differ by perspective) |

### 1.6 arXiv 2412.14368 (Jiang and Ferraro), v6 retitled "Beyond Math: Stories as a Testbed for Memorization-Constrained Reasoning in LLMs"
Read: abstract and section 5.1. Testbed on character-centric story understanding where verbatim recall is constrained by **replacing character names** (settings include Name Masking and Cross-Cultural Name Replacement); reports about a 10% drop under replacement and concludes memorisation reliance is not fully eliminated. The directive described this id as name-replacement work; the current title differs. Relevant to any renaming control (T4, C1). Overlap with C1: **the strongest renaming prior art found**; any renaming-based leakage control must be differentiated from it.

---

## 2. Works seen only as snippets ([LEAD], to be read)

| Work | What the snippet gave | What still needs reading |
|---|---|---|
| TimeChara (Ahn et al., ACL Findings 2024, arXiv 2405.18027) | Point-in-time character hallucination, 10,895 instances, 219 time points, Narrative-Experts | Whether it controls for parametric knowledge; its time-point labels |
| BookCoref (Martinelli et al., ACL 2025) | Book-scale coref; silver train and 3-book gold test; averages 200K+ tokens per document (snippet, one source is a PhD profile page) | Everything |
| Maverick (Martinelli, Barba, Navigli; ACL 2024) | Efficient coreference system; code released; pip package licence listed CC BY-NC 4.0 by one index | Original-protocol numbers (third-party aggregator listed 83.6 CoNLL-2012 and 78.3 LitBank; **unverified, do not cite**) |
| FantasyCoref (Han et al., CRAC 2021) | Omniscient writer's-view coref on 211 Grimm tales plus 3 fantasy works | Everything |
| Song and Liu (Li Song, Ying Liu; LREC-COLING 2024, "Approaches and Challenges for Resolving Different Representations of Fictional Characters for Chinese Novels") | Frames character resolution as anaphora resolution on one Chinese novel | The directive says it lists hidden-identity plots as unsolved; the abstract snippet does **not** mention hidden identity. Unverified |
| Narrative Weaver (CVPR 2026) | New to this audit; long-range visual consistency via sequential reference-image generation | Everything; possibly relevant to the reference-selection direction |

---

## 3. Not verified or not found

- **VividWorld / "Grounding the Visual Axis of a Narrative World Model: Consistency-Aware Reference Generation for Long-Form Stories"**: not found by two searches (including an extended one). The closest hit was CANVAS (arXiv 2604.13452), which I did not download (18 MB). It remains an unresolved possible competitor to a reveal-aware visual-memory direction. **Needs owner approval to download CANVAS and to look for an OpenReview PDF.**
- **Jularr PR #451**: not found. The repo ledger's claim that it anticipates N4 remains UNVERIFIED by me.
- **FilmWorld (2607.19038)**: 50 MB PDF, not downloaded.
- **BookNLP or a modern coreference system evaluated on translated web novels**: not found in one English/Chinese mixed search. Chinese-language venues (CCL, JCIP) and Korean venues were **not** searched.

---

## 4. What the reading changes about the candidates (INFER)

- **C4 (progression-aware, disclosure-safe state):** NWM and NarraWorld both already implement chapter-safe / admissible-view reads, observer or belief views, reveal order separate from event order (NWM) and append-only validity intervals with provenance (NarraWorld). Both are generation-oriented memory systems, not identity-resolution or visual-reference systems, and neither (by my keyword search) addresses parametric leakage. The residual gap for C4 is narrower than the repo ledger's wording and is the visual-asset lineage side, which I could not check against CANVAS or VividWorld.
- **C1 (disclosure-faithful identity resolution under parametric leakage):** Renaming as a leakage control has prior art (2412.14368); disclosure-scoped admissible views have prior art (NarraWorld, NWM); reader-vs-omniscient labels have prior art (KoCoNovel). C1's open space is the **combination on identity items over long serials, measured against a renaming control**, which requires human labels that do not exist yet.
- **C2 (benchmark):** KoCoNovel precedes it on reader/omniscient views; its documents are short stories, so long reveal distances would be a real differentiator. Not verified beyond that.
- **C3:** GenWebNovel is an annotated mention-recognition corpus and is cleanly in scope, but only for a Chinese-text detector.

No row above should be quoted as "novel", "not covered", or "validated" without the section reference given.

---

<!-- merged-from: docs/research/CHIMERA_REPOSITORY_AUDIT.md -->
## Source: `docs/research/CHIMERA_REPOSITORY_AUDIT.md`

# CHIMERA repository audit (Checkpoint 1, Gate 1)

| Field | Value |
|---|---|
| Commit | `6c7e2c2`, branch `validation/evidence-pass-2026-09-24`, 2026-10-15 |
| Read | `docs/research/{README,DECISION_LOG,ECHOTALES_NOVELTY_LEDGER}.md`, `docs/results/{GOLD_DATASET_README,SCORER_DIAGNOSIS,EXTERNAL_BENCHMARK,FINAL_EVIDENCE_TABLE}.md`; code excerpts cited by file:line below |
| Ran | `git --no-optional-locks` read-only commands; test suites in a scratch copy (not the owner's tree); read-only SQLite queries on a scratch copy of the RI database; unauthenticated GitHub API reads |
| Delegated | Three read-only Explore subagents traced the code. Their reports are model output. Every claim I rely on below is either re-verified by me ([INSPECT], marked V in tables) or marked INFERRED / agent-reported |
| Not done | No file in the repo was modified. No commits. No GPU. No paid API. No pipeline run beyond pytest |

---

## 1. Initial state

| Item | Finding | Tag |
|---|---|---|
| Branch / HEAD | `validation/evidence-pass-2026-09-24` @ `6c7e2c2` | [INSPECT] |
| Untracked paths | 23 (matches directive). Preserved, untouched. | [INSPECT] |
| Remote | `origin git@github.com:adhyan-jain/EchoTales.git` | [INSPECT] |
| `.git/index.lock` | **Does not exist** as of this audit. The directive says a stale lock existed. Either it was removed or it never persisted. Nothing for the owner to delete. | [INSPECT] contradiction |
| Local vs public snapshot | 134 commits ahead of `6aed9f9` | [INSPECT] |
| **Public visibility** | **The GitHub repo is public** (`visibility: public`, unauthenticated API 200). Public `master` is still `6aed9f9` (2026-09-12), but **branch `validation/evidence-pass-2026-09-24` is also public at `6c7e2c2`** (pushed 2026-10-13). No licence file. | [INSPECT] |
| What the public branch exposes | Tracked and on that branch: `packages/ecrdt/IPR_REVIEW{,_FINAL,_V2,_V3,_V4}.md`; `docs/archive/STORYTRACE_TRANSFER.md`; `data/gold/*.jsonl` (each record has a `context` field of about 130 characters of source-novel text, so roughly 20k short excerpts of copyrighted novels are public); all of `docs/research/` as of `6c7e2c2`. `docs/private/` is gitignored and **not** tracked (0 files), which is correct. The three gold/IP file groups are also on public `master`. | [INSPECT] |
| Relevance | Conflicts with D2's default ("nothing is pushed or made public; an arXiv version waits") and with CLAUDE.md's rule that source novels are never committed (excerpt-level text is committed). **No action taken. The decision belongs to the owner.** | [INSPECT] + [INFER] |
| Host | 16 CPUs, 15 GB RAM (about 2 GB free), not the "2 CPU / 3 GB" sandbox the directive mentions | [INSPECT] |

### Tests (scratch copy, `ECHOTALES_LLM_MODE=stub`, core + pipeline suites)
- First run: 1,237 passed, 9 failed, 6 skipped (1,252 collected). All 9 failures were in the owner's untracked `test_adjudication_package.py`, caused by **gitignored inputs that `git archive` does not carry** (`data/eval/human_review_*.csv`, `data/db/reverend-insanity.db`). [INSPECT]
- After copying those inputs into the scratch copy, `test_adjudication_package.py` + `test_llm_annotate.py`: **25 passed**. [INSPECT] Caveat: the RI database was copied without its `-wal` file, so it may lag the owner's live copy.
- The docs claim 1,277 tests; I collected 1,252 in the same two suites. The 25-test difference is unexplained (research tests were not run). [INSPECT]; discrepancy unexplained.

---

## 2. Firewall (decision D1)

- **Where the rule is stated:** `docs/research/README.md:22` ("StoryTrace firewall (no narrative temporal/observer/identity/alias/consistency contribution)"); `ECHOTALES_SOURCE_INVENTORY.md:28` names commit `79e28b6` (2026-10-02) as its adoption; `ECHOTALES_NOVELTY_LEDGER.md` section A heading ("Inside 2026-10-02 Firewall"); and **`packages/research/src/echotales/research/hypotheses.toml`**, where every hypothesis carries a `firewall = "..."` rationale ("no narrative modelling", "not identity resolution") that `packages/research/tests/test_registry.py:24` **requires non-empty**. [INSPECT]
- **Not recorded:** `DECISION_LOG.md` contains no mention of the firewall, its rationale, or any lift (grep returned nothing). The rationale is unrecorded in the repo, as the directive says. [INSPECT]
- **Still stating the old rule after a lift:** the four places above. `hypotheses.toml` plus its test is code, not prose, and encodes the old scope per hypothesis.
- **Proposed wording for the owner to add to `DECISION_LOG.md`** (I have not edited it):

  > **2026-10-15 - Firewall re-scoped (owner decision D1).** The 2026-10-02 StoryTrace firewall, which barred any narrative temporal / observer / identity / alias / consistency contribution from the research track, is lifted for the purpose of *auditing and gate-testing* candidates on those topics (see `CHIMERA_NOVELTY_GATE.md`). It is **not** lifted for: (a) the separately scoped StoryTrace prototype and its code; (b) patent-candidate detail, which stays in the gitignored `docs/private/IP/` with only a pointer in tracked files; (c) any claim of novelty, validation or reproduction, which still requires the evidence gates. Rationale for the original firewall: *[owner to supply; not recorded in the repo]*. Re-scope rationale: *[owner to supply]*.

- Until the owner records it, identity / observer / time candidates are treated as allowed for audit and gate-testing only (D1 default).

---

## 3. Architecture (as traced)

```
EPUB -> ingest/ (chapters, blocks)         [no models; deterministic]
     -> spans/ (rule-based classify)       [recomputed per stage, not read back]
     -> mentions/ (gazetteer + qwen2.5:7b NER, commonness filter, alias_type)
     -> anaphora/ (local groups, kinship)  [pronoun links computed, not stored]
     -> resolve/ (retrieve -> evidence -> prefilter FORCE_LINK/BLOCK/SCORE -> gate)
           post-loop: link_title_holders, merge_transmigrations, retry_deferred
     -> CLI-only: detect_reveals, detect_observations; appearance_extract (LLM)
     -> persona/ (split bodies, wiki_canon overlay, canon, reference sheets)
     -> core/state.py::state_of()  (story time x disclosure time x observer)
              +-> compile_render_state -> render/panels.py (persona choice only)
     appearance_of / persona_at / story_context / wiki canon   (BYPASS state_of)
     -> render: reference_images=[]  -> NoobAI XL
     -> voice/ (whole-book traits, no state, no observer)
     -> video/ (joins manifests by chapter; no state)
     eval: scripts/eval/*  (silver gold only; LitBank is the sole human key)
```

---

## 4. The questions the directive asked first

### 4.1 Can the resolver run on a strict chapter prefix? **Not as a supported mode.**
- `resolve_novel(...)` takes no chapter-limit argument and iterates `store.iter_chapters(novel_id)` over every chapter (`resolve/runner.py:811-827, 890`). [agent-reported]
- `echotales resolve --chapters` is parsed (`cli.py:101`) but **silently ignored**: `cmd_resolve` calls `resolve_novel` without it (`commands.py:728-737`). [INSPECT: verified; `args.chapters` is used at lines 112, 686, 756, 957, 1005 but not in the resolve call]
- A prefix run works only if the database holds just the prefix. Re-ingesting a prefix over a full database does not delete later chapters (INFERRED: no delete in `ingest_config`).
- Stages **upstream** of the resolver use whole-volume information, so a prefix-bounded resolver on a full DB is still not causal: commonness profile from the whole corpus (`mentions/runner.py:330-332`, `mentions/commonness.py:102-127`) and a lexicon induced from 12 chapters spread over the book (`mentions/induce.py:130-143`). [agent-reported]
- No test asserts prefix invariance (resolving chapters 1..c alone equals the first c chapters of a full run). [agent grep]

### 4.2 Can a decision at chapter c see context from after c? **Yes, in deliberate post-hoc passes.**
There are **no 30-50 chapter LLM windows** for NER or alias resolution. `Settings.window_size = 40` governs only the contradiction-sweep / `retry_deferred` cadence and compounding-curve bucketing (`config.py:127-128`, `resolve/runner.py:919-921`). The "30-50 chapter window" wording at `mentions/gazetteer.py:3-4` is stale (the gazetteer rebuilds on staleness per chapter). NER chunks are 6,000 characters within one chapter (`mentions/ner.py:48-53`). So the directive's "30-50 chapter windows" premise is **not what the code does**. [agent-reported]

Real look-ahead, by severity:
1. `link_title_holders` (`resolve/title_holders.py:301`): volume-first by design; the first holder's tenure is forced to start at chapter 1 (`:287`, "retroactive") and earlier title mentions are linked backward. Cannot run causally.
2. `merge_transmigrations` (`resolve/transmigration.py:104-114`): post-loop, rewrites mention targets across all chapters.
3. `retry_deferred` re-scores against later profiles. **Verified: it never links.** On `Decision.LINK` it removes the case from the queue and increments counters; there is no `_apply_link` and no store write (`resolve/runner.py:646-682`). Any "recovered from deferral" figure counts queue removals, not links. [INSPECT]
4. `adjudicate_remaining` (whole-book profiles, outcome discarded) runs only if `use_llm and router`; `cmd_resolve` passes neither. Not reached from the CLI path. [INSPECT for commands.py]
5. Downstream: appearance and world-fact extraction send whole-run samples to the LLM and stamp each value at the earliest grounding chapter, so later evidence can shape an earlier-stamped fact (`resolve/appearance_extract.py:481-533, 781-811`). `world/extract.py::extract_world` has no non-test caller. [agent-reported]

### 4.3 Does wiki-derived appearance describe a later state than its stamp? **Yes, and it has no stamp.**
- The module docstring promises "Every imported trait is dated to the character's *first appearance* chapter" (`persona/wiki_canon.py:26-28`). Not implemented: it stores flat `{label: {trait: value}}` JSON with no chapter, position or interval; grep for `first_appear|chapter` in the file finds only docstrings and comments. [INSPECT]
- The repo records the damage itself: the wiki `typical_attire: "white robes"` was "sourced from deep in the story (the body-2 era)" and "silently beat extraction's correct answer on every pre-regression panel" (`persona/canon.py:49-60`). The fix was hand-authored per-body canon for one character (Fang Yuan). The wiki layer stays position- and body-blind for every other character. [INSPECT]
- `apply_canon` is called after `state_of` and outside the cache digest: `render/panels.py:1398`, `world/context.py:248`, `persona/reference_gen.py:670`. [INSPECT] Agent report: the digest excludes canon, so editing `wiki-appearance.json` changes prompts without changing `state_digest` (INFERRED consequence: stale cache).

---

## 5. Do all render paths consult the same narrative state? **No.**

| Path | Narrative-state input |
|---|---|
| Persona choice per beat | `state_of` at fractional position, with `--observer` (`render/plan_builder.py`, `panels.py:2086`) |
| Persona **attributes** drawn | `appearance_of(position)` filters only `interval.from_lb > position`; ignores observer, `learned_at_pos`, timeline, retraction (`persona/reference_gen.py:208`) |
| Director brief | `story_context`: filters on `learned_at_pos.chapter <= chapter` only; no observer; integer chapter (`world/context.py:128-149`) |
| Cast membership / reveals | chapter-exact event scan, no observer (`render/panels.py:1126-1159`) |
| Reference sheets | whole-novel `appearance_of` + wiki canon, chosen by `reference_path_for`, ignoring position and observer (`persona/reference_gen.py:657-665, 788-801`) |
| Audio | none: whole-book trait profiles, `position=None` (latest body), no observer. The code says so (`voice/runner.py:199-207`) |
| Video | joins panel and voice manifests by chapter; no state; no check they share an observer |
| Visual-memory prototype | explicit (position, cutoff, observer, policy) with lineage; **not wired** into `render_panels` |

(Agent-traced.) So `--observer X` scopes persona choice and the state object's aliases, but the drawn appearance, director brief and reference sheet stay reader-view. INFERRED from the table, not demonstrated by a run.

### Reference conditioning is off in production
`render/panels.py:2740-2741` builds `PanelImageRequest(..., reference_images=[], reference_weight=0.0)` [INSPECT]. The only generation call is `engine.generate(_panel_request)` (`:2850`, agent-reported). Reference-selection code above it still runs but its result never reaches the engine, yet `conditioned_on` metadata and `report.conditioned_panels` are still populated (agent-reported `:2128, :2864, :2854-2855`). **Consequence for the evidence record (INFERRED from the agent's reading, not re-run):** the headline "reference-conditioned: reader 5/5, non-reader 0/5" in `FINAL_EVIDENCE_TABLE.md` and `OBSERVER_CONTRAST_VALIDATION.md` counts a manifest tag, not pixel conditioning. That run (2026-09-25) is after IP-Adapter removal (2026-08-21, EVOLUTION 4.47), and no repo script produces the figure.

### Visual-memory selection is unreachable and not in the cache key
`build_render_plan(visual_registry=...)` would select references through `VisualMemorySelector`, but its only render caller passes none, and the chosen `reference_paths` is neither hashed by `plan_digest` nor copied into the request (agent-reported: `plan_builder.py:171-229`, `contract.py:~155-160`). The selector is exercised only by tests and the owner's synthetic probe harness, which labels it `unwired_component ... on synthetic lineage`.

---

## 6. Component forensic trace (15 components)

Agent-traced; items marked (V) I re-verified.

| # | Component | Key interfaces / callers | Kept / dropped | Model | Known bypass or defect | Determinism | Evaluation trust |
|---|---|---|---|---|---|---|---|
| 1 | Ingestion / normalisation | `ingest_novel` (`ingest/runner.py:46`); `cmd_run`, `cmd_ingest` | Block text, italics; chapter number float from TOC; other markup dropped | none | `--chapters` honoured here only; prefix ingest does not delete later chapters (INFERRED) | deterministic | Fine |
| 2 | Mention detection | `detect_mentions` (`mentions/runner.py:289`); gazetteer + qwen2.5:7b NER, temp 0 | Segment always `segments[0]`; fractional chapters collide | qwen2.5:7b (ollama) | Hard cases lost here (below) | roster-dependent; NER cache key omits roster | **Low for hard cases** |
| 3 | Aliases / resolution / coref | `resolve_novel`; scorer; prefilters; `anaphora/` | Segment, speaker, scene, mention offset dropped; context by first text match | none in default path | Scorer links nothing alone (bias -4.0, threshold 0.80, `score.py:47-80`); `temporal_certainty`, `concurrent_personas`, `speaker` never populated, so the temporal BLOCK never fires | deterministic | Silver only |
| 4 | Fact / event extraction | `detectors.py` regexes; `detect_reveals`, `detect_observations` (CLI-only); `appearance_extract` (LLM); `world/extract.py` (no non-test caller) | Detector events use chapter-first mention; raw string subject/object | LLM | Reveals/observations are not pipeline stages; detector output is not fed back to resolution | LLM nondeterminism | Low |
| 5 | Graph and store | `core/store.py` (SQLite) | `state_of` return type drops per-fact provenance | none | No retract for attributes or relations | deterministic | n/a |
| 6 | Story-time vs disclosure-time | `TemporalFact.interval`, `learned_at_pos`; `state_of` (`core/state.py:207-353`) | Axes real | none | Writers stamp `learned_at` from whole-book analysis (`persona/split.py:~855-866`); whole-novel trait profiles stamped at first attestation (`persona/build.py:~270-290`) | deterministic | Axes real, stamps partly non-causal |
| 7 | Character knowledge | `Observation` table, `observer_id` | Observations attach only to alias facts; almost all facts are `observer_id=READER` | none | Attribute-level observer divergence is never written | deterministic | Self-referential eval |
| 8 | Retractions / contradictions | `retracted_at`; `contradiction.sweep` | `retract_alias_bindings` (`contradiction.py:277`) has **no non-test callers (V)**; `store.retract_alias` called only in tests (V) | none | **Zero production writers.** RI database: 0 retracted rows in alias_binding, attribute, relation (V) | deterministic | Implemented and tested, never exercised on real data |
| 9 | `state_of` / generation state | `compile_generation_state` (`state.py:751-813`) | Digest excludes observer, story position, canon | none | `appearance_of` bypasses `state_of` filters | deterministic | Core is tested |
| 10 | Retrieval / context | `story_context` (`world/context.py`); `CandidateRetriever` | Disclosure-time only, no observer | none | Alphabetical truncation of the known-name roster to 120 (`ner.py:249`) | deterministic | Low |
| 11 | Appearance tracking | `appearance_extract` (LLM, whole-run sample); `wiki_canon`; `canon.py` | Wiki traits unstamped | LLM | Section 4.3 | LLM | Low |
| 12 | Visual references / caching | `reference_gen`, `scene_refs`, `cache_key.py` | Key hashes plan, prompt, seed, backend; **no reference input** since refs are `[]` | NoobAI XL etc. | Prompt cache keyed by DB mtime+size, ignores observer, model, template (`panels.py:~2347`); audio and video have no cache key | seeded | n/a |
| 13 | Panels | `render_panels` (`panels.py`) | `conditioned_on` metadata overstates conditioning | gemma2:9b director; NoobAI XL | Section 5 | seeded | n/a |
| 14 | Audio / video | `voice/runner.py`; `render/runner.py` | No state | Chatterbox TTS; ffmpeg | No observer on the `voice` CLI; manifests can mismatch silently | TTS nondeterminism | No audio scoring script |
| 15 | Evaluation infrastructure | `echotales eval`, `scripts/eval/*`, `gold.py` | `confirmed` tier **empty (V)** | none | Every EchoTales-specific number is silver or model-provisional; LitBank is the only human key; "recovered from deferral" is not a link count | deterministic | See section 8 |

### Mention-detection defects behind the hard-case losses (agent-traced)
- `is_address` exists in `classify_alias_type` but **no caller passes it** (V: grep shows only the definition and recursion), so address-form relational deictics ("Master, ...") are never classified as such.
- `_TRANSFERABLE_TITLE_NOUNS` is a 23-entry hand list; titles outside it fall to `GENERIC_DESCRIPTOR` and are dropped under non-negotiable 4 (`mentions/alias_type.py:49-56, 131-132`).
- `AMBIGUITY_BLOCKLIST` (master, elder, father, uncle, king, lord ...) makes `Gazetteer.add` drop seeded deictics that are exactly one of those words (`mentions/gazetteer.py:37-62, 129-130`).
- The whole-volume commonness filter (`mentions/commonness.py:102-120`, determiner-rate threshold 0.08) would, by the agent's reading of the thresholds, drop surfaces like "master" or "uncle" (INFERRED; not run).
- Title strings absorbed as aliases can later FORCE_LINK to the first absorber and defeat title transfer (mechanism in code per the agent; consequence INFERRED).

---

## 7. Separation of kinds

- **Existing functionality (executed in pipeline or CLI):** ingest, spans, mentions (gazetteer + NER), local anaphora groups, resolve with prefilters, title-holder linking, transmigration merge, appearance extraction, persona split, per-beat `state_of` for persona choice, panels, voice, video.
- **Existing but unintegrated helpers:** `VisualMemorySelector`, `emit_scoped_reference`, `compile_minimal_disclosure` (experiment-only), `retract_alias_bindings`, `retry_deferred` (runs, never links), `adjudicate_remaining` (unreachable from CLI), `coref.resolve_span_pronouns`, `world/extract.py::extract_world`, the `is_address` parameter.
- **Prototypes / research code:** reveal-aware visual memory Phases 1-2 (`core/visual_memory.py`; docs under `docs/research/reveal_aware_visual_memory/`); the technical-contribution probes (synthetic lineage). No `reveal_aware_visual_memory` code exists in `packages/research`; the implementation is in `packages/core` and `packages/pipeline/persona/scoped_reference.py`.
- **Verified artifacts (I re-checked):** 0 confirmed gold records; 58 undetected hard cases (including 1 control, 2 span defects); `reference_images=[]`; 0 retracted rows, 12 observation rows and 0 relation rows in the RI database; 11,095 alias bindings (all TRUE) and 617 attributes (588 TRUE, 29 INFERRED); 25/25 owner tests pass when inputs are present.
- **Unverified earlier claims:** the cache-staleness consequence of wiki canon; `--observer` leaving the brief reader-view; the commonness filter's effect on "master"/"uncle"; what "reference-conditioned 5/0" means; the ~98.9% gazetteer share of FORCE_LINKs (a code comment at `score.py:104-108` only); the directive's "3 reveals" (not re-counted; the reveal detector is CLI-only and not a stored table).

---

## 8. Prioritised defect list

| Rank | Defect | Why it matters for research claims | Evidence |
|---|---|---|---|
| 1 | **No human gold anywhere.** 0 confirmed records; 3,457 RI records carry a reviewer name but `confirmed: false` | Every EchoTales accuracy number is model-provenance | V |
| 2 | **Public repo exposes IPR review files and about 20k excerpt-level text snippets** on a public branch, contradicting D2 defaults | IP and copyright exposure; owner decision | V |
| 3 | **Reference conditioning is off while metadata says "conditioned"** | The observer-conditioned visual result may not be a conditioning result | V (code), INFERRED (consequence) |
| 4 | **Wiki canon is position- and body-blind and outside the cache digest** | Later state leaks into earlier panels; the repo documents one measured instance | V |
| 5 | **No prefix-safe resolver mode; `resolve --chapters` is a silent no-op** | Blocks any disclosure-faithful claim | V |
| 6 | **`retry_deferred` never links; "recovered" counts are queue removals** | Any figure built on `recovered_from_deferral` overstates resolution | V |
| 7 | **Four narrative-state policies coexist; audio and video use none; `--observer` only partly effective** | "Same state for all outputs" cannot be claimed | agent-traced, INFERRED for the observer leak |
| 8 | **Retraction has zero production writers** | The retraction axis cannot be tested on real data | V |
| 9 | **Hard-case detection losses from curated lists, blocklist, commonness filter, unused `is_address`** | The engineering target for C3 | partly V |
| 10 | Test-count discrepancy (docs 1,277 vs 1,252 collected); the novelty ledger says "clean tree" while 23 paths are untracked | Documentation accuracy | V |

I did not exhaustively grep `docs/HANDOFF.md` or `EVOLUTION.md`, so I cannot say whether defects 3 and 6 are already recorded there.

---

## 9. Owner decisions (recorded only; I have decided none)

| ID | Decision | Status | Default applied |
|---|---|---|---|
| D1 | Lift or re-scope StoryTrace firewall | Owner chose to lift (chat, 2026-10-15). Not recorded in the repo. Draft wording in section 2. | Audit and gate-testing only |
| D2 | Publication / IP sequencing | **Open, and the repo is already public** (section 1) | Treat all outputs as private |
| D3 | Reconstruct GenWebNovel text | Not granted; Qidian terms INACCESSIBLE | Do not run |
| D4 | Paid or local-model inference | Not granted | None |
| D5 | Human annotator availability | Unanswered | One annotator plus a second on 20% |
| D6 | Evaluation corpus | Unanswered | RI / LOTM / ORV as local |
