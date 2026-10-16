# Pre-registration M3b: title-holder temporal model on synthetic worlds (version 1)

Written and frozen **before the M3b code exists or runs**. Repo HEAD `6c7e2c2`, 2026-10-15. Hash in `MANIFEST_M3.json` (second entry). Labels are by construction from the world spec (synthetic); no model, no human, no novel text, no spend.

## 1. Question

The shipped title-holder pass starts the first holder's tenure at chapter 1 and links earlier title mentions backward (by design, volume-first). Does a bitemporal tenure model, which keeps that story-time interval but stamps each link with the position at which the reader is told, give the right answer under **both** the reader view and the omniscient view, where a causal-only model and the volume-first model each fail one view? TAC-KBP temporal slot filling already covers the representation of tenure intervals; this test is about the two-view behaviour on mention links, not a claim of a new tenure model.

## 2. Worlds and oracle

The 40 SIO v1 worlds (seeds 0 to 39), unchanged, from `sio_synthetic_oracle.make_world` (no new generator). Title mentions only: `title_pre` (even seeds, chapters 1 and 2, before the holder is declared), `title_post` (odd seeds, chapters 1 and 2, after declaration), and the chapter 8 mention (holder H2). Oracle (spec only): omniscient = the holder at that story time; reader view = UNDETERMINED for `title_pre`, the declared holder otherwise. n = 120 title mentions (40 chapter-8 plus 80 in chapters 1 and 2).

## 3. Systems (deterministic, CPU)

Holder declarations are harvested from the world text with the pattern `Clan head <Name> rose` (the generator's declaration phrase) together with the first plain-name mention of that holder.
- **V (volume-first):** a tenure starts at chapter 1 for the first holder, a later holder starts at the first declaration; every title mention gets the holder of its position (the shipped behaviour).
- **C (causal-only):** the holder is the latest holder declared at or before the mention position; before any declaration the mention is unlinked.
- **B (bitemporal):** keeps V's story-time interval and stamps `learned_at` = position of the first declaration; the **reader view** returns the holder only if `learned_at <= mention position`, otherwise unlinked; the **omniscient view** returns the story-time holder.
Also scored for reference: the shipped resolver's own title links (S0 from `resolve_novel`).

## 4. Metrics (Wilson 95%)

Reader-view accuracy (unlinked correct for `title_pre`, holder correct otherwise); omniscient accuracy; premature rate (a `title_pre` mention linked to its eventual holder in the reader view); and a TAC-KBP-style tenure score: for each world, the mean of 1/(1+|ti - gi|) over (T1 start-lower, T2 start-upper, T3 end-lower, T4 end-upper) for the first holder against the spec tenure, reported for story time (V, B) and reader time (C, B).

## 5. Decision rules (fixed now)

- **R1**: V has premature = 100% of `title_pre` mentions and omniscient accuracy 100%; C has premature = 0 and omniscient accuracy below 100% (it cannot answer the omniscient view on `title_pre`); B has both 100%. If not, the model or the oracle has a bug and is reported.
- **R2**: the shipped resolver's links agree with V on the title mentions it links (cross-check of the harvest).
- **R3**: the result is true by construction for the designed systems; what it shows is that one stamped link serves both views, and that the defect in the product is the missing stamp on the per-mention link (the binding itself is already bitemporal).

## 6. What may be claimed

Only that a bitemporal stamp on the link serves both views on these synthetic worlds. **Not** claimed: a new tenure model (TAC-KBP covers tenure intervals), real-text performance, or novelty. This result is Track S.

## 7. Deviations log

None at freeze.
