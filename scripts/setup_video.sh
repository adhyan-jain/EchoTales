#!/usr/bin/env bash
# Create the video environment (.venv-video) used by echotales/pipeline/video/ltx_worker.py.
#
# Why a second environment: the video stack (torch 2.15 cu13, diffusers from main, transformers 5.22,
# bitsandbytes) conflicts with the main environment, and the main one must not change. The worker is run
# by file path with this interpreter, so echotales is not installed here.
#
# The pins are `uv pip freeze` of the environment the EVOLUTION 4.146 probe measured on (RTX 4060 Laptop
# 8 GB), 2026-11-15. Model weights are NOT downloaded here; they come from the Hugging Face cache
# (Lightricks/LTX-Video, Lightricks/LTX-Video-0.9.5, city96/t5-v1_1-xxl-encoder-bf16).
#
# Usage: scripts/setup_video.sh   then set in .env:  ECHOTALES_VIDEO_PYTHON=<repo>/.venv-video/bin/python
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || { echo "uv is required (https://docs.astral.sh/uv/)" >&2; exit 1; }
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-600}"

uv venv .venv-video --python 3.12
REQ="$(mktemp)"
trap 'rm -f "$REQ"' EXIT
cat > "$REQ" <<'REQS'
accelerate==1.15.0
annotated-doc==0.0.6
annotated-types==0.8.0
anyio==4.16.0
bitsandbytes==0.50.2
certifi==2026.10.23
charset-normalizer==3.5.2
click==8.5.1
cuda-bindings==13.5.0
cuda-pathfinder==1.8.6
cuda-toolkit==13.2.2
diffusers @ git+https://github.com/huggingface/diffusers@2c58e66a08a61ea5c58b9add560cf808e2c851de
filelock==4.2.10
fsspec==2026.9.0
ftfy==6.3.1
gguf==0.19.0
h11==0.16.0
hf-xet==1.8.0
httpcore2==2.16.0
httpx2==2.16.0
huggingface-hub==2.4.0
idna==3.20
imageio==2.38.1
imageio-ffmpeg==0.8.1
importlib-metadata==10.2.0
jinja2==3.1.6
lazy-importer==0.1.0
lazy-loader==0.6
markdown-it-py==4.3.0
markupsafe==3.0.4
mdurl==0.1.2
mpmath==1.3.0
networkx==3.7
numpy==2.5.4
nvidia-cublas==13.4.1.3
nvidia-cuda-cccl==13.3.5.0.6
nvidia-cuda-cupti==13.2.86
nvidia-cuda-nvrtc==13.2.86
nvidia-cuda-runtime==13.2.86
nvidia-cudnn-cu13==9.26.0.51
nvidia-cufft==12.2.0.57
nvidia-cufile==1.17.1.22
nvidia-cusolver==12.2.0.11
nvidia-cusparse==12.7.10.12
nvidia-cusparselt-cu13==0.8.1
nvidia-nccl-cu13==2.30.7
nvidia-nvjitlink==13.5.37
nvidia-nvshmem-cu13==3.7.2
nvidia-nvtx==13.2.86
opencv-python-headless==5.0.0.93
packaging==26.3
pillow==13.0.0
protobuf==7.36.2
psutil==7.2.2
pydantic==2.14.3
pydantic-core==2.50.4
pygments==2.21.0
pyyaml==6.0.3
regex==2026.11.9
requests==2.34.2
rich==15.0.0
safetensors==0.8.0
scikit-image==0.26.0
scipy==1.18.1
sentencepiece==0.2.3
setuptools==84.2.1
shellingham==1.5.4
sympy==1.14.0
tifffile==2026.11.12
tokenizers==0.23.3
torch==2.15.0
torchvision==0.29.2
tqdm==4.70.1
transformers==5.22.2
triton==3.9.0
truststore==0.10.5
typer==0.29.1
typing-extensions==4.16.0
typing-inspection==0.4.5
REQS
uv pip install --python .venv-video/bin/python -r "$REQ"
.venv-video/bin/python -c "import torch, diffusers, transformers; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
echo "done. Add to .env: ECHOTALES_VIDEO_PYTHON=$PWD/.venv-video/bin/python"
