"""Visual genre profiles (persona/genre.py): an unlisted novel is no longer drawn as Reverend Insanity.

Before: every `attire.py` lookup fell back to RI's xianxia value for a novel it did not list, so ORV's panels kept
"hands concealed in long draping sleeves" and every new project was a Chinese cultivation novel. The three research
novels keep their tuned entries unchanged (checked on real chapters by diffing rendered prompts, 2026-10-18: RI and
LotM identical, ORV loses only the sleeve clause and the xianxia culture negative).
"""

from __future__ import annotations

import pytest

from echotales.core.enums import BlockType, SpanType
from echotales.core.models import Block, Chapter, Span
from echotales.core.store import Store
from echotales.pipeline.persona import attire, genre
from echotales.pipeline.persona.prompt import genre_mismatch_negative, negative_for
from echotales.pipeline.persona.reference_gen import build_reference_prompt, reference_negative


def _book(tmp_path, nid: str, text: str, genre_choice: str | None = None) -> Store:
    store = Store(str(tmp_path / f"{nid}.db"))
    store.add_novel(nid, nid, "x.epub", "generic")
    store.add_chapter(Chapter(novel_id=nid, number=1.0, title="T", source_href="1.html",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)]))
    store.add_spans([Span(id="s1", novel_id=nid, chapter=1.0, block_index=0, start=0, end=len(text),
                          span_type=SpanType.NARRATION_ACTION, text=text)])
    if genre_choice:
        store.set_visual_genre(nid, genre_choice)
    return store


@pytest.fixture(autouse=True)
def _project_genres():
    # A project's genre is stored or detected from its text; the tests stand in for that for the old test books.
    saved = dict(genre._PROJECT_GENRE)
    genre._PROJECT_GENRE.update({
        "reverend-insanity": "xianxia", "lord-of-the-mysteries": "victorian_gothic",
        "omniscient-readers-viewpoint": "modern_apocalypse",
    })
    yield
    genre._PROJECT_GENRE.clear()
    genre._PROJECT_GENRE.update(saved)


def test_an_unlisted_novel_is_not_drawn_as_xianxia(tmp_path) -> None:
    store = _book(tmp_path, "new-book", "She checked her phone on the subway while the monster scenario began.", "modern_apocalypse")
    assert genre.use_store_genre(store, "new-book") == "modern_apocalypse"
    assert "xianxia" not in attire.style_anchor("new-book") and "xianxia" not in attire.manga_base("new-book")
    assert "sleeve" not in attire.hands_default_clause("new-book")
    assert "Seoul" in attire.world_setting("new-book")
    assert "hanfu" not in build_reference_prompt("Dokja", {}, novel_id="new-book")
    # RI's "modern clothing, school uniform" negative is wrong here and must not be inherited.
    assert "modern clothing" not in negative_for("close_up", "new-book")
    assert "modern clothing" not in reference_negative("new-book")
    assert "hanfu" in genre_mismatch_negative("new-book", "a quiet street")


def test_a_stored_choice_wins_over_detection(tmp_path) -> None:
    store = _book(tmp_path, "b", "The knight rode to the castle and the dragon woke.", "science_fiction")
    assert genre.use_store_genre(store, "b") == "science_fiction"
    store.set_visual_genre("b", None)
    assert genre.use_store_genre(store, "b") == "western_fantasy"  # cleared: back to what the words say


def test_detection_reads_the_books_own_words(tmp_path) -> None:
    victorian = "The hansom cab rattled past the gaslight. The coachman tipped his hat to the inspector. " * 6
    assert genre.detect_genre(_book(tmp_path, "v", victorian), "v")[0] == "victorian_gothic"
    wuxia = "The sect elder taught the disciple to cultivate qi in the dantian. " * 6
    assert genre.detect_genre(_book(tmp_path, "x", wuxia), "x")[0] == "xianxia"
    assert genre.detect_genre(_book(tmp_path, "n", "He went home."), "n")[0] == "generic"


def test_re_adding_a_novel_keeps_its_chosen_genre(tmp_path) -> None:
    store = _book(tmp_path, "keep", "x", "western_fantasy")
    store.add_novel("keep", "Renamed", "", "generic")  # re-ingest
    assert store.get_novel("keep")["visual_genre"] == "western_fantasy"


def test_the_reference_negative_follows_a_genre_change_without_a_restart(tmp_path) -> None:
    # Cached on the novel id it kept the first genre's culture line until the server restarted (code review).
    store = _book(tmp_path, "switch", "x", "xianxia")
    genre.use_store_genre(store, "switch")
    assert "school uniform" in reference_negative("switch")
    store.set_visual_genre("switch", "modern_apocalypse")
    genre.use_store_genre(store, "switch")
    assert "school uniform" not in reference_negative("switch") and "xianxia" in reference_negative("switch")


def test_every_profiles_culture_negative_survives_the_reference_budget() -> None:
    # A part that does not fit the 77-token negative is dropped whole by `fit_to_budget`: ORV's first draft of its
    # culture line (17 tokens) was silently absent from every reference sheet.
    for name, prof in genre.GENRES.items():
        if not prof.negative_culture:
            continue
        genre._PROJECT_GENRE["probe"] = name
        try:
            first = prof.negative_culture.split(",")[0].strip()
            assert first in reference_negative("probe"), name
        finally:
            genre._PROJECT_GENRE.pop("probe", None)


def test_a_stage_can_check_only_the_models_it_uses() -> None:
    # `echotales render` was refused over llama3:latest (segmentation, sentiment) though it only calls the panel director.
    from echotales.pipeline.llm.tasks import Task, models_required

    assert models_required("ollama", {Task.PANEL_DIRECTION}) == {"gemma2:9b"}
    assert "gemma2:9b" in models_required("ollama") and "llama3:latest" not in models_required("ollama")


# --- the setting survives the prompt budget (LotM render review, 2026-10-18) --------------------------------------


def _direction(novel_id: str):
    from echotales.pipeline.render.direction import Direction, PanelDirection

    d = PanelDirection(
        shot="medium", action="sitting_up_in_bed, hand_on_head", layout="Zhou Mingrui, solo",
        setting="small_room, low_wooden_bed, brown_door, cabinet", lighting="midnight, candlelight",
        key_objects=["revolver"], mood="anxious", expression="pained_expression",
    )
    look = "short brown hair, grey eyes, youth, slender build, pale skin, wearing a black tailored coat and cravat"
    return Direction(direction=d, cast={"Zhou Mingrui": look}, novel_style="x", novel_id=novel_id)


def test_a_victorian_prompt_keeps_the_room_the_bed_and_the_revolver_and_no_duplicate_quality_tags() -> None:
    prompt = _direction("lord-of-the-mysteries").to_image_prompt()
    for wanted in ("low_wooden_bed", "revolver", "midnight"):
        assert wanted in prompt, prompt
    assert "score_9" not in prompt  # the engine prepends its own quality_prefix; the duplicate cost ~8 tokens
    assert prompt.index("revolver") < prompt.index("anxious")  # the beat's objects outrank the mood


def test_reverend_insanitys_tuned_order_is_untouched() -> None:
    parts = _direction("reverend-insanity").to_image_prompt_parts()
    assert "score_9, score_8_up, highly detailed, cinematic lighting" in parts  # tier 2 as tuned
    assert parts.index("anxious mood") < parts.index("small_room, low_wooden_bed, brown_door, cabinet")  # place last
    assert parts == _direction("").to_image_prompt_parts()  # no novel in hand keeps the xianxia vocabulary


def test_the_directors_instructions_no_longer_hand_it_a_lighting_or_place_to_copy() -> None:
    from echotales.pipeline.render.direction import build_prompt

    prompt = build_prompt("He woke.", cast={}, novel_style="x")
    assert "day, bright_sunlight" not in prompt and "mountain_background" not in prompt
    assert "do not guess daylight" in prompt and "never reuse wording from these instructions" in prompt


def test_the_scene_setting_note_finds_the_room_and_the_hour_from_the_whole_scene() -> None:
    from echotales.pipeline.render.direction import scene_setting_note

    scene = [
        "Why would I suddenly have such an excruciating headache in the middle of the night?",
        "He frowned and rubbed his temples.",
        "The room was not very large, with a brown door on each side of the room. Close to an opposite wall was a low wooden bed.",
        "Between the bed and the left door was a cabinet.",
    ]
    note = scene_setting_note(scene)
    assert "low wooden bed" in note and "cabinet" in note and "middle of the night" in note
    assert "rubbed his temples" not in note  # no place or time word: left out
    assert scene_setting_note(["He nodded.", "She left."]) == ""
    assert len(scene_setting_note(scene * 20, max_chars=200)) <= 200


def test_a_wooden_bed_is_a_bedroom_not_a_forest_for_the_non_xianxia_books() -> None:
    # "wood" counted inside "wooden" filed a night-time bedroom under a forest and put a moonlit moor on every panel.
    text = "Why would I have a headache in the middle of the night? The room was small, with a low wooden bed and a cabinet."
    assert attire.scene_locale("lord-of-the-mysteries", text) == "a modest Victorian bedroom, lamplight"
    assert "bedroom" in attire.scene_locale("omniscient-readers-viewpoint", text)
    # Whole words still match with a plural, and a real forest is still a forest.
    assert "wood" in attire.scene_locale("lord-of-the-mysteries", "He crossed the woods at dawn. The trees were bare.")


def test_reverend_insanitys_locale_matching_keeps_its_tuned_substring_count() -> None:
    assert "bamboo grove" in attire.scene_locale("reverend-insanity", "He walked into the bamboo forest under the trees.")
    # No bedroom key in RI's table: the new bedroom cues are skipped, never a KeyError.
    assert attire.scene_locale("reverend-insanity", "She slept in the bedroom on the bed.")


def test_a_scene_with_no_place_cue_inherits_the_chapters_place_and_a_bed_outweighs_wood() -> None:
    chapter = ("Why would I have a headache in the middle of the night? The room was small, with a low wooden bed. "
               "He touched the wood of the cabinet.")
    assert attire.scene_locale("lord-of-the-mysteries", chapter, strict=True) == "a modest Victorian bedroom, lamplight"
    assert attire.scene_locale("lord-of-the-mysteries", "He groaned and shut his eyes.", strict=True) == ""
    # "inside" is in every interior and every thought, and says nothing about where.
    assert attire.scene_locale("lord-of-the-mysteries", "Something moved inside his head.", strict=True) == ""


def test_one_ambiguous_word_is_not_evidence_of_a_place() -> None:
    # "a throbbing pain in his temples" is a body part; it filed LotM's first scene under a temple hall (a study).
    assert attire.scene_locale("lord-of-the-mysteries", "He felt a throbbing pain in his temples.", strict=True) == ""
    assert "bedroom" in attire.scene_locale("lord-of-the-mysteries", "He lay on the bed, pain in his temples.", strict=True)
    # RI keeps its substring count: a single "temple" there is still a hall.
    assert attire.scene_locale("reverend-insanity", "They walked to the ancestral temple.", strict=True)


def test_the_wood_of_a_table_is_not_a_forest() -> None:
    desk = "The wood of the desk was cold, and his pen was a thin piece of wood."
    assert attire.scene_locale("lord-of-the-mysteries", desk, strict=True) == ""
    assert "wood" in attire.scene_locale("lord-of-the-mysteries", "He crossed the woods under the trees.", strict=True)
