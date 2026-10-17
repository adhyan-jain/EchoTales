"""The Read page's cast as of a reading position (webview.py::build_reader_cast) and its API route.

A three-chapter book with an alias reveal: "the masked guest" (chapters 1-2) is revealed as Arthur Vane in chapter 3,
whose pronouns also arrive only then; Corin first appears in chapter 3. The whole-volume payload labels the guest
"Arthur Vane" everywhere and lists Corin from chapter 1 -- the spoiler the reader cast exists to remove. The
faithfulness test is the definition applied directly: the cast served at chapter k from the full book must equal the
cast a store truncated at k serves (colour excepted, which is a whole-volume ranking kept for stable highlights).
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest
from echotales.core.enums import (
    AliasType,
    AttributionMethod,
    BlockType,
    ReferenceMode,
    SpanType,
    TargetKind,
)
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.store import Store
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.persona import build_personas
from echotales.pipeline.webview import build_novel_payload, build_reader_cast
from echotales.pipeline.webview_server import Registry, make_handler

TEXT = {
    1: "The masked guest bowed to Mira.",
    2: "The masked guest watched Mira leave.",
    3: "Arthur Vane removed his mask. He smiled at Mira, and he told Corin his name. His voice was low. He sat.",
}
MENTIONS = [  # (chapter, offset, text, alias type, target)
    (1, 0, "The masked guest", AliasType.EPITHET, "t:guest"), (1, 26, "Mira", AliasType.RIGID_NAME, "t:mira"),
    (2, 0, "The masked guest", AliasType.EPITHET, "t:guest"), (2, 25, "Mira", AliasType.RIGID_NAME, "t:mira"),
    (3, 0, "Arthur Vane", AliasType.RIGID_NAME, "t:guest"), (3, 42, "Mira", AliasType.RIGID_NAME, "t:mira"),
    (3, 61, "Corin", AliasType.RIGID_NAME, "t:corin"),
]
LABELS = {"t:guest": "Arthur Vane", "t:mira": "Mira", "t:corin": "Corin"}
LINE = '"Good evening," said Arthur Vane.'


def _book(tmp_path, upto: int, tag: str) -> Store:
    store = Store(str(tmp_path / f"{tag}.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    for c in range(1, upto + 1):
        blocks = [Block(index=0, block_type=BlockType.PROSE, text=TEXT[c])]
        if c == 3:
            blocks.append(Block(index=1, block_type=BlockType.PROSE, text=LINE))
        store.add_chapter(Chapter(novel_id="t", number=float(c), title="T", source_href=f"{c}.html", blocks=blocks))
    first = {}
    for c, _o, _t, _a, tid in MENTIONS:
        first.setdefault(tid, c)
    for tid, label in LABELS.items():
        if first[tid] <= upto:
            store.add_self(Self(id=tid, novel_id="t", canonical_label=label,
                                first_attested_pos=DiscoursePosition(chapter=float(first[tid]), offset=0), kind=TargetKind.SELF))
    store.add_spans([Span(id=f"sp{c}", novel_id="t", chapter=float(c), block_index=0, start=0, end=len(TEXT[c]),
                          span_type=SpanType.NARRATION_ACTION, text=TEXT[c]) for c in range(1, upto + 1)])
    if upto >= 3:
        # The attribution ladder writes the speaker's *surface* here, not an entity id.
        store.add_spans([Span(id="sp3d", novel_id="t", chapter=3.0, block_index=1, start=0, end=len(LINE),
                              span_type=SpanType.DIALOGUE, text=LINE, speaker_self_id="Arthur Vane",
                              attribution_method=AttributionMethod.EXPLICIT)])
    store.add_mentions([
        Mention(id=f"m{i}", novel_id="t", segment_id="s", chapter=float(c), offset=o, block_index=0, text=t, alias_type=a,
                span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id=tid)
        for i, (c, o, t, a, tid) in enumerate(MENTIONS) if c <= upto
    ])
    store.conn.commit()
    build_personas("t", store, prefix_causal=True)
    return store


def _by_id(cast: dict) -> dict:
    return {e["id"]: e for e in cast["entities"]}


def test_whole_volume_payload_is_the_spoiler_this_replaces(tmp_path) -> None:
    payload = build_novel_payload(_book(tmp_path, 3, "full"), "t", "T")
    guest = next(e for e in payload["entities"] if e["id"] == "t:guest")
    assert guest["label"] == "Arthur Vane" and "Arthur Vane" in guest["aliases"]
    ch1_marks = [m for s in payload["chapters"][0]["spans"] for m in s["marks"]]
    assert {m["label"] for m in ch1_marks if m["id"] == "t:guest"} == {"Arthur Vane"}  # hovering chapter 1 names him


def test_reader_cast_before_the_reveal_knows_only_the_alias(tmp_path) -> None:
    cast = _by_id(build_reader_cast(_book(tmp_path, 3, "full"), "t", 2))
    assert set(cast) == {"t:guest", "t:mira"}  # Corin is not introduced yet
    guest = cast["t:guest"]
    assert guest["label"] == "The masked guest"
    assert guest["aliases"] == ["The masked guest"]
    assert guest["last_chapter"] == 2 and guest["count"] == 2
    assert guest["traits"].get("gender") == "unknown"  # his pronouns arrive in chapter 3
    assert guest["speaks"] is False


def test_reader_cast_after_the_reveal_uses_the_name(tmp_path) -> None:
    cast = _by_id(build_reader_cast(_book(tmp_path, 3, "full"), "t", 3))
    assert cast["t:guest"]["label"] == "Arthur Vane"
    assert cast["t:guest"]["traits"].get("gender") == "male"
    assert "t:corin" in cast


@pytest.mark.parametrize("k", [1, 2, 3])
def test_reader_cast_equals_the_cast_of_a_book_truncated_at_the_reading_position(tmp_path, k: int) -> None:
    def strip(cast):
        return {i: {f: v for f, v in e.items() if f != "colour"} for i, e in _by_id(cast).items()}

    assert strip(build_reader_cast(_book(tmp_path, 3, f"full{k}"), "t", k)) == strip(build_reader_cast(_book(tmp_path, k, f"k{k}"), "t", k))


def test_reader_route(tmp_path) -> None:
    db_path = _book(tmp_path, 3, "route").path
    registry = Registry([], corrections_dir=tmp_path / "corrections", projects_dir=tmp_path / "projects")

    class _Handle:
        # The real server serves from the thread that opened its stores; this test serves from a second thread, and
        # sqlite3 refuses a connection used outside the thread that created it, so open it where it is used.
        @property
        def store(self):
            return Store(db_path)

    registry.handles["t"] = _Handle()  # type: ignore[assignment]
    queue = JobQueue()
    queue.start()
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, queue))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        def get(path):
            conn = HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
            conn.request("GET", path)
            r = conn.getresponse()
            out = r.status, r.read()
            conn.close()
            return out

        status, body = get("/api/novels/t/reader?chapter=2")
        assert status == 200
        assert {e["label"] for e in json.loads(body)["entities"]} == {"The masked guest", "Mira"}
        assert get("/api/novels/t/reader?chapter=abc")[0] == 400
        assert get("/api/novels/t/reader?chapter=nan")[0] == 400  # int(nan) raised: a 500
        assert get("/api/novels/t/reader?chapter=inf")[0] == 400  # served the whole book as a reader's view
        assert get("/api/novels/nope/reader?chapter=1")[0] == 404
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_a_speaker_surface_is_joined_to_its_character(tmp_path) -> None:
    store = _book(tmp_path, 3, "speaker")
    payload = build_novel_payload(store, "t", "T")
    line = next(s for s in payload["chapters"][2]["spans"] if s["type"] == "DIALOGUE")
    assert line["speaker_id"] == "Arthur Vane" and line["speaker_entity_id"] == "t:guest"
    assert next(e for e in payload["entities"] if e["id"] == "t:guest")["speaks"] is True
    assert _by_id(build_reader_cast(store, "t", 3))["t:guest"]["speaks"] is True


def test_the_persona_stage_counts_a_characters_spoken_lines(tmp_path) -> None:
    from echotales.pipeline.persona.build import _gather_evidence

    dialogue, _narration, _surfaces, total = _gather_evidence(_book(tmp_path, 3, "evidence"), "t", "t:guest")
    assert total == 1 and dialogue == [LINE]  # was 0 for every character before the surface join


def test_label_keeps_the_canonical_name_across_article_possessive_and_plural() -> None:
    from echotales.pipeline.webview import _label_known_at

    assert _label_known_at("Magician", {"The Magician": 3}, {}) == "Magician"
    assert _label_known_at("Beyonder", {"Beyonders": 2}, {}) == "Beyonder"
    assert _label_known_at("Ellain Forest Vital Force", {"Ellain Forest's Vital Force": 1}, {}) == "Ellain Forest Vital Force"
    # A different name is still a reveal the reader has not reached.
    assert _label_known_at("Arthur Vane", {"The masked guest": 2}, {}) == "The masked guest"
