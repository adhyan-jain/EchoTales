"""Run the audits of PREREG_ANCHORED.md Addendum 1 (cue window v2).

    /home/adhyan/Desktop/EchoTales/.venv/bin/python scripts/prefix_audit/run_v2_audits.py

Confirmatory data: the three web-novel serials at the 24 cuts of the original sweep. Development data: the two English books at
their default cuts. Settings (1, 0.8) and (2, 0.8), window variant v2. At most 4 jobs at a time. CPU only, no model call.
"""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
PY = "/home/adhyan/Desktop/EchoTales/.venv/bin/python"
RES = WT / "data" / "eval" / "prefix_audit"
CUTS = {
    "lord-of-the-mysteries": "5,10,15,20,25,30,35",
    "omniscient-readers-viewpoint": "5,10,15,20,25,30,35",
    "reverend-insanity": "10,20,30,40,60,80,100,120,140,160",
    "oliver-twist": None,
    "three-musketeers": None,
}
SETTINGS = ((1, 0.8), (2, 0.8))


def run(job: tuple[str, int, float]) -> int:
    nid, m, g = job
    out = RES / f"audit_anchv2_{m}_{round(g * 100)}-on_{nid}.json"
    cmd = [PY, str(WT / "scripts/prefix_audit/audit.py"), "--novel", nid, "--repair", "on", "--anchored", f"{m},{g},v2", "--out", str(out)]
    if CUTS[nid]:
        cmd += ["--ks", CUTS[nid]]
    env = {"PYTHONPATH": f"{WT}/packages/core/src:{WT}/packages/pipeline/src", "PATH": "/usr/bin:/bin"}
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=WT)
    print(nid, m, g, "exit", r.returncode, flush=True)
    if r.returncode:
        print(r.stderr[-500:], flush=True)
    return r.returncode


def main() -> None:
    jobs = [(nid, m, g) for (m, g) in SETTINGS for nid in CUTS]
    with ThreadPoolExecutor(max_workers=4) as ex:
        sys.exit(1 if any(ex.map(run, jobs)) else 0)


if __name__ == "__main__":
    main()
