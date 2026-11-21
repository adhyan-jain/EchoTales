# wan_video: image-to-video (`wan-runpod`)

Handler for `echotales.pipeline.video.runpod_video.RunPodVideoEngine`. Contract is in `handler.py`'s docstring and is checked field by field by `packages/pipeline/tests/test_runpod_workers.py`.

- **Model.** Default `Wan-AI/Wan2.2-TI2V-5B-Diffusers` (Wan 2.2, 5B hybrid text/image-to-video). **Licence:** Apache-2.0 (verify on the model card before a public release).
- **GPU.** 24 GB is enough for the 5B model (RTX 4090 / L4 class; pick a 24 GB or 48 GB tier). For the A14B image-to-video repo set `WAN_MODEL_ID` and use an 80 GB GPU (A100 / H100), or 48 GB with `WAN_OFFLOAD=1` (slower).
- **Image.** Weights are baked in by default (cold start loads to GPU only, image is large). `--build-arg BAKE_WEIGHTS=0` makes a small image that downloads on the first job instead.
- **Env vars.** `WAN_MODEL_ID`, `WAN_OFFLOAD` (`1` = CPU offload), `WAN_WIDTH` / `WAN_HEIGHT` (default 832x480), `HF_HOME`.
- **Limits.** `num_frames` must be 4n+1 (5..161). `last_frame` is refused. `audio` is accepted and ignored (reported as `audio_ignored`): this is not a speech-to-video checkpoint, so `mode` `s2v` (the client default) behaves as `i2v`.
- **Uncertain (verify).** The diffusers class name and call arguments for the 5B checkpoint, the exact pinned versions, and RunPod's request/response size caps (a long clip as base64 may pass the response limit; shorten `num_frames` if a job fails on size).
