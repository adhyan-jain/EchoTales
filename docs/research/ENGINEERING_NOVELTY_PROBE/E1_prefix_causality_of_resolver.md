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
