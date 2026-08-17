"""Fandom-wiki appearance import (`persona/wiki_canon.py`)."""

from __future__ import annotations

from pathlib import Path

from echotales.pipeline.persona.wiki_canon import (
    appearance_text,
    build_wiki_canon,
    load_wiki_canon,
    parse_appearance,
    save_wiki_canon,
)

PAGE = """
{{Infobox character|name=Fang Yuan}}
'''Fang Yuan''' is the protagonist.

== Appearance ==
Fang Yuan is a tall and lean man standing at 188 cm. He has [[midnight black]] hair
worn as waist-length straight hair, and jet-black eyes that are cold and narrow.
His skin is pale. He is usually seen in green robes.

=== After the rebirth ===
In his fifteen-year-old body he is noticeably shorter.

== History ==
In chapter 500 he kills the [[Spectral Soul Demon Venerable]] and becomes
the ruler of the world, after betraying Bai Ning Bing.

== Relationships ==
Fang Zheng is his rival.
"""


def test_only_appearance_sections_are_read() -> None:
    text = appearance_text(PAGE)
    assert "waist-length" in text
    assert "fifteen-year-old" in text  # a sub-heading of Appearance
    # The spoiler sections are never parsed at all.
    assert "Demon Venerable" not in text
    assert "betraying" not in text
    assert "rival" not in text


def test_markup_is_stripped() -> None:
    text = appearance_text(PAGE)
    assert "[[" not in text and "{{" not in text
    assert "midnight black" in text


def test_traits_are_typed_into_appearance_keys() -> None:
    traits = parse_appearance(appearance_text(PAGE))
    assert traits["hair_color"] == "midnight black"
    assert traits["hair_style"] == "waist-length"
    assert traits["eye_color"] == "jet-black"
    assert traits["skin_tone"] == "pale"
    assert traits["height_build"] == "188 cm"
    assert traits["typical_attire"] == "green robes"


def test_a_page_without_an_appearance_section_falls_back_to_the_lead() -> None:
    # Most character pages have no Appearance section; the lead paragraph
    # is where the description lives. Text under History is still ignored.
    page = "He is a young man with black hair.\n== History ==\nHe has white hair now."
    assert parse_appearance(appearance_text(page))["hair_color"] == "black"


def test_an_empty_page_yields_nothing() -> None:
    assert parse_appearance(appearance_text("")) == {}


def test_late_story_bodies_do_not_overwrite_the_early_one() -> None:
    """A long appearance section is a chronology; only its opening applies.

    Fang Yuan's real page runs 6,700 characters and describes a stolen
    immortal body and a six-metre zombie form thousands of chapters after
    the part being adapted.
    """
    page = (
        "== Appearance ==\n"
        "He has short hair and wears green robes.\n" + ("filler text. " * 200) +
        "\nMuch later he has waist-length hair and wears white robes."
    )
    traits = parse_appearance(appearance_text(page))
    assert traits["hair_style"] == "short"
    assert traits["typical_attire"] == "green robes"


def test_non_colour_words_are_not_hair_colours() -> None:
    assert "hair_color" not in parse_appearance("Her hair is shiny and moves well.")


def test_transient_condition_is_never_imported() -> None:
    page = "== Appearance ==\nHe is gravely wounded, his robes torn to shreds."
    assert "current_condition" not in parse_appearance(appearance_text(page))


def test_build_reports_and_round_trips_through_disk(tmp_path: Path) -> None:
    def fake_fetch(wiki: str, title: str) -> str | None:
        assert wiki == "reverend-insanity"
        return PAGE if title == "Fang Yuan" else None

    report = build_wiki_canon(
        "reverend-insanity", ["Fang Yuan", "Nobody At All"], fetch=fake_fetch
    )
    assert report.requested == 2
    assert report.with_appearance == 1
    assert report.entries["Fang Yuan"]["hair_color"] == "midnight black"

    save_wiki_canon(report, data_root=tmp_path)
    assert load_wiki_canon("reverend-insanity", data_root=tmp_path) == report.entries


def test_unknown_novel_has_no_wiki_and_does_not_fetch() -> None:
    def explode(wiki: str, title: str) -> str | None:  # pragma: no cover
        raise AssertionError("must not fetch for a novel with no wiki")

    report = build_wiki_canon("some-other-novel", ["Someone"], fetch=explode)
    assert report.entries == {}


def test_missing_cache_is_not_an_error(tmp_path: Path) -> None:
    assert load_wiki_canon("reverend-insanity", data_root=tmp_path) == {}


def test_hand_authored_canon_outranks_the_wiki(tmp_path: Path, monkeypatch) -> None:
    from echotales.pipeline.persona import canon as canon_mod

    monkeypatch.setattr(
        canon_mod,
        "CANON_APPEARANCE",
        {"reverend-insanity": {"Fang Yuan": {"hair_color": "hand-typed black"}}},
    )
    monkeypatch.setattr(
        "echotales.pipeline.persona.wiki_canon.load_wiki_canon",
        lambda novel_id, **kw: {
            "Fang Yuan": {"hair_color": "wiki black", "skin_tone": "pale"}
        },
    )
    got = canon_mod.canon_for("reverend-insanity", "Fang Yuan")
    assert got["hair_color"] == "hand-typed black"
    # ...but the wiki still fills what the table does not mention.
    assert got["skin_tone"] == "pale"


def test_gu_pages_are_not_characters() -> None:
    from echotales.pipeline.persona.wiki_canon import is_character_page

    gu = (
        "{{Infobox Gu|path=Metal Path|Rank = Rank 1}}\n"
        "Iron Skin Gu emitted a black iron-like glow.\n"
        "[[Category:Gu]]\n[[Category:Rank 1 Gu]]"
    )
    assert not is_character_page(gu)


def test_person_categories_mark_a_character() -> None:
    from echotales.pipeline.persona.wiki_canon import is_character_page

    # RI tags its protagonist Human/Male with no Characters category.
    assert is_character_page("Fang Yuan.\n[[Category:Human]]\n[[Category:Male]]")
    assert is_character_page("{{Infobox_Character}}\n[[Category:Characters]]")
    # A bare stub is given the benefit of the doubt.
    assert is_character_page("A short page with nothing on it.")


def test_non_character_pages_are_counted_not_imported() -> None:
    def fake_fetch(wiki: str, title: str) -> str | None:
        return "{{Infobox Gu}}\nIt has bronze skin.\n[[Category:Gu]]"

    report = build_wiki_canon("reverend-insanity", ["Iron Skin Gu"], fetch=fake_fetch)
    assert report.entries == {}
    assert report.skipped_not_a_character == 1
