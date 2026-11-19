"""The two doors into packs besides the library: `echotales pack export|import` and the `pack_export` / `pack_import`
job kinds. Each runs from a temporary working directory because `paths.DATA_ROOT` is relative."""

from __future__ import annotations

import json

import pytest
from echotales.core.models import Job, JobStatus
from echotales.pipeline import jobs
from echotales.pipeline.cli import main
from test_reader_cast import _book


@pytest.fixture()
def cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_kinds_are_registered() -> None:
    assert {"pack_export", "pack_import"} <= set(jobs.JOB_KINDS)


def test_the_cli_exports_then_imports(cwd, capsys) -> None:
    src = _book(cwd, 3, "src")
    assert main(["--db", src.path, "pack", "export", "--novel", "t", "--corrections", str(cwd / "c.jsonl")]) == 0
    pack = cwd / "data" / "novels" / "t" / "packs" / "t.etpack"
    assert pack.is_file() and "packs/t.etpack" in capsys.readouterr().out

    dst = _book(cwd, 3, "dst")
    assert main(["--db", dst.path, "pack", "import", "--novel", "t", str(pack), "--corrections", str(cwd / "d.jsonl")]) == 0
    assert "applied" in capsys.readouterr().out


def test_the_cli_refuses_a_file_that_is_not_a_pack(cwd, capsys) -> None:
    bad = cwd / "bad.etpack"
    bad.write_bytes(b"nope")
    dst = _book(cwd, 3, "dst")
    assert main(["--db", dst.path, "pack", "import", "--novel", "t", str(bad)]) == 2
    assert "refusing" in capsys.readouterr().err


def _run(store, kind: str, params: dict) -> Job:
    job = Job(job_id=f"t:{kind}:1", novel_id="t", kind=kind, status=JobStatus.PENDING, created_at=1.0,
              params_json=json.dumps(params))
    store.add_job(job)
    jobs.run_job(store, job, params)
    return store.get_job(job.job_id)


def test_pack_export_and_import_run_as_jobs(cwd) -> None:
    src = _book(cwd, 3, "src")
    done = _run(src, "pack_export", {"name": "my-pack"})
    assert done.status == JobStatus.SUCCEEDED, done.error_summary
    assert (cwd / "data" / "novels" / "t" / "packs" / "my-pack.etpack").is_file()

    done = _run(_book(cwd, 3, "dst"), "pack_import", {"name": "my-pack"})
    assert done.status == JobStatus.SUCCEEDED, done.error_summary


def test_a_pack_name_cannot_escape_the_packs_folder(cwd) -> None:
    done = _run(_book(cwd, 3, "src"), "pack_export", {"name": "../../evil"})
    assert done.status == JobStatus.SUCCEEDED
    assert (cwd / "data" / "novels" / "t" / "packs" / "evil.etpack").is_file()
    assert not (cwd / "evil.etpack").exists()


def test_importing_a_pack_that_is_not_there_fails_with_the_name(cwd) -> None:
    done = _run(_book(cwd, 3, "dst"), "pack_import", {"name": "missing"})
    assert done.status == JobStatus.FAILED and "missing.etpack" in done.error_summary
