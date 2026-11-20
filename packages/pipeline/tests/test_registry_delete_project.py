"""`Registry.delete_project` removes a project's whole asset folder, nested folders included, and never follows a
symlink out of it. It used to `unlink()` every child, which raised on `reference_uploads/` after the database was
already gone, leaving a DB-less project with assets (security review)."""

from __future__ import annotations

from pathlib import Path

import pytest
from echotales.pipeline.webview_server import Registry


def _project(tmp_path: Path) -> tuple[Registry, Path, Path]:
    registry = Registry([], corrections_dir=tmp_path / "c", projects_dir=tmp_path / "projects")
    registry.create_project("p1", "P1", "novel")
    assets = registry.project_asset_dir("p1")
    (assets / "reference_uploads" / "deep").mkdir(parents=True)
    (assets / "source.epub").write_bytes(b"x")
    (assets / "reference_uploads" / "deep" / "a.png").write_bytes(b"y")
    return registry, assets, tmp_path / "projects" / "p1.db"


def test_delete_removes_nested_asset_folders_and_the_db(tmp_path: Path) -> None:
    registry, assets, db = _project(tmp_path)
    assert registry.delete_project("p1") is True
    assert not assets.exists() and not db.exists()
    assert "p1" not in registry.handles


def test_delete_does_not_follow_a_symlink_out_of_the_folder(tmp_path: Path) -> None:
    registry, assets, _ = _project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("precious")
    (assets / "reference_uploads" / "link").symlink_to(outside, target_is_directory=True)
    (assets / "filelink").symlink_to(outside / "keep.txt")
    assert registry.delete_project("p1") is True
    assert not assets.exists()
    assert (outside / "keep.txt").read_text() == "precious"


def test_a_failed_asset_removal_leaves_the_database_so_the_delete_can_be_retried(tmp_path: Path, monkeypatch) -> None:
    registry, assets, db = _project(tmp_path)

    def boom(*a, **k):
        raise OSError("disk says no")

    monkeypatch.setattr("echotales.pipeline.webview_server.shutil.rmtree", boom)
    with pytest.raises(OSError):
        registry.delete_project("p1")
    assert db.exists() and assets.exists()
