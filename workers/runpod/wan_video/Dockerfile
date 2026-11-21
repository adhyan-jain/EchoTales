# Wan 2.2 image-to-video worker. Build from the repo root:  docker build -f workers/runpod/wan_video/Dockerfile -t REGISTRY/echotales-wan:1 .
# Base tag is pinned; confirm it still exists on Docker Hub (runpod/pytorch) before building (verify).
FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

ENV PYTHONUNBUFFERED=1 HF_HOME=/models/hf WAN_MODEL_ID=Wan-AI/Wan2.2-TI2V-5B-Diffusers
RUN pip install --no-cache-dir \
    runpod==1.7.13 diffusers==0.35.1 transformers==4.56.1 accelerate==1.10.1 \
    huggingface_hub==0.34.4 safetensors==0.6.2 sentencepiece==0.2.1 ftfy==6.3.1 imageio==2.37.0 imageio-ffmpeg==0.6.0 \
    pillow==11.3.0 numpy==1.26.4

# Weights baked in (BAKE_WEIGHTS=1, default): bigger image, a cold start that only loads to GPU.
# --build-arg BAKE_WEIGHTS=0 gives a small image that downloads ~25 GB on the first request instead (a slow first job).
ARG BAKE_WEIGHTS=1
RUN if [ "$BAKE_WEIGHTS" = "1" ]; then python -c "from huggingface_hub import snapshot_download; snapshot_download('${WAN_MODEL_ID}')"; fi

COPY workers/runpod/wan_video/handler.py /handler.py
CMD ["python", "-u", "/handler.py"]
