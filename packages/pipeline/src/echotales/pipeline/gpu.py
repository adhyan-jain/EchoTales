"""Is the GPU free for a model that will load onto it?

The owner's rule (2026-10-02, after a RAM spike): heavy models go on the GPU only after checking it is free, and never
offload into system RAM. The CLI leaves that check to the person at the keyboard; a render queued from the Studio has
nobody checking, so the server asks here before it accepts a job that loads an image model. `nvidia-smi` rather than a
CUDA binding, so the answer is available without importing torch (`llm/client.py::detect_vram_bytes` does the same).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

#: Above this much memory already in use, something else (ollama, another render) is holding the card.
BUSY_ABOVE_MB = 1500


@dataclass(frozen=True, slots=True)
class GpuStatus:
    name: str
    used_mb: int
    total_mb: int

    @property
    def free(self) -> bool:
        return self.used_mb <= BUSY_ABOVE_MB

    def describe(self) -> str:
        return f"{self.name}: {self.used_mb} of {self.total_mb} MiB in use"


def gpu_status() -> GpuStatus | None:
    """The first GPU's memory use, or None when there is no NVIDIA GPU (or it cannot be read)."""
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        name, used, total = (part.strip() for part in out.stdout.strip().splitlines()[0].split(","))
        return GpuStatus(name, int(float(used)), int(float(total)))
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        return None
