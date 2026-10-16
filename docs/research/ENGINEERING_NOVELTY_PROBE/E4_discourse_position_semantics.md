# E4. Discourse-position semantics on real data: unit of `offset`, and chapter lag of the reader query

Status: PRE-DECLARATION written 2026-10-16 BEFORE the confirmatory run. Label provenance: SYSTEM-INTERNAL (real scratch DB copies; no labels).

## Invariants under test
- E4a (type contract, core/models.py): `DiscoursePosition(chapter, offset)` is "always a total order and never ambiguous" and is
  the knowledge-time coordinate. The dominant writer stamps `learned_at_pos = mention.position`, i.e. `offset` = the mention's offset
  WITHIN ITS BLOCK (Mention.offset docstring), so two positions in different blocks of one chapter are ordered by their in-block
  offsets, not by their place in the text. Hypothesis: within-chapter order of positions agrees with text order for >= 95% of pairs.
  Falsifier: agreement below 95% on any serial (Wilson).
- E4b (reader query): `state_of(READER, position=c)` sets knowledge_pos=(int(c), 0), so facts learned inside chapter c at offset > 0
  are invisible at position c and appear only at c+1. Hypothesis (spec reading "knowledge_pos defaults to the chapter containing position"):
  state_of at position c equals the reader's state after reading chapter c, i.e. no (entity, chapter) query changes if knowledge is taken at
  the end of chapter c. Falsifier: more than 1% of (entity, chapter) queries differ. This is a spec ambiguity as much as a bug; the
  finding is the measured size of the lag and whether production consumers rely on it.
- E4c (consequence): attribute winners inside one chapter are chosen by `learned_at_pos >= prev` (block-relative offset). Count same-chapter
  same-key conflicting attribute pairs and how often the winner differs from the one chosen by true text order (only measurable where the
  evidence position is recoverable; otherwise report the count of conflicts only).

---
## RESULTS (run 2026-10-16; `scripts/chimera/eng_probe_e4_discourse_position.py`; data `data/eval/chimera/eng_probe_E4_<novel>.json`)

Label provenance: SYSTEM-INTERNAL (read-only scratch copies, no labels).

### E4a. The `offset` of a DiscoursePosition is block-relative, so within-chapter order is not an order
Unit confirmed on the data: in one chapter, mentions sorted by (block, offset) have offsets 36, 40, 14, 29, 151, 41, 217, ... i.e. the offset resets at each block. Same-chapter pairs with distinct text positions, comparing the order the DiscoursePosition type gives with the true (block, offset) order:

| Serial | mention pairs | concordant | discordant | tied offsets | alias-binding fact pairs (matched to their founding mention) | concordant |
|---|---|---|---|---|---|---|
| LOTM | 77,678 | **46.5%** [46.2, 46.9] | 49.8% | 3.7% | 25,295 | 56.1% [55.5, 56.7] |
| ORV | 76,726 | **47.9%** [47.5, 48.3] | 49.4% | | 75,753 | 53.7% [53.3, 54.0] |
| RI | 354,787 | **48.2%** [48.0, 48.3] | 47.8% | | 343,405 | 58.2% [58.1, 58.4] |

A random order would give 50%. **H_E4a (>= 95% agreement) is falsified by a wide margin**: within a chapter the knowledge-time coordinate carries almost no ordering information. 81% to 87% of alias bindings and 90% to 95% of attributes carry a non-zero offset (RI: 9,002 of 11,095 and 552 of 617); persona bindings and the title-holder, transmigration and appearance-extraction writers stamp offset 0 (chapter granularity), so one `DiscoursePosition` type holds three different units across writers (block-relative characters, chapter-granular zero, and a block index in `render/panels.py`'s `SceneState` stamp).

Downstream reach today: every comparison that matters is chapter-level (`state_of` truncates `knowledge_pos` to `(int(position), 0)`), so no production answer is wrong because of this; it **makes sub-chapter prefix causality impossible to state** (a within-chapter reveal cannot be ordered against a within-chapter fact), and it makes the same-chapter attribute-winner rule and the retraction-vs-learned comparison arbitrary whenever two facts share a chapter (E3/I8; no such pair occurs in the real DBs).

### E4b. Chapter lag of `state_of(READER, position=c)`
`knowledge_pos` is `(int(c), 0)`, so facts learned in chapter c at offset > 0 appear at position c+1, not c. Over each character's span from first learning to the end of the volume (queries with end-of-chapter knowledge versus the default):

| Serial | alias queries that change | 95% | persona-attribute queries that change | characters whose own name is missing at their first chapter |
|---|---|---|---|---|
| LOTM | 3.1% | [2.3, 4.4] | 3.7% | 30 of 43 |
| ORV | 3.0% | [2.0, 4.5] | n/a (no attributes) | 21 of 29 |
| RI | 0.81% | [0.65, 1.00] | 0.88% [0.71, 1.08] | 61 of 90 |

Under the pre-declared 1% bound this is falsified for the two 40-chapter serials and not for RI, but the effect is by construction one chapter per fact, so it shrinks with volume length; I read it as the **start-of-chapter convention** the code implements, not a bug. The finding is the **inconsistency across fact tables**: at position c a persona binding learned in chapter c is visible (offset 0: 98 of 98 in RI) while 81% of alias bindings and 90% of attributes learned in chapter c are not.

### E4c. Same-chapter attribute conflicts in the real data
0 (persona, key) groups with two or more distinct admissible values in RI, LOTM or ORV: the winner-by-learned-offset rule and the tie rule are never exercised on real data.
