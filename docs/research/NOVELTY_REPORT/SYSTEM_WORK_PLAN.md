# System work plan (CP-G), 2026-10-15

Track S (product) only, plus the Track P pieces that need code. **Nothing here has been done.** No existing file has been touched; code changes beyond new files wait for your authorisation of a branch (section 1). Merging a component is engineering and is never claimed as paper novelty. Defect numbers refer to `CHIMERA_DEFECT_BACKLOG.md` (B1 to B12, A1 to A14) plus **B13**, a new defect found in M0: `FuzzyInterval` has no `last_evidence` field, so the argument passed in the closed-tenure call in `resolve/title_holders.py` is silently dropped (verified by running the constructor).

## 1. What I need from you

- **Authorise one local branch**, for example `chimera/system-adapters`, created from the current HEAD (`6c7e2c2`). Not pushed, no commits unless you say so (the standing "no commits" rule stays). Today's branch is the public `validation/evidence-pass-2026-09-24`; I recommend not editing on it.
- **Choose a scope** (section 4): A (recommended), B or C.
- Decide whether a changed default may alter existing numbers (several fixes change how earlier results read; each is flagged below).

## 2. What can be done with NEW FILES ONLY, no branch needed

| Item | New file | Track | Notes |
|---|---|---|---|
| M3a reveal-aware synthetic resolver wrapper | `scripts/chimera/reveal_aware_resolver.py` | P | Wraps `resolve_novel` output with a reader-observer reveal pass on the SIO worlds, so the SIO result stops being vacuous; no repo file edited |
| M3b title-holder temporal model (holder, title, organisation, story time) with TAC-KBP 4-tuple scoring | `scripts/chimera/title_tenure_model.py` | P and S | Evaluated on SIO oracle truth and on the 5 of 22 early-stamped RI events; if it only reproduces TAC-KBP it moves to the system section |
| Prompt-boundary invariant checker (what enters a prompt vs `state_of`) | `scripts/chimera/prompt_invariant_check.py` plus a test | S | Audits `story_context` output for later-chapter items without changing it; produces a measured leak count |
| M1 evidence gate v2, M2 cross-family replication | `PREREG_L1_v2_*.md`, prompts file, runner | P | Spend requests follow at CP-H |
| Diagnostic scripts for B1, B2, B13 | `scripts/chimera/diag_*.py` | S | Reproduce each defect with an executed command so the fix has a before-number |

## 3. Adapters proposed (each isolated, disable-able, with its own tests and, where measurable, an ablation)

All need a branch because they edit existing files. Order is by value per risk.

| # | Adapter or fix | Defects | Existing files touched | What changes for the product | What changes in existing numbers | Test and ablation |
|---|---|---|---|---|---|---|
| 1 | **Honest counters**: `retry_deferred` writes a link or stops counting "recovered"; `conditioned_on` derived from the request actually sent | B1, B3 | `resolve/runner.py`, `render/panels.py` | Reports stop overstating resolution and conditioning | **Yes**: `recovered_from_deferral` and `by_method[DEFERRED_RERESOLVED]` drop; `conditioned_on` loses sheet labels that did not condition | Unit tests on synthetic deferrals; assert `conditioned_on` equals the serialised refs |
| 2 | **Prefix resolve**: make `resolve --chapters` real (`max_chapter` parameter) | B2 | `pipeline/cli.py`, `commands.py`, `resolve/runner.py` | Lets any "resolve up to chapter c" run work | None for default runs | Test: results for chapters up to c equal a run on a truncated copy; needed for real-novel prefix experiments |
| 3 | **Prompt-boundary state policy**: a `PromptItem(text, ref, learned_at_pos, observer_scope)` builder that refuses items beyond the position; `story_context` and `appearance_of` read through `state_of`; wire in the existing `EpistemicLeakageValidator` | A1, A2, B3 | `world/context.py`, `persona/reference_gen.py`, render call sites | One state policy for panel, voice and wiki paths; auditable invariant | **Yes**: briefs and appearance attributes may lose later-chapter facts | Invariant test (plant a chapter-20 fact, assert refusal at position 9); ablation: policy on vs off, leak count from the checker in section 2 |
| 4 | **Dated wiki canon**: stamp canon with `learned_at_pos` and apply it inside the state digest | B4 | `persona/wiki_canon.py`, `persona/canon.py`, `render/panels.py`, `world/context.py` | Later canon stops leaking into earlier panels | **Yes**: panel prompts and digests change; cached panels invalidate | Test with a fixture canon fact dated after the position |
| 5 | **Title-holder repair**: fix the dropped `last_evidence`; gate the chapter-1 backward extension behind a `--causal` flag | B13, A7 | `resolve/title_holders.py`, possibly `core/interval.py` | Closed tenures keep their evidence; causal mode available | None by default; causal mode changes titles linked before the holder is declared | Compare on SIO and RI events; ablation switch is the flag |
| 6 | **Mention detection**: pass `is_address` from the dialogue path and measure; later a proposer test (Maverick, research-only because of its non-commercial licence) and a BookCoref-style verifier switch | B6, A9 | `mentions/runner.py`, `mentions/alias_type.py` | Targets the 58/88 undetected hard cases | **Yes**: mention counts change | Detection recall on the silver hard cases now, on human-verified ones after your labels |
| 7 | **Retraction writer**: give `retract_alias_bindings` a caller | B5 | `resolve/contradiction.py`, `resolve/runner.py` | The retraction axis becomes exercisable on real data | Possibly none until a retraction fires | Synthetic retraction fixture |
| 8 | **Reference guard**: an independent leak check on the finished image prompt, and re-wired reveal-aware reference selection behind a flag; StoryDiffusion only after a VRAM proof | B7, A3, Jularr-style guard | `render/panels.py`, `render/contract.py`, `persona/reference_gen.py` | Fewer spoiler leaks into panels; references conditioned honestly | Panel digests change if references are re-wired | Seeded-leak recall and false-block rate; image inspection by you (text-only tests do not prove visual correctness) |
| 9 | **Smaller**: data-hygiene notes (B8, B9, B11), alias-bucketing rule (A12), NER roster truncation and cache key (A11) | various | gold docs, `runner.py`, `ner.py` | Hygiene | Small | Each with a unit test |

Not proposed: a repository rewrite, new modalities, replacing the resolver with any donor (Graphiti, LlmLink), calibrated-abstention work as a claim, FLUX or other models outside the NoobAI-only rule.

## 4. Scope options

- **A (recommended, about 4 to 6 days of work):** adapters 1, 2, 3, 4, 5. They are what Track P experiments need (B2 prefix runs, B3 and the invariant for honest provenance, B13 and A7 for the title-holder model) and they fix the verified High-severity defects B1 to B4. Every numeric change is flagged and documented in the report.
- **B (A plus detection and retraction, about 2 more days):** adds 6 and 7.
- **C (everything in section 3, about 2 weeks):** adds 8 and 9; image-side work needs your inspection and a confirmed GPU.

## 5. Guardrails for the branch work

- Every adapter is a config switch or isolated module, off by default if it changes numbers; defaults only change when you say so.
- No silent loss of confidence, evidence, temporal, observer or provenance metadata.
- Tests first for each fix; the existing 1,277-test suite must still pass (the CLAUDE.md count) before anything is called done.
- `docs/EVOLUTION.md` and `docs/HANDOFF.md` get entries through the docs-sync agent only after you approve edits to existing docs.
- Source novels and any novel text stay out of every file; nothing is pushed.

## 6. Public exposure (information only)

Nothing new created here carries novel text. The standing public-exposure issue stays with you.
