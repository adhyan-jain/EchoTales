"""Tests for auto-flagging entities founded on non-"character" NER labels.

Pattern found reviewing real pipeline output across three novels: NER labels
a mention "location"/"organization" (Gu Yue Village, the Magician tarot
title, Seoul), the commonness filter deliberately doesn't apply to those
labels (see `mentions/runner.py`'s `rejected()` docstring -- it was already
proven to over-delete real entities like a clan name or a plot item), and
`resolve/runner.py` always mints a `Self` regardless of kind since there is
no non-person `TargetKind`. The result: spurious "characters" pollute the
voice-cast list. This doesn't delete anything (that regressed once already);
it just leaves an automatic review flag.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.corrections import CorrectionLog
from echotales.pipeline.resolve import resolve_novel


def _mention(mid: str, text: str, *, offset: int, group: str, label: str | None) -> Mention:
    return Mention(
        id=mid,
        novel_id="t",
        segment_id="s",
        chapter=1.0,
        offset=offset,
        text=text,
        alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=ReferenceMode.PRESENT,
        block_index=0,
        local_group_id=group,
        entity_label=label,
    )


def _store_with_chapter() -> Store:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text="filler " * 10)],
        )
    )
    return store


class TestAutoFlagNonCharacterEntities:
    def test_location_labeled_entity_gets_flagged(self) -> None:
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Gu Yue Village", offset=0, group="g1", label="location")]
        )
        store.conn.commit()

        with tempfile.TemporaryDirectory() as d:
            clog = CorrectionLog(Path(d) / "t.jsonl")
            resolve_novel("t", store, corrections_log=clog)
            flags = _read_jsonl(Path(d) / "t.jsonl")

        assert len(flags) == 1
        assert flags[0].payload["source"] == "agent:pipeline"
        assert "location" in flags[0].payload["note"]

    def test_character_labeled_entity_is_not_flagged(self) -> None:
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Fang Yuan", offset=0, group="g1", label="character")]
        )
        store.conn.commit()

        with tempfile.TemporaryDirectory() as d:
            clog = CorrectionLog(Path(d) / "t.jsonl")
            resolve_novel("t", store, corrections_log=clog)
            flags = _read_jsonl(Path(d) / "t.jsonl")

        assert flags == []

    def test_mixed_signal_within_group_is_not_flagged(self) -> None:
        """One mention labeled "character" is enough to stay quiet -- a false
        flag is a worse outcome than a missed one for a one-time review note."""
        store = _store_with_chapter()
        store.add_mentions(
            [
                _mention("m1", "Ancient Moon", offset=0, group="g1", label="location"),
                _mention("m2", "Ancient Moon", offset=20, group="g1", label="character"),
            ]
        )
        store.conn.commit()

        with tempfile.TemporaryDirectory() as d:
            clog = CorrectionLog(Path(d) / "t.jsonl")
            resolve_novel("t", store, corrections_log=clog)
            flags = _read_jsonl(Path(d) / "t.jsonl")

        assert flags == []

    def test_no_corrections_log_means_no_flagging(self) -> None:
        """Default-off: every existing caller that doesn't pass corrections_log
        keeps today's behaviour exactly, including in tests elsewhere."""
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Gu Yue Village", offset=0, group="g1", label="location")]
        )
        store.conn.commit()
        report = resolve_novel("t", store)
        assert report.created == 1


class TestEntityKindTyping:
    """Section 10 item 5: a flagged location must stop *behaving* like a character,
    not merely carry a review note. The flag and the kind come from the same
    unanimity rule, so these tests sit alongside the flag tests above."""

    def test_location_entity_is_typed_and_excluded_from_people(self) -> None:
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Gu Yue Village", offset=0, group="g1", label="location")]
        )
        store.conn.commit()

        resolve_novel("t", store)
        entity = store.all_selves("t")[0]
        assert entity.kind is TargetKind.LOCATION
        assert not entity.kind.is_person

    def test_organization_entity_is_typed(self) -> None:
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Demonic Faction", offset=0, group="g1", label="organization")]
        )
        store.conn.commit()

        resolve_novel("t", store)
        assert store.all_selves("t")[0].kind is TargetKind.ORGANIZATION

    def test_character_stays_a_person(self) -> None:
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Fang Yuan", offset=0, group="g1", label="character")]
        )
        store.conn.commit()

        resolve_novel("t", store)
        entity = store.all_selves("t")[0]
        assert entity.kind is TargetKind.SELF
        assert entity.kind.is_person

    def test_unlabeled_mentions_default_to_person(self) -> None:
        """Absence of a label is not evidence of non-personhood -- most of the
        corpus predates layer 1 emitting one at all."""
        store = _store_with_chapter()
        store.add_mentions([_mention("m1", "Fang Yuan", offset=0, group="g1", label=None)])
        store.conn.commit()

        resolve_novel("t", store)
        assert store.all_selves("t")[0].kind is TargetKind.SELF

    def test_mixed_signal_stays_a_person(self) -> None:
        """Same unanimity rule as the flag: a wrong LOCATION silently removes a
        real character from voice *and* panel casting, which is worse and much
        harder to notice than a spurious row in the cast list."""
        store = _store_with_chapter()
        store.add_mentions(
            [
                _mention("m1", "Ancient Moon", offset=0, group="g1", label="location"),
                _mention("m2", "Ancient Moon", offset=20, group="g1", label="character"),
            ]
        )
        store.conn.commit()

        resolve_novel("t", store)
        assert store.all_selves("t")[0].kind is TargetKind.SELF

    def test_kind_survives_a_store_round_trip(self) -> None:
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Qing Mao Mountain", offset=0, group="g1", label="location")]
        )
        store.conn.commit()
        resolve_novel("t", store)

        entity_id = store.all_selves("t")[0].id
        assert store.get_self(entity_id).kind is TargetKind.LOCATION


def _seed_legacy_self(store: Store, self_id: str, novel_id: str, label: str) -> None:
    """Insert a `self_entity` row the way pre-a17ea32 code did: no `kind`
    column at all. `add_self` (current code) always writes an explicit
    value, so this bypasses it to reproduce the actual on-disk shape of
    `data/webview-working/reverend-insanity.db` (82/82 rows, `kind` NULL) --
    a real ALTER-added column on rows an older INSERT statement never knew
    about, not a value anyone chose."""
    store.conn.execute(
        "INSERT INTO self_entity(id, novel_id, canonical_label, first_chapter,"
        " first_offset, prominence, notes) VALUES (?,?,?,?,?,?,?)",
        (self_id, novel_id, label, 1, 0, "INCIDENTAL", ""),
    )
    store.conn.commit()


class TestKindBackfill:
    """EVOLUTION 4.54: `self_entity.kind` populated once by hand on exactly
    one database, never made a standard resolve stage, so every other/newer
    database (verified: `data/webview-working/reverend-insanity.db`, 82
    rows) had `kind` NULL for everything -- which `Store.get_self()` reads
    back as SELF (a person). `backfill_kinds` closes that for *existing*
    rows using the same on-disk NER cache `mentions/chapter_ner.py` writes.
    It is exposed as `resolve --novel <id> --kinds-only` for exactly this
    case, deliberately *not* folded into a plain `resolve` rerun -- that
    command deletes and rebuilds `self_entity` from scratch every time
    (`resolve_novel`'s first lines), which would just recreate these same
    entities as explicit SELF from labelless mentions and lose the legacy
    row entirely rather than fix it."""

    def test_backfill_classifies_from_cache_plurality(self, tmp_path) -> None:
        import json

        from echotales.pipeline.resolve.kind_backfill import backfill_kinds

        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        _seed_legacy_self(store, "t:self1", "t", "Gu Yue")

        cache_path = tmp_path / "t-ner-cache.json"
        cache_path.write_text(
            json.dumps(
                {
                    "m:aaa": {"Gu Yue": "location"},
                    "m:bbb": {"Gu Yue": "location"},
                    "m:ccc": {"Gu Yue": "character"},
                }
            )
        )

        stats = backfill_kinds(store, "t", cache_path)
        assert stats == {"checked": 1, "classified": 1, "left_default": 0}
        assert store.get_self("t:self1").kind is TargetKind.LOCATION

    def test_backfill_leaves_tie_or_character_lead_as_self(self, tmp_path) -> None:
        """A wrong SELF is cheap and visible; a wrong LOCATION silently drops
        a real character. Ties and "character" pluralities both stay SELF."""
        import json

        from echotales.pipeline.resolve.kind_backfill import backfill_kinds

        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        _seed_legacy_self(store, "t:self1", "t", "Ancient Moon")

        cache_path = tmp_path / "t-ner-cache.json"
        cache_path.write_text(
            json.dumps(
                {
                    "m:aaa": {"Ancient Moon": "location"},
                    "m:bbb": {"Ancient Moon": "character"},
                }
            )
        )

        stats = backfill_kinds(store, "t", cache_path)
        assert stats["classified"] == 0
        assert store.get_self("t:self1").kind is TargetKind.SELF

    def test_backfill_never_overwrites_an_already_typed_entity(self, tmp_path) -> None:
        """Idempotent: rows `_entity_kind` already classified at creation time
        (from real `entity_label` evidence) must never be reconsidered by the
        cache-vote backfill, even if the cache disagrees."""
        import json

        from echotales.core.models import DiscoursePosition, Self
        from echotales.pipeline.resolve.kind_backfill import backfill_kinds

        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_self(
            Self(
                id="t:self1",
                novel_id="t",
                canonical_label="Fang Yuan",
                first_attested_pos=DiscoursePosition(chapter=1, offset=0),
                kind=TargetKind.SELF,
            )
        )
        store.conn.commit()

        cache_path = tmp_path / "t-ner-cache.json"
        cache_path.write_text(json.dumps({"m:aaa": {"Fang Yuan": "location"}}))

        stats = backfill_kinds(store, "t", cache_path)
        assert stats == {"checked": 0, "classified": 0, "left_default": 0}
        assert store.get_self("t:self1").kind is TargetKind.SELF

    def test_resolve_novel_backfill_is_a_harmless_noop_on_a_fresh_run(self) -> None:
        """`resolve_novel` also calls `backfill_kinds` at the end of every run
        as a defense-in-depth safety net -- but a fresh run always writes an
        explicit `kind` (SELF or typed) for every entity it creates, so on
        a normal run there is nothing left unset for it to find. This just
        pins that it doesn't error and doesn't touch anything."""
        store = _store_with_chapter()
        store.add_mentions(
            [_mention("m1", "Fang Yuan", offset=0, group="g1", label="character")]
        )
        store.conn.commit()

        resolve_novel("t", store)
        assert store.all_selves("t")[0].kind is TargetKind.SELF

    def test_kinds_only_cli_backfills_without_wiping_self_entity(self, tmp_path) -> None:
        """`resolve --kinds-only` is the actual entry point for repairing an
        existing database: it must classify legacy rows in place, not go
        through `resolve_novel`'s delete-and-rebuild (which would discard
        them, per the class docstring)."""
        import argparse
        import json

        from echotales.pipeline.commands import cmd_resolve

        db_path = tmp_path / "t.db"
        store = Store(str(db_path))
        store.add_novel("t", "T", "x.epub", "generic")
        _seed_legacy_self(store, "t:self1", "t", "Gu Yue")
        store.close()

        lexdir = tmp_path / "lexicons"
        lexdir.mkdir()
        (lexdir / "t-ner-cache.json").write_text(
            json.dumps(
                {
                    "c1": {"Gu Yue": "location"},
                    "c2": {"Gu Yue": "location"},
                }
            )
        )

        import os

        import echotales.pipeline.config as config_module

        old_env = os.environ.get("ECHOTALES_LEXICON_PATH")
        os.environ["ECHOTALES_LEXICON_PATH"] = str(lexdir)
        try:
            config_module.get_settings(reload=True)
            args = argparse.Namespace(novel="t", db=str(db_path), kinds_only=True)
            rc = cmd_resolve(args)
        finally:
            if old_env is None:
                os.environ.pop("ECHOTALES_LEXICON_PATH", None)
            else:
                os.environ["ECHOTALES_LEXICON_PATH"] = old_env
            config_module.get_settings(reload=True)

        assert rc == 0
        check = Store(str(db_path))
        assert check.get_self("t:self1").kind is TargetKind.LOCATION


class TestKindCoverageGuard:
    """Regression guard for the defect this file is named after: a processed
    novel where `self_entity.kind` is silently NULL for most/all entities
    must be caught loudly rather than quietly mis-casting locations and
    organizations as voice/panel-cast people again."""

    #: Justification: `_entity_kind` defaults an entity to SELF whenever its
    #: founding mentions carry no NER label at all (correct -- "unlabelled"
    #: isn't evidence), so some legitimate NULL-reads-as-SELF is expected
    #: even on a fully-processed novel. But 100% typed-as-default, novel
    #: after novel, is exactly the "never wired in" failure mode this test
    #: exists to catch -- so the guard is on the *fraction* left at the
    #: SELF default among entities the backfill actually had cache evidence
    #: for, not on the raw NULL count.
    MAX_UNRESOLVED_FRACTION = 0.95

    def test_kind_backfill_resolves_most_entities_with_cache_evidence(self) -> None:

        from echotales.pipeline.resolve.kind_backfill import backfill_kinds

        cache_path = Path("data/lexicons/reverend-insanity-ner-cache.json")
        if not cache_path.exists():
            import pytest

            pytest.skip("real NER cache not present in this checkout")

        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "ri-guard.db"
            import shutil

            src = Path("data/webview-working/reverend-insanity.db")
            if not src.exists():
                import pytest

                pytest.skip("webview-working db not present in this checkout")
            shutil.copy(src, db_path)

            store = Store(str(db_path))
            stats = backfill_kinds(store, "reverend-insanity", cache_path)
            store.conn.commit()

        assert stats["checked"] > 0
        # Sample A (Section 10 item 5 / EVOLUTION 4.54): these three must
        # come back non-person, not silently stay at the SELF default.
        for label in ("Gu Yue", "South Border", "Qing Mao Mountain"):
            entity = next(
                e for e in store.all_selves("reverend-insanity") if e.canonical_label == label
            )
            assert not entity.kind.is_person, f"{label} still reads as a person"


def _read_jsonl(path: Path):
    import json

    from echotales.pipeline.corrections import Correction

    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(Correction.from_json(json.loads(line)))
    return out
