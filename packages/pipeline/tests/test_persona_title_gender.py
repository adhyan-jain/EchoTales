"""A gender title in a character's canonical name wins over pronoun counts and over the model (P&P e2e 2026-11-22).

Mr. Bennet was stored `female`: the narration around his name is mostly about his wife ("her mind", "she was a woman of
mean understanding"), so a pronoun count or a small model read the paragraph, not the man. A title that is part of the name
is the one cue that is about this character and nothing else. Synthetic text only.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from echotales.pipeline.persona.extract import CharacterProfileResponse, extract_traits
from echotales.pipeline.persona.traits import infer_traits_deterministic, title_gender

#: The pattern from P&P ch1: narration about the couple, written mostly about her.
ABOUT_HER = ["She was a woman of mean understanding. Her mind was less difficult. She said her piece. She sighed."] * 3
ABOUT_HIM = ["He was sarcastic. His wife did not understand him. He replied that he had not."] * 3


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Mr. Bennet", "male"), ("Mr Bennet", "male"), ("MR. BENNET", "male"), ("Sir William Lucas", "male"),
        ("Mrs. Bennet", "female"), ("Mrs Bennet", "female"), ("Miss Bennet", "female"), ("Ms. Lee", "female"),
        ("Lady Catherine", "female"), ("Madam Pomfrey", "female"),
        # not a title in the name, or no single side: nothing is claimed
        ("Bennet", None), ("Mr. and Mrs. Bennet", None), ("Master Chen", None), ("Lord Yao Ji", None), ("Misty Rain", None),
    ],
)
def test_title_gender_reads_only_a_title_that_is_part_of_the_name(label: str, expected: str | None) -> None:
    assert title_gender(label) == expected


def test_mr_wins_over_a_female_pronoun_majority() -> None:
    profile = infer_traits_deterministic("t:s", "Mr. Bennet", surfaces=["Mr. Bennet"], pronoun_passages=ABOUT_HER)
    assert profile.gender == "male"
    assert any("title" in n for n in profile.notes)


def test_mrs_wins_over_a_male_pronoun_majority() -> None:
    profile = infer_traits_deterministic("t:s", "Mrs. Bennet", surfaces=["Mrs. Bennet"], pronoun_passages=ABOUT_HIM)
    assert profile.gender == "female"


def test_the_anchored_pronoun_cue_does_not_beat_the_title_either() -> None:
    profile = infer_traits_deterministic(
        "t:s", "Mr. Bennet", surfaces=["Mr. Bennet"], pronoun_passages=[], anchor_windows=[", she", " and her", ", she"]
    )
    assert profile.gender == "male"


def test_a_pronoun_still_outranks_a_title_that_is_not_in_the_name() -> None:
    """RI measurement kept: "Lord Yao Ji" is a woman and translated xianxia uses Lord for both."""
    profile = infer_traits_deterministic("t:s", "Lord Yao Ji", surfaces=["Lord Yao Ji"], pronoun_passages=ABOUT_HER)
    assert profile.gender == "female"


class _FemaleModel:
    """A small model that read the wife's paragraphs and answered female."""

    def complete(self, task, prompt, schema, *, system="", novel_id="", **_):  # noqa: ANN001, ANN003, ANN201
        return SimpleNamespace(value=CharacterProfileResponse(gender="female", age_band="adult", speech_register="neutral"))


def test_the_model_cannot_overwrite_a_gender_the_title_fixed() -> None:
    base = infer_traits_deterministic("t:s", "Mr. Bennet", surfaces=["Mr. Bennet"], pronoun_passages=ABOUT_HER)
    out = extract_traits(base, dialogue=["My dear Mrs. Bennet"], narration=ABOUT_HER, client=_FemaleModel())
    assert out.provenance == "llm" and out.gender == "male"


def test_the_model_still_decides_when_the_name_carries_no_title() -> None:
    base = infer_traits_deterministic("t:s", "Elizabeth", surfaces=["Elizabeth"], pronoun_passages=[])
    out = extract_traits(base, dialogue=["Hello"], narration=ABOUT_HER, client=_FemaleModel())
    assert out.gender == "female"
