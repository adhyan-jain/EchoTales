"""The person who speaks a line is the one in the frame, first in CAST and the lead of the shot (P&P e2e 2026-11-22).

Mr. Bennet was drawn in nearly every panel, including "My dear Mr. Bennet" (said by his wife), and Mrs. Bennet in 6 of 32: the
cast came from PRESENT mentions, a line's speaker is not a mention, and a beat with no fresh PRESENT mention carried the previous
beat's cast forward (the one man). The graph already holds the speaker of every line (`Span.speaker_self_id`).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from echotales.core.enums import OBSERVER_READER, AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, NarrativeSegment, Self, Span
from echotales.core.store import Store
from echotales.pipeline.persona.split import BodyEpoch, write_epochs
from echotales.pipeline.render.direction import PanelDirection
from echotales.pipeline.render.panels import render_panels
from echotales.pipeline.render.plan import load_panel_plan

NOVEL = "pp"
MR, MRS = "pp:mr", "pp:mrs"
TEXTS = [
    (BlockType.HEADING, "Chapter 1"),
    (BlockType.PROSE, "Mr. Bennet sat in the library at Longbourn, reading by the window."),
    (BlockType.PROSE, '"My dear Mr. Bennet, have you heard that Netherfield Park is let at last?" said his wife.'),
    (BlockType.PROSE, '"I have not," said Mr. Bennet, without looking up.'),
    (BlockType.PROSE, '"But it is," she cried, "Mrs. Long has just been here and told me all about it."'),
    (BlockType.PROSE, '"Do you not want to know who has taken it?" said his wife impatiently.'),
]
#: block -> (start, end, speaker) of the quoted words
LINES = {2: (0, 74, MRS), 3: (0, 14, MR), 4: (0, 12, MRS), 5: (0, 44, MRS)}


def _store(path: Path) -> Store:
    store = Store(str(path))
    store.add_novel(NOVEL, "P", "x.epub", "generic")
    store.add_chapter(Chapter(novel_id=NOVEL, number=1.0, title="T", source_href="a.html",
                              blocks=[Block(index=i, block_type=bt, text=tx) for i, (bt, tx) in enumerate(TEXTS)]))
    for sid, label in ((MR, "Mr. Bennet"), (MRS, "Mrs. Bennet")):
        store.add_self(Self(id=sid, novel_id=NOVEL, canonical_label=label,
                            first_attested_pos=DiscoursePosition(chapter=1, offset=0), kind=TargetKind.SELF))
        write_epochs(store, NOVEL, store.get_self(sid),
                     [BodyEpoch(index=0, persona_id=f"{sid}:body1", body_label=label, from_pos=1.0, to_pos=None, cause="birth", evidence="")],
                     observer_id=OBSERVER_READER)
    # Only Mr. Bennet is ever PRESENT by mention; his wife speaks without a PRESENT mention (her tag is "his wife" / "she").
    mentions = [Mention(id="m1", novel_id=NOVEL, segment_id="s1", chapter=1.0, offset=0, block_index=1, text="Mr. Bennet",
                        alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT,
                        target_kind=TargetKind.SELF, target_id=MR),
                Mention(id="m2", novel_id=NOVEL, segment_id="s1", chapter=1.0, offset=8, block_index=2, text="Mr. Bennet",
                        alias_type=AliasType.RIGID_NAME, span_type=SpanType.DIALOGUE, reference_mode=ReferenceMode.DIALOGUE_REFERENCE,
                        target_kind=TargetKind.SELF, target_id=MR)]
    store.add_mentions(mentions)
    spans: list[Span] = []
    for i, (bt, tx) in enumerate(TEXTS):
        if bt is not BlockType.PROSE:
            continue
        if i in LINES:
            _s, _e, who = LINES[i]
            a, b = tx.index('"'), tx.rindex('"') + 1
            spans.append(Span(id=f"d{i}", novel_id=NOVEL, chapter=1.0, block_index=i, start=a, end=b, span_type=SpanType.DIALOGUE,
                              text=tx[a:b], speaker_self_id=who))
            if b < len(tx):
                spans.append(Span(id=f"n{i}", novel_id=NOVEL, chapter=1.0, block_index=i, start=b, end=len(tx),
                                  span_type=SpanType.NARRATION_ACTION, text=tx[b:]))
        else:
            spans.append(Span(id=f"n{i}", novel_id=NOVEL, chapter=1.0, block_index=i, start=0, end=len(tx),
                              span_type=SpanType.NARRATION_ACTION, text=tx))
    store.add_spans(spans)
    store.add_segments([NarrativeSegment(id="s1", novel_id=NOVEL, chapter_from=1.0, offset_from=0, chapter_to=1.0,
                                         offset_to=10**6, story_seq_from=1, story_seq_to=1)])
    store.conn.commit()
    return store


class _Director:
    """Records the CAST the director was handed for each panel; answers with a plain medium shot."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, task, prompt, schema, **kwargs):  # noqa: ANN001, ANN003, ANN201
        if schema is not PanelDirection:
            return SimpleNamespace(value=None)
        self.prompts.append(prompt)
        return SimpleNamespace(value=PanelDirection(shot="medium", action="talking in the library", setting="a library", lighting="day"))


def _render(tmp_path: Path):
    store = _store(tmp_path / "pp.db")
    director = _Director()
    render_panels(NOVEL, store, out_dir=tmp_path / "out", version="v1", max_panels=20, client=director)
    return load_panel_plan(tmp_path / "out" / "ch1" / "v1"), director


def _panel_over(rows, block: int):
    return next(r for r in rows if block in r.block_indexes)


def test_the_speaker_of_the_line_leads_the_cast_even_with_no_present_mention(tmp_path) -> None:
    rows, _ = _render(tmp_path)
    mrs_line, mr_line = _panel_over(rows, 2), _panel_over(rows, 3)
    assert mrs_line.cast and mrs_line.cast[0].self_id == MRS
    assert mr_line.cast and mr_line.cast[0].self_id == MR


def test_the_listener_is_still_in_the_cast(tmp_path) -> None:
    rows, _ = _render(tmp_path)
    assert {c.self_id for c in _panel_over(rows, 2).cast} == {MRS, MR}


def test_the_director_is_handed_the_speaker_in_cast(tmp_path) -> None:
    _, director = _render(tmp_path)
    cast_lines = [next(ln for ln in p.splitlines() if ln.startswith("CAST")) if any(ln.startswith("CAST") for ln in p.splitlines()) else "" for p in director.prompts]
    assert any("Mrs. Bennet" in c for c in cast_lines), cast_lines


def test_mrs_bennet_is_not_a_figure_who_appears_only_when_named(tmp_path) -> None:
    rows, _ = _render(tmp_path)
    drawn = [r for r in rows if any(c.self_id == MRS for c in r.cast)]
    assert len(drawn) >= 2, [[c.label for c in r.cast] for r in rows]
