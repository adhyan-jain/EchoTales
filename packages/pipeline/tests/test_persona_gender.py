"""Gender for characters whose pronoun count could not call it (casting audit 2026-11-19).

Measured on the RI/LotM databases: 65 of 98 RI persons (20 of 44 speaking characters, among them Fang Yuan with 902
lines) and 3 of 17 LotM speakers were `unknown`, so voice casting offered both genders and gave a man a female voice.
Two causes are pinned here: the model's "unknown" overwrote a pronoun-derived gender, and nothing re-read the text
for characters the pronoun rule left open.
"""

from __future__ import annotations

from types import SimpleNamespace

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.store import Store
from echotales.pipeline.persona.gender import GenderResponse, infer_missing_genders
from echotales.pipeline.persona.traits import TraitProfile


class ScriptedClient:
    """Answers the gender question from a callback and records every prompt."""

    def __init__(self, answer=None) -> None:
        self.answer = answer or (lambda prompt: {})
        self.prompts: list[str] = []

    def complete(self, task, prompt, schema, *, system="", novel_id=""):
        self.prompts.append(prompt)
        return SimpleNamespace(value=schema.model_validate(self.answer(prompt)))


def _novel(tmp_path, text: str, *, label: str = "Fang Yuan", surface: str | None = None, repeats: int = 4, personas: bool = True):
    """One entity named `repeats` times, once per paragraph, in one chapter."""
    surface = surface or label
    paragraphs = [text] * repeats
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t", number=1.0, title="T", source_href="a.html",
            blocks=[Block(index=i, block_type=BlockType.PROSE, text=p) for i, p in enumerate(paragraphs)],
        )
    )
    store.add_spans(
        [
            Span(
                id=f"t:1:{i}:0", novel_id="t", chapter=1.0, block_index=i, start=0, end=len(p),
                span_type=SpanType.NARRATION_ACTION, text=p,
            )
            for i, p in enumerate(paragraphs)
        ]
    )
    store.add_self(
        Self(
            id="t:self1", novel_id="t", canonical_label=label, kind=TargetKind.SELF,
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
        )
    )
    store.add_mentions(
        [
            Mention(
                id=f"m{i}", novel_id="t", segment_id="s", chapter=1.0, offset=p.index(surface), block_index=i,
                text=surface, alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id="t:self1",
            )
            for i, p in enumerate(paragraphs)
        ]
    )
    store.conn.commit()
    from echotales.pipeline.persona import build_personas

    if personas:
        build_personas("t", store)
    return store


def _gender(store: Store) -> str:
    from echotales.pipeline.persona import load_trait_profiles

    return load_trait_profiles("t", store)["t:self1"].gender


class TestTitleCue:
    def test_title_before_every_mention_decides_without_the_model(self, tmp_path) -> None:
        store = _novel(tmp_path, "Mr. Darcy walked on.", label="Darcy", surface="Darcy")
        client = ScriptedClient()
        report = infer_missing_genders("t", store, client)
        assert _gender(store) == "male"
        assert client.prompts == []
        assert report.by_cue == 1

    def test_female_title(self, tmp_path) -> None:
        store = _novel(tmp_path, "Miss Bingley smiled at the room.", label="Bingley", surface="Bingley")
        infer_missing_genders("t", store, ScriptedClient())
        assert _gender(store) == "female"

    def test_lord_is_not_a_gender_cue(self, tmp_path) -> None:
        """RI: 'Lord Yao Ji' is an old woman and 'Lord Qing Shu' a man; translated xianxia uses it for both."""
        store = _novel(tmp_path, "Lord Yao Ji raised her bid.", label="Yao Ji", surface="Yao Ji")
        report = infer_missing_genders("t", store, ScriptedClient())
        assert report.by_cue == 0

    def test_conflicting_titles_defer_to_the_model(self, tmp_path) -> None:
        """'Mr. Bennet' and 'Mrs. Bennet' can share one entity when the family name is the only surface."""
        store = _novel(tmp_path, "Mr. Bennet spoke.", label="Bennet", surface="Bennet", repeats=2)
        store.add_mentions(
            [
                Mention(
                    id="mx", novel_id="t", segment_id="s", chapter=1.0, offset=0, block_index=0, text="Mrs. Bennet",
                    alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                    reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id="t:self1",
                )
            ]
        )
        client = ScriptedClient()
        infer_missing_genders("t", store, client)
        assert _gender(store) == "unknown"
        assert client.prompts, "a title conflict must be put to the model, not decided by regex"

    def test_a_single_title_is_not_enough(self, tmp_path) -> None:
        store = _novel(tmp_path, "Mr. Klein looked up.", label="Klein", surface="Klein", repeats=1)
        infer_missing_genders("t", store, ScriptedClient(), min_mentions=1)
        assert _gender(store) == "unknown"


TEXT = "Fang Yuan looked at the sky. He did not smile."


class TestModelReading:
    def test_verbatim_evidence_is_accepted_and_stored(self, tmp_path) -> None:
        store = _novel(tmp_path, TEXT)
        client = ScriptedClient(lambda p: {"gender": "male", "quote": "He did not smile", "confident": True})
        report = infer_missing_genders("t", store, client)
        assert _gender(store) == "male"
        assert report.by_model == 1
        rows = [
            a for a in store.get_attributes(TargetKind.PERSONA, "t:self1:body1") if a.key == "gender"
        ]
        assert any("He did not smile" in a.evidence and a.value == "male" for a in rows)

    def test_prompt_names_the_character_and_shows_name_anchored_text(self, tmp_path) -> None:
        store = _novel(tmp_path, TEXT)
        client = ScriptedClient()
        infer_missing_genders("t", store, client)
        assert "Fang Yuan" in client.prompts[0]
        assert "looked at the sky" in client.prompts[0]

    def test_quote_not_in_the_text_is_rejected(self, tmp_path) -> None:
        store = _novel(tmp_path, TEXT)
        client = ScriptedClient(lambda p: {"gender": "male", "quote": "He drew his sword", "confident": True})
        report = infer_missing_genders("t", store, client)
        assert _gender(store) == "unknown"
        assert report.rejected_quote == 1

    def test_a_hedging_answer_is_rejected(self, tmp_path) -> None:
        store = _novel(tmp_path, TEXT)
        client = ScriptedClient(lambda p: {"gender": "male", "quote": "He did not smile", "confident": False})
        report = infer_missing_genders("t", store, client)
        assert _gender(store) == "unknown"
        assert report.rejected_hedged == 1

    def test_quote_that_supports_the_other_gender_is_rejected(self, tmp_path) -> None:
        store = _novel(tmp_path, TEXT)
        client = ScriptedClient(lambda p: {"gender": "female", "quote": "He did not smile", "confident": True})
        infer_missing_genders("t", store, client)
        assert _gender(store) == "unknown"

    def test_quote_with_no_gendered_word_is_rejected(self, tmp_path) -> None:
        store = _novel(tmp_path, TEXT)
        client = ScriptedClient(lambda p: {"gender": "male", "quote": "looked at the sky", "confident": True})
        infer_missing_genders("t", store, client)
        assert _gender(store) == "unknown"

    def test_unknown_answer_stays_unknown(self, tmp_path) -> None:
        store = _novel(tmp_path, TEXT)
        infer_missing_genders("t", store, ScriptedClient(lambda p: {"gender": "unknown"}))
        assert _gender(store) == "unknown"

    def test_stub_backend_declines_and_is_deterministic(self, tmp_path) -> None:
        """`ECHOTALES_LLM_MODE=stub` answers the schema's defaults; the pass must read that as 'no evidence'."""
        store = _novel(tmp_path, TEXT)
        report = infer_missing_genders("t", store, ScriptedClient())
        assert _gender(store) == "unknown"
        assert report.by_model == 0

    def test_no_gendered_word_near_the_name_skips_the_model_call(self, tmp_path) -> None:
        store = _novel(tmp_path, "Fang Yuan looked at the sky.")
        client = ScriptedClient()
        report = infer_missing_genders("t", store, client)
        assert client.prompts == []
        assert report.no_evidence == 1

    def test_known_gender_is_never_re_asked(self, tmp_path) -> None:
        text = "Fang Yuan rose. He left, and his steps were slow. He did not look back, nor did he speak."
        store = _novel(tmp_path, text)
        assert _gender(store) == "male"
        client = ScriptedClient()
        report = infer_missing_genders("t", store, client)
        assert client.prompts == []
        assert report.skipped_known == 1

    def test_character_without_a_persona_is_skipped_not_written(self, tmp_path) -> None:
        """ORV's database had no personas: a gender row on a body that does not exist is read by nothing."""
        store = _novel(tmp_path, TEXT, personas=False)
        client = ScriptedClient(lambda p: {"gender": "male", "quote": "He did not smile", "confident": True})
        report = infer_missing_genders("t", store, client)
        assert client.prompts == []
        assert report.no_persona == 1

    def test_too_few_mentions_and_no_lines_is_left_alone(self, tmp_path) -> None:
        store = _novel(tmp_path, TEXT, repeats=2)
        client = ScriptedClient()
        infer_missing_genders("t", store, client, min_mentions=3)
        assert client.prompts == []


def test_response_defaults_mean_no_answer() -> None:
    r = GenderResponse()
    assert (r.gender, r.quote, r.confident) == ("unknown", "", False)


def test_reader_gender_check_reads_past_a_superseded_unknown_row():
    # The gender pass supersedes the old "unknown" row instead of retracting it; the reader's conflict check
    # must see the grounded value, not the first row.
    from echotales.pipeline.reader.facts_pass import _recorded_gender

    rows = [SimpleNamespace(key="gender", value="unknown"), SimpleNamespace(key="gender", value="male")]
    store = SimpleNamespace(get_attributes=lambda target, tid: rows if tid == "s1" else [])
    assert _recorded_gender(store, "s1") == "male"
    assert _recorded_gender(SimpleNamespace(get_attributes=lambda t, i: [rows[0]]), "s1") == ""
