// postbuild: remove build/data/ from the production bundle.
//
// CRA copies everything in public/ into build/. `echotales webview --format
// react` writes full-novel JSON exports (chapter text of copyrighted novels,
// ~14 MB for three books) into public/data/, which is gitignored -- but it
// still ended up in every build and would ship with any deployment of build/
// (found 2026-09-26). The app no longer reads those files at all; it always
// talks to the live webview-server. This only ever touches build/, never the
// user's public/ directory.
const fs = require('fs');
const path = require('path');

const target = path.join(__dirname, '..', 'build', 'data');
if (fs.existsSync(target)) {
  fs.rmSync(target, { recursive: true, force: true });
  console.info('postbuild: removed build/data (offline novel exports are not shipped)');
}
