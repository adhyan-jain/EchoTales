"""Run the pre-registered grid of the anchored pronoun cue (docs/research/PREFIX_FAITHFULNESS/PREREG_ANCHORED.md).

    /home/adhyan/Desktop/EchoTales/.venv/bin/python scripts/prefix_audit/sweep_anchored.py

Six settings (min_obs 1/2/3 x majority 0.8/1.0) on the three serials at the 13 original and 11 added cuts, repair on, so the
full build and every truncated build use the same extractor. At most 4 jobs at a time (RAM). CPU only, no model call.
"""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
PY = "/home/adhyan/Desktop/EchoTales/.venv/bin/python"
CUTS = {
    "lord-of-the-mysteries": "5,10,15,20,25,30,35",
    "omniscient-readers-viewpoint": "5,10,15,20,25,30,35",
    "reverend-insanity": "10,20,30,40,60,80,100,120,140,160",
}
GRID = [(m, g) for m in (1, 2, 3) for g in (0.8, 1.0)]


def run(job: tuple[str, int, float]) -> tuple[str, int]:
    nid, m, g = job
    out = WT / "data" / "eval" / "prefix_audit" / f"audit_anch{m}_{round(g * 100)}-on_{nid}.json"
    env = {"PYTHONPATH": f"{WT}/packages/core/src:{WT}/packages/pipeline/src", "PATH": "/usr/bin:/bin"}
    r = subprocess.run([PY, str(WT / "scripts/prefix_audit/audit.py"), "--novel", nid, "--repair", "on", "--ks", CUTS[nid],
                        "--anchored", f"{m},{g}", "--out", str(out)], env=env, capture_output=True, text=True, cwd=WT)
    print(nid, m, g, "exit", r.returncode, flush=True)
    if r.returncode:
        print(r.stderr[-400:], flush=True)
    return nid, r.returncode


def main() -> None:
    jobs = [(nid, m, g) for (m, g) in GRID for nid in CUTS]
    with ThreadPoolExecutor(max_workers=4) as ex:
        codes = list(ex.map(run, jobs))
    sys.exit(1 if any(c for _n, c in codes) else 0)


if __name__ == "__main__":
    main()
