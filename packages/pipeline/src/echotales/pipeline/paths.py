"""Where a novel's rendered output lives on disk.

**Asset type first, then chapter, then version.** With one chapter in flight
it made no difference; with two hundred it is the difference between a
browsable tree and a directory listing nobody can read. Every render writes a
new version rather than overwriting the last, so any two runs can be compared
side by side -- the rule `HANDOFF.md` adopted after a render silently
destroyed the reference video an earlier review was written against.

    data/<CODE>/panels/ch1/v3/...      one render's panels
    data/<CODE>/video/ch1/v3/...       that render's finished video
    data/<CODE>/audio/ch1/...          synthesis output
    data/<CODE>/references/            IP-Adapter character sheets

The novel's short code is the directory, so the output root is already
novel-scoped and nothing below it repeats the novel id.
"""

from __future__ import annotations

from pathlib import Path

#: Short directory codes. A novel with no entry falls back to its full id,
#: which is unambiguous if ugly -- better than inventing an abbreviation
#: that later collides with a real one.
NOVEL_CODES = {
    "reverend-insanity": "RI",
    "lord-of-the-mysteries": "LOTM",
    "omniscient-readers-viewpoint": "ORV",
}

DATA_ROOT = Path("data")


def novel_code(novel_id: str) -> str:
    return NOVEL_CODES.get(novel_id, novel_id)


def novel_root(novel_id: str, *, data_root: Path | str = DATA_ROOT) -> Path:
    """The directory holding everything this novel's pipeline produces."""
    return Path(data_root) / novel_code(novel_id)


def asset_dir(novel_id: str, kind: str, *, data_root: Path | str = DATA_ROOT) -> Path:
    """`data/<CODE>/<kind>` -- e.g. `data/RI/panels`."""
    return novel_root(novel_id, data_root=data_root) / kind


def next_version(base: Path) -> str:
    """The next unused `vN` under `base`.

    Versions are per chapter, so `base` is expected to be
    `.../panels/ch1`. Numbering continues from the highest existing `vN`
    rather than counting directories, so deleting an old version never
    causes a new render to overwrite a surviving one.
    """
    highest = 0
    if base.is_dir():
        for child in base.iterdir():
            name = child.name
            if child.is_dir() and name.startswith("v") and name[1:].split("_")[0].isdigit():
                highest = max(highest, int(name[1:].split("_")[0]))
    return f"v{highest + 1}"
