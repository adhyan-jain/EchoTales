"""On-demand model router for the RunPod L40S pod (runs ON THE POD, not locally).

Why: the 48 GB card holds one model at a time and every swap used to need the owner to paste commands into the web terminal. This
process owns public port 8000 and starts the requested vLLM model on an internal port when a request names a model that is not
loaded. While a swap is in progress it answers HTTP 503 {"error":"loading"} at once (the RunPod proxy cuts any request that waits
longer than about 100 s, so requests must not be held), and the client retries (pd_remote_run.ensure_model).

Callers: started once on the pod by the owner (`nohup python /workspace/pod_router.py ...`); called by scripts/chimera/pd_remote_run.py
over the public proxy URL with the same bearer token as before (env VLLM_API_KEY). The vLLM children use the same flags as the exploratory
runs. ROUTER_FAKE=1 swaps the vLLM command for a stub server so the swap logic can be tested without a GPU (pod_router_fake.py).
"""
import asyncio
import os
import signal
import subprocess
import sys

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

KEY = os.environ["VLLM_API_KEY"]
PUBLIC_PORT = int(os.environ.get("ROUTER_PORT", "8000"))
INNER = int(os.environ.get("ROUTER_INNER_PORT", "8001"))
VLLM = os.environ.get("VLLM_BIN", "/workspace/venv/bin/vllm")
FAKE = os.environ.get("ROUTER_FAKE") == "1"
COMMON = ["--api-key", KEY, "--host", "127.0.0.1", "--port", str(INNER), "--gpu-memory-utilization", "0.92"]
MODELS = {
    "qwen32b": ["Qwen/Qwen2.5-32B-Instruct-AWQ", "--max-model-len", "8192"],
    "olmo32b": ["allenai/OLMo-2-0325-32B-Instruct", "--quantization", "fp8", "--max-model-len", "4096"],
    "mistral24": ["mistralai/Mistral-Small-3.2-24B-Instruct-2506", "--quantization", "fp8", "--tokenizer-mode", "mistral",
                  "--config-format", "mistral", "--load-format", "mistral", "--limit-mm-per-prompt", '{"image":0}',
                  "--max-model-len", "8192"],
}
state = dict(current=None, ready=False, want=None, proc=None, inflight=0, switching=False, error=None)
app = FastAPI()
client = httpx.AsyncClient(timeout=httpx.Timeout(600.0))


def command(name):
    if FAKE:
        return [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pod_router_fake.py"), name, str(INNER)]
    return [VLLM, "serve", MODELS[name][0], "--served-model-name", name] + MODELS[name][1:] + COMMON


async def stop():
    p = state["proc"]
    if p and p.poll() is None:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        for _ in range(60):
            if p.poll() is not None:
                break
            await asyncio.sleep(1)
        if p.poll() is None:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        await asyncio.sleep(1 if FAKE else 3)  # let the GPU memory free
    state["proc"] = None


async def switcher():
    if state["switching"]:
        return
    state["switching"] = True
    try:
        while state["want"] and state["want"] != state["current"]:
            name = state["want"]
            state["ready"] = False
            while state["inflight"] > 0:
                await asyncio.sleep(0.5)
            await stop()
            state["current"], state["error"] = None, None
            log = open(os.devnull if FAKE else f"/workspace/vllm_{name}.log", "wb")
            state["proc"] = subprocess.Popen(command(name), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            for _ in range(1500):  # up to 25 minutes (the first download of a model is slow)
                if state["proc"].poll() is not None:
                    state["error"] = f"{name} exited with code {state['proc'].returncode}"
                    break
                try:
                    r = await client.get(f"http://127.0.0.1:{INNER}/health", timeout=3.0)
                    if r.status_code == 200:
                        state["current"], state["ready"] = name, True
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(1)
            if not state["ready"]:
                state["want"] = state["current"]  # give up on this model; the client sees the error in /router/status
    finally:
        state["switching"] = False


def authed(request: Request) -> bool:
    return request.headers.get("authorization") == f"Bearer {KEY}"


@app.get("/router/status")
async def status(request: Request):
    if not authed(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return {k: state[k] for k in ("current", "ready", "want", "inflight", "switching", "error")}


@app.get("/v1/models")
async def models(request: Request):
    if not authed(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return {"object": "list", "data": [{"id": n, "object": "model", "loaded": n == state["current"] and state["ready"]} for n in MODELS]}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    if not authed(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    name = body.get("model")
    if name not in MODELS:
        return JSONResponse({"error": f"unknown model {name}"}, status_code=400)
    if not (state["current"] == name and state["ready"]):
        state["want"] = name
        asyncio.create_task(switcher())
        return JSONResponse({"error": "loading", "model": name, "detail": state["error"]}, status_code=503, headers={"Retry-After": "10"})
    state["inflight"] += 1
    try:
        r = await client.post(f"http://127.0.0.1:{INNER}/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {KEY}"})
        return JSONResponse(r.json(), status_code=r.status_code)
    except httpx.HTTPError as e:
        return JSONResponse({"error": f"upstream {type(e).__name__}"}, status_code=502)
    finally:
        state["inflight"] -= 1


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PUBLIC_PORT, log_level="warning")
