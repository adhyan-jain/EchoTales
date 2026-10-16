# SIO implementation notes and results (synthetic; not real-novel evidence)

Pre-registration: `docs/research/preregistrations/PREREG_SIO_synthetic_identity_oracle.md` v1, sha256 `df93ef3a4f219c9225641632558dc622606b0acd5d6d4b20801dfa7ad0a5a121`, re-hashed before the run and equal to `MANIFEST.json` `[REPO]`. Frozen files were not edited.

Runner: `scripts/chimera/sio_synthetic_oracle.py` (sha256 `3b87daa9...`). Results: `data/eval/chimera/sio_results.json` (sha256 `dd7534ae...`). Tests: `packages/pipeline/tests/test_sio_generator.py` (5 passed). Command: `python scripts/chimera/sio_synthetic_oracle.py --out data/eval/chimera/sio_results.json` (8 s, CPU, no LLM, no network, no key). Seeds 0..39, no selection, one run of record. A 2-world debug smoke was run first to the scratchpad only, to catch bugs; it was not used for any number.

Label provenance: every label here is **by construction from the world spec** (synthetic). No model labelled anything. No novel text is used.

## Interpretations I made where the frozen prereg is ambiguous (not edits to it)

1. "Retroactive half" of the title worlds = even seeds: the bare title is mentioned in ch1-2 before the holder is named (named + declared in ch3-4). Odd seeds: holder declared first, then mentioned. Chapter-level, not sentence-level.
2. The resolver's co-presence is chapter-wide (`runner.py:902`, `reference_mode.is_physically_present`). So every alias chapter holds exactly one PRESENT named mention (Z). Holder-introduction mentions inside alias chapters carry `NARRATOR_REFERENCE`. This is a deviation from "reference mode PRESENT" for those mentions only.
3. Layout: reveal 0 has a=3, r in 5..7 (distance 2..4 by seed%3); reveal 1 has a=9, r in 11..12 (distance 2..3). Title declarations: H1 ch1-2 (odd seeds) or ch3-4 (even), H2 ch5-6; M1 cuts include 4 and 5 as specified.
4. M1 compares the canonical label of the target (or None) per mention between F and each prefix P_c, pooled over (mention, cut) pairs; the pooled count is not independent, so a world-level count is also reported.

## Known generator flaw (found after the run; results not re-tuned)

The H2-tenure title mention is in ch8. When reveal 0 has distance 4 (seed%3==2, 13 of 40 worlds) ch8 is a post-reveal chapter with a sole PRESENT named mention, so the sole-co-present rule links the title to that person. Exploratory row `title_in_H2_tenure_linked_to_H2_F` (27/40) is therefore confounded and must not be read as a title-holder failure. Pre-registered M1-M4 do not use ch8 mentions. Verified by inspecting seeds 2 and 5 (method `RELATIONAL_COPRESENCE`).

## Results (Wilson 95%)

| Metric | k/n | rate | 95% CI |
|---|---|---|---|
| M1 prefix-invariance violations, pooled (mention, cut) pairs | 0/3741 | 0.000 | [0.000, 0.001] |
| M1 worlds with any violation | 0/40 | 0.000 | [0.000, 0.088] |
| M2 premature resolution to Y, full run F | 0/218 | 0.000 | [0.000, 0.017] |
| M2 premature resolution to Y, prefix run before reveal | 0/218 | 0.000 | [0.000, 0.017] |
| M2 by distance 2 / 3 / 4 (F) | 0/70, 0/96, 0/52 | 0 | upper 0.052 / 0.038 / 0.069 |
| M3 post-reveal alias NOT linked to Y (F) | 221/221 | 1.000 | [0.983, 1.000] |
| M4 retroactive title link (title precedes naming, F) | 40/40 | 1.000 | [0.912, 1.000] |
| control: title after naming linked to holder (F) | 40/40 | 1.000 | [0.912, 1.000] |

Exploratory, not pre-registered:

| Quantity | k/n |
|---|---|
| pre-reveal alias linked to ANY entity (F and prefix) | 218/218 |
| pre-reveal alias linked to the co-present Z, a different person than Y (F) | 218/218 |
| post-reveal alias linked to any entity (F) | 221/221 (all to Z, none to Y by M3) |
| plain PRESENT named controls resolved to their own label (F) | 702/702 |
| title LINK events whose `cause_pos` chapter is earlier than the holder binding's `learned_at_pos` | 40/107 |
| frozen reveal sentence matches the repo's `REVEAL_PATTERNS` | 0/80 |
| repo stock phrases ("This was none other than X.") match `REVEAL_PATTERNS` (regex only, 2 hand-written strings) | 2/2 |

## What this shows and does not show

- Pre-registered decision rule: M1 = 0 and M2(F) = 0, so "the resolver's `mention.target_id` is prefix-causal on these structures" holds. M4 > 0 in the retroactive half as pre-declared. M4 is the by-design backward extension documented in `title_holders.py` (first holder's tenure is extended to chapter 1).
- **The M2 = 0 is vacuous as evidence of disclosure-faithfulness.** The resolver never uses the reveal sentence at all (M3 = 100%): it links every alias, before and after the reveal, to the sole co-present character, who is the wrong person under both the reader view and the omniscient view (218/218 and 221/221). That is a different failure: over-commitment on a deictic alias. Its size depends on this generator's design of exactly one co-present name per alias chapter, and does not transfer to real text.
- Reveals are not meant to rewrite `mention.target_id`: `detect_reveals` logs reader-observer events separately `[INSPECT]`. This test therefore does not test the reveal pipeline end to end, only the mention layer.
- `state_of` gates on `binding.learned_at_pos` and does not reference events or `cause_pos` `[INSPECT: grep of packages/core/src/echotales/core/state.py]`. So the early event stamp (40/107) is a log inconsistency, not shown to leak through `state_of`. Other consumers of `mention.target_id` were not traced: UNVERIFIED.
- **No comparison of "plain resolver vs whole-input renaming vs evidence-gated linking" was possible.** The deterministic resolver has no parametric memory, so renaming and gating cannot change its output, and T4 closed with the renaming control unvalidated. C1b (gating) and C1a (leakage under renaming) are therefore **untested** by SIO. They need an LLM resolver; none was run.
- Power: cannot detect violation rates below about 0.1% pooled or 9% by world.
