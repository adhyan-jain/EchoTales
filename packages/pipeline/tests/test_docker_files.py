"""The container files keep the data volume and GPU reservation, and keep books and databases out of the image.

Why: an image that bakes in data/raw or a .epub would ship copyrighted text; a compose file without the volume loses
every render on `docker compose down`.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(not (ROOT / "compose.yaml").exists(), reason="compose.yaml missing")


def test_compose_has_data_volume_and_gpu_reservation() -> None:
    svc = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]["echotales"]
    assert any(str(v).endswith(":/app/data") for v in svc["volumes"])
    devices = svc["deploy"]["resources"]["reservations"]["devices"]
    assert any(d["driver"] == "nvidia" and "gpu" in d["capabilities"] for d in devices)


def test_dockerignore_keeps_books_and_databases_out() -> None:
    lines = {ln.strip() for ln in (ROOT / ".dockerignore").read_text().splitlines()}
    assert {"data/raw", "data/db", "*.epub", ".venv"} <= lines


def test_dockerfile_default_command_is_webview_server() -> None:
    text = (ROOT / "Dockerfile").read_text()
    assert 'CMD ["echotales", "webview-server"' in text
