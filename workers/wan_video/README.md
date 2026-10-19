# Wan 2.2 Video Serverless Worker

RunPod Serverless Flex worker running Wan 2.2 S2V (Speech-to-Video lip-sync) and Wan 2.2 A14B + LightX2V 4-step video generator.

## Deployment to RunPod

1. Build and push container image:
   ```bash
   docker build -t your-org/echotales-wan-video:latest workers/wan_video/
   docker push your-org/echotales-wan-video:latest
   ```
2. Create RunPod Serverless Flex Endpoint:
   - GPU Type: RTX 4090 (24 GB) or L40S (48 GB) / A100 (80 GB)
   - Max Workers: 3
   - Idle Timeout: 20s
3. Configure EchoTales:
   - In `.env`: `ECHOTALES_RUNPOD_VIDEO_ENDPOINT_ID=<endpoint-id>`
   - `RUNPOD_API_KEY=<your-key>`
