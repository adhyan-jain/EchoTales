"""A two-scene, one-segment chapter plus a fake director, for the panel-plan tests.

The chapter is built so one `NarrativeSegment` holds two scenes (courtyard,
then the temple, then a cave) and one scene has a crowd cut -- the shapes the
plan record and the scene-state key have to get right. No model is involved.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from echotales.core.enums import (
    OBSERVER_READER,
    AliasType,
    BlockType,
    ReferenceMode,
    SpanType,
    TargetKind,
)
from echotales.core.models import (
    Block,
    Chapter,
    DiscoursePosition,
    Mention,
    NarrativeSegment,
    Self,
    Span,
)
from echotales.core.store import Store
from echotales.pipeline.persona.split import BodyEpoch, write_epochs
from echotales.pipeline.render.direction import PanelDirection

TEXTS = [
    (BlockType.HEADING, "Chapter 1"),
    (BlockType.PROSE, "Fang Yuan stood in the walled stone courtyard, watching the mist."),
    (BlockType.PROSE, '"Old bastard Fang, stop resisting," a voice shouted from the wall.'),
    (BlockType.PROSE, "Fang Yuan did not answer. His expression stayed calm."),
    (BlockType.PROSE, "The mist thickened over the stone walls."),
    (BlockType.PROSE, "A bell rang somewhere beyond the wall."),
    (BlockType.PROSE, "He walked on toward the ancestral temple where the elders gathered."),
    (BlockType.PROSE, "Inside the ancestral temple, Bai Ning waited beside the incense."),
    (BlockType.PROSE, '"You are late," Bai Ning said.'),
    (BlockType.PROSE, "A crowd of clansmen surrounded them, shouting."),
    (BlockType.PROSE, "Fang Yuan lowered his head."),
    (BlockType.PROSE, "Outside, the cave mouth glowed with torchlight."),
    (BlockType.PROSE, "Fang Yuan drew a slow breath in the dark cave."),
]
NOVEL = "t"


def build_store(path: Path) -> Store:
    store = Store(str(path))
    store.add_novel(NOVEL, "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id=NOVEL, number=1.0, title="T", source_href="a.html",
            blocks=[Block(index=i, block_type=bt, text=tx) for i, (bt, tx) in enumerate(TEXTS)],
        )
    )
    names = (("t:fang", "Fang Yuan"), ("t:bai", "Bai Ning"))
    for sid, label in names:
        store.add_self(
            Self(
                id=sid, novel_id=NOVEL, canonical_label=label,
                first_attested_pos=DiscoursePosition(chapter=1, offset=0), kind=TargetKind.SELF,
            )
        )
        # A bound persona is what makes a self part of a panel's cast.
        write_epochs(
            store, NOVEL, store.get_self(sid),
            [BodyEpoch(index=0, persona_id=f"{sid}:body1", body_label=label, from_pos=1.0,
                       to_pos=None, cause="birth", evidence="")],
            observer_id=OBSERVER_READER,
        )
    mentions = [
        Mention(
            id=f"m{i}{sid}", novel_id=NOVEL, segment_id="s1", chapter=1.0, offset=i * 100,
            block_index=i, text=label, alias_type=AliasType.RIGID_NAME,
            span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT,
            target_kind=TargetKind.SELF, target_id=sid,
        )
        for i, (_bt, tx) in enumerate(TEXTS)
        for sid, label in names
        if label in tx
    ]
    store.add_mentions(mentions)
    spans: list[Span] = []
    for i, (bt, tx) in enumerate(TEXTS):
        if bt is not BlockType.PROSE:
            continue
        pieces: list[tuple[int, int, SpanType]] = [(0, len(tx), SpanType.NARRATION_ACTION)]
        if '"' in tx:
            a, b = tx.index('"'), tx.rindex('"') + 1
            pieces = [(a, b, SpanType.DIALOGUE)]
            if a:
                pieces.append((0, a, SpanType.NARRATION_ACTION))
            if b < len(tx):
                pieces.append((b, len(tx), SpanType.NARRATION_ACTION))
        spans += [
            Span(id=f"sp{i}_{s}", novel_id=NOVEL, chapter=1.0, block_index=i, start=s, end=e,
                 span_type=t, text=tx[s:e])
            for s, e, t in pieces
        ]
    store.add_spans(spans)
    store.add_segments(
        [
            NarrativeSegment(
                id="s1", novel_id=NOVEL, chapter_from=1.0, offset_from=0, chapter_to=1.0,
                offset_to=10**6, story_seq_from=1, story_seq_to=1,
            )
        ]
    )
    store.conn.commit()
    return store


_SHOTS = ("wide", "close", "medium")


class FakeDirector:
    """Returns a fixed, call-order-determined `PanelDirection`; never a model.

    Cycling through all three shots matters: the negative-prompt style bucket
    follows the director's `shot`, so a single shot would hide a two-phase
    difference.
    """

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, task, prompt, schema, **kwargs):
        if schema is not PanelDirection:  # the scene staging call is not a panel and must not advance the shot cycle
            return SimpleNamespace(value=None)
        shot = _SHOTS[self.calls % len(_SHOTS)]
        self.calls += 1
        return SimpleNamespace(
            value=PanelDirection(
                shot=shot,
                action=f"standing quietly, hand_on_chest, beat{self.calls}",
                layout="Fang Yuan, solo, centered" if shot != "wide" else "wide_view, surrounded",
                setting="stone_courtyard, mist",
                lighting="dusk, misty",
                key_objects=["lantern"],
                mood="tense",
                expression="calm_expression",
            )
        )


def manifest_rows(version_dir: Path) -> dict[int, dict]:
    """Per-block (prompt, negative prompt, cache key) as the version's manifest recorded them."""
    out = {}
    for line in (version_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        out[row["block_index"]] = {
            "prompt": row["prompt"],
            "negative_prompt": row["negative_prompt"],
            "cache_key": row["cache_key"],
        }
    return out
