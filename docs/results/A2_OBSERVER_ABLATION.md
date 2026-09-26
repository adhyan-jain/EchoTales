# A2 — knowledge time removed, observer kept

**2026-09-26.** Same script, rules and 228 queries as A1 (`docs/results/A1_OBSERVER_ABLATION.md`).

A1 removes *who* is asking. A2 keeps the observer filter and removes *when* they learned. Observations are admitted regardless of their learned date (`knowledge_pos` = +∞), while story position and temporal validity are retained. This isolates the knowledge-time axis inside the observer model.

Mapping to the brief: the requested "story position + temporal state, but no observer-specific filtering" is A1 at the state level (character observers answered from reader-scoped facts at the same position). A2 is the complementary ablation, which the observer model also needs.

## Result

| | Leak | Under-exposure | Generation leak |
|---|---:|---:|---:|
| **FULL** | **0** | 9 | 0 |
| **A2 (knowledge time removed)** | **14** | 0 | 0 |

- Every A2 leak is a **witness asking from before their own reveal**: Bai Ning Bing @166: 5; @197: 1; Gu Yue Yao Ji @178: 8.
- Non-witnesses are unaffected (0): without an observation, removing its date changes nothing.
- The 9 FULL under-exposures disappear under A2 for the same reason they appeared (see A1): the mid-chapter reveal position stops mattering.
- **Generation leak stays 0** because character observers never resolve a persona (READER-scoped bindings). The knowledge-time axis therefore changes names, not drawn identity, on this corpus.

## Conclusion

Both axes are causally active at the state level:
- removing the observer changes 194 of 228 answers (A1);
- removing knowledge time changes 14 (A2), exactly the pre-reveal witness queries.

At the generation level only the reader-vs-character distinction shows (A1). Witness-level rendering is blocked by the READER-scoped persona bindings, which is the documented limitation.
