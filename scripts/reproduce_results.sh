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
#   * There is NO human gold (EVOLUTION 4.74). Metrics are scored against the
#     SILVER tier -- LLM-drafted, non-circular records (docs/results/GOLD_DATASET_README.md)
#     -- and every report carries that banner. That is not a bug in this script.
#   * The default DB is the canonical v1 run (docs/results/CANONICAL_RUN.md, EVOLUTION
#     4.90), promoted to data/db/reverend-insanity.db with its sha256 recorded.
#     The diagnostics scripts default to the same path.

set -euo pipefail

NOVEL="${1:-reverend-insanity}"
DB="${2:-data/db/reverend-insanity.db}"
HARDCASES="data/gold/${NOVEL}-hardcases.jsonl"
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
echo "=== silver reference set: automatic validation ==="
# Exits non-zero on the main RI file by design: its circular records fail the
# surface-triviality check, and 777 spans no longer sit at their offset (7 of
# them silver -- see docs/results/GOLD_DATASET_README.md "Span drift"). The verdict is
# the finding; it must not abort the rest of the reproduction.
echotales --db "$DB" eval --novel "$NOVEL" --validate-gold || echo "  (validation verdict: FAIL -- expected, see above)"

if [[ -f "$HARDCASES" ]]; then
  echo
  echo "=== hard-case set: per-alias-type recall@K (SILVER) ==="
  echotales --seed "$SEED" --db "$DB" eval --novel "$NOVEL" --gold "$HARDCASES"
fi

if [[ "$NOVEL" == "reverend-insanity" ]]; then
  echo
  echo "=== diagnostics (RI only; hardcoded to the measured rerun DB) ==="
  python3 scripts/eval/recall_by_category.py --db "$DB"  # -> data/eval/recall_by_category.json
  python3 scripts/eval/hardcase_resolution.py --db "$DB"  # -> data/eval/hardcase_resolution.json
  python3 scripts/eval/scorer_diagnosis.py --db "$DB"
  python3 scripts/eval/scorer_fit_probe.py
  python3 scripts/eval/baseline_comparison.py --db "$DB"  # -> data/eval/baseline_comparison.json
  python3 scripts/eval/observer_ablation.py --db "$DB"   # A1/A2 -> data/eval/observer_ablation.json
  # A7 is slow (8 full stub render passes, ~30 min) and LitBank needs a local
  # ollama plus the corpus under data/external/litbank; run them explicitly:
  #   python3 scripts/eval/a7_cache_ablation.py --db "$DB"
  #   python3 scripts/eval/litbank_eval.py
  python3 scripts/paper/make_paper_artifacts.py    # -> docs/paper/TABLES.md, FIGURES.md
  python3 scripts/paper/plot_paper_figures.py      # -> docs/paper/figures/*.svg (plots)
  python3 scripts/paper/draw_diagrams.py           # -> Figures 1-7 (diagrams; 5 and 6 to docs/private)
fi

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
if echotales --db "$DB" ablate --novel "$NOVEL" --out "data/eval/ablation/${NOVEL}.json" 2>/dev/null; then
  :
else
  echo "  no cached evidence. Capture it with:"
  echo "    echotales --db <scratch.db> resolve --novel $NOVEL --capture-evidence"
fi

echo
echo "Results written under data/eval/results/. Each directory records the"
echo "commit, database, gold path and seed the numbers came from."
