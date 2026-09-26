# EchoTales v1 — readiness

**Updated:** 2026-09-26 · **Branch:** `validation/evidence-pass-2026-09-24` (local, **never pushed**) · **Canonical database:** `data/reverend-insanity.db`, unchanged (sha256 `86c4dbf4…`).

Every accuracy figure in this project is scored against an **LLM-drafted silver reference set**, not human labels. Details and per-claim evidence: `docs/FINAL_EVIDENCE_TABLE.md`. What is still missing: `docs/REMAINING_WORK.md`. The webview's own QA record: `webview/docs/FINAL_WEBVIEW_QA.md`.

> Patent and disclosure analysis is kept **privately** in `docs/IP/` (gitignored) and handed to the VIT IPR cell. It is deliberately not summarised in this tracked file, because the repository is public. What can be said publicly: the repository has been public since 2026-08-06, so **do not push this branch or post a preprint until the IPR cell has decided.**

## Test status (2026-09-26)

| Suite | Result |
|---|---|
| Backend (`packages/core` + `packages/pipeline`) | 1,120 passed |
| Webview (Jest) | 82 passed |
| Webview accessibility (axe-core) | 0 violations across 16 routes × 4 widths × 2 themes (128 runs) |
| Webview production build from a clean `npm ci` | compiles; no source maps; no offline novel exports shipped |

## Areas

| # | Area | Status | Basis |
|---|---|---|---|
| 1 | Engineering | **DONE for v1 scope** | Pipeline runs end to end on a 199-chapter volume; webview redesigned and QA'd; audio orchestrator now has an end-to-end test. Known open engineering items are under "Open" below. |
| 2 | Reproducibility | **DONE** | `scripts/reproduce_results.sh`; canonical database hash pinned. It cannot rebuild the database from a clean checkout (the source EPUBs are copyrighted and not committed). |
| 3 | Core resolution | **PARTIAL** | Silver CEAF-e F1 67.4; 58 of 88 hard cases are never detected; the LOTM transmigration comes out as two characters. |
| 4 | Observer state | **PARTIAL** | Mechanism demonstrated and ablated; witness-level rendering and mid-chapter reveals are not supported (see the evidence table). |
| 5 | Multimodal generation | **PARTIAL** | Images, audio and vertical (1080×1920) video all render on real data. Panel quality is below the product bar by the owner's own standard; the webview's Studio only submits the stub (placeholder) image engine. Audio does not consume narrative state. |
| 6 | Ablations | **DONE** | A1, A2, A7 and the resolution ablation, with negative results reported. |
| 7 | External validation | **DONE (one benchmark), weak result** | LitBank, 100 documents. Not comparable to supervised systems. |
| 8 | Human validation | **WAITING ON HUMAN** | The review sheets and protocol are prepared; **0 labels**; no kappa. |
| 9 | Patent / IP | **WAITING ON IPR CELL** | Packet prepared privately. |
| 10 | Publication | **PARTIAL** | Experiment table, claim boundaries, venue decision and a draft skeleton exist. Gated on human labels and the IPR decision. |
| 11 | Security | **PARTIAL** | `.env` is untracked and no keys are in the repo or its history. **The keys in `.env` were exposed in earlier session transcripts and must be rotated by their owner** (`docs/SECURITY_KEY_ROTATION.md`). |
| 12 | Documentation | **DONE** | EVOLUTION, STATUS, HANDOFF and the webview docs are current. |

## Done by an agent this session, verified

| Item | Evidence |
|---|---|
| Nine Review correction flows exercised against an isolated scratch database, including Apply | `webview/docs/REVIEW_FLOW_QA.md`; the canonical database hash is unchanged and `data/corrections/` is clean |
| A leaked test line in the tracked corrections log | Reverted; the server gained `--corrections-dir` so QA runs cannot write there again |
| Native `prompt()`/`alert()` in Review | Replaced by an accessible in-app dialog with tests |
| Production serving | The backend serves the built app (`--static-dir`) with SPA fallback, verified on every route |
| Production data leak | `build/data` is stripped after every build; source maps are off; a clean-checkout build was inspected |
| Image weight | Landing page images 23 MB to about 0.7 MB (server-side WebP thumbnails) |
| Payload weight | Pages that never read the novel no longer download it (Characters 9.5 MB to 57 KB) |
| Failure states | No server text or traceback reaches a user; every page has loading, empty and error states |
| Audio orchestrator | `render_novel` was untested; now 6 end-to-end tests |

## Open

**Engineering, not blocked:**
- Observer-scoped persona bindings have no writer, so witness-level rendering is not possible.
- The audio path does not consume narrative state, so a character keeps one voice through a body change.
- The 9:16 "reels" helper (`render/reels.py`) is an unused planner. Chapter videos are already vertical 1080×1920; there is no automatic short highlight cut, and nothing measured says one is needed.
- The webview Studio only submits the stub image engine; real engines run from the command line.
- Two pre-existing lint findings remain in files this session did not touch.

**Human or external:**
1. Label the 200-row and 88-row review sheets (two reviewers for kappa).
2. Rotate the API keys.
3. IPR cell decision and counsel's reading of the closest patent, before any push.
4. Listening test and panel ratings; team sign-off on the course report.

**v1.1 research backlog:** undetected hard cases; the transmigration merge; comprehensive human visual rating and audio MOS; GraphRAG / CORE-KG baselines.

## Repository state

- Branch is ahead of `origin/master` (6aed9f9) and unpushed.
- The working tree also contains another effort's uncommitted work in `packages/core` and `docs/eval/` (a `GenerationState` feature and evaluation write-ups). It is not part of this readiness statement.
