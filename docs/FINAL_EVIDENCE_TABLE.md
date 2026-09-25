# EchoTales v1 — final evidence table

**2026-09-25.** Canonical database `data/reverend-insanity.db` (sha256
`42107645…`, `docs/CANONICAL_RUN.md`). Every accuracy figure is scored against
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
| Scorer | contributes 0 links | Table 6, `SCORER_DIAGNOSIS.md` | no | characterised as OPTIONAL/EXPERIMENTAL |
| Retrieval | 89.1% @10, production context | Table 5 | no | one context used throughout |
| Observer state | demonstrated on real data | `data/eval/observer_evidence.json` | no | persisted artifact and identity test |
| Self/Persona | sequential real; exotic test-only; transmigration mis-modelled | `SELF_PERSONA_VALIDATION.md`, LOTM run | no | LOTM failure documented |
| Retraction / timelines | query semantics tested; 0 real rows | SQL counts below | no | re-counted on canonical database |
| Read-set invalidation | tested; aliases not in read set | `test_readset_invalidation.py` | no | — |
| Multimodal | visual consumes `state_of`; audio does not | `OBSERVER_CONTRAST_VALIDATION.md` | no | documented asymmetry |
| Audio | renders; attribution 46.1%, unstable tier 4 | `data/audio-ears-native/`, EVOLUTION 4.88 | no | sanity check, instability measured |
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
| Retrieval given the reference span | `data/eval/recall_by_category.json`; Table 5 | hardcases, 46 mapped cases, production context | Recall@1 / 5 / 10 / 20 | 67.4 / 87.0 / **89.1** / 95.7% | small-n per type; snippet context gives 84.4% @10 |
| Deterministic rules carry every link | `data/eval/ablation/reverend-insanity.json`; Table 6 | 16,538 cached candidate pairs | links by layer | 1,376 force-links (1,281 gazetteer), 3,072 blocked, scorer 0 | re-scores cached evidence, not a re-resolve |
| Gazetteer compounding | same; Table 6a | same | force-links without compounding | 1,376 → 704 (−49%); gazetteer share 73.5% (w0) → 82.0% (w4) | — |
| Observer-scoped knowledge | `data/eval/observer_evidence.json` | RI, Bai Ning Bing, reveal ch166 | aliases by observer | reader 2 / witness 1 / non-witness 0 | 12 observations total, 3 reveals |
| Knowledge time per observer | same | same witness, asking from ch150/166/200 | aliases | **0 / 1 / 1** | same |
| Same fact, same identity, visibility differs | same (6 checks, all pass); `test_observer_axis.py::test_one_fact_one_identity_visibility_varies` | real + synthetic | identity and read-set checks | pass | — |
| Observer-conditioned visual generation | `OBSERVER_CONTRAST_VALIDATION.md` | ch169, 5 blocks, NoobAI XL | reference-conditioned panels | reader 5/5, non-witness 0/5; keys differ 10/10 | one chapter; cast-change contrast, not two depictions of one person |
| Self/Persona, sequential | `SELF_PERSONA_VALIDATION.md` | RI protagonist | bindings | one Self, two disjoint bodies | one real case |
| Read-set invalidation | `test_readset_invalidation.py` (5 tests) | synthetic | key change on state change | cast change invalidates; offstage does not | aliases are not in the read set |
| Baselines, same range | `data/eval/baseline_comparison.json`; Table 7 | RI ch1–10, 356 silver mentions | calls; B³ recall | A: 1 call, 0.2%; B: 177 calls, 4.6%; EchoTales: 0 resolution calls, **78.9%** | surface-trivial range, so this measures extraction coverage; an earlier table compared against the full-volume 96.3% by mistake |

### PARTIAL

| Claim | Evidence file | Dataset / split | Metric | Result | Limitation |
|---|---|---|---|---|---|
| Generalisation to a second novel | `data/eval/results/lord-of-the-mysteries-1790302402-816d231e/` | LOTM ch1–3, 155 independent silver | B³ R; CEAF-e F1 | 62.3%; 41.4 | 3 chapters; 44/155 undetected; **Zhou Mingrui / Klein split into two Selves**, contrary to the model's own Self/Persona semantics |
| Speaker attribution | `CANONICAL_RUN.md`, EVOLUTION 4.88 | RI, 5,192 speech spans | share attributed | **46.1%** | precision only spot-checked; tier 4 (LLM, ch1–3) 12 right / 16 wrong and not stable across runs (10/29 lines changed) |
| Typed alias bindings incl. title transfer | canonical database | RI | bindings; transfer events | 11,092 bindings; transfer detector fired | 16/17 title-transfer mentions undetected |
| Audio rendering | `data/audio-ears-native/manifest.jsonl` | RI ch1 | lines rendered | 97 lines, 892 s, 7 voices, 0 failures | no listening test; attribution errors audible |

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
- Image quality (CLIPScore, identity consistency, human rating); audio MOS and speaker similarity.
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
