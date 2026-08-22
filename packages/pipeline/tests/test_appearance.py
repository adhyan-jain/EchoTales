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
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    Attribute,
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
    AttributeClaim,
    _claims_from,
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

    def complete(self, task, prompt, schema, **kwargs):
        self.prompts.append(prompt)
        return _FakeResult(self.value)


def _store(
    tmp_path,
    *,
    mentions_per_chapter: int = 40,
    narration_text: str = "Fang Yuan had black hair and wore green robes. He was injured.",
) -> Store:
    """A novel where `Fang Yuan` is described in narration and present."""
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")

    blocks = [
        Block(index=0, block_type=BlockType.PROSE, text=narration_text),
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
                end=len(narration_text),
                span_type=SpanType.NARRATION_DESCRIPTION,
                text=narration_text,
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
        assert passages == ["Fang Yuan had black hair and wore green robes. He was injured."]

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
        out = _claims_from(
            AppearanceResponse(
                hair_color=AttributeClaim(value="unknown", source="x"),
                eye_color=AttributeClaim(value="", source=""),
                skin_tone=AttributeClaim(value="pale", source="her skin was pale"),
            )
        )
        assert list(out) == ["skin_tone"]
        assert out["skin_tone"][0].value == "pale"

    def test_feature_list_is_joined_for_storage(self) -> None:
        out = _claims_from(
            AppearanceResponse(
                distinguishing_features=[
                    AttributeClaim(value="a scar", source="a scar crossed his cheek"),
                    AttributeClaim(value="one eye", source="he had only one eye"),
                ]
            )
        )
        assert [c.value for c in out["distinguishing_features"]] == ["a scar", "one eye"]


class TestCitationVerification:
    """Fix 2: a claim must cite a real passage sentence that is actually
    about the target, not merely echo the extraction prompt's own vocabulary
    back."""

    def test_fabricated_source_is_discarded(self) -> None:
        from echotales.pipeline.resolve.appearance_extract import (
            AppearanceReport,
            _verify_citations,
        )

        report = AppearanceReport(novel_id="t")
        claims = {
            "typical_attire": [
                AttributeClaim(value="green robes", source="Bai Ning Bing wore green robes.")
            ]
        }
        out = _verify_citations(claims, ["Bai Ning Bing, clothed in white."], {"bai ning bing"}, report)
        assert out == {}
        assert report.discards_by_reason["source_not_in_passages"] == 1

    def test_real_quote_about_someone_else_is_discarded(self) -> None:
        """The exact real case: "green" genuinely appears in the passage --
        as Xiong Jiang's iris colour -- so the source-exists check alone
        would pass it. The proximity-to-target check must still reject it."""
        from echotales.pipeline.resolve.appearance_extract import (
            AppearanceReport,
            _verify_citations,
        )

        report = AppearanceReport(novel_id="t")
        passage = (
            "Xiong Jiang used Roaming Zombie Gu, his two irises turning "
            "gloomy green; Xiong Li's two eyes were red whereas Bai Ning "
            "Bing's pair of pupils were azure like crystals."
        )
        claims = {
            "typical_attire": [
                AttributeClaim(value="green robes", source="his two irises turning gloomy green")
            ]
        }
        out = _verify_citations(claims, [passage], {"bai ning bing"}, report)
        assert out == {}
        assert report.discards_by_reason["target_not_near_source"] == 1

    def test_grounded_citation_survives(self) -> None:
        from echotales.pipeline.resolve.appearance_extract import (
            AppearanceReport,
            _verify_citations,
        )

        report = AppearanceReport(novel_id="t")
        passage = "Standing on a slope was Bai Ning Bing, clothed in white."
        claims = {
            "typical_attire": [
                AttributeClaim(
                    value="white robes",
                    source="Standing on a slope was Bai Ning Bing, clothed in white.",
                )
            ]
        }
        out = _verify_citations(claims, [passage], {"bai ning bing"}, report)
        assert out == {"typical_attire": "white robes"}
        assert report.discards_by_reason == {}

    def test_pronoun_continuation_after_naming_clause_survives(self) -> None:
        """"the sentence carrying the appearance is frequently the pronoun
        sentence right after the naming one" (`gather_appearance_passages`).
        A citation for the pronoun clause must still ground against the
        name in the clause before it."""
        from echotales.pipeline.resolve.appearance_extract import (
            AppearanceReport,
            _verify_citations,
        )

        report = AppearanceReport(novel_id="t")
        passage = "This was none other than Bai Ning Bing. His hair was snowy white."
        claims = {
            "hair_color": [
                AttributeClaim(value="snowy white", source="His hair was snowy white.")
            ]
        }
        out = _verify_citations(claims, [passage], {"bai ning bing"}, report)
        assert out == {"hair_color": "snowy white"}

    def test_missing_source_is_discarded(self) -> None:
        from echotales.pipeline.resolve.appearance_extract import (
            AppearanceReport,
            _verify_citations,
        )

        report = AppearanceReport(novel_id="t")
        claims = {"hair_color": [AttributeClaim(value="black", source="")]}
        out = _verify_citations(claims, ["Fang Yuan had black hair."], {"fang yuan"}, report)
        assert out == {}
        assert report.discards_by_reason["missing_source"] == 1

    def test_ungrounded_values_are_dropped(self) -> None:
        """The real case: Bai Ning Bing is introduced as "This white-clothed
        young man was none other than ... Bai Ning Bing", and the extractor
        returned typical_attire="green robes" -- green being the Gu Yue
        clan's colour and the novel's most frequent robe description, so the
        model reached for the genre default over the sentence in front of
        it. Nothing about that is detectable from the response alone."""
        from echotales.pipeline.resolve.appearance_extract import _clean_values

        surfaces = {"bai ning bing"}
        passages = [
            "This white-clothed young man was none other than Bai Ning Bing. "
            "His snowy white hair stirred.",
        ]
        out = _clean_values(
            {"typical_attire": "green robes", "hair_color": "snowy white"},
            "Bai Ning Bing",
            surfaces,
            passages,
        )
        assert out == {"hair_color": "snowy white"}

    def test_word_grounded_elsewhere_in_evidence_does_not_ground_the_target(self) -> None:
        """The bug this whole fix exists for: "green" is genuinely present in
        the evidence pool, but describes Xiong Jiang's irises, not Bai Ning
        Bing's attire. A bag-of-words check over the pooled evidence let this
        ground `typical_attire="green robes"` for Bai Ning Bing; a check
        scoped to text near his own surface form must reject it."""
        from echotales.pipeline.resolve.appearance_extract import _clean_values

        surfaces = {"bai ning bing"}
        passages = [
            "Xiong Jiang used Roaming Zombie Gu, his two irises turning "
            "gloomy green; Xiong Li's two eyes were red whereas Bai Ning "
            "Bing's pair of pupils were azure like crystals.",
        ]
        out = _clean_values(
            {"typical_attire": "green robes"},
            "Bai Ning Bing",
            surfaces,
            passages,
        )
        assert out == {}

    def test_generic_only_values_are_left_alone(self) -> None:
        """A value made purely of generic nouns carries no claim to check,
        so it is kept rather than dropped for lack of evidence."""
        from echotales.pipeline.resolve.appearance_extract import _clean_values

        out = _clean_values(
            {"hair_style": "long"}, "X", {"x"}, ["nothing relevant here"]
        )
        assert out == {"hair_style": "long"}

    def test_prompt_separates_standing_identity_from_transient_state(self) -> None:
        """Measured on RI ch1 (Fang Yuan's death scene): without this, the
        extractor returned typical_attire="deep green robes that had been
        torn to shreds" and features "covered in blood" -- which, baked into
        a reference sheet, redraws him bloodied for all 199 chapters."""
        prompt = build_prompt("Fang Yuan", ["He bled."])
        assert "not \"torn white robes\"" in prompt
        assert "Never injuries, blood" in prompt

    def test_prompt_warns_off_describing_bystanders(self) -> None:
        """Real RI ch1 output attributed a neighbour's build to Fang Yuan
        until the prompt said not to."""
        prompt = build_prompt("Fang Yuan", ["He stood there."])
        assert "describes someone else, even if they are compared" in prompt


class TestExtractAppearance:
    def test_writes_inferred_attributes_under_the_persona(self, tmp_path) -> None:
        from echotales.pipeline.resolve.appearance_extract import extract_appearance

        store = _store(tmp_path)
        client = _FakeClient(
            AppearanceResponse(
                hair_color=AttributeClaim(
                    value="black", source="Fang Yuan had black hair and wore green robes."
                ),
                typical_attire=AttributeClaim(
                    value="green robes",
                    source="Fang Yuan had black hair and wore green robes.",
                ),
            )
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
        client = _FakeClient(
            AppearanceResponse(
                hair_color=AttributeClaim(value="black", source="Fang Yuan had black hair")
            )
        )
        extract_appearance("t", store, client=client)
        again = extract_appearance("t", store, client=client)

        assert again.attributes_written == 0
        assert again.attributes_already_known == 1

    def test_a_failing_call_does_not_sink_the_stage(self, tmp_path) -> None:
        from echotales.pipeline.resolve.appearance_extract import extract_appearance

        class Boom:
            def complete(self, *a, **k):
                raise RuntimeError("model down")

        report = extract_appearance("t", _store(tmp_path), client=Boom())
        assert report.failures == 1
        assert report.attributes_written == 0


class TestPositionScopedAppearance:
    def test_a_later_attribute_does_not_leak_into_an_earlier_panel(self, tmp_path) -> None:
        """Fix 3: a chapter 5 panel must not see a scar the text only
        reveals at chapter 100 -- temporal leakage from a flat, unscoped
        read of the attribute history."""
        from echotales.pipeline.persona.reference_gen import appearance_of

        store = _store(tmp_path)
        store.add_attribute(
            "t",
            Attribute(
                target_kind=TargetKind.PERSONA,
                target_id="t:self1:body1",
                key="hair_color",
                value="black",
                interval=FuzzyInterval.open_ended(1.0, last_evidence=1.0),
                learned_at_pos=DiscoursePosition(chapter=1.0, offset=0),
                observer_id="READER",
            ),
        )
        store.add_attribute(
            "t",
            Attribute(
                target_kind=TargetKind.PERSONA,
                target_id="t:self1:body1",
                key="distinguishing_features",
                value="long scar",
                interval=FuzzyInterval.open_ended(100.0, last_evidence=100.0),
                learned_at_pos=DiscoursePosition(chapter=100.0, offset=0),
                observer_id="READER",
            ),
        )
        store.conn.commit()

        early = appearance_of(store, "t:self1:body1", position=5.0)
        late = appearance_of(store, "t:self1:body1", position=150.0)
        unscoped = appearance_of(store, "t:self1:body1")

        assert early == {"hair_color": "black"}
        assert late == {"hair_color": "black", "distinguishing_features": "long scar"}
        assert unscoped == late


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
        assert "xianxia" in prompt and "chinese ink painting" in prompt
        # Danbooru tag, not the English word: anime checkpoints weight it far
        # more strongly, and it is what decides the figure's sex. Without it
        # Fang Yuan generated as a woman on the first real run.
        assert prompt.startswith("1boy")

    def test_a_full_sheet_still_carries_its_style(self) -> None:
        """Measured bug: a detailed appearance clause alone runs to ~65 of
        CLIP's 77 tokens, and appending the style string after it meant the
        style -- three-quarter framing, ink-painting medium -- never reached
        the model. It has to survive alongside a real, long appearance."""
        from echotales.pipeline.persona.prompt import count_tokens
        from echotales.pipeline.persona.reference_gen import build_reference_prompt

        appearance = {
            "height_build": "tall and lean, gaunt with age and injury",
            "hair_color": "midnight black",
            "hair_style": "very long straight hair down to the waist",
            "eye_color": "jet black, cold and narrow",
            "skin_tone": "pale",
            "distinguishing_features": "cold expressionless stare, ruthless demeanour",
            "typical_attire": "simple robes with wide sleeves",
        }
        prompt = build_reference_prompt(
            "Fang Yuan", appearance, gender="male", age_band="adult", detailed=True
        )
        assert count_tokens(prompt) <= 77
        assert "three-quarter" in prompt
        assert "chinese ink painting" in prompt
        # And the identifying attribute must not have been the casualty.
        assert "midnight black" in prompt

    def test_generation_is_cached_on_the_appearance_digest(self, tmp_path) -> None:
        """Regenerating every principal on every run is not viable; only an
        appearance change should invalidate a sheet."""
        from echotales.pipeline.persona.reference_gen import generate_references
        from echotales.pipeline.render.panels import get_engine
        from echotales.pipeline.resolve.appearance_extract import extract_appearance

        store = _store(tmp_path)
        extract_appearance(
            "t",
            store,
            client=_FakeClient(
                AppearanceResponse(
                    hair_color=AttributeClaim(
                        value="black", source="Fang Yuan had black hair"
                    )
                )
            ),
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

        store = _store(
            tmp_path,
            narration_text="Fang Yuan, black-haired and injured, wore green robes.",
        )
        extract_appearance(
            "t",
            store,
            client=_FakeClient(
                AppearanceResponse(
                    hair_color=AttributeClaim(
                        value="black", source="Fang Yuan, black-haired and injured"
                    ),
                    current_condition=AttributeClaim(
                        value="injured", source="black-haired and injured"
                    ),
                )
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
