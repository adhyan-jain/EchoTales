"""Prefix causality of the persona trait stage (docs/research/PREFIX_FAITHFULNESS/REPORT.md).

The persona stage used to stamp every trait at the chapter of first sighting while computing it from up to twelve
later chapters. `state_of(READER)` then served, at the end of chapter 2, a gender whose only evidence is in chapter 3.
Measured on 3 serials: 23 of 289 character-cuts differed from a build over the prefix alone. These tests pin the
mechanism on a synthetic three-chapter volume, invented text only, so they run without any novel.
"""

from __future__ import annotations

import pytest

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.pipeline.persona import build_personas

# Chapters 1 and 2 name the character without gendering them; the pronoun evidence arrives in chapter 3.
NARRATION = {
    1: "Mei stood.",
    2: "Mei waited.",
    3: "Mei spoke. She raised her hand, and her voice was calm as she steadied herself. Her sleeve fell.",
}
TRAIT_KEYS = ("age_band", "gender", "register", "archetype", "big_five")


def _volume(tmp_path, upto: int, tag: str, *, prefix_causal: bool, dialogue: bool = False, client=None, floor: int = 25) -> Store:
    """A store holding chapters 1..upto only, with the persona stage already run.

    `dialogue=True` adds one attributed spoken line in chapter 1. Extraversion is dialogue lines divided by the
    mention count, so it is the one trait that also reads the whole-volume count; on the three real serials no
    character had a dialogue line in its evidence sample, so that path is exercised here and nowhere else.
    """
    store = Store(str(tmp_path / f"{tag}.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    for c in range(1, upto + 1):
        store.add_chapter(
            Chapter(
                novel_id="t", number=float(c), title="T", source_href=f"{c}.html",
                blocks=[Block(index=0, block_type=BlockType.PROSE, text=NARRATION[c])],
            )
        )
    store.add_self(
        Self(
            id="t:self1", novel_id="t", canonical_label="Mei",
            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind=TargetKind.SELF,
        )
    )
    store.add_spans(
        [
            Span(
                id=f"sp{c}", novel_id="t", chapter=float(c), block_index=0, start=0, end=len(NARRATION[c]),
                span_type=SpanType.NARRATION_ACTION, text=NARRATION[c],
            )
            for c in range(1, upto + 1)
        ]
    )
    if dialogue:
        store.add_spans(
            [
                Span(
                    id="dl1", novel_id="t", chapter=1.0, block_index=0, start=0, end=8,
                    span_type=SpanType.DIALOGUE, text='"Hello."', speaker_self_id="t:self1",
                )
            ]
        )
    store.add_mentions(
        [
            Mention(
                id=f"m{c}", novel_id="t", segment_id="s", chapter=float(c), offset=0, block_index=0, text="Mei",
                alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id="t:self1",
            )
            for c in range(1, upto + 1)
        ]
    )
    store.conn.commit()
    build_personas("t", store, prefix_causal=prefix_causal, client=client, llm_mention_floor=floor)
    return store


def _traits_at_end_of_chapter(store: Store, k: int) -> dict[str, str]:
    """The trait values state_of(READER) serves once chapter k has been read (the E6 query convention)."""
    res = StateResolver(store, "t")
    knowledge = DiscoursePosition(chapter=k, offset=10**6)
    st = res.state_of("t:self1", position=k + 0.5, knowledge_pos=knowledge)
    assert len(st.persona_ids) == 1
    attrs = res.state_of(
        st.persona_ids[0], target_kind=TargetKind.PERSONA, position=k + 0.5, knowledge_pos=knowledge
    ).attributes
    return {key: attrs[key] for key in TRAIT_KEYS}


def test_unrepaired_stage_serves_a_gender_the_prefix_cannot_know(tmp_path) -> None:
    """The defect, pinned. If this stops failing the audit's baseline no longer describes the code."""
    full = _volume(tmp_path, 3, "full_off", prefix_causal=False)
    prefix = _volume(tmp_path, 2, "k2_off", prefix_causal=False)
    served = _traits_at_end_of_chapter(full, 2)
    assert _traits_at_end_of_chapter(prefix, 2)["gender"] == "unknown"
    assert served["gender"] == "female"  # chapter 3's pronouns, stamped at the chapter of first sighting
    assert served["archetype"] != _traits_at_end_of_chapter(prefix, 2)["archetype"]


@pytest.mark.parametrize("k", [1, 2, 3])
def test_prefix_causal_matches_a_build_over_the_prefix_at_every_cut(tmp_path, k: int) -> None:
    full = _volume(tmp_path, 3, "full_on", prefix_causal=True)
    prefix = _volume(tmp_path, k, f"k{k}_on", prefix_causal=True)
    assert _traits_at_end_of_chapter(full, k) == _traits_at_end_of_chapter(prefix, k)


def test_prefix_causal_reveals_the_gender_exactly_when_its_evidence_arrives(tmp_path) -> None:
    full = _volume(tmp_path, 3, "full_reveal", prefix_causal=True)
    assert _traits_at_end_of_chapter(full, 1)["gender"] == "unknown"
    assert _traits_at_end_of_chapter(full, 2)["gender"] == "unknown"
    assert _traits_at_end_of_chapter(full, 3)["gender"] == "female"


def test_unrepaired_extraversion_divides_by_a_mention_count_from_chapters_not_yet_read(tmp_path) -> None:
    full = _volume(tmp_path, 3, "ext_full_off", prefix_causal=False, dialogue=True)
    prefix = _volume(tmp_path, 1, "ext_k1_off", prefix_causal=False, dialogue=True)
    # 1 spoken line / 1 mention in the prefix, 1 / 3 in the whole volume.
    assert _traits_at_end_of_chapter(full, 1)["big_five"] != _traits_at_end_of_chapter(prefix, 1)["big_five"]


@pytest.mark.parametrize("k", [1, 2, 3])
def test_prefix_causal_extraversion_follows_the_cumulative_mention_count(tmp_path, k: int) -> None:
    full = _volume(tmp_path, 3, "ext_full_on", prefix_causal=True, dialogue=True)
    prefix = _volume(tmp_path, k, f"ext_k{k}_on", prefix_causal=True, dialogue=True)
    assert _traits_at_end_of_chapter(full, k) == _traits_at_end_of_chapter(prefix, k)
    if k == 3:  # the value really moved across chapters, so the equality above is not trivial
        assert _traits_at_end_of_chapter(full, 1)["big_five"] != _traits_at_end_of_chapter(full, 3)["big_five"]


def test_default_path_writes_one_row_per_key(tmp_path) -> None:
    """Flag off must stay byte-compatible with what the stage always wrote: six keys, one row each."""
    full = _volume(tmp_path, 3, "full_rows", prefix_causal=False)
    rows = full.conn.execute("SELECT key FROM attribute WHERE novel_id='t'").fetchall()
    assert sorted(r["key"] for r in rows) == sorted((*TRAIT_KEYS, "trait_provenance"))


class _FakeClient:
    """Answers hashed from the prompt: identical prompts agree, different prompts differ. Counts calls."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, task, prompt, schema, *, system="", novel_id="", **_kw):  # noqa: ANN001, ANN003, ANN201
        import hashlib
        import types

        self.calls += 1
        h = int(hashlib.sha256(prompt.encode()).hexdigest(), 16)
        return types.SimpleNamespace(value=schema(gender=("male", "female")[h % 2], age_band="adult", speech_register="neutral",
                                                  extraversion=0.6))


def _served(store: Store, k: int) -> dict[str, str]:
    res = StateResolver(store, "t")
    knowledge = DiscoursePosition(chapter=k, offset=10**6)
    st = res.state_of("t:self1", position=k + 0.5, knowledge_pos=knowledge)
    return dict(res.state_of(st.persona_ids[0], target_kind=TargetKind.PERSONA, position=k + 0.5, knowledge_pos=knowledge).attributes)


def test_unrepaired_model_gate_uses_the_whole_volume_count(tmp_path) -> None:
    """The defect on the model path, pinned: with a floor of 2 the full volume (3 mentions) is model-read from the first stamp,
    a build over chapter 1 alone (1 mention) is not."""
    full = _volume(tmp_path, 3, "gate_full_off", prefix_causal=False, client=_FakeClient(), floor=2)
    prefix = _volume(tmp_path, 1, "gate_k1_off", prefix_causal=False, client=_FakeClient(), floor=2)
    assert _served(full, 1)["trait_provenance"] == "llm"
    assert _served(prefix, 1)["trait_provenance"] == "deterministic"


def test_prefix_causal_model_gate_follows_the_mentions_read_so_far(tmp_path) -> None:
    full = _volume(tmp_path, 3, "gate_full_on", prefix_causal=True, client=_FakeClient(), floor=2)
    assert [_served(full, k)["trait_provenance"] for k in (1, 2, 3)] == ["deterministic", "llm", "llm"]


@pytest.mark.parametrize("k", [1, 2, 3])
def test_prefix_causal_model_path_matches_a_build_over_the_prefix(tmp_path, k: int) -> None:
    full = _volume(tmp_path, 3, "mp_full", prefix_causal=True, client=_FakeClient(), floor=2)
    prefix = _volume(tmp_path, k, f"mp_k{k}", prefix_causal=True, client=_FakeClient(), floor=2)
    keys = (*TRAIT_KEYS, "trait_provenance")
    assert {x: _served(full, k)[x] for x in keys} == {x: _served(prefix, k)[x] for x in keys}


def test_prefix_causal_model_path_does_not_make_the_default_whole_volume_read(tmp_path) -> None:
    """One model read per chapter at which the prompt can change and the gate is open: chapters 2 and 3 here, not three."""
    client = _FakeClient()
    _volume(tmp_path, 3, "calls", prefix_causal=True, client=client, floor=2)
    assert client.calls == 2


def test_memo_client_asks_a_repeated_prompt_once() -> None:
    from echotales.pipeline.persona.build import _MemoClient

    inner = _FakeClient()
    memo = _MemoClient(inner)
    schema = __import__("echotales.pipeline.persona.extract", fromlist=["CharacterProfileResponse"]).CharacterProfileResponse
    a, b = memo.complete(None, "p", schema), memo.complete(None, "p", schema)
    memo.complete(None, "q", schema)
    assert a is b and inner.calls == 2
