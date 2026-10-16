# Handoff: prefix-faithfulness work (2026-10-16)

Branch `claude/prefix-faithfulness` (worktree `.claude/worktrees/prefix-faithfulness`, base `6c7e2c2`). **Nothing is committed.** Read `REPORT.md` section 0 first; this note is the index, not a second report. Label provenance matters everywhere: sections 4.1 to 4.8 have no labels, 4.9 to 4.12, 4.14, 4.16 use model-generated labels (two annotators, **no human labels**), 4.13 is synthetic.

## 1. Claims that stand, with their evidence

| Claim | Evidence (REPORT section; data in `data/eval/prefix_audit/`) |
|---|---|
| A trait stamped at first sighting but computed from up to 12 later chapters makes the served gender differ from a prefix-only build. 8.0% of 289 character-cuts first pass; **6.0% of 685** with 11 added cuts (4.5% to 8.0% by cut placement). | 4.1, 4.10; `audit_repair-off_*`, `audit_dense-off_*` |
| It reproduces outside the original serials: 4.5% of 179 on two English originals; 9% to 17% of pairs on a synthetic volume with known truth (no annotator). | 4.14, 4.13; `labels_summary_pd.json`, `synthetic/` |
| Reader-visible harm is smaller: premature disclosure is **2.0% to 2.6%** of character-cuts for the model reader (1.7% by my own labels on the original cuts); the rest of the diverging values were already supported by the text. | 4.10, 4.12; `labels_summary_v2.json`, `labels_summary_permissive.json` |
| The horizon repair gives exactly 0 divergence in every run (0 of 685 gender pairs and 0 of 3,425 trait rows, 0 of 179, 0 in each synthetic configuration). It is safe, not correct, and withholds about 1 to 4 text-supported values per spoiler removed. Hiding exposed facts is worse than doing nothing (82 vs 23 of 289). | 4.4 to 4.6, 4.10; `FORMAL.md` P1 to P6 |
| Pre-registered **H5**: an anchored pronoun cue under the same horizon recovers 97% of the lost values at 1.2% wrong on the web novels, with the same setting chosen in every leave-one-serial-out fold and with each annotator alone as reference. | 4.11; `anchored_summary*.json` |
| Pre-registered **L4**: a prefix-causal prominence gate removes the model path's gate effect (50 to 0 of 296 pairs, 0 divergences in 101 both-model pairs, noise floor 0, calls unchanged at 348, real `qwen2.5:7b`). | 4.15; `llm_model_pc_*.json` |
| Synthetic mechanism and failure map (the cue's wrong rate exceeds 3% only when own cues are sparse and misleading cues are at least half as common). | 4.13 |

Tests: core and pipeline suites passed at 1259 passed, 6 skipped before the v2 window test was added; the two persona test files pass afterwards (34 tests). All new behaviour is off by default and the default path is byte-identical (366 ORV rows reproduced exactly).

## 2. Documented failures and corrections (keep them in any write-up)

- **PD3 not supported (REPORT 4.14).** On the English originals the cue's wrong rate was 7.8% against a pre-registered 3% bar. The base extractor alone is 6.7% wrong there (three women called male in every build: Charlotte, Mrs. Bedwin, Kitty), the cue's own errors are one character (Milady, 3 pairs), and its precision on added values was 8 of 11 against 34 of 35 on the web novels.
- **H6 not supported at `(1, 0.8)` (REPORT 4.16).** A v2 window was supported at `(2, 0.8)` and failed at `(1, 0.8)` because a one-pronoun cue overrode a correct honorific value (Mother Shen, three cuts). Window v1 stays the recommended one. The English books were used to design v2, so they are a development set, not evidence.
- **`FORMAL.md` P8 amended.** The claim that a fallback cannot change what the base serves holds only if the fallback fills an `unknown`; the implemented cue can override an honorific.
- Smaller, all in the pre-registrations: the unknown share of the combined reference is 31%, above the declared 25% limit, so correctness results are flagged as a subset; the synthetic S2 "recovered fraction" is degenerate and not quoted; `PREREG_LABELS.md` records Deviation 1 (the prefix-label rule decided after reading the sheets) and Addendum 2a (the 80% quote check, after a 3-call smoke test).
- Not measured or not repaired: body splits (7 of 296), appearance and world facts, any human verification. `labels/human_check.csv` (30 characters, model labels hidden) is unfilled.

## 3. Dependence on the other branch's uncommitted resolver edits

**My results do not depend on them.** `PREREG.md` Amendment 1: the audit never re-resolves; it holds the stored mention-to-entity assignment fixed and tests the persona stage in isolation. E6 replicated on that basis (23 of 289 against E6's 23 of 288).

**The other session's E1 and E6 do depend on them, and a joint paper that cites E1 inherits the problem.** At HEAD `6c7e2c2`, `resolve_novel()` lacks the `chapters`, `prefix_volume_passes`, `causal_titles` and `apply_deferred_links` parameters. They exist only in uncommitted edits of `resolve/runner.py` and `resolve/title_holders.py`; `scripts/chimera/eng_probe_*` and `data/eval/chimera/eng_probe_*` are untracked. A fresh checkout cannot reproduce E1's "resolver exactly prefix-causal (0 of 28,165)". Committing or discarding those edits is the owner's decision. The two sessions do not overlap on modified files (mine: `persona/build.py`, `persona/traits.py`, one additive `Store` method, tests, `scripts/prefix_audit/`, `docs/research/PREFIX_FAITHFULNESS/`, `data/eval/prefix_audit/`).

## 4. What a merge into a joint "two leakage channels" paper would need from me

Proposed framing, for the owner to accept or reject: a position-filtered narrative graph can leak the future through (a) the **identity layer**, where resolution or a model uses disclosure that has not happened yet (CHIMERA: premature resolution, parametric leakage, the public-domain benchmark) and (b) the **trait layer**, where a derived fact is stamped earlier than the evidence it is computed from (this work). Both reduce to "served value at position k should equal what a build over the prefix holds".

From me:
1. **Commit decision and a clean branch.** The changes are additive and off by default; the branch needs a decision to commit and a merge check against the other branch's modified files (none overlap today). `docs-sync` has not been run and should run at merge time, not before, because HANDOFF, EVOLUTION and README are edited by both sessions.
2. **One vocabulary.** "Premature disclosure" here (a trait value served before the text supports it) is not CHIMERA's premature-resolution metric (an identity decided before its reveal). The paper needs two named quantities and one definition of prefix-causality.
3. **One provenance ledger.** My results are model-generated labels plus a synthetic oracle; theirs are silver or model-selected events. Spend: $0.1140 of `gpt-5.6-luna` here (of which $0.0610 from the owner's extra $0.20), separate from CHIMERA's $0.2824. Neither session has human labels.
4. **Human labels.** Both sessions are waiting on weekend annotation. `labels/human_check.csv` here, their 72-item and 19-event sheets there. Until they exist the joint claim should say "model-generated reference".
5. **Shared prior art.** Add the Dataflow model (watermarks, accumulating panes) as the closest structural relative of the versioned repair, and the look-ahead-bias literature for the model-memory channel (REPORT section 5). Keep the horizon rule's status as point-in-time correctness.
6. **Reproducibility package.** The label files contain short quotes from the source novels and should not be published as they are; `scripts/prefix_audit/luna_labels.py` (estimate first, hard budget, key never printed) and `run_llm_when_free.py` (the GPU is shared) are the two scripts with side effects to document.
7. **An honest rating.** Narrow, better supported than at the start, one codebase and five real volumes; a method-and-measurement contribution, not a new algorithm.
