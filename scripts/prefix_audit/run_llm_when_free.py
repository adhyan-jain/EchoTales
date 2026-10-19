"""Run the real-model audit of the prefix-causal gate when the GPU is free (PREREG_LLM.md Addendum 3).

    PYTHONPATH=<worktree>/packages/core/src:<worktree>/packages/pipeline/src \
      /home/adhyan/Desktop/EchoTales/.venv/bin/python scripts/prefix_audit/run_llm_when_free.py

The GPU is shared with another session. This waits until `llm_audit.gpu_is_free()` has held for 60 s in a row, then runs one
serial at a time; if the guard refuses mid-run (the other session loaded a model) it waits again. My own model stays resident
after a run and would trip the guard for the next serial, so it is unloaded with `ollama stop`, but only when the loaded model
is mine (context 8192, as in .env); a model at another context belongs to the other session and is never touched.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import llm_audit as L  # noqa: E402

PY = "/home/adhyan/Desktop/EchoTales/.venv/bin/python"
NOVELS = ("omniscient-readers-viewpoint", "lord-of-the-mysteries", "reverend-insanity")
MAX_WAIT_S = 4 * 3600
MY_CONTEXT = "8192"


def wait_free(deadline: float) -> bool:
    ok_since = None
    while time.time() < deadline:
        free, _why = L.gpu_is_free()
        if free:
            ok_since = ok_since or time.time()
            if time.time() - ok_since >= 60:
                return True
        else:
            ok_since = None
        time.sleep(20)
    return False


def unload_mine() -> None:
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout.splitlines()[1:]
    for line in out:
        parts = line.split()
        if parts and MY_CONTEXT in parts:
            subprocess.run(["ollama", "stop", parts[0]], capture_output=True)
    time.sleep(8)


def main() -> None:
    deadline = time.time() + MAX_WAIT_S
    for nid in NOVELS:
        if (WT / "data/eval/prefix_audit" / f"llm_model_pc_{nid}.json").exists():
            continue
        while True:
            if not wait_free(deadline):
                print("gave up waiting for the GPU", flush=True)
                sys.exit(2)
            r = subprocess.run([PY, str(HERE / "llm_audit.py"), "--novel", nid, "--backend", "model", "--prefix-causal"],
                               env={"PYTHONPATH": f"{WT}/packages/core/src:{WT}/packages/pipeline/src", "PATH": "/usr/bin:/bin:/usr/local/bin",
                                    "PREFIX_AUDIT_ALLOW_GPU": "1", "HOME": "/home/adhyan"},
                               capture_output=True, text=True, cwd=WT)
            tail = (r.stdout + r.stderr)[-300:].replace("\n", " | ")
            print(nid, "exit", r.returncode, tail, flush=True)
            unload_mine()
            if r.returncode == 0:
                break
            if "refusing to start" not in r.stdout + r.stderr:  # a real failure, not the guard
                sys.exit(1)


if __name__ == "__main__":
    main()
