# Qwen-Image Serverless Worker

RunPod Serverless Flex worker running Qwen-Image-2512 and Qwen-Image-Edit-2511 with Multiple Angles LoRA.

## Deployment to RunPod

1. Build and push container image:
   ```bash
   docker build -t your-org/echotales-qwen-image:latest workers/qwen_image/
   docker push your-org/echotales-qwen-image:latest
   ```
2. Create RunPod Serverless Flex Endpoint:
   - GPU Type: RTX 4090 (24 GB) or L40S (48 GB)
   - Max Workers: 5
   - Idle Timeout: 10s
   - Environment: `HF_TOKEN`, `MODEL_ID=Qwen/Qwen-Image-Edit-2511`
3. Configure EchoTales:
   - In `.env`: `ECHOTALES_RUNPOD_IMAGE_ENDPOINT_ID=<endpoint-id>`
   - `RUNPOD_API_KEY=<your-key>`
