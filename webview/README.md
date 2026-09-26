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

Set `ECHOTALES_WEBVIEW_PASSWORD` in the server's environment to require a password; the UI then shows a sign-in page first.

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

- `GET /api/novels/<id>/output/file?path=...` serves generated files with HTTP **Range** support, so browsers can seek video and audio, and streams in chunks.
- Add `&w=320|480|960` to an image request for a cached WebP thumbnail (`data/cache/thumbs/`). The landing page, library and cards use it: full panels are up to 1.4 MB each.
- `GET /api/novels/<id>/chapters` returns chapter numbers and titles only. The full novel payload (`GET /api/novels/<id>`) is about 9.4 MB for a 199-chapter book and is loaded only by Overview, Read and Review.

## Tests and checks

```bash
CI=true npx react-scripts test --watchAll=false     # 82 tests
npx eslint src --ext .js                            # 2 known findings in Section7Smoke.test.js
npm run build                                       # production build (no source maps)
```

Accessibility was audited with axe-core against a running build (16 routes × 4 widths × 2 themes; see `docs/FINAL_WEBVIEW_QA.md`). The public copy is pinned by `src/__tests__/CopyClaims.test.js`: it must not claim complete voice coverage, perfect identity tracking, or name internal mechanisms.

## More

- `docs/REVIEW_FLOW_QA.md`: the nine correction flows, verified in the UI and the database.
- `docs/FINAL_WEBVIEW_QA.md`: routes, accessibility, responsive, error states, performance, production-server and test results.
- `docs/PRODUCTION_DATA_AUDIT.md`: what a production build may and may not contain.
