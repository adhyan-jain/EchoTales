# EchoTales cleanup/refactor pass — report

**2026-09-29**, branch `validation/evidence-pass-2026-09-24`, local only, not
pushed. Scope: make the repository understandable to a new researcher without
reading years of session notes, as a cleanup pass — no feature work, no
changed research claims, nothing deleted without evidence.

Before touching anything, three research agents surveyed the ground truth
(code imports/CLI wiring, docs/data inventory, tests/scripts inventory). The
headline finding: **the code was already clean.** No orphaned CLI commands,
no unimported subpackages, no `core`→`pipeline` import violations, no real
duplicate implementations, every script/test traces to real usage. The real
work turned out to be protecting uncommitted work and consolidating
documentation, not deleting code.

## 1. Current canonical architecture

See `docs/status/CURRENT_ARCHITECTURE.md` — written as part of this pass, it
is the new single source of truth for package structure, entrypoints, and
what's production vs. research vs. historical.

## 2. Files/modules deleted

None. The three Explore agents found zero confidently-dead code, so nothing
was deleted "to make the repo cleaner" without evidence backing it up —
that would have violated the pass's own rule (don't delete without evidence).

## 3. Files moved

- `docs/design/STORYTRACE_TRANSFER.md` → `docs/archive/STORYTRACE_TRANSFER.md`
  — a one-time decision record with zero code references; its still-relevant
  conclusion (the bounded-investigator decision) was folded into
  `docs/design/architecture.md` Section 7 before the move.

**Considered and reverted:** `docs/design/plans.md` was initially moved to
`docs/archive/` (its opening framing — "paste this as context, delete any
existing code, start from scratch" — clearly describes a founding prompt, not
current architecture). The move was reverted after discovering 51 source
files cite its Phase/Section numbering directly in code comments (e.g. "Phase
6 pre-filters," "Section 4.3 FABRICATED"). Archiving it would have broken
every one of those citations for zero benefit. Left in place with a banner
pointing to `architecture.md`/`details.md` as the current description
instead. This is the kind of thing the inventory-first approach is meant to
catch — the initial plan assumed it was purely historical based on its
opening paragraph; reading the actual citation graph said otherwise.

## 4. Dead code removed

None found. Verified: every `cli.py`/`commands.py` subcommand has a live
handler and import; all 13 pipeline subpackages are reachable from
`commands.py` directly or transitively; `packages/core`→`packages/pipeline`
imports are zero (grep-verified twice, before and after this pass's changes).

## 5. Duplicate abstractions consolidated

One naming collision, not a true duplicate: `anaphora/runner.py::resolve_novel`
(local Phase 5 anaphora resolution) and `resolve/runner.py::resolve_novel`
(global Phase 6 cross-chapter identity resolution) shared a name. Their one
collision point (`commands.py::cmd_run`) already aliased both distinctly on
import, so this was never a behavioral bug — just confusing to a reader
scanning either module in isolation. Renamed the anaphora one to
`resolve_anaphora_for_novel` across its definition, `anaphora/__init__.py`'s
re-export, `commands.py`'s import, and `test_anaphora.py`'s 7 usages.
Behavior-preserving; full suite green before and after.

No other duplicate implementations found (`webview` vs. `webview-server` are
complementary — one-shot exporter vs. long-running HTTP API — not
duplicates).

## 6. Documentation archived/deleted

`docs/status/STATUS.md`, `REMAINING_WORK.md`, and `FINAL_ECHOTALES_READINESS.md`
had converged on saying the same things three ways (per-subsystem state map /
gap list by audience / readiness grid), all deferring outward to
`docs/results/FINAL_EVIDENCE_TABLE.md` without that hierarchy being explicit.
Merged into one `STATUS.md` that states the hierarchy up front. The other two
files were removed (`git rm`, content preserved in the merge and in git
history) rather than left as stub pointers, per the owner's explicit
instruction to merge and trim rather than archive wholesale.

Every downstream reference to the removed files was found and fixed:
`docs/README.md`, `docs/HANDOFF.md`, `docs/results/CANONICAL_RUN.md`, and one
code comment in `packages/pipeline/.../voice/runner.py`. `docs/EVOLUTION.md`
was deliberately left with its own historical references intact — it's an
append-only log per its own rule, never edited to fix a stale claim.

`docs/paper/`'s nine files were suspected of overlap going in (by filename:
TABLES vs. EXPERIMENT_TABLE, CONTRIBUTION_MATRIX vs. REPORT_MATERIAL,
PUBLICATION_READINESS vs. VENUE_ANALYSIS) but were read in full, not assumed
from names, and found to serve genuinely distinct purposes — raw generated
data, a curated paper-ready summary, contribution-strength framing for the
paper, a MUST-item submission checklist, and venue/CFP fit analysis. Left
untouched; merging them would have destroyed real, distinct information.

`docs/private/` (gitignored, IP-sensitive: patent drafts, prior-art
bibliography, unverified paper drafts) was not touched, read in full, or
referenced from any public doc, per the pass's own boundary.

## 7. Tests removed/merged/reclassified

None removed. `test_ablation_harness.py`, `test_baseline_a.py`,
`test_baseline_b.py` were flagged during inventory as possibly testing
throwaway experiments (by name), but `scripts/reproduce_results.sh` confirms
the `scripts/eval/*.py` modules they cover are load-bearing reproduction
infrastructure, not one-off experiments. Left as-is, no reclassification
needed — the concern didn't survive contact with evidence.

## 8. Scripts/CLI cleaned

None removed. Every file in `scripts/eval/`, `scripts/maintenance/`,
`scripts/paper/`, `scripts/review/` traces to real usage in
`scripts/reproduce_results.sh` or direct CLI-argument consistency (`.db`
paths, novel IDs all resolve to real files on disk). `a7_cache_ablation.py`
and `litbank_eval.py` are already correctly commented out in
`reproduce_results.sh` as optional/manual (slow, require ollama/corpus) —
left as documented.

## 9. Data cleanup

None. `data/scratch/` (981M) and `data/archive/` (184M) are already
self-documented in `data/README.md` as disposable/retired — that's existing,
correct policy, already followed; nothing needed to change.
`data/eval/results/` (31 timestamped run dirs, 1.5M total) is small and
possibly useful provenance — marked `KEEP-UNCERTAIN` rather than pruned, per
the pass's rule against deleting uncertain material without evidence it's
safe to.

## 10. Remaining technical debt

- `render/reels.py` is an unused planner (no ffmpeg call) that duplicates
  `director.py` — flagged as dead in `docs/status/STATUS.md`'s component
  matrix but not removed this pass (out of scope: this pass fixed the
  cleanup-inventory-confirmed-dead case, this one is a *feature-code*
  deletion candidate the owner should decide on, not a doc/structure
  cleanup).
- `data/db/reverend-insanity.db` has zero SELF-kind attribute/relation rows
  (found building the MDC ablation harness, EVOLUTION 4.99) — blocks
  meaningful real-data evaluation of anything reading SELF attributes.
  Tracked as an open defect in `docs/status/STATUS.md`, not fixed this pass
  (data population, not a structure/cleanup task).
- `docs/design/plans.md`'s 51 code-comment citations mean any future rename
  of its Phase/Section numbers needs a repo-wide sweep — noted so a future
  session doesn't try to move the file again without checking first.

## 11. Intentionally preserved as historical/research material

- `docs/EVOLUTION.md` (8,169 lines) and `docs/HANDOFF.md` — append-only
  session log and current-pickup doc, by design per `CLAUDE.md`, never a
  cleanup target.
- `docs/archive/` — now 6 files (the original 4 plus `STORYTRACE_TRANSFER.md`
  from this pass; `plans.md` stayed in `docs/design/` after the revert above).
- `packages/ecrdt/` — standalone research package (E-CRDT: World Convergence
  with Provable Epistemic Non-Interference), committed intact this pass
  (Phase 0 safety commit) with its 5 rounds of IPR review, benchmarks, and
  scaling results preserved as-is.
- `data/db/` archive DBs, `data/gold/_unusable/` (quarantined circular gold,
  kept for provenance per its own README).

## 12. Exact production entrypoints

`echotales` console script (`cli.py:main`) → `ingest`, `resolve`,
`appearance`, `persona`, `voice`, `render`, `eval`, `query`, `graph`,
`export`, `webview`, `webview-server`, `run`, `review`, `ablate`,
`observations`, `annotate`, `relevance`. See
`docs/status/CURRENT_ARCHITECTURE.md` for the full map.

## 13. Exact research entrypoints

```bash
cd packages/ecrdt
PYTHONPATH=src python3 -m pytest tests/ -q      # 48 passing
PYTHONPATH=src python3 -m ecrdt.bench           # synthetic benchmark + report
```
`core/disclosure.py::compile_minimal_disclosure` is reachable in-pipeline
only via `plan_builder.build_render_plan(..., use_mdc=True)`, off by default
everywhere; its ablation is `scripts/eval/mdc_disclosure_ablation.py`.

## 14. Final test/lint/type-check/build results

| Check | Result |
|---|---|
| `pytest packages/core/tests packages/pipeline/tests` | **1,206 passed** |
| `pytest packages/ecrdt/tests` | **48 passed** |
| `ruff check` on every file this pass touched | clean (2 mechanical import/`__all__`-sort findings introduced by the `disclosure.py` export were fixed with `ruff check --fix`; pre-existing findings in untouched code — e.g. `voice/runner.py`'s `B023`/`N806` — left alone, out of scope) |
| `grep -rn "from echotales.pipeline" packages/core/src/` | empty, both before and after this pass |
| Stale-reference sweep (old paths of moved/deleted docs) | zero remaining outside `docs/EVOLUTION.md` (append-only, correctly left as historical record) |
| `mypy` (repo-wide, not run to completion this pass) | not re-run; `CLAUDE.md`'s existing note (`import-untyped` noise repo-wide) presumed still accurate, not re-verified — flag for a future pass if a clean `mypy` run becomes a submission requirement |

## Commits this pass (local only, not pushed)

1. `core: Minimal Disclosure Compiler (priority 1 of 3 IPR-review candidates)`
   — safety-committed uncommitted MDC work (disclosure.py, its test, the
   render integration, the ablation script/results, and the matching
   EVOLUTION/HANDOFF/CLAUDE.md entries that were already modified on disk).
2. `ecrdt: add E-CRDT standalone research prototype` — safety-committed the
   entire untracked `packages/ecrdt/` package.
3. `anaphora: rename resolve_novel to resolve_anaphora_for_novel` — the one
   clarity fix.
4. `docs: merge status/ trio into one STATUS.md, archive the founding-prompt
   doc` — the documentation consolidation.
5. This report + `docs/status/CURRENT_ARCHITECTURE.md` (this commit).
