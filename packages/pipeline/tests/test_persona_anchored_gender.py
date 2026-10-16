"""The anchored pronoun cue under the evidence horizon (docs/research/PREFIX_FAITHFULNESS/PREREG_ANCHORED.md).

The paragraph rule needs six pronouns around a character, so an early prefix withholds a gender that one sentence already
states ("Mei stood, her sleeve trailing"). The anchored cue reads the first pronoun right after each mention. Synthetic
text only, so these tests run without any novel.
"""

from __future__ import annotations

import pytest

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.pipeline.persona import build_personas
from echotales.pipeline.persona.traits import anchored_window, gender_from_anchors, infer_traits_deterministic

NARRATION = {1: "Mei stood, her sleeve trailing.", 2: "Mei waited and she sighed.", 3: "Mei spoke."}
TRAIT_KEYS = ("age_band", "gender", "register", "archetype", "big_five")
ANCHORED = (2, 0.85)


def _volume(tmp_path, upto: int, tag: str, *, prefix_causal: bool, anchored) -> Store:
    store = Store(str(tmp_path / f"{tag}.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    for c in range(1, upto + 1):
        store.add_chapter(
            Chapter(novel_id="t", number=float(c), title="T", source_href=f"{c}.html",
                    blocks=[Block(index=0, block_type=BlockType.PROSE, text=NARRATION[c])])
        )
    store.add_self(Self(id="t:self1", novel_id="t", canonical_label="Mei",
                        first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind=TargetKind.SELF))
    store.add_spans([
        Span(id=f"sp{c}", novel_id="t", chapter=float(c), block_index=0, start=0, end=len(NARRATION[c]),
             span_type=SpanType.NARRATION_ACTION, text=NARRATION[c])
        for c in range(1, upto + 1)
    ])
    store.add_mentions([
        Mention(id=f"m{c}", novel_id="t", segment_id="s", chapter=float(c), offset=0, block_index=0, text="Mei",
                alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id="t:self1")
        for c in range(1, upto + 1)
    ])
    store.conn.commit()
    build_personas("t", store, prefix_causal=prefix_causal, anchored_gender=anchored)
    return store


def _traits_at_end_of_chapter(store: Store, k: int) -> dict[str, str]:
    res = StateResolver(store, "t")
    knowledge = DiscoursePosition(chapter=k, offset=10**6)
    st = res.state_of("t:self1", position=k + 0.5, knowledge_pos=knowledge)
    assert len(st.persona_ids) == 1
    attrs = res.state_of(st.persona_ids[0], target_kind=TargetKind.PERSONA, position=k + 0.5, knowledge_pos=knowledge).attributes
    return {key: attrs[key] for key in TRAIT_KEYS}


def test_window_stops_at_the_sentence_end_and_at_the_next_name() -> None:
    assert anchored_window(", his sword gleamed. Zhao laughed.") == ", his sword gleamed"
    assert anchored_window(" turned to Zhao and took her hand") == " turned to "
    assert anchored_window(" thought that I should go, and he left") == " thought that I should go, and he left"
    assert len(anchored_window(" x" * 200)) <= 160


def test_v2_window_cuts_at_clause_boundaries_and_unnamed_third_parties_only() -> None:
    # the two patterns behind the errors on the English originals
    assert anchored_window(", seeing the stranger lay his hand on his sword", "v2") == ", seeing "
    assert anchored_window("; he cast a passing glance at", "v2") == ""
    assert anchored_window(" turned, looking at the young man; and he left", "v2") == " turned, looking at "
    # a real own cue must survive: no determiner plus role noun, no clause boundary before the pronoun
    assert anchored_window(" stood on the deck, his body undulating", "v2") == " stood on the deck, his body undulating"
    assert anchored_window(" waited and she sighed", "v2") == " waited and she sighed"
    # v1 is untouched by the new argument
    assert anchored_window(", seeing the stranger lay his hand on his sword") == ", seeing the stranger lay his hand on his sword"
    assert anchored_window("; he cast a passing glance at", "v1") == "; he cast a passing glance at"


@pytest.mark.parametrize(
    ("windows", "min_obs", "majority", "expected"),
    [
        ([", her sleeve"], 1, 0.8, "female"),
        ([", her sleeve"], 2, 0.8, None),  # a single observation is below the floor
        ([", her", " and she", " and he"], 2, 0.8, None),  # 2/3 is not a majority of 0.8
        ([", her", " and she", " and he"], 2, 0.6, "female"),
        ([" and he", " his", " him"], 3, 1.0, "male"),
        ([" stood", " sat"], 1, 0.8, None),  # no pronoun, no observation
    ],
)
def test_anchored_decision_rule(windows, min_obs, majority, expected) -> None:
    assert gender_from_anchors(windows, min_obs=min_obs, majority=majority)[0] == expected


def test_anchored_cue_is_a_fallback_and_the_paragraph_rule_wins_when_it_calls() -> None:
    thin = ["Mei stood, her sleeve trailing."]  # 1 pronoun: below the paragraph floor of 6
    base = infer_traits_deterministic("t:s", "Mei", pronoun_passages=thin)
    assert base.gender == "unknown"  # default call unchanged
    with_anchor = infer_traits_deterministic("t:s", "Mei", pronoun_passages=thin, anchor_windows=[", her", " and she"],
                                             anchor_min_obs=2, anchor_majority=0.85)
    assert with_anchor.gender == "female"
    strong_male = ["He drew his sword and he turned; his boots, his cloak, and he bowed to him."]
    assert infer_traits_deterministic("t:s", "Mei", pronoun_passages=strong_male, anchor_windows=[", her", " she"],
                                      anchor_min_obs=2, anchor_majority=0.85).gender == "male"


def test_off_by_default_the_early_prefix_stays_unknown(tmp_path) -> None:
    full = _volume(tmp_path, 3, "off", prefix_causal=True, anchored=None)
    assert [_traits_at_end_of_chapter(full, k)["gender"] for k in (1, 2, 3)] == ["unknown", "unknown", "unknown"]


def test_anchored_reveals_the_gender_exactly_when_its_second_observation_arrives(tmp_path) -> None:
    full = _volume(tmp_path, 3, "reveal", prefix_causal=True, anchored=ANCHORED)
    assert [_traits_at_end_of_chapter(full, k)["gender"] for k in (1, 2, 3)] == ["unknown", "female", "female"]


@pytest.mark.parametrize("k", [1, 2, 3])
@pytest.mark.parametrize("truncated_prefix_causal", [True, False])
def test_anchored_repair_equals_a_build_over_the_prefix_at_every_cut(tmp_path, k: int, truncated_prefix_causal: bool) -> None:
    """The audit compares the full repaired build with a truncated build that uses the same extractor."""
    full = _volume(tmp_path, 3, "full_a", prefix_causal=True, anchored=ANCHORED)
    prefix = _volume(tmp_path, k, f"k{k}_{truncated_prefix_causal}", prefix_causal=truncated_prefix_causal, anchored=ANCHORED)
    assert _traits_at_end_of_chapter(full, k) == _traits_at_end_of_chapter(prefix, k)
