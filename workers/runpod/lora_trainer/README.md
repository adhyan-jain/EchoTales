# lora_trainer: Z-Image character LoRA (`character-lora-runpod`)

Handler for `echotales.pipeline.cloud_lora.submit`. Contract is in `handler.py`'s docstring and is checked by `packages/pipeline/tests/test_runpod_workers.py`.

**Z-Image Turbo LoRA training support is UNCERTAIN.** The trainer is [ostris/ai-toolkit](https://github.com/ostris/ai-toolkit). I believe it has a Z-Image Turbo architecture that trains through a "training adapter" (Turbo is step-distilled), but this was not checked against a real run. Before building, open the ai-toolkit repo, confirm an example config for Z-Image exists, pin `AI_TOOLKIT_REF` to that commit, and compare `_config()` in `handler.py` with it. If the installed build does not support the base, training exits non-zero and the job fails with the trainer's last output in the error. A `base_model` other than `z-image-turbo` is refused at once.

- **Models.** `Tongyi-MAI/Z-Image-Turbo`, **Apache-2.0** (stated in `THIRD_PARTY_LICENSES.md`). ai-toolkit: **MIT** (verify).
- **GPU.** 24 GB with the quantised config here (RTX 4090 class); 48 GB is more comfortable. Estimate: about 30 minutes for 1000 steps (an assumption, `JOB_SECONDS["lora"]`).
- **Image.** Small; weights (~12 GB) download on the first job. Attach a network volume at `/models` to keep them.
- **Env vars.** `AI_TOOLKIT_DIR` (default `/opt/ai-toolkit`), `ZIMAGE_MODEL_ID`, `HF_HOME`.
- **Output.** The `.safetensors` comes back base64 in the job output; a rank-16 file is tens of MB, which may exceed RunPod's output size cap (verify). If so, lower `rank` or send the file to your own storage from the handler.
- **Using it.** Put the file where `ECHOTALES_ZIMAGE_LORA` points (`workers_zimage.lora_args`).
