# Webview final QA

**Run:** 2026-09-26 · **Build:** production, from a clean `npm ci` · **Backend:** an isolated scratch server on `:8788` serving the build via `--static-dir` · **Data:** a copy of the Reverend Insanity database plus 73 copied media files. The canonical database and the tracked corrections log were not modified (verified by hash and `git status`).

> **Superseded in part (later on 2026-09-26).** Three commits followed this run: server hardening (`888a158`), React review fixes (`f9bbdba`) and a full visual redesign (`a1bf892`). Consequences for this document:
> - Every visual description below ("cinematic", violet accent, and any screenshot-based observation) describes the **replaced** design. The current design is in `webview/README.md` ("Design") and `EVOLUTION.md` 4.93.
> - The test counts in section H are stale: webview is now **89** (9 suites; was 82), backend **1,134** on the committed tree (was 1,120; `test_webview_server_static_thumbs` 29 to 43).
> - The 128-run axe sweep and the 36-step journeys were run on the old design and were **not repeated in that form**. After the redesign, axe was re-run over 12 routes x 2 themes x 2 widths (1440, 390): 0 violations. Journeys, the per-route metric sweep at four widths and the error-state simulations were not re-run.
> - Section G "Media": a malformed or multi-range `Range` is now ignored (200), not 416; only a well-formed out-of-bounds range is 416. Thumbnails are now `private`, and file routes revalidate by ETag.
> - Section E: 401 now returns to the sign-in screen; a response body that stalls is covered by the 30 s timeout.
> - No person has reviewed the redesign or the flows for usability; the screen-reader and touch-device gaps below remain.

Everything below was measured or observed in that run unless marked *not tested*.

## A. Routes

16 routes × 4 widths (390, 768, 1024, 1440) × 2 themes = **128 page checks**, each asserting: no horizontal overflow, no broken image, no stuck "Loading…", exactly one `<h1>` and one `<main>`, and no uncaught exception. **Result: 0 problems.**

| Route | Result |
|---|---|
| `/`, `/projects`, `/projects/new`, `/design` | pass |
| `/p/<id>`, `/read/<n>?focus=<id>`, `/characters`, `/characters/<id>`, `/studio`, `/studio?tab=library`, `/review`, `/settings` | pass |
| `/definitely-not-a-page` | not-found page |
| `/p/<id>/read/9999` | "Chapter 9999 isn't in this book", with a link to chapter 1 |
| `/p/<id>/characters/nobody` | "Character not found", with a way back |
| `/p/nope-project`, `/p/%ZZ` | "Project not found", with a link to the library |

- **Direct load and reload** work on every route (the backend answers non-API paths with `index.html`).
- **Chapter and highlighted character survive a reload** and are shareable; clearing the highlight removes it from the URL.
- **Browser back** returned from a character dossier to the grid. *Forward navigation was not separately tested.*
- **Old URLs** (unit-tested): `?review` goes to `/projects`, `?gallery` to `/design`, `/cast/<id>` to `/characters/<id>`.
- **Journeys** (real clicks, each step asserted, at 1440 and 390): new reader (landing, library, overview, read, next chapter, dossier, back, studio, back to read); power user (library, characters, dossier, studio library, review, a correction, state check, read shows it); shared link (chapter 5 with highlight, reload). **36/36 steps passed.**

## B. Review flows

Nine flows plus Apply, verified in the UI, the corrections log and the database: `REVIEW_FLOW_QA.md`. Nine defects found by that run were fixed.

## C. Accessibility

- **axe-core 4.13:** 0 violations of any impact on all 128 page runs. Two contrast findings and three structural ones were fixed along the way (see below).
- **Keyboard:** mentions and speaker labels are focusable (Enter/Space); the character picker is arrow-navigable with a focus trap; dialogs take focus, close on Escape and return focus to the control that opened them. Covered by unit tests.
- **Semantics:** every action is a `<button>`/`<a>`; one `h1` and one `main` per page; status text is announced (`role="status"`, `role="alert"`); icon-only buttons carry labels; decorative icons are `aria-hidden`.
- **Colour:** every text token was contrast-checked in both themes, including status chips on their own tint.
- **Target size:** per-line actions are 44 px on touch and narrow screens; icon buttons (theme toggle, chapter arrows) are 36 px. That meets WCAG 2.2 AA (24 px minimum) but **not** the 44 px AAA/HIG guideline.
- ***Not tested:*** a real screen reader, and a physical touch device.

## D. Responsive

- No horizontal overflow at any of the four widths on any route.
- Below 1024 px the sidebar becomes a menu drawer; Review gets an Entities drawer (merging was impossible on a phone before); dialogs become bottom sheets under 640 px; per-line actions are always visible on touch.
- Visual review by screenshot: landing, overview, reader, characters, studio and review at 1440; landing, overview and review at 390. At 768 and 1024 only the metric checks above were run.

## E. Error states

Simulated in the browser (network interception) against every page: backend down, HTTP 500 carrying a Python traceback, HTTP 404, a request that never answers, malformed ids, a missing chapter and character, a failed correction, a failed render, and a failed job in the list.

| Situation | What the user sees |
|---|---|
| Backend unreachable | "Can't reach the EchoTales server…" plus how to start it |
| 500 with a traceback | "The server hit a problem handling that…". **No server text is shown**; a regex check found no `Traceback`, `.py`, `sqlite` or raw id on any page |
| 404 | "That wasn't found on this server" / a specific not-found screen; the raw id is never echoed |
| Request that never answers | After 30 s, the unreachable message. Before this pass, an endless "Loading…" |
| Failed correction | Toast in plain language; the picker stays open for a retry |
| Failed render | Toast; a FAILED job shows "This render did not finish. Nothing was changed…" with the exception behind a "Technical detail" disclosure, truncated |
| Wrong password | "That password isn't right." (it previously read as an expired session) |

Every async page has loading, empty and error states; empty states were checked with an empty project list, no characters, no output and no jobs. **No blank screens, no uncaught exceptions.**

## F. Performance

| Measure | Before | After |
|---|---|---|
| Landing images | 18 full-size PNGs, about 23 MB | 16 WebP thumbnails, 624 KB |
| Overview images | full-size | 204 KB |
| Characters page API payload | 9,469 KB | 57 KB |
| Studio API payload | 18,825 KB (novel fetched twice) | 7 KB |
| Library API payload | 9,421 KB | 9 KB |
| Settings API payload | 9,413 KB | 1 KB |
| Main JS | 124.8 kB gzip | 126.6 kB gzip (421 KB raw) |
| CSS | | 9.7 kB gzip |

- The 9.4 MB novel payload now loads only for Overview, Read and Review.
- One small duplicate remains: Settings requests the project list twice (about 1 KB).
- Page load to network-idle was 0.53 to 0.73 s per route on localhost, measured *before* the payload change; it was not re-timed afterwards.
- A 262 MB chapter video no longer loads into server memory: the server streams it in 64 KiB chunks and answers byte ranges. In a browser, seeking a 646 s video to 5:00 and pressing play advanced the clock to 5:02 within 2.5 s.
- Long lists are paged (24 at a time) instead of rendering 1,000+ entries.

## G. Production server

- **Clean install and build:** `npm ci` then `npm run build` in a fresh copy: compiles, 508 KB, no source maps, no `build/data`.
- **Served by the backend** (`--static-dir`): every route above, plus SPA fallback for client routes. A missing asset is a **404**, not the HTML shell. Path traversal attempts (`/../x`, `/%2e%2e/x`, `/static/../../x`) return nothing outside the build directory (unit-tested).
- **Auth:** with a password set, a deep link shows the sign-in page; the API returns 401 without a token; the landing page stays public; after sign-in the user lands on the deep link.
- **Media:** `206` byte ranges, `416` for unsatisfiable ranges, thumbnails cached (a 1.2 MB panel served as 25 KB WebP), audio decodes (24 kHz mono WAV, 6.4 s).
- **Same origin:** a production build talks to its own origin; `REACT_APP_API_BASE` overrides.
- ***Not tested:*** the `npm start` development server in this pass; serving behind a reverse proxy or over HTTPS.

## H. Test counts

| Suite | Tests |
|---|---|
| Webview (Jest, 9 suites) | **82 passed** (28 at the start of this QA pass, 54 added) |
| Backend (`packages/core` + `packages/pipeline`) | **1,120 passed** (1,085 before, 35 added) |
| axe-core over the running build | 128 runs, 0 violations |
| Playwright journeys | 36 of 36 steps |

New this pass: `ReviewDialogs` (3), `errors` (11), `FailureStates` (4), `CopyClaims` (21), `AnalysisPanel` (3), more `KeyboardAccess`, `Routes` and `ProductScreens` cases; backend `test_webview_server_static_thumbs` (29) and `test_voice_render_novel` (6). ESLint reports 2 pre-existing findings in `Section7Smoke.test.js`.

## I. Known limitations

- **Studio "Generate" only submits the placeholder (stub) engine.** Real image engines run from the command line. The screen says so.
- **New mentions and line merges appear only after Apply** (the server's preview has no case for them); a notice says so.
- Flags are notes and are never applied; removing one is Undo.
- Everything at 390 px used mouse clicks; there was no touch-device or screen-reader run.
- The Review flows are verified manually; there is no automated end-to-end suite.
- A file upload times out after 5 minutes; every other request after 30 seconds.
- **A backend started before this pass** lacks `--static-dir`, thumbnails, byte ranges and the chapter-list route. The UI still works against it (the chapter list falls back to the full payload) but images are full size and video will not seek until the server is restarted.
- The panel images in the library are renders of copyrighted novels' scenes; they are served from local `data/` and are not in the repository or the build.
- Data-level accuracy of what the pipeline shows (attribution 43%, hard cases, transmigration) is a pipeline limitation, reported honestly in the UI and in `docs/STATUS.md`; this QA is about the interface.
