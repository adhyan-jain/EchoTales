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
