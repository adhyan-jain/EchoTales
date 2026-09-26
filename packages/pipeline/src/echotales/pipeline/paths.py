"""Every location under data/, in one place.

**Asset type first, then chapter, then version.** With one chapter in flight
it made no difference; with two hundred it is the difference between a
browsable tree and a directory listing nobody can read. Every render writes a
new version rather than overwriting the last, so any two runs can be compared
side by side -- the rule `docs/HANDOFF.md` adopted after a render silently
destroyed the reference video an earlier review was written against.

    data/db/<novel-id>.db                  the novel's database (run of record)
    data/novels/<CODE>/panels/ch1/v3/      one render's panels
    data/novels/<CODE>/video/ch1/v3/       that render's finished video
    data/novels/<CODE>/audio/              synthesis output
    data/novels/<CODE>/references/         character reference sheets
    data/scratch/                          anything disposable

Until 2026-09-27 these defaults were scattered string literals, several
hard-coded to `data/RI/...`, so a render or voice run for any other novel
wrote into Reverend Insanity's folders, and a novel with no short code got a
second top-level directory (`data/lord-of-the-mysteries/`) beside `data/RI/`
(docs/EVOLUTION.md 4.94). Callers take their defaults from here.
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
DB_DIR = DATA_ROOT / "db"
NOVELS_DIR = DATA_ROOT / "novels"
SCRATCH_DIR = DATA_ROOT / "scratch"
EXPORTS_DIR = DATA_ROOT / "exports"
CACHE_DIR = DATA_ROOT / "cache"
EVAL_DIR = DATA_ROOT / "eval"
GOLD_DIR = DATA_ROOT / "gold"
LEXICON_DIR = DATA_ROOT / "lexicons"
CORRECTIONS_DIR = DATA_ROOT / "corrections"
VOICE_BANK_DIR = DATA_ROOT / "voice"
SOURCES_PATH = DATA_ROOT / "sources.toml"
#: The database used when neither `--db` nor a novel is given.
DEFAULT_DB = DB_DIR / "reverend-insanity.db"


def novel_code(novel_id: str) -> str:
    return NOVEL_CODES.get(novel_id, novel_id)


def novel_root(novel_id: str, *, data_root: Path | str = DATA_ROOT) -> Path:
    """The directory holding everything this novel's pipeline produces."""
    return Path(data_root) / "novels" / novel_code(novel_id)


def db_path(novel_id: str | None = None) -> Path:
    """`data/db/<novel-id>.db`, or the default database when no novel is named."""
    return DB_DIR / f"{novel_id}.db" if novel_id else DEFAULT_DB


def asset_dir(novel_id: str, kind: str, *, data_root: Path | str = DATA_ROOT) -> Path:
    """`data/<CODE>/<kind>` -- e.g. `data/novels/RI/panels`."""
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
