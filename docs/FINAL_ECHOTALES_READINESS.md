# EchoTales v1 — final readiness

**2026-09-25; gate re-scored 2026-09-26 after the evidence-upgrade pass**, branch `validation/evidence-pass-2026-09-24` (not pushed).
Canonical database `data/reverend-insanity.db`, sha256 `42107645…`
(`docs/CANONICAL_RUN.md`). 1,085 tests pass (2026-09-26).

Every accuracy figure is scored against the **LLM-DRAFTED SILVER REFERENCE
SET**: drafted by Claude, not human-annotated, no IAA. Per-claim evidence
files are in `docs/FINAL_EVIDENCE_TABLE.md`; what is still missing is in
`docs/REMAINING_WORK.md`.

---

## Readiness gate (2026-09-26)

**Definition of 100%:** every item the project set out to show is either measured on real data with a persisted artifact, or explicitly out of scope, with nothing waiting on work the team could do alone. "WAITING ON HUMAN/IPR" means the team's part is finished and the next step belongs to reviewers, the IPR cell or counsel.

| # | Area | Status | Basis |
|---|---|---|---|
| 1 | ENGINEERING | **DONE** | Pipeline end to end over 199 chapters; 1,085 tests; the A7 stale-appearance cache defect was found and fixed, with regression tests |
| 2 | REPRODUCIBILITY | **DONE** | `scripts/reproduce_results.sh` (now includes A1/A2; A7 and LitBank are documented as explicit slow/ollama steps); canonical DB hash pinned |
| 3 | CORE RESOLUTION | **PARTIAL** | Silver CEAF-e 67.4, B³ P 100, hard cases 24/24 decidable; but 58/88 hard cases are undetected, LOTM is weaker, and transmigration is mis-modelled |
| 4 | OBSERVER STATE | **DONE** (mechanism) / **PARTIAL** (coverage) | A1: 194 → 0 leaks, A2: 14 → 0; 9 mid-chapter under-exposures; witness derivation unvalidated; no witness-level embodiment |
| 5 | MULTIMODAL GENERATION | **PARTIAL** | Observer-conditioned render 5/5 vs 0/5 on one chapter; cache key correct after the fix but over-invalidates (274); no image-quality metric; audio does not consume state |
| 6 | ABLATIONS | **DONE** | A1, A2, A7 plus the existing resolution ablation; negative results reported (digest not observer-causal; over-invalidation) |
| 7 | EXTERNAL VALIDATION | **DONE** (one benchmark), result weak | LitBank, 100 documents, human key: standard CoNLL F1 15.9 (full person key) / 42.4 (names only); not comparable to supervised systems |
| 8 | HUMAN VALIDATION | **WAITING ON HUMAN** | 200 + 88 rows and a protocol prepared; **0 labels**; κ is not computed and is not reported with one reviewer |
| 9 | PATENT / IP | **WAITING ON IPR** | Private packet complete (kept out of this public-tracked file; see Section H); the decision rests with the IPR cell and counsel |
| 10 | PUBLICATION | **PARTIAL** | Experiment table, claim boundaries and venue decision done (workshop/demo first; main track only after human labels); no paper draft yet; sequenced after the IPR decision |
| 11 | SECURITY | **PARTIAL** | `.env` untracked and never committed; no key patterns in tracked files or history; nothing pushed since `6aed9f9`. **The live keys in `.env` were exposed in session transcripts and must be rotated by the owner.** |
| 12 | DOCUMENTATION | **DONE** | EVOLUTION 4.91, experiment docs under `docs/eval/`, evidence matrix (`FINAL_EVIDENCE_TABLE.md` section 6), CLAUDE.md test count fixed |

**Overall:**

| | % | What is missing |
|---|---:|---|
| Engineering | 90 | Observer-scoped persona bindings, a transmigration merge, and less over-invalidation in the digest |
| Research evidence | 65 | Human labels (the single largest gap); witness-derivation precision; multi-chapter render evidence |
| Patent package | 90 | Counsel's reading of the closest patent's full text, and the IPR cell's decision |
| Publication package | 55 | Human labels, a paper draft, and the IPR go-ahead |

---

## A. Verified

Real data, with a persisted artifact:
- End-to-end pipeline over 199 chapters on an 8 GB laptop GPU, with no paid API.
- Entity-level coreference: CEAF-e F1 67.4; B³ precision 100%.
- Hard cases the resolver detects are linked correctly: 24 of 24 decidable, 0 wrong.
- Retrieval given the reference span: recall@10 89.1% (production context).
- Deterministic evidence rules make every link; hard constraints block 3,072 of 16,538 pairs.
- Gazetteer compounding: removing it halves forced links (1,376 → 704).
- Observer-scoped knowledge state: reader 2 / witness 1 / non-witness 0 aliases, and the witness 0 / 1 / 1 asking from ch150 / 166 / 200. Same identity in every query; 6/6 checks pass.
- Observer-conditioned visual generation on a real engine: reader 5/5 conditioned panels, non-reader 0/5.
- Sequential Self/Persona: one Self, two disjoint bodies.
- Read-set-derived cache invalidation: controlled tests, plus the A7 ablation (218 panels). The digest prevents 46 stale reuses; it also over-invalidates 274.
- Observer ablations A1/A2: collapsing the observer yields 194 leaks; removing knowledge time yields 14 (full: 0).
- External LitBank benchmark, human-annotated key: standard CoNLL F1 15.9 / 42.4 (full person key / names only).
- Same-range baseline comparison, cost and coverage.

## B. Partially verified

- **Speaker attribution:** 46.1% of speech spans. Precision only spot-checked. The LLM tier is 12 right / 16 wrong and changed 10 of 29 lines between runs.
- **Generalisation, LOTM ch1–3:** B³ recall 62.3%, CEAF-e F1 41.4. Transmigration is split into two Selves.
- **Typed alias and title bindings:** 11,092 bindings exist, but 16 of 17 annotated title-transfer mentions are never detected.
- **Audio rendering:** 97 lines, 7 voices, no failures. No listening test; attribution errors are audible.

## C. Experimental

- **Learned scorer:** OPTIONAL / EXPERIMENTAL; 0 links, maximum score 0.41 against a 0.80 threshold.
- **LLM attribution tier (ch1–3):** on by default, low precision, unstable across runs.
- **Pronoun speaker recovery:** opt-in (`--recover-pronoun-speakers`); measured 2 of 15 correct.

## D. Not implemented / not evaluated

- **Implemented and tested, never exercised on real data:** retraction (0 rows); facts on a non-main timeline (0); concurrent, possession, body-swap, clone, disguise and dream personas (0 instances).
- **Not implemented:**
  - observer-scoped persona bindings (no writer);
  - aliases in the render read set;
  - audio consuming `state_of` / Persona;
  - a shared multimodal `GenerationState`;
  - a transmigration merge;
  - vocative, relation-graph and title-holder detection.
- **Not evaluated:**
  - human-anchored P/R/F1 and IAA;
  - LINK / NEW / DEFER accuracy and calibration coverage;
  - CLIPScore, identity consistency and image rating;
  - audio MOS and speaker similarity;
  - BOOKCOREF, GraphRAG and CORE-KG (not reproduced here); LitBank was run, see A;
  - GPU time saved or spent by the render cache (A7 is stub-only);
  - LOTM full volume and ORV.

## E. Final benchmark numbers

| Measure | Result | Source |
|---|---|---|
| Silver coreference, 1,816 mentions: MUC / B³ / CEAF-e F1; CoNLL | 97.9 / 97.0 / **67.4**; 87.4 | Table 4 |
| Hard cases, 88: detected; correct / wrong among decidable | 30; **24 / 0** | `hardcase_resolution.json` |
| Hard-case misses, 58: address / relational / title / pronoun / other | 16 / 15 / 11 / 10 / 6 | `hardcase_taxonomy.json` |
| Retrieval Recall@1 / 5 / 10 / 20, n=46, production context | 67.4 / 87.0 / **89.1** / 95.7% | Table 5 |
| Baselines ch1–10, B³ recall: A / B / EchoTales | 0.2% / 4.6% / **78.9%** (1 / 177 / 0 resolution calls) | Table 7 |
| Ablation, 16,538 pairs: force-link / blocked / scorer links | 1,376 / 3,072 / 0 | Table 6 |
| Observer query: reader / witness / non-witness; witness ch150 / 166 / 200 | 2 / 1 / 0; 0 / 1 / 1 | `observer_evidence.json` |
| Observer render: reader / non-reader conditioned panels | 5/5 / 0/5 | `OBSERVER_CONTRAST_VALIDATION.md` |
| Speaker attribution coverage | 46.1% (2,392 / 5,192) | `CANONICAL_RUN.md` |
| LOTM ch1–3: B³ recall; CEAF-e F1 | 62.3%; 41.4 | LOTM results dir |
| A1 / A2 observer ablations: state leaks (full → ablated) | 0 → 194 / 0 → 14 | `observer_ablation.json` |
| A7 cache key: stale reuses without / with the digest; unnecessary regenerations | 46 / 0; 274 | `a7_cache_ablation.json` |
| LitBank (human key, 100 docs): standard CoNLL F1, full / names only | 15.9 / 42.4 | `litbank_results.json` |

## F. Remaining limitations

1. Silver-only evaluation, and most of it is surface-trivial. CEAF-e and the hardcases file are the discriminative measures.
2. Recall is lost at mention detection for vocatives, relational references and definite titles. These need new coreference work, not tuning.
3. The learned component contributes nothing; resolution is rule-driven.
4. One novel at volume scale. The second is weaker, and its central transmigration case is mis-modelled.
5. Speaker attribution is incomplete and its LLM tier is unreliable.
6. Visual evidence is a five-panel mechanism demonstration, not a quality benchmark. Audio does not consume graph state.

## G. Reproducibility instructions

```bash
source .venv/bin/activate && ollama serve &
bash scripts/reproduce_results.sh        # tests, eval, validation, diagnostics, tables, figures
```

It defaults to the canonical database and exited 0 on 2026-09-25. Rebuilding the database from source needs the EPUB, which is copyrighted and not committed; the build order is in `CANONICAL_RUN.md` Section 2.

## H. Patent / invention disclosure status

A prior-art and disclosure due-diligence pass was completed on 2026-09-25. Its results are kept **privately** in `docs/IP/` (gitignored) and handed to the VIT IPR cell. They are deliberately not summarised here, because this file is tracked in a public repository.

What can be stated publicly:
- The public repository (activity from 2026-08-06) already describes the system's core concepts.
- Close third-party prior art exists for most of them.
- Any filing decision rests with the IPR cell.
- **Do not push this branch or post a preprint until that decision is made.** The branch contains implementation not yet public.

## I. Course-report status

`docs/REPORT_MATERIAL.md` covers all 16 sections with canonical-run numbers. `docs/paper/` has 6 generated tables and 4 rendered figures. A private webview screenshot is in `docs/IP/screenshots/`.

**Still needed, all human:**
- author lists for references 3–12;
- each member's own papers and limitations paragraphs;
- team sign-off on Section 7;
- drawing the 7 diagram figures.
