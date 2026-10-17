"""The exposure screen's read-set table, checked against the real deterministic derivation (FORMAL.md P1).

The screen in scripts/prefix_audit/audit.py::horizons assigns each persona trait an evidence horizon read off the code by
hand: gender, age band, register and archetype read only the evidence sample of the first EVIDENCE_CHAPTERS attested
chapters; big_five additionally reads the whole-volume mention count, and only when the entity has dialogue. P1 says
the screen is sound exactly when that read set is a certificate, and the paper listed it as an unverified assumption
(Section 3.2, Section 10). These properties check it on the real `infer_traits_deterministic`: the inputs that carry
whole-volume information (mention_count, prominence, and dialogue_lines, a count over the same window) are varied freely
while the windowed evidence is held fixed, and every short-horizon key must not move.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from echotales.core.enums import Prominence
from echotales.pipeline.persona.build import _trait_values
from echotales.pipeline.persona.traits import infer_traits_deterministic

SHORT_HORIZON_KEYS = ("age_band", "gender", "register", "archetype")

_WORDS = ["he", "she", "him", "her", "his", "hers", "they", "the", "Elder", "Granny", "young master", "Lady", "Sir",
          "Madam", "Lord", "boy", "girl", "said", "walked", "Old", "Miss", "Mr.", "Brother", "Sister", "uncle", "aunt"]
_text = st.lists(st.sampled_from(_WORDS), min_size=0, max_size=40).map(" ".join)
_windowed = st.fixed_dictionaries(
    dict(surfaces=st.lists(_text, min_size=0, max_size=4), pronoun_passages=st.lists(_text, min_size=0, max_size=24),
         anchor_windows=st.one_of(st.none(), st.lists(_text, min_size=0, max_size=12)))
)
_volume = st.fixed_dictionaries(
    dict(mention_count=st.integers(0, 5000), dialogue_lines=st.integers(0, 2000), prominence=st.sampled_from(list(Prominence)))
)


def _values(windowed: dict, volume: dict) -> dict:
    return _trait_values(infer_traits_deterministic("e1", "label", **windowed, **volume))


@settings(max_examples=400, deadline=None)
@given(_windowed, _volume, _volume)
def test_short_horizon_keys_ignore_every_whole_volume_input(windowed, vol_a, vol_b):
    a, b = _values(windowed, vol_a), _values(windowed, vol_b)
    assert {k: a[k] for k in SHORT_HORIZON_KEYS} == {k: b[k] for k in SHORT_HORIZON_KEYS}


@settings(max_examples=400, deadline=None)
@given(_windowed, _volume, st.integers(0, 5000))
def test_big_five_reads_the_whole_volume_count_only_when_there_is_dialogue(windowed, vol, other_count):
    """The table's big_five horizon is `last` iff dialogue_total > 0, else the short window."""
    a = _values(windowed, vol)
    b = _values(windowed, dict(vol, mention_count=other_count))
    if vol["dialogue_lines"] == 0:
        assert a["big_five"] == b["big_five"]


def test_big_five_dependency_on_the_whole_volume_count_is_real():
    """The other direction: with dialogue, the whole-volume count does move big_five, so its long horizon is not over-cautious."""
    windowed = dict(surfaces=["Sir"], pronoun_passages=[], anchor_windows=None)
    a = _values(windowed, dict(mention_count=10, dialogue_lines=5, prominence=Prominence.RECURRING))
    b = _values(windowed, dict(mention_count=1000, dialogue_lines=5, prominence=Prominence.RECURRING))
    assert a["big_five"] != b["big_five"]
