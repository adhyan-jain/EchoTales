# Implementation plan (conditional: NARROW)

The gate did not pass cleanly (NOVELTY_DECISION). This plan covers only the NARROW core and is ordered so that it can be
**abandoned after Stage 0 or 1 at low cost**. Nothing here has been started. No GPU, no paid calls; each stage is
unit-test scale.

## Invariants that must stay intact
- `core` imports nothing from `pipeline` (`test_import_direction.py`).
- The existing test suite stays green (`python3 -m pytest packages/core/tests packages/pipeline/tests`).
- Render cache keys change only through a `RENDER_CACHE_VERSION` bump (documented in `cache_key.py`).
- No change to default render output for a store with no retrospective/retracted facts (D4 says that is every shipped DB),
  verified by a before/after `state_digest` comparison on RI and LOTM.

## Stage 0 — Make the property executable (1-2 days)
- Add `packages/core/tests/test_cutoff_faithfulness.py` from `probes/prop_cutoff.py`: seeded random stores; assert
  `compile(S,k) == compile(S|≤k,k)` for the `state_of` channel (passes now) and for the render compile (fails now; mark
  `xfail(strict=True)` with the D-number until Stage 1).
- Add the two regression tests from `probe_audit.py` (probes A and B).
- **Kill criterion:** if the differential test finds no violation outside the persona channel and Stage 1 turns it green
  with a ≤30-line change, this is a bug fix, not a research direction: stop and write a HANDOFF section.

## Stage 1 — Close the persona channel (M1, M7, M8) (2-3 days)
- `plan_builder.compile_render_state`: persona reader derived from `StateResolver.state_of(PERSONA, observer,
  knowledge_pos)` restricted to `APPEARANCE_KEYS`, replacing `appearance_of(position=…)`; `_fold_target` `persona_facts`
  from the same call.
- `TemporalFact` validator for I3/I4; `Store.retract_attribute`.
- Deterministic ordering: `ORDER BY` on every `get_*` used by `state_of` (A3).
- Bump `RENDER_CACHE_VERSION`. Compare digests on RI/LOTM before/after (expect equal, per D4).

## Stage 2 — Positional voiding and a retrospective mode (M2, M10) (2 days)
- `NarrativeSegment.voided_at: DiscoursePosition | None`; `keep()` excludes a voided timeline only when
  `knowledge_pos ≥ voided_at`.
- Explicit `knowledge_pos` override on `compile_*` for flashback panels.
- Tests: the D7 scenario at `k=105` vs `k=125`.

## Stage 3 — Certainty and refs in the spec (M3) (3-4 days)
- `GenerationState` gains `cert` and `ref` per field and a `plausible` policy; `to_dict`/`from_dict`/digest updated.
  Default `exclude` changes behavior (PLAUSIBLE persona facts stop appearing), so gate it with a flag until measured on RI.
- **Kill criterion:** if `exclude` leaves more than a few percent of RI panel characters without a drawn persona, the policy
  is unusable for generation and the uncertainty claim of C-A weakens; fall back to `mark`.

## Stage 4 — Close the boundary (M4, M5) (1-2 weeks, optional, highest risk)
- Build the director brief from `Spec` (not `story_context`); route `apply_canon` and the lexicon through labelled
  extensions.
- Label-propagating prompt assembly with a subset check; a production caller for the validator.
- **Kill criterion:** if re-rendering one RI chapter changes more than the panels the diff explains, or director quality
  visibly regresses, revert and keep Stages 0-3 only.

## Stage 5 — Voice adapter (M6) and the narrow demonstration (about 1 week)
- Stub engines only (`ECHOTALES_LLM_MODE=stub`, `--image-engine stub`). A synthetic 12-chapter fixture with one
  retraction, one retrospective reveal, one body swap, and one observer with a witness row. Ingest chapter by chapter and
  assert: (T3) no artifact with cutoff ≤ n is recomputed when chapter n+1 is added; (T2) the pre-retraction spec is
  byte-identical after the retraction; image, voice and director specs agree on `admitted`.
- Output a table, not a benchmark campaign.

## What would invalidate the design
- A real novel (or a hand-annotated slice) shows the extractor cannot produce retraction/retrospective facts at usable
  precision (M11): the semantics then has no real-world content to protect.
- NWM or a follow-up publishes observer-scoped, retraction-aware retrieval with a stated property.
- Stage 4's boundary closure cannot be achieved without rewriting the director.

## Explicitly out of scope
Tri-temporal `correct()` (M9), any claim about generated pixels or audio, a paper draft, benchmarks, model comparisons.
