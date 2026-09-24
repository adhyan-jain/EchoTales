#!/usr/bin/env bash
# Reproduce every number this repository reports, from a checkout.
#
# COMPLETION_PLAN Track 2 item 10. Written because EVOLUTION 4.74 retracted a
# headline figure that no one could trace: there was no record of which gold
# file, which database, or which commit produced it. Every command below
# writes its output under data/eval/results/<run_id>/ with the commit, the
# database, the gold path and the seed beside the metrics.
#
# Usage:
#   scripts/reproduce_results.sh [NOVEL] [DB]
#
# Honest preconditions, stated rather than assumed:
#   * The DB must already be ingested and resolved. This script does NOT run
#     the pipeline: a full real run needs ollama and ~1h, and silently
#     starting one from a "reproduce results" script would be a surprise.
#   * data/raw/*.epub is gitignored (copyrighted source texts). A fresh
#     checkout cannot regenerate a database from nothing.
#   * There is currently NO confirmed gold (EVOLUTION 4.74). Every coreference
#     number this produces is scored against unconfirmed drafts and is
#     labelled as such in the output. That is not a bug in this script.

set -euo pipefail

NOVEL="${1:-reverend-insanity}"
DB="${2:-data/webview-working/${NOVEL}.db}"
SEED="${ECHOTALES_SEED:-20260923}"

if [[ ! -f "$DB" ]]; then
  echo "error: no database at $DB" >&2
  echo "       ingest and resolve first:" >&2
  echo "       echotales --db $DB run --novel $NOVEL" >&2
  exit 2
fi

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "=== environment ==="
echo "novel:  $NOVEL"
echo "db:     $DB"
echo "seed:   $SEED"
echo "commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)$(
  [[ -n "$(git status --porcelain 2>/dev/null)" ]] && echo '-dirty'
)"
python3 --version

echo
echo "=== test suite ==="
python3 -m pytest packages/core/tests packages/pipeline/tests -q

echo
echo "=== evaluation (coreference metrics, escalation, CIs, held-out coverage) ==="
echotales --seed "$SEED" --db "$DB" eval --novel "$NOVEL"

echo
echo "=== gazetteer compounding curve ==="
if [[ -f "data/eval/compounding/${NOVEL}.json" ]]; then
  python3 -c "
import json, sys
curve = json.load(open('data/eval/compounding/${NOVEL}.json'))
for half in ('detection', 'resolution'):
    rows = curve.get(half) or []
    if rows:
        print(f'  {half}: ' + ' '.join(f'w{r[0]}={r[1]:.0%}' for r in rows))
    else:
        print(f'  {half}: not recorded -- run the stage that writes it')
"
else
  echo "  no curve recorded yet; run: echotales --db $DB resolve --novel $NOVEL"
fi

echo
echo "=== ablations (re-scores cached evidence; needs --capture-evidence first) ==="
if echotales --db "$DB" ablate --novel "$NOVEL" 2>/dev/null; then
  :
else
  echo "  no cached evidence. Capture it with:"
  echo "    echotales --db <scratch.db> resolve --novel $NOVEL --capture-evidence"
fi

echo
echo "Results written under data/eval/results/. Each directory records the"
echo "commit, database, gold path and seed the numbers came from."
