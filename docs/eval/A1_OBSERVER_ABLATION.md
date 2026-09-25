# A1 — observer state collapsed to READER

**2026-09-26.** Script `scripts/observer_ablation.py`; result `data/eval/observer_ablation.json`; canonical database `data/reverend-insanity.db`.

## Pre-registered rules (fixed in the script's docstring before any number was computed)

- **Reveal events:** every (fact, learned chapter r) in the `observation` table. That gives **3 events over 2 facts**: "Bai Ning Bing" at ch166 and ch197, and "Gu Yue Yao Ji" at ch178.
- **Observers:** all witnesses of the fact, plus the 20 most-mentioned Selves that are neither witnesses nor the target.
- **Positions:** r−1, r, 200. That is **228 queries**, of which 34 are should-know.
- **Should-know:** the observer has an observation of the fact dated at or before the position. This is the system's own record; whether the record is right is a separate question for human review (`HUMAN_REVIEW_PROTOCOL.md`).
- **Leak:** the revealed alias is returned although the observer should not know it.
- **Under-exposure:** the alias is not returned although the observer should know it.
- **Generation leak:** the render plan built for that observer, with the target in the cast, draws the target's persona although the observer should not know it.
- **Condition A1:** the same query answered as `READER`, i.e. the "who" axis removed.

## Result

| | Leak | Under-exposure | Wrong-identity exposure | Generation leak |
|---|---:|---:|---:|---:|
| **FULL** | **0** | 9 | 0 | **0** |
| **A1 (observer → READER)** | **194** | 0 | 0 | **194** |
| Difference | +194 | −9 | 0 | +194 |

**By observer class:**
- Non-witnesses: FULL 0 leaks, A1 **180 / 180** queries.
- Witnesses: FULL 0, A1 14. The 14 are witnesses asking before their reveal.

**By reveal event (leaks, FULL → A1):**
- Bai Ning Bing @166: 0 → 65
- Bai Ning Bing @197: 0 → 61
- Gu Yue Yao Ji @178: 0 → 68

## Reading it honestly

- **FULL leaks 0 by construction**, because "leak" is defined against the system's own observation records. What A1 measures is causal: **removing the observer axis changes the returned identity in 194 of 228 queries**, and the rendered cast in the same 194.
- **The 9 FULL under-exposures are a mismatch between the rule and the system's granularity, not a system error.** The ch178 and ch197 reveals sit at block 7 of their chapters. Asked from the start of the reveal chapter, the witness correctly does not know yet. The pre-registered rule compares chapters only, so it counts them. The result is left as measured and not re-scored.
- **At the generation level, FULL also draws no character for a witness who should know** (0 of 34). Persona bindings are READER-scoped, so every character observer resolves no body. A1's 34 "drawn when known" come only from answering as the reader. **Observer-conditioned rendering is therefore demonstrated as reader vs non-reader, not witness vs non-witness.**
- The scale is small: 3 events, 2 facts. The observer axis is thinly populated on this corpus.
