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
**Results.** On a 199-chapter volume, against an LLM-drafted silver reference set:
- entity-level CEAF-e F1 is 67.4, with B³ precision at 100%;
- repairing two mention-layer defects raised the entity inventory from 82 to 267;
- every hard case the system detects is linked correctly (24/24), and the misses are at mention detection (58/88);
- given the span, retrieval finds the right entity in the top 10 for 89.1% of hard cases;
- on ten chapters, matched baselines reach 0.2% and 4.6% B³ recall against 78.9%;
- a character who witnessed a reveal sees the revealed name only from the chapter it happened, a non-witness never sees it, and a real image engine renders the difference.

**Limitations.** No human-annotated gold; the learned scorer contributes no links; hard alias types are mostly missed at detection; a transmigrated protagonist in a second novel is split into two identities; speaker attribution covers 46.1% of speech.

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
6. **An evidence-backed negative result on learned scoring**: every link is made
   by deterministic evidence rules; the learned scorer makes none and is kept
   as an optional, experimental layer. [M]
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
reference-clip cloning over the EARS studio speech corpus; ffmpeg
(composition, pitch); React and static HTML review interfaces over a stdlib
HTTP API; pytest (1,078 tests), ruff, mypy. Hardware: NVIDIA RTX 4060 Laptop,
8 GB. External API spend: zero.

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
16,538 pairs (canonical run, Table 6), with no re-inference.

## 10. Dataset
Three novels ingested in full: Reverend Insanity (199 chapters, primary), Lord
of the Mysteries (213), Omniscient Reader's Viewpoint (188). [M]

Reference sets are the **LLM-DRAFTED SILVER REFERENCE SET**, drafted by Claude models, not the system under test [M]:

| File | Records | Use |
|---|---:|---|
| RI main file | 1,816 silver entity mentions | coreference |
| RI hardcases | 88 records with identity; alias types rigid / title / relational / epithet; five categories (body change, disguise, reveal, title transfer, relational) | hard cases and retrieval |
| LOTM ch1–3 | 155 entity records, drafted without seeing the pipeline's output | generalisation |

**[L]** No human-annotated gold and no IAA. The RI main file and the LOTM file
are 100% reproducible by surface-string grouping, so their MUC/B³ figures
measure string matching; CEAF-e and the hardcases file are the discriminative
measures.

**[L]** Source novels are copyrighted; annotations store offsets and short
snippets only. Voice references: VCTK, CREMA-D, and EARS (CC BY-NC 4.0 —
research use only).

## 11. Proposed approach and architecture
See the one-page flowchart in `docs/private/IP/EchoTales_Project_Documentation.html`
Section 3 and `docs/paper/FIGURES.md`. Central query:
`state_of(target, timeline, position, observer) → {aliases, attributes,
relationships, persona, certainty, read_set}`. [I]

**Resolution is layered, and the layers are measured separately**
(`docs/results/FINAL_EVIDENCE_TABLE.md` Section 4, 16,538 candidate pairs) [M]:

| Layer | Role | Measured |
|---|---|---|
| Hard constraints (co-presence, temporal gate) | veto | 3,072 blocked |
| Deterministic evidence rules (gazetteer, declaration, name containment) | link | 1,376 links: all of them |
| Retrieval | candidate generation | recall@10 89.1% given the span |
| Learned scorer | optional ranking | 0 links; **OPTIONAL / EXPERIMENTAL** |

## 12. Results and discussion [M]
All figures are from the canonical run (`docs/results/CANONICAL_RUN.md`) against the
LLM-drafted silver reference set, unless stated otherwise.

- **End to end:** 199 chapters on one 8 GB laptop GPU; 47 min cold, 12 min with the NER cache.
- **Coreference (Table 4):** CEAF-e P / R / F1 **89.8 / 53.9 / 67.4**; B³ precision 100%. MUC/B³ F1 (97.9 / 97.0) are reported but mostly measure string matching on this set.
- **Hard cases (88):** 30 detected, and of the decidable ones **24/24 linked correctly, 0 wrong**; 58 undetected.
  - Failure taxonomy: address terms 16, relational 15, definite titles 11, pronouns 10 (by design), other 6.
  - Detection, not linking, is the bottleneck.
- **Retrieval (Table 5, Figure 8):** given the reference span, production context, recall@1/5/10/20 = 67.4 / 87.0 / **89.1** / 95.7% (n=46; titles 88.9% @10, n=9).
- **Resolution layers:** deterministic rules make every link; the learned scorer makes none (maximum score 0.41 against a 0.80 threshold) and is reported as optional/experimental.
- **Observer-conditioned state** (`data/eval/observer_evidence.json`): the same fact about the same character is visible to the reader (2 aliases), a witness (1) and a non-witness (0). The witness sees 0 / 1 / 1 aliases asking from ch150 / 166 / 200.
- **Observer-conditioned generation:** reader 5/5 reference-conditioned panels naming the character; non-reader 0/5, "a figure", one person.
- **One detection bug found and fixed:** "Wang Er" was invisible for 199 chapters (demonstrative idiom); CEAF-e F1 63.1 → 67.4.
- **Speaker attribution:** 46.1% of speech spans. A pronoun pass that inflated this to 63.0% was measured at 2/15 correct and removed from the default. The LLM tier is 12 right / 16 wrong and unstable across runs.
- **Generalisation (LOTM ch1–3):** B³ recall 62.3%, CEAF-e F1 41.4. The transmigrated protagonist is split into two Selves.
- **Pre-registered predictions:** two of three were refuted (mentions did not double; attribution did not rise).

**Discussion.** Quality comes from deterministic, evidence-accumulating
rules, and precision holds at 100% on silver. Recall is lost at mention
detection for the hard reference types. The contribution is the
representation and what it enables: the observer and embodiment axes, and
generation that respects them. The weakest points are stated as results, not
hidden.

## 13. Comparative analysis [M]
Same model, host, scorer and reference set; chapters 1–10, 356 silver mentions
(`docs/paper/TABLES.md` Table 7, Figure 9):

| | Baseline A (long-context) | Baseline B (dual-LLM, LLMLINK-style) | EchoTales |
|---|---:|---:|---:|
| Model calls | 1 | 177 | 0 at resolution |
| Prompt tokens | 24,302 | 142,835 | — |
| Wall time | 129 s | 354 s | — |
| Mentions recovered | 10 | 133 | 369 |
| B³ precision / recall | 100.0 / 0.2% | 95.4 / 4.6% | 100.0 / **78.9%** |

**Scope correction.** An earlier version of this table put EchoTales'
*full-volume* recall (96.3%) beside the baselines' ch1–10 figures. The row
above is the same-range number.

**[L]** On this range the reference set is surface-trivial, so this compares
extraction coverage, not coreference quality.

LLMLINK, LINK-KG, BOOKCOREF and LitBank figures are **not directly comparable
and not reproduced in this evaluation**: different corpora, and for LINK-KG
different metrics (node duplication over legal documents).

## 14. User manual
```bash
source .venv/bin/activate
ollama serve &                                        # local model server
DB=data/db/reverend-insanity.db                          # canonical (docs/results/CANONICAL_RUN.md)
echotales --db $DB run --novel reverend-insanity                  # full pipeline
echotales --db $DB observations --novel reverend-insanity         # observer axis
echotales --db $DB query state-of --novel reverend-insanity \
    --target "Bai Ning Bing" --chapter 200 --observer READER     # the core query
echotales --db $DB eval --novel reverend-insanity                 # coreference, silver
echotales --db $DB eval --novel reverend-insanity \
    --gold data/gold/reverend-insanity-hardcases.jsonl --validate-gold
echotales --db $DB ablate --novel reverend-insanity --out data/eval/ablation/reverend-insanity.json
echotales --db $DB render --novel reverend-insanity --chapters 169 \
    --image-engine noobai --observer <self_id> --max-panels 3       # panels
echotales --db $DB voice --novel reverend-insanity \
    --bank data/voice/ears --bank-kind ears --engine chatterbox     # audio
echotales webview --source "$DB:reverend-insanity:Reverend Insanity" --format static
bash scripts/reproduce_results.sh                                # every reported number
python3 -m pytest packages/core/tests packages/pipeline/tests    # 1,078 tests
```

- Stub mode (`ECHOTALES_LLM_MODE=stub`, `--image-engine stub`) runs everything with no GPU and no network.
- **Run-order warning:** `resolve` deletes persona bindings; never run it after `run` without rebuilding personas.
- **Screenshots** (private, because they contain copyrighted chapter text): `docs/private/IP/screenshots/webview-overview.png` shows the review viewer, with entity list, per-line speaker and method, and highlighted mentions. Rendered panels are under `data/novels/RI/experiments/observer-contrast/reader/` and `data/novels/RI/experiments/observer-contrast/nonwitness/`.

## 15. References
1. Zhu, L., Wang, J., He, Y. LlmLink: Dual LLMs for Dynamic Entity Linking on Long Narratives with Collaborative Memorisation and Prompt Optimisation. COLING 2025, 11334–11347.
2. Meher, D., Domeniconi, C., Correa-Cabrera, G. LINK-KG: LLM-Driven Coreference-Resolved Knowledge Graphs for Human Smuggling Networks. arXiv:2510.26486, 2025.
3. Martinelli, G., Bonomo, T., Huguet Cabot, P.-L., Navigli, R. BOOKCOREF: Coreference Resolution at Book Scale. ACL 2025. arXiv:2507.12075.
4. Hicke, R. M. M., Mimno, D. [Lions: 1] and [Tigers: 2] and [Bears: 3], Oh My! Literary Coreference Annotation with LLMs. arXiv:2401.17922, 2024.
5. Bourgois, A., Poibeau, T. The Elephant in the Coreference Room: Resolving Coreference in Full-Length French Fiction Works. arXiv:2510.15594, 2025.
6. Zhao, R., Zhu, Q., Xu, H., Li, J., Zhou, Y., He, Y., Gui, L. Large Language Models Fall Short: Understanding Complex Relationships in Detective Narratives. arXiv:2402.11051, 2024.
7. Shin, A., Kaneko, K. Generating Visually Consistent Images for Storytelling via Narrative Graph Prompting. ICCV Workshops (AISTORY), 2025.
8. Zhang, J., Tang, J., Zhang, R., Lv, T., Sun, X. StoryWeaver: A Unified World Model for Knowledge-Enhanced Story Character Customization. arXiv:2412.07375, 2024.
9. Gong, Y., Pang, Y., Cun, X., Xia, M., He, Y., Chen, H., Wang, L., Zhang, Y., Wang, X., Shan, Y., Yang, Y. TaleCrafter: Interactive Story Visualization with Multiple Characters. arXiv:2305.18247, 2023.
10. Zheng, S., Fu, Y. ContextualStory: Consistent Visual Storytelling with Spatially-Enhanced and Storyline Context. arXiv:2407.09774, 2024.
11. Lin, Z., Wang, Z., Liu, Q., Zhang, X., Liu, J. Narratology meets text-to-image: a survey of consistency in AI generated storybook illustrations. Artificial Intelligence Review, 2025. doi:10.1007/s10462-025-11482-6.
12. Chen, Y.-C. Hierarchical Knowledge Graphs for Story Understanding in Visual Narratives. arXiv:2506.10008, 2025 (v1 was titled "Structured Graph Representations for Visual Narrative Reasoning: A Hierarchical Framework for Comics").
13. Bamman, D., Lewke, O., Mansoor, A. An Annotated Dataset of Coreference in English Literature (LitBank). LREC 2020.
14. ISO/IEC 9075:2011 (SQL:2011) — temporal and bitemporal tables.
15. Richter, J. et al. EARS: An Anechoic Fullband Speech Dataset Benchmarked for Speech Enhancement and Dereverberation. Interspeech 2024.

*(Author lists for 3–12 were taken on 2026-09-27 from the arXiv API, the CVF
open-access page (7) and Crossref (11). Only references 1, 2 and 13 have been
read in full; the rest are cited from their abstracts.)*

## 16. Appendix
- `docs/archive/VALIDATION_BASELINE.md` — starting state and environment
- `docs/results/NER_WINDOWING_RESULT.md` — the adjudicated full-volume re-run
- `docs/results/GOLD_DATASET_README.md` — reference-set provenance and validity
- `docs/results/EVAL_RETRIEVER.md`, `docs/results/SCORER_DIAGNOSIS.md`, `docs/results/BASELINES.md`
- `docs/results/STATE_OF_VALIDATION.md`, `docs/results/SELF_PERSONA_VALIDATION.md`,
  `docs/results/OBSERVER_CONTRAST_VALIDATION.md`
- `docs/paper/PRIOR_ART_LINKKG.md` — full-text verification of LLMLINK and LINK-KG
- `docs/paper/TABLES.md`, `docs/paper/FIGURES.md` — generated from artifacts
- `data/eval/` — every persisted metric, with commit and seed
