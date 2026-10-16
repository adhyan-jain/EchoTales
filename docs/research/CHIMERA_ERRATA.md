# CHIMERA errata (Checkpoint 2, W0)

Append-only. Each entry quotes the Checkpoint 1 text, gives the correction, and says how I know. The five Checkpoint 1 files (`CHIMERA_REPOSITORY_AUDIT.md`, `CHIMERA_PRIOR_ART.md`, `CHIMERA_COMPONENT_MATRIX.md`, `CHIMERA_DATA_AND_BENCHMARK_PLAN.md`, `CHIMERA_NOVELTY_GATE.md`) are **not edited**; where they conflict with this file, this file wins from 2026-10-15.

## Re-baseline (W0 step 1)

| Item | Value | Tag |
|---|---|---|
| HEAD / branch | `6c7e2c2` / `validation/evidence-pass-2026-09-24` | [INSPECT] |
| `.git/index.lock` | absent | [INSPECT] |
| Tracked modifications | **1: `.gitignore`**, modified after Checkpoint 1 **at the owner's request** (two ignore patterns for the pilot and blind adjudication sheets that carry `source_text`). Checkpoint 1 itself left no tracked change | [INSPECT] |
| Untracked paths | 27 `??` entries: the owner's 22 remaining original paths + the 5 CHIMERA files. The original 23 became 22 because `data/eval/pilot_review_10.csv` is now ignored | [INSPECT] |
| Commits since Checkpoint 1 | none (a commit and a push were attempted at the owner's request and refused by the permission classifier; nothing ran) | [INSPECT] |
| Authorisation block A1-A8 | left unfilled in the Checkpoint 2 directive, which says blank means NO. So: no branch, no local inference, no paid API, no GenWebNovel, no host CPU experiments. Read-only tracing and `--collect-only` were treated as outside A8 | owner's directive |

---

## E1. Size of the public text excerpts

Checkpoint 1 audit, section 1 ("What the public branch exposes"): "each record has a `context` field of about 130 characters of source-novel text, so roughly 20k short excerpts of copyrighted novels are public". Data plan finding is consistent with it.

**Correction.** About 130 was the maximum I sampled from one file, not the typical length. Measured on `data/gold/reverend-insanity.jsonl` (7,879 records): `context` length mean **74.8**, median **35**, max **145** characters. The hard-case file's first record was 129. The total record count across the six public gold JSONL files (about 20k) stands, but "about 130 characters each" should read "mean about 75, up to about 145". The owner's figure of about 75 is right. The exposure finding itself is unchanged. [INSPECT]

## E2. "1,277 vs 1,252 test count unexplained"

Checkpoint 1 audit, section 1: "The docs claim 1,277 tests; I collected 1,252 in the same two suites. The 25-test difference is unexplained", and defect-list rank 10.

**Correction: explained, not a discrepancy.** I collected tests at the commit where CLAUDE.md dates the figure, `e34a628` (2026-10-02), in a scratch checkout: core + pipeline **1,206**, research **16**, ecrdt **55**, total **1,277**. The docs' figure counts four suites; I compared it against two. Today: core + pipeline 1,252 (the 46 more are the owner's tests added since, including the 25 in the two new untracked files), research 29, ecrdt 55 (unchanged), so 1,336 across four suites. Remove defect rank 10's first clause. [INSPECT, `--collect-only`]

## E3. "58 of 88, not 59 of 89"

Checkpoint 1 data plan finding 2: "The hard-case count is 58 undetected of 88, not 59 of 89", and the audit's "at most 55 are real".

**Correction: both numbers are real, from different runs, and the "89" was never the evaluated denominator.**
- The evaluation script reads the gold file through `read_gold(...).silver_only.entities_only` (`scripts/eval/hardcase_resolution.py:~68`, `eval/gold.py:314-315`). `entities_only` drops records whose kind is not an entity. The gold file has 89 records; exactly one (`3.0/7926 "the Awakening Ceremony"`, kind `not_an_entity`) is dropped, so **n = 88** in every version of the output. [INSPECT]
- The "59" is from the **first, non-canonical** run: `git show 6facc1e:data/eval/hardcase_resolution.json` gives overlap alignment not-detected **59**, correct **23**, n **88**. After canonical promotion (`7c0432f`) it is not-detected **58**, correct **24**, n **88**. [INSPECT]
- `docs/EVOLUTION.md:7682` ("59 of 89") and `docs/archive/STORYTRACE_TRANSFER.md:33` therefore mix the stale count (59) with the gold-file size (89). The current artifacts (`FINAL_EVIDENCE_TABLE.md`, `PAPER_CLAIM_BOUNDARIES.md`, `STATUS.md`) say 58/88.
- Exact alignment (not overlap) gives 67 not-detected (canonical). Which alignment a doc cites matters and none of the "58" statements say "overlap alignment" except `FINAL_EVIDENCE_TABLE.md:46`.
- **"At most 55 are real" holds only under the repo's own taxonomy labels.** `hardcase_taxonomy.json` (58 records) labels one `annotation-control` (`105/3604 "the Spring Autumn Cicada"`, kind `item`, category `not_entity_control`) and two `gold-span-defect` (`54/10645 "his identity"`, `86/6554 "he turned out to be C grade"`, both category `reveal`). 58 - 1 - 2 = 55. I did not independently judge whether those two spans are defects; the label is the script's. [INSPECT counts; label unverified]
- Note the control that remains in n=88 is the item-kind one; the dropped one is the entity-kind-excluded one, so "1 control inside the 58" is correct.

## E4. Retraction writer: "I did not exhaustively grep"; "no non-test callers"

Checkpoint 1 audit, component 8: "`retract_alias_bindings` (`contradiction.py:277`) has **no non-test callers (V)**"; defect rank 8 treated this as a finding; the audit closed by saying it did not grep HANDOFF/EVOLUTION for already-recorded items.

**Corrections.**
1. It has **no callers at all, tests included**. My grep over `packages` found only the definition (`resolve/contradiction.py:277`). The only `store.retract_alias(` callers are the line inside that unused function (`contradiction.py:301`) and tests in `core/tests/test_state.py`. "No non-test callers" understated it. [INSPECT]
2. It is **already recorded**: `docs/status/STATUS.md:227` ("`retract_alias_bindings` has zero callers; `retracted_chapter IS NOT NULL` returns 0 rows in every database") and `docs/archive/VALIDATION_BASELINE.md:59` ("Retraction **writer** | **MISSING** ... 0 rows across all 27 DBs"). It is not new. [INSPECT]

## E5. `conditioned_on` overstating conditioning

Checkpoint 1 audit, section 5 and defect rank 3: reference-selection code runs but its result is discarded, yet "`conditioned_on` metadata and `report.conditioned_panels` are still populated"; the headline "reference-conditioned 5/5" "counts a manifest tag".

**Qualification (the owner's re-check was right that it is partly fixed).**
- A comment at `render/panels.py:2808-2823` ("Section 4.4: `conditioned_on` must not claim conditioning that never happens") records a fix for the **curated** tag specifically. `EVOLUTION.md:6168` also discusses the field. [INSPECT]
- What remains: character-sheet labels are still appended to `conditioned` at `panels.py:2127-2128` (after the curated override at 2118-2123, so both sheet kinds are appended), at `2232`, and carried forward at `2143` and `2165`. `conditioned` is cleared only in the crowd/no-prompt branch (`2656-2657`) and for chunk-mob panels that are not close-ups (`2793-2794`). Then `engine.generate(_panel_request)` is called with `reference_images=[]` (`2740-2741`, `2850`), `report.conditioned_panels` increments whenever `conditioned` is non-empty (`2854-2855`), and `PanelImage.conditioned_on=conditioned` is stored (`2864`). [INSPECT: read each site]
- **Verdict:** confirmed for normal panels. The pre-existing partial fix does not cover character sheets.
- **Still INFERRED:** that the "reader 5/5, non-reader 0/5" figure in `OBSERVER_CONTRAST_VALIDATION.md` is a manifest-tag count. I did not open that run's manifest. The code path makes it likely; it is not demonstrated.

## E6. Items the owner marked qualified that I now resolve

| Claim in Checkpoint 1 | Verdict | Evidence |
|---|---|---|
| `retry_deferred` counts "recovered" without writing a link | **Confirmed.** On `Decision.LINK` it calls `queue.remove`, increments `recovered_from_deferral` and `by_method[DEFERRED_RERESOLVED]`, and returns; no `_apply_link`, no store write (`resolve/runner.py:646-682`, body read in full) | [INSPECT] |
| `cmd_resolve` does not read `--chapters` | **Confirmed.** The parser accepts it (`cli.py:101`); `cmd_resolve` builds its `resolve_novel(...)` call from `args.novel`, `lexicon`, `strict_kind_check`, `force_rewipe`, `capture_evidence`, `evidence_run_tag` only (`commands.py:728-737`). `args.chapters` is read at `commands.py:112, 686, 756, 957, 1005`, none of them in the resolve call. (`--chapters` on `voice`, `render` and `appearance` is consumed.) Static trace; not executed | [INSPECT] |
| `is_address` never passed | **Confirmed.** Only the definition, its docstring and a recursive call inside `classify_alias_type` reference it | [INSPECT] |
| Wiki canon undated | **Confirmed.** `persona/wiki_canon.py:26-28` promises first-appearance dating; the saved structure is `{label: {trait: value}}` with no chapter or position, and `persona/canon.py:49-60` records a measured regression from it | [INSPECT] |

## E7. Defects 3 and 6 "may not be recorded"

Audit section 8 said: "I did not exhaustively grep `docs/HANDOFF.md` or `EVOLUTION.md`, so I cannot say whether defects 3 and 6 are already recorded".

**Now checked.** `retry_deferred` appears in `docs/EVOLUTION.md:7006` only in a note about threading arguments, not as a no-write defect; `recovered_from_deferral` appears in no doc I grepped (HANDOFF, EVOLUTION, STATUS). `conditioned_on` is discussed in `EVOLUTION.md:4387, 6168` (the curated fix) but not as the remaining character-sheet overstatement. So defect 6 (`retry_deferred`) and the remainder of defect 3 are **not recorded as open**. [INSPECT, grep]

## E8. Not errors, but statements that need a qualifier

- Audit section 4.1 says no test asserts prefix invariance, citing an agent's grep. Still **agent-reported**; I did not re-grep every test file.
- Audit section 4.2 says there are no 30-50 chapter LLM windows. Re-confirmed in code only for `window_size = 40`'s uses as reported; the stale gazetteer docstring at `mentions/gazetteer.py:3-4` is what the directive's phrase came from. Still agent-reported for line numbers beyond those I opened.
- Prior-art row 1.2 says NWM's public corpus is "12 books per the directive; I did not re-count". Unchanged.

## Not corrected (checked, stands)

- 0 confirmed gold records in all six gold files; 3,457 RI records with `confirmed_by` set but `confirmed: false`. [INSPECT again this session]
- `reference_images=[]` at `panels.py:2740-2741`. [INSPECT]
- RI database: 0 retracted rows, 0 relation rows, 12 observation rows. [INSPECT, scratch copy without the `-wal`]
