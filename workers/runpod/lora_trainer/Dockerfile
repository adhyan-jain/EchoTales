# Z-Image character LoRA trainer (ostris/ai-toolkit). Build from the repo root:
#   docker build -f workers/runpod/lora_trainer/Dockerfile -t REGISTRY/echotales-lora:1 .
# Base tag is pinned; confirm it still exists on Docker Hub (runpod/pytorch) before building (verify).
FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

ENV PYTHONUNBUFFERED=1 HF_HOME=/models/hf AI_TOOLKIT_DIR=/opt/ai-toolkit ZIMAGE_MODEL_ID=Tongyi-MAI/Z-Image-Turbo
# AI_TOOLKIT_REF must be a commit that knows the zimage architecture; replace "main" with that commit hash after checking
# (verify). Pinned by hash so a later upstream change cannot alter a training run.
ARG AI_TOOLKIT_REF=main
RUN git clone https://github.com/ostris/ai-toolkit.git ${AI_TOOLKIT_DIR} \
    && git -C ${AI_TOOLKIT_DIR} checkout ${AI_TOOLKIT_REF} \
    && pip install --no-cache-dir -r ${AI_TOOLKIT_DIR}/requirements.txt \
    && pip install --no-cache-dir runpod==1.7.13

# Weights are NOT baked in: training runs for many minutes, so a one-time ~12 GB download on the first job is small next
# to it, and the image stays small. Mount a RunPod network volume at /models to keep the download across cold starts.
COPY workers/runpod/lora_trainer/handler.py /handler.py
CMD ["python", "-u", "/handler.py"]
