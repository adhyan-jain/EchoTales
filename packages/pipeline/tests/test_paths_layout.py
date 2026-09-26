"""The data/ layout (data/README.md) as the code resolves it.

Before 2026-09-27 output defaults were literals, several hard-coded to
`data/RI/...`: `echotales voice --novel lord-of-the-mysteries` wrote into
Reverend Insanity's audio folder, and a novel without a short code grew its
own top-level directory beside `data/RI/`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from echotales.pipeline import paths
from echotales.pipeline.cli import _fill_path_defaults, build_parser

REPO_ROOT = Path(__file__).resolve().parents[3]


def _args(*argv: str):
    args = build_parser().parse_args(list(argv))
    _fill_path_defaults(args)
    return args


def test_every_novel_lives_under_data_novels_by_code() -> None:
    assert paths.novel_root("reverend-insanity") == Path("data/novels/RI")
    assert paths.novel_root("lord-of-the-mysteries") == Path("data/novels/LOTM")
    assert paths.novel_root("some-new-book") == Path("data/novels/some-new-book")


def test_the_database_defaults_to_the_novels_own() -> None:
    assert _args("voice", "--novel", "lord-of-the-mysteries").db == "data/db/lord-of-the-mysteries.db"


def test_an_explicit_db_is_kept() -> None:
    assert _args("--db", "data/scratch/x.db", "voice", "--novel", "reverend-insanity").db == "data/scratch/x.db"


@pytest.mark.parametrize(
    ("argv", "attr", "expected"),
    [
        (("voice", "--novel", "lord-of-the-mysteries"), "out", "data/novels/LOTM/audio"),
        (("render", "--novel", "lord-of-the-mysteries"), "panel_dir", "data/novels/LOTM/panels"),
        (("render", "--novel", "lord-of-the-mysteries"), "motion_dir", "data/novels/LOTM/motion"),
        (("render", "--novel", "lord-of-the-mysteries"), "voice_dir", "data/novels/LOTM/audio"),
        (("render", "--novel", "lord-of-the-mysteries"), "out", "data/novels/LOTM/video"),
        (("persona", "reference", "--novel", "lord-of-the-mysteries"), "out", "data/novels/LOTM/references"),
        (("relevance", "--novel", "reverend-insanity"), "manifest", "data/novels/RI/panels/manifest.jsonl"),
    ],
)
def test_no_output_defaults_into_another_novels_folder(argv, attr, expected) -> None:
    assert getattr(_args(*argv), attr) == expected


def test_an_explicit_output_dir_is_kept() -> None:
    assert _args("voice", "--novel", "reverend-insanity", "--out", "data/scratch/audio").out == "data/scratch/audio"


def test_every_registered_canonical_database_is_under_data_db() -> None:
    registry = json.loads((REPO_ROOT / "data" / "canonical_dbs.json").read_text())
    assert registry["paths"]
    assert all(p.startswith("data/db/") and p.endswith(".db") for p in registry["paths"])


def test_the_characters_page_finds_voices_where_the_voice_stage_writes_them(tmp_path: Path) -> None:
    """It read `data/audio/<novel_id>/manifest.jsonl`, which nothing wrote, so every
    character showed "no voice yet"; manifests written before the 2026-09-27 move
    also carry old clip paths, which are re-anchored on the manifest's folder."""
    from echotales.pipeline.webview import _voice_assignments_from_manifest

    audio = paths.asset_dir("reverend-insanity", "audio", data_root=tmp_path)
    (audio / "ch1").mkdir(parents=True)
    (audio / "ch1" / "line.wav").write_bytes(b"RIFF")
    row = {"speaker_id": "t:self1", "speaker_label": "Fang Yuan", "voice": "p251",
           "audio_path": "data/RI/audio/ch1/line.wav"}
    (audio / "manifest.jsonl").write_text(json.dumps(row) + "\n")
    found = _voice_assignments_from_manifest("reverend-insanity", data_root=str(tmp_path))
    assert found["t:self1"]["voice"] == "p251"
    assert found["t:self1"]["sample_audio_path"] == str(audio / "ch1" / "line.wav")
