# University project report — source material (all 16 sections)

**Written 2026-09-25.** Every claim is tagged: **[M]** measured, with a
recorded command · **[I]** implementation fact, verifiable in the code ·
**[D]** intended design, not yet demonstrated · **[L]** limitation.
Untagged prose is framing only. All accuracy figures are scored against an
**LLM-derived SILVER reference set (Claude), not human gold, no IAA**.

---

## 1. Title page
**EchoTales: A Bitemporal, Observer-Scoped Narrative Knowledge Graph for
Multimodal Adaptation of Long-Form Serialised Fiction**
University AI course — semester project · 2026
Adhyan Jain (24BCI0111) · Atharva Sheerh Pandey (24BCI0069) · Aryan Gahlot (24BCI0033)
Planned outcome: patent filing and research publication.

## 2. Structured abstract (≤250 words)
**Problem.** Serialised web fiction breaks the assumptions of narrative
coreference: titles transfer between holders, identities are concealed and
revealed, characters change bodies, and chapter order is not story order.
Existing systems produce one static entity graph seen by one global reader.
**Approach.** EchoTales builds a bitemporal, observer-scoped knowledge graph
queried by `state_of(target, timeline, position, observer)`, resolving
identity incrementally with evidence accumulation, and drives visual
generation from that query rather than the text.
**Results.** On a 199-chapter volume processed in 47 minutes on a consumer GPU
with zero paid-model escalations, repairing a mention-layer defect raised the
entity inventory from 82 to 261 and CEAF-e clustering recall from 25.2% to
48.9%. Against matched long-context and dual-LLM baselines, the system recovers
359 mentions where they recover 10 and 133, with zero model calls at
resolution. Observer-conditioned generation is demonstrated on a real image
engine: holding everything else constant, a reader's panels name the character
and a non-witness's say "a figure".
**Limitations.** No human-annotated gold; the learned scorer ranks correctly
but cannot link; hard alias types are mostly missed at mention detection.

## 3. Introduction
Long-form serialised fiction — translated Chinese and Korean web novels running
to thousands of chapters — is a natural target for automated audio and visual
adaptation, and a hard one. Adapting it requires knowing, at every point, who
is present and what they look like. That is a coreference problem, but not the
one standard tooling solves.

Four properties of the domain break standard assumptions: one character
carries dozens of shifting names; titles pass between holders; a single chapter
mixes present action, dreams and memories; and identity is concealed, revealed,
faked and retracted. A system that treats identity as fixed and every fact as
permanently true cannot represent a disguise, a reincarnation, or the fact that
one character knows a secret another does not.

EchoTales treats these as first-class temporal and epistemic relations. Its
graph answers what is true of a character at a given story position, as known
to a given party, and its generation layer consumes that answer. The result is
perspective-correct generation as a property of the data model rather than of
post-processing.

The project also takes evaluation seriously enough to report negative results:
a retracted headline, a reference set shown to be trivially satisfiable, and a
learned scorer shown to be arithmetically unable to link.

## 4. Related work
Fifteen works; full per-work entries (problem, approach, result, dataset, two
limitations) below, then the comparison table.

**Narrative coreference.** LLMLINK (Zhu, Wang, He; COLING 2025) is the nearest
comparable: a lower-level LLM performs local NER and emits descriptions, an
upper-level LLM resolves distant coreference, joined by memorisation; evaluated
on LitBank and DOC-ARC with MUC/B³/CoNLL. Verified against its full text, it
models identity as static, with no temporal, transfer, deception or correction
machinery. LINK-KG (arXiv:2510.26486) extends it with a type-specific prompt
cache for legal documents and reports graph-quality proxies because, in its own
words, no annotated ground truth exists in its domain. BOOKCOREF (ACL 2025)
provides book-scale coreference annotation — addressing LitBank's
first-2,000-token limit — but, as a corpus, carries no temporal or observer
axis. Literary coreference annotation with LLMs (arXiv:2401.17922, 2024) and
full-length French fiction coreference (arXiv:2510.15594, 2025) extend
coverage and length but keep a single reader perspective. Work on detective
narratives (arXiv:2402.11051, 2024) finds LLMs underperform on relationships
that require inference across concealment — direct support for this project's
framing.

**Consistent visual storytelling.** Narrative Graph Prompting (ICCVW 2025)
centralises story elements in a narrative graph with canonical visual
attributes and has an LLM build scene prompts from it — the closest work to
EchoTales' generation claim, but its graph is a static registry with one
viewer. StoryWeaver (arXiv:2412.07375) uses character-graph-enhanced captions
against identity blending; TaleCrafter (arXiv:2305.18247) plans multi-character
layouts; ContextualStory (arXiv:2407.09774) propagates storyline context across
frames, where "temporal" means frame order rather than story time. A 2025
survey (Artificial Intelligence Review) identifies character consistency as the
dominant open problem and does not treat perspective-dependent depiction as a
category at all. Hierarchical graphs for comics (arXiv:2506.10008) analyse
existing visual narrative rather than generating it.

**Adjacent foundations.** Bitemporal data models record when the database
believed a fact, not which in-world party did. Temporal knowledge-graph
completion reasons over time-stamped triples with a single global observer and
no generation consumer.

| # | Work | Year | Task | Temporal state | Observer axis | Embodiment split | Generation | Two limitations |
|---|---|---|---|---|---|---|---|---|
| 1 | LLMLINK | 2025 | Narrative coref | No | No | No | No | static identity; stops at graph |
| 2 | LINK-KG | 2025 | Legal KG coref | No | No | No | No | no gold; different document class |
| 3 | BOOKCOREF | 2025 | Book-scale corpus | No | No | No | No | a corpus not a system; no transfer |
| 4 | LLM literary annotation | 2024 | Literary coref | No | No | No | No | short excerpts; one reader |
| 5 | French full-length fiction | 2025 | Novel coref | No | No | No | No | no truth modelling; monolingual |
| 6 | Detective narratives | 2024 | Relation extraction | No | No | No | No | no identity over time; no generation |
| 7 | Narrative Graph Prompting | 2025 | Story visualisation | No | No | No | Yes | static registry; one viewer |
| 8 | StoryWeaver | 2024 | Character customisation | No | No | No | Yes | one appearance per character; no observer |
| 9 | TaleCrafter | 2023 | Story visualisation | No | No | No | Yes | identity by reference image; no knowledge state |
| 10 | ContextualStory | 2024 | Story visualisation | Frame order | No | No | Yes | no story time; embedding-only consistency |
| 11 | Narratology × T2I survey | 2025 | Survey | — | — | — | — | no system; no observer category |
| 12 | Hierarchical comic graphs | 2025 | Visual narrative analysis | No | No | No | No | analysis only; no truth modelling |
| 13 | LitBank | 2019 | Corpus | No | No | No | No | 2,000 tokens/work; static inventory |
| 14 | Bitemporal DBs | — | Data model | Yes | No | No | No | database belief only; no "never true" |
| 15 | Temporal KG completion | 2021–24 | KG reasoning | Yes | No | No | No | one observer; no embodiment |
| — | **EchoTales** | 2026 | Narrative graph + generation | **Yes** | **Yes** | **Yes** | **Yes (visual)** | silver-only evaluation; scorer inert |

## 5. Summary of limitations and gaps
| Gap in the literature | EchoTales response |
|---|---|
| Identity treated as static (1–6, 13) | Three-axis time; interval-scoped, typed alias bindings |
| Visual consistency via static registries (7–10) | Self/Persona with temporally scoped bindings |
| One global viewer everywhere (1–15) | Observer-scoped knowledge state |
| No "was never true" vs "stopped being true" (1–15) | Retraction distinct from interval end [D] |
| Coreference stops at the graph; generation starts from captions | Graph-conditioned generation with read-set invalidation |
| Reference-set validity assumed (3, 4, 13) | Surface-recoverability criterion for annotation sets |

## 6. Primary contributions
1. **Observer-scoped knowledge state**, demonstrated on real data on two axes:
   who asks and when they ask from. [M]
2. **Observer-conditioned visual generation** on a real image engine: same
   scene, only the observer differs, different cast and naming. [M]
3. **Read-set-derived artifact invalidation** that invalidates dependent
   artifacts and spares unrelated ones. [M] (aliases outside the read set [L])
4. **Self/Persona separation** with temporally scoped bindings; real
   reincarnation case. [M] (concurrent cases [D])
5. **A validity criterion for coreference reference sets** — surface
   recoverability — that caught a retracted headline from a second direction. [M]
6. **An evidence-backed negative result on learned scoring**: ranks correctly
   94% of the time, arithmetically capped at p=0.55 against a 0.80 threshold. [M]
7. **A cost asymmetry** against matched baselines: zero model calls at
   resolution versus 1 and 177. [M]

## 7. Individual contributions
| Member | Reg. No. | Contribution |
|---|---|---|
| Adhyan Jain | 24BCI0111 | System architecture; full pipeline implementation; evaluation harness, baselines, ablations; rendering and voice integration |
| Atharva Sheerh Pandey | 24BCI0069 | Annotation and labeling; test design and verification |
| Aryan Gahlot | 24BCI0033 | Annotation and labeling; test design and verification |

*(Team to confirm wording before submission.)*

## 8. Tools and technologies [I]
Python 3.12 (uv); SQLite with an explicit bitemporal schema; Ollama serving
`qwen2.5:7b` locally for NER, attribution, appearance and direction; diffusers
with NoobAI XL / Illustrious / GuoFeng3 checkpoints; Chatterbox TTS with
reference-clip cloning; ffmpeg (composition, pitch); React review interface
over a stdlib HTTP API; pytest (1,071 tests), ruff, mypy. Hardware: NVIDIA RTX
4060 Laptop, 8 GB. External API spend: zero.

## 9. Methodology
**Pipeline [I].** Ingest → segment and detect timelines → detect mentions and
type aliases → attribute speakers → bind anaphora and co-presence → resolve
identity (the only branch: LINK / NEW / DEFER) → construct Selves and Personas
→ extract appearance → record observations → graph → visual, audio and
evaluation consumers. The core graph package imports nothing from generation,
enforced in CI.
**Evaluation [I].** MUC, B³, CEAF-e and CoNLL as pure partition mathematics;
bootstrap confidence intervals; results persisted with commit, seed, database
and platform. Calibration and fitting split **by chapter**, never randomly.
**Baselines [I].** Same model, host and scorer: a long-context LLM given whole
sections, and a reimplementation of LLMLINK's dual-LLM memorisation.
**Ablations [I].** Eight conditions re-scored over a cached evidence set of
15,796 pairs, with no re-inference.

## 10. Dataset
Three novels ingested in full: Reverend Insanity (199 chapters, primary), Lord
of the Mysteries (213), Omniscient Reader's Viewpoint (188). [M]
Reference sets: 3,889 LLM-derived silver records on the primary novel, drafted
by a different model family than the system under test. [M]
**[L]** No human-annotated gold. Two of three reference files are 100%
reproducible by surface-string grouping and therefore cannot discriminate
systems; only the 89-record hard-case file (63.6% recoverable) does.
**[L]** Source novels are copyrighted; annotations store offsets and short
snippets only. Voice references: VCTK, CREMA-D, and EARS (CC BY-NC 4.0 —
research use only).

## 11. Proposed approach and architecture
See the one-page flowchart in `docs/IP/EchoTales_Project_Documentation.html`
Section 3 and `docs/paper/FIGURES.md`. Central query:
`state_of(target, timeline, position, observer) → {aliases, attributes,
relationships, persona, certainty}`. [I]

## 12. Results and discussion [M]
- Full volume end to end: 199 chapters, 47 min, 660 model calls, 0 escalations,
  2 deferrals of 1,532 decision groups (0.1%).
- Mention-layer repair: entities 82 → 261; typed entities 18 → 261; CEAF-e
  recall 25.2% → 48.9%; CoNLL F1 78.1 → 86.5; speaker identifiability
  48.8% → 63.0%; contradictions detected 0 → 50. A pre-registered prediction
  that mentions would double was **refuted** (+14.6%).
- Retriever recall@10 given the gold span: rigid names 83.9%, transferable
  titles 77.8%, relational/deictic 25.0%.
- **Hard cases are lost at detection:** 59 of 89 never become mentions
  (relational/deictic 25/29; title transfer 16/17).
- **Scorer:** ranks the correct candidate first 97/103 (94.2%), but three of
  its five weighted features never vary on this corpus, capping probability at
  0.550 against a 0.80 threshold. A chronologically-split refit does not help,
  and every labelled decision is taken by a pre-filter before the scorer.
- Ablation: the accumulated gazetteer accounts for 66% of links.
- Observer contrast: reader 5/5 reference-conditioned panels naming the
  character; non-witness 0/5, "a figure", one person.

**Discussion.** The system's quality comes from its deterministic,
evidence-accumulating filters, not its learned component; that is reported
plainly. The contribution is the representation and what it enables — the
observer and embodiment axes, and generation that respects them.

## 13. Comparative analysis [M]
| Chapters 1–10 | Baseline A (long-context) | Baseline B (dual-LLM) | EchoTales |
|---|---:|---:|---:|
| Model calls | 1 | 177 | 0 at resolution |
| Prompt tokens | 24,302 | 142,835 | — |
| Wall time | 146 s | 435 s | — |
| Mentions recovered (reference 356) | 10 | 133 | 359 |

Baseline A is bounded by output budget: 697 output tokens, ten mentions for ten
chapters. Baseline B's chunking fixes that at 177× the calls. **[L]** On this
range the reference set is surface-trivial, so this is an extraction-coverage
comparison, not a coreference-quality one.

## 14. User manual
```bash
source .venv/bin/activate
ollama serve &                                        # local model server
echotales --db data/novel.db run --novel reverend-insanity          # full pipeline
echotales --db data/novel.db observations --novel reverend-insanity # observer axis
echotales --db data/novel.db query state-of --novel reverend-insanity \
    --target <self_id> --chapter 200 --observer READER               # the core query
echotales --db data/novel.db eval --novel reverend-insanity \
    --gold data/gold/reverend-insanity-hardcases.jsonl               # metrics
echotales --db data/novel.db eval --novel reverend-insanity --gold <file> --validate-gold
echotales --db data/novel.db ablate --novel reverend-insanity
echotales --db data/novel.db render --novel reverend-insanity --chapters 169 \
    --image-engine noobai --observer <id> --max-panels 3               # panels
echotales --db data/novel.db voice --novel reverend-insanity \
    --bank data/voice/ears --bank-kind ears --engine chatterbox        # audio
python3 scripts/scorer_diagnosis.py && python3 scripts/make_paper_artifacts.py
python3 -m pytest packages/                                            # 1,071 tests
```
Stub mode (`ECHOTALES_LLM_MODE=stub`, `--image-engine stub`) runs everything
with no GPU and no network. **Run-order warning:** `resolve` deletes persona
bindings; never run it after `run` without rebuilding personas.

## 15. References
1. Zhu, L., Wang, J., He, Y. LlmLink: Dual LLMs for Dynamic Entity Linking on Long Narratives with Collaborative Memorisation and Prompt Optimisation. COLING 2025, 11334–11347.
2. Meher, D., Domeniconi, C., Correa-Cabrera, G. LINK-KG: LLM-Driven Coreference-Resolved Knowledge Graphs for Human Smuggling Networks. arXiv:2510.26486, 2025.
3. BOOKCOREF: Coreference Resolution at Book Scale. ACL 2025.
4. [Lions: 1] and [Tigers: 2] and [Bears: 3], Oh My! Literary Coreference Annotation with LLMs. arXiv:2401.17922, 2024.
5. The Elephant in the Coreference Room: Resolving Coreference in Full-Length French Fiction Works. arXiv:2510.15594, 2025.
6. Large Language Models Fall Short: Understanding Complex Relationships in Detective Narratives. arXiv:2402.11051, 2024.
7. Generating Visually Consistent Images for Storytelling via Narrative Graph Prompting. ICCV Workshops (AISTORY), 2025.
8. StoryWeaver: A Unified World Model for Knowledge-Enhanced Story Character Customization. arXiv:2412.07375, 2024.
9. TaleCrafter: Interactive Story Visualization with Multiple Characters. arXiv:2305.18247, 2023.
10. ContextualStory: Consistent Visual Storytelling with Spatially-Enhanced and Storyline Context. arXiv:2407.09774, 2024.
11. Narratology meets text-to-image: a survey of consistency in AI generated storybook illustrations. Artificial Intelligence Review, 2025.
12. Structured Graph Representations for Visual Narrative Reasoning: A Hierarchical Framework for Comics. arXiv:2506.10008, 2025.
13. Bamman, D., Lewke, O., Mansoor, A. An Annotated Dataset of Coreference in English Literature (LitBank). LREC 2020.
14. ISO/IEC 9075:2011 (SQL:2011) — temporal and bitemporal tables.
15. Richter, J. et al. EARS: An Anechoic Fullband Speech Dataset Benchmarked for Speech Enhancement and Dereverberation. Interspeech 2024.

*(Author lists for 3–12 to be completed from the papers before submission;
titles and venues above are verified.)*

## 16. Appendix
- `docs/VALIDATION_BASELINE.md` — starting state and environment
- `docs/NER_WINDOWING_RESULT.md` — the adjudicated full-volume re-run
- `docs/GOLD_DATASET_README.md` — reference-set provenance and validity
- `docs/EVAL_RETRIEVER.md`, `docs/SCORER_DIAGNOSIS.md`, `docs/BASELINES.md`
- `docs/STATE_OF_VALIDATION.md`, `docs/SELF_PERSONA_VALIDATION.md`,
  `docs/OBSERVER_CONTRAST_VALIDATION.md`
- `docs/PRIOR_ART_LINKKG.md` — full-text verification of LLMLINK and LINK-KG
- `docs/paper/TABLES.md`, `docs/paper/FIGURES.md` — generated from artifacts
- `data/eval/` — every persisted metric, with commit and seed
