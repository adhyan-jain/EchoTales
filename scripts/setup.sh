#!/usr/bin/env bash
# One-shot local setup for EchoTales: Python workspace, the web app, and a check of the things it cannot install
# for you. Safe to re-run. It downloads no voice bank and no novel (those have their own licences).
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here" || exit 1
missing=0

need() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "ok       $1"
  else
    echo "MISSING  $1 -- $2"
    missing=1
  fi
}

echo "== tools"
need uv "install from https://docs.astral.sh/uv/"
need node "Node 20 or newer, for the web app"
need ffmpeg "needed to write the audiobook (M4B) and the chapter videos"
need ollama "runs the language models locally; https://ollama.com"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | sed 's/^/gpu      /'
else
  echo "note     no NVIDIA GPU found: the placeholder (stub) engines still run, speech and images need a GPU"
fi

if ! command -v uv >/dev/null 2>&1 || ! command -v node >/dev/null 2>&1; then
  echo "Install the missing tools above, then run this again."
  exit 1
fi

echo "== python workspace"
uv sync --all-packages --group dev || exit 1

echo "== web app"
(cd webview && npm ci && npm run build) || exit 1

echo "== configuration"
[ -f .env ] || { cp .env.example .env && echo "created  .env from .env.example (edit it for your machine)"; }
[ -f config.json ] || { cp config.json.example config.json && echo "created  config.json from config.json.example"; }

echo "== language models (ollama)"
if command -v ollama >/dev/null 2>&1; then
  for model in gemma2:9b qwen2.5:7b; do
    if ollama list 2>/dev/null | grep -q "^$model"; then
      echo "ok       $model"
    else
      echo "pull it: ollama pull $model"
    fi
  done
fi

echo
echo "Voice bank: place CSTR VCTK (CC BY 4.0, fine for commercial use) under data/voice/ -- see docs/HANDOFF.md."
echo "            EARS is CC BY-NC 4.0: not for a commercial release."
echo "Run the tests:   ECHOTALES_LLM_MODE=stub uv run python -m pytest packages/core/tests packages/pipeline/tests"
echo "Start the app:   uv run echotales webview-server --static-dir webview/build"
echo "                 then open http://127.0.0.1:8787 and create a project (upload an EPUB)."
exit "$missing"
