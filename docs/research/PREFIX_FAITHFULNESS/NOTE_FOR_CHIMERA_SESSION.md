# Note for the CHIMERA session (read before merging or re-running E1/E6)

Written 2026-10-16 by the prefix-faithfulness session. I have not edited anything in your files, your directories, or the main checkout. Everything of mine is on branch `claude/prefix-faithfulness`, worktree `.claude/worktrees/prefix-faithfulness`, uncommitted.

## 1. A reproducibility risk in your engineering probes

E1 and E6 (and E2/E5) only run against edits that are **uncommitted** in the main checkout: `resolve/runner.py` (the `chapters`, `prefix_volume_passes`, `causal_titles` and `apply_deferred_links` parameters, B1/B2/A7) and `resolve/title_holders.py`. `scripts/chimera/eng_probe_*.py` and `data/eval/chimera/eng_probe_*.json` are untracked. At HEAD (`6c7e2c2`) `resolve_novel()` has none of those parameters, so a fresh checkout cannot run the probes and the numbers in `ENGINEERING_NOVELTY_PROBE/` cannot be reproduced from the repository. I found this because the first smoke run of my audit failed with `TypeError: resolve_novel() got an unexpected keyword argument 'chapters'`. If those edits are meant to be kept, commit them (the owner rule is no commit/push without the owner, so this is for the owner to decide); if not, the E-notes should say they depend on a working-tree state.

## 2. What overlaps and what does not

- My changes touch `packages/pipeline/src/echotales/pipeline/persona/build.py` and `packages/core/src/echotales/core/store.py` (one additive method). Neither is in your modified list. No overlap with `canon.py`, `commands.py`, `panels.py`, `runner.py`, `title_holders.py`, `context.py`.
- The default behaviour of `build_personas` is unchanged: a new `prefix_causal=False` keyword. Checked by hashing every persona-stage row on ORV from this branch and from the main checkout's unmodified `build.py`: 232 rows, identical SHA-256 prefix.
- The audit holds your stored mention assignment fixed, so it does not depend on your uncommitted resolver edits and does not re-test E1.

## 3a. Update (end of 2026-10-16): use REPORT section 0 and the updated paragraph in section 8, not the numbers in 3

Later work changed the headline. With two model annotators (no human labels) the divergence is 6.0% of 685 character-cuts, of which 1.7% to 3.5% of all character-cuts are genuine premature disclosures; the repair is safe rather than correct; a pre-registered anchored cue and a prefix-causal model gate recover most of the price (REPORT 4.11, 4.15); a second text domain and a synthetic known-truth volume reproduce the defect (4.13, 4.14). One point for your report: all new code is off by default (`prefix_causal`, `anchored_gender`), the default path is byte-identical, and nothing outside `persona/build.py`, `persona/traits.py` and one additive `Store` method was touched. I spent $0.1140 of OpenAI `gpt-5.6-luna` calls in total (the owner's instruction to use Luna, then the owner's $0.20 extra grant); this is separate from your $0.2824 and is not in your ledger. The GPU was shared with your runs: my model-path runs waited for quiet windows and never unloaded a model that was not mine.

## 3. Numbers you can cite (first pass; all system-internal, no labels; superseded by 3a where they differ)

E6's headline replicates on a different harness: 23 of 289 character-cuts (E6: 23 of 288), all gender plus derived archetype, 7 body-split differences, 0 for age_band, register, big_five. New: 139 of 289 cuts are exposed to later evidence, 0 divergences fall outside the window, a revision-by-evidence-horizon repair gives 0 of 289, and hiding every exposed fact gives 82 of 289 (worse than the 23 it started with). A paste-ready paragraph is in `REPORT.md` section 8. One framing point for your report: E6's "persona stage is not prefix-causal" is also a second, independent instance of the premature-disclosure problem your premature-resolution metric measures, at the trait layer instead of the identity layer.

## 4. GPU

I did not use it. At the time of writing it was at 6.5 of 8 GB with an `ollama runner` that is not mine, which I assume is yours. `scripts/prefix_audit/llm_audit.py --backend model` refuses to start unless `PREFIX_AUDIT_ALLOW_GPU=1` is set and the GPU is under 35% used with no runner active. It needs about 360 short model calls in total.

## 5. Not done, so you do not assume it was

`docs-sync` (it edits HANDOFF, EVOLUTION, README, which you also edit), any commit or push, the real-model LLM audit, the observer-relative retraction extension, any change to your gold, silver or pilot files.
