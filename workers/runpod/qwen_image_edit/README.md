# qwen_image_edit: multi-reference keyframes (`qwen-image-edit-runpod`)

Handler for `echotales.pipeline.render.runpod_edit.RunPodEditEngine`. Contract is in `handler.py`'s docstring and is checked by `packages/pipeline/tests/test_runpod_workers.py`.

- **Model.** `Qwen/Qwen-Image-Edit-2509` (the release that takes several input images), run through diffusers `QwenImageEditPlusPipeline`. **Licence:** Apache-2.0 (verify on the model card).
- **GPU.** About 40 GB of bf16 weights: 80 GB (A100 / H100) is the safe pick; 48 GB (A6000 / L40S) works with `QWEN_OFFLOAD=1`, slower. A 24 GB card will not hold it without quantisation, which this worker does not do.
- **Image.** Weights baked in by default (~55 GB image, fast cold start). `--build-arg BAKE_WEIGHTS=0` for a small image that downloads on the first job.
- **Env vars.** `QWEN_MODEL_ID`, `QWEN_OFFLOAD` (`1` = CPU offload), `HF_HOME`.
- **Limits.** 1 to 3 references, sides 256..2048. Several PNG references as base64 can approach RunPod's request size cap (about 10 MB for `/run`, verify): send smaller reference sheets if a job is rejected on size.
- **Uncertain (verify).** The pipeline's argument names (`true_cfg_scale`, `image` as a list) against the pinned diffusers version, and the step count (40) as a quality/cost setting; neither has been run.
