"""Reference files under data/eval/benchmark/: load, validate, and say how much of each a person has checked.

The state words are deliberate. A reference is "drafted by a model" until every item has `checked_by_human: true` with
a `checked_on` date; until then `banner()` says NOT human-verified, and nothing here ever says "verified" for a file
with an unchecked item.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BENCH_DIR = Path("data/eval/benchmark")
TASKS = ("speaker", "identity", "scene")


def load(path: Path | str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return doc


def save(path: Path | str, doc: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find(bench_dir: Path | str = BENCH_DIR, task: str | None = None) -> list[Path]:
    return sorted(p for p in Path(bench_dir).glob("*__*.json") if task is None or p.name.startswith(f"{task}__"))


def validate(doc: dict[str, Any]) -> None:
    if doc.get("task") not in TASKS:
        raise ValueError(f"task must be one of {TASKS}, not {doc.get('task')!r}")
    for item in doc.get("items", []):
        if item.get("checked_by_human") and not item.get("checked_on"):
            raise ValueError(f"item {item.get('id')}: checked_by_human is true but checked_on is missing")


def status(doc: dict[str, Any]) -> dict[str, Any]:
    items = doc.get("items", [])
    checked = sum(1 for i in items if i.get("checked_by_human") is True)
    return {"items": len(items), "checked": checked, "unchecked": len(items) - checked,
            "fully_checked": bool(items) and checked == len(items)}


def banner(st: dict[str, Any]) -> str:
    if st["fully_checked"]:
        return f"all {st['items']} items checked by a person"
    return (f"NOT human-verified: {st['checked']} of {st['items']} items checked by a person; "
            "the rest are a model's draft, so any score is a regression number, not an accuracy claim")
