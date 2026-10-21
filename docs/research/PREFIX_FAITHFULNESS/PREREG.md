# Pre-registration: evidence-horizon honesty of the persona stage

Written 2026-10-16 BEFORE any run of the scripts in `scripts/prefix_audit/` and before any edit to `persona/build.py`. Branch `claude/prefix-faithfulness` (worktree). Label provenance: **SYSTEM-INTERNAL (no labels)**. The oracle is the system itself rebuilt on truncated input. CPU only, deterministic persona mode (`client=None`), `ECHOTALES_LLM_MODE=stub`, $0 spend. Scratch copies only; the canonical `data/db/*.db` files are copied with the SQLite backup API and never opened in place (they have live `-wal` files).

Relation to existing work. `docs/research/ENGINEERING_PROBES.md` measured the dynamic divergence (23 of 288 character-cuts) on a first run. This note does not re-claim that. It adds (a) a static certificate, (b) a repair, (c) the cost of the repair. Anything below that restates E6 is a replication check, labelled as such.

## Definitions

- A *fact* is one `(entity, key)` persona trait with the value `state_of(READER)` serves.
- Its *stamp* is the `learned_at_pos` the store holds. Today `persona/build.py:286` writes `entity.first_attested_pos` for every trait.
- Its *evidence horizon* `h(f)` is the latest chapter among the inputs the value was computed from.
- A fact is *honest* iff `stamp >= h(f)` (chapter granularity). It is *exposed* at cut `k` iff `stamp <= k < h(f)`: visible to a reader who has read chapters up to `k`, but computed from chapters the reader has not read.
- A fact *diverges* at cut `k` iff the value `state_of(READER, k + 0.5)` returns from the full-volume graph differs from the value the same query returns on the graph rebuilt from chapters `<= k` only (the E6 oracle, same query convention).

Inputs per trait, derived by reading `persona/build.py` and `persona/traits.py` (line references are in the report):

| key | reads | horizon |
|---|---|---|
| gender, age_band, register, archetype | surface forms and narration passages from the first 12 chapters where the entity is attested | `max(first 12 attested chapters)` |
| big_five (extraversion) | dialogue lines in those 12 chapters, and the whole-volume `mention_count`, but only if dialogue lines > 0 | last attested chapter if dialogue > 0, else `max(first 12)` |
| trait_provenance | constant | stamp |
| body split (`SelfPersonaBinding`) | `find_change_candidates` requires attestation after the change, counted over the whole volume | last attested chapter |
| `self_entity.prominence` column | whole-volume mention count; **has no stamp at all** | out of the store's temporal model |

## Hypotheses and falsifiers (declared now)

**H1 (soundness of the certificate).** Every dynamic divergence lies inside an exposure window. Falsifier: any `(entity, key, k)` that diverges while `stamp >= h(f)` or `k >= h(f)`. By construction this should hold if the resolver is prefix-causal (E1) and the dependency table above is complete, so a violation means the table is wrong or E1 is wrong; it is a check on the audit harness, not a discovery, and I will report it as such.

**H2 (usefulness of the screen).** The exposed share of `(fact, cut)` pairs is reported with the share of exposed pairs that actually diverge (precision of the screen as a divergence predictor). I expect low precision (most exposed facts keep the same value); no threshold is pre-declared because the quantity is descriptive. If precision is below 10% the report says the certificate is a necessary-condition screen and not a predictor.

**H3 (repair).** After the repair, the E6 harness (same 13 cuts: LOTM 5/10/20/30, ORV 5/10/20/30, RI 10/20/40/80/120) shows **0 trait divergences of 288 pairs** for gender, age_band, register, archetype and big_five. Falsifier: any trait divergence. Any residual is traced to a code path before it is called a finding.

**H4 (cost).** The repair has an availability cost: facts become visible later. Reported, not thresholded: (i) share of person entities with `gender = unknown` at the end of chapter `k`, original versus repaired, per cut; (ii) number of attribute rows, original versus repaired; (iii) wall-clock of the persona stage. A cost large enough that a voice would be uncastable at a cut is stated as such.

**Scope limits declared now (not to be softened afterwards).**
1. Body-split divergences (E6: 7 persona-id-set differences) are **not** repaired. `state_of` unions concurrent persona bindings and has no supersession for them, so a late-confirmed split cannot be stamped honestly without a core change. They are measured and reported as an unrepaired limit.
2. The `prominence` column is reported as unstamped derived state and is not repaired.
3. The LLM trait path (`client != None`) is not repaired and not measured here; every number is for the deterministic path.
4. Chapter granularity: a revision computed from chapter `c` is stamped at the end of chapter `c`, so a trait about a character introduced mid-chapter `c` is not visible before the end of that chapter. That is an intended cost, counted in H4.
5. Three serials, one system. This is an audit plus a design rule, not a general law about narrative knowledge graphs.

## Amendment 1 (2026-10-16, before any result exists): resolution is held fixed

The first smoke run failed with `TypeError: resolve_novel() got an unexpected keyword argument 'chapters'`. At this worktree's HEAD (`6c7e2c2`) `resolve_novel` has no `chapters`, `prefix_volume_passes`, `causal_titles` or `apply_deferred_links` parameters, and always runs the whole-volume title-holder and transmigration passes. E1 and E6 ran against the other session's **uncommitted** edits of `resolve/runner.py` (a diff of the two files shows the B1 deferred-link fix, the B2 `chapters` filter and the A7 prefix switches). Re-resolving a truncated copy here would therefore test a different resolver than E6 did, and copying the other session's uncommitted code into this branch would entangle the two lines of work.

Change: the audit does **not** re-resolve. Both graphs start from the same stored mention-to-entity assignment (the canonical databases' `mention.target_id`). The prefix graph is that database with every `chapter`, `span`, `mention` and `narrative_segment` row after chapter `k` deleted, then `build_personas` is run. The audit therefore tests the **persona stage in isolation, conditional on a fixed resolution**, which is the stage the claim is about; the resolver's own causality is E1's result and is not re-tested here. Entities with no mention at or before `k` are excluded from the comparison (they have no evidence in the prefix).

Consequence for the replication check below: the baseline is no longer expected to equal E6's counts exactly, because E6's full graph came from a fresh resolution with the volume passes off and mine uses the stored one. The difference is reported, not tuned away.

## Replication check (not a hypothesis)

With the repair switched off, I report my baseline next to E6's published numbers (23 of 288 trait divergences; 7 persona-id-set differences) and the difference between them. I do not adjust the harness to match.

## What would make me drop the claim

If H3 fails with residuals that are not traceable to the stages declared out of scope, the repair claim is dropped and the report is an audit only. If the exposed share of facts is very small (say under 5% of `(fact, cut)` pairs at every cut beyond chapter 20), the practical significance of the certificate is small and the report says so.
