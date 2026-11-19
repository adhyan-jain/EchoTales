"""The spoiler-safe companion: cards, relationships, timeline and glossary as a reader "through chapter N" knows them.

Built on the three-chapter book of `test_reader_cast.py` (the masked guest is named in chapter 3, Corin first appears
in chapter 3), plus a relation and a place that only chapter 3 introduces. The faithfulness test is the same
definition: the companion served at chapter k from the full book equals the companion of a book truncated at k.
"""

from __future__ import annotations

import json

import pytest
from echotales.core.enums import OBSERVER_READER, AliasType, ReferenceMode, SpanType, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import DiscoursePosition, Mention, Relation, Self
from echotales.pipeline.companion import build_companion, write_companion_site
from test_reader_cast import _book

OPEN = FuzzyInterval.open_ended(0.0)


def _book_with_extras(tmp_path, upto: int, tag: str):
    store = _book(tmp_path, upto, tag)
    store.add_relation("t", Relation(src_self="t:mira", dst_self="t:guest", type="acquaintance", interval=OPEN,
                                     learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER,
                                     evidence="a sentence from the book that must never ship"))
    if upto >= 3:
        store.add_relation("t", Relation(src_self="t:mira", dst_self="t:corin", type="betrothed", interval=OPEN,
                                         learned_at_pos=DiscoursePosition(chapter=3), observer_id=OBSERVER_READER))
        store.add_self(Self(id="t:keep", novel_id="t", canonical_label="Hollow Keep", kind=TargetKind.LOCATION,
                            first_attested_pos=DiscoursePosition(chapter=3, offset=0)))
        store.add_mentions([Mention(id="mk", novel_id="t", segment_id="s", chapter=3.0, offset=80, block_index=0,
                                    text="Hollow Keep", alias_type=AliasType.RIGID_NAME,
                                    span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT,
                                    target_kind=TargetKind.LOCATION, target_id="t:keep")])
    store.conn.commit()
    return store


def _flat(obj) -> str:
    return json.dumps(obj, sort_keys=True)


def test_cards_relationships_timeline_and_glossary_are_filled(tmp_path) -> None:
    data = build_companion(_book_with_extras(tmp_path, 3, "full"), "t", 3)
    cards = {c["id"]: c for c in data["cards"]}
    assert cards["t:guest"]["label"] == "Arthur Vane" and cards["t:guest"]["first_chapter"] == 1
    assert {r["type"] for r in data["relationships"]} == {"acquaintance", "betrothed"}
    assert [g["term"] for g in data["glossary"]] == ["Hollow Keep"]
    assert any(e["chapter"] == 3 and "Corin" in e["text"] for e in data["timeline"])


def test_a_fact_from_after_chapter_n_is_absent_everywhere(tmp_path, ) -> None:
    store = _book_with_extras(tmp_path, 3, "full")
    data = build_companion(store, "t", 2)
    text = _flat(data)
    for later in ("Arthur Vane", "Corin", "betrothed", "Hollow Keep", "t:corin", "t:keep"):
        assert later not in text, later
    assert [c["id"] for c in data["cards"]] == ["t:guest", "t:mira"] or {c["id"] for c in data["cards"]} == {"t:guest", "t:mira"}
    assert data["glossary"] == []
    assert max(e["chapter"] for e in data["timeline"]) <= 2


def test_a_relation_is_filtered_by_when_the_reader_learned_it_not_by_the_chapter_it_describes(tmp_path) -> None:
    data = build_companion(_book_with_extras(tmp_path, 3, "full"), "t", 2)
    assert [r["type"] for r in data["relationships"]] == ["acquaintance"]


def test_no_book_text_is_carried_the_relation_evidence_stays_out(tmp_path) -> None:
    data = build_companion(_book_with_extras(tmp_path, 3, "full"), "t", 3)
    assert "must never ship" not in _flat(data)
    assert "masked guest bowed" not in _flat(data)


@pytest.mark.parametrize("k", [1, 2, 3])
def test_the_companion_equals_the_companion_of_a_book_truncated_at_that_chapter(tmp_path, k: int) -> None:
    def strip(d):
        # Colours are a whole-volume ranking kept stable across positions; they are not content.
        return json.loads(_flat({**d, "cards": [{f: v for f, v in c.items() if f != "colour"} for c in d["cards"]]}))

    full = build_companion(_book_with_extras(tmp_path, 3, f"full{k}"), "t", k)
    cut = build_companion(_book_with_extras(tmp_path, k, f"cut{k}"), "t", k)
    assert strip(full) == strip(cut)


def test_the_static_site_is_plain_files_with_the_data_inline(tmp_path) -> None:
    data = build_companion(_book_with_extras(tmp_path, 3, "full"), "t", 2)
    out = tmp_path / "site"
    write_companion_site(data, out)
    assert {p.name for p in out.iterdir()} == {"index.html", "style.css", "companion.json"}
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "The masked guest" in html and "Mira" in html
    # Works from file:// with no server and no network: nothing is fetched or loaded from elsewhere.
    for needle in ("http://", "https://", "fetch(", "<script src"):
        assert needle not in html
    assert json.loads((out / "companion.json").read_text(encoding="utf-8"))["through"] == 2
    for later in ("Arthur Vane", "Corin", "Hollow Keep"):
        assert later not in html and later not in (out / "companion.json").read_text(encoding="utf-8")


def test_names_are_escaped_in_the_page(tmp_path) -> None:
    data = build_companion(_book_with_extras(tmp_path, 3, "full"), "t", 2)
    data["cards"][0]["label"] = "<script>alert(1)</script>"
    out = tmp_path / "site"
    write_companion_site(data, out)
    assert "<script>alert(1)" not in (out / "index.html").read_text(encoding="utf-8")


def test_the_cli_builds_the_site_through_a_chapter(tmp_path) -> None:
    from echotales.pipeline.cli import main

    store = _book_with_extras(tmp_path, 3, "cli")
    out = tmp_path / "site"
    assert main(["--db", store.path, "export", "companion", "--novel", "t", "--through", "2", "--out", str(out)]) == 0
    assert "Corin" not in (out / "index.html").read_text(encoding="utf-8")


def test_the_cli_refuses_a_companion_without_a_reading_position(tmp_path) -> None:
    from echotales.pipeline.cli import main

    store = _book_with_extras(tmp_path, 3, "cli2")
    assert main(["--db", store.path, "export", "companion", "--novel", "t", "--out", str(tmp_path / "x")]) == 2
