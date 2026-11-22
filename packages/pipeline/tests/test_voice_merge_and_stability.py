"""Voice casting after a merge, and across re-runs (P&P e2e 2026-11-22, defects 12, 14).

12. After `merge_entities(Lizzy -> Elizabeth)` the next voice run still cast two voices, and one dialogue line still
    credited Lizzy: the merge rebound mentions only, so the absorbed entity kept its persona, its trait profile and
    the `speaker_self_id` of its spans.
14. Re-voicing after a bible re-lock moved Mr. Bennet to another voice: casting drew its tie-breaks from one rng
    stream in profile order, so any change in the cast (a new entity, a merge) reshuffled everyone.
Synthetic text only.
"""

from __future__ import annotations

import json
from pathlib import Path

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
from echotales.pipeline.corrections import Correction, CorrectionType, _apply_merge
from echotales.pipeline.persona import build_personas, load_trait_profiles
from echotales.pipeline.voice.bank import VoiceBank, parse_speaker_info
from echotales.pipeline.voice.engine import get_engine
from echotales.pipeline.voice.runner import render_novel

#: Four adult women and four adult men: enough that a re-roll would land elsewhere.
INFO = "ID  AGE  GENDER  ACCENTS  REGION\n" + "".join(
    f"p{200 + i}  30  {g}    English    Surrey\n" for i, g in enumerate("FFFFMMMM")
)

TEXTS = [
    '"Hello," Elizabeth said.',
    '"Good day," Lizzy said.',
    '"Well," Mr. Bennet said.',
    "Elizabeth smiled at Lizzy.",
]


def _bank() -> VoiceBank:
    return VoiceBank(voices=parse_speaker_info(INFO))


def _store(tmp_path: Path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t", number=1.0, title="One", source_href="a.html",
            blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(TEXTS)],
        )
    )
    names = {"t:eliz": "Elizabeth", "t:lizzy": "Lizzy", "t:bennet": "Mr. Bennet"}
    for i, (sid, label) in enumerate(names.items()):
        store.add_self(
            Self(id=sid, novel_id="t", canonical_label=label,
                 first_attested_pos=DiscoursePosition(chapter=1.0, offset=i), kind=TargetKind.SELF)
        )
    mentions = [
        ("t:eliz", "Elizabeth", 0, 0), ("t:lizzy", "Lizzy", 1, 0), ("t:bennet", "Mr. Bennet", 2, 0),
        ("t:eliz", "Elizabeth", 3, 0), ("t:lizzy", "Lizzy", 3, 20),
    ]
    store.add_mentions(
        [
            Mention(
                id=f"m{i}", novel_id="t", segment_id="s", chapter=1.0, offset=off, block_index=block, text=text,
                alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id=sid,
            )
            for i, (sid, text, block, off) in enumerate(mentions)
        ]
    )
    # Speaker ids as the reader writes them: a Self id for some lines, a surface label for others.
    speakers = ["t:eliz", "t:lizzy", "Mr. Bennet", None]
    store.add_spans(
        [
            Span(
                id=f"sp{i}", novel_id="t", chapter=1.0, block_index=i, start=0, end=len(TEXTS[i]),
                span_type=SpanType.DIALOGUE if speakers[i] else SpanType.NARRATION_ACTION, text=TEXTS[i],
                speaker_self_id=speakers[i],
                attribution_method=AttributionMethod.EXPLICIT if speakers[i] else AttributionMethod.UNRESOLVED,
            )
            for i in range(4)
        ]
    )
    store.conn.commit()
    build_personas("t", store)
    store.conn.commit()
    return store


def _merge(store: Store, from_id: str, into_id: str) -> None:
    _apply_merge(
        store, Correction(novel_id="t", type=CorrectionType.MERGE_ENTITIES, payload={"from_id": from_id, "into_id": into_id}),
        seq=store.next_seq(),
    )
    store.conn.commit()


def _voices(out: Path) -> dict[str, str]:
    rows = [json.loads(x) for x in (out / "manifest.jsonl").read_text().splitlines() if x.strip()]
    return {r["span_id"]: r["voice"] for r in rows}


def test_merged_alias_is_resolved_by_the_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge(store, "t:lizzy", "t:eliz")
    assert store.merged_into("t") == {"t:lizzy": "t:eliz"}


def test_merged_alias_follows_a_chain(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge(store, "t:lizzy", "t:eliz")
    _merge(store, "t:eliz", "t:bennet")
    assert store.merged_into("t") == {"t:lizzy": "t:bennet", "t:eliz": "t:bennet"}


def test_the_merge_moves_the_alias_spans_to_the_survivor(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge(store, "t:lizzy", "t:eliz")
    assert {s.speaker_self_id for s in store.get_spans("t", 1.0)} == {"t:eliz", "Mr. Bennet", None}


def test_a_merged_alias_has_no_trait_profile_so_it_is_not_cast(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge(store, "t:lizzy", "t:eliz")
    assert "t:lizzy" not in load_trait_profiles("t", store)
    assert "t:eliz" in load_trait_profiles("t", store)


def test_one_voice_after_the_merge_even_when_an_old_span_still_names_the_alias(tmp_path: Path) -> None:
    """A database merged before the spans were rewritten still has `t:lizzy` on a line."""
    store = _store(tmp_path)
    # the old merge: mentions rebound and the event logged, spans untouched
    for m in store.get_mentions("t", 1.0):
        if m.target_id == "t:lizzy":
            m.target_id = "t:eliz"
    store.add_mentions([m for m in store.get_mentions("t", 1.0) if m.target_id == "t:eliz"])
    from echotales.core.enums import EventType
    from echotales.core.models import ResolutionEvent

    store.append_event(
        ResolutionEvent(
            id="e1", seq=store.next_seq(), type=EventType.MERGE,
            payload={"from_id": "t:lizzy", "into_id": "t:eliz"}, cause_pos=DiscoursePosition(chapter=0, offset=0),
        )
    )
    store.conn.commit()
    out = tmp_path / "audio"
    render_novel("t", store, _bank(), out_dir=out, engine=get_engine("stub"), synthesize=False)
    voices = _voices(out)
    assert voices["sp0"] == voices["sp1"]
    lines = [json.loads(x) for x in (out / "manifest.jsonl").read_text().splitlines() if x.strip()]
    assert {ln["speaker_label"] for ln in lines if ln["span_id"] in ("sp0", "sp1")} == {"Elizabeth"}


def test_a_character_keeps_its_voice_when_the_cast_changes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = tmp_path / "a"
    render_novel("t", store, _bank(), out_dir=first, engine=get_engine("stub"), synthesize=False)
    base = _voices(first)

    # one more character joins the book; the shared rng stream used to shift every later tie-break
    store.add_self(
        Self(id="t:amy", novel_id="t", canonical_label="Amy",
             first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind=TargetKind.SELF)
    )
    store.add_mentions([
        Mention(id="mx", novel_id="t", segment_id="s", chapter=1.0, offset=30, block_index=3, text="Amy",
                alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id="t:amy")
    ])
    store.conn.commit()
    build_personas("t", store)
    store.conn.commit()
    second = tmp_path / "b"
    render_novel("t", store, _bank(), out_dir=second, engine=get_engine("stub"), synthesize=False)
    again = _voices(second)
    assert again["sp2"] == base["sp2"]  # Mr. Bennet
    assert again["sp0"] == base["sp0"]  # Elizabeth


def test_a_changed_gender_recasts_the_character(tmp_path: Path) -> None:
    from echotales.pipeline.persona.gender import write_gender

    store = _store(tmp_path)
    out = tmp_path / "a"
    render_novel("t", store, _bank(), out_dir=out, engine=get_engine("stub"), synthesize=False)
    first = {v.speaker_id: v.gender for v in _bank().voices}
    before = _voices(out)["sp2"]
    write_gender(store, "t", "t:bennet", "female" if first[before] == "male" else "male", "human: reviewer set gender",
                 confidence=1.0, at=DiscoursePosition(chapter=5, offset=0))
    store.conn.commit()
    out2 = tmp_path / "b"
    render_novel("t", store, _bank(), out_dir=out2, engine=get_engine("stub"), synthesize=False)
    after = _voices(out2)["sp2"]
    assert first[after] != first[before]


def test_a_voice_the_bank_no_longer_has_is_recast_not_kept(tmp_path: Path) -> None:
    store = _store(tmp_path)
    out = tmp_path / "a"
    render_novel("t", store, _bank(), out_dir=out, engine=get_engine("stub"), synthesize=False)
    gone = _voices(out)["sp2"]
    smaller = VoiceBank(voices=[v for v in _bank().voices if v.speaker_id != gone])
    out2 = tmp_path / "b"
    render_novel("t", store, smaller, out_dir=out2, engine=get_engine("stub"), synthesize=False)
    assert _voices(out2)["sp2"] != gone
