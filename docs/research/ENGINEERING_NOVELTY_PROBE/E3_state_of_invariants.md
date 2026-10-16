# E3. Adversarial invariants of `state_of` on synthetic stores, with real-data prevalence

Status: PRE-DECLARATION written 2026-10-16 BEFORE the confirmatory run. Label provenance: SYNTHETIC (labels by construction from an
independent oracle written from the documented spec: docs/design/architecture.md Sections 3 and 5, core/state.py module docstring).
Real databases are used only for prevalence counts (read-only SQL on scratch copies).

## Claimed invariants (each with its source) and what would falsify it
Each claim is falsified by one reproducible counterexample (existence). Prevalence in the generator is meaningless (I choose the mix);
the real-data prevalence is reported separately.
- I1 prefix causality: deleting every fact learned after k leaves state_of(READER, p, k) unchanged (metamorphic).
- I2 insertion-order invariance: permuting store row order leaves every state_of answer unchanged.
- I3 retraction vs interval end (Section 5): a retracted fact is visible at k < retracted_at and invisible at k >= retracted_at;
  a closed-interval fact is invisible past its end at every k; the two never behave alike. Checked for alias, attribute, relation AND persona binding.
- I4 FALSE facts are hidden from in-world observers and visible to SYSTEM (Section 5; state_of docstring "Truth status"). Checked for all four fact kinds.
- I5 a character observer does not inherit the reader's knowledge (Section 5), including the knowledge that a claim was retracted.
- I6 reader knowledge advances with reading position on every timeline (module docstring: "knowledge time ... without it narration spoils every reveal").
- I7 canonicity: facts in VOIDED segments are excluded; others are not (module docstring "Canonicity").
- I8 determinism of the attribute winner: two same-key admissible facts resolve independent of insertion order.
Expected (stated so it can be wrong): I1 and I3 hold for alias/attribute/relation; I3/I4 fail for persona bindings (no retracted_at column,
truth_status unread in the persona branch); I5 fails for retractions; I6 fails off the MAIN timeline with default arguments;
I7 fails or is dangerous (timeline-level voiding); I8 fails on ties.
Gate-vs-engine rule: if the oracle and code disagree I decide by the cited spec sentence whether the oracle or the code is wrong,
and report spec ambiguity as ambiguity, not as a bug.

---
## RESULTS (run 2026-10-16; `scripts/chimera/eng_probe_e3_state_of_invariants.py`; data `data/eval/chimera/eng_probe_E3_state_of.json`; regression form `scripts/chimera/test_eng_probe_e3_state_of.py`: 8 passed, 6 xfailed)

Label provenance: SYNTHETIC (expectations from the quoted spec sentences). In-memory stores. Prevalence in the generator is meaningless; real-data prevalence below.

| Invariant | Result | Minimal repro (all in the script) | Real-data prevalence (3 scratch DBs) |
|---|---|---|---|
| I1 prefix truncation (metamorphic, 300 random stores x 16 (p, k), 4,800 queries) | **holds, 0 violations** | drop facts learned after k, answer at (p, k) unchanged | n/a |
| I3 retraction vs interval end, alias / attribute / relation | **holds** (visible at k < retracted_at, hidden after, at every story position; closed intervals hidden past their end at every k) | | 0 retracted rows in any DB |
| I3 persona binding | **not representable**: `SelfPersonaBinding` has no `retracted_at` and `state_of`'s persona branch ignores `truth_status` | | 0 non-TRUE bindings (all 98 / 93 / 0 are TRUE) |
| I4 FALSE hidden from in-world observers, alias / attribute / relation | **holds** | | all alias rows TRUE |
| I4 persona binding | **violated**: a FALSE binding is returned to the READER (state_of lines 322-333 never read truth_status) | one binding, `truth_status=FALSE`, `state_of(READER)` returns the persona | latent: the only writer (`persona/split.py`) writes TRUE |
| I5 retraction is observer-global | **violated (modelling gap)**: character C witnessed a claim at ch5; the reader is told it was false at ch20; C is never told. `state_of(C, k=15)` returns it, `state_of(C, k=30)` does not. `retracted_at` is a single reader-discourse position applied to every observer, and there is no observation row type for "learned that it is false" | alias with `retracted_at=(20,0)` plus one Observation | 0 retractions, 12 observation rows in RI: not exercised |
| I6 reader knowledge on a non-MAIN timeline | **violated by default arguments**: a DREAM-timeline fact learned at ch30 is returned to the READER with no `knowledge_pos` (default 10**6); correct when `knowledge_pos` is passed; the MAIN timeline is correct | | 0 non-MAIN facts; production callers pass only MAIN |
| I7 canonicity | **violated, latent**: `_voided_timelines` is timeline-level, so a VOIDED segment on `MAIN_TIMELINE` makes `state_of` return nothing at all (0 aliases), though the docstring promises fact-level exclusion; a VOIDED segment on its own timeline behaves correctly | `store.void_span([seg])` on a MAIN segment | `void_span` has no pipeline caller; 0 VOIDED segments in the DBs |
| I8 / I2 insertion-order invariance | **violated for attribute ties**: two admissible same-key facts with equal `learned_at_pos` resolve to the last row iterated. 1,200 random order-permuted queries: 8 differ, **all 8 are attribute-only differences with a tie on learned_at_pos (read and classified)** | white/black, same (5,0), both orders | 0 conflicting attribute pairs in the DBs (`E4c`) |

### Gate-vs-engine reading
Each violated line was decided against the cited spec sentence, not against the code. I6 is a documented design choice (the comment says deriving k from a dream position would filter out the whole timeline), so it is a **spoiler-unsafe default**, not a wrong answer; I7 and I3/I4-persona are real gaps between the docstring and the code that no data path exercises today; I5 is the only one that is a limit of the *model* (it cannot say that an observer learned of a retraction, in either direction) rather than of an implementation line.

### Verdict
The core filters (story containment x knowledge time x truth/retraction) are correct for alias, attribute and relation on the MAIN timeline: prefix truncation and the retraction/interval-end distinction survive an adversarial grid. The defects are at the edges: persona bindings, off-MAIN timelines, VOIDED-on-MAIN, ties, and observer-relative retraction. None has a real-data instance in the three serials (which hold zero retractions, zero non-MAIN facts and zero conflicting attributes), so none changes any reported number.
