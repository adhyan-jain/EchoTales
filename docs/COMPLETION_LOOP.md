# Completion loop tracker

Started 2026-09-26. Source of the gap list: `docs/REMAINING_WORK.md`, `docs/STATUS.md`, the approved webview QA plan, and a scan of the working tree.

**Rule for this loop:** do every item an agent can close and *verify* it (a real run, not a claim). Items that need a person, a paid resource, or a decision are listed under BLOCKED and are not marked done. Nothing here is pushed.

## A. Webview (approved QA plan)

| # | Item | Status |
|---|---|---|
| A1 | Nine review flows against an isolated scratch DB, with DB checks | DONE (see `webview/docs/REVIEW_FLOW_QA.md`) |
| A2 | In-app flag / add-mention dialogs, focus + validation | DONE |
| A3 | Thumbnails, `--static-dir`, `--corrections-dir`, build/data stripped | DONE |
| A4 | Axe on every route, both themes | DONE (0 violations) |
| A5 | Error / backend-failure states (backend down, 500, 404, malformed ids) | TODO |
| A6 | Loading / empty states audit per page | TODO |
| A7 | Journeys A-D incl. mobile 390 | TODO |
| A8 | Performance sanity numbers + duplicate `listProjects` | TODO |
| A9 | Copy / claim sweep of all webview strings | TODO |
| A10 | Visual consistency (GenerationWorkspace, NewProject old styles) | TODO |
| A11 | Dead-code / stale-comment cleanup | TODO |
| A12 | `webview/README.md`, `webview/docs/FINAL_WEBVIEW_QA.md`, STATUS correction | TODO |

## B. Backend / pipeline

| # | Item | Status |
|---|---|---|
| B1 | `render_novel` has zero direct test coverage (STATUS: Audio/TTS) | TODO |
| B2 | Pre-existing lint errors in files this work touches (webview_server, cli) | TODO |
| B3 | `render/reels.py` has no ffmpeg call (9:16 reels "Missing") | TODO: assess size first |
| B4 | Docs that overstate completion (readiness doc "100% agent-closable", QA doc port/flows) | TODO |

## C. BLOCKED (not agent-closable; not marked done)

- Human labels for the 200-row and 88-row review sheets (no kappa without them).
- Rotate the API keys in `.env` (exposed in earlier transcripts).
- IPR cell decision; counsel reading of the closest patent; do not push the branch before it.
- Listening test / panel ratings; team sign-offs for the report.
- CLIPScore / identity metrics need a 1.7 GB model download (local, but not done; see REMAINING_WORK 1.4).
- Mechanisms the project's own doc says NOT to build until a measurement justifies them: retraction writer, concurrent personas, LLM investigator. A separate in-progress effort on `GenerationState` exists in `packages/core`; it is not part of this loop.
