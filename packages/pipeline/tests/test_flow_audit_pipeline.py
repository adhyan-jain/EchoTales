"""Auditor checks for the mentions, speakers and resolve stages: each passes on a tiny consistent database and fails,
naming the chapter and quoting the text, on a deliberately corrupted one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from echotales.core.enums import AttributionMethod, BlockType
from echotales.core.models import Block, Chapter, DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline import flow
from echotales.pipeline.flow import Stage, Status
from echotales.pipeline.spans import classify_chapter

NOVEL = "t"
TEXT = "“Hello there,” said Alice Smith. Bob Jones nodded slowly in the doorway."
FILLER = "The corridor was long and quiet and nobody walked along it for a good while that evening. " * 20


def _ins_mention(store: Store, mid: str, chapter: float, block: int, offset: int, text: str, target: str | None,
                 alias: str = "RIGID_NAME", group: str | None = None) -> None:
    store.conn.execute(
        "INSERT INTO mention (id, novel_id, segment_id, chapter, offset, text, alias_type, span_type, reference_mode,"
        " target_kind, target_id, local_group_id, confidence, method, provenance, block_index)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (mid, NOVEL, "s", chapter, offset, text, alias, "NARRATION_ACTION", "PRESENT",
         "SELF" if target else None, target, group, 0.9, "SCORED" if target else None, "MACHINE", block),
    )


@pytest.fixture
def db(tmp_path: Path):
    store = Store(tmp_path / "t.db")
    store.add_novel(NOVEL, "T", "x", "generic")
    for n in (1.0, 2.0):
        store.add_chapter(Chapter(novel_id=NOVEL, number=n, title=f"C{n:g}", source_href="x",
                                  blocks=[Block(index=0, block_type=BlockType.PROSE, text=TEXT),
                                          Block(index=1, block_type=BlockType.PROSE, text=FILLER)]))
        spans = classify_chapter(store.get_chapter(NOVEL, n))  # type: ignore[arg-type]
        for s in spans:
            if s.span_type.value == "DIALOGUE":
                s.speaker_self_id, s.attribution_method, s.confidence = f"{NOVEL}:self1", AttributionMethod.EXPLICIT, 0.95
        store.add_spans(spans)
        a, b = TEXT.index("Alice Smith"), TEXT.index("Bob Jones")
        _ins_mention(store, f"m{n:g}a", n, 0, a, "Alice Smith", f"{NOVEL}:self1")
        _ins_mention(store, f"m{n:g}b", n, 0, b, "Bob Jones", f"{NOVEL}:self2")
    for i, label in ((1, "Alice Smith"), (2, "Bob Jones")):
        store.add_self(Self(id=f"{NOVEL}:self{i}", novel_id=NOVEL, canonical_label=label,
                            first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    store.conn.commit()
    yield store
    store.close()


def run(store: Store, check_id: str) -> flow.CheckResult:
    stage = next(s for s in Stage if any(c.check_id == check_id for c in flow.CHECKS[s]))
    return flow._find(stage, check_id).fn(store, NOVEL, None)


ALL = [c.check_id for s in (Stage.MENTIONS, Stage.SPEAKERS, Stage.RESOLVE) for c in flow.CHECKS[s]]


def test_consistent_database_passes_every_new_check(db: Store) -> None:
    bad = {c: (r.status, [s.render() for s in r.shortfalls]) for c in ALL
           if (r := run(db, c)).status is Status.FAIL}
    assert not bad
    assert run(db, "resolve.corrections_present").status is Status.SKIPPED
    assert run(db, "mentions.ner_coverage").status is Status.SKIPPED


def test_empty_stages_are_skipped_not_passed(tmp_path: Path) -> None:
    store = Store(tmp_path / "e.db")
    store.add_novel(NOVEL, "T", "x", "generic")
    for c in ALL:
        assert run(store, c).status is Status.SKIPPED, c


def test_offsets_report_the_size_of_the_shift(db: Store) -> None:
    db.conn.execute("UPDATE mention SET offset=offset+1 WHERE id='m1a'")
    r = run(db, "mentions.offsets")
    assert r.status is Status.FAIL and r.total_shortfalls == 1
    assert "chapter 1" in r.shortfalls[0].render()
    assert "-1 characters" in r.shortfalls[0].detail
    db.conn.execute("UPDATE mention SET offset=9999 WHERE id='m2b'")
    assert run(db, "mentions.offsets").total_shortfalls == 2


def test_overlapping_mentions_fail(db: Store) -> None:
    _ins_mention(db, "m1c", 1.0, 0, TEXT.index("Alice") + 2, "ice Smith", None)
    r = run(db, "mentions.no_overlap")
    assert r.status is Status.FAIL and "overlaps" in r.shortfalls[0].detail


def test_chapter_without_mentions_fails_when_long(db: Store) -> None:
    db.conn.execute("DELETE FROM mention WHERE chapter=2")
    r = run(db, "mentions.chapter_coverage")
    assert r.status is Status.FAIL and r.shortfalls[0].chapter == 2.0


def test_uncovered_name_is_a_warning_with_counts(db: Store) -> None:
    db.add_chapter(Chapter(novel_id=NOVEL, number=3.0, title="C3", source_href="x",
                           blocks=[Block(index=0, block_type=BlockType.PROSE, text="Then Carol Dunn left. Carol Dunn wept.")]))
    db.conn.commit()
    r = run(db, "mentions.name_coverage")
    assert r.status is Status.PASS
    assert any("2x 'Carol Dunn'" in w for w in r.warnings)


def test_ner_tier_that_skipped_a_chapter_fails(db: Store, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from echotales.pipeline.config import get_settings

    monkeypatch.setattr(get_settings(), "lexicon_path", tmp_path)
    from echotales.pipeline.mentions.chapter_ner import CHUNK_CHARS, chunk_text
    from echotales.pipeline.mentions.ner import _windows

    need = sum(len(_windows(c)) for c in chunk_text(db.get_chapter(NOVEL, 1).story_text, CHUNK_CHARS))  # type: ignore[union-attr]
    for _ in range(need):
        db.log_llm_call(stage="ner", tier="local", model="m", escalated=False, prompt_tokens=1, completion_tokens=1,
                        latency_ms=1, ok=True, novel_id=NOVEL, chapter=1.0)
    db.conn.commit()
    r = run(db, "mentions.ner_coverage")
    assert r.status is Status.FAIL and r.total_shortfalls == 1 and r.shortfalls[0].chapter == 2.0


def test_speaker_end_states(db: Store) -> None:
    db.conn.execute("UPDATE span SET speaker_self_id='t:self99' WHERE chapter=1 AND span_type='DIALOGUE'")
    db.conn.execute("UPDATE span SET speaker_self_id='Zed Nobody' WHERE chapter=2 AND span_type='DIALOGUE'")
    r = run(db, "speakers.dialogue_end_state")
    assert r.status is Status.FAIL and r.total_shortfalls == 2
    details = " ".join(s.detail for s in r.shortfalls)
    assert "points at no entity" in details and "matches no entity label or mention text" in details
    v = run(db, "speakers.queue_visibility")
    assert v.status is Status.FAIL and "never shows it" in v.shortfalls[0].detail


def test_name_string_speaker_is_a_counted_documented_state(db: Store) -> None:
    db.conn.execute("UPDATE span SET speaker_self_id='Alice' WHERE span_type='DIALOGUE'")
    r = run(db, "speakers.dialogue_end_state")
    assert r.status is Status.PASS and r.stats["speaker_kinds"]["surface"] == 2


def test_method_without_speaker_and_narration_speaker_fail(db: Store) -> None:
    db.conn.execute("UPDATE span SET speaker_self_id=NULL WHERE chapter=1 AND span_type='DIALOGUE'")
    assert "claims an attribution" in run(db, "speakers.dialogue_end_state").shortfalls[0].detail
    db.conn.execute("UPDATE span SET speaker_self_id='t:self1' WHERE span_type='NARRATION_ACTION' AND chapter=2")
    r = run(db, "speakers.narration_has_no_speaker")
    assert r.status is Status.FAIL and r.shortfalls[0].chapter == 2.0


def test_method_vocabulary(db: Store) -> None:
    db.conn.execute("UPDATE span SET attribution_method='GUESSWORK' WHERE chapter=1 AND span_type='DIALOGUE'")
    db.conn.execute("UPDATE span SET attribution_method='HUMAN', confidence=0.5 WHERE chapter=2 AND span_type='DIALOGUE'")
    r = run(db, "speakers.method_vocabulary")
    assert r.status is Status.FAIL and r.total_shortfalls == 2
    assert r.stats["methods"]["GUESSWORK"] == 1


def test_unresolved_dialogue_is_visible_to_the_queue(db: Store) -> None:
    db.conn.execute("UPDATE span SET speaker_self_id=NULL, attribution_method='UNRESOLVED', confidence=0.0"
                    " WHERE span_type='DIALOGUE'")
    r = run(db, "speakers.queue_visibility")
    assert r.status is Status.PASS and r.stats["queue_reasons"]["unnamed"] == 2


def test_deferred_naming_group_is_counted_unrecorded(db: Store) -> None:
    db.conn.execute("UPDATE mention SET target_id=NULL, target_kind=NULL, method=NULL WHERE id='m1b'")
    r = run(db, "resolve.mention_outcome")
    assert r.status is Status.FAIL and r.shortfalls[0].chapter == 1.0
    assert "Bob Jones" in r.shortfalls[0].excerpt and r.stats["deferred_groups_unrecorded"] == 1
    db.conn.execute("UPDATE mention SET alias_type='RELATIONAL_DEICTIC' WHERE id='m1b'")
    assert run(db, "resolve.mention_outcome").status is Status.PASS


def test_orphans_and_dangling_targets(db: Store) -> None:
    db.conn.execute("UPDATE mention SET target_id='t:gone' WHERE id='m1a'")
    db.conn.execute("UPDATE mention SET target_id='t:self2' WHERE id='m2a'")
    r = run(db, "resolve.no_orphans")
    assert r.status is Status.FAIL
    text = " ".join(s.detail for s in r.shortfalls)
    assert "'t:gone' does not exist" in text and "no mention and no alias binding" in text


def _alias(db: Store, **over: object) -> None:
    row = dict(novel_id=NOVEL, alias="Al", alias_norm="al", alias_type="RIGID_NAME", target_kind="SELF",
               target_id="t:self1", timeline_id="main", story_from_lb=0, story_from_ub=1, story_to_lb=5,
               story_to_ub=float("inf"), learned_chapter=2, learned_offset=0, observer_id="READER",
               asserted_by="NARRATOR", truth_status="TRUE", retracted_chapter=None, retracted_offset=None)
    row.update(over)
    db.conn.execute(f"INSERT INTO alias_binding ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))


def test_bindings(db: Store) -> None:
    _alias(db)
    assert run(db, "resolve.bindings").status is Status.PASS
    _alias(db, target_id="t:missing")
    _alias(db, story_from_lb=9, story_from_ub=1)
    _alias(db, retracted_chapter=1, retracted_offset=0, truth_status="TRUE")
    r = run(db, "resolve.bindings")
    assert r.status is Status.FAIL
    text = " ".join(s.detail for s in r.shortfalls)
    for part in ("does not exist", "malformed interval", "truth_status is TRUE", "before it was learned"):
        assert part in text


def test_applied_corrections_must_still_be_present(db: Store, tmp_path: Path) -> None:
    manual = f"{NOVEL}:manual:c1"
    db.add_self(Self(id=manual, novel_id=NOVEL, canonical_label="Eve", first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    span_id = db.conn.execute("SELECT id FROM span WHERE span_type='DIALOGUE' AND chapter=1").fetchone()[0]
    db.conn.execute("UPDATE span SET speaker_self_id=?, attribution_method='HUMAN', confidence=1.0 WHERE id=?", (manual, span_id))
    log = tmp_path / "c.jsonl"
    log.write_text(json.dumps({"id": "c1", "novel_id": NOVEL, "type": "reassign_speaker", "applied": True,
                               "payload": {"span_id": span_id, "chapter": 1, "new_label": "Eve"}}) + "\n")
    token = flow._corrections_path.set(str(log))
    try:
        assert run(db, "resolve.corrections_present").status is Status.PASS
        db.conn.execute("DELETE FROM self_entity WHERE id=?", (manual,))
        r = run(db, "resolve.corrections_present")
    finally:
        flow._corrections_path.reset(token)
    assert r.status is Status.FAIL and "is gone" in r.shortfalls[0].detail


def test_entity_profile_reports_stats_and_split_hints(db: Store) -> None:
    db.add_self(Self(id="t:self3", novel_id=NOVEL, canonical_label="Mr. Alice Smith",
                     first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    for i in range(3):
        _ins_mention(db, f"x{i}", 2.0, 1, i * 10, "Mr. Alice Smith", "t:self3")
        _ins_mention(db, f"y{i}", 2.0, 1, 100 + i * 10, "Alice Smith", "t:self1")
    r = run(db, "resolve.entity_profile")
    assert r.status is Status.PASS and r.stats["entities"] == 3
    assert r.stats["top_entities"][0]["mentions"] >= 3
    assert any("possible split" in w for w in r.warnings)


def test_cli_accepts_the_new_stages(db: Store, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from echotales.pipeline import cli

    db.close()
    code = cli.main(["--db", str(tmp_path / "t.db"), "audit", "--novel", NOVEL, "--stage", "resolve", "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert code in (0, 1) and doc["stages"] == ["resolve"]
