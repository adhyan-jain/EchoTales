# Prior art verification — LLMLINK and LINK-KG

**Verified 2026-09-24 against the full paper text**, not a summary. Closes
`docs/COMPLETION_PLAN.md` Track 6 item 27 and the blocking item in
`docs/IP/invention_disclosure.md` Section 3.1, which recorded the four claims in
`plans.md:818-823` as "asserted, not checked" and required verification
"before this document goes to VIT."

Method: fetched `arxiv.org/pdf/2510.26486`, extracted with `pdftotext
-layout`, then grepped the whole text per concept rather than reading an
abstract. Counts below are occurrences across the entire paper.

---

## 1. What the paper actually is

> **LINK-KG: LLM-Driven Coreference-Resolved Knowledge Graphs for Human
> Smuggling Networks** — Dipak Meher, Carlotta Domeniconi, Guadalupe
> Correa-Cabrera (arXiv:2510.26486)

| | |
|---|---|
| **Domain** | US federal and state **court case documents** on human smuggling, filed 1994-2024, via Nexis Uni. Only the "Opinion" section is used. |
| **Corpus size** | **16 legal cases** (7 short, ≤2,500 words; 9 long) |
| **Entity types** | Seven, domain-specific — actors, events, communication, smuggled items, routes, vehicles, intermediaries |
| **Model** | LLaMA 3.3 70B, temperature 0, served via **Ollama**, on an A100 80GB |
| **Baselines** | GraphRAG 0.3.2 and CORE-KG |
| **Metrics** | **Node duplication %** and **noisy node %** — not precision/recall/F1, not MUC/B³/CEAF |
| **Headline result** | Average node duplication 27.02% (GraphRAG) → 17.00% (CORE-KG) → **10.61%** (LINK-KG) on short cases; noisy nodes 23.59% → 12.41% → **12.28%** |

---

## 2. The four claims in `plans.md:818-823` — all VERIFIED TRUE

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | No temporal axis | **VERIFIED** | One occurrence of "temporal" in the whole paper, inside the *title of a cited reference* (line 449), not the method. Zero occurrences of timeline, chronology, valid time or interval reasoning. |
| 2 | No truth status | **VERIFIED** | Zero occurrences of deception, retraction, contradiction or falsehood. The single "unreliable" hit describes coreference degrading on long documents, not narrative unreliability. |
| 3 | No persona/embodiment split | **VERIFIED** | Zero occurrences of persona, embodiment, disguise, body-swap or reincarnation. Identity is one node per resolved entity. |
| 4 | No downstream multimodal consumption | **VERIFIED** | Zero occurrences of multimodal, image generation or audio. The paper ends at the constructed graph. |

**All four hold.** They were correctly asserted and are now checked.

---

## 3. Two corrections this verification forces

### 3.1 "The current state of the art" needs a qualifier

`plans.md:818` calls LINK-KG "the current state of the art, and now the
primary positioning target in place of LlmLink alone."

It is state of the art **for knowledge-graph construction from legal case
documents about criminal networks**, measured against GraphRAG and CORE-KG on
node-duplication and noise rates. It is not a narrative-coreference system and
reports no coreference metric. Holding it up as *the* positioning target
invites the obvious reviewer response — that is a different task, on a
different corpus, under different metrics. The four negatives above are all
true but **trivially** true, because the paper never attempts any of them.

**Recommended framing:** cite LINK-KG as evidence that the dual-LLM /
prompt-cache line of work has reached long-document entity resolution and
*still* models identity as static and atemporal — a supporting citation, not
the head-to-head comparison.

### 3.2 LLMLINK, not LINK-KG, is the real positioning target

LINK-KG's own related-work paragraph is the most useful sentence in the paper
for this project (emphasis added):

> "Recent work such as LLMLINK [4] leverages dual LLMs and reference tracking
> to improve coreference resolution in long texts. While effective on
> structured, homogeneous datasets like **book chapters**, it struggles with
> complex texts involving **multi-role entities, shifting aliases**, and plural
> references. To address these challenges, we propose LINK-KG, a modular
> LLM-guided framework **extending LLMLINK** with type-specific entity
> tracking."

Three things follow:

1. **LLMLINK is the work evaluated on book chapters**, so it — not LINK-KG —
   is EchoTales' nearest comparable, and Baseline B (an LLMLINK-style dual-LLM
   reimplementation, `plans.md:735`) is aimed at the right target.
2. The repo's claim that LINK-KG "extends LlmLink's dual-LLM memorisation
   architecture" is **correct**, stated verbatim by the paper. An earlier note
   in this session doubted it on the strength of the abstract alone; the full
   text settles it. Reference [4] is *L. Zhu, J. Wang, Y. He, "LlmLink: Dual
   LLMs for dynamic entity linking."*
3. "Multi-role entities" and "**shifting aliases**" are the SOTA paper's own
   words for the gap. A citable statement of the problem EchoTales attacks,
   from the nearest prior work, is stronger positioning material than any of
   the four negatives.

---

## 4. The finding that matters most for this project's defensibility

> "**Since no annotated ground truth exists for structured knowledge graphs in
> this domain**, we adopt both a qualitative and quantitative evaluation
> framework." — Section D, Evaluation Measures

LINK-KG reports no precision, recall or F1 against gold **because it has no
gold**. It substitutes two proxy metrics, detecting duplicates with RapidFuzz
`partial_ratio ≥ 75%` and then having a subject-matter expert manually review
the clusters to remove false positives.

This bears directly on EchoTales' own biggest stated weakness — zero
human-confirmed gold (`EVOLUTION.md` 4.74). The nearest SOTA work in the space
is in the same position and says so in print.

**This does not excuse the gap, and must not be used to.** EchoTales still has
no human-adjudicated ground truth, and `docs/GOLD_DATASET_README.md` says so
plainly. But it does establish that *absence of annotated ground truth is a
condition of this research area* rather than a failing peculiar to this
project — legitimate and citable in both the report's limitations section and
the disclosure.

It also fixes the shape of the comparison: against LINK-KG it is
**methodological, not numerical**. A node-duplication rate over 16 legal
opinions is not comparable to a B³ over a 199-chapter novel, and no table in
this repository may imply that it is.

---

## 5. LLMLINK — VERIFIED 2026-09-25, and it is the real comparable

Full text fetched from the ACL Anthology and grepped, same method as Section 1.

> **LLMLINK: Dual LLMs for Dynamic Entity Linking on Long Narratives with
> Collaborative Memorisation and Prompt Optimisation** — Lixing Zhu (KCL),
> Jun Wang (Warwick / KCL), Yulan He (KCL / Alan Turing Institute).
> COLING 2025, pages 11334–11347.

| | |
|---|---|
| **Task** | Coreference resolution in **chunked long narratives** — the same task |
| **Architecture** | A lower-level LLM for local NER that also emits auxiliary descriptions, and an upper-level LLM specialising in distant coreference, exchanging information through two memorisation schemes |
| **Datasets** | **Coreference-Annotated LitBank** (Bamman et al. 2019) and **DOC-ARC** (Jörke et al. 2020) |
| **Metrics** | **MUC, B³, CoNLL** — the same metric family this project reports |
| **Backbones** | GPT-3.5-turbo and Mixtral-8x7B-Instruct; GPT-4 Turbo as the ranker |
| **Claimed gain** | Performance over other LLM-based and fine-tuning approaches, "significantly reducing the resources required for inference and training" |

### The four claims at `plans.md:816` — all VERIFIED TRUE

| Claim | Verdict | Evidence (occurrences in the full paper) |
|---|---|---|
| Treats identity as static / no temporal binding | **VERIFIED** | One occurrence of "temporal", inside a *citation* to Piper et al. 2021 about "locations and temporal specifications" — not its own mechanism. Zero occurrences of timeline, chronology or valid time. |
| No title transfer | **VERIFIED** | Zero occurrences of transfer, transferable, or alias typing of any kind. |
| No deception / truth status | **VERIFIED** | Zero occurrences of deception, retraction, unreliable narration, truth status or contradiction. |
| No correction loop | **VERIFIED** | Zero occurrences of human-in-the-loop, correction loop, or deferral. |

**Why this matters more than the LINK-KG verification.** LINK-KG's four
negatives are true but *trivially* so — it is a legal-document system that
never attempts any of them (Section 3.1). LLMLINK attempts **the same task on
the same kind of data with the same metrics**, so its negatives are
substantive: a system built for long-narrative coreference, evaluated on
LitBank, that still models identity as static and atemporal. That is the gap
this project addresses, and LLMLINK is therefore the legitimate head-to-head
comparable.

**Baseline B is faithful to it.** `eval/baseline_b.py` implements exactly the
described split — a chunk-local extractor that emits a surface plus a short
descriptor, and a separate linker that sees only the descriptor and a compact
running memory. The paper's own architecture, reimplemented on the same model
family as the system under test.

---

## 6. What still needs checking
- **CORE-KG**, LINK-KG's own baseline, is unexamined and may sit closer to this
  project than LINK-KG does.
- No professional prior-art search has been performed. This is an engineer's
  reading, and the disclosure's ASSERT—VERIFY WITH COUNSEL framing applies to
  every word here.
