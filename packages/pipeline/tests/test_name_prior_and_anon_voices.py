"""First-name gender prior for casting, and stable voices for anonymous slots (P&P e2e 2026-11-22, defects 13, 15).

Kitty, Lydia and Maria Lucas have no own pronoun in the text, so they stayed gender-unknown and Lydia was cast a
male voice. A first name that is overwhelmingly one gender in public records steers casting only; it is never a graph
fact. Unknown Speaker slots took a different voice whenever another character's casting moved. Synthetic text only.
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
from echotales.pipeline.persona import build_personas, load_trait_profiles
from echotales.pipeline.persona.first_names import name_gender_prior
from echotales.pipeline.persona.gender import gender_lean, gender_lean_basis
from echotales.pipeline.voice.bank import VoiceBank, parse_speaker_info
from echotales.pipeline.voice.casting import cast_voices
from echotales.pipeline.voice.engine import get_engine
from echotales.pipeline.voice.runner import render_novel

BANK = "ID  AGE  GENDER  ACCENTS  REGION\n" + "".join(
    f"p{300 + i}  30  {g}    English    Surrey\n" for i, g in enumerate("FFMMMM")
)


def _book(tmp_path: Path, label: str, paragraphs: list[str]) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t", number=1.0, title="T", source_href="a.html",
            blocks=[Block(index=i, block_type=BlockType.PROSE, text=p) for i, p in enumerate(paragraphs)],
        )
    )
    kind = SpanType.NARRATION_ACTION
    store.add_spans(
        [Span(id=f"t:1:{i}:0", novel_id="t", chapter=1.0, block_index=i, start=0, end=len(p), span_type=kind, text=p)
         for i, p in enumerate(paragraphs)]
    )
    store.add_self(
        Self(id="t:self1", novel_id="t", canonical_label=label, kind=TargetKind.SELF,
             first_attested_pos=DiscoursePosition(chapter=1, offset=0))
    )
    surface = label.split()[0]
    store.add_mentions(
        [
            Mention(
                id=f"m{i}", novel_id="t", segment_id="s", chapter=1.0, offset=max(p.find(surface), 0), block_index=i,
                text=surface, alias_type=AliasType.RIGID_NAME, span_type=kind,
                reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id="t:self1",
            )
            for i, p in enumerate(paragraphs)
        ]
    )
    store.conn.commit()
    build_personas("t", store)
    return store


def test_the_table_knows_strongly_leaning_first_names_and_nothing_else() -> None:
    assert name_gender_prior("Lydia") == "female"
    assert name_gender_prior("Kitty") == "female"
    assert name_gender_prior("Maria Lucas") == "female"
    assert name_gender_prior("George") == "male"
    assert name_gender_prior("Mr. Bennet") is None  # a title is not a first name
    assert name_gender_prior("Zzyzx Wuxian") is None  # absent from the table: unknown stays unknown
    assert name_gender_prior("Kai") is None  # mixed: not a strong lean


def test_a_name_with_no_pronoun_evidence_leans_by_its_first_name(tmp_path: Path) -> None:
    store = _book(tmp_path, "Lydia", ["Lydia was stout.", "Lydia danced, said the room."])
    assert gender_lean(store, "t", {"t:self1"}) == {"t:self1": "female"}
    # a steer, not a fact: nothing is written to the graph
    assert load_trait_profiles("t", store)["t:self1"].gender == "unknown"


def test_the_first_name_of_a_longer_label_counts(tmp_path: Path) -> None:
    store = _book(tmp_path, "Maria Lucas", ["Maria went in.", "Maria sat."])
    assert gender_lean(store, "t", {"t:self1"}) == {"t:self1": "female"}


def test_an_unlisted_name_stays_unknown(tmp_path: Path) -> None:
    store = _book(tmp_path, "Zzyzx", ["Zzyzx went in.", "Zzyzx sat."])
    assert gender_lean(store, "t", {"t:self1"}) == {}


def test_pronoun_evidence_wins_and_conflicting_pronouns_cancel_the_prior(tmp_path: Path) -> None:
    male = _book(tmp_path, "Lydia", ["Lydia laughed, shaking his head."])
    assert gender_lean(male, "t", {"t:self1"}) == {"t:self1": "male"}
    (tmp_path / "t.db").unlink()
    mixed = _book(tmp_path, "Lydia", ["Lydia laughed, shaking her head.", "Lydia sighed, rubbing his eyes."])
    assert gender_lean(mixed, "t", {"t:self1"}) == {}


def test_casting_uses_the_prior_and_the_report_names_it(tmp_path: Path) -> None:
    store = _book(tmp_path, "Lydia", ["Lydia was stout.", "Lydia danced."])
    profiles = load_trait_profiles("t", store)
    bank = VoiceBank(voices=parse_speaker_info(BANK))
    basis = gender_lean_basis(store, "t", {"t:self1"})
    assert basis == {"t:self1": ("female", "name prior")}
    assignments, report = cast_voices(
        "t", profiles, bank, store=store,
        lean={t: side for t, (side, _) in basis.items()}, lean_basis={t: how for t, (_, how) in basis.items()},
    )
    voice = next(v for v in bank.voices if v.speaker_id == assignments["t:self1"].speaker_id)
    assert voice.gender == "female"
    assert report.name_prior == ["Lydia"]
    assert "name prior" in report.summary()


# ---------------------------------------------------------------------------- anonymous slots

ANON_BANK = "ID  AGE  GENDER  ACCENTS  REGION\n" + "".join(
    f"p{200 + i}  30  {g}    English    Surrey\n" for i, g in enumerate("FFFFFFFFFFMMMMMMMMMM")
)
SLOTS = [f"t:anon:1:{n}" for n in range(1, 5)]


def _anon_book(path: Path, named: list[tuple[str, str]]) -> Store:
    """Four anonymous slots, each speaking once, plus `named` (label, own-pronoun) characters who speak too."""
    path.mkdir()
    store = Store(str(path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    texts = [f'"Line {n}," someone said.' for n in range(len(SLOTS))]
    texts += [f'"Hello," {label} said, {pron} hat on.' for label, pron in named]
    store.add_chapter(
        Chapter(novel_id="t", number=1.0, title="T", source_href="a.html",
                blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(texts)])
    )
    spans, mentions = [], []
    for i, t in enumerate(texts):
        slot = SLOTS[i] if i < len(SLOTS) else None
        label = None if slot else named[i - len(SLOTS)][0]
        spans.append(Span(
            id=f"sp{i}", novel_id="t", chapter=1.0, block_index=i, start=0, end=len(t), span_type=SpanType.DIALOGUE,
            text=t, speaker_self_id=slot or label,
            attribution_method=AttributionMethod.ANONYMOUS_SLOT if slot else AttributionMethod.EXPLICIT,
        ))
        if label:
            sid = f"t:{label.lower()}"
            store.add_self(Self(id=sid, novel_id="t", canonical_label=label, kind=TargetKind.SELF,
                                first_attested_pos=DiscoursePosition(chapter=1, offset=i)))
            mentions.append(Mention(
                id=f"m{i}", novel_id="t", segment_id="s", chapter=1.0, offset=t.index(label), block_index=i,
                text=label, alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id=sid))
    store.add_spans(spans)
    store.add_mentions(mentions)
    store.conn.commit()
    build_personas("t", store)
    store.conn.commit()
    return store


def _run(tmp_path: Path, name: str, named: list[tuple[str, str]]) -> tuple[dict[str, str], str]:
    store = _anon_book(tmp_path / f"db_{name}", named)
    out = tmp_path / name
    bank = VoiceBank(voices=parse_speaker_info(ANON_BANK))
    render_novel("t", store, bank, out_dir=out, engine=get_engine("stub"), synthesize=False)
    rows = [json.loads(x) for x in (out / "manifest.jsonl").read_text().splitlines() if x.strip()]
    return {r["speaker_id"]: r["voice"] for r in rows if ":anon:" in r["speaker_id"]}, bank.voices[0].speaker_id


def test_anonymous_slots_never_take_the_narrator_voice_and_differ_from_each_other(tmp_path: Path) -> None:
    from echotales.pipeline.voice.runner import _narrator_voice

    voices, _ = _run(tmp_path, "a", [])
    narrator = _narrator_voice(VoiceBank(voices=parse_speaker_info(ANON_BANK)))
    assert set(voices) == set(SLOTS)
    assert narrator not in voices.values()
    assert len(set(voices.values())) == len(SLOTS)


def test_a_slot_keeps_its_voice_when_other_characters_are_cast_differently(tmp_path: Path) -> None:
    alone, _ = _run(tmp_path, "a", [])
    crowded, _ = _run(tmp_path, "b", [("Anna", "her"), ("Ben", "his"), ("Cora", "her"), ("Dan", "his")])
    assert crowded == alone


def test_a_named_character_never_takes_a_voice_an_unknown_speaker_slot_can_take(tmp_path: Path) -> None:
    out = tmp_path / "c"
    store = _anon_book(tmp_path / "db_c", [("Anna", "her"), ("Ben", "his"), ("Cora", "her"), ("Dan", "his")])
    bank = VoiceBank(voices=parse_speaker_info(ANON_BANK))
    render_novel("t", store, bank, out_dir=out, engine=get_engine("stub"), synthesize=False)
    rows = [json.loads(x) for x in (out / "manifest.jsonl").read_text().splitlines() if x.strip()]
    slot = {r["voice"] for r in rows if ":anon:" in r["speaker_id"]}
    named = {r["voice"] for r in rows if r["speaker_label"] in ("Anna", "Ben", "Cora", "Dan")}
    assert named and not slot & named
