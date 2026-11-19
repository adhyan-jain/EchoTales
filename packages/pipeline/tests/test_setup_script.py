"""scripts/setup.sh --dry-run picks a hardware preset from nvidia-smi without touching anything.

Why: the preset decides ECHOTALES_COMPUTE (local-low protects an 8 GB card from the OOM that froze the dev laptop),
so a wrong detection is a crash on first render, not a cosmetic bug.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "setup.sh"

pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="scripts/setup.sh missing")


def _run(tmp_path: Path, vram: str | None, *args: str) -> subprocess.CompletedProcess[str]:
    # A PATH holding only symlinks to what the script needs, so the host's real nvidia-smi can never leak in.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("bash", "awk", "head", "tr", "sed", "grep", "dirname", "cat"):
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)
    if vram is not None:
        stub = bindir / "nvidia-smi"
        stub.write_text(f"#!/bin/sh\necho {vram}\n")
        stub.chmod(0o755)
    env = {**os.environ, "PATH": str(bindir)}
    return subprocess.run(
        [str(bindir / "bash"), str(SCRIPT), "--dry-run", *args],
        capture_output=True, text=True, env=env, cwd=tmp_path, timeout=30,
    )


def test_8gb_card_gets_laptop_preset(tmp_path: Path) -> None:
    out = _run(tmp_path, "8188")
    assert out.returncode == 0, out.stderr
    assert "preset   laptop-8gb" in out.stdout
    assert "ECHOTALES_COMPUTE=local-low" in out.stdout
    assert "Apache-2.0" in out.stdout and "dry-run  nothing changed" in out.stdout


def test_24gb_card_gets_desktop_preset(tmp_path: Path) -> None:
    out = _run(tmp_path, "24564")
    assert "preset   desktop-24gb" in out.stdout
    assert "ECHOTALES_COMPUTE=local-high" in out.stdout


def test_no_nvidia_smi_falls_back_to_laptop(tmp_path: Path) -> None:
    out = _run(tmp_path, None)
    assert out.returncode == 0, out.stderr
    assert "vram     0 MiB" in out.stdout
    assert "preset   laptop-8gb" in out.stdout


def test_cloud_preset_lists_no_local_models(tmp_path: Path) -> None:
    out = _run(tmp_path, None, "--preset", "cloud")
    assert "ECHOTALES_COMPUTE=cloud" in out.stdout
    assert "gemma2:9b" not in out.stdout
