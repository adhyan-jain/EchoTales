"""Core Pipeline Hardening #9.1: `resolve_novel` must mint the same
self_id for the same entity across two runs over identical upstream input.

Before this fix, `Resolver._create_entity` used an in-process counter
(`self1`, `self2`, ...), so re-resolving the same chapters could silently
permute which entity got which id -- any artifact that hard-coded a
self_id (gold sets, corrections logs) went stale without warning. See
`resolve/runner.py::_stable_entity_id`.
"""

from __future__ import annotations

import json

import pytest
from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
from echotales.core.models import Block, Chapter, Mention
from echotales.core.pipeline_run import PartialStageFailure
from echotales.core.store import Store
from echotales.pipeline.resolve import resolve_novel
from echotales.pipeline.resolve.runner import CanonicalRewipeBlocked, GlobalResolver


def _mention(mid: str, text: str, *, chapter: float, offset: int, group: str) -> Mention:
    return Mention(
        id=mid,
        novel_id="t",
        segment_id="s",
        chapter=chapter,
        offset=offset,
        text=text,
        alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=ReferenceMode.PRESENT,
        block_index=0,
        local_group_id=group,
        entity_label="character",
    )


def _store_with_two_chapters() -> Store:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    for n in (1.0, 2.0):
        store.add_chapter(
            Chapter(
                novel_id="t",
                number=n,
                title="T",
                source_href=f"{int(n)}.html",
                blocks=[Block(index=0, block_type=BlockType.PROSE, text="filler " * 10)],
            )
        )
    store.add_mentions(
        [
            _mention("m1", "Fang Yuan", chapter=1.0, offset=0, group="g1"),
            _mention("m2", "Wang Ju Chi", chapter=2.0, offset=5, group="g2"),
        ]
    )
    store.conn.commit()
    return store


def test_self_ids_are_identical_across_two_resolve_runs_on_identical_input():
    store = _store_with_two_chapters()

    resolve_novel("t", store)
    first_run = {s.canonical_label: s.id for s in store.all_selves("t")}
    assert len(first_run) == 2

    resolve_novel("t", store)  # rerun: resolve_novel wipes and rebuilds internally
    second_run = {s.canonical_label: s.id for s in store.all_selves("t")}

    assert first_run == second_run


def test_self_id_is_a_function_of_label_and_first_position_not_a_counter():
    """A third, independent entity introduced in a *different* chapter
    position must not perturb the ids already assigned to the first two --
    the direct behavioural difference from a counter, where insertion order
    (not content) determined every id."""
    store = _store_with_two_chapters()
    resolve_novel("t", store)
    baseline = {s.canonical_label: s.id for s in store.all_selves("t")}

    store.add_mentions(
        [_mention("m3", "Bai Ning Bing", chapter=2.0, offset=40, group="g3")]
    )
    store.conn.commit()
    resolve_novel("t", store)
    after = {s.canonical_label: s.id for s in store.all_selves("t")}

    assert after["Fang Yuan"] == baseline["Fang Yuan"]
    assert after["Wang Ju Chi"] == baseline["Wang Ju Chi"]
    assert "Bai Ning Bing" in after


def test_self_id_does_not_use_db_auto_increment_or_row_count():
    store = _store_with_two_chapters()
    resolve_novel("t", store)
    ids = [s.id for s in store.all_selves("t")]
    for self_id in ids:
        assert self_id.startswith("t:self:")
        # not a bare small integer counter suffix like ":self1"
        suffix = self_id.removeprefix("t:self:")
        assert not suffix.isdigit()


#: Deliberately distinct, multi-token names sharing no name component --
#: two mentions sharing a token (e.g. "Character 1"/"Character 2") make the
#: gate DEFER rather than immediately create a new entity (ambiguous:
#: could be the same person), which is correct resolver behaviour but
#: would make these tests about deferral timing rather than about
#: transaction/rollback safety.
_DISTINCT_NAMES = [
    "Fang Yuan",
    "Wang Ju Chi",
    "Bai Ning Bing",
    "Zhao Yuan De",
    "Han Tian Ming",
]


def _store_with_n_chapters(n: int) -> Store:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    mentions = []
    for c in range(1, n + 1):
        store.add_chapter(
            Chapter(
                novel_id="t",
                number=float(c),
                title="T",
                source_href=f"{c}.html",
                blocks=[Block(index=0, block_type=BlockType.PROSE, text="filler " * 10)],
            )
        )
        mentions.append(
            _mention(f"m{c}", _DISTINCT_NAMES[c - 1], chapter=float(c), offset=0, group=f"g{c}")
        )
    store.add_mentions(mentions)
    store.conn.commit()
    return store


class TestPerChunkTransactionSafety:
    """Core Pipeline Hardening #9.7: a mid-run failure must (a) preserve
    every already-committed chunk, (b) discard only the current,
    uncommitted chunk, and (c) surface which chapter it died on and how
    much survived -- not silently truncate."""

    def test_failure_preserves_prior_commits_and_rolls_back_current_chunk(self, monkeypatch):
        store = _store_with_n_chapters(5)
        real_resolve_group = GlobalResolver.resolve_group

        def boom_on_chapter_3(self, mentions, chapter_text, **kwargs):
            if mentions[0].chapter == 3.0:
                raise ValueError("simulated LLM/scoring failure")
            return real_resolve_group(self, mentions, chapter_text, **kwargs)

        monkeypatch.setattr(GlobalResolver, "resolve_group", boom_on_chapter_3)

        with pytest.raises(PartialStageFailure) as excinfo:
            resolve_novel("t", store, commit_every=2)

        assert "chapter 2" in excinfo.value.progress
        # Chapters 1-2 committed (commit_every=2) before chapter 3 failed --
        # those two entities must survive the rollback of chapter 3's
        # uncommitted, in-flight chunk.
        surviving_labels = {s.canonical_label for s in store.all_selves("t")}
        assert surviving_labels == {"Fang Yuan", "Wang Ju Chi"}

    def test_failure_before_any_commit_is_not_reported_as_partial(self, monkeypatch):
        store = _store_with_n_chapters(5)
        real_resolve_group = GlobalResolver.resolve_group

        def boom_on_chapter_1(self, mentions, chapter_text, **kwargs):
            if mentions[0].chapter == 1.0:
                raise ValueError("simulated failure before first commit")
            return real_resolve_group(self, mentions, chapter_text, **kwargs)

        monkeypatch.setattr(GlobalResolver, "resolve_group", boom_on_chapter_1)

        with pytest.raises(RuntimeError) as excinfo:
            resolve_novel("t", store, commit_every=2)

        assert not isinstance(excinfo.value, PartialStageFailure)
        assert store.all_selves("t") == []


class TestCanonicalRewipeGuard:
    """Core Pipeline Hardening #6: resolve_novel's startup wipe must refuse
    against a registered canonical DB with existing resolution state,
    unless force_rewipe=True."""

    def _canonical_store(self, tmp_path, monkeypatch):
        db_path = tmp_path / "webview-working" / "reverend-insanity.db"
        registry_path = tmp_path / "canonical_dbs.json"
        registry_path.write_text(json.dumps({"paths": [str(db_path)]}))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Store, "_CANONICAL_REGISTRY", registry_path)
        store = Store(str(db_path))
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(
            Chapter(
                novel_id="t",
                number=1.0,
                title="T",
                source_href="1.html",
                blocks=[Block(index=0, block_type=BlockType.PROSE, text="filler " * 10)],
            )
        )
        store.add_mentions([_mention("m1", "Fang Yuan", chapter=1.0, offset=0, group="g1")])
        store.conn.commit()
        return store

    def test_refuses_to_rewipe_canonical_db_with_existing_state(self, tmp_path, monkeypatch):
        store = self._canonical_store(tmp_path, monkeypatch)
        resolve_novel("t", store)  # first run: no existing state yet, allowed

        with pytest.raises(CanonicalRewipeBlocked):
            resolve_novel("t", store)  # second run: now has existing state

    def test_force_rewipe_overrides_the_guard(self, tmp_path, monkeypatch):
        store = self._canonical_store(tmp_path, monkeypatch)
        resolve_novel("t", store)

        # Must not raise.
        resolve_novel("t", store, force_rewipe=True)

    def test_scratch_db_is_never_blocked(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # no canonical_dbs.json here -- scratch
        store = _store_with_two_chapters()
        resolve_novel("t", store)
        resolve_novel("t", store)  # rerun on a non-canonical DB: always fine
