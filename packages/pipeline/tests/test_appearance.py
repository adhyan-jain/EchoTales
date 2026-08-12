"""Appearance extraction and reference-sheet generation (Phase 7b / 9).

The two stages that closed the "every character is a blank to the visual
pipeline" gap: `resolve/appearance_extract.py` reads how a character looks
out of narration, `persona/reference_gen.py` turns that into the reference
image IP-Adapter conditions panels against.
"""

from __future__ import annotations

from echotales.core.enums import (
    AliasType,
    BlockType,
    Prominence,
    ReferenceMode,
    SpanType,
    TargetKind,
    TruthStatus,
)
from echotales.core.models import (
    Block,
    Chapter,
    DiscoursePosition,
    Mention,
    Self,
    Span,
)
from echotales.core.store import Store
from echotales.pipeline.resolve.appearance_extract import (
    AppearanceResponse,
    _values_from,
    build_prompt,
    eligible_prominence,
    gather_appearance_passages,
)


class _FakeResult:
    def __init__(self, value: object) -> None:
        self.value = value
        self.prompt_tokens = 0
        self.completion_tokens = 0


class _FakeClient:
    """Returns a fixed appearance, recording the prompts it was given."""

    def __init__(self, value: AppearanceResponse) -> None:
        self.value = value
        self.prompts: list[str] = []

    def complete(self, task, prompt, schema, **kwargs):  # noqa: ANN001, ARG002
        self.prompts.append(prompt)
        return _FakeResult(self.value)


def _store(tmp_path, *, mentions_per_chapter: int = 40) -> Store:
    """A novel where `Fang Yuan` is described in narration and present."""
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")

    blocks = [
        Block(index=0, block_type=BlockType.PROSE, text="Fang Yuan wore green robes."),
        Block(index=1, block_type=BlockType.DIALOGUE, text='"Hand it over!"'),
    ]
    store.add_chapter(
        Chapter(novel_id="t", number=1.0, title="T", source_href="a.html", blocks=blocks)
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
    store.add_spans(
        [
            Span(
                id="sp0",
                novel_id="t",
                chapter=1.0,
                block_index=0,
                start=0,
                end=27,
                span_type=SpanType.NARRATION_DESCRIPTION,
                text="Fang Yuan wore green robes.",
            ),
            Span(
                id="sp1",
                novel_id="t",
                chapter=1.0,
                block_index=1,
                start=0,
                end=17,
                span_type=SpanType.DIALOGUE,
                text='"Hand it over!"',
            ),
        ]
    )
    # Enough mentions to clear the RECURRING floor.
    store.add_mentions(
        [
            Mention(
                id=f"m{i}",
                novel_id="t",
                segment_id="s",
                chapter=1.0,
                offset=0,
                block_index=0,
                text="Fang Yuan",
                alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_DESCRIPTION,
                reference_mode=ReferenceMode.PRESENT,
                target_kind=TargetKind.SELF,
                target_id="t:self1",
            )
            for i in range(mentions_per_chapter)
        ]
    )
    store.conn.commit()
    return store


class TestEvidenceGathering:
    def test_narration_is_evidence_and_dialogue_is_not(self, tmp_path) -> None:
        """A character's own spoken line says nothing about their face, and
        block 1 is where the dialogue lives."""
        store = _store(tmp_path)
        passages = gather_appearance_passages(store, "t", "t:self1")
        assert passages == ["Fang Yuan wore green robes."]

    def test_chapter_scoping_excludes_everything_else(self, tmp_path) -> None:
        store = _store(tmp_path)
        assert gather_appearance_passages(
            store, "t", "t:self1", allowed_chapters={9.0}
        ) == []

    def test_prominence_is_derived_not_read_off_the_stale_column(
        self, tmp_path
    ) -> None:
        """Measured on the real RI database: every entity carries the
        `INCIDENTAL` default even at 5,191 mentions, so trusting the stored
        column makes this stage silently process nothing."""
        store = _store(tmp_path)
        entity = store.get_self("t:self1")
        assert entity.prominence is Prominence.INCIDENTAL  # the stale column
        assert eligible_prominence(store, "t", entity) is Prominence.RECURRING


class TestResponseHandling:
    def test_empty_and_non_committal_values_are_dropped(self) -> None:
        """"unknown" is the model declining, not a hair colour."""
        out = _values_from(
            AppearanceResponse(hair_color="unknown", eye_color="", skin_tone="pale")
        )
        assert out == {"skin_tone": "pale"}

    def test_feature_list_is_joined_for_storage(self) -> None:
        out = _values_from(
            AppearanceResponse(distinguishing_features=["a scar", "one eye"])
        )
        assert out["distinguishing_features"] == "a scar, one eye"

    def test_prompt_separates_standing_identity_from_transient_state(self) -> None:
        """Measured on RI ch1 (Fang Yuan's death scene): without this, the
        extractor returned typical_attire="deep green robes that had been
        torn to shreds" and features "covered in blood" -- which, baked into
        a reference sheet, redraws him bloodied for all 199 chapters."""
        prompt = build_prompt("Fang Yuan", ["He bled."])
        assert "never 'torn green robes'" in prompt
        assert "Never injuries, blood" in prompt

    def test_prompt_warns_off_describing_bystanders(self) -> None:
        """Real RI ch1 output attributed a neighbour's build to Fang Yuan
        until the prompt said not to."""
        prompt = build_prompt("Fang Yuan", ["He stood there."])
        assert "only Fang Yuan's own appearance" in prompt


class TestExtractAppearance:
    def test_writes_inferred_attributes_under_the_persona(self, tmp_path) -> None:
        from echotales.pipeline.resolve.appearance_extract import extract_appearance

        store = _store(tmp_path)
        client = _FakeClient(
            AppearanceResponse(hair_color="black", typical_attire="green robes")
        )
        report = extract_appearance("t", store, client=client)

        assert report.attributes_written == 2
        attrs = {
            a.key: a for a in store.get_attributes(TargetKind.PERSONA, "t:self1:body1")
        }
        assert attrs["hair_color"].value == "black"
        # A model's reading of the prose, never the prose's own assertion.
        assert attrs["hair_color"].truth_status is TruthStatus.INFERRED

    def test_rerunning_does_not_duplicate_known_values(self, tmp_path) -> None:
        """Re-attestation adds evidence; it must not write the same fact twice."""
        from echotales.pipeline.resolve.appearance_extract import extract_appearance

        store = _store(tmp_path)
        client = _FakeClient(AppearanceResponse(hair_color="black"))
        extract_appearance("t", store, client=client)
        again = extract_appearance("t", store, client=client)

        assert again.attributes_written == 0
        assert again.attributes_already_known == 1

    def test_a_failing_call_does_not_sink_the_stage(self, tmp_path) -> None:
        from echotales.pipeline.resolve.appearance_extract import extract_appearance

        class Boom:
            def complete(self, *a, **k):  # noqa: ANN002, ANN003, ARG002
                raise RuntimeError("model down")

        report = extract_appearance("t", _store(tmp_path), client=Boom())
        assert report.failures == 1
        assert report.attributes_written == 0


class TestReferenceGeneration:
    def test_prompt_is_built_from_stored_appearance_and_is_manga(self) -> None:
        from echotales.pipeline.persona.reference_gen import build_reference_prompt

        prompt = build_reference_prompt(
            "Fang Yuan",
            {"hair_color": "black", "hair_style": "long", "typical_attire": "green robes"},
            gender="male",
            age_band="youth",
        )
        assert "black long hair" in prompt
        assert "wearing green robes" in prompt
        assert "manga style" in prompt and "black and white" in prompt

    def test_generation_is_cached_on_the_appearance_digest(self, tmp_path) -> None:
        """Regenerating every principal on every run is not viable; only an
        appearance change should invalidate a sheet."""
        from echotales.pipeline.persona.reference_gen import generate_references
        from echotales.pipeline.render.panels import get_engine
        from echotales.pipeline.resolve.appearance_extract import extract_appearance

        store = _store(tmp_path)
        extract_appearance(
            "t", store, client=_FakeClient(AppearanceResponse(hair_color="black"))
        )

        first = generate_references(
            "t", store, engine=get_engine("stub"), out_dir=tmp_path / "refs"
        )
        assert first.generated == 1

        second = generate_references(
            "t", store, engine=get_engine("stub"), out_dir=tmp_path / "refs"
        )
        assert second.generated == 0
        assert second.reused_cached == 1

    def test_transient_condition_never_reaches_the_reference_sheet(
        self, tmp_path
    ) -> None:
        """The second half of the consistency guarantee: even if the model
        ignores the prompt and files an injury as identity, it is dropped at
        the boundary rather than drawn into every later chapter."""
        from echotales.pipeline.persona.reference_gen import appearance_of
        from echotales.pipeline.resolve.appearance_extract import extract_appearance

        store = _store(tmp_path)
        extract_appearance(
            "t",
            store,
            client=_FakeClient(
                AppearanceResponse(hair_color="black", current_condition="injured")
            ),
        )
        standing = appearance_of(store, "t:self1:body1")
        assert standing == {"hair_color": "black"}
        assert "current_condition" in appearance_of(
            store, "t:self1:body1", standing_only=False
        )

    def test_character_with_no_appearance_gets_no_sheet(self, tmp_path) -> None:
        from echotales.pipeline.persona.reference_gen import generate_references
        from echotales.pipeline.render.panels import get_engine

        report = generate_references(
            "t", _store(tmp_path), engine=get_engine("stub"), out_dir=tmp_path / "refs"
        )
        assert report.generated == 0
        assert report.skipped_no_appearance == 1
