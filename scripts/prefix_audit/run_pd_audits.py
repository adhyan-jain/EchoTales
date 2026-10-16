"""Run the audits of PREREG_PD.md: two public-domain books x {status quo, plain repair, anchored (1, 0.8), anchored (2, 0.8)}.

    /home/adhyan/Desktop/EchoTales/.venv/bin/python scripts/prefix_audit/run_pd_audits.py

Requires the stores from scripts/prefix_audit/pd_volume.py. At most 4 jobs at a time. CPU only, no model call.
"""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
PY = "/home/adhyan/Desktop/EchoTales/.venv/bin/python"
BOOKS = ("oliver-twist", "three-musketeers")
RES = WT / "data" / "eval" / "prefix_audit"
VARIANTS = [("off", None, "audit_repair-off_{n}.json"), ("on", None, "audit_repair-on_{n}.json"),
            ("on", "1,0.8", "audit_anch1_80-on_{n}.json"), ("on", "2,0.8", "audit_anch2_80-on_{n}.json")]


def run(job: tuple[str, str, str | None, str]) -> int:
    nid, repair, anchored, name = job
    cmd = [PY, str(WT / "scripts/prefix_audit/audit.py"), "--novel", nid, "--repair", repair, "--out", str(RES / name.format(n=nid))]
    if anchored:
        cmd += ["--anchored", anchored]
    env = {"PYTHONPATH": f"{WT}/packages/core/src:{WT}/packages/pipeline/src", "PATH": "/usr/bin:/bin"}
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=WT)
    print(nid, repair, anchored, "exit", r.returncode, flush=True)
    if r.returncode:
        print(r.stderr[-600:], flush=True)
    return r.returncode


def main() -> None:
    jobs = [(n, rep, anc, name) for n in BOOKS for rep, anc, name in VARIANTS]
    with ThreadPoolExecutor(max_workers=4) as ex:
        sys.exit(1 if any(ex.map(run, jobs)) else 0)


if __name__ == "__main__":
    main()
