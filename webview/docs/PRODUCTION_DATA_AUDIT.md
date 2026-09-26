# Production build: what may ship

**Audited:** 2026-09-26 · **Scope:** `webview/build/` from a clean `npm ci && npm run build`.

## Findings

| # | Finding | Severity | Fix | Verified |
|---|---|---|---|---|
| 1 | **Full novel text was copied into every build.** CRA copies `public/` into `build/`. The gitignored exports in `webview/public/data/` (chapter text of three copyrighted novels, about 14 MB: 9.2, 2.8 and 2.1 MB) appeared as `build/data/*.json`. The app no longer reads them, but any deployment of `build/` would have served them. | High | `scripts/strip-static-data.js` runs as `postbuild` and deletes `build/data/`. It touches only `build/`, never `public/`. | A canary file placed in `public/data/` was removed by the build (log line `postbuild: removed build/data ...`); a clean build has no `build/data`. |
| 2 | **Source maps shipped.** They embed every source file, including its comments (internal design notes, and character names used in code comments). | Medium | `npm run build` sets `GENERATE_SOURCEMAP=false`. | `find build -name "*.map"` returns nothing; the build is 508 KB, down from 2.4 MB. |
| 3 | The corrections panel help text cited an internal doc and database internals. | Low | Reworded for users. | Test and visual check. |

## Scans run on the final build

- **Chapter text:** searched `build/` for distinctive phrases from chapter 1 ("Spring Autumn Cicada", "river of time") and for character names. No hits in the bundle. (Names appeared only in the source maps, now gone.) This is a spot check on a handful of phrases, not an exhaustive scan; finding 1's fix is what guarantees no exports ship.
- **Secrets:** no `sk-ant`, `ANTHROPIC` or `api_key` strings in `build/static`. The frontend holds no keys; the only credential it handles is the user's password token, in `sessionStorage`.
- **Public copy:** `src/__tests__/CopyClaims.test.js` fails the build's tests if the landing page or page metadata claim complete voice coverage, perfect identity tracking or "never leaves your computer", or name internal mechanisms.

## Note on the deleted exports

An earlier process removed the local `webview/public/data/*.json` files. They are derived exports, regenerable from the databases with `echotales webview --format react`, and the redesigned app does not use them. They were gitignored, so git history has no copy.

## Not covered

- Images: the landing page and library show renders of copyrighted novels' scenes (art, not text). They are served from local `data/`, are not in the repository (`data/*/panels/**` and `data/cache/` are gitignored), and are not part of the build.
- The screenshot of the webview containing chapter text kept under `docs/IP/` is private and unrelated to the build.
