# EchoTales with CUDA 12 for the GPU engines. Build:  docker build -t echotales .
# Run:  docker compose up   (see compose.yaml). Models and books are NOT baked in: weights are large and carry their
# own licences, books are copyrighted. Mount them through the data/ volume.

# ---- web app ----
FROM node:20-slim AS web
WORKDIR /webview
COPY webview/package.json webview/package-lock.json ./
RUN npm ci
COPY webview/ ./
RUN npm run build

# ---- runtime ----
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-managed \
    PATH="/app/.venv/bin:/root/.local/bin:${PATH}"
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app
# `render` is the GPU image stack.
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
RUN uv sync --all-packages --no-dev --extra render

COPY config.json.example ./
COPY --from=web /webview/build ./webview/build

# All generated and user-supplied material lives here (databases, novels, voice banks, model weights).
VOLUME /app/data
EXPOSE 8787
# The container's own loopback is unreachable from the host, so bind all interfaces; compose publishes it on the
# host's 127.0.0.1 only.
CMD ["echotales", "webview-server", "--host", "0.0.0.0", "--port", "8787", "--static-dir", "webview/build"]
