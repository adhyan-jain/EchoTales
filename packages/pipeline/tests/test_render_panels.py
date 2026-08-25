"""Panel image generation (xyz.md Step 4, video-assembly revision)."""

from __future__ import annotations

import pytest

from echotales.core.enums import (
    OBSERVER_READER,
    AliasType,
    AssertedBy,
    BlockType,
    ReferenceMode,
    SpanType,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, Block, Chapter, DiscoursePosition, Mention, Self
from echotales.core.store import Store
from echotales.pipeline.persona.reference_gen import REFERENCE_PATH_KEY
from echotales.pipeline.persona.split import BodyEpoch, write_epochs
from echotales.pipeline.render.panels import (
    character_looks,
    get_engine,
    present_beat_entities_with_reveals,
    render_panels,
)


def _seeded_store(tmp_path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[
                Block(index=0, block_type=BlockType.HEADING, text="Chapter 1"),
                Block(index=1, block_type=BlockType.PROSE, text="Fang Yuan stood."),
            ],
        )
    )
    store.add_self(
        Self(
            id="t:self1",
            novel_id="t",
            canonical_label="Fang Yuan",
            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
            kind=TargetKind.SELF,
        )
    )
    store.add_mentions(
        [
            Mention(
                id="m1",
                novel_id="t",
                segment_id="s",
                chapter=1.0,
                offset=0,
                block_index=1,
                text="Fang Yuan",
                alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT,
                target_kind=TargetKind.SELF,
                target_id="t:self1",
            )
        ]
    )
    store.conn.commit()
    return store


class TestRenderPanels:
    def test_renders_one_panel_per_beat_not_per_block(self, tmp_path) -> None:
        """A paragraph is not a panel. Drawing every block produced 89
        near-duplicate images for one RI chapter, mostly scenery -- see
        `render/beats.py`. The heading block still contributes nothing."""
        store = _seeded_store(tmp_path)
        report = render_panels("t", store, out_dir=tmp_path / "panels")
        assert report.panels == 1

    def test_panel_count_is_capped_per_chapter(self, tmp_path) -> None:
        """The cap is the point: fewer, better images beat a hundred
        variations on an empty courtyard, and the render budget is better
        spent on more steps per image than on more images."""
        store = _seeded_store(tmp_path)
        report = render_panels(
            "t", store, out_dir=tmp_path / "panels", max_panels=1
        )
        assert report.panels <= 1

    def test_block_range_restricts_which_blocks_get_panels(self, tmp_path) -> None:
        """Panel cost is set by --max-panels, not chapter length, so a full
        chapter costs the same whether you are tuning one portion of it or
        all of it. block_range lets a caller restrict generation to a
        contiguous range for testing, without first classifying scenes."""
        store = Store(str(tmp_path / "t.db"))
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(
            Chapter(
                novel_id="t",
                number=1.0,
                title="T",
                source_href="a.html",
                blocks=[
                    Block(index=i, block_type=BlockType.PROSE, text=f"Block {i} prose.")
                    for i in range(10)
                ],
            )
        )
        store.conn.commit()

        report = render_panels(
            "t", store, out_dir=tmp_path / "panels", max_panels=20, block_range=(0, 4)
        )
        out_dir = tmp_path / "panels" / "ch1"
        # Filenames are `p{seq}_b{block}` -- sequential in play order, with
        # the source block kept for tracing.
        rendered = {
            int(p.stem.split("_b")[1].removesuffix("_crowd"))
            for p in out_dir.glob("*.png")
        }
        assert rendered and max(rendered) <= 4
        assert report.panels == len(rendered)

    def test_stub_writes_a_real_png(self, tmp_path) -> None:
        """Not a no-op: `director.py`/`compose.py` will open these files and
        read their dimensions, and a stub that wrote nothing would let a
        broken path pass CI -- same reasoning as `voice/engine.py::StubEngine`."""
        store = _seeded_store(tmp_path)
        out_dir = tmp_path / "panels"
        render_panels("t", store, out_dir=out_dir)
        image = next((out_dir / "ch1").glob("p*_b0001.png"))
        assert image.exists()
        assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_rerun_reuses_cached_panels(self, tmp_path) -> None:
        store = _seeded_store(tmp_path)
        out_dir = tmp_path / "panels"
        render_panels("t", store, out_dir=out_dir)
        report = render_panels("t", store, out_dir=out_dir)
        assert report.skipped_cached == 1
        assert report.panels == 1

    def test_unknown_engine_raises_rather_than_silently_stubbing(self) -> None:
        with pytest.raises(ValueError, match="unknown image engine"):
            get_engine("nope")

    def test_identical_prompts_across_blocks_are_deduped_not_regenerated(
        self, tmp_path
    ) -> None:
        """Two blocks whose final prompt is byte-identical -- same cast (none),
        same environment, same locale, same beat text -- must not pay for a
        second diffusion pass. With one fixed seed per run, an identical
        prompt produces an identical image, so a second generation call
        reproduces a file already on disk for pure GPU cost."""
        store = Store(str(tmp_path / "t.db"))
        store.add_novel("t", "T", "x.epub", "generic")
        for chapter_number in (1.0, 2.0):
            store.add_chapter(
                Chapter(
                    novel_id="t",
                    number=chapter_number,
                    title="T",
                    source_href=f"{chapter_number:g}.html",
                    blocks=[Block(index=0, block_type=BlockType.PROSE, text="A room was quiet.")],
                )
            )
        store.conn.commit()

        report = render_panels("t", store, out_dir=tmp_path / "panels")
        assert report.panels == 2
        assert report.deduped_panels == 1
        # And the deduped file is a real, independent copy, not a symlink
        # into the manifest referencing a path that vanishes if the source
        # is ever cleaned up.
        ch1 = next((tmp_path / "panels" / "ch1").glob("p*_b0000.png"))
        ch2 = next((tmp_path / "panels" / "ch2").glob("p*_b0000.png"))
        assert ch1.exists() and ch2.exists()
        assert ch1.read_bytes() == ch2.read_bytes()

    def test_a_non_person_entity_never_joins_the_foreground_cast(self, tmp_path) -> None:
        """Measured on real RI ch1: a LOCATION ("Qing Mao Mountain") and an
        ORGANIZATION ("Daoist Gu") were both marked PRESENT in the block
        Fang Yuan is in, and rode into the panel prompt as if they were
        people to draw -- the generated panel was a stranger's face with no
        gender, hair or expression grounding it, because two of the three
        "characters" had no appearance data and never could."""
        from echotales.core.enums import TargetKind
        from echotales.core.models import MAIN_TIMELINE, NarrativeSegment
        from echotales.pipeline.persona.runner import get_panel_cast

        store = _seeded_store(tmp_path)
        store.add_self(
            Self(
                id="t:self2",
                novel_id="t",
                canonical_label="Some Mountain",
                first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
                kind=TargetKind.LOCATION,
            )
        )
        store.add_mentions(
            [
                Mention(
                    id="m2",
                    novel_id="t",
                    segment_id="s",
                    chapter=1.0,
                    offset=0,
                    block_index=1,
                    text="Some Mountain",
                    alias_type=AliasType.RIGID_NAME,
                    span_type=SpanType.NARRATION_ACTION,
                    reference_mode=ReferenceMode.PRESENT,
                    target_kind=TargetKind.SELF,  # stale on purpose -- see note below
                    target_id="t:self2",
                )
            ]
        )
        store.conn.commit()

        chapter = store.get_chapter("t", 1.0)
        mentions = store.get_mentions("t", 1.0)
        segment = NarrativeSegment(
            id="seg-1",
            novel_id="t",
            chapter_from=1.0,
            offset_from=0,
            chapter_to=1.0,
            offset_to=1,
            timeline_id=MAIN_TIMELINE,
            story_seq_from=1.0,
            story_seq_to=1.0,
        )
        cast = get_panel_cast(
            "t", chapter, 1, mentions=mentions, segments=[segment], spans=[], store=store
        )
        labels = [c.self_label for c in cast.foreground_characters]
        assert "Fang Yuan" in labels
        assert "Some Mountain" not in labels

    def test_present_beat_entities_with_reveals_includes_the_revealed_id(
        self, tmp_path
    ) -> None:
        """FIX 2: the director path's cast-building (`present_beat_entities`)
        had no notion of a narrator reveal at all -- only the mechanical
        fallback path's `get_panel_cast` did, and no real render uses that
        path. A block that reveals someone by name ("this was none other
        than Fang Yuan") must add them to the director's cast too."""
        from echotales.pipeline.resolve.detect_reveals import detect_reveals

        store = Store(str(tmp_path / "t.db"))
        store.add_novel("t", "T", "x.epub", "generic")
        narration = "This was none other than Fang Yuan."
        store.add_chapter(
            Chapter(
                novel_id="t",
                number=1.0,
                title="T",
                source_href="a.html",
                blocks=[Block(index=0, block_type=BlockType.PROSE, text=narration)],
            )
        )
        store.add_self(
            Self(
                id="t:self1",
                novel_id="t",
                canonical_label="Fang Yuan",
                first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
                kind=TargetKind.SELF,
            )
        )
        from echotales.core.models import Span

        store.add_spans(
            [
                Span(
                    id="sp0",
                    novel_id="t",
                    chapter=1.0,
                    block_index=0,
                    start=0,
                    end=len(narration),
                    span_type=SpanType.NARRATION_DESCRIPTION,
                    text=narration,
                )
            ]
        )
        # A placeholder mention -- someone is here, but no resolved name --
        # is what a reveal is meant to supplement, not the empty-mentions
        # case: reference_mode is deliberately NOT PRESENT so the plain
        # present_beat_entities pass alone finds nobody.
        store.add_mentions(
            [
                Mention(
                    id="m0",
                    novel_id="t",
                    segment_id="s",
                    chapter=1.0,
                    offset=0,
                    block_index=0,
                    text="This",
                    alias_type=AliasType.RIGID_NAME,
                    span_type=SpanType.NARRATION_DESCRIPTION,
                    reference_mode=ReferenceMode.NARRATOR_REFERENCE,
                    target_kind=TargetKind.SELF,
                    target_id="t:self1",
                )
            ]
        )
        store.conn.commit()
        detect_reveals(store, "t")

        mentions = store.get_mentions("t", 1.0)
        without_reveals = [m for m in mentions if m.reference_mode is ReferenceMode.PRESENT]
        assert without_reveals == []  # sanity: the plain pass really finds nobody

        ids = present_beat_entities_with_reveals(
            mentions, [0], store=store, novel_id="t", chapter_number=1.0
        )
        assert "t:self1" in ids

    def test_present_beat_entities_with_reveals_no_store_is_a_plain_pass(
        self, tmp_path
    ) -> None:
        """Guard: no store (mirrors `direct_beat`'s own `store=None` default)
        must not crash -- it degrades to the plain PRESENT-only pass."""
        ids = present_beat_entities_with_reveals(
            [], [0], store=None, novel_id="t", chapter_number=1.0
        )
        assert ids == []

    def test_empty_present_beat_carries_forward_in_scene_cast_via_director(
        self, tmp_path, monkeypatch
    ) -> None:
        """FIX 1 + FIX 3: exercises the LLM-director branch end to end (no
        real render test did before this -- every existing test called
        `render_panels` with the default `client=None`, so the branch every
        real render actually uses had zero coverage).

        A scene's second beat has no PRESENT mention of anyone -- only a
        dialogue-only reference to a different, absent character ("Fang
        Yuan, stop!" shouted at him from off scene). The old fallback
        pulled in *any* mention regardless of reference mode, which is the
        confirmed mechanism behind "every panel is Fang Yuan": he is
        addressed in dialogue constantly even in scenes he never appears
        in. The fix must carry forward the scene's real PRESENT cast (the
        bystander from beat 1) instead, never reach for the absent name.
        """
        from echotales.pipeline.render import panels as panels_mod
        from echotales.pipeline.render.direction import Direction, PanelDirection
        from echotales.pipeline.render.scenes import Scene

        store = Store(str(tmp_path / "t.db"))
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(
            Chapter(
                novel_id="t",
                number=1.0,
                title="T",
                source_href="a.html",
                blocks=[
                    Block(index=i, block_type=BlockType.PROSE, text=f"Block {i} prose.")
                    for i in range(8)
                ],
            )
        )
        store.add_self(
            Self(
                id="t:bystander",
                novel_id="t",
                canonical_label="A Bystander",
                first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
                kind=TargetKind.SELF,
            )
        )
        store.add_self(
            Self(
                id="t:fangyuan",
                novel_id="t",
                canonical_label="Fang Yuan",
                first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
                kind=TargetKind.SELF,
            )
        )
        store.add_mentions(
            [
                Mention(
                    id="m1",
                    novel_id="t",
                    segment_id="s",
                    chapter=1.0,
                    offset=0,
                    block_index=0,
                    text="A Bystander",
                    alias_type=AliasType.RIGID_NAME,
                    span_type=SpanType.NARRATION_ACTION,
                    reference_mode=ReferenceMode.PRESENT,
                    target_kind=TargetKind.SELF,
                    target_id="t:bystander",
                ),
                # Blocks 4-7 (the scene's second beat) have no PRESENT
                # mention of anyone -- only this dialogue-only reference to
                # a character who is not physically in this scene.
                Mention(
                    id="m2",
                    novel_id="t",
                    segment_id="s",
                    chapter=1.0,
                    offset=0,
                    block_index=5,
                    text="Fang Yuan",
                    alias_type=AliasType.RIGID_NAME,
                    span_type=SpanType.DIALOGUE,
                    reference_mode=ReferenceMode.DIALOGUE_REFERENCE,
                    target_kind=TargetKind.SELF,
                    target_id="t:fangyuan",
                ),
            ]
        )
        store.conn.commit()

        # One continuous 8-block scene -- isolates the carry-forward logic
        # under test from `group_scenes`'s own boundary detection, which
        # this fix does not touch.
        monkeypatch.setattr(
            panels_mod, "group_scenes", lambda *a, **k: [Scene(index=0, blocks=list(range(8)))]
        )
        _looks = {
            "t:bystander": ("A Bystander", "a bystander clause", None, "male"),
            "t:fangyuan": ("Fang Yuan", "fang yuan clause", None, "male"),
        }
        monkeypatch.setattr(
            panels_mod, "character_looks", lambda store, entity_id, **kw: _looks.get(entity_id)
        )

        received_casts: list[dict[str, str]] = []

        def _fake_direct_beat(
            beat_text, *, cast, novel_style, client, novel_id="", context_brief="", store=None
        ):
            received_casts.append(dict(cast))
            return Direction(
                direction=PanelDirection(action="Someone stands.", layout="Someone stands alone."),
                cast=cast,
                novel_style=novel_style,
            )

        monkeypatch.setattr(panels_mod, "direct_beat", _fake_direct_beat)

        report = render_panels(
            "t", store, out_dir=tmp_path / "panels", max_panels=5, client=object()
        )

        assert len(received_casts) == 2  # beat 1 (blocks 0-3), beat 2 (blocks 4-7)
        assert "A Bystander" in received_casts[0]
        # The carry-forward beat: the real in-scene cast survives...
        assert "A Bystander" in received_casts[1]
        # ...and the old any-reference-mode fallback (which would have
        # picked up Fang Yuan's dialogue-only mention) does not fire.
        assert "Fang Yuan" not in received_casts[1]
        assert report.panels >= 1


class TestCharacterLooksBodySelection:
    """Fix 10: a panel must draw the body that is actually active at its own
    chapter, not whichever body happened to be extracted first.

    IP-Adapter itself was permanently removed (colour/composition
    contamination -- `render/panels.py`'s own comment at the `engine.generate`
    call site, HANDOFF 4.47); `character_looks` still has to hand back the
    *correct* per-chapter reference path regardless of what, if anything,
    later conditions pixels on it -- the manifest records `conditioned_on`
    for provenance even when generation is prompt-only.
    """

    def _two_body_store(self, tmp_path) -> Store:
        store = Store(str(tmp_path / "t.db"))
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_self(
            Self(
                id="t:self1",
                novel_id="t",
                canonical_label="Fang Yuan",
                first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
                kind=TargetKind.SELF,
            )
        )
        epochs = [
            BodyEpoch(
                index=0,
                persona_id="t:self1:body1",
                body_label="Fang Yuan",
                from_pos=1.0,
                to_pos=2.0,
                cause="death",
                evidence="",
            ),
            BodyEpoch(
                index=1,
                persona_id="t:self1:body2",
                body_label="Fang Yuan (body 2)",
                from_pos=2.0,
                to_pos=None,
                cause="rebirth",
                evidence="",
            ),
        ]
        write_epochs(store, "t", store.get_self("t:self1"), epochs, observer_id=OBSERVER_READER)

        body1_sheet = tmp_path / "body1.png"
        body2_sheet = tmp_path / "body2.png"
        body1_sheet.write_bytes(b"")
        body2_sheet.write_bytes(b"")

        for persona_id, path in (("t:self1:body1", body1_sheet), ("t:self1:body2", body2_sheet)):
            store.add_attribute(
                "t",
                Attribute(
                    target_kind=TargetKind.PERSONA,
                    target_id=persona_id,
                    key=REFERENCE_PATH_KEY,
                    value=str(path),
                    interval=FuzzyInterval.open_ended(1.0, last_evidence=1.0),
                    learned_at_pos=DiscoursePosition(chapter=1.0, offset=0),
                    observer_id=OBSERVER_READER,
                    asserted_by=AssertedBy.INFERENCE,
                    truth_status=TruthStatus.INFERRED,
                ),
            )
        store.conn.commit()
        return store, body1_sheet, body2_sheet

    def test_reference_switches_at_the_body_boundary(self, tmp_path) -> None:
        store, body1_sheet, body2_sheet = self._two_body_store(tmp_path)

        before = character_looks(store, "t:self1", novel_id="t", chapter=1.5)
        after = character_looks(store, "t:self1", novel_id="t", chapter=2.5)

        assert before is not None and after is not None
        assert before[2] == body1_sheet
        assert after[2] == body2_sheet

    def test_reference_at_the_exact_transition_goes_to_the_new_body(self, tmp_path) -> None:
        """Point-known intervals are half-open (`FuzzyInterval.point_known`);
        the position the new body starts at must already read as the new
        body, not the last moment of the old one."""
        store, _body1_sheet, body2_sheet = self._two_body_store(tmp_path)

        at_boundary = character_looks(store, "t:self1", novel_id="t", chapter=2.0)

        assert at_boundary is not None
        assert at_boundary[2] == body2_sheet
