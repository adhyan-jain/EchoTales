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
