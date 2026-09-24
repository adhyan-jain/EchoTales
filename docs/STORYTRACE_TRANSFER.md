# StoryTrace → EchoTales pattern transfer

**Written 2026-09-25.** Records which engineering patterns from
`adhyan-jain/StoryTrace` were considered for EchoTales, what was adopted, and
what was deliberately not. **No StoryTrace code was copied**, and no StoryTrace
research claim is made here: the two projects share temporal state as a theme,
which is not a basis for merging their contributions.

| Pattern | StoryTrace source | Outcome in EchoTales | Research-claim impact |
|---|---|---|---|
| Bounded evidence-grounded investigator | `backend/v2/agent/investigator.py` (`max_calls = 6`, `FinalVerdictV2` with `verbatim_evidence_quotes`) | **Not transferred — ruled out by measurement** | None |
| Reproducible evidence traces | investigator step traces; `scripts/v2/audit_investigator.py` | **Adapted** as per-case and per-candidate diagnosis tables | None — methodology only |
| Adversarial evaluation structure | `tests/v2/test_investigator.py`, `backend/eval/pipeline_only_investigator.py` | **Adapted** as in-cast vs offstage controls and best-wrong-candidate margins | None — methodology only |
| Provenance enforcement | verdicts carry their quoted source spans | **Already present** in EchoTales (`gold.py` `CIRCULAR_DRAFTERS`, `SILVER_BANNER`); nothing to transfer | None |
| Append-only evidence history | event history | **Already present** (`resolution_event`, append-only `EVOLUTION.md`) | None |

---

## 1. Bounded investigator — considered, not transferred

**StoryTrace pattern.** An LLM agent investigates one ambiguous candidate
under a hard call budget, using tools over an evidence store, and returns a
verdict with verbatim quotes and step-by-step reasoning.

**Proposed adaptation.** Route only DEFER-band identity decisions to a bounded
investigator with Store-backed tools (source window, alias history,
co-presence, reveal/transfer events), a six-call budget, and a recorded trace.

**Why it was not built** (`docs/SCORER_DIAGNOSIS.md`):
1. **No labels where it would operate.** Every labelled gold candidate in the
   silver corpus is decided by a pre-filter (101 FORCE_LINK, 2 BLOCK, 0 SCORE),
   so "accuracy before and after investigation" cannot be measured.
2. **The hard cases never reach it.** 59 of 89 hard cases are lost at mention
   detection, before any candidate list exists for an investigator to examine.
3. **The deferral band is nearly empty.** 2 deferrals across 1,532 groups.

Adding it would have been architecture built to make a documentation claim
true, which the completion plan forbids. It remains the right design **if** a
later pass supplies labels in the scorer's operating region and repairs
detection for relational and title spans.

## 2. Reproducible evidence traces — adapted

StoryTrace records every piece of evidence an investigation consulted.
EchoTales adapts the principle, not the code: `scripts/scorer_diagnosis.py`
writes `data/eval/scorer_diagnosis/cases.csv` (per gold mention: rank, score,
best-wrong score, margin, pre-filter verdict, outcome) and `candidates.csv`
(all eleven evidence features per scored pair), so every conclusion in the
diagnosis can be re-derived row by row. **Files:** `scripts/scorer_diagnosis.py`,
`scripts/scorer_fit_probe.py`. **Tests:** none (read-only analysis scripts;
their outputs are committed).

## 3. Adversarial evaluation — adapted

StoryTrace evaluates a detector against constructed counter-cases. Two
EchoTales evaluations take the same shape:
- **Read-set invalidation** tests a change that *should not* invalidate
  (an offstage character) alongside one that should
  (`packages/pipeline/tests/test_readset_invalidation.py`, 5 tests).
- **Scorer diagnosis** measures each gold candidate against its strongest
  wrong competitor (margin), not just in isolation.

## 4. Explicitly not imported
ClickHouse storage, the closed-world possession/injury state grammar,
screenplay-specific parsing, and StoryTrace's continuity-checking thesis. No
EchoTales requirement justifies any of them.
