"""Walk a reference file and record a person's accept or edit for each item.

The text of a line is shown at the prompt from the reader's own copy and is never written to the reference file.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eval.public import refs, sources


def _show(item: dict[str, Any], canonical: str | None) -> list[str]:
    lines = [f"[{item['id']}]"]
    if canonical is not None and "offset" in item:
        start = int(item["offset"])
        lines.append("  text:    " + canonical[start:start + int(item["length"])].replace("\n", " "))
        lines.append("  context: ..." + canonical[max(0, start - 160):start].replace("\n", " "))
    for key in ("speaker", "panel", "image", "characters", "required", "forbidden"):
        if key in item:
            lines.append(f"  {key}: {item[key]}")
    return lines


def walk(
    path: Path | str, canonical: str | None, *, ask: Callable[[str], str], say: Callable[[str], None],
    today: str | None = None,
) -> int:
    """Return how many items were accepted or edited. `a` accept, `e` edit the speaker, `s` skip, `q` quit.

    Refuses outright if the local text does not hash to what the reference recorded: a check against a different
    edition would mark wrong offsets as accepted."""
    doc = refs.load(path)
    today = today or datetime.date.today().isoformat()
    if canonical is not None:
        bad = [i["id"] for i in doc["items"] if "offset" in i and not sources.verify_slice(canonical, i)]
        if bad:
            raise ValueError(f"local text does not match the reference for {len(bad)} items (first: {bad[0]}); wrong edition?")
    changed = 0
    for item in doc["items"]:
        if item.get("checked_by_human"):
            continue
        for line in _show(item, canonical):
            say(line)
        answer = ask("accept [a], edit speaker [e], skip [s], quit [q]: ").strip().lower()
        if answer == "q":
            break
        if answer == "e" and "speaker" not in item:
            say("  only speaker items can be edited here; edit the JSON file for this one, or accept or skip")
            continue
        if answer == "e":
            new = ask("speaker: ").strip()
            if new and new != item.get("speaker"):
                item["edited_from"] = item.get("speaker")
                item["speaker"] = new
            answer = "a"
        if answer == "a":
            item["checked_by_human"] = True
            item["checked_on"] = today
            changed += 1
        refs.save(path, doc)
    refs.save(path, doc)
    return changed
