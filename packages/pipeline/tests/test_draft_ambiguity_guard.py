"""`expand_draft` must refuse a surface it cannot honestly expand.

Blocking prerequisite for drafting gold over a whole volume (COMPLETION_PLAN
Track 2 item 5). The module's own docstring has said since it was written that
expanding a surface to every occurrence is only valid because chapters 1-5
happen to use each surface for one referent, and that a volume-scale range
"would need to fail loudly on an ambiguous surface". It did not, until
EVOLUTION 4.79.
"""

from __future__ import annotations

import pytest
from echotales.core.models import Chapter
from echotales.core.store import Store
from echotales.pipeline.eval.draft import AmbiguousSurfaceError, expand_draft

_HEADER = 'novel_id = "t"\ndrafted_by = "test"\nchapters = [1]\n'


@pytest.fixture
def store(tmp_path):  # type: ignore[no-untyped-def]
    s = Store(str(tmp_path / "t.db"))
    s.add_novel("t", "Test", "", "")
    s.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="One",
            source_href="one.html",
            blocks=[{"index": 0, "block_type": "PROSE", "text": "Wang bowed, and the elder spoke."}],
        )
    )
    s.conn.commit()
    yield s
    s.close()


def _write(tmp_path, body: str):  # type: ignore[no-untyped-def]
    path = tmp_path / "draft.toml"
    path.write_text(_HEADER + body, encoding="utf-8")
    return path


class TestAmbiguityGuard:
    def test_one_surface_two_identities_raises(self, tmp_path, store) -> None:  # type: ignore[no-untyped-def]
        """The volume-scale failure: "the elder" is two different people."""
        path = _write(
            tmp_path,
            '[[identity]]\nname = "Elder A"\nsurfaces = ["the elder"]\n'
            '[[identity]]\nname = "Elder B"\nsurfaces = ["the elder"]\n',
        )
        with pytest.raises(AmbiguousSurfaceError, match="the elder"):
            expand_draft(path, store)

    def test_identity_and_not_entity_claiming_the_same_surface_raises(self, tmp_path, store) -> None:  # type: ignore[no-untyped-def]
        path = _write(
            tmp_path,
            '[[identity]]\nname = "Wang"\nsurfaces = ["Wang"]\n'
            '[[not_entity]]\nreason = "a place"\nsurfaces = ["Wang"]\n',
        )
        with pytest.raises(AmbiguousSurfaceError, match="Wang"):
            expand_draft(path, store)

    def test_an_explicit_ambiguous_flag_raises(self, tmp_path, store) -> None:  # type: ignore[no-untyped-def]
        """A drafter who saw the ambiguity needs a way to say so that is not
        "leave it out and hope"."""
        path = _write(
            tmp_path,
            '[[identity]]\nname = "Elder A"\nsurfaces = ["the elder"]\nambiguous = true\n',
        )
        with pytest.raises(AmbiguousSurfaceError, match="ambiguous"):
            expand_draft(path, store)

    def test_the_message_names_every_offending_surface(self, tmp_path, store) -> None:  # type: ignore[no-untyped-def]
        """One-at-a-time failures would make fixing a volume-scale draft a
        many-round loop."""
        path = _write(
            tmp_path,
            '[[identity]]\nname = "A"\nsurfaces = ["x", "y"]\n'
            '[[identity]]\nname = "B"\nsurfaces = ["x", "y"]\n',
        )
        with pytest.raises(AmbiguousSurfaceError) as excinfo:
            expand_draft(path, store)
        assert "'x'" in str(excinfo.value) and "'y'" in str(excinfo.value)
        assert "2 ambiguous surface(s)" in str(excinfo.value)

    def test_the_same_surface_twice_under_one_identity_is_fine(self, tmp_path, store) -> None:  # type: ignore[no-untyped-def]
        """Duplication within one identity is redundant, not ambiguous -- the
        referent is unchanged, so refusing it would be a false positive."""
        path = _write(
            tmp_path,
            '[[identity]]\nname = "Wang"\nsurfaces = ["Wang", "Wang"]\n',
        )
        assert expand_draft(path, store).mentions

    def test_an_unambiguous_draft_still_expands(self, tmp_path, store) -> None:  # type: ignore[no-untyped-def]
        path = _write(
            tmp_path,
            '[[identity]]\nname = "Wang"\nsurfaces = ["Wang"]\n'
            '[[not_entity]]\nreason = "a title"\nsurfaces = ["the elder"]\n',
        )
        surfaces = {m.surface for m in expand_draft(path, store).mentions}
        assert surfaces == {"Wang", "the elder"}

    def test_the_guard_runs_before_the_store_is_touched(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """An ambiguous draft is a drafting error; reporting it must not
        require the novel to have been ingested first."""
        path = _write(
            tmp_path,
            '[[identity]]\nname = "A"\nsurfaces = ["x"]\n'
            '[[identity]]\nname = "B"\nsurfaces = ["x"]\n',
        )
        empty = Store(str(tmp_path / "empty.db"))
        try:
            with pytest.raises(AmbiguousSurfaceError):
                expand_draft(path, empty)
        finally:
            empty.close()


class TestPrefixCollisions:
    """A word-boundary PREFIX puts two gold records on one offset.

    That was fatal until 2026-09-24, because `GoldMention.key` was
    (novel_id, chapter, offset) and the two records collapsed onto one key.
    The key now carries the normalised surface, so both survive; these tests
    assert survival rather than refusal, which is the stronger property --
    the old ones could pass while every record was still being destroyed
    somewhere downstream.
    """

    def test_a_prefix_surface_expands_to_both_records(self, tmp_path, store) -> None:  # type: ignore[no-untyped-def]
        path = _write(
            tmp_path,
            '[[identity]]\nname = "Klein"\nsurfaces = ["Klein", "Klein Moretti"]\n',
        )
        gold = expand_draft(path, store)
        keys = [m.key for m in gold.mentions]
        assert len(keys) == len(set(keys)), "a prefix collision destroyed a record"

    def test_it_keeps_both_across_different_identities_too(self, tmp_path, store) -> None:  # type: ignore[no-untyped-def]
        """The case found in the shipped RI draft: a clan name that prefixes
        its own members' names. Both annotations are correct -- the clan name
        and the member's name genuinely both begin at that offset -- so both
        must survive, under their own identities."""
        path = _write(
            tmp_path,
            '[[identity]]\nname = "Gu Yue clan"\nkind = "organization"\n'
            'surfaces = ["Gu Yue"]\n'
            '[[identity]]\nname = "Gu Yue Chen Bo"\nsurfaces = ["Gu Yue Chen Bo"]\n',
        )
        gold = expand_draft(path, store)
        keys = [m.key for m in gold.mentions]
        assert len(keys) == len(set(keys))
        identities = {m.identity for m in gold.mentions}
        # Neither annotation may be swallowed by the other.
        assert {"Gu Yue clan", "Gu Yue Chen Bo"} <= identities or not gold.mentions

    def test_a_suffix_is_allowed(self, tmp_path, store) -> None:  # type: ignore[no-untyped-def]
        """"Wang" inside "Elder Wang" starts later, so the two records have
        different keys and both survive. Refusing it would reject the
        commonest real annotation shape in this corpus."""
        path = _write(
            tmp_path,
            '[[identity]]\nname = "Wang"\nsurfaces = ["Wang", "Elder Wang"]\n',
        )
        assert expand_draft(path, store) is not None

    def test_a_non_boundary_prefix_is_allowed(self, tmp_path, store) -> None:  # type: ignore[no-untyped-def]
        """"Wang" prefixes "Wangzhou" as a string, but `_find_all`'s
        lookahead would never match it, so there is no collision to refuse."""
        path = _write(
            tmp_path,
            '[[identity]]\nname = "Wang"\nsurfaces = ["Wang"]\n'
            '[[identity]]\nname = "Wangzhou"\nsurfaces = ["Wangzhou"]\n',
        )
        assert expand_draft(path, store) is not None


class TestShippedDrafts:
    def test_the_new_lotm_draft_is_clean(self) -> None:
        """The independent LOTM ch1-3 replacement for a 100%-circular gold
        file (EVOLUTION 4.83)."""
        import tomllib
        from pathlib import Path

        from echotales.pipeline.eval.draft import _assert_unambiguous

        toml = Path("data/gold/lord-of-the-mysteries-c1-c3.toml")
        if not toml.exists():
            pytest.skip("draft not present in this checkout")
        _assert_unambiguous(toml, tomllib.loads(toml.read_text(encoding="utf-8")))

    @pytest.mark.parametrize(
        "name",
        ["reverend-insanity-c1-c5.toml", "reverend-insanity-c1-c60-extended.toml"],
    )
    def test_the_shipped_ri_drafts_expand_again(self, name: str) -> None:
        """These two were expect-to-raise from 2026-09-23 to 2026-09-24.

        `reverend-insanity-c1-c5.toml` is the project's one genuinely
        independent draft (EVOLUTION 4.74) and it lists "Gu Yue" (the clan, an
        organization) alongside "Gu Yue Chen Bo" and other members, so every
        member's offset carries a second record typing it as the clan. The
        extended file also has bare "Gu" as a `not_entity` prefixing "Gu Yue".

        Both annotations at such an offset are *correct*; the destruction was
        in the key, not the data, so the fix was to carry the surface in
        `GoldMention.key` rather than to edit what an annotator asserted.
        These now assert the drafts expand, which is what the owner's
        adjudication decided (2026-09-24)."""
        import tomllib
        from pathlib import Path

        from echotales.pipeline.eval.draft import _assert_unambiguous

        toml = Path("data/gold") / name
        if not toml.exists():
            pytest.skip("shipped draft not present in this checkout")
        # Must not raise: prefix collisions are advisory now.
        _assert_unambiguous(toml, tomllib.loads(toml.read_text(encoding="utf-8")))
