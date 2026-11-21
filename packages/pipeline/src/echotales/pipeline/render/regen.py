"""Redraw one panel, keep every attempt, and let the reviewer pick which picture the panel uses.

A render writes a version folder (`panels/ch1/v3_...`) with a `panel_plan.jsonl`. A single panel redraw never touches
that run: each attempt is a numbered round under `<version>/regen/<panel_seq>/` (`r1c0.png`, `r1c1.png`, ... plus
`index.json`), so nothing is overwritten and a bad redraw costs nothing. The pick is one line in `panel_choices.json`;
`render/plan.py::load_panel_plan` applies it, which is the one place pages, the episode video and the anime pass read
panels from, so a pick reaches every export without those code paths knowing about it (EVOLUTION 4.179).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from echotales.pipeline import paths
from echotales.pipeline.render.plan import (
    PANEL_PLAN_FILE,
    load_panel_plan,
)
from echotales.pipeline.render.plan import _read_choices as read_choices

CHOICES_FILE = "panel_choices.json"
REGEN_DIR = "regen"
ORIGINAL = "original"
MAX_CANDIDATES = 8
#: Two by default: a single draw gives the reviewer nothing to pick from, and each extra one is a full image.
DEFAULT_CANDIDATES = 2
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")


class PanelRegenError(ValueError):
    """The request names a panel, version or candidate that does not exist; the message says which."""


def default_candidates() -> int:
    from echotales.pipeline.config import get_settings

    configured = int(get_settings().render_candidates or 0)
    return min(max(configured, 1), MAX_CANDIDATES) if configured else DEFAULT_CANDIDATES


def chapter_dir(novel_id: str, chapter: float, out_dir: Path | str | None = None) -> Path:
    return Path(out_dir or paths.asset_dir(novel_id, "panels")) / f"ch{chapter:g}"


def version_dir(novel_id: str, chapter: float, version: str | None = None, out_dir: Path | str | None = None) -> Path:
    """The named version, or the newest one that has a panel plan (a root-level stub run has none)."""
    base = chapter_dir(novel_id, chapter, out_dir)
    if version:
        # A name from the request must stay one folder under the chapter, never a path.
        if not _SAFE.fullmatch(version) or ".." in version:
            raise PanelRegenError(f"version {version!r} is not a version folder name")
        found = base / version
        if not (found / PANEL_PLAN_FILE).is_file():
            raise PanelRegenError(f"chapter {chapter:g} has no rendered version {version!r}")
        return found

    def order(p: Path) -> int:
        head = p.name[1:].split("_")[0]
        return int(head) if p.name.startswith("v") and head.isdigit() else -1

    plans = sorted((p for p in base.glob("v*") if (p / PANEL_PLAN_FILE).is_file()), key=order)
    if not plans:
        raise PanelRegenError(f"chapter {chapter:g} has no rendered panels with a plan; render it first")
    return plans[-1]


def _panel_row(vdir: Path, panel_id: str):  # type: ignore[no-untyped-def]
    for row in load_panel_plan(vdir, apply_choices=False):
        if row.panel_id == panel_id:
            return row
    raise PanelRegenError(f"no panel {panel_id!r} in {vdir.name}")


def _index_path(vdir: Path, seq: int) -> Path:
    return vdir / REGEN_DIR / str(seq) / "index.json"


def _read_index(vdir: Path, seq: int) -> dict[str, Any]:
    try:
        index: dict[str, Any] = json.loads(_index_path(vdir, seq).read_text(encoding="utf-8"))
        return index
    except (OSError, ValueError):
        return {"rounds": []}


def screenplay_direction(store: Any, episode_id: str, shot_index: int) -> str:
    """The `action` text of a shot as saved in the screenplay editor ("Screenplay episode saved.")."""
    episode = store.get_screenplay_episode(episode_id)
    for shot in (episode or {}).get("shots", []):
        if int(shot.get("shot_index", -1)) == int(shot_index):
            return str(shot.get("action") or "").strip()
    raise PanelRegenError(f"episode {episode_id!r} has no shot {shot_index}")


def regenerate_panel(
    novel_id: str,
    *,
    chapter: float,
    panel_id: str,
    engine: Any,
    direction: str = "",
    candidates: int | None = None,
    version: str | None = None,
    out_dir: Path | str | None = None,
    job_id: str = "",
) -> dict[str, Any]:
    """Draw `candidates` new pictures of one panel from its recorded prompt, the direction (if any) leading it.

    The direction goes first so `fit_to_budget` keeps it: CLIP reads 77 tokens and the recorded prompt is already
    close to that, so an appended edit would be the first thing cut and the redraw would ignore it.
    """
    from echotales.pipeline.persona.prompt import (
        _USABLE_TOKENS,
        count_tokens,
        fit_to_budget,
    )
    from echotales.pipeline.render.panels import PanelImageRequest

    n = default_candidates() if candidates is None else int(candidates)
    if not 1 <= n <= MAX_CANDIDATES:
        raise PanelRegenError(f"candidates must be 1 to {MAX_CANDIDATES}, got {n}")
    vdir = version_dir(novel_id, chapter, version, out_dir)
    row = _panel_row(vdir, panel_id)
    direction = direction.strip()
    prompt = row.prompt
    if direction:
        reserved = count_tokens(getattr(engine, "quality_prefix", "") or "")
        prompt = fit_to_budget([direction, row.prompt], limit=max(_USABLE_TOKENS - reserved, 1))
    index = _read_index(vdir, row.panel_seq)
    folder = vdir / REGEN_DIR / str(row.panel_seq)
    # Files count too: an engine error part-way through a round leaves r<N>c0.png with no index line, and numbering from
    # the index alone reused N and then refused to overwrite, so that panel could never be redrawn again.
    on_disk = (int(m.group(1)) for f in folder.glob("r*c*.png") if (m := re.fullmatch(r"r(\d+)c\d+\.png", f.name)))
    rnd = 1 + max([*(int(r["round"]) for r in index["rounds"]), *on_disk], default=0)
    made: list[dict[str, str]] = []
    for i in range(n):
        target = folder / f"r{rnd}c{i}.png"
        if target.exists():  # a round number is never reused, so this means the index was lost; do not overwrite
            raise PanelRegenError(f"{target.name} already exists; refusing to overwrite a previous candidate")
        engine.generate(PanelImageRequest(
            prompt=prompt, out_path=target, negative_prompt=row.negative_prompt,
            width=row.width, height=row.height, seed=row.seed + 1000 * rnd + i,
        ))
        made.append({"id": f"r{rnd}c{i}", "file": f"{REGEN_DIR}/{row.panel_seq}/{target.name}"})
    index["rounds"].append({
        "round": rnd, "direction": direction, "prompt": prompt, "engine": getattr(engine, "name", ""),
        "job_id": job_id, "created": time.strftime("%Y-%m-%d %H:%M:%S"), "candidates": made,
    })
    _index_path(vdir, row.panel_seq).write_text(json.dumps(index, indent=2), encoding="utf-8")
    versions = vdir.parent / "VERSIONS.md"
    with versions.open("a", encoding="utf-8") as fh:
        fh.write(
            f"\n## {vdir.name} panel {row.panel_seq} redraw round {rnd}\n"
            f"{n} candidate(s) from the Studio ({job_id or 'no job'}, {time.strftime('%Y-%m-%d')}), "
            f"{'edited direction' if direction else 'same direction, new seeds'}; not yet reviewed.\n"
        )
    return {"version": vdir.name, "panel_id": panel_id, "round": rnd, "candidates": [m["id"] for m in made]}


def choose_candidate(
    novel_id: str, *, chapter: float, panel_id: str, candidate_id: str,
    version: str | None = None, out_dir: Path | str | None = None,
) -> dict[str, str]:
    """Make `candidate_id` (or `original`) the picture this panel uses from now on."""
    vdir = version_dir(novel_id, chapter, version, out_dir)
    row = _panel_row(vdir, panel_id)
    choices = read_choices(vdir)
    if candidate_id == ORIGINAL:
        choices.pop(panel_id, None)
        file = row.image_path
    else:
        found = {c["id"]: c["file"] for r in _read_index(vdir, row.panel_seq)["rounds"] for c in r["candidates"]}
        if candidate_id not in found or not (vdir / found[candidate_id]).is_file():
            raise PanelRegenError(f"panel {panel_id!r} has no candidate {candidate_id!r}")
        file = found[candidate_id]
        choices[panel_id] = file
    (vdir / CHOICES_FILE).write_text(json.dumps(choices, indent=2, sort_keys=True), encoding="utf-8")
    return {"version": vdir.name, "panel_id": panel_id, "candidate_id": candidate_id, "image": file}


def list_panels(
    novel_id: str, chapter: float, *, version: str | None = None, out_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Each panel of the version with its current picture, its candidates and the direction it was last drawn with.
    Paths are relative to the project's output folder (the `output/file` route serves them)."""
    vdir = version_dir(novel_id, chapter, version, out_dir)
    root = Path(out_dir) if out_dir else paths.novel_root(novel_id)
    choices = read_choices(vdir)
    seen: set[str] = set()
    panels: list[dict[str, Any]] = []

    def rel(file: str) -> str:
        try:
            return str((vdir / file).relative_to(root))
        except ValueError:
            return file

    for row in load_panel_plan(vdir, apply_choices=False):
        if row.panel_id in seen:
            continue
        seen.add(row.panel_id)
        index = _read_index(vdir, row.panel_seq)
        cands = [{"id": ORIGINAL, "round": 0, "direction": "", "path": rel(row.image_path)}]
        for r in index["rounds"]:
            cands += [
                {"id": c["id"], "round": r["round"], "direction": r["direction"], "path": rel(c["file"])}
                for c in r["candidates"]
            ]
        chosen = next((c["id"] for c in cands if c["path"] == rel(choices[row.panel_id])), ORIGINAL) \
            if row.panel_id in choices else ORIGINAL
        panels.append({
            "panel_id": row.panel_id, "panel_seq": row.panel_seq, "chosen": chosen, "candidates": cands,
            "prompt": row.prompt, "direction": index["rounds"][-1]["direction"] if index["rounds"] else "",
        })
    return {"novel_id": novel_id, "chapter": chapter, "version": vdir.name, "panels": panels}
