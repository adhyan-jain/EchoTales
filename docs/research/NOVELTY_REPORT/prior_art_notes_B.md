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
