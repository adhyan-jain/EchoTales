# Effect of routing titles and shared alias keys through the resolve gate (RI)

Change under test: commit 956a6d7 (`gazetteer_exact_match` no longer forces a LINK for
TRANSFERABLE_TITLE / RELATIONAL_DEICTIC / PATHWAY_TITLE / TAROT_TITLE surfaces or for an alias key
held by more than one entity; plus zero-weight name-order / romanization retrieval candidates).

## Method
- Two copies of `data/db/reverend-insanity.db` (199 chapters, 11,174 mentions) in `data/scratch/reruns/`
  (`ner_gate_before.db`, `ner_gate_after.db`; scratch, not committed). Canonical DB untouched.
- `echotales --db <copy> resolve --novel reverend-insanity`, whole novel (about 1 minute each), run with
  base 8a4fb22 (temporary worktree) vs this branch. `ECHOTALES_LLM_MODE=stub`.
- **Stub-mode caveat:** the LLM adjudicator is a no-op on both sides, so this is a controlled
  comparison of the deterministic scorer + gate only. With a live adjudicator, some of the newly
  deferred mentions could be resolved, so the DEFER rate here is an upper bound.
- Per-mention diff by mention id (same 11,174 ids in both); detail: `data/eval/ner/gate_change_ri_changed_mentions.json`.

## Results
| | before | after |
|---|---|---|
| entities | 267 | 267 |
| groups linked / new / deferred | 1,259 / 266 / 2 | 1,207 / 266 / 3 |
| deliberately deferred (deictic, no entity) | 76 | 127 |
| escalated to review (DEFER rate) | 2 (0.12%) | 2 (0.12%) |
| mentions with a target | 11,122 | 11,070 |
| GAZETTEER_EXACT links | 1,232 | 1,173 |

- Mentions whose target changed: **52 of 11,174 (0.47%)**. All 52 went from SELF (Fang Yuan) to no
  target; none moved to a different entity, no entity was split or created.
- All 52 are RELATIONAL_DEICTIC surfaces: "sir" 45, "this one" 5, "my lord" 2.
- Review queue unchanged (2 `resolve_deferred` items); escalation rate unchanged at 0.12%.
- `scripts/eval/hardcase_resolution.py` (offline, silver refs): output identical before/after
  (ALL 88: 21 correct, 0 wrong, 0 unresolved, 67 not-detected, exact alignment). The 52 changed
  mentions are not in its gold, so it cannot see this change.

## Verdict
No wrong splits of real characters: entity count, review queue and every named-mention link are
unchanged. The change removes forced merges. Spot check: ch.15 "Sir Flower Wine" and "Sir, please spare
my worthless life!" were all force-linked to Fang Yuan before. The first is a different character, and
a bare "sir" is relative to the speaker/addressee, which the gazetteer cannot know. Not every one of the
52 was wrong ("this one" is often Fang Yuan speaking), so some correct links are now unlinked; that is
a recall cost for 52 mentions, which downstream speaker/addressee logic may recover. Only 52 of 125
deictic mentions in the novel were affected. Not human-checked beyond the spot sample.
