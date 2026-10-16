# Prior-art notes A (verification pass, 2026-10-15)

Claim under test: "disclosure-faithful identity resolution under parametric leakage" (chapter-filtering context does
not stop an LLM linking an alias to a later-revealed identity because it remembers the novel). Candidate
contributions: C1 premature-resolution metric via renaming controls; C2 evidence-gated linking rule; C3 small
reader-view / omniscient-view item set.

Method: each PDF fetched from arxiv.org/pdf/<id>, `pdftotext -layout`, relevant sections read (intro, method,
benchmark construction, eval protocol, limitations, data appendices) plus keyword sweeps (alias, coreference, identity,
leak, memoriz, parametric, renam, pretrain, spoiler, disclos, reveal, translat, serial, contamin). "No hits" = sweep of
the full extracted text returned nothing; figures were not inspected visually. Tags: [PUB] = read in the paper's own
text; [LEAD] = search snippet only; UNVERIFIED. Quotes verbatim. Section refs are the papers' own.

## 1. Narrative World Model: Narratology-Grounded Writer Memory for Long-Form Fiction  [PUB]
- Saifullah, Kornmaier, Kazi, Sharma, Kanade, Yadav (PocketFM). arXiv 2607.05577v1 [cs.AI], 6 Jul 2026. "Preprint.
  Under review." (no venue).
- Task/data: writer-memory QA; typed temporal-state graph + hybrid retrieval vs Graphiti/Zep, GraphRAG, RAG, all
  read through a held-constant Opus 4.8 reader over "chapter-safe" evidence (Fig. 1; s3.1 "chapters > n hidden").
  s4.1: 12 Project Gutenberg books (576 Qs; 110 multi-hop) + private "five production-style serialized books of 50
  chapters each" (not redistributable, de-identified Books A-E).
- (a) disclosure vs story time: YES, central. s2: "knowledge boundaries, reveal order ... focalized observer" are
  "first-class"; s3.2 scene records carry "event order, reveal order"; question families "focalization/epistemic (who
  knows what, and when they learned it)" and "reveal-order-versus-event-order" (s4.1).
- (b) alias/identity/coref: NO. Sweep hits "alias" only inside a Table 6 story example ("courts the same woman under an
  alias"). Schema (s3.2) has no entity-linking record; no "is mention X person Y" task.
- (c) leakage/memorisation control: NONE. No hits for leak/parametric/memoriz/contamin/pretrain. Chapter filtering is
  the only control. s8: the no-memory row "is an evidence-free abstention control, not a closed-book recall probe".
  Pseudonymised names in private corpus are for confidentiality (App. B), not leakage control. Gutenberg corpus is
  likely memorised by the reader; not discussed.
- (d) web serials/translated: "serialized books" only; origin/language not stated. UNVERIFIED.
- Closest overlap with EchoTales: chapter-safe cutoff plus reveal-order vs event-order as a modelled axis (supports C3's
  reader/omniscient split in spirit).
- Exact difference: no identity linking, no premature-resolution metric, no renaming/leakage control; scores QA
  accuracy of memory representations.

## 2. Shared Worlds, Private Minds: Structured Memory for Long-Form Writing as World Creation (system: NarraWorld)  [PUB]
- Tian, Gu, Su, Chao, Yin, Guo, Zhang, Shen, Luo, Kong, Xia, Liu* (Southeast Univ., Beijing Zhongguancun Academy,
  ZhuiWen Technology, others). arXiv 2609.32401v1 [cs.CL], 26 Sep 2026. No venue in the text read.
- Task/data (s3.1): long-form writing memory. ConStory-Bench (200 stories), TMAS (168 continuation checkpoints), LSGC
  (5 starters x 14 chapters); transfer to RMTBench role-play and LoCoMo. Baselines Mem0, Graphiti, Hindsight, AriGraph,
  StructMem. Metrics: writing quality / consistency error density.
- (a) disclosure vs story time: PARTIAL, as a design principle. s2.4: "Relevant memory and usable memory differ by
  story time, disclosure state, focalization, and branch. For example, in a mystery, the detective may not yet know
  the truth, while the culprit's identity should not be disclosed prematurely." Admissible view V_q filters
  "temporal, disclosure, and branch scope"; per-character belief view B[c] can hold "a false belief" (App. A.2).
  Never measured as a disclosure-faithfulness metric.
- (b) alias/identity: YES, internal pipeline stage only. App. A.1: "links aliases to existing entities when the
  evidence supports the match and creates a new entity otherwise". Not evaluated; not gated on reveal time.
- (c) leakage/memorisation control: NONE (no hits for leak/parametric/memoriz/contamin/renam). s3.1: conditions
  "exclude future text and evaluator-only references" (context filtering only).
- (d) web serials/translated: not addressed; English benchmarks.
- Closest overlap: explicit "identity should not be disclosed prematurely" + alias-linking stage + append-only store
  where "A state change closes the previous validity interval" (App. A.1), architecturally near EchoTales' graph.
- Exact difference: premature disclosure is a design aim, unmeasured; alias linking unevaluated and unconditioned on
  reveal time; no leakage/renaming control; downstream task is writing quality.

## 3. Scaling Long-Form Story Generation via Narrative State Tracking (NstAgent)  [PUB]
- Zhennan Wan, Jianfei Chen (Tsinghua). arXiv 2609.35759v1 [cs.CL], 28 Sep 2026. "Preprint."
- Task/data (s3-4): generate 10K-100K-word stories; typed state (character states, past events, future requirements);
  revised ConStory-Bench windowed Consistency Error Density + WritingBench. Stories are LLM-generated from prompts.
- (a) disclosure vs story time: NO. State is "retrospective ... as well as ... prospective" (s4.1); "knowledge" is
  only a field inside character state; the "scope marker" (s3) is a judge-window device.
- (b) alias/identity: NO. Only identity-related text is a failure case: the agent "names the same character Bishop
  Armitage in Chapter 0 and Bishop Haldane from Chapter 4 onward"; "Nothing in the loop compares a new entry against
  the earlier text" (own-generation name drift, not resolution).
- (c) leakage control: NO (no hits). (d) web serials/translated: NO; synthetic stories.
- Closest overlap: none substantive (chapter t prompt "contains no earlier chapter text").
- Exact difference: generation-side consistency; no identity, disclosure or leakage dimension. Cite only as generic
  narrative-state related work, not competing prior art.

## 4. TimeChara: Evaluating Point-in-Time Character Hallucination of Role-Playing LLMs  [PUB]
- Ahn, Lee, Lim, Kim, Yun, Lee, Kim (SNU, NAVER AI). arXiv 2405.18027, 28 May 2024; Findings of ACL 2024, pp.
  3291-3325 [LEAD for venue/pages, from search result; PDF is the arXiv version].
- Task/data (s1, s3, s5): 10,895 interview-style instances; 14 characters from Harry Potter, LotR, Twilight, Hunger
  Games; 219 time points; types future / past-absence / past-presence / past-only; GPT-4 judge with spatiotemporal
  labels. Baselines: zero-shot, CoT, RAG, "RAG-cutoff" ("limit its retrieval exclusively to the events prior to a defined
  character period"), and Narrative-Experts.
- (a) disclosure vs story time: YES in role-play form: "avoiding spoilers" is a stated rationale; metric is
  future-type accuracy ("All baselines ... accuracies at 51% or below", s5.4). Character-knowledge boundary, not
  reader-knowledge boundary.
- (b) alias/identity/coref: NO (sweep: none; questions are scene-event interview prompts).
- (c) leakage: ACKNOWLEDGED AND EXPLOITED, not controlled. s3: LLMs "store knowledge of these series well in their
  parametric memories ..., facilitating tests"; s1: "despite LLMs memorizing extensive knowledge from books ... they
  still struggle". No renaming/anonymised control. RAG-cutoff is context filtering only.
- (d) web serials/translated: NO; Limitations: "Sourced only from English books".
- Closest overlap: best direct precedent that LLMs leak future-plot knowledge of famous novels despite being told not
  to; RAG-cutoff = the chapter-filter baseline.
- Exact difference: role-play event knowledge, not alias->identity linking; leakage is the phenomenon but never
  isolated by renaming; no evidence-gated rule; no leakage metric of the proposed kind. Supports the premise only.

## 5. SynthWorlds: Controlled Parallel Worlds for Disentangling Reasoning and Knowledge in Language Models  [PUB]
- Ken Gu, Advait Bhat, Mike A. Merrill, Robert West, Xin Liu, Daniel McDuff, Tim Althoff (UW, Stanford, EPFL,
  Google). arXiv 2510.24427 (v1 28 Oct 2025); ICLR 2026 (PDF header: "Published as a conference paper at ICLR 2026").
- Task/data (s3-4, App. B): parallel Wikidata-derived corpora, real-mapped (RM) vs synthetic-mapped (SM) with identical
  structure; multi-hop QA and page navigation; metric "knowledge advantage gap" (RM minus SM).
- (a) disclosure vs story time: NO. Timestamps shifted by fixed offset only "to prevent timestamps from trivially
  revealing real-world identities" (App. B); no narrative or disclosure axis.
- (b) alias/identity: NO as a task. Only name-derivation consistency ("Vancouver -> Metronis, then George Vancouver ->
  Altheon Metronis").
- (c) leakage control: YES, the whole paper; strongest precedent for C1's method. s1: synthetic data built from
  "existing content directly (e.g., novels)" "results in parametric knowledge leakage". App. B: "Simple renaming risks
  (a) factual leakage ... (e.g., Tokyo -> Torioka, which continues to suggest Japanese origins)". Leak audit: an LM is
  asked to guess the real entity behind each synthetic page and leaked pages are removed. s6: idea "generalizes to any
  knowledge graph".
- (d) web serials/translated: NO.
- Closest overlap: renaming as leakage control, a performance gap metric, and a rename-leak audit.
- Exact difference: encyclopedic multi-hop QA, not fiction; no disclosure-time or premature-resolution notion. Any
  EchoTales renaming control must cite SynthWorlds as the method source; novelty of C1 can only lie in the narrative /
  disclosure-cutoff metric, not in renaming itself.

## 6. E2RAG / ChronoQA: Respecting Temporal-Causal Consistency: Entity-Event Knowledge Graphs for RAG  [PUB]
- Ze Yu Zhang, Zitao Li, Yaliang Li, Bolin Ding, Bryan Kian Hsiang Low (NUS, Alibaba). arXiv 2506.05939v1 [cs.IR],
  6 Jun 2025; EACL 2026 Long Papers [LEAD, from search result].
- Task/data (s3, Tables 1-2): ChronoQA, 497 QA pairs over 9 stories (Oz, Sherlock Holmes x4, Phantom of the Opera,
  Harry Potter 1 and 2, Les Miserables), all stated as Project Gutenberg; 8 facets (Character Consistency 229, Causal
  96, ...); questions auto-generated by o1-pro / Claude-3.7 with passage offsets.
- (a) disclosure vs story time: PARTIAL. Query 1: naive RAG "overlooks crucial information revealed later" (Quirrell vs
  Snape); questions hinge on temporal facets ("after the troll incident"). That is retrieval of the right chronological
  passage; no reader-time cutoff protocol found.
- (b) alias/identity: OPPOSITE DESIGN. s4: "We therefore keep each mention ... distinct"; "Hermione in Chapter 9 versus
  Miss Granger in Chapter 16" are separate nodes; no merging; no resolution evaluation.
- (c) leakage control: NONE (no hits for leak/memoriz/parametric/contamin/renam); heavily-read books used without a
  closed-book or renamed baseline.
- (d) web serials/translated: NO.
- Closest overlap: time-aware KG over novels with a "revealed later" example; mention-level entity nodes.
- Exact difference: retrieval QA quality, not identity linking; avoids premature merging by never merging, rather than
  gating merges on evidence/disclosure; no leakage control.

## Cross-paper takeaways
1. None of the six defines a premature-resolution metric, an evidence-gated alias->identity rule, or a reader-view vs
   omniscient-view item set (absence from read sections and keyword sweeps; not proof for unread figures).
2. Renaming as leakage control: precedent SynthWorlds (Wikidata, not fiction). Leakage-in-novels motivation: TimeChara.
   Neither combines them with alias resolution under a disclosure cutoff.
3. Closest on disclosure-aware memory: NWM (reveal order, chapter-safe cutoff) and NarraWorld ("identity should not be
   disclosed prematurely"; alias stage). Neither evaluates leakage or premature linking.
4. Unverified: venues for TimeChara (Findings of ACL 2024) and E2RAG (EACL 2026) come from search snippets; NWM's
   private "serialized books" provenance (web serial or not) is UNVERIFIED. No paper here covers web serials or
   translated novels.
