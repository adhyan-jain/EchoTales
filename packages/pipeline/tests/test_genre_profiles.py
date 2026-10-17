"""Visual genre profiles (persona/genre.py): an unlisted novel is no longer drawn as Reverend Insanity.

Before: every `attire.py` lookup fell back to RI's xianxia value for a novel it did not list, so ORV's panels kept
"hands concealed in long draping sleeves" and every new project was a Chinese cultivation novel. The three research
novels keep their tuned entries unchanged (checked on real chapters by diffing rendered prompts, 2026-10-18: RI and
LotM identical, ORV loses only the sleeve clause and the xianxia culture negative).
"""

from __future__ import annotations

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


def test_the_research_novels_keep_their_tuned_entries() -> None:
    assert attire.style_anchor("reverend-insanity") == attire.STYLE_ANCHOR_BY_NOVEL["reverend-insanity"]
    assert attire.manga_base("lord-of-the-mysteries") == attire.MANGA_BASE_BY_NOVEL["lord-of-the-mysteries"]
    assert genre.genre_of("omniscient-readers-viewpoint") == "modern_apocalypse"
    assert "sleeve" in attire.hands_default_clause("reverend-insanity")
    # No novel in hand (`novel_id=""`) keeps the vocabulary every such caller always got.
    assert "xianxia" in attire.style_anchor("")


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
