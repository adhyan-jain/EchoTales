#!/usr/bin/env bash
# One-shot local setup for EchoTales: hardware preset, Python workspace, the web app, and a check of the things it
# cannot install for you. Safe to re-run. It never downloads a model without listing it with its licence and asking.
#
#   scripts/setup.sh [--preset laptop-8gb|desktop-24gb|cloud] [--yes] [--dry-run]
#
#   --preset   override the detected preset (use `cloud` on a machine with no GPU that will call hosted models)
#   --yes      accept the model list without the y/N prompt
#   --dry-run  print the hardware, the preset and the model plan, then stop; changes nothing
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here" || exit 1
missing=0
yes=0
dry=0
preset=""

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) yes=1 ;;
    --dry-run) dry=1 ;;
    --preset) shift; preset="${1:-}" ;;
    --preset=*) preset="${1#--preset=}" ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

# Hardware. VRAM is the first card's total in MiB; no nvidia-smi (or no answer) counts as 0.
vram=0
if command -v nvidia-smi >/dev/null 2>&1; then
  vram="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -dc '0-9')"
  vram="${vram:-0}"
fi
ram_mb=0
if [ -r /proc/meminfo ]; then
  ram_mb="$(awk '/^MemTotal:/ {print int($2/1024)}' /proc/meminfo)"
fi

# Presets map to ECHOTALES_COMPUTE (packages/pipeline/src/echotales/pipeline/compute.py). 12 GB and up is the
# "desktop" tier from the roadmap (M5); below that, including no GPU, gets the safe laptop defaults.
if [ -z "$preset" ]; then
  if [ "$vram" -ge 12000 ]; then preset="desktop-24gb"; else preset="laptop-8gb"; fi
fi
case "$preset" in
  laptop-8gb) compute="local-low" ;;
  desktop-24gb) compute="local-high" ;;
  cloud) compute="cloud" ;;
  *) echo "unknown preset '$preset' (laptop-8gb, desktop-24gb, cloud)" >&2; exit 2 ;;
esac

echo "== hardware"
echo "vram     ${vram} MiB"
echo "ram      ${ram_mb} MiB"
echo "preset   $preset"
echo "compute  ECHOTALES_COMPUTE=$compute"

# Every model the code loads, with the licence it ships under. Hosted presets fetch nothing locally.
echo "== models (nothing is downloaded until you agree)"
if [ "$preset" = "cloud" ]; then
  echo "none     cloud preset: models run on the hosted provider you configure in .env"
else
  echo "model    Z-Image Turbo (Tongyi-MAI/Z-Image-Turbo), images      Apache-2.0   [manual: see docs/HANDOFF.md, ECHOTALES_ZIMAGE_DIR]"
  echo "model    Chatterbox TTS (Resemble AI), speech                  MIT          [fetched by the package on first use]"
  echo "model    gemma2:9b, reader and director                        Gemma Terms of Use   [ollama pull]"
  echo "model    qwen2.5:7b, name finding                              Apache-2.0   [ollama pull]"
  echo "data     LibriTTS-R, narrator voice bank                       CC BY 4.0    [manual: place under data/voice/]"
  echo "data     Hi-Fi TTS, narrator voice bank                        CC BY 4.0    [manual: place under data/voice/]"
fi
echo "Full list and notes: NOTICE and THIRD_PARTY_LICENSES.md"

if [ "$dry" = 1 ]; then
  echo "dry-run  nothing changed"
  exit 0
fi

pull_models=0
if [ "$preset" != "cloud" ]; then
  if [ "$yes" = 1 ]; then
    pull_models=1
  elif [ -t 0 ]; then
    printf "Download the ollama models above (gemma2:9b, qwen2.5:7b) and accept their licences? [y/N] "
    read -r answer
    case "$answer" in y|Y|yes|YES) pull_models=1 ;; esac
  else
    echo "note     not a terminal and no --yes: skipping model downloads"
  fi
fi

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
if grep -q '^ECHOTALES_COMPUTE=' .env 2>/dev/null; then
  echo "kept     ECHOTALES_COMPUTE already set in .env (preset suggests $compute)"
else
  echo "ECHOTALES_COMPUTE=$compute" >> .env && echo "wrote    ECHOTALES_COMPUTE=$compute to .env"
fi
[ -f config.json ] || { cp config.json.example config.json && echo "created  config.json from config.json.example"; }

echo "== language models (ollama)"
if command -v ollama >/dev/null 2>&1; then
  for model in gemma2:9b qwen2.5:7b; do
    if ollama list 2>/dev/null | grep -q "^$model"; then
      echo "ok       $model"
    else
      if [ "$pull_models" = 1 ]; then
        ollama pull "$model"
      else
        echo "pull it: ollama pull $model"
      fi
    fi
  done
fi

echo
echo "Voice bank: place LibriTTS-R or Hi-Fi TTS (both CC BY 4.0) under data/voice/ -- see docs/HANDOFF.md."
echo "            EARS is CC BY-NC 4.0: not for a commercial release."
echo "Run the tests:   ECHOTALES_LLM_MODE=stub uv run python -m pytest packages/core/tests packages/pipeline/tests"
echo "Start the app:   uv run echotales webview-server --static-dir webview/build"
echo "                 then open http://127.0.0.1:8787 and create a project (upload an EPUB)."
exit "$missing"
