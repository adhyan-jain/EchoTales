# Pre-registration: counterfactual-suffix test of the persona stage (written 2026-10-17, before any flipped build exists)

**Seen before writing:** every result in REPORT.md (4.1 to 4.16), the stored truncate-and-rebuild rows of `audit_repair-off_<serial>.json` and `audit_repair-on_<serial>.json`. No build with a modified suffix has been run.

## Why

Truncate-and-rebuild compares the full build with one other volume, the prefix. The definition of reader-faithfulness (paper 3.1) quantifies over *every* volume with the same first k chapters. A served value can depend on chapters after k and still equal the prefix value on this book: the persona stage reads up to twelve attested chapters for gender, and in 80 exposed gender cuts the prefix already held the final value (REPORT 4.6). Truncation scores those as "no divergence". A **counterfactual suffix** keeps chapters <= k byte-identical and changes only what comes after. Here we swap the gendered pronouns, and check whether the value served at k moves. It tests dependence, not divergence. It needs no truncation and no labels, and it works on a closed-vocabulary output (male, female, unknown), where a string canary (RF-E2E addendum 12) can never appear. FORMAL P10 notes that canaries need a copying channel.

## Intervention

On a throwaway copy of each serial's store (`scripts/prefix_audit/common.py`), for every span with `chapter > k`, swap third-person pronouns case-preservingly at word boundaries: he<->she, him->her, his->her, himself<->herself, her->him, hers->his. Nothing else changes: mentions, targets, chapters <= k, and stored resolution are kept (resolution held fixed, as in the audit). Then delete persona and attribute rows and run `build_personas` on the **whole** volume.

## Comparison

For each of the original 13 cuts (LotM and ORV 5/10/20/30; RI 10/20/40/80/120) and each person entity with a persona in both builds, compare `state_of(READER)` gender at position k + 0.5 between the unmodified full build and the flipped full build. A **flip** is a change of the served value. Run with the stage unrepaired (default) and repaired (`prefix_causal=True`).

## Hypotheses

- **H14.1 (the oracle agrees with truncation where truncation finds a leak).** Among the 23 unrepaired gender cuts that diverge under truncate-and-rebuild, at least 70% flip.
- **H14.2 (dependence the truncation oracle cannot see).** The unrepaired stage flips on at least one gender cut that does **not** diverge under truncate-and-rebuild; the count is reported with the split by prefix value (already final versus unknown).
- **H14.3 (screen soundness under a second oracle).** No unrepaired cut outside its exposure window (stamp <= k < horizon, audit.py) flips. Any flip outside the window falsifies the hand-derived read set on real data.
- **H14.4 (the repair's guarantee, FORMAL P6).** The repaired stage flips on 0 cuts.
- **Descriptive.** Flips on the other traits (age band, register, archetype, big_five) for both builds.

Cost: CPU only, no model, no labels. Label provenance: SYSTEM-INTERNAL.
