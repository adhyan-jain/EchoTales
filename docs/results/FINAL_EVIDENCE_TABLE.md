# EchoTales v1 — final evidence table

**2026-09-25, v1.1/v1.2 2026-09-27.** Canonical database `data/db/reverend-insanity.db` (v1.2,
content digest `3495ee2901115c1e`; v1.2 changes only eight entity kinds, and its mentions, spans and aliases are
identical to v1.1, so every figure below holds for both; `docs/results/CANONICAL_RUN.md`). Every accuracy figure is scored against
the **LLM-DRAFTED SILVER REFERENCE SET**. It was drafted by Claude models, not
annotated by humans, and has no inter-annotator agreement. No figure below is
a human-gold result.

Status key:
- **VERIFIED**: exercised on real data, with a persisted artifact.
- **PARTIAL**: real data, but incomplete or small-n.
- **TEST-ONLY**: synthetic fixtures only.
- **NOT EVALUATED**: no measurement exists.

---

## 1. Completion matrix

| Area | Current state | Evidence | Blocking? | Action taken this pass |
|---|---|---|---|---|
| Core pipeline | 199 chapters end to end, local GPU | `CANONICAL_RUN.md` | no | rebuilt from scratch, promoted |
| Hard cases | detection-bound; linked cases correct | `data/eval/hardcase_resolution.json`, `hardcase_taxonomy.json` | no | taxonomy built, one structural bug fixed |
| Scorer | contributes 0 links | Table 6, `EXPERIMENT_RESULTS.md` (scorer diagnosis) | no | characterised as OPTIONAL/EXPERIMENTAL |
| Retrieval | 89.1% @10, production context | Table 5 | no | one context used throughout |
| Observer state | demonstrated on real data | `data/eval/observer_evidence.json` | no | persisted artifact and identity test |
| Self/Persona | sequential real; exotic test-only; transmigration mis-modelled | `EXPERIMENT_RESULTS.md` (self/persona), LOTM run | no | LOTM failure documented |
| Retraction / timelines | query semantics tested; 0 real rows | SQL counts below | no | re-counted on canonical database |
| Read-set invalidation | tested; aliases not in read set | `test_readset_invalidation.py` | no | — |
| Multimodal | visual consumes `state_of`; audio does not | `ABLATIONS.md` (observer contrast) | no | documented asymmetry |
| Audio | renders; attribution 46.1%, unstable tier 4 | `data/novels/RI/audio-runs/ears-native/`, EVOLUTION 4.88 | no | sanity check, instability measured |
| Baselines | same-range comparison | Table 7 | no | re-scored on canonical database |
| Human gold / IAA | none, by owner decision | — | **yes, for human-anchored claims** | none possible without annotators |
| Generalisation | LOTM ch1–3 only, weaker | LOTM results dir | partial | measured, documented |

## 2. Evidence table

### VERIFIED

| Claim | Evidence file | Dataset / split | Metric | Result | Limitation |
|---|---|---|---|---|---|
| Full volume processes end to end on local hardware | `CANONICAL_RUN.md` Section 2 | RI ch1–199 | wall time, stages | 553 s pipeline (NER cached); 47 min cold | one novel at volume scale |
| Coreference, entity-level | `data/eval/results/reverend-insanity-1790342230-8ff45048/metrics.json`; Table 4 | RI silver, 1,816 mentions | CEAF-e P / R / F1 | 89.8 / 53.9 / **67.4** | silver; set is surface-trivial, so MUC/B³ (97.9 / 97.0 F1) mostly measure string matching |
| Precision is never traded away | same | same | B³ precision | 100.0% | silver; recall is where the misses are |
| Resolver links detected hard cases correctly | `data/eval/hardcase_resolution.json` | 88 hardcases records | correct / wrong among detected, decidable | **24 / 0** (6 undecidable) | n=24; Wilson 95% lower bound ≈ 86% |
| Hard cases are lost at detection | same; `hardcase_taxonomy.json` | same | undetected (overlap alignment) | **58 / 88** | see taxonomy (Section 3) |
| Retrieval given the reference span | `data/eval/recall_by_category.json`; Table 5 | hardcases, 46 mapped cases, production context | Recall@1 / 5 / 10 / 20 | 67.4 / 84.8 / **89.1** / 95.7% | small-n per type; snippet context gives 84.4% @10 |
| Deterministic rules carry every link | `data/eval/ablation/reverend-insanity.json`; Table 6 | 16,538 cached candidate pairs | links by layer | 1,376 force-links (1,281 gazetteer), 3,072 blocked, scorer 0 | re-scores cached evidence, not a re-resolve |
| Gazetteer compounding | same; Table 6a | same | force-links without compounding | 1,376 → 704 (−49%); gazetteer share 73.5% (w0) → 82.0% (w4) | — |
| Observer-scoped knowledge | `data/eval/observer_evidence.json` | RI, Bai Ning Bing, reveal ch166 | aliases by observer | reader 2 / witness 1 / non-witness 0 | 12 observations total, 3 reveals |
| Knowledge time per observer | same | same witness, asking from ch150/166/200 | aliases | **0 / 1 / 1** | same |
| Same fact, same identity, visibility differs | same (6 checks, all pass); `test_observer_axis.py::test_one_fact_one_identity_visibility_varies` | real + synthetic | identity and read-set checks | pass | — |
| Observer-conditioned visual generation | `ABLATIONS.md` (observer contrast) | ch169, 5 blocks, NoobAI XL | reference-conditioned panels | reader 5/5, non-reader 0/5; keys differ 10/10 | one chapter; cast-change contrast, not two depictions of one person |
| Self/Persona, sequential | `EXPERIMENT_RESULTS.md` (self/persona) | RI protagonist | bindings | one Self, two disjoint bodies | one real case |
| Read-set invalidation | `test_readset_invalidation.py` (5 tests) | synthetic | key change on state change | cast change invalidates; offstage does not | aliases are not in the read set |
| Baselines, same range | `data/eval/baseline_comparison.json`; Table 7 | RI ch1–10, 356 silver mentions | calls; B³ recall | A: 1 call, 0.2%; B: 177 calls, 4.6%; EchoTales: 0 resolution calls, **78.9%** | surface-trivial range, so this measures extraction coverage; an earlier table compared against the full-volume 96.3% by mistake |

### PARTIAL

| Claim | Evidence file | Dataset / split | Metric | Result | Limitation |
|---|---|---|---|---|---|
| Generalisation to a second novel | `data/eval/results/lord-of-the-mysteries-1790302402-816d231e/` | LOTM ch1–3, 155 independent silver | B³ R; CEAF-e F1 | 62.3%; 41.4 | 3 chapters; 44/155 undetected. **Fixed 2026-09-27** (name order + transmigration merge, EVOLUTION 4.95): the same ch1–20 database re-resolved scores B³ R **74.6**, CEAF-e F1 **43.3**, precision unchanged (`data/eval/results/lord-of-the-mysteries-1790467690-5ed86f9a/`); Zhou Mingrui, Klein Moretti and Klein are one Self |
| Speaker attribution | `CANONICAL_RUN.md`, EVOLUTION 4.88 | RI, 5,192 speech spans | share attributed | **46.1%** | precision only spot-checked; tier 4 (LLM, ch1–3) 12 right / 16 wrong and not stable across runs (10/29 lines changed) |
| Typed alias bindings incl. title transfer | canonical database | RI | bindings; transfer events | 11,092 bindings; transfer detector fired | 16/17 title-transfer mentions undetected |
| Audio rendering | `data/novels/RI/audio-runs/ears-native/manifest.jsonl` | RI ch1 | lines rendered | 97 lines, 892 s, 7 voices, 0 failures | no listening test; attribution errors audible |

### TEST-ONLY

| Claim | Evidence | Real-data count on canonical database |
|---|---|---|
| Retraction distinct from interval end | `test_state.py::TestRetractionVersusIntervalEnd` (4 tests) | `retracted_chapter IS NOT NULL`: **0** rows; the writer has no production caller |
| Facts on non-main timelines | `test_state.py` timeline tests | alias bindings off `MAIN_TIMELINE`: **0**; persona bindings: **0** |
| Concurrent embodiment, possession, body-swap, clone, disguise, dream persona | `test_state.py` classes | **0** instances in the corpus |

### NOT EVALUATED

- Human-anchored P/R/F1 and IAA (owner decision: no human annotation).
- Learned-scorer benefit: nothing is left for it to decide (0 labelled pairs reach it).
- LINK / NEW / DEFER decision accuracy and held-out calibration coverage.
- Image quality (identity consistency, human rating); audio MOS and speaker similarity. Prompt-image alignment is now measured: CLIPScore, current RI render 77/87 panels match their own prompt better than another panel's (`CLIPSCORE.md`).
- BOOKCOREF / LitBank, GraphRAG / CORE-KG: **not directly comparable / not reproduced in this evaluation**.
- LOTM full volume, ORV.

## 3. Hard-case failure taxonomy

`data/eval/hardcase_taxonomy.json`: the 58 hard cases still undetected, by rule.

| Mode | n | Fix class |
|---|---:|---|
| address-term ("senior brother", "young landlord") | 16 | research: vocative coreference |
| relational ("his uncle", "his master") | 15 | research: needs a persistent relation graph; the kinship resolver binds only with apposition or in-scene establishment, by design (precision over recall) |
| definite-title ("the clan leader", "the previous landlord") | 11 | research: title-holder resolution at a story position |
| pronoun | 10 | by design: pronouns are never graph mentions |
| gold-span defect (clause-length surface) | 2 | annotation issue, left unedited |
| rigid-name ("Gu Yue" as the founder, "First gen Gu Yue") | 2 | research: a clan name used as a person |
| possessive-np | 1 | annotation boundary |
| annotation control record | 1 | the known contract-violating record |

**Fixed this pass:** "Wang Er", an NER-tagged name that was dropped from all 199 chapters by the commonness filter's demonstrative rule (EVOLUTION 4.90). Recovered: hardcases ch175@8342 (`disguise`), plus 7 silver "Mother Shen" mentions. No regression in precision.

## 4. Resolution layers, measured

| Layer | Role | Share of decisions (16,538 pairs) |
|---|---|---|
| Hard constraints (co-presence block, temporal gate) | veto a link | 3,072 blocked (18.6%); the temporal gate changes 0 |
| Deterministic evidence rules (gazetteer, declaration, name containment, relational co-presence) | force a link | 1,376 (8.3%): **every link made** |
| Retrieval | candidate generation | Recall@10 89.1% given the span |
| Learned scorer | optional ranking and threshold | 12,090 pairs reach it; **0 links**; max score 0.41 against a 0.80 threshold. **OPTIONAL / EXPERIMENTAL** |

## 5. Prior-art status (paper-side summary)

The paper-side comparison is `docs/paper/RELATED_WORK_FINAL.md` and `CONTRIBUTION_MATRIX.md`. In short:
- observer-scoped knowledge, time-scoped narrative state, incremental resolution and state-driven story visualisation are all crowded research areas;
- EchoTales' distinction is the pairing of time- and observer-scoped *identity* with generation, and its empirical findings.

The patent-side analysis is private (`docs/private/IP/`, not tracked).

## 6. Causal evidence matrix (evidence-upgrade pass, 2026-09-26)

Reference types:
- **silver**: the LLM-drafted reference set.
- **system records**: the system's own observation records.
- **external-human**: LitBank's human annotation.
- **controlled**: synthetic or stub experiments.

| # | Claim | Mechanism | Ablation / baseline | Result | Dataset | Reference type | Evidence file | Status | Limitation |
|---|---|---|---|---|---|---|---|---|---|
| C1 | Observer knowledge changes what an observer can resolve | `state_of(observer, knowledge_pos)` with observation records | A1: observer → READER; A2: knowledge time removed | 228 queries: FULL 0 leaks, A1 **194**, A2 **14** | RI canonical, 3 reveal events | system records | `docs/results/ABLATIONS.md`, `A2_…` | **SUPPORTED** | Only 3 events / 2 facts; leak is defined against the system's own records; 9 FULL under-exposures from mid-chapter reveals |
| C2 | Observer-conditioned state changes generated media | render plan built from observer-conditioned `state_of` | A1 at the render-plan level; real-engine contrast | A1: 194 render plans draw an identity FULL withholds; real engine: reader 5/5 vs non-reader 0/5 | RI ch169 (render); 3 reveals (plans) | controlled + real engine | A1 doc; `ABLATIONS.md` (observer contrast) | **SUPPORTED, reader vs non-reader only** | No character observer is ever drawn (READER-scoped persona bindings), so witness-level rendering is **not supported** |
| C3 | The cache key separates state-dependent artifacts | `state_digest` (drawn persona + attributes, persona ids, Self attributes) inside the render key | A7: full key vs digest removed (B) vs all state-derived parts removed (C), with prompt/plan/seed held fixed | Fixed key: 0 stale reuses on every event; without the digest, **46** stale reuses (E1, E1b). The shipped key had served those 46 stale too; now fixed | 218 panels, 5 chapters | controlled | `docs/results/ABLATIONS.md`, `data/eval/a7_cache_ablation*.json` | **SUPPORTED after a fix found by this experiment** | Aliases are not in the key; reference bytes are not hashed; stub engine |
| C4 | Artifacts whose dependencies do not change are reused | cache lookup by key | A7 E0 / E2 / E5 | 218/218 reused under every condition; **274 unnecessary** regenerations on non-drawn changes (E3, E6) | same | controlled | same | **PARTIAL**: reuse holds, but the digest over-invalidates | GPU saving only estimated (22 s/panel); no measured compute effect |
| C5 | Removing observer state increases information leakage | as C1 | A1, A2 | +194 (A1) and +14 (A2) leaks | as C1 | system records | as C1 | **SUPPORTED** (same caveats as C1) | Whether the records themselves are right needs human review |
| C6 | Resolves long-span identity better than the tested simple baselines | deterministic evidence resolution with a compounding gazetteer | long-context LLM; two-LLM memory (ch1–10) | B³ recall 78.9% vs 0.2% / 4.6%, at 0 resolution calls | RI ch1–10, 356 mentions | silver | Table 7 | **SUPPORTED on silver, as extraction coverage** | Surface-trivial range; on human-annotated LitBank the name-level CoNLL F1 is 42.4 (standard) and recall is limited by detection |

**External human-annotated check** (LitBank, 100 documents, zero-shot):
- Full person key: CoNLL F1 **15.9**.
- Proper-name mentions: **42.4** (standard scoring) / 46.7 (key-restricted).
- Name-link precision: MUC 99.0, B³ 99.7 (key-restricted).
- Not comparable to LitBank's supervised 68.1 (`docs/results/EXPERIMENT_RESULTS.md`).

**Human validation:** the package is prepared (200 + 88 rows), with **no labels**. κ is not computed.
