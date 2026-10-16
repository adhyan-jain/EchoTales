# E6. Prefix causality of the persona (trait) stage: do facts visible at chapter k depend on chapters after k?

Status: PRE-DECLARATION written 2026-10-16 BEFORE the confirmatory run. Label provenance: SYSTEM-INTERNAL (no reference labels). Scratch copies; CPU only; the persona stage is run in its deterministic mode (client=None), no LLM.

## Why this probe exists
E1 shows the resolver loop is exactly prefix-causal. The graph also carries persona facts (age_band, gender, register, archetype, big_five).
`persona/build.py` stamps them `learned_at_pos = entity.first_attested_pos` (the chapter of first sighting) but computes them from up to 12
appearance chapters (`chapters_for_target(limit=12)`) and from the WHOLE-volume mention count (talkativeness = dialogue/mention_count, prominence).
CHIMERA backlog A6 reports this as agent-traced, never measured. The reader-observer query `state_of(READER, p)` should return the
state a reader who has read only chapters < p would hold; this probe tests that on real text.

## Design
For each serial and cut k: (full) resolve all chapters (volume passes off) then `build_personas`; (trunc) copy the DB, delete every chapter,
span, mention and segment row after chapter k, resolve, `build_personas`. Spans' stored speaker attributions are held fixed (computed upstream).
For every character entity present in both: compare `state_of(persona, READER, position=k+1)` attributes (position k+1 = after reading chapter k),
`state_of(self).aliases` and `persona_ids`. Metric: fraction of (entity, trait key) facts whose value differs between the truncated and full graph
at the same query position, per key; and the fraction of entities with any differing trait.

## Hypothesis and falsifier (pre-declared)
H_E6: the persona stage is prefix-causal: every fact visible at k in the full graph equals the fact in the graph built from chapters <= k only.
Falsifier: any (entity, key) difference. I expect differences for big_five/extraversion and prominence-driven archetype (whole-volume mention
count), few for gender and age_band (honorific/pronoun from earliest appearances). Quantity to report: per-key disagreement with Wilson interval.
Gate-vs-engine rule: every differing key is traced to its code path (whole-volume count, later appearance chapters, or a probe artefact such as
a changed prominence floor on a truncated mention count) before it is called a finding; a difference that only reflects "the character has
fewer mentions in a truncated volume" is reported as the mechanism, not hidden.

## Amendment (same day, before the reported run)
The first execution queried at `position = k + 1`. Reading the one alias-set difference it reported (LOTM k=5) showed it was a **probe artefact**:
the full graph holds chapter k+1 and `state_of` at that position admits aliases stamped `(k+1, 0)` (offset-0 writers, see E4), which cannot exist in a
graph truncated at k. The query was changed to the end of chapter k (`position = k + 0.5`, `knowledge_pos = (k, 10**6)`) and the whole probe re-run;
the hypothesis and falsifier are unchanged. Only the corrected run is reported below.

---
## RESULTS (corrected run 2026-10-16; `scripts/chimera/eng_probe_e6_persona_prefix.py`; data `data/eval/chimera/eng_probe_E6_<novel>.json`)

Label provenance: SYSTEM-INTERNAL. Trait values are closed vocabularies, no novel text. "Compared" = characters with a persona fact in both graphs at the end of chapter k. Alias sets compared too: 0 differences at every cut (consistent with E1).

| Serial | k | characters compared | with any trait difference | gender differs | archetype differs (derived from gender) | age_band / register / big_five differ | persona-id set differs |
|---|---|---|---|---|---|---|---|
| LOTM | 5 | 13 | 6 (46%, Wilson [23, 71]) | 6 | 6 | 0 / 0 / 0 | 0 |
| LOTM | 10 | 19 | 3 (16%) | 3 | 3 | 0 | 0 |
| LOTM | 20 | 29 | 1 | 1 | 1 | 0 | 0 |
| LOTM | 30 | 34 | 0 | 0 | 0 | 0 | 2 |
| ORV | 5 / 10 / 20 / 30 | 7 / 10 / 16 / 21 | 2 / 1 / 0 / 0 | 2 / 1 / 0 / 0 | same | 0 | 0 |
| RI | 10 / 20 / 40 / 80 / 120 | 11 / 13 / 20 / 37 / 58 | 2 / 2 / 1 / 3 / 2 | same | same | 0 | 2 / 2 / 1 / 0 / 0 |
| pooled | 13 cuts | 288 (nested cuts) | 23 (8.0%) | 23 | 23 | 0 of 288 each | 7 |

**H_E6 falsified (existence): the persona stage is not prefix-causal.** Two mechanisms, each traced to code before being called a finding:
1. **Gender (and the archetype string derived from it)**: in 21 of the 23 differences the prefix graph says `unknown` and the full graph already says `male`/`female` for a character introduced shortly before the cut (in 2 cases the reverse). `gender_from_pronouns` reads narration sampled from the earliest 12 chapters where the entity appears (`chapters_for_target(limit=12)`), and the result is stamped `learned_at_pos = first_attested_pos`. A fact whose evidence arrives in chapters after k is therefore served at position k with a learned-at stamp <= k. The effect is large where it can be (46% of the cast available after chapter 5 of LOTM) and shrinks with depth because most characters have already accumulated evidence; it does not vanish (RI k=80: 3 of 37).
2. **Body (persona) splits**: 7 persona-id-set differences (LOTM 2, RI 5), e.g. two RI characters whose full-graph persona flips to a second body at story position 4.87 (inside chapter 4) while the graph built from chapters <= 10 keeps one body. `find_change_candidates` rejects a body change unless the entity is attested in enough chapters AFTER it ("a change with no story left after it explains nothing"), counted over the whole volume: a decision about chapter 4 that needs chapters beyond 10 (by design, but not prefix-causal).

What did NOT differ: age_band, register and big_five in 0 of 288 (the deterministic profile reads honorific surfaces and ratios that were identical in the prefix). The whole-volume mention count that I expected to move big_five did not move it in the deterministic mode (talkativeness stayed identical), so my prior on that key was wrong.

### Gate-vs-engine reading
The first run used position k+1 and reported one spurious alias difference; reading it showed a probe artefact (offset-0 stamps of chapter k+1 exist only in the full graph) and the probe was corrected before the reported run (amendment above). The remaining differences were each traced to the two code paths above. Whether the full-graph value is *wrong* is not measured (no labels); the finding is that it is **not what a reader of chapters <= k can know**, which is the claim the reader-observer query makes.
