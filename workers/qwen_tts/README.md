# Qwen3-TTS & Dia2 Serverless Worker

RunPod Serverless Flex worker running Qwen3-TTS and Dia2 dialogue synthesis engines.

## Deployment to RunPod

1. Build and push container image:
   ```bash
   docker build -t your-org/echotales-qwen-tts:latest workers/qwen_tts/
   docker push your-org/echotales-qwen-tts:latest
   ```
2. Create RunPod Serverless Flex Endpoint:
   - GPU Type: RTX 3090 (24 GB) or RTX 4090 (24 GB)
   - Max Workers: 3
   - Idle Timeout: 15s
3. Configure EchoTales:
   - In `.env`: `ECHOTALES_RUNPOD_TTS_ENDPOINT_ID=<endpoint-id>`
   - `RUNPOD_API_KEY=<your-key>`
