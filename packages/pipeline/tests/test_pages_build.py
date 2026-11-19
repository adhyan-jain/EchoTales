"""M1 step 4: a chapter's latest rendered panels become pages, through the CLI function and the `pages` job."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from echotales.core.enums import SpanType
from echotales.core.models import Chapter, Job, JobStatus, Span
from echotales.core.store import Store
from echotales.pipeline import jobs
from echotales.pipeline.pages.build import build_chapter_pages, panel_lettering
from echotales.pipeline.pages.lettering import LetterKind
from echotales.pipeline.render.direction import CharacterDirection, PanelDirection
from echotales.pipeline.render.plan import PanelPlan, PlanCastMember, append_panel_plan
from PIL import Image

NOVEL = "n"


def _span(block: int, i: int, kind: SpanType, text: str, speaker: str | None = None) -> Span:
    return Span(
        id=f"{NOVEL}:1:{block}:{i}", novel_id=NOVEL, chapter=1.0, block_index=block, start=i * 100,
        end=i * 100 + len(text), span_type=kind, text=text, speaker_self_id=speaker,
    )


def _plan(seq: int, blocks: list[int], slot: str = "scene", scene: int = 0, direction=None) -> PanelPlan:
    return PanelPlan(
        novel_id=NOVEL, chapter=1.0, panel_seq=seq, panel_id=f"{NOVEL}:1:{seq}", scene_index=scene, slot_kind=slot,
        lead_block=blocks[0], block_indexes=blocks, cast=[PlanCastMember(self_id="s1", label="Ann")],
        direction=direction, prompt="p", engine="stub", width=64, height=96, seed=0,
        image_path=f"p{seq}.png", cache_key="k", provenance="generated",
    )


SPANS = [
    _span(0, 0, SpanType.NARRATION_DESCRIPTION, "A grey morning."),
    _span(1, 0, SpanType.DIALOGUE, "“Get out!”", "s1"),
    _span(1, 1, SpanType.NARRATION_ACTION, "she shouted."),
    _span(2, 0, SpanType.DIALOGUE, "“No.”", "s1"),
    _span(2, 1, SpanType.NARRATION_ACTION, "he said calmly."),
    _span(3, 0, SpanType.INNER_MONOLOGUE, "Why now?", "s1"),
    _span(3, 1, SpanType.NARRATION_EXPOSITION, "Background lore."),
    _span(4, 0, SpanType.NARRATION_ACTION, "First."),
    _span(4, 1, SpanType.NARRATION_ACTION, "Second."),
]


def _store(tmp_path: Path) -> Store:
    s = Store(":memory:")
    s.add_novel(NOVEL, "The Novel", "x.epub", "generic")
    s.add_chapter(Chapter(novel_id=NOVEL, number=1.0, title="Opening", source_href="a", blocks=[]))
    s.add_spans(SPANS)
    return s


def _by_block(spans: list[Span]) -> dict[int, list[Span]]:
    out: dict[int, list[Span]] = {}
    for s in spans:
        out.setdefault(s.block_index, []).append(s)
    return out


def _render_panels(tmp_path: Path, version: str = "v1_x") -> Path:
    d = tmp_path / "panels" / "ch1" / version
    d.mkdir(parents=True)
    direction = PanelDirection(characters=[CharacterDirection(name="Ann", position="right")])
    plans = [
        _plan(1, [0], slot="establishing"),
        _plan(2, [1], direction=direction),
        _plan(3, [2, 3]),
        _plan(4, [4]),
    ]
    for p in plans:
        Image.new("RGB", (64, 96), (40 * p.panel_seq, 90, 140)).save(d / p.image_path)
        append_panel_plan(d / "panel_plan.jsonl", p)
    return d


def test_lettering_uses_span_types_speaker_position_and_the_speech_tag() -> None:
    plan = _plan(1, [1, 2, 3], direction=PanelDirection(characters=[CharacterDirection(name="Ann", position="right")]))
    items, facts, omitted = panel_lettering(plan, _by_block(SPANS))
    kinds = [i.kind for i in items]
    assert kinds == [LetterKind.SPEECH, LetterKind.SPEECH, LetterKind.THOUGHT]
    assert items[0].text == "Get out!" and items[0].shouted and not items[1].shouted
    assert items[0].speaker_position == "right"
    assert facts.dialogue_lines == 2 and facts.intensity == 3
    assert omitted == []


def test_extra_narration_is_reported_not_silently_dropped() -> None:
    items, _, omitted = panel_lettering(_plan(1, [4]), _by_block(SPANS))
    assert [i.text for i in items] == ["First."]
    assert [(o.kind, o.lost_text) for o in omitted] == [("omitted", "Second.")]


def test_chapter_builds_pages_in_a_versioned_directory(tmp_path: Path) -> None:
    _render_panels(tmp_path)
    store = _store(tmp_path)
    res = build_chapter_pages(
        store, NOVEL, 1.0, fmt="manga", exports=["png", "pdf", "cbz"],
        panel_dir=tmp_path / "panels", out_root=tmp_path / "pages",
    )
    assert res.out_dir == tmp_path / "pages" / "ch1" / "v1_manga"
    names = {f.name for f in res.files}
    assert {"0001.png", f"{NOVEL}_ch1.pdf", f"{NOVEL}_ch1.cbz", "pages.json"} <= names
    manifest = json.loads((res.out_dir / "pages.json").read_text())
    assert manifest["panels_version"] == "v1_x" and manifest["pages"] == res.page_count
    assert any(o["kind"] == "omitted" for o in manifest["overflow"])
    with zipfile.ZipFile(res.out_dir / f"{NOVEL}_ch1.cbz") as z:
        assert "ComicInfo.xml" in z.namelist()
    assert "v1_manga" in (tmp_path / "pages" / "ch1" / "VERSIONS.md").read_text()
    # A second run never overwrites the first.
    again = build_chapter_pages(
        store, NOVEL, 1.0, fmt="comic", exports=["png"], panel_dir=tmp_path / "panels", out_root=tmp_path / "pages"
    )
    assert again.out_dir.name == "v2_comic"


def test_reads_the_latest_panel_version(tmp_path: Path) -> None:
    _render_panels(tmp_path, "v1_old")
    _render_panels(tmp_path, "v2_new")
    res = build_chapter_pages(
        _store(tmp_path), NOVEL, 1.0, fmt="comic", exports=["png"],
        panel_dir=tmp_path / "panels", out_root=tmp_path / "pages",
    )
    assert res.panels_version == "v2_new"


def test_webtoon_pieces_are_exported(tmp_path: Path) -> None:
    _render_panels(tmp_path)
    res = build_chapter_pages(
        _store(tmp_path), NOVEL, 1.0, fmt="webtoon", exports=["png"],
        panel_dir=tmp_path / "panels", out_root=tmp_path / "pages",
    )
    assert res.page_count >= 1 and (res.out_dir / "0001.png").is_file()


def test_missing_render_is_refused_with_the_fix(tmp_path: Path) -> None:
    from echotales.pipeline.pages.build import build_pages
    from echotales.pipeline.render.anime import AnimeRefusal

    with pytest.raises(AnimeRefusal, match="render"):
        build_pages(_store(tmp_path), NOVEL, [1.0], fmt="manga", exports=["png"], panel_dir=tmp_path / "panels", out_root=tmp_path / "pages")


# --------------------------------------------------------------------------- the `pages` job kind


def _run_job(store: Store, params: dict) -> Job:
    job = Job(job_id=f"{NOVEL}:pages:1", novel_id=NOVEL, kind="pages", status=JobStatus.PENDING, created_at=1.0,
              params_json=json.dumps(params))
    store.add_job(job)
    jobs.run_job(store, job, params)
    return store.get_job(job.job_id)


def test_pages_is_a_job_kind() -> None:
    assert "pages" in jobs.JOB_KINDS


def test_pages_job_dispatches_and_writes_a_manifest_listing_the_files(tmp_path: Path, monkeypatch) -> None:
    _render_panels(tmp_path)
    monkeypatch.setattr("echotales.pipeline.paths.asset_dir", lambda novel_id, kind: tmp_path / kind)
    store = _store(tmp_path)
    job = _run_job(store, {"chapters": [1], "format": "comic", "export": ["png", "cbz"]})
    assert job.status == JobStatus.SUCCEEDED, job.error_summary
    manifest = json.loads((tmp_path / "pages" / "ch1" / "v1_comic" / "pages.json").read_text())
    assert f"{NOVEL}_ch1.cbz" in manifest["files"]


def test_pages_job_refuses_without_chapters_or_with_a_bad_format(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("echotales.pipeline.paths.asset_dir", lambda novel_id, kind: tmp_path / kind)
    store = _store(tmp_path)
    assert "chapters" in _run_job(store, {}).error_summary
    store2 = _store(tmp_path)
    bad = Job(job_id="n:pages:2", novel_id=NOVEL, kind="pages", created_at=1.0, params_json="{}")
    store2.add_job(bad)
    jobs.run_job(store2, bad, {"chapters": [1], "format": "scroll"})
    assert "format" in store2.get_job("n:pages:2").error_summary


def test_cli_pages_subcommand_writes_the_exports(tmp_path: Path, capsys) -> None:
    from echotales.pipeline.cli import main

    _render_panels(tmp_path)
    db = tmp_path / "t.db"
    s = Store(str(db))
    s.add_novel(NOVEL, "The Novel", "x.epub", "generic")
    s.add_chapter(Chapter(novel_id=NOVEL, number=1.0, title="Opening", source_href="a", blocks=[]))
    s.add_spans(SPANS)
    s.conn.commit()
    s.close()
    code = main(["--db", str(db), "pages", "--novel", NOVEL, "--chapters", "1", "--format", "comic",
                 "--export", "png,cbz", "--panel-dir", str(tmp_path / "panels"), "--out", str(tmp_path / "pages")])
    assert code == 0
    assert (tmp_path / "pages" / "ch1" / "v1_comic" / f"{NOVEL}_ch1.cbz").is_file()
    assert "pages" in capsys.readouterr().out
