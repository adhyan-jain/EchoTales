# EchoTales API Annotation Pilot Report

**Date**: 2026-10-13  
**Status**: Pilot complete (10/10 rows); schema validated; budget strictly verified ($0.000984 actual cost); pipeline ready for scaling.  

---

## 1. Files & Code Paths Inspected

- **Research Context & Decisions**:
  - [`docs/research/ECHOTALES_NEXT_RESEARCH_DECISION.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_NEXT_RESEARCH_DECISION.md)
  - [`docs/research/ECHOTALES_NOVELTY_LEDGER.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_NOVELTY_LEDGER.md)
  - [`docs/research/ECHOTALES_SOURCE_INVENTORY.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/ECHOTALES_SOURCE_INVENTORY.md)
  - [`docs/paper/PUBLICATION_READINESS.md`](file:///home/adhyan/Desktop/EchoTales/docs/paper/PUBLICATION_READINESS.md)
- **Review Protocol & Sheets**:
  - [`docs/results/HUMAN_REVIEW_PROTOCOL.md`](file:///home/adhyan/Desktop/EchoTales/docs/results/HUMAN_REVIEW_PROTOCOL.md): Defines exact label set (`correct`, `incorrect`, `unresolved`), column layout, and 1-sentence note requirement.
  - [`data/eval/human_review_200.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/human_review_200.csv): 200 stratified mention rows across 7 strata (`easy_name`, `alias`, `title`, `relational`, `unresolved_name`, `observer_sensitive`, `background`).
  - [`data/eval/human_review_hardcases_88.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/human_review_hardcases_88.csv): 88 silver hard-case entity shifts.
  - Zero sample ID or text overlap verified between the two files (288 unique items).
- **Implementation & Tests**:
  - [`scripts/review/prepare_human_review.py`](file:///home/adhyan/Desktop/EchoTales/scripts/review/prepare_human_review.py): Generator script for review sheets.
  - [`scripts/review/llm_annotate.py`](file:///home/adhyan/Desktop/EchoTales/scripts/review/llm_annotate.py): Structured annotation engine with batching, untrusted text delimiters, JSON schema validation, checkpointing, and cost tracking.
  - [`packages/pipeline/tests/test_llm_annotate.py`](file:///home/adhyan/Desktop/EchoTales/packages/pipeline/tests/test_llm_annotate.py): Unit test suite covering prompt builders, schema parsing, cost calculation, and dry-run logic.

---

## 2. Pilot Selection & Exact Execution Command

### Pilot Selection (10 Stratified Mentions)
Ten representative mentions from [`data/eval/human_review_200.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/human_review_200.csv) covering all 7 narrative strata:
1. `R001` (`unresolved_name`): `Bai Ning Bing` (predicted `UNRESOLVED`).
2. `R004` (`title`): `the clan head` (predicted `UNRESOLVED`).
3. `R006` (`background`): `Fang Yuan` (predicted `Fang Yuan`).
4. `R007` (`easy_name`): `Fang Zheng` (predicted `Fang Zheng`).
5. `R010` (`relational`): `my lord` (predicted `Fang Yuan`).
6. `R023` (`alias`): `Mo Bei` (predicted `Gu Yue Mo Bei`).
7. `R025` (`relational`): `uncle` (predicted `Gu Yue Dong Tu`).
8. `R031` (`alias`): `Mo Yan` (predicted `Gu Yue Mo Yan`).
9. `R144` (`observer_sensitive`): `Bai Ning Bing` (predicted `Bai Ning Bing`, chapter 82).
10. `R184` (`observer_sensitive`): `Gu Yue Yao Ji` (predicted `Gu Yue Yao Ji`).

### Exact Command Run
```bash
.venv/bin/python scripts/review/llm_annotate.py \
  --input data/eval/human_review_200.csv \
  --output data/eval/pilot_review_10.csv \
  --model gpt-5.6-luna \
  --reasoning-effort low \
  --batch-size 10 \
  --sample-ids R001,R004,R006,R007,R010,R023,R025,R031,R144,R184
```

---

## 3. Test & Validation Results

- **Unit Tests**:
  Command: `.venv/bin/pytest packages/pipeline/tests/test_llm_annotate.py`  
  Outcome: **8 passed in 0.24s** (covering prompt generation, validation fallbacks, cost estimation, overwrite protection, and resumption).
- **Output Inspection**:
  File: [`data/eval/pilot_review_10.csv`](file:///home/adhyan/Desktop/EchoTales/data/eval/pilot_review_10.csv)  
  - Exactly 10 target rows annotated; remaining 190 rows left blank for resumption.
  - Source data and stable IDs (`R001`–`R184`) preserved 100%.
  - Zero modifications to original evaluation CSVs.
  - All 10 candidate labels fall strictly within `{'correct', 'incorrect', 'unresolved'}`.
  - Explanations are exactly 1 concise sentence grounded in the provided excerpt.

### Sample Output Annotations
- `R001` (`unresolved_name`): Label `unresolved`. Note: *"The mention refers to Bai Ning Bing, but the system left the entity unresolved."*
- `R004` (`title`): Label `unresolved`. Note: *"The mention denotes the clan head, but the excerpt does not identify that person by name."*
- `R010` (`relational`): Label `correct`. Note: *"The hunter addresses Fang Yuan as 'my lord' while apologizing for offending him."*
- `R023` (`alias`): Label `correct`. Note: *"The mention refers to Gu Yue Mo Bei, who is listed alongside Chi Cheng and Fang Zheng."*

---

## 4. API Telemetry & Cost Breakdown

| Metric | Measured Value | Budget Cap |
|---|---|---|
| **API Model** | `gpt-5.6-luna` | First-choice cost model |
| **Reasoning Setting** | `reasoning_effort="low"` | Lowest reasonable setting |
| **Request Count** | **1** (single batched request) | $\le 1$ |
| **Prompt Tokens** | 1,417 tokens | — |
| **Completion Tokens** | 630 tokens (including internal reasoning) | — |
| **Total Tokens** | 2,047 tokens | — |
| **Latency** | 6.97 seconds | — |
| **Measured Cost** | **$0.000984** (~0.10 cents) | **< US$0.05** |

### Projected Full-Run Cost (Remaining 278 Mentions)
- At ~205 tokens per mention: $278 \times 205 \approx 57,000$ tokens total.
- **Projected Total Cost for Full 288-Mention Run**: **~$0.028 – $0.035 USD** (less than 4 cents total).

---

## 5. Failures, Limitations & Scaling Safety

- **Failures**: Zero technical failures, zero API retries, zero malformed JSON responses.
- **Limitations**:
  1. *Candidate Labels Only*: Model outputs represent automated candidate labels; they must NOT be claimed as human ground truth until author adjudication is complete.
  2. *Bounded Context*: The snippet contains $\le 200$ characters. For pronouns or deictic titles where identity was introduced earlier in the chapter, the model correctly flags `unresolved` when the name is absent from the window.
- **Scaling Assessment**: **SAFE TO SCALE**.
  - Pipeline is fully idempotent and checkpointed (saves to disk after every batch).
  - Explicit output path prevents overwriting source datasets.
  - Cost is verified to be negligible (< $0.05 for the entire dataset).

---

## 6. Required Human Decisions

1. **StoryTrace Research Firewall**:
   To publish the N1 systems paper, the owner must formally lift or re-scope the 2026-10-02 firewall in [`docs/research/DECISION_LOG.md`](file:///home/adhyan/Desktop/EchoTales/docs/research/DECISION_LOG.md).  
   *Suggested Decision Wording*:
   > **Decision (2026-10-13)**: The 2026-10-02 StoryTrace research firewall is lifted for publication track N1. Narrative temporal, observer, and identity modeling—together with the formal compiler harness and cutoff-scoped visual asset selector—are authorized as core system contributions for submission to WNU 2027 / ACL 2027 System Demonstrations Track.
2. **Adjudication Authorization**:
   Review the next prompt below and authorize running the full 288-mention annotation batch.
