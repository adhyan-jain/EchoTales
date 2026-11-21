# Qwen-Image-Edit-2509 worker. Build from the repo root:  docker build -f workers/runpod/qwen_image_edit/Dockerfile -t REGISTRY/echotales-qwen-edit:1 .
# Base tag is pinned; confirm it still exists on Docker Hub (runpod/pytorch) before building (verify).
FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

ENV PYTHONUNBUFFERED=1 HF_HOME=/models/hf QWEN_MODEL_ID=Qwen/Qwen-Image-Edit-2509
RUN pip install --no-cache-dir \
    runpod==1.7.13 diffusers==0.35.1 transformers==4.56.1 accelerate==1.10.1 \
    huggingface_hub==0.34.4 safetensors==0.6.2 sentencepiece==0.2.1 pillow==11.3.0 numpy==1.26.4

# Weights baked in (BAKE_WEIGHTS=1, default): ~55 GB image, but a cold start only loads to GPU instead of downloading.
# --build-arg BAKE_WEIGHTS=0 gives a small image that downloads on the first request (minutes, billed as GPU time).
ARG BAKE_WEIGHTS=1
RUN if [ "$BAKE_WEIGHTS" = "1" ]; then python -c "from huggingface_hub import snapshot_download; snapshot_download('${QWEN_MODEL_ID}')"; fi

COPY workers/runpod/qwen_image_edit/handler.py /handler.py
CMD ["python", "-u", "/handler.py"]
