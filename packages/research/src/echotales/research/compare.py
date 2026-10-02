"""Line up runs of one hypothesis side by side (summary metrics, mode,
config hash, dirty-tree flag) -- the table a DECISION_LOG entry cites."""

from __future__ import annotations

import json
from pathlib import Path

from echotales.pipeline.paths import RESEARCH_DIR


def runs(hypothesis_id: str, root: Path = RESEARCH_DIR) -> list[dict]:
    out = []
    for d in sorted((Path(root) / hypothesis_id).glob("*/")):
        res, prov = d / "results.json", d / "provenance.json"
        if not res.exists():
            continue
        r = json.loads(res.read_text())
        p = json.loads(prov.read_text()) if prov.exists() else {}
        out.append({"run": d.name, "mode": r["mode"], "config_hash": r["config_hash"],
                    "dirty": p.get("git_dirty"), "sha": (p.get("git_sha") or "")[:8],
                    "verdict_hint": r["verdict_hint"], "summary": r["summary"]})
    return out


def markdown_table(hypothesis_id: str, keys: list[str], root: Path = RESEARCH_DIR) -> str:
    rows = runs(hypothesis_id, root)
    head = "| run | mode | sha | dirty | " + " | ".join(keys) + " |"
    sep = "|" + "---|" * (4 + len(keys))
    lines = [head, sep]
    for r in rows:
        vals = [str(r["summary"].get(k, "")) for k in keys]
        lines.append(f"| {r['run']} | {r['mode']} | {r['sha']} | {r['dirty']} | "
                     + " | ".join(vals) + " |")
    return "\n".join(lines)
