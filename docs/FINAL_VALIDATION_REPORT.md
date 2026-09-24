# Final validation report — 2026-09-24 evidence pass

Branch `validation/evidence-pass-2026-09-24`, cut from `6aed9f9`.
Baseline: `docs/VALIDATION_BASELINE.md`. Suite **1,051 passed** (was 1,038).

---

## 1. Executive summary

The pass set out to make EchoTales defensible for a research evaluation, an
invention disclosure, and a university report. Five things happened that
change the project's evidentiary position.

1. **The top blocker was a misdiagnosis.** Every document recorded the
   measuring re-run as blocked because "ollama is unreachable from a sandboxed
   shell." The daemon was not running. `ollama serve` brought it up in **one
   second**, and the run that "gates the most" completed in 47 minutes.
2. **The re-run's pre-registered prediction was adjudicated, and one third of
   it is refuted.** CEAF-e recall and speaker attribution improved as
   predicted; "mentions roughly double" did not (+14.6%). The fix finds
   **entities** (82 → 261, +218%), not mentions.
3. **The project's gold sets are surface-trivial**, which re-condemns the
   already-retracted headline from a second, independent direction. Scoring
   the *non-circular* silver subset still returns exactly P=100.0/R=94.6/
   F1=97.2, because 1,816 mentions span only **23 distinct surfaces**.
4. **The scorer's last defence is closed.** With the pipeline no longer blind
   to half of every chapter and a 57% larger evidence cache, the learned
   scorer still settles **zero** links under every ablation condition.
5. **Baseline A ran for the first time** and recovers **10 of 356** gold
   mentions over ten chapters — recall **0.2%**.

---

## 1b. Session 2 (2026-09-25) — what changed

| Item | Before | Now |
|---|---|---|
| Observer-conditioned **generation** | "wired, never exercised" | **Demonstrated end to end on a real image engine** (`docs/OBSERVER_CONTRAST_VALIDATION.md`): same chapter/blocks/checkpoint/seed, only the observer varies — READER gets 5/5 reference-conditioned panels naming `Bai Ning Bing`; a non-witness gets 5/5 prompt-only panels saying `a figure`, and `1boy … solo` instead of `2boys`. Cache keys and pixels differ on 10/10 blocks. Also demonstrated at the plan level: Same panel, varying only the observer: READER yields `characters=1`, digest `de02bdbf…`; a non-witness yields `characters=0`, digest `3ce24425…`. `cache_key.py` derives the artifact key from that digest, so the observer changes what would be generated *and* cached. |
| Real image engine | never run | **Run.** NoobAI XL produced a 1.59 MB panel for ch169 under a real observer parameter — not a stub. |
| LLMLINK prior art | unread, carrying the positioning weight | **Verified against the full paper.** All four claims hold, and unlike LINK-KG the negatives are substantive: same task, same data class (LitBank, DOC-ARC), same metrics (MUC/B³/CoNLL), and it still models identity as static. |
| Self/Persona on real data | asserted | **Bounded.** One real case (Fang Yuan, two temporally disjoint bodies); five case classes are tests-only with row counts. |
| `--compose-engine stub` | believed working | **Was broken.** `StubComposeEngine` lacked the `speed` field `cmd_render` passes, so the CI/no-GPU path raised `TypeError`. Fixed, with a dataclass-parity test. |
| Persona bindings after a re-resolve | assumed durable | **`resolve` deletes them.** `resolve/runner.py:832` drops every binding for the novel. Running it after `run` silently emptied all 92, which empties every render plan three stages later. |

### Two defects found by doing, not by reading

1. **The stub compose path had never worked since `speed` was added.** It
   crashed *after* generating 100 panels, which is the worst place to fail.
   Nothing caught it because no test built both engines from one kwarg set.
2. **`resolve` is destructive to persona state and says so nowhere.** The
   symptom (generic prompts, no character identity in any panel) appears three
   stages downstream and looks nothing like the cause. Documented in
   `docs/RUNPOD_MIGRATION.md` Section 4, because on a rented GPU it costs the
   whole session.

### A gap the observer work exposed

All 92 `self_persona_binding` rows carry `observer_id = READER`, so a witness
to a reveal learns the **alias** but cannot resolve the **persona** — a
witness-conditioned render drops the character rather than depicting them with
partial knowledge. `detect_observations.py` writes alias observations only.
The binding row already has an `observer_id` column; it has no writer.

---

## 2. What is verified

Each row has a reproducible command behind it.

| Claim | Evidence |
|---|---|
| NER truncation repaired, effect measured | `docs/NER_WINDOWING_RESULT.md`; full volume, 47 min, 660 calls |
| Entity inventory tripled | 82 → **261**; entity typing 64 unknown → **0 unknown** |
| Bai Ning Bing recovered at the predicted offsets | ch1 mentions `[]` → `[6697, 6814, 8757]`, matching gold exactly; first appearance ch108 → **ch1** |
| CEAF-e entity clustering roughly doubled | recall **25.2% → 48.9%**, F1 38.8% → 63.1%, same gold and scorer |
| Speaker attribution improved | identifiability **48.8% → 63.0%**; `TURN_TAKING` (82.9% wrong) eliminated |
| Contradiction detector fires on real data | 0 hits on 60 chapters → **50 contradictions → 50 splits** |
| Observer-conditioned **query** | READER 2 / witness 1 / non-witness 0, on a freshly resolved volume |
| **Knowledge-time axis** (new) | same witness: **0** aliases at ch150, **1** at ch166, **1** at ch200 |
| Scorer is inert | `scorer-would-link = 0` across all 8 conditions over **15,796** pairs |
| Gazetteer carries the system | disabling it drops force-links 1,318 (8.3%) → 448 (2.8%) — **66% of all links** |
| Temporal blocking is inert | `no-temporal-scoping` changes nothing; all 2,888 blocks are co-presence |
| Escalation rate | 660 calls, **0 escalations**, 2 deferrals (0.1%) of 1,532 groups |
| Prior art verified | `docs/PRIOR_ART_LINKKG.md` — four claims confirmed against the full paper |
| Baseline A executed | 1 call, 24,302 prompt tokens, 146 s, **recall 0.2%** |

## 3. What improved

- Entity inventory +218%; entity typing complete.
- CEAF-e recall +94% relative; CoNLL F1 78.1 → 86.5.
- Speaker identifiability +29% relative.
- Contradiction detection from zero signal to 50 real cases.
- Retriever TRANSFERABLE_TITLE recall@10 66.7% → **77.8%**.
- Evidence cache 10,058 → 15,796 pairs (+57%).

## 4. What did not improve

- **Mentions per chapter: +14.6%**, against a predicted doubling.
- **`RELATIONAL_DEICTIC` recall@10: 25.0% → 25.0%.** Unmoved, and the weakest
  part of the system by a wide margin (n=4; directional only).
- **The retriever gate still FAILS** — 77.8% against an 80% threshold. *(Superseded 2026-09-25: 88.9% with production-exact context, gate passes by one case at n=9; `docs/EVAL_RETRIEVER.md` Section 6.)*
- **The learned scorer still links nothing**, on 57% more evidence.
- **Confirmed gold: still 0 records**, by owner decision this pass.

## 5. Negative findings

Recorded because they are results, not failures.

1. **Surface triviality.** `reverend-insanity.jsonl` (silver subset) and
   `reverend-insanity-c1-c5.jsonl` are **100% recoverable by grouping on the
   surface string**. Any exact-string matcher reproduces them. Every B³/MUC
   number from them is a tautology. `reverend-insanity-hardcases.jsonl`
   (63.6%) is the **only** evaluation set in the corpus that measures
   anything, and it is 89 records.
2. **The gold key was silently destroying annotations.** `(novel, chapter,
   offset)` let a word-boundary prefix surface overwrite the longer surface it
   prefixes — **55 of c1-c5's 343 records (16%) died at load time**, passing CI
   for six weeks.
3. **770 spans in the circular tier are shifted by exactly +1** (all
   `gold-auto-builder`, all ch61-199). The silver tier is clean.
4. **The retraction writer has zero callers.** `retracted_chapter IS NOT NULL`
   is **0 rows across all 27 databases**.
5. **"Concurrent" Self/Persona binding is unit-tests-only.** 0 personas bound
   to >1 self, 0 non-MAIN-timeline bindings, 0 `FABRICATED` aliases anywhere.
6. **`GenerationState` does not exist.** The visual path consumes the graph
   query; the **voice path never calls `state_of` or touches `Persona`**.
7. **The evaluation harness could not emit a number**, for three mechanical
   reasons: no `--gold` flag, recall@k gated behind always-empty `confirmed`,
   and the evaluation retriever built with empty context (zeroing the
   contextual half of its own blend).
8. **LINK-KG is mispositioned in `plans.md`.** It is a legal-document system
   scored on node-duplication rates. **LLMLINK** is the real comparable.

## 6. Core metrics

Silver tier, `reverend-insanity.jsonl`, same gold and scorer on both sides.
**Section 5.1 applies: B³/MUC here are tautological and must not be quoted as
accuracy.**

| Metric | pre-fix | post-fix |
|---|---:|---:|
| B³ P / R | 100.0 / 95.4 | 100.0 / 96.3 |
| MUC F1 | 97.9 | 98.4 |
| **CEAF-e P / R / F1** | 84.1 / **25.2** / 38.8 | 89.0 / **48.9** / **63.1** |
| CoNLL F1 | 78.1 | **86.5** |

Retriever, hardcases silver set (the non-trivial one), post-fix:

| Alias type | n | @1 | @10 | @20 |
|---|---:|---:|---:|---:|
| Overall | 45 | 62.2% | 77.8% | 91.1% |
| RIGID_NAME | 31 | 77.4% | 83.9% | 96.8% |
| TRANSFERABLE_TITLE | 9 | 33.3% | **77.8%** (gate FAIL; 88.9% and PASS with production context, see EVAL_RETRIEVER Section 6) | 100% |
| RELATIONAL_DEICTIC | 4 | 0.0% | 25.0% | 25.0% |

## 7. Baseline results

| | Baseline A | Baseline B | EchoTales |
|---|---:|---:|---:|
| Architecture | long-context, 1 call/section | dual-LLM memorisation | graph + gazetteer |
| **LLM calls** | **1** | **177** (43 extract + 134 link) | ~30 NER, **0** resolution |
| Prompt tokens | 24,302 | 142,835 | — |
| Wall time | 146 s | 435 s | — |
| **Mentions found (ch1-10)** | **10** | **133** | **359** |
| B³ precision | 100.0% | 95.4% | 100.0% |
| **B³ recall** | **0.2%** | **4.6%** | 96.3% |

Silver gold for ch1-10 holds 356 mentions. Both baselines ran 2026-09-24, same
model, same host, same scorer.

Baseline A's failure mode is **output budget, not comprehension**: 24,302
prompt tokens left roughly 8k of headroom and it emitted 697 tokens containing
ten mentions. Baseline B's chunked extractor fixes exactly that — **13× more
mentions** — and pays **177× the calls** for it.

**On this corpus the recall column is an extraction-coverage comparison, not a
coreference-quality one.** EchoTales' 96.3% is measured against gold that is
100% recoverable by grouping on the surface string; the baselines are
handicapped on the same axis in the opposite direction, having to find a
mention before they can match it.

## 8. Ablation results

15,796 cached pairs, post-fix:

| Condition | force-links | reached scorer | scorer would link |
|---|---:|---:|---:|
| full | 1,318 (8.3%) | 11,590 | **0** |
| no-gazetteer-compounding | 448 (2.8%) | 12,460 | **0** |
| no-temporal-scoping | 1,318 (8.3%) | 11,590 | **0** |
| no-copresence-blocking | 1,329 (8.4%) | 14,467 | **0** |
| no-prefilters-at-all | 0 (0.0%) | 15,796 | **0** |

**This settles `COMPLETION_PLAN`'s A/B/C/D/E question.** Hypothesis (A),
retrieval starvation, was the scorer's remaining defence and is now **refuted
as the explanation**: starvation was real, it is fixed, and the scorer's
inertness survived it. The answer is **B+C+D** — the evidence features cannot
express the decision, the hard rules carry all 1,318 links (93% gazetteer),
and the scorer is unnecessary to this corpus as built.

## 9. Multimodal demonstration status

**COMPLETE for the observer contrast** (`docs/OBSERVER_CONTRAST_VALIDATION.md`).
Run 2026-09-25, local RTX 4060, NoobAI XL, 5 panels per observer, everything
held constant but the observer:

| | READER | non-witness |
|---|---:|---:|
| Reference-conditioned panels | **5** | **0** |
| Prompt-only panels | 0 | **5** |
| Cache key / pixels differ | 10/10 blocks | — |

The prompt names the character for one observer (`Bai Ning Bing`) and not the
other (`a figure`), and the cast count differs (`2boys` vs `1boy … solo`)
because the non-witness does not have her in their scene at all. That is a
property of the graph query, not of two authored prompts.

**Still open:** a two-*depiction* contrast (both observers see a character,
but a different one) needs a sustained disguise, which RI does not contain;
and no rendered pixel has been scored, so nothing here claims image quality.

## 10. Remaining blockers

| Blocker | Nature |
|---|---|
| Baseline B result | Running at time of writing; unfinished, not blocked |
| CLIPScore pixel QA | Real — needs a ~1.7 GB model download |
| Observer-contrast figures | Needs an idle GPU (~1 h) |
| Confirmed gold | Owner decision: not being created; silver used instead, labelled |
| LLMLINK paper unread | Now the primary positioning target; verify before filing |
| `RELATIONAL_DEICTIC` retrieval | 25% recall@10 — the sharpest open research problem |

## 11. Patent-relevant technical features

Status after this pass. `docs/IP/invention_disclosure.md` is corrected in
place and stays gitignored.

| Mechanism | Status |
|---|---|
| Self/Persona split | Implemented; **sequential** reincarnation on real data. **Concurrency is unit-tests-only** — downgraded |
| Observer-scoped knowledge time | **Strongest claim.** Both axes now demonstrated on real data |
| `retract` vs `close_interval` | Query semantics tested; **writer has zero callers** — downgraded, not reduced to practice |
| Fuzzy-interval partial-order story time | Implemented; **no fact is ever on a non-MAIN timeline** |
| Graph-conditioned render + state-derived cache key | Wired, stub-mode only |
| Observer-conditioned generation | Query half real; **generation half never run against a real engine** |
| Shared multimodal compiler | **Does not exist** — visual only; audio bypasses `state_of` entirely |

## 12. Paper-relevant contributions

1. **A measured, pre-registered, partially-refuted repair.** The prediction was
   recorded before the run and one third of it is wrong in print.
2. **Surface triviality as an evaluation-design finding.** A gold set
   reproducible by string grouping cannot measure a resolver — with a corpus
   demonstration and an automated check.
3. **A negative result on learned scoring**, robust to the starvation
   confound across 15,796 pairs.
4. **Observer- and knowledge-time-scoped identity**, demonstrated on real data
   on both axes.
5. **Cost asymmetry**: zero LLM calls at resolution against O(sections) and
   O(mentions) baselines.
6. **A gazetteer-compounding measurement** reported with its denominators.

## 13. Exact next steps

1. Finish Baseline B; record it in `docs/BASELINES.md` Section 4.
2. Run the observer-contrast render on the idle GPU (item 18) — the one figure
   nothing else can produce.
3. Read LLMLINK; it now carries the positioning weight.
4. Attack `RELATIONAL_DEICTIC` retrieval (25% @10), not the scorer.
5. Adjudicate the two flagged hardcases records (`GOLD_DATASET_README.md` Section 5).
6. Build the figure/table generation scripts; no paper artifact exists yet.

---

```
==========================
ECHOTALES READINESS MATRIX
==========================

Research contribution:        PARTIALLY VERIFIED
Patent technical disclosure:  NEEDS EVIDENCE (close)
Academic project report:      NEEDS RESULTS
End-to-end product:           PARTIAL
Gold evaluation:              IN PROGRESS
Baseline comparison:          COMPLETE (both executed)
Multimodal demonstration:     COMPLETE (observer contrast, real engine)
```

**Research contribution — PARTIALLY VERIFIED.** Verified: the NER repair and
its adjudicated prediction (`docs/NER_WINDOWING_RESULT.md`), the scorer
negative result over 15,796 pairs, the observer and knowledge-time axes
(`docs/STATE_OF_VALIDATION.md`), the gazetteer's 66% share. Not verified: any
accuracy claim anchored to human judgement, and the central visual ablation.

**Patent technical disclosure — NEEDS EVIDENCE, and it is close.** The
document exists, its blocking prior-art item is closed
(`docs/PRIOR_ART_LINKKG.md`), and three over-claims are corrected in place.
Remaining: LLMLINK unread; the generation half of the strongest claim has
never run against a real engine.

**Academic project report — NEEDS RESULTS.** Source material now exists for
methodology, dataset, related work, results and limitations. **No figure or
table generation script exists**, and most of the required 16-section
structure is unwritten.

**End-to-end product — PARTIAL.** Render and voice run; `docs/STATUS.md`'s
component matrix is the authority and is unchanged by this pass.

**Gold evaluation — IN PROGRESS.** Validator built and run corpus-wide, three
real defects found, key fixed, silver tier defined and labelled. Zero
human-confirmed records, by decision.

**Baseline comparison — IN PROGRESS.** Baseline A executed for the first time;
Baseline B built and running.

**Multimodal demonstration — MISSING.** No observer-contrast render exists.
