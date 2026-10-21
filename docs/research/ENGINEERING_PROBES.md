# Engineering novelty probes E1-E6 and summary

> Merged on 2026-10-22 from 7 separate documents to keep the docs tree small. Each section below is one original file, text unchanged; its old path is in the section heading. The originals are in git history.

---

<!-- merged-from: docs/research/ENGINEERING_NOVELTY_PROBE/E1_prefix_causality_of_resolver.md -->
## Source: `docs/research/ENGINEERING_NOVELTY_PROBE/E1_prefix_causality_of_resolver.md`

# E1. Prefix causality of the incremental resolver on real serials (graph level)

Status: PRE-DECLARATION written 2026-10-16 BEFORE the confirmatory run. Results are appended below the line "RESULTS" once run.
Label provenance: SYSTEM-INTERNAL (no reference labels, nothing here is accuracy). Scratch copies only; CPU only; no LLM.

## What invariant is tested
Architecture claim (non-negotiable 1 and the "reader-observer" use of `state_of`): resolution is *incremental* and
processes chapters in discourse order, so a decision about chapter c should depend only on chapters <= c. SIO M1 tested
this on synthetic templated text at the mention layer (0/3741). It was not tested on a real serial at the
graph (entity-assignment) layer. Defect B2 (`resolve --chapters` was a no-op) means the test was impossible before this branch.

## Design
For each serial (RI 199 ch, LOTM 40 ch, ORV 40 ch; stored mentions are held fixed, so mention detection is OUT of scope):
- F0 = resolve chapters 1..N, volume-first passes (title holders, transmigration) skipped. This is the "full volume, resolver loop only" reference.
- P_k = resolve chapters 1..k only (same flags), for several k.
- Compare, over the mentions of chapters <= k only: (i) identical target id (ids are deterministic from first surface + first position), (ii) partition agreement (adjusted Rand index) independent of ids, (iii) category of each difference (linked in P_k / unlinked in F0, unlinked in P_k / linked in F0, linked to a different entity).
- Graph level: alias bindings with learned chapter <= k, as multisets of (target, alias hash, type), P_k vs F0.
- F1 = the standard full run (volume passes on) vs F0, to size the by-design volume-first effect on the <= k region.
- Determinism control: F0 run twice (must agree 100% or nothing below is interpretable).

## Hypothesis and falsifier (pre-declared)
H_E1 (the claim): the resolver loop is prefix-causal on real text: for every serial and every k, P_k and F0 give the same
target for >= 99% of mentions in chapters <= k, and the alias-binding multisets restricted to learned chapter <= k are equal.
Falsifier: for any (serial, k) the disagreement over mentions in chapters <= k exceeds 1% with the Wilson 95% lower bound
above 1%, OR the alias-binding multisets differ. My prior expectation (stated so it can be wrong): non-zero disagreement
caused by the window-boundary contradiction sweep / retry_deferred, which revise earlier links with later profiles.
Gate-vs-engine rule: before calling anything a finding I read the members of every disagreement class and attribute
each to (a) my probe, (b) a by-design retroactive pass, or (c) an unintended dependence.

## Not claimed
Mention detection, NER and the commonness profile used whole-volume information when the stored mentions were created;
this probe holds the stored mentions fixed, so it bounds only the resolver stage.

---
## RESULTS (run 2026-10-16; `scripts/chimera/eng_probe_e1_prefix_causality.py`; data `data/eval/chimera/eng_probe_E1_<novel>.json`)

Label provenance: SYSTEM-INTERNAL. Determinism control: F0 run twice, 0 disagreements on all three serials (so any difference below would be real).

| Serial | cuts k | mentions of ch <= k compared (summed over cuts) | prefix run P_k vs F0: mentions with a different target | alias bindings (learned <= k) only in P_k / only in F0 |
|---|---|---|---|---|
| LOTM (40 ch) | 5, 10, 20, 30 | 3,605 | 0 | 0 / 0 at every cut |
| ORV (40 ch) | 5, 10, 20, 30 | 2,762 | 0 | 0 / 0 |
| RI (199 ch) | 10, 20, 40, 80, 120, 160 | 21,798 | 0 | 0 / 0 |
| all | 14 cuts | 28,165 (12,227 distinct mentions; cuts are nested) | **0** | 0 |

One-sided 95% upper bound on the disagreement rate: 3/28,165 = 0.011% (treating cut-mention pairs as independent, which they are not; on the 12,227 distinct mentions it is 0.025%). ARI = 1.0 at every cut. Also 0 disagreement against F0 run with window_size = 10^6 (so the window-boundary sweep and retry are not what is being relied on).

**Verdict: H_E1 NOT falsified.** The resolver loop is exactly prefix-causal on the three real serials at the level of mention-to-entity assignment and alias bindings, for stored mentions. Entity ids are also identical, so appending chapters never renames an earlier entity (append stability). In the positive-control comparison below the alias-binding multisets differ by 2..3 rows (F1 vs F0), which are the volume passes' own bindings.

### Positive control (the probe can see non-causality)
F1 = the standard run with the volume-first passes on, compared with F0 on the same mentions of chapters <= k (mention-level "different target"):

| Serial | k | mentions compared | differ (F1 vs F0) | rate |
|---|---|---|---|---|
| LOTM | 5 / 10 / 20 / 30 | 207 / 452 / 1,140 / 1,806 | 11 / 80 / 411 / 709 | 5.3% / 17.7% / 36.1% / 39.3% |
| ORV | 5..30 | 124..1,480 | 0 | 0% |
| RI | 10 / 20 / 40 / 80 / 120 / 160 | 369 .. 8,941 | 5 / 5 / 5 / 11 / 15 / 18 | 1.4% down to 0.2% |

Reading the classes (gate-vs-engine): LOTM, 709 of the 1,806 mentions of ch <= 30 change entity; every one is a `linked_to_different_entity` (698 GAZETTEER_EXACT, 11 SCORED) produced by `merge_transmigrations`, which rewrites the absorbed body-name entities' mentions into the protagonist's entity. The merge binding is stamped learned-at chapter 1 (first cue chapter), so it is disclosed-consistent in LOTM (no rewrite precedes its binding; this matches the earlier audit's 0 early links for LOTM). RI: all differences are `TITLE_HOLDER` links of 5..18 mentions (the already-known title-holder pass; 5 precede the reader's binding). So the non-causality of the standard pipeline is confined to the two by-design volume passes (backlog A7), now sized: up to 39% of early LOTM mentions are re-targeted by a pass that is disclosure-consistent only because the cue is in chapter 1.

### Limits (what this does not show)
- Mention detection, NER, the commonness profile and the seed lexicon are held fixed (stored mentions); look-ahead in those stages is not measured here (the RI lexicon named in sources.toml does not exist locally, backlog B11, so the seed was used for all runs).
- The two 40-chapter serials have 0 deferred cases, so the window sweep never acts there; RI has 2 deferred. Prefix causality is therefore established for a resolver whose retroactive machinery barely fires on these data (retry_deferred never links, backlog B1).
- No labels: causal does not mean correct.

---

<!-- merged-from: docs/research/ENGINEERING_NOVELTY_PROBE/E2_order_and_batching_sensitivity.md -->
## Source: `docs/research/ENGINEERING_NOVELTY_PROBE/E2_order_and_batching_sensitivity.md`

# E2. Order, batching and re-run sensitivity of incremental resolution (non-negotiable 1)

Status: PRE-DECLARATION written 2026-10-16 BEFORE the confirmatory run. Label provenance: SYSTEM-INTERNAL, scratch copies, CPU only.

## Invariant under test
"No clustering - incremental resolution with evidence accumulation." Incremental methods trade the order-independence of
clustering for causality. The architecture claims (a) re-running `resolve` is a pure function of the stored mentions
(idempotence; T4 v5 measured determinism of one run pair), (b) the 40-chapter window only schedules corrective sweeps and
does not decide links (docs/design/architecture.md Section 6), and implicitly (c) small perturbations of chapter order or
batching do not rewrite the entity set. (c) was never measured. This probe measures it on three real serials.

## Design (stored mentions held fixed, volume passes off so the loop alone is tested)
- Idempotence: resolve the same DB twice in place; compare mention targets.
- Window size: window_size in {10, 20, 40, 10^6} vs the default 40.
- Local order perturbation: swap a random 10% of adjacent chapter pairs (3 fixed seeds) in the order chapters are fed to the loop.
- Extreme control: reverse chapter order (anti-causal ceiling; shows the metric is able to move).
Metrics: same-target rate over all mentions, adjusted Rand index of the mention partition (unlinked mentions = singletons),
entity count change; ids are deterministic from (first surface, first position) so same-target is meaningful, ARI is the id-free check.

## Hypothesis and falsifier (pre-declared)
H_E2: idempotence is exact; window size and a 10% adjacent-swap perturbation change fewer than 1% of mention targets
(ARI >= 0.99) on every serial.
Falsifier: for any serial, disagreement > 1% with the Wilson 95% lower bound above 1% under window size or adjacent swaps,
or any non-zero idempotence disagreement. The reversal control must move the partition (else the probe is blind and nothing is concluded).
Prior expectation: window size changes nothing on LOTM/ORV (no deferrals) and little on RI; adjacent swaps change a small
but non-zero share (alias first-attestation positions and the gazetteer state depend on order). Every disagreement class is
read before it is called a finding.

---
## RESULTS (run 2026-10-16; `scripts/chimera/eng_probe_e2_order_batching.py`; data `data/eval/chimera/eng_probe_E2_<novel>.json`)

Label provenance: SYSTEM-INTERNAL. Reference = default order, window 40, volume passes off.

| Variant | LOTM (2,402 mentions, 93 entities) | ORV (2,267, 59) | RI (11,174, 266) |
|---|---|---|---|
| second `resolve` in place | 0 differ | 0 | 0 |
| window_size 10 / 20 / 10^6 | 0 / 0 / 0 differ | 0 / 0 / 0 | 0 / 0 / 0 (2 deferred cases) |
| 10% adjacent swaps, seeds 0/1/2 (chapters displaced 2/12/10; 2/12/10; 28/42/42): same target id | 0 / 3.7% / 11.2% | 0 / 11.9% / 4.3% | 1.4% / 5.3% / 1.3% |
| ... partition (id-free): mentions moved to another cluster | 0 / 0 / 2 | 0 / 0 / 0 | 0 / 0 / 0 |
| ... ARI | 1.0 / 1.0 / 0.9951 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| ... linked only in the reference | 0 / 0 / 22 | 0 / 0 / 0 | 0 / 0 / 0 |
| control: full chapter reversal, same target id | 90.8% | 96.7% | 94.5% |
| ... partition: mentions moved / ARI / entities | 14 / 0.984 / 91 (ref 93) | 0 / 1.000 / 59 | 41 / 0.985 / 265 (ref 266) |
| ... linked only in reference / only in variant | 22 / 1 | 0 / 0 | 60 / 5 |

### Gate-vs-engine reading
- The pre-declared falsifier used the same-target (id) disagreement. That metric is a **gate artefact for permutations**: entity ids are `sha256(first surface, first position)` of the founding mention (`_stable_entity_id`), so reordering chapters changes which surface founds an entity and therefore its id while the clustering is identical (ORV: 96.7% of ids change under reversal and ARI is exactly 1.0). On the id-free partition metric H_E2 is **not falsified**: ARI >= 0.995 under 10% adjacent swaps and >= 0.984 under total reversal.
- Read the residual order-dependence (the only genuine partition differences): in LOTM seed 2 (22 mentions), LOTM reversal (22 + 1) and RI reversal (60 + 5) the differing mentions are **all `RELATIONAL_DEICTIC`**, linked in the reference by `GAZETTEER_EXACT` (or `RELATIONAL_COPRESENCE`) and unlinked in the variant. A relational deictic ("my sister") is resolvable only after an earlier occurrence has bound it; moving the first occurrence later leaves later ones unresolved. This is the intended causal behaviour of the gazetteer, not a defect.
- Consequence: where order matters at all, it matters for relational deictics only; the order-sensitive mechanism that distinguishes an incremental resolver from a clustering one touches 0.4% to 0.9% of mentions even under chapter reversal (RI 41+, LOTM 14+).

### Verdict
- Re-run idempotence and window-size invariance hold exactly (the window is inert on these serials because few cases are deferred; the 40-chapter serials have none).
- Id stability is **not** order-invariant (ids are position-and-surface derived), which is only a problem if a consumer keys on ids across a re-ordered ingest (not a realistic scenario; appended chapters leave ids unchanged, see E1).
- Interpretation that matters for the research claim: because the partition barely moves under reversal, the "incremental evidence accumulation" is not what decides most links on these serials; see E5 (the exact-match share equals the surface-repetition share, and the partition is within ARI 0.97 to 0.985 of plain normalised-string clustering).

---

<!-- merged-from: docs/research/ENGINEERING_NOVELTY_PROBE/E3_state_of_invariants.md -->
## Source: `docs/research/ENGINEERING_NOVELTY_PROBE/E3_state_of_invariants.md`

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

---

<!-- merged-from: docs/research/ENGINEERING_NOVELTY_PROBE/E4_discourse_position_semantics.md -->
## Source: `docs/research/ENGINEERING_NOVELTY_PROBE/E4_discourse_position_semantics.md`

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

---

<!-- merged-from: docs/research/ENGINEERING_NOVELTY_PROBE/E5_gazetteer_compounding_null_model.md -->
## Source: `docs/research/ENGINEERING_NOVELTY_PROBE/E5_gazetteer_compounding_null_model.md`

# E5. Does the gazetteer "compound"? Null model and an error-side proxy on three serials

Status: PRE-DECLARATION written 2026-10-16 BEFORE the confirmatory run. Label provenance: SYSTEM-INTERNAL (no labels) plus an ambiguity proxy.

## Claim (non-negotiable 8; architecture.md "The compounding gazetteer")
"The system gets cheaper and more accurate as it reads." EVOLUTION 4.77 measured the cheaper half on RI only: the GAZETTEER_EXACT share of
links rose 81% -> 93% over the first two 40-chapter windows then plateaued, with no null model and no accuracy-side measurement.

## Design
Per serial, resolver loop only (stored mentions fixed): per 10-chapter bucket (and per 40-chapter window) compute
(1) exact-match share of link groups and scorer-reached share (cost), with bootstrap-over-groups intervals;
(2) NULL MODEL: the exact-match share expected from repetition alone = share of groups whose normalised surface was already seen in an earlier
group, under the real order and under 20 random chapter permutations; if the real curve is not above the permuted curve at matched
vocabulary depth, "compounding" is memoisation, not a property of reading order;
(3) ERROR-SIDE PROXY: among exact-match links, the share whose normalised surface is held by >= 2 distinct entities in the final graph
(a force-link on an ambiguous surface can only be right for one of them), by depth.
## Hypotheses and falsifiers (pre-declared)
H_E5a: exact-match share rises with depth (Spearman across buckets > 0 with CI excluding 0) on every serial.
H_E5b: the real-order curve exceeds the permuted-order null by more than the permutation 95% band (i.e. narrative order matters).
H_E5c: the ambiguous-surface share of exact-match links does not increase with depth (accuracy side does not degrade).
Falsifier for the "cheaper AND more accurate" claim: H_E5a fails, or H_E5b fails (curve explained by repetition alone), or H_E5c fails.
Prior expectation: H_E5a holds on RI and fails or is weak on 40-chapter LOTM/ORV; H_E5b likely fails (repetition explains most);
H_E5c unknown. Reported either way.

---
## RESULTS (run 2026-10-16; `scripts/chimera/eng_probe_e5_gazetteer_compounding.py`; data `data/eval/chimera/eng_probe_E5_<novel>.json`)

Label provenance: SYSTEM-INTERNAL. Unit = a link group (chapter, local group), 372 to 1,603 per serial; five equal-sized bins in reading order.

| | LOTM (453 groups) | ORV (372) | RI (1,603) |
|---|---|---|---|
| GAZETTEER_EXACT share by fifth | .44 .56 .61 .75 .66 | .62 .81 .85 .91 .88 | .68 .79 .80 .76 .81 |
| scorer-reached share by fifth | .37 .27 .12 .14 .12 | .34 .18 .12 .05 .11 | .21 .14 .15 .19 .14 |
| Spearman(exact, reading position), bootstrap 95% | 0.19 [0.11, 0.29] | 0.22 [0.12, 0.33] | 0.07 [0.02, 0.12] |
| share of groups whose surface was linked earlier ("seen before") by fifth | .46 .56 .61 .79 .66 | .62 .81 .85 .91 .88 | .69 .79 .80 .76 .81 |
| exact-match groups whose surface was NOT seen before | **0 of 274** | **0 of 303** | **0 of 1,232** |
| seen-before groups that were exact matches | 274 / 279 | 303 / 303 | 1,232 / 1,238 |
| fifths where the real "seen-before" share lies outside the 200-permutation chapter-shuffle 95% band | none | none | fifth 1 (higher than null) and fifth 4 (lower) |
| exact-match links whose surface is held by >= 2 entities in the final graph | 5 of 274 (fifths 2 and 3) | 0 | 0 |

### Reading (gate-vs-engine)
- **GAZETTEER_EXACT is identical to "this normalised surface was linked before"** (zero exceptions on one side, 5 to 6 on the other, all three serials). So the "cheaper as it reads" curve is a memo-table hit rate. It rises because names repeat; H_E5a holds (positive trend on all three, weak on RI because it plateaus after the first 50 chapters, as EVOLUTION 4.77 found), but H_E5b is not supported: on LOTM and ORV the real curve is indistinguishable from the same groups with chapters shuffled, and on RI the real order is *flatter* than shuffled (higher early, lower late), i.e. reading order adds nothing and, on RI, slightly hurts after the first third.
- The accuracy side: no evidence of deterioration (H_E5c holds: ambiguity proxy 0 of 1,232 on RI, 0 of 303 on ORV, 5 of 274 on LOTM), but this proxy cannot detect a wrong link on an unambiguous surface, and there are no labels. "More accurate with depth" is untested, not supported.

### String-identity baseline (id-free, no labels)
Partition of the resolver's linked mentions versus the partition by the repo's own `comparison_key(text)`:

| | LOTM | ORV | RI |
|---|---|---|---|
| linked mentions | 2,334 | 2,262 | 11,092 |
| distinct normalised surfaces / entities | 106 / 93 | 64 / 59 | 289 / 266 |
| surfaces held by more than one entity | **1** | **0** | **0** |
| mentions in a non-dominant surface of their entity (alias-merged) | 106 (4.5%) | 63 (2.8%) | 522 (4.7%) |
| ARI vs surface-key partition | 0.985 | 0.971 | 0.971 |

So 95 to 97% of mention-to-entity assignments are exactly "same normalised string, same entity", the resolver never splits a surface across entities except 1 surface (4 of 2,334 mentions) in LOTM, and everything that is not a string lookup is the 3 to 5% of mentions that join an alias to an entity. The architecture's motivating case, "two mentions may be character-identical yet denote different people" (architecture.md Section 2), is realised 0, 0 and 1 times in the output graphs. No claim about correctness: if the serials contain homonymous characters the resolver collapses them (precision is not measured), and if they do not, the case is vacuous on these data.

---

<!-- merged-from: docs/research/ENGINEERING_NOVELTY_PROBE/E6_persona_stage_prefix_causality.md -->
## Source: `docs/research/ENGINEERING_NOVELTY_PROBE/E6_persona_stage_prefix_causality.md`

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

---

<!-- merged-from: docs/research/ENGINEERING_NOVELTY_PROBE/SUMMARY.md -->
## Source: `docs/research/ENGINEERING_NOVELTY_PROBE/SUMMARY.md`

# Engineering-weakness probes: summary (2026-10-16)

All probes are system-internal or synthetic (no human labels), CPU only, on scratch copies, with a pre-declared hypothesis and falsifier written before the confirmatory run (the first section of each note). Scripts: `scripts/chimera/eng_probe_*.py`; results: `data/eval/chimera/eng_probe_*.json`; regression tests for E3: `scripts/chimera/test_eng_probe_e3_state_of.py`.

| Probe | Claimed invariant | Result | Genuine weakness? | Publishable as a finding? |
|---|---|---|---|---|
| E1 prefix causality of the resolver (real serials) | decisions at chapter c depend only on chapters <= c | **holds**: 0 of 28,165 mention-cut pairs differ (14 cuts, 3 serials), ids stable; the by-design volume passes break it (up to 39% of early LOTM mentions) | No (a positive property); the volume passes are known (A7) and are now sized | Weak alone: a verified negative; useful as the positive control for E6 |
| E2 order / batching / re-run | incremental resolution is stable under perturbation | **holds on the partition** (ARI >= 0.995 under swaps, >= 0.984 under chapter reversal; window size inert; re-run exact); ids are order-dependent; residual order effect is only relational deictics | No | Supporting evidence for E5 |
| E3 `state_of` invariants (synthetic) | bitemporal filters, retraction != interval end, observer scope | core filters **hold**; gaps: persona bindings ignore truth/retraction, retraction is observer-global, off-MAIN default is omniscient, VOIDED-on-MAIN wipes the graph, attribute ties are order-dependent | Yes, but latent: no real-data instance | Observer-global retraction is a modelling point; the rest is engineering |
| E4 discourse-position semantics (real) | DiscoursePosition is a total order | **violated**: same-chapter order agrees with text order only 47-58% (random is 50%); offset is block-relative; granularity differs by writer | Yes (data-model integrity), no downstream error today (all queries are chapter-level) | Engineering finding |
| E5 gazetteer compounding + string baseline (real) | the system gets cheaper and more accurate as it reads | exact-match share **equals** the share of surfaces linked before (0 exceptions on 1,809 exact groups); curve is within a chapter-shuffle null; resolver partition is within ARI 0.97-0.985 of normalised-string clustering; 0-1 homonym splits | The compounding claim is memoisation, not a reading-order effect | Best candidate (see report), combined with E2 |
| E6 persona-stage prefix causality (real) | state_of(READER, k) equals the graph built from chapters <= k | **violated**: 23 of 288 (8.0%) characters-cuts have a differing fact; 46% of the cast after LOTM ch5; gender via later pronoun evidence, body splits via a whole-volume "life after" rule | Yes (backlog A6, now measured) | Best candidate with E1 as an audit protocol |
