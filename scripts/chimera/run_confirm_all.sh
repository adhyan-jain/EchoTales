#!/bin/bash
# Sequence of the confirmatory model runs through the pod router (one model loaded at a time; the router swaps on demand).
# Priority order set by the owner at 17:58 IST: the OLMo corpus check and E5 first, so olmo32b runs E1 then E5 first (the corpus check
# needs e1_olmo32b and runs locally at once), then mistral24, then qwen32b. Judges: mistral24 judges qwen32b and olmo32b outputs,
# qwen32b judges mistral24 outputs (different family from the output's model, addendum 3). Minimises swaps: olmo, mistral, qwen, mistral.
# Usage: ( set -a; . ./.env; set +a; bash scripts/chimera/run_confirm_all.sh ); the key is read only from the environment.
set -u
cd "$(dirname "$0")/../.."
source .venv/bin/activate
R="python -u scripts/chimera/pd_confirm_run.py"
E2="--events data/scratch/confirm/e2/events.json --texts data/scratch/confirm/e2/texts --tag e2"
stamp() { echo "== $(date +%H:%M:%S) $*"; }
stamp olmo32b;   $R e1 --model olmo32b; (python -u scripts/chimera/pd_olmo_corpus_check.py > data/scratch/confirm/olmo_check.log 2>&1 &); $R e5 --model olmo32b; $R e1 --model olmo32b $E2; $R e4 --model olmo32b
stamp mistral24; $R e1 --model mistral24; $R e5 --model mistral24; $R e1 --model mistral24 $E2; $R e4 --model mistral24; $R e5judge --model mistral24 --of olmo32b
stamp qwen32b;   $R e1 --model qwen32b; $R e5 --model qwen32b; $R e4 --model qwen32b; $R e5judge --model qwen32b --of mistral24
stamp judge;     $R e5judge --model mistral24 --of qwen32b
stamp done
