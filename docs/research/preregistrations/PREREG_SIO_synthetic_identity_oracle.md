# Pre-registration SIO: synthetic identity-reveal oracle (version 1)

Written and frozen **before the world generator or any resolver run exists**. Repo HEAD `6c7e2c2`, 2026-10-15. Hash recorded in `MANIFEST.json` before anything runs. A change is a new version file.

**Provenance of the design.** The Checkpoint 2 owner message asks for a "synthetic-world oracle test" and points to `ECHOTALES_NOVELTY_REPORT_PROMPT.md`, which does not exist anywhere on this machine. This is **my interpretation**, built from the Checkpoint 1 requirement for "an independent oracle where feasible, deterministic fixtures (long-range references, ambiguous aliases, progression, true-before-disclosed ...)" and from the existing, different state-admissibility oracle in `technical_contribution_probes/`. It is open to correction as soon as the prompt file is supplied; if the owner's definition differs, this becomes SIO v2.

## 1. Question

On synthetic stories whose identity structure is known exactly, (a) is the repo's deterministic resolver **prefix-causal** (does a decision about a mention at chapter c depend only on chapters <= c), and (b) does it **link prematurely** (does it link an alias to its post-reveal identity before the story discloses it)? This tests **properties of the mechanism on synthetic input, not real-world performance**.

## 2. World generator (frozen specification)

A world is built from a seed in `0..39` (40 worlds, no seed selection, no extra seeds).

- 12 chapters; 6 named characters with unique invented names (single-token and two-token, some sharing a family token so containment relations exist); 2 places; text from fixed English templates.
- **Reveal R (2 per world):** character X appears first under a deictic or title alias A ("the masked guest", "the stranger") in chapters `a..r-1`, co-present with exactly one named character; at chapter `r` (`r >= a+2`) a sentence discloses that A is the already-named character Y ("The masked guest was, in truth, Y"). Before `r` the reader-warranted referent of A is UNDETERMINED; from `r` it is Y. Omniscient referent is Y throughout.
- **Title transfer (1 per world):** the title "the clan head" is held by H1 in chapters 1-4 and by H2 from chapter 5; mentions of the bare title appear in both ranges; the holder is named in the **same or a later** chapter than some earlier mentions in half the worlds (so retroactive linking is possible by design), and the first mention precedes the first naming in the other half.
- **Plain controls:** named-character mentions with an unambiguous referent.
- Mentions are supplied **directly by the generator with exact offsets** (perfect detection), so any error is attributable to resolution, not detection. Reference mode PRESENT, alias types RIGID_NAME / TRANSFERABLE_TITLE / RELATIONAL_DEICTIC as appropriate. The text of each chapter is stored as a single prose block.

## 3. Oracle (independent)

The oracle reads **only the world spec**, never a Store, `state_of`, or resolver output. For each mention it returns:

- `reader_warranted(m)`: the referent at the cut (end of the sentence containing the mention): UNDETERMINED for a pre-reveal alias, the revealed Y for a post-reveal alias, the current holder of a title as the reader has been told it, the named character for plain names.
- `omniscient(m)`: the true referent over the whole story.

## 4. Systems and runs

- **F (full run):** `resolve_novel` default (no LLM) on the whole world.
- **P_c (prefix run):** for each reveal chapter r, a separate fresh in-memory store containing only chapters `1..r-1` (pre-reveal prefix) and one containing `1..r`, resolved independently. For title worlds, prefixes at chapter 4 and chapter 5.
- The resolver is called exactly as in the existing tests (`Store(":memory:")`, `add_novel`, `add_chapter`, `add_mentions`, `resolve_novel`). The lexicon is the generic default with no per-novel title or declaration entries unless the generator's templates need a declaration pattern the repo's lexicon already supports; if so it is the repo's, not a custom one.

## 5. Metrics (all per mention, then Wilson 95%)

- **M1 prefix-invariance violation rate:** among mentions in chapters `<= c`, the share whose resolved target label or resolved/unresolved status in **F** differs from its status in **P_c**. Zero means the resolver is causal on these worlds.
- **M2 premature-resolution rate:** among pre-reveal alias mentions (oracle: UNDETERMINED), the share that F links to the post-reveal identity Y. Reported separately for P_c, where the answer must be 0 (the prefix run cannot know Y); a nonzero P_c value would mean the resolver invents Y from surface features.
- **M3 post-reveal miss rate:** among post-reveal alias mentions, the share not linked to Y in F.
- **M4 retroactive title link rate:** among title mentions that precede the first naming of the holder, the share F links to a holder not named in the prefix.

## 6. Decision rule (fixed now)

- If **M1 = 0 and M2(F) = 0 and M4 = 0** on all 40 worlds: report "the resolver is prefix-causal on these synthetic structures"; this does **not** transfer to real text, and the known whole-volume passes (`link_title_holders`, `merge_transmigrations`) are then shown to be inactive on this generator, which must be stated.
- If **M1 > 0 or M4 > 0**: report as a demonstrated property failure with the counterexample worlds and the code path (`resolve/title_holders.py`, `resolve/transmigration.py` per the audit). This is the **expected** outcome for title worlds; the pre-declared prediction is M4 > 0 in the "first mention precedes first naming" half, and M1 = 0 in the reveal worlds. A result against this prediction is reported as such.
- Does not kill or keep C1 by itself. It supports or weakens the audit claim that the resolver "cannot run causally" and, if M2(F) > 0, supplies a controlled demonstration of premature resolution that T3 and the labels would then need to confirm on real text.

## 7. Power statement

40 worlds x 2 reveals = 80 reveal items and 40 title items. With 0 violations of 80 the Wilson 95% upper bound is 4.6%; with 8 of 80 the interval is [5.2%, 18.5%]. It cannot detect violation rates below about 4%, and it cannot speak for text that is not generated by these templates.

## 8. Scope limits

Synthetic fixtures validate properties, not real-world performance (Checkpoint 1, Gate 5 rule). No claim from this test goes into a result about RI/LOTM/ORV. It tests the resolver, not the detector, not state_of, and not any LLM.

## 9. Deviations log

None at freeze.
