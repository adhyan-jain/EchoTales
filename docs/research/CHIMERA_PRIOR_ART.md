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
