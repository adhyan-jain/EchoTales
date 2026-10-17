"""A render queued from the Studio (`jobs.py` render job) gets its own version directory, like `echotales render`.

It used to write into the root of `panels/ch<N>/`: on 2026-10-18 a stub render from the Studio put 33 placeholder
panels next to LotM's real v1 render and replaced the only manifest that render had.
"""

from __future__ import annotations

import json

from echotales.core.models import Job
from echotales.pipeline.jobs import run_job
from test_render_runner import _seeded_store


def test_a_studio_render_lands_in_a_new_named_version_and_is_recorded(tmp_path) -> None:
    store = _seeded_store(tmp_path)
    panels = tmp_path / "panels"
    (panels / "ch1" / "v1").mkdir(parents=True)  # an earlier real render
    # The third job repeats the second exactly, which `run_stage` skips by design: no third version.
    for n, seed in ((1, 1), (2, 2), (3, 2)):
        params = {"engine": "stub", "chapters": [1.0], "panel_dir": str(panels), "seed": seed}
        job = Job(job_id=f"t:render:{n}", novel_id="t", kind="render", created_at=0.0, params_json=json.dumps(params))
        store.add_job(job)
        run_job(store, job, params)
        assert store.get_job(job.job_id).status.value == "SUCCEEDED", store.get_job(job.job_id).error_summary

    chapter = panels / "ch1"
    assert sorted(p.name for p in chapter.iterdir() if p.is_dir()) == ["v1", "v2_stub-studio", "v3_stub-studio"]
    assert not list(chapter.glob("*.png"))  # nothing written beside the versions
    assert list((chapter / "v2_stub-studio").glob("*.png"))
    log = (chapter / "VERSIONS.md").read_text()
    assert "## v2_stub-studio" in log and "## v3_stub-studio" in log and "not a real render" in log
