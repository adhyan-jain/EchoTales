# EchoTales webview

The React front end for EchoTales: a public landing page, a project library, and a per-project workspace for reading a processed novel, browsing its cast, viewing generated output, and reviewing/correcting the pipeline's results.

It is a client for the backend in `packages/pipeline/src/echotales/pipeline/webview_server.py`. **There is no offline mode:** every page reads the live server. (Earlier builds could fall back to static JSON exports in `public/data/`; that mode was removed, and `postbuild` deletes `build/data/` so full-novel text can never ship in a build.)

## Routes

| Path | Page |
|---|---|
| `/` | Landing (public; imagery is the first project's own renders) |
| `/projects` | Library dashboard |
| `/projects/new` | New project |
| `/p/:id` | Overview |
| `/p/:id/read/:chapter?` (`?focus=<entity id>`) | Reader; chapter and highlighted character are in the URL |
| `/p/:id/characters/:selfId?` | Characters and a character's dossier |
| `/p/:id/studio` (`?tab=library`) | Generate and Output library |
| `/p/:id/review` (`?ch=<chapter>`) | Correction tools |
| `/p/:id/settings` | Source, ingestion status, appearance |
| `/design` | Internal UI primitives gallery |

Old links keep working: `/?review` goes to `/projects`, `/?gallery` to `/design`, and `/p/:id/cast[/:selfId]` to `/p/:id/characters[/:selfId]`. Unknown paths show a not-found page; a missing chapter, character or project shows a specific not-found state.

## Run it

Both need the backend running. `--source` names a database, a novel id and a label:

```bash
uv run echotales webview-server --source data/reverend-insanity.db:reverend-insanity:"Reverend Insanity"
```

**Development** (hot reload; talks to the backend on `http://localhost:8787`):

```bash
cd webview && npm install && npm start        # http://localhost:3000
```

**Production** (the backend serves the built app itself, same origin, no CORS):

```bash
cd webview && npm ci && npm run build
cd .. && uv run echotales webview-server --source <db>:<id>:<label> --static-dir webview/build
# open http://127.0.0.1:8787/
```

`--static-dir` serves real files from the build and answers every other non-`/api` path with `index.html`, so client routes such as `/p/<id>/read/3` survive a reload. A missing asset (`/static/js/x.js`) is a 404, not the HTML shell. The frontend is served before the login check (the login screen is part of it); the data is not.

**If you host `build/` with another static server, it must send `index.html` for unknown paths** or deep links 404. To point a separately hosted build at a backend, build with `REACT_APP_API_BASE=https://host:port npm run build`.

Set `ECHOTALES_WEBVIEW_PASSWORD` in the server's environment to require a password; the UI then shows a sign-in page first, and any 401 from the API returns the user to it.

**Auth and media:** the API takes the session token as `Authorization: Bearer`. `<img>`, `<video>` and `<audio>` cannot send that header, so the **output-file route only** (`GET`/`HEAD` `/api/novels/<id>/output/file`) also accepts the token as `?access_token=`; the JSON API never does. A token in a URL can end up in browser history and server logs; that is a known trade-off of this route, not an oversight.

## Design

The direction was changed on 2026-09-26/27 (details in `EVOLUTION.md` 4.92/4.93; token history in the comment at the top of `tailwind.config.js`):

1. an "editorial archive" (Fraunces, brass, 2 px corners) was rejected as too quiet;
2. "cinematic dark" (violet accent, glow, Inter / Inter Tight) was rejected as generic;
3. a "warm ink" redesign (Newsreader serif, amber accent, ledger row, landing specimen) was tried, and the owner then asked to go back to violet on 2026-09-27.

Current (commit `ec6a1d2`): the violet cinematic-dark look, with a light theme; violet accent (`accent` for text/icons/focus, deeper `primary` for button fills), Inter / Inter Tight, glow shadow and accent gradient. Design tokens live in `tailwind.config.js` and `src/index.css` (CSS variable triples). Kept from the warm-ink work: the phone reader layout (speaker above the line under 640 px), `min-width`/`overflow-wrap` guards on `.line .body`, the unknown-speaker contrast fix (`--sp` colour-mix in `index.css` and `ScriptLine.js`), and the short-window sidebar and narrow-screen panel fixes. **No human usability review was done**; the numbers below are machine checks only.

**State and requests:** `ProjectLayout` mounts one `ProjectProvider` per project, keyed by id, so pages do not leak state across a project switch and the whole-book payload is fetched once for Overview, Read and Review. The request timeout (30 s) covers reading the response body, not only the headers. A non-JSON 2xx, or an error that did not come from the API, shows generic copy rather than the response text. Modals and both drawers share `lib/useDialogFocus.js`.

## Reviewing safely (scratch database)

Corrections are a JSONL log per novel (`<corrections-dir>/<novel>.jsonl`), **not** rows in the database, until you press Apply. The default corrections directory is `data/corrections`, relative to the server's working directory, which is inside the tracked repo. To try the Review tools without touching real data, work on copies and start the server from a scratch directory:

```bash
mkdir -p /tmp/qa/data/corrections && cp data/reverend-insanity.db /tmp/qa/ri.db
cd /tmp/qa && uv run --project <repo> echotales webview-server \
  --source /tmp/qa/ri.db:reverend-insanity:"Reverend Insanity" \
  --corrections-dir /tmp/qa/data/corrections --static-dir <repo>/webview/build --port 8788
```

(The server also resolves `data/<novel code>/` for panels, audio and video relative to the working directory; copy or link the few files you want to see.) Apply writes into the database the server was started with.

## What the server provides beyond JSON

- `GET /api/novels/<id>/output/file?path=...` serves generated files with HTTP **Range** support, so browsers can seek video and audio, and streams in chunks. A malformed or multi-range `Range` header is ignored (full 200 body, per RFC 9110); only a well-formed range outside the file is a 416. `HEAD` is supported, and file responses carry `ETag`/`Last-Modified` and answer `If-None-Match` with 304.
- Add `&w=320|480|960` to an image request for a cached WebP thumbnail (`data/cache/thumbs/`). The landing page, library and cards use it: full panels are up to 1.4 MB each. `w` must be an ASCII decimal in that set (anything else is 400); thumbnails are `Cache-Control: private, max-age=86400` and revalidate by ETag. Pillow is a declared dependency of `packages/pipeline`.
- The handler has a 30 s socket timeout. The server is single-threaded, so before this one client that stopped reading (a paused video, a dropped phone) blocked every other request; a stalled connection is now dropped. A NUL byte in a static path is a 404 (or the SPA fallback), not a 500.
- `GET /api/novels/<id>/chapters` returns chapter numbers and titles only. The full novel payload (`GET /api/novels/<id>`) is about 9.4 MB for a 199-chapter book and is loaded only by Overview, Read and Review.

## Tests and checks

```bash
CI=true npx react-scripts test --watchAll=false     # 89 tests
npx eslint src --ext .js                            # clean as of ec6a1d2
npm run build                                       # production build (no source maps)
```

Accessibility was audited with axe-core against a running build (16 routes × 4 widths × 2 themes for the earlier design; after the 2026-09-27 return to the violet look (`ec6a1d2`), 12 routes × 2 themes × 2 widths = 48 runs, 0 violations, plus a 220-check route × viewport × theme sweep with no overflow or scroll trap; see `docs/FINAL_WEBVIEW_QA.md`). The public copy is pinned by `src/__tests__/CopyClaims.test.js`: it must not claim complete voice coverage, perfect identity tracking, or name internal mechanisms.

## More

- `docs/REVIEW_FLOW_QA.md`: the nine correction flows, verified in the UI and the database.
- `docs/FINAL_WEBVIEW_QA.md`: routes, accessibility, responsive, error states, performance, production-server and test results.
- `docs/PRODUCTION_DATA_AUDIT.md`: what a production build may and may not contain.
